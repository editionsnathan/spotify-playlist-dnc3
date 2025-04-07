from flask import Flask, request, redirect, render_template, url_for, session
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os

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

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        title = request.form["title"]
        artist = request.form["artist"]
        proposals = load_proposals()
        proposals.append({"title": title, "artist": artist})
        save_proposals(proposals)
        return render_template("submitted.html")
    return render_template("index.html")

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
    return render_template("admin.html", proposals=proposals)

@app.route("/validate/<int:index>")
def validate(index):
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = load_proposals()
    if index >= len(proposals):
        return redirect(url_for("admin"))
    proposal = proposals.pop(index)
    save_proposals(proposals)
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
    if index < len(proposals):
        proposals.pop(index)
        save_proposals(proposals)
    return redirect(url_for("admin"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)