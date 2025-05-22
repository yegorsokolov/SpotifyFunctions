from flask import Blueprint, render_template, request, jsonify
from app.db import get_db
from .app import sp

bp = Blueprint("recovery", __name__, url_prefix="/recovery")

def restore_playlist_by_id(pid):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT Name, Id FROM Playlists WHERE SpotifyPlaylistId = ?", (pid,))
    row = cur.fetchone()
    if not row:
        return None
    name, db_id = row

    # Gather track URIs
    cur.execute("""
      SELECT SpotifyTrackId
        FROM Tracks
       WHERE PlaylistId = ?
       ORDER BY Id
    """, (db_id,))
    uris = [f"spotify:track:{r[0]}" for r in cur.fetchall()]

    # Create & populate the restored playlist
    me     = sp.me()["id"]
    new    = sp.user_playlist_create(me, f"Restored: {name}", public=False)
    new_id = new["id"]
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(new_id, uris[i:i+100])

    # Update our DB tables
    cur.execute(
      "UPDATE Playlists SET SpotifyPlaylistId = ? WHERE SpotifyPlaylistId = ?",
      (new_id, pid)
    )
    cur.execute(
      "DELETE FROM DeletedPlaylists WHERE SpotifyPlaylistId = ?",
      (pid,)
    )
    conn.commit()

    return new_id

@bp.route("/control")
def control():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT SpotifyPlaylistId, Name FROM DeletedPlaylists ORDER BY SpotifyPlaylistId DESC")
    plays = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    return render_template("recovery.html", playlists=plays)

@bp.route("/restore", methods=["POST"])
def do_restore():
    data   = request.get_json(force=True)
    pid    = data.get("playlist_id")
    new_id = restore_playlist_by_id(pid)
    if not new_id:
        return jsonify({"error": "not found"}), 404
    return jsonify({"new_id": new_id})
