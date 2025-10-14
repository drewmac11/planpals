from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import text
from urllib.parse import urlparse
import os

from extensions import db, login_manager
from models import User, Event, RSVP, Availability, ChecklistItem, Unavailability

DEFAULT_CHECKLIST = [
    "Chairs","Snacks","Alcohol","Weed","Soft drinks","Water",
    "Ice","Cups","Plates","Napkins","Games","Music speaker"
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
    db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS start_time TIME"))
    db.session.execute(text("ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS end_time TIME"))
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS unavailability (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id),
            start_dt TIMESTAMP NOT NULL,
            end_dt   TIMESTAMP NOT NULL
        )
    '''))
    db.create_all()
    db.session.commit()
    print("✅ ensured tables/columns")

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
            print("⚠️  DB connect failed, fallback to SQLite:", e)
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

    # -------- Profile --------
    @app.route("/profile")
    @login_required
    def profile():
        my_events = Event.query.filter_by(creator_id=current_user.id).order_by(Event.date.asc()).all()
        return render_template("profile.html", events=my_events)

    @app.route("/event/<int:event_id>/delete", methods=["POST"])
    @login_required
    def delete_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can delete this event.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        ChecklistItem.query.filter_by(event_id=e.id).delete()
        RSVP.query.filter_by(event_id=e.id).delete()
        db.session.delete(e); db.session.commit()
        flash("Event deleted.", "success")
        return redirect(url_for("profile"))

    @app.route("/event/<int:event_id>/edit", methods=["GET","POST"])
    @login_required
    def edit_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can edit this event.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        if request.method == "POST":
            e.title = request.form["title"].strip()
            e.description = request.form.get("description","").strip()
            e.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            e.start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
            no_end = request.form.get("no_end") == "on"
            e.end_time = None if no_end or not request.form.get("end_time") else datetime.strptime(request.form["end_time"], "%H:%M").time()
            e.capacity = max(1, int(request.form["capacity"]))
            e.dry = request.form.get("dry") == "on"
            db.session.commit()
            flash("Event updated.", "success")
            return redirect(url_for("event_detail", event_id=e.id))
        return render_template("edit.html", e=e)

    # -------- Availability with time windows --------
    @app.route("/schedule", methods=["GET","POST"])
    @login_required
    def schedule():
        if request.method == "POST":
            start = request.form.get("start_dt","").strip()
            end = request.form.get("end_dt","").strip()
            try:
                sdt = datetime.strptime(start, "%Y-%m-%dT%H:%M")
                edt = datetime.strptime(end,   "%Y-%m-%dT%H:%M")
                if edt <= sdt:
                    raise ValueError
            except Exception:
                flash("Please enter a valid start/end for your busy time.", "error")
                return redirect(url_for("schedule"))
            db.session.add(Unavailability(user_id=current_user.id, start_dt=sdt, end_dt=edt))
            db.session.commit()
            flash("Busy time saved.", "success")
            return redirect(url_for("schedule"))
        blocks = Unavailability.query.filter_by(user_id=current_user.id).order_by(Unavailability.start_dt.asc()).all()
        return render_template("schedule.html", blocks=blocks)

    @app.get("/who_can_attend")
    @login_required
    def who_can_attend():
        date_str = request.args.get("date")
        start_str = request.args.get("start")
        end_str = request.args.get("end") or None
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            st = datetime.strptime(start_str, "%H:%M").time()
            et = None if not end_str else datetime.strptime(end_str, "%H:%M").time()
            start_dt = datetime.combine(d, st)
            end_dt = datetime.combine(d, et) if et else datetime.combine(d, st).replace(hour=23,minute=59)
        except Exception:
            return jsonify({"available": [], "busy": []})
        all_users = User.query.all()
        busy_ids = set()
        for u in all_users:
            for blk in Unavailability.query.filter_by(user_id=u.id).all():
                if blk.start_dt < end_dt and blk.end_dt > start_dt:
                    busy_ids.add(u.id); break
        available = [first_name(u.name) for u in all_users if u.id not in busy_ids]
        busy = [first_name(u.name) for u in all_users if u.id in busy_ids]
        return jsonify({"available": available, "busy": busy})

    # -------- Core pages --------
    @app.route("/")
    def index():
        events = Event.query.order_by(Event.date.asc()).all()
        data = []
        for e in events:
            yes = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='yes').all()]
            maybe = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='maybe').all()]
            no = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id==User.id).filter(RSVP.event_id==e.id, RSVP.status=='no').all()]
            data.append((e, yes, maybe, no))
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

    # -------- Auth --------
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

    # -------- Create Event --------
    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create_event():
        if request.method == "POST":
            title = request.form["title"].strip()
            date_str = request.form["date"].strip()
            start_str = request.form.get("start_time","").strip()
            end_str = request.form.get("end_time","").strip()
            no_end = request.form.get("no_end") == "on"
            desc = request.form.get("description","").strip()
            dry = request.form.get("dry") == "on"

            capacity_raw = request.form.get("capacity","").strip()
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

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                st = datetime.strptime(start_str, "%H:%M").time()
                et = None if no_end or not end_str else datetime.strptime(end_str, "%H:%M").time()
            except Exception:
                flash("Please provide valid date/time.", "error")
                return render_template("create.html")

            labels = request.form.getlist("preset_item")
            custom_checklist_raw = request.form.get("checklist","").strip()
            if custom_checklist_raw:
                for line in custom_checklist_raw.splitlines():
                    t = line.strip()
                    if t and t not in labels:
                        labels.append(t)

            e = Event(
                title=title, date=dt, start_time=st, end_time=et,
                description=desc, creator_id=current_user.id,
                capacity=cap, checklist=custom_checklist_raw, dry=dry
            )
            db.session.add(e); db.session.commit()
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
