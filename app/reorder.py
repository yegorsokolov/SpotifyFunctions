from flask import Blueprint, render_template, request, jsonify
from .app import sp

bp = Blueprint("reorder", __name__, url_prefix="/reorder")

@bp.route("/control")
def control():
    data  = sp.current_user_playlists(limit=50)["items"]
    picks = [{"id": p["id"], "name": p["name"]} for p in data]
    return render_template("reorder.html", playlists=picks)

@bp.route("/fetch_tracks", methods=["POST"])
def fetch_tracks():
    payload = request.get_json() or {}
    pid     = payload.get("playlist_id")
    if not pid:
        return jsonify({"error": "playlist_id required"}), 400

    items  = []
    results = sp.playlist_tracks(pid, fields="items.track.id,items.track.name,next")
    items.extend(results["items"])
    while results.get("next"):
        results = sp.next(results)
        items.extend(results["items"])

    tracks = []
    for itm in items:
        t = itm.get("track")
        if t and t.get("id") and t.get("name"):
            tracks.append({"id": t["id"], "name": t["name"]})

    return jsonify(tracks)

@bp.route("/save", methods=["POST"])
def save_order():
    payload = request.get_json() or {}
    pid     = payload.get("playlist_id")
    order   = payload.get("order", [])

    if not pid or not isinstance(order, list):
        return jsonify({"error": "invalid payload"}), 400

    uris = [f"spotify:track:{tid}" for tid in order]
    sp.playlist_replace_items(pid, [])
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(pid, uris[i:i+100])

    return jsonify({"status": "ok"})
