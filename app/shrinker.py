# app/shrinker.py
from flask import Blueprint, render_template, request, jsonify, url_for
from app.db import get_db
from .app import sp

bp = Blueprint("shrinker", __name__, url_prefix="/shrinker")

def shrink_playlist(playlist_id, top_n):
    # 1) Fetch & sort tracks by popularity
    all_items = []
    results = sp.playlist_tracks(
        playlist_id,
        fields="items.track.id,items.track.popularity,next"
    )
    all_items.extend(results["items"])
    while results.get("next"):
        results = sp.next(results)
        all_items.extend(results["items"])

    valid = [
      i for i in all_items
      if i.get("track")
         and isinstance(i["track"].get("id"), str)
         and isinstance(i["track"].get("popularity"), int)
    ]
    valid.sort(key=lambda i: i["track"]["popularity"], reverse=True)
    uris = [f"spotify:track:{i['track']['id']}" for i in valid[:top_n]]

    # 2) Create the new playlist on Spotify
    original_name = sp.playlist(playlist_id)["name"]
    me            = sp.me()["id"]
    new_pl        = sp.user_playlist_create(me, f"Shrunk {top_n} of {original_name}", public=False)
    new_id        = new_pl["id"]
    # batch‐add in 100s
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(new_id, uris[i:i+100])

    # 3) Upsert user + playlist into your local SQLite
    db  = get_db()
    cur = db.cursor()

    # a) ensure user
    cur.execute("INSERT OR IGNORE INTO Users (SpotifyUserId) VALUES (?)", (me,))
    cur.execute("SELECT Id FROM Users WHERE SpotifyUserId = ?", (me,))
    owner_id = cur.fetchone()["Id"]

    # b) ensure original playlist row
    cur.execute("""
      INSERT OR IGNORE INTO Playlists
        (SpotifyPlaylistId, Name, OwnerId)
      VALUES (?, ?, ?)
    """, (playlist_id, original_name, owner_id))
    cur.execute("SELECT Id FROM Playlists WHERE SpotifyPlaylistId = ?", (playlist_id,))
    orig_db_id = cur.fetchone()["Id"]

    # c) now log the shrink
    cur.execute("""
      INSERT INTO ShrunkPlaylists
        (OriginalPlaylistId, NewSpotifyPlaylistId)
      VALUES (?, ?)
    """, (orig_db_id, new_id))

    db.commit()
    return new_id

@bp.route("/control")
def control():
    data  = sp.current_user_playlists(limit=50)["items"]
    picks = [{
      "id":    p["id"],
      "name":  p["name"],
      "total": p["tracks"]["total"]
    } for p in data]
    return render_template("shrinker.html", playlists=picks)

@bp.route("/shrink", methods=["POST"])
def do_shrink():
    # handle both JSON (AJAX) and form submits
    if request.is_json:
        payload = request.get_json()
        pid     = payload.get("playlist_id")
        top_n   = int(payload.get("top_n", 0))
    else:
        pid   = request.form.get("playlist_id")
        top_n = int(request.form.get("top_n", 0) or 0)

    if not pid or top_n <= 0:
        return jsonify({"error": "invalid input"}), 400

    new_id = shrink_playlist(pid, top_n)

    if request.is_json:
        return jsonify({"new_id": new_id})

    # fallback for non‐AJAX
    return f"""
    <script>
      window.open("https://open.spotify.com/playlist/{new_id}", "_blank");
      window.location = "{url_for('shrinker.control')}";
    </script>
    """
