import os
import pyodbc
from flask import Flask, redirect, url_for, render_template, request
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# 1) Load config
load_dotenv()
DB_CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_DATABASE')};"
    "Encrypt=no;TrustServerCertificate=yes;Trusted_Connection=yes;"
)

# 2) Spotify OAuth & client
oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="playlist-read-private playlist-modify-private",
    show_dialog=True
)
sp = spotipy.Spotify(auth_manager=oauth)

# 3) Flask setup
app = Flask(__name__,
            static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__),"../static")),
            template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__),"../templates")))
app.secret_key = os.urandom(24)

# 4) Login / logout / callback
@app.route("/")
def start():
    return render_template("start.html")

@app.route("/login")
def login():
    oauth.token_info = None
    return redirect(oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    oauth.get_access_token(code, as_dict=False)
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    path = getattr(oauth.cache_handler, "cache_path", None)
    if path and os.path.exists(path):
        os.remove(path)
    oauth.token_info = None
    return redirect("/")

# 5) Dashboard: sync & show two-tool chooser
@app.route("/dashboard")
def dashboard():
    # 1) fetch spotify playlists
    current = {p["id"]: p for p in sp.current_user_playlists(limit=50)["items"]}
    spotify_user = sp.me()["id"]

    with pyodbc.connect(DB_CONN) as conn:
        cur = conn.cursor()

        # upsert user & get its int PK
        cur.execute("""
          MERGE dbo.Users AS tgt
          USING (SELECT ? AS SpotifyUserId) AS src
            ON tgt.SpotifyUserId = src.SpotifyUserId
          WHEN NOT MATCHED THEN
            INSERT (SpotifyUserId) VALUES (src.SpotifyUserId);
        """, spotify_user)
        conn.commit()

        cur.execute("SELECT Id FROM dbo.Users WHERE SpotifyUserId=?", spotify_user)
        owner_id = cur.fetchone()[0]

        # insert new playlists
        for pid, p in current.items():
            cur.execute("""
              IF NOT EXISTS(SELECT 1 FROM dbo.Playlists WHERE SpotifyPlaylistId=?)
                INSERT dbo.Playlists(SpotifyPlaylistId, Name, OwnerId)
                  VALUES (?, ?, ?);
            """, pid, pid, p["name"], owner_id)

        # mark deletions
        cur.execute("SELECT SpotifyPlaylistId, Name FROM dbo.Playlists")
        for db_pid, name in cur.fetchall():
            if db_pid not in current:
                cur.execute("""
                  IF NOT EXISTS(SELECT 1 FROM dbo.DeletedPlaylists
                                 WHERE SpotifyPlaylistId=?)
                    INSERT dbo.DeletedPlaylists(SpotifyPlaylistId, Name)
                      VALUES (?, ?);
                """, db_pid, db_pid, name)

        conn.commit()

    return render_template("dashboard.html")

# 6) Register blueprints
from .shrinker import bp as shrink_bp
from .recovery import bp as recover_bp
app.register_blueprint(shrink_bp)
app.register_blueprint(recover_bp)
