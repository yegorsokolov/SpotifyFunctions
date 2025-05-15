import pyodbc
from flask import Blueprint, render_template, request, url_for, jsonify
from .app import sp, DB_CONN

bp = Blueprint("recovery", __name__, url_prefix="/recovery")

def restore_playlist_by_id(pid):
    # 1) Fetch the original name & DB PK
    with pyodbc.connect(DB_CONN) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT Name, Id FROM dbo.Playlists WHERE SpotifyPlaylistId = ?",
            pid
        )
        row = cur.fetchone()
        if not row:
            return None
        name, db_id = row

        # 2) Gather track URIs
        cur.execute("""
            SELECT SpotifyTrackId
              FROM dbo.Tracks
             WHERE PlaylistId = ?
             ORDER BY AddedAt
        """, db_id)
        uris = [f"spotify:track:{r[0]}" for r in cur.fetchall()]

    # 3) Create new playlist
    me     = sp.me()["id"]
    new    = sp.user_playlist_create(me, f"Restored: {name}", public=False)
    new_id = new["id"]

    # 4) Add tracks in batches
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(new_id, uris[i:i+100])

    return new_id

@bp.route("/control")
def control():
    with pyodbc.connect(DB_CONN) as conn:
        cur = conn.cursor()
        cur.execute("""
          SELECT SpotifyPlaylistId, Name
            FROM dbo.DeletedPlaylists
           ORDER BY DeletedAt DESC
        """)
        playlists = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    return render_template("recovery.html", playlists=playlists)

@bp.route("/restore", methods=["POST"])
def do_restore():
    data = request.get_json(force=True)
    pid  = data.get("playlist_id")
    new_id = restore_playlist_by_id(pid)
    if not new_id:
        return jsonify({"error": "Playlist not found"}), 404

    # 5) Update Playlists to use the new Spotify ID,
    #    then remove from DeletedPlaylists
    with pyodbc.connect(DB_CONN) as conn:
        cur = conn.cursor()
        # A) Update the Playlists table so the recovered playlist
        #    replaces the old (deleted) SpotifyPlaylistId
        cur.execute("""
          UPDATE dbo.Playlists
             SET SpotifyPlaylistId = ?
           WHERE SpotifyPlaylistId = ?
        """, new_id, pid)

        # B) Remove from DeletedPlaylists
        cur.execute("""
          DELETE FROM dbo.DeletedPlaylists
           WHERE SpotifyPlaylistId = ?
        """, pid)

        conn.commit()

    # 6) Return the new ID for frontend to open
    return jsonify({"new_id": new_id})
