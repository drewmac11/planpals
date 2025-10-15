from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import text, Boolean
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

        # --- lightweight schema migrations ---
        try:
            with app.app_context():
                # Add new columns to event if they don't exist
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS open_time TIME"))
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS close_time TIME"))
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS dry BOOLEAN DEFAULT FALSE"))
                # Availability table
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS availability (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                        day INTEGER NOT NULL,
                        start_time TIME NOT NULL,
                        end_time TIME NOT NULL
                    )
                """))
                db.session.commit()
        except Exception as e:
            app.logger.error(f"Schema migration error: {e}")

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

        # --- lightweight schema migrations ---
        try:
            with app.app_context():
                # Add new columns to event if they don't exist
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS open_time TIME"))
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS close_time TIME"))
                db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS dry BOOLEAN DEFAULT FALSE"))
                # Availability table
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS availability (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                        day INTEGER NOT NULL,
                        start_time TIME NOT NULL,
                        end_time TIME NOT NULL
                    )
                """))
                db.session.commit()
        except Exception as e:
            app.logger.error(f"Schema migration error: {e}")


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
            otp = datetime.strptime(open_time_str, "%H:%M").time() if open_time_str else None
        ctp = datetime.strptime(close_time_str, "%H:%M").time() if close_time_str else None
        e = Event(title=title, date=dt, description=desc, creator_id=current_user.id)
        # direct SQL updates to new columns without redefining model
        db.session.add(e)
        db.session.flush()
        if otp is not None:
            db.session.execute(text("UPDATE event SET open_time=:ot WHERE id=:id"), {"ot": otp, "id": e.id})
        if ctp is not None:
            db.session.execute(text("UPDATE event SET close_time=:ct WHERE id=:id"), {"ct": ctp, "id": e.id})
        db.session.execute(text("UPDATE event SET dry=:d WHERE id=:id"), {"d": dry_flag, "id": e.id})
        
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

    @app.route("/profile", methods=["GET","POST"])
    @login_required
    def profile():
        # Change display name
        if request.method == "POST":
            new_name = request.form.get("name","").strip()
            if new_name:
                current_user.name = new_name
                db.session.commit()
                flash("Profile updated", "success")
            else:
                flash("Name cannot be empty", "error")
        # List current user's events
        my_events = Event.query.filter_by(creator_id=current_user.id).order_by(Event.date.desc()).all()
        return render_template("profile.html", my_events=my_events)

    @app.route("/event/<int:event_id>/edit", methods=["GET","POST"])
    @login_required
    def edit_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("You can only edit your own events.", "error")
            return redirect(url_for("index"))
        if request.method == "POST":
            title = request.form["title"].strip()
            date_str = request.form["date"]
            desc = request.form.get("description","").strip()
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format", "error")
                return render_template("edit.html", event=e)
            e.title = title
            e.date = dt
            e.description = desc
            db.session.commit()
            flash("Event updated", "success")
            return redirect(url_for("profile"))
        return render_template("edit.html", event=e)

    @app.post("/event/<int:event_id>/delete")
    @login_required
    def delete_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("You can only delete your own events.", "error")
            return redirect(url_for("index"))
        db.session.delete(e)
        db.session.commit()
        flash("Event deleted", "success")
        return redirect(url_for("profile"))

    @app.route("/schedule", methods=["GET","POST"])
    @login_required
    def schedule():
        if request.method == "POST":
            day = int(request.form["day"])
            start = datetime.strptime(request.form["start"], "%H:%M").time()
            end = datetime.strptime(request.form["end"], "%H:%M").time()
            db.session.execute(text("INSERT INTO availability (user_id, day, start_time, end_time) VALUES (:u,:d,:s,:e)"),
                               {"u": current_user.id, "d": day, "s": start, "e": end})
            db.session.commit()
            flash("Added unavailable slot", "success")
            return redirect(url_for("schedule"))
        rows = db.session.execute(text("SELECT id, day, start_time, end_time FROM availability WHERE user_id=:u ORDER BY day, start_time"),
                                  {"u": current_user.id}).mappings().all()
        class Row: pass
        slots = []
        for r in rows:
            obj = Row()
            obj.id = r["id"]; obj.day = r["day"]; obj.start_time = r["start_time"]; obj.end_time = r["end_time"]
            slots.append(obj)
        return render_template("schedule.html", slots=slots)

    @app.post("/schedule/delete/<int:slot_id>")
    @login_required
    def delete_slot(slot_id):
        db.session.execute(text("DELETE FROM availability WHERE id=:i AND user_id=:u"), {"i": slot_id, "u": current_user.id})
        db.session.commit()
        flash("Removed slot", "success")
        return redirect(url_for("schedule"))

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
