from flask import Flask, request, redirect, render_template, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from datetime import datetime
from collections import Counter
import unicodedata

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "supersecret")

# PostgreSQL config
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
db = SQLAlchemy(app)

# Spotify API variables
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REFRESH_TOKEN = os.environ.get("SPOTIPY_REFRESH_TOKEN")
SPOTIFY_PLAYLIST_ID = os.environ.get("SPOTIFY_PLAYLIST_ID")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AMZLDNC3")

# Normalize
def normalize(text):
    return unicodedata.normalize("NFKD", text.strip().lower()).encode("ASCII", "ignore").decode("utf-8")

# Database model
class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80))
    title = db.Column(db.String(120))
    artist = db.Column(db.String(120))
    status = db.Column(db.String(20))  # pending, validated, refused
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

db.create_all()

def get_spotify_client():
    auth_manager = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri="http://localhost:8888/callback",
        scope="playlist-modify-public playlist-modify-private"
    )
    auth_manager.refresh_access_token(SPOTIPY_REFRESH_TOKEN)
    token_info = auth_manager.get_cached_token()
    return spotipy.Spotify(auth=token_info["access_token"])

def is_duplicate(title, artist, sp):
    query = f"{title} {artist}"
    results = sp.search(q=query, limit=1, type="track")
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        return False
    track_id = tracks[0]["id"]
    playlist_tracks = sp.playlist_items(SPOTIFY_PLAYLIST_ID, fields="items.track.id,total", additional_types=['track'])
    existing_ids = [item['track']['id'] for item in playlist_tracks['items']]
    return track_id in existing_ids

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    if request.method == "POST":
        login = request.form["login"]
        title = request.form["title"]
        artist = request.form["artist"]
        sp = get_spotify_client()

        query = f"{title} {artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])

        if not tracks:
            message = "🚫 Ce morceau est introuvable sur Spotify."
        elif is_duplicate(title, artist, sp):
            message = "🚫 Ce morceau est déjà présent dans la playlist."
        else:
            proposal = Proposal(login=login, title=title, artist=artist, status="pending")
            db.session.add(proposal)
            db.session.commit()
            return render_template("submitted.html")

    return render_template("index.html", message=message)

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        flash("Mot de passe incorrect.")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login")
    pending = Proposal.query.filter_by(status="pending").all()
    return render_template("admin.html", proposals=pending)

@app.route("/validate/<int:proposal_id>")
def validate(proposal_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    sp = get_spotify_client()
    proposal = Proposal.query.get(proposal_id)
    if proposal:
        query = f"{proposal.title} {proposal.artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        if tracks:
            track_id = tracks[0]["id"]
            sp.playlist_add_items(SPOTIFY_PLAYLIST_ID, [track_id])
        proposal.status = "validated"
        db.session.commit()
    return redirect("/admin")

@app.route("/reject/<int:proposal_id>")
def reject(proposal_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    proposal = Proposal.query.get(proposal_id)
    if proposal:
        proposal.status = "refused"
        db.session.commit()
    return redirect("/admin")

@app.route("/refused")
def refused():
    if not session.get("admin"):
        return redirect("/admin-login")
    refused_list = Proposal.query.filter_by(status="refused").all()
    return render_template("refused.html", refused=refused_list)

@app.route("/restore/<int:proposal_id>")
def restore(proposal_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    proposal = Proposal.query.get(proposal_id)
    if proposal and proposal.status == "refused":
        proposal.status = "pending"
        db.session.commit()
    return redirect("/refused")

@app.route("/preview")
def preview():
    title = request.args.get("title", "")
    artist = request.args.get("artist", "")
    if not title or not artist:
        return jsonify({"found": False})
    sp = get_spotify_client()
    results = sp.search(q=f"{title} {artist}", limit=1, type="track")
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
