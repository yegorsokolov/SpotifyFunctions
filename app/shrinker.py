# app/shrinker.py

import pyodbc
from flask import Blueprint, render_template, request, url_for, jsonify
from flask import redirect
from .app import sp, DB_CONN

bp = Blueprint("shrinker", __name__, url_prefix="/shrinker")

def shrink_playlist(playlist_id, top_n):
    original = sp.playlist(playlist_id)["name"]
    items = sp.playlist_tracks(playlist_id)["items"]
    sorted_items = sorted(items,
                          key=lambda i: i["track"]["popularity"],
                          reverse=True)
    uris = [i["track"]["uri"] for i in sorted_items[:top_n]]
    me = sp.me()["id"]
    new = sp.user_playlist_create(me, f"Shrunk {top_n} of {original}", public=False)
    sp.playlist_add_items(new["id"], uris)
    with pyodbc.connect(DB_CONN) as conn:
        cur = conn.cursor()
        cur.execute("""
          INSERT dbo.ShrunkPlaylists (OriginalPlaylistId, NewSpotifyPlaylistId)
            VALUES(
              (SELECT Id FROM dbo.Playlists WHERE SpotifyPlaylistId=?),
              ?
            );
        """, playlist_id, new["id"])
        conn.commit()
    return new["id"]

@bp.route("/control")
def control():
    data = sp.current_user_playlists(limit=50)
    picks = [{"id": p["id"], "name": p["name"], "total": p["tracks"]["total"]}
             for p in data["items"]]
    return render_template("shrinker.html", playlists=picks)

@bp.route("/shrink", methods=["POST"])
def do_shrink():
    # Accept JSON
    if request.is_json:
        body = request.get_json()
        pid = body["playlist_id"]
        top_n = int(body["top_n"])
    else:
        # fallback form-encoded
        pid = request.form["playlist_id"]
        top_n = int(request.form["top_n"])

    new_id = shrink_playlist(pid, top_n)
    # Return JSON—frontend will open the new tab
    return jsonify({"new_id": new_id})
