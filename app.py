from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import text
import os

from extensions import db, login_manager
from models import User, Event, RSVP, ChecklistItem, Unavailability

DEFAULT_CHECKLIST = [
    "Chairs","Snacks","Soft drinks","Water","Ice","Cups",
    "Plates","Napkins","Games","Music speaker","Blankets",
    "BBQ/Grill","Cooler","Sunscreen","Bug spray","Alcohol","Weed"
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
    if raw.startswith("postgresql+psycopg://"):
        sep = "&" if "?" in raw else "?"
        if "sslmode=" not in raw:
            raw += f"{sep}sslmode=require"; sep="&"
        if "connect_timeout=" not in raw:
            raw += f"{sep}connect_timeout=5"
    return raw

def ensure_schema():
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS "user"(
          id SERIAL PRIMARY KEY,
          name VARCHAR(100) NOT NULL,
          email VARCHAR(150) UNIQUE NOT NULL,
          password_hash VARCHAR(255) NOT NULL,
          created_at TIMESTAMP DEFAULT now()
        )'''))
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS event(
          id SERIAL PRIMARY KEY,
          title VARCHAR(200) NOT NULL,
          date DATE NOT NULL,
          start_time TIME,
          end_time TIME,
          description TEXT DEFAULT '',
          creator_id INTEGER REFERENCES "user"(id),
          capacity INTEGER,
          checklist TEXT DEFAULT '',
          dry BOOLEAN DEFAULT FALSE
        )'''))
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS rsvp(
          id SERIAL PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES "user"(id),
          event_id INTEGER NOT NULL REFERENCES event(id),
          status VARCHAR(10) NOT NULL DEFAULT 'yes',
          updated_at TIMESTAMP DEFAULT now(),
          CONSTRAINT uniq_user_event UNIQUE(user_id,event_id)
        )'''))
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS checklist_item(
          id SERIAL PRIMARY KEY,
          event_id INTEGER NOT NULL REFERENCES event(id),
          label VARCHAR(200) NOT NULL,
          checked BOOLEAN DEFAULT FALSE
        )'''))
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS unavailability(
          id SERIAL PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES "user"(id),
          start_dt TIMESTAMP NOT NULL,
          end_dt   TIMESTAMP NOT NULL
        )'''))
    for ddl in [
        "ALTER TABLE event ADD COLUMN IF NOT EXISTS capacity INTEGER",
        "ALTER TABLE event ADD COLUMN IF NOT EXISTS checklist TEXT DEFAULT ''",
        "ALTER TABLE event ADD COLUMN IF NOT EXISTS dry BOOLEAN DEFAULT FALSE",
        "ALTER TABLE event ADD COLUMN IF NOT EXISTS start_time TIME",
        "ALTER TABLE event ADD COLUMN IF NOT EXISTS end_time TIME",
    ]:
        db.session.execute(text(ddl))
    db.session.commit()

def first_name(full: str) -> str:
    full = (full or "").strip()
    return full.split()[0] if full else ""

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = normalize_db_url(os.environ.get("DATABASE_URL", "sqlite:///planpals.db"))
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        try:
            db.create_all()
            ensure_schema()
            db.session.execute(text("SELECT 1"))
        except Exception as e:
            print("DB failed, fallback to SQLite:", e)
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/planpals.db"
            db.session.remove()
            try: db.engine.dispose()
            except Exception: pass
            db.create_all(); ensure_schema()

    @app.get("/health")
    def health(): return "ok", 200

    # Auth
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form["name"].strip()
            email = request.form["email"].strip().lower()
            pw = request.form["password"]
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "error")
            else:
                u = User(name=name, email=email, password_hash=generate_password_hash(pw))
                db.session.add(u); db.session.commit()
                flash("Registered! Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form["email"].strip().lower()
            pw = request.form["password"]
            u = User.query.filter_by(email=email).first()
            if u and check_password_hash(u.password_hash, pw):
                login_user(u); return redirect(url_for("index"))
            flash("Invalid credentials", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user(); return redirect(url_for("index"))

    # Schedule
    @app.route("/schedule", methods=["GET", "POST"])
    @login_required
    def schedule():
        if request.method == "POST":
            start = request.form.get("start_dt", "")
            end = request.form.get("end_dt", "")
            try:
                sdt = datetime.strptime(start, "%Y-%m-%dT%H:%M")
                edt = datetime.strptime(end, "%Y-%m-%dT%H:%M")
                if edt <= sdt: raise ValueError
            except Exception:
                flash("Enter a valid busy start/end.", "error")
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
            end_dt = datetime.combine(d, et) if et else datetime.combine(d, st).replace(hour=23, minute=59)
        except Exception:
            return jsonify({"available": [], "busy": []})
        users = User.query.all()
        busy_ids = set()
        for u in users:
            for blk in Unavailability.query.filter_by(user_id=u.id).all():
                if blk.start_dt < end_dt and blk.end_dt > start_dt:
                    busy_ids.add(u.id); break
        available = [first_name(u.name) for u in users if u.id not in busy_ids]
        busy = [first_name(u.name) for u in users if u.id in busy_ids]
        return jsonify({"available": available, "busy": busy})

    # Events
    @app.route("/")
    def index():
        events = Event.query.order_by(Event.date.asc()).all()
        enriched = []
        for e in events:
            yes = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id == User.id).filter(RSVP.event_id == e.id, RSVP.status == 'yes').all()]
            maybe = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id == User.id).filter(RSVP.event_id == e.id, RSVP.status == 'maybe').all()]
            no = [first_name(u.name) for u in User.query.join(RSVP, RSVP.user_id == User.id).filter(RSVP.event_id == e.id, RSVP.status == 'no').all()]
            enriched.append((e, yes, maybe, no))
        return render_template("index.html", events_data=enriched)

    @app.route("/event/<int:event_id>")
    def event_detail(event_id):
        e = Event.query.get_or_404(event_id)
        yes, maybe, no = e.rsvp_counts()
        items = ChecklistItem.query.filter_by(event_id=e.id).order_by(ChecklistItem.id.asc()).all()
        my = None
        if current_user.is_authenticated:
            rec = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id).first()
            my = rec.status if rec else None
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
        status = (status or "").lower()
        if status not in ("yes", "no", "maybe"):
            flash("Invalid RSVP.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        e = Event.query.get_or_404(event_id)
        already_yes = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id, status="yes").first()
        if status == "yes" and e.is_full() and not already_yes:
            flash("Sorry, this event is full.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        rec = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id).first()
        if rec: rec.status = status
        else: db.session.add(RSVP(event_id=event_id, user_id=current_user.id, status=status))
        db.session.commit()
        flash("RSVP updated.", "success")
        return redirect(url_for("event_detail", event_id=event_id))

    # Create/Edit/Profile
    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create_event():
        if request.method == "POST":
            title = request.form["title"].strip()
            date_str = request.form["date"].strip()
            start_str = request.form.get("start_time", "").strip()
            end_str = request.form.get("end_time", "").strip()
            no_end = request.form.get("no_end") == "on"
            desc = request.form.get("description", "").strip()
            dry = request.form.get("dry") == "on"
            capacity_raw = request.form.get("capacity", "").strip()
            if not capacity_raw:
                flash("Capacity is required.", "error")
                return render_template("create.html", defaults=DEFAULT_CHECKLIST)
            try:
                cap = int(capacity_raw)
                if cap < 1: raise ValueError
            except Exception:
                flash("Capacity must be a number ≥ 1.", "error")
                return render_template("create.html", defaults=DEFAULT_CHECKLIST)
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                st = datetime.strptime(start_str, "%H:%M").time()
                et = None if no_end or not end_str else datetime.strptime(end_str, "%H:%M").time()
            except Exception:
                flash("Please provide valid date/time.", "error")
                return render_template("create.html", defaults=DEFAULT_CHECKLIST)
            e = Event(title=title, date=date, start_time=st, end_time=et, description=desc,
                      creator_id=current_user.id, capacity=cap, checklist="", dry=dry)
            db.session.add(e); db.session.commit()
            labels = request.form.getlist("preset_item")
            custom = request.form.get("checklist", "").strip()
            if custom:
                for line in custom.splitlines():
                    t = line.strip()
                    if t and t not in labels: labels.append(t)
            for lbl in labels:
                db.session.add(ChecklistItem(event_id=e.id, label=lbl))
            db.session.commit()
            flash("Event created!", "success")
            return redirect(url_for("event_detail", event_id=e.id))
        return render_template("create.html", defaults=DEFAULT_CHECKLIST)

    @app.route("/profile")
    @login_required
    def profile():
        rows = Event.query.filter_by(creator_id=current_user.id).order_by(Event.date.asc()).all()
        return render_template("profile.html", events=rows)

    @app.route("/event/<int:event_id>/delete", methods=["POST"])
    @login_required
    def delete_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can delete.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        ChecklistItem.query.filter_by(event_id=e.id).delete()
        RSVP.query.filter_by(event_id=e.id).delete()
        db.session.delete(e); db.session.commit()
        flash("Event deleted.", "success")
        return redirect(url_for("profile"))

    @app.route("/event/<int:event_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can edit.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        if request.method == "POST":
            e.title = request.form["title"].strip()
            e.description = request.form.get("description", "").strip()
            e.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            e.start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
            no_end = request.form.get("no_end") == "on"
            e.end_time = None if no_end or not request.form.get("end_time") else datetime.strptime(request.form["end_time"], "%H:%M").time()
            e.capacity = max(1, int(request.form["capacity"]))
            e.dry = (request.form.get("dry") == "on")
            db.session.commit()
            flash("Event updated.", "success")
            return redirect(url_for("event_detail", event_id=event_id))
        return render_template("edit.html", e=e)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
