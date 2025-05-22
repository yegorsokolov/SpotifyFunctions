from flask import Blueprint, render_template, request, redirect, url_for
from app.db import get_db

bp = Blueprint("cleanup", __name__, url_prefix="/cleanup")

@bp.route("/control")
def control():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT SpotifyPlaylistId, Name FROM DeletedPlaylists ORDER BY Name;")
    deleted = [{"id": pid, "name": name} for pid, name in cur.fetchall()]
    return render_template("cleanup.html", playlists=deleted)

@bp.route("/delete", methods=["POST"])
def do_delete():
    to_delete = request.form.getlist("playlist_ids")
    if not to_delete:
        return redirect(url_for("cleanup.control"))

    conn = get_db()
    cur  = conn.cursor()
    for pid in to_delete:
        # 1) Tracks
        cur.execute("""
          DELETE FROM Tracks
           WHERE PlaylistId = (
             SELECT Id FROM Playlists WHERE SpotifyPlaylistId = ?
           );
        """, (pid,))

        # 2) Playlist record
        cur.execute("DELETE FROM Playlists WHERE SpotifyPlaylistId = ?", (pid,))

        # 3) Archive entry
        cur.execute("DELETE FROM DeletedPlaylists WHERE SpotifyPlaylistId = ?", (pid,))

    conn.commit()
    return redirect(url_for("dashboard"))
