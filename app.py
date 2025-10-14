from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import text
from urllib.parse import urlparse
import os

from extensions import db, login_manager
from models import User, Event, RSVP, Availability, ChecklistItem

DEFAULT_CHECKLIST = [
    "Chairs", "Snacks", "Alcohol", "Weed", "Soft drinks", "Water",
    "Ice", "Cups", "Plates", "Napkins", "Games", "Music speaker"
]

def normalize_db_url(raw: str) -> str:
    raw = (raw or "").strip().strip('"').strip("'")
    if raw.startswith("railwaypostgres://"):
        raw = raw.replace("railwaypostgres://", "postgres://", 1)
    if raw.startswith("railwaypostgresql://"):
        raw = raw.replace("railwaypostgresql://", "postgresql://", 1)
    if raw.startswith("postgresql+psycopg2://"):
        raw = raw.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql+psycopg://") and "sslmode=" not in raw:
        host = urlparse(raw).hostname or ""
        if not host.endswith(".railway.internal"):
            raw += ("&" if "?" in raw else "?") + "sslmode=require"
    return raw

def ensure_columns():
    db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS capacity INTEGER"))
    db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS checklist TEXT DEFAULT ''"))
    db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS dry BOOLEAN DEFAULT FALSE"))
    db.create_all()
    db.session.commit()
    print("✅ ensured columns & tables exist")

def first_name(full: str) -> str:
    parts = (full or "").strip().split()
    return parts[0] if parts else ""

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
        return User.query.get(int(user_id))

    with app.app_context():
        try:
            db.create_all()
            ensure_columns()
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
            ensure_columns()

    @app.get("/health")
    def health():
        return "ok", 200

    @app.route("/schedule", methods=["GET", "POST"])
    @login_required
    def schedule():
        weekdays = list(range(7))
        if request.method == "POST":
            sub = request.form.getlist("weekday")
            chosen = set(int(x) for x in sub)
            Availability.query.filter_by(user_id=current_user.id).delete()
            for w in sorted(chosen):
                db.session.add(Availability(user_id=current_user.id, weekday=w))
            db.session.commit()
            flash("Availability updated!", "success")
            return redirect(url_for("schedule"))
        mine = {a.weekday for a in Availability.query.filter_by(user_id=current_user.id).all()}
        return render_template("schedule.html", mine=mine, weekdays=weekdays)

    @app.get("/who_can_attend")
    @login_required
    def who_can_attend():
        date_str = request.args.get("date")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return jsonify({"available": [], "busy": []})
        weekday = dt.weekday()
        users = User.query.all()
        avail_map = {a.user_id: True for a in Availability.query.filter_by(weekday=weekday).all()}
        available, busy = [], []
        for u in users:
            name = first_name(u.name)
            (available if avail_map.get(u.id) else busy).append(name)
        return jsonify({"available": available, "busy": busy})

    @app.route("/")
    def index():
        events = Event.query.order_by(Event.date.asc()).all()
        data = []
        for e in events:
            yes = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='yes').all()]
            maybe = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='maybe').all()]
            no = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='no').all()]
            weekday = e.date.weekday()
            avail_user_ids = {a.user_id for a in Availability.query.filter_by(weekday=weekday).all()}
            all_users = User.query.all()
            busy = [first_name(u.name) for u in all_users if u.id not in avail_user_ids]
            data.append((e, yes, maybe, no, busy))
        return render_template("index.html", events_data=data)

    @app.route("/event/<int:event_id>")
    def event_detail(event_id):
        e = Event.query.get_or_404(event_id)
        yes, maybe, no = e.rsvp_counts()
        items = ChecklistItem.query.filter_by(event_id=e.id).order_by(ChecklistItem.id.asc()).all()
        my = None
        if current_user.is_authenticated:
            r = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id).first()
            my = r.status if r else None
        return render_template("event.html", e=e, yes=yes, maybe=maybe, no=no, items=items, my=my)

    @app.post("/event/<int:event_id>/checklist/toggle/<int:item_id>")
    @login_required
    def toggle_item(event_id, item_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can edit the checklist.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        it = ChecklistItem.query.filter_by(id=item_id, event_id=event_id).first_or_404()
        it.checked = not it.checked
        db.session.commit()
        return redirect(url_for("event_detail", event_id=event_id))

    @app.route("/event/<int:event_id>/rsvp/<status>", methods=["POST"])
    @login_required
    def rsvp(event_id, status):
        status = status.lower()
        if status not in ("yes", "no", "maybe"):
            flash("Invalid RSVP.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        e = Event.query.get_or_404(event_id)
        if status == "yes" and e.is_full() and not RSVP.query.filter_by(event_id=event_id, user_id=current_user.id, status="yes").first():
            flash("Sorry, this event is full.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        rec = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id).first()
        if rec:
            rec.status = status
        else:
            db.session.add(RSVP(event_id=event_id, user_id=current_user.id, status=status))
        db.session.commit()
        flash("RSVP updated.", "success")
        return redirect(url_for("event_detail", event_id=event_id))

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
            date_str = request.form["date"].strip()
            desc = request.form["description"].strip()
            dry = True if request.form.get("dry") == "on" else False

            capacity_raw = request.form.get("capacity", "").strip()
            if not capacity_raw:
                flash("Capacity is required.", "error")
                return render_template("create.html")
            try:
                cap = int(capacity_raw)
                if cap < 1:
                    raise ValueError
            except ValueError:
                flash("Capacity must be a number ≥ 1.", "error")
                return render_template("create.html")

            custom_checklist_raw = request.form.get("checklist", "").strip()

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format", "error")
                return render_template("create.html")

            e = Event(
                title=title, date=dt, description=desc, creator_id=current_user.id,
                capacity=cap, checklist=custom_checklist_raw, dry=dry
            )
            db.session.add(e)
            db.session.commit()

            labels = list(DEFAULT_CHECKLIST)
            if custom_checklist_raw:
                for line in custom_checklist_raw.splitlines():
                    t = line.strip()
                    if t and t not in labels:
                        labels.append(t)
            for lbl in labels:
                db.session.add(ChecklistItem(event_id=e.id, label=lbl))
            db.session.commit()

            flash("Event created!", "success")
            return redirect(url_for("event_detail", event_id=e.id))

        return render_template("create.html")

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
