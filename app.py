from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import text
from urllib.parse import urlparse
import os

from extensions import db, login_manager
from models import User, Event

def normalize_db_url(raw: str) -> str:
    raw = (raw or "").strip().strip('"').strip("'")

    # Fix common mistakes
    if raw.startswith("railwaypostgres://"):
        raw = raw.replace("railwaypostgres://", "postgres://", 1)
    if raw.startswith("railwaypostgresql://"):
        raw = raw.replace("railwaypostgresql://", "postgresql://", 1)

    # Force psycopg3 driver
    if raw.startswith("postgresql+psycopg2://"):
        raw = raw.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)

    # Add SSL only for public hosts
    if raw.startswith("postgresql+psycopg://") and "sslmode=" not in raw:
        host = urlparse(raw).hostname or ""
        if not host.endswith(".railway.internal"):
            raw += ("&" if "?" in raw else "?") + "sslmode=require"
    return raw

def create_app():
    app = Flask(__name__)

    env_url = os.environ.get("DATABASE_URL", "sqlite:///planpals.db")
    db_url = normalize_db_url(env_url)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        # Simple for now; SQLAlchemy 2.x warns about Query.get but fine
        return User.query.get(int(user_id))

    with app.app_context():
        try:
            db.create_all()
            db.session.execute(text("SELECT 1"))
        except Exception as e:
            print("⚠️  Postgres connection failed, falling back to SQLite:", e)
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/planpals.db"
            db.session.remove()
            try:
                db.engine.dispose()
            except Exception:
                pass
            db.create_all()

    @app.get("/health")
    def health():
        return "ok", 200

    @app.route("/")
    def index():
        events = Event.query.order_by(Event.date.asc()).all()
        return render_template("index.html", events=events)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form["name"].strip()
            email = request.form["email"].strip().lower()
            password = request.form["password"]
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "error")
            else:
                user = User(name=name, email=email, password_hash=generate_password_hash(password))
                db.session.add(user)
                db.session.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form["email"].strip().lower()
            password = request.form["password"]
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for("index"))
            flash("Invalid credentials", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create_event():
        if request.method == "POST":
            title = request.form["title"].strip()
            date_str = request.form["date"]
            desc = request.form["description"].strip()
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format", "error")
                return render_template("create.html")
            e = Event(title=title, date=dt, description=desc, creator_id=current_user.id)
            db.session.add(e)
            db.session.commit()
            flash("Event created!", "success")
            return redirect(url_for("index"))
        return render_template("create.html")

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/readyz")
    def readyz():
        try:
            db.session.execute(text("SELECT 1"))
            return "ready", 200
        except Exception as e:
            return ("not-ready: " + str(e)), 503

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
