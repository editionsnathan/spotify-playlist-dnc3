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

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REFRESH_TOKEN = os.environ.get("SPOTIPY_REFRESH_TOKEN")
SPOTIFY_PLAYLIST_ID = os.environ.get("SPOTIFY_PLAYLIST_ID")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AMZLDNC3")

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

def normalize(text):
    return unicodedata.normalize("NFKD", text.strip().lower()).encode("ASCII", "ignore").decode("utf-8")

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
        else:
            track_id = tracks[0]["id"]
            existing = Proposal.query.filter_by(title=title, artist=artist).first()
            playlist_tracks = sp.playlist_items(SPOTIFY_PLAYLIST_ID, fields="items.track.id,total", additional_types=['track'])
            playlist_ids = [item['track']['id'] for item in playlist_tracks['items']]
            if existing or track_id in playlist_ids:
                message = "🚫 Ce morceau est déjà proposé ou présent dans la playlist."
            else:
                p = Proposal(login=login, title=title, artist=artist, status="pending")
                db.session.add(p)
                db.session.commit()
                return render_template("submitted.html")
    return render_template("index.html", message=message)

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form["password"]
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        flash("❌ Mot de passe incorrect.")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login")
    proposals = Proposal.query.filter_by(status="pending").all()
    sp = get_spotify_client()
    for p in proposals:
        query = f"{p.title} {p.artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        p.image = tracks[0]["album"]["images"][0]["url"] if tracks and tracks[0]["album"]["images"] else ""
    return render_template("admin.html", proposals=proposals)

@app.route("/validate/<int:id>")
def validate(id):
    if not session.get("admin"):
        return redirect("/admin-login")
    p = Proposal.query.get(id)
    if p:
        sp = get_spotify_client()
        query = f"{p.title} {p.artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        if tracks:
            track_id = tracks[0]["id"]
            sp.playlist_add_items(SPOTIFY_PLAYLIST_ID, [track_id])
        p.status = "validated"
        db.session.commit()
    return redirect(url_for("admin"))

@app.route("/reject/<int:id>")
def reject(id):
    if not session.get("admin"):
        return redirect("/admin-login")
    p = Proposal.query.get(id)
    if p:
        p.status = "refused"
        db.session.commit()
    return redirect(url_for("admin"))

@app.route("/refused")
def view_refused():
    if not session.get("admin"):
        return redirect("/admin-login")
    refused = Proposal.query.filter_by(status="refused").all()
    sp = get_spotify_client()
    for r in refused:
        query = f"{r.title} {r.artist}"
        results = sp.search(q=query, limit=1, type="track")
        tracks = results.get("tracks", {}).get("items", [])
        r.image = tracks[0]["album"]["images"][0]["url"] if tracks and tracks[0]["album"]["images"] else ""
    return render_template("refused.html", refused=refused)

@app.route("/restore/<int:id>")
def restore(id):
    if not session.get("admin"):
        return redirect("/admin-login")
    p = Proposal.query.get(id)
    if p and p.status == "refused":
        p.status = "pending"
        db.session.commit()
    return redirect(url_for("view_refused"))

@app.route("/delete_refused/<int:id>")
def delete_refused(id):
    if not session.get("admin"):
        return redirect("/admin-login")
    p = Proposal.query.get(id)
    if p and p.status == "refused":
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for("view_refused"))

@app.route("/delete_all_refused")
def delete_all_refused():
    if not session.get("admin"):
        return redirect("/admin-login")
    Proposal.query.filter_by(status="refused").delete()
    db.session.commit()
    return redirect(url_for("view_refused"))

@app.route("/stats")
def stats():
    if not session.get("admin"):
        return redirect("/admin-login")
    all_entries = Proposal.query.filter(Proposal.status.in_(["pending", "validated"])).all()
    total = len(all_entries)
    logins = [normalize(p.login) for p in all_entries]
    artists = [normalize(p.artist) for p in all_entries]
    login_counts = Counter(logins)
    artist_counts = Counter(artists)
    return render_template("stats.html", total=total, top_logins=login_counts.most_common(), top_artists=artist_counts.most_common(10))

@app.route("/reset-stats", methods=["POST"])
def reset_stats():
    if not session.get("admin"):
        return redirect("/admin-login")
    password = request.form.get("confirm_password")
    if password != ADMIN_PASSWORD:
        flash("❌ Mot de passe incorrect.")
        return redirect("/stats")
    Proposal.query.filter_by(status="validated").delete()
    db.session.commit()
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
