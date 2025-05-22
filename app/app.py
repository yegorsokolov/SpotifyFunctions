import os
from flask import Flask, redirect, url_for, render_template, request
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from apscheduler.schedulers.background import BackgroundScheduler

from app.db import get_db, init_db

# 1) Load environment variables
load_dotenv()

# 2) Ensure SQLite file & tables exist
init_db()

# 3) Set up Spotify OAuth & client (refresh token persists)
oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="playlist-read-private playlist-modify-private",
    show_dialog=False
)
sp = spotipy.Spotify(auth_manager=oauth)

# 4) Create Flask app
app = Flask(
    __name__,
    static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "../static")),
    template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "../templates"))
)
app.secret_key = os.urandom(24)

# 5) Login / logout / callback routes
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

# 6) Dashboard chooser route
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# 7) Sync helper: fetch & store playlists + tracks
def sync_all_playlists():
    """Fetch current Spotify playlists & tracks, mirror into SQLite, 
       and mark any missing as DeletedPlaylists."""
    # need app context to use get_db()
    with app.app_context():
        conn = get_db()
        cur = conn.cursor()

        # a) fetch current from Spotify
        current = {p["id"]: p for p in sp.current_user_playlists(limit=50)["items"]}
        spotify_user = sp.me()["id"]

        # b) upsert user
        cur.execute(
            "INSERT OR IGNORE INTO Users (SpotifyUserId) VALUES (?)",
            (spotify_user,)
        )
        cur.execute(
            "SELECT Id FROM Users WHERE SpotifyUserId = ?",
            (spotify_user,)
        )
        owner_id = cur.fetchone()["Id"]

        # c) for each playlist: upsert & sync tracks
        for pid, p in current.items():
            # playlist row
            cur.execute(
                "INSERT OR IGNORE INTO Playlists (SpotifyPlaylistId, Name, OwnerId) VALUES (?,?,?)",
                (pid, p["name"], owner_id)
            )
            cur.execute(
                "SELECT Id FROM Playlists WHERE SpotifyPlaylistId = ?",
                (pid,)
            )
            pl_db_id = cur.fetchone()["Id"]

            # fetch all tracks (paginated)
            all_items = []
            results = sp.playlist_tracks(pid,
                                         fields="items.track.id,next")
            all_items.extend(results["items"])
            while results.get("next"):
                results = sp.next(results)
                all_items.extend(results["items"])

            # clear & reinsert tracks
            cur.execute("DELETE FROM Tracks WHERE PlaylistId = ?", (pl_db_id,))
            for itm in all_items:
                track = itm.get("track")
                if track and track.get("id"):
                    cur.execute(
                        "INSERT INTO Tracks (PlaylistId, SpotifyTrackId) VALUES (?,?)",
                        (pl_db_id, track["id"])
                    )

        # d) mark deletions: any Playlist in DB not in current → DeletedPlaylists
        cur.execute("SELECT SpotifyPlaylistId, Name FROM Playlists")
        for db_pid, name in cur.fetchall():
            if db_pid not in current:
                cur.execute(
                    "INSERT OR IGNORE INTO DeletedPlaylists (SpotifyPlaylistId, Name) VALUES (?,?)",
                    (db_pid, name)
                )

        conn.commit()

# 8) Start background scheduler (runs every 0.2 minute)
scheduler = BackgroundScheduler()
scheduler.add_job(sync_all_playlists, 'interval', minutes=0.2, id='playlist_sync')
scheduler.start()

# 9) Run one sync immediately so recovery/cleanup pages aren’t empty
sync_all_playlists()

# 10) Register the shrinker, recovery, cleanup & reorder blueprints
from .shrinker import bp as shrink_bp
from .recovery import bp as recover_bp
from .cleanup import bp as cleanup_bp
from .reorder import bp as reorder_bp

app.register_blueprint(shrink_bp)
app.register_blueprint(recover_bp)
app.register_blueprint(cleanup_bp)
app.register_blueprint(reorder_bp)

if __name__ == "__main__":
    app.run(port=8888, debug=True)
