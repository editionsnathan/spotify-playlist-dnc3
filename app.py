from flask import Flask, request, redirect, render_template, url_for, session, jsonify, Response, flash
from flask_sqlalchemy import SQLAlchemy
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from datetime import datetime
from collections import Counter
import unicodedata

# Initialisation Flask
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "supersecret")

# Configuration PostgreSQL Railway
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialisation SQLAlchemy
db = SQLAlchemy(app)

# Définition du modèle
class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Création des tables dans le bon contexte
with app.app_context():
    db.create_all()

# Normalisation du texte
def normalize(text):
    return unicodedata.normalize("NFKD", text.strip().lower()).encode("ASCII", "ignore").decode("utf-8")

# (Routes et logique ici à compléter...)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
