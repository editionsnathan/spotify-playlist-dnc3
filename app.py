from flask import Flask, request, redirect, render_template, url_for
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os

app = Flask(__name__)

# Spotify API credentials
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = "http://localhost:5000/callback"
SCOPE = "playlist-modify-public playlist-modify-private"

sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                        client_secret=SPOTIPY_CLIENT_SECRET,
                        redirect_uri=SPOTIPY_REDIRECT_URI,
                        scope=SCOPE)

token_info = None
playlist_id = os.environ.get("SPOTIFY_PLAYLIST_ID")  # à définir dans Render

# Chargement des propositions depuis un fichier JSON
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

@app.route("/admin")
def admin():
    proposals = load_proposals()
    return render_template("admin.html", proposals=proposals)

@app.route("/validate/<int:index>")
def validate(index):
    global token_info
    proposals = load_proposals()
    if index >= len(proposals):
        return redirect(url_for("admin"))
    proposal = proposals.pop(index)
    save_proposals(proposals)

    # Authentification avec Spotify
    if not token_info or sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.get_access_token(as_dict=False)
    sp = spotipy.Spotify(auth=token_info)

    query = f"{proposal['title']} {proposal['artist']}"
    results = sp.search(q=query, limit=1, type="track")
    tracks = results.get("tracks", {}).get("items", [])

    if tracks:
        track_id = tracks[0]["id"]
        sp.playlist_add_items(playlist_id, [track_id])
    return redirect(url_for("admin"))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
