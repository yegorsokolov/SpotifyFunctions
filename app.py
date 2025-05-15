import os
import pyodbc
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, render_template, request, redirect

# 1) Load environment
load_dotenv()

# 2) Spotipy client
# Extract SpotifyOAuth into its own object so we can reuse and reset it
oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="playlist-read-private playlist-modify-private",
    show_dialog=True          # <<< this forces the Spotify login/consent dialog every time
)

# Create your Spotify client once with that oauth manager
sp = spotipy.Spotify(auth_manager=oauth)

# 3) SQL Server ODBC connection
conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_DATABASE')};"
    f"UID={os.getenv('DB_USERNAME')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
    "Trusted_Connection=yes;"
)

def shrink_playlist(playlist_id, top_n=20):
    # 1) Fetch original playlist name
    original = sp.playlist(playlist_id)
    original_name = original["name"]

    # 2) Get and sort tracks
    items = sp.playlist_tracks(playlist_id)["items"]
    sorted_items = sorted(
        items,
        key=lambda i: i["track"]["popularity"],
        reverse=True
    )
    uris = [i["track"]["uri"] for i in sorted_items[:top_n]]

    # 3) Create the new playlist
    me = sp.me()["id"]
    new = sp.user_playlist_create(
        me,
        f"Shrunk {top_n} of {original_name}",
        public=False
    )

    # 4) Add tracks to it
    sp.playlist_add_items(new["id"], uris)

    # 5) (Optional) log user → SQL Server
    with pyodbc.connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute("""
          MERGE dbo.Users AS tgt
          USING (SELECT ? AS SpotifyUserId) AS src
          ON tgt.SpotifyUserId = src.SpotifyUserId
          WHEN NOT MATCHED THEN
            INSERT (SpotifyUserId) VALUES (src.SpotifyUserId);
        """, me)
        conn.commit()

    return new["id"]

# 4) Flask setup
app = Flask(__name__)
app.secret_key = os.urandom(24)  # for session

# --------------------------------
# 1) Start page
@app.route("/")
def start():
    return render_template("start.html")

# 2) Kick off OAuth
@app.route("/login")
def login():
    # Clear any in-memory token so we always start fresh
    oauth.token_info = None

    # Build the Spotify login URL & send the user there
    auth_url = oauth.get_authorize_url()
    return redirect(auth_url)

# 3) Handle the callback
@app.route("/callback")
def callback():
    code = request.args.get("code")
    oauth.get_access_token(code, as_dict=False)
    return redirect("/dashboard")


# 4) Dashboard: show playlist dropdown
@app.route("/dashboard")
def dashboard():
    data = sp.current_user_playlists(limit=50)
    playlists = [
      {
        "id": p["id"],
        "name": p["name"],
        "total": p["tracks"]["total"]      # <-- total track count
      }
      for p in data["items"]
    ]
    return render_template("dashboard.html", playlists=playlists)

# 5) Process the shrink
@app.route("/shrink", methods=["POST"])
def do_shrink():
    pid   = request.form["playlist_id"]
    top_n = int(request.form.get("top_n", 20))
    new_id = shrink_playlist(pid, top_n=top_n)
    return redirect(f"https://open.spotify.com/playlist/{new_id}")

# 6) Log out
@app.route("/logout")
def logout():
    # 1) Delete the cache file on disk
    cache_path = getattr(oauth.cache_handler, "cache_path", None)
    if cache_path and os.path.exists(cache_path):
        os.remove(cache_path)

    # 2) Clear any in-memory token
    oauth.token_info = None

    # 3) Send user back to the start page
    return redirect("/")
# --------------------------------

if __name__ == "__main__":
    # Make Flask listen on port 8888 to match your redirect URI
    app.run(port=8888, debug=True)
