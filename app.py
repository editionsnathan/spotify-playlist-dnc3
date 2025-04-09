from flask import Flask, request, redirect, render_template, url_for, session, jsonify, Response, flash
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
from collections import Counter

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "supersecret")

SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REFRESH_TOKEN = os.environ.get("SPOTIPY_REFRESH_TOKEN")
SPOTIFY_PLAYLIST_ID = os.environ.get("SPOTIFY_PLAYLIST_ID")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AMZLDNC3")

def get_spotify_client():
    auth_manager = spotipy.oauth2.SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri="http://localhost:8888/callback",
        scope="playlist-modify-public playlist-modify-private"
    )
    auth_manager.refresh_access_token(SPOTIPY_REFRESH_TOKEN)
    token_info = auth_manager.get_cached_token()
    return spotipy.Spotify(auth=token_info["access_token"])

def load_proposals():
    if not os.path.exists("proposals.json"):
        return []
    with open("proposals.json", "r") as f:
        return json.load(f)

def save_proposals(data):
    with open("proposals.json", "w") as f:
        json.dump(data, f, indent=2)

def load_refused():
    if not os.path.exists("refused.json"):
        return []
    with open("refused.json", "r") as f:
        return json.load(f)

def save_refused(data):
    with open("refused.json", "w") as f:
        json.dump(data, f, indent=2)

def load_validated():
    if not os.path.exists("validated.json"):
        return []
    with open("validated.json", "r") as f:
        return json.load(f)

def save_validated(data):
    with open("validated.json", "w") as f:
        json.dump(data, f, indent=2)

def is_duplicate(title, artist, proposals, sp):
    query = f"{title} {artist}"
    results = sp.search(q=query, limit=1, type="track")
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        return False
    track_id = tracks[0]["id"]
    playlist_tracks = sp.playlist_items(SPOTIFY_PLAYLIST_ID, fields="items.track.id,total", additional_types=['track'])
    existing_ids = [item['track']['id'] for item in playlist_tracks['items']]
    if track_id in existing_ids:
        return True
    for p in proposals:
        if p["title"].strip().lower() == title.strip().lower() and p["artist"].strip().lower() == artist.strip().lower():
            return True
    return False

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    if request.method == "POST":
        login = request.form["login"]
        title = request.form["title"]
        artist = request.form["artist"]
        proposals = load_proposals()
        sp = get_spotify_client()
        query = f"{title} {artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            message = "🚫 Ce morceau est introuvable sur Spotify."
        elif is_duplicate(title, artist, proposals, sp):
            message = "🚫 Ce morceau est déjà proposé ou présent dans la playlist."
        else:
            proposals.append({"login": login, "title": title, "artist": artist})
            save_proposals(proposals)
            return render_template("submitted.html")
    return render_template("index.html", message=message)

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form["password"]
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = load_proposals()
    sp = get_spotify_client()
    for p in proposals:
        query = f"{p['title']} {p['artist']}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        if tracks and tracks[0]["album"]["images"]:
            p["image"] = tracks[0]["album"]["images"][0]["url"]
        else:
            p["image"] = ""
    return render_template("admin.html", proposals=proposals)

@app.route("/validate/<int:index>")
def validate(index):
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = load_proposals()
    validated = load_validated()
    if index >= len(proposals):
        return redirect(url_for("admin"))
    proposal = proposals.pop(index)
    validated.append(proposal)
    save_proposals(proposals)
    save_validated(validated)
    sp = get_spotify_client()
    query = f"{proposal['title']} {proposal['artist']}"
    results = sp.search(q=query, limit=1, type="track")
    tracks = results.get("tracks", {}).get("items", [])
    if tracks:
        track_id = tracks[0]["id"]
        sp.playlist_add_items(SPOTIFY_PLAYLIST_ID, [track_id])
    return redirect(url_for("admin"))

@app.route("/reject/<int:index>")
def reject(index):
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = load_proposals()
    refused = load_refused()
    if index < len(proposals):
        refused.append(proposals.pop(index))
        save_proposals(proposals)
        save_refused(refused)
    return redirect(url_for("admin"))

@app.route("/refused")
def view_refused():
    if not session.get("admin"):
        return redirect("/admin-login")
    refused = load_refused()
    sp = get_spotify_client()
    for r in refused:
        query = f"{r['title']} {r['artist']}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        if tracks and tracks[0]["album"]["images"]:
            r["image"] = tracks[0]["album"]["images"][0]["url"]
        else:
            r["image"] = ""
    return render_template("refused.html", refused=refused)

@app.route("/restore/<int:index>")
def restore(index):
    if not session.get("admin"):
        return redirect("/admin-login")
    refused = load_refused()
    proposals = load_proposals()
    if index < len(refused):
        proposals.append(refused.pop(index))
        save_refused(refused)
        save_proposals(proposals)
    return redirect(url_for("view_refused"))

@app.route("/stats")
def stats():
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = load_proposals()
    validated = load_validated()
    all_entries = proposals + validated
    total = len(all_entries)
    import unicodedata
def normalize(text):
    return unicodedata.normalize("NFKD", text.strip().lower()).encode("ASCII", "ignore").decode("utf-8")
logins = [normalize(p["login"]) for p in all_entries if "login" in p]
artists = [normalize(p["artist"]) for p in all_entries if "artist" in p]
    login_counts = Counter(logins)
    artist_counts = Counter(artists)
    top_logins = login_counts.most_common()
    top_artists = artist_counts.most_common(10)
    return render_template("stats.html", total=total, top_logins=top_logins, top_artists=top_artists)

@app.route("/reset-stats", methods=["POST"])
def reset_stats():
    if not session.get("admin"):
        return redirect("/admin-login")

    password = request.form.get("confirm_password")
    if password != ADMIN_PASSWORD:
        flash("❌ Mot de passe incorrect.")
        return redirect("/stats")

    save_validated([])
    flash("✅ Statistiques réinitialisées avec succès.")
    return redirect("/stats")

@app.route("/preview")
def preview():
    title = request.args.get("title", "")
    artist = request.args.get("artist", "")
    if not title or not artist:
        return jsonify({"found": False})
    sp = get_spotify_client()
    query = f"{title} {artist}"
    results = sp.search(q=query, limit=1, type="track")
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        return jsonify({"found": False})
    track = tracks[0]
    return jsonify({
        "found": True,
        "image": track["album"]["images"][0]["url"] if track["album"]["images"] else "",
        "preview_url": track.get("preview_url"),
        "explicit": track.get("explicit", False),
        "track_id": track["id"]
    })

@app.route("/delete_refused/<int:index>")
def delete_refused(index):
    if not session.get("admin"):
        return redirect("/admin-login")
    refused = load_refused()
    if index < len(refused):
        refused.pop(index)
        save_refused(refused)
    return redirect(url_for("view_refused"))

@app.route("/delete_all_refused")
def delete_all_refused():
    if not session.get("admin"):
        return redirect("/admin-login")
    save_refused([])
    return redirect(url_for("view_refused"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
