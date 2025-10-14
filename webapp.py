import os
import datetime as dt
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import or_, and_
from extensions import db, login_manager
from models import User, Event, RSVP, AvailabilityWindow, ChecklistItem, default_bring_items

def normalize_db_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://","postgresql://",1)
    # Railway often provides SSL by default; SQLAlchemy handles with query args if present
    return raw_url

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = os.environ.get("SECRET_KEY","dev-secret")
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = normalize_db_url(db_url)
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///planpals.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
    _bootstrap_migrations(app)
    return app

app = create_app()
print("PlanPals: Flask app created")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {"now": dt.datetime.utcnow()}

@app.route("/")
def index():
    events = Event.query.order_by(Event.date.asc(), Event.doors_open_time.asc().nullsfirst()).all()
    # RSVP summary
    summary = {}
    for ev in events:
        s = {"going":[], "maybe":[], "no":[], "busy":[]}
        # compute busy from availability windows
        ev_start, ev_end = ev.time_window()
        users = User.query.all()
        for u in users:
            # Check unavailability overlap
            busy = False
            awins = AvailabilityWindow.query.filter_by(user_id=u.id, date=ev.date).all()
            if ev_end is None:
                # any window on date means busy sometime; still show 'busy' (red) but can still RSVP
                busy = any(w.is_unavailable for w in awins)
            else:
                for w in awins:
                    if w.is_unavailable:
                        w_start = dt.datetime.combine(w.date, w.start_time)
                        w_end = dt.datetime.combine(w.date, w.end_time)
                        # overlap
                        if not (w_end <= ev_start or w_start >= ev_end):
                            busy = True; break
            if busy:
                s["busy"].append(u.name)
        # pull RSVPs
        for r in ev.rsvps:
            s[r.status].append(r.user.name)
        summary[ev.id] = s
    return render_template("index.html", events=events, summary=summary)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].lower().strip()
        password = request.form["password"]
        if not name or not email or not password:
            flash("All fields are required.","error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.","error")
            return redirect(url_for("register"))
        u = User(name=name, email=email)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower().strip()
        password = request.form["password"]
        u = User.query.filter_by(email=email).first()
        if u and u.check_password(password):
            login_user(u)
            return redirect(url_for("index"))
        flash("Invalid credentials.","error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/create", methods=["GET","POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form["title"].strip()
        date_str = request.form["date"]
        description = request.form.get("description","").strip()
        capacity = int(request.form.get("capacity","0") or 0)
        dry = bool(request.form.get("dry"))
        doors_open = request.form.get("doors_open_time") or None
        leave_by = request.form.get("leave_by_time") or None
        no_end = bool(request.form.get("no_end"))
        if not title or not date_str:
            flash("Title and date are required.","error")
            return redirect(url_for("create"))
        ev = Event(
            title=title,
            date=dt.datetime.strptime(date_str,"%Y-%m-%d").date(),
            description=description,
            capacity=capacity,
            dry=dry,
            doors_open_time=dt.datetime.strptime(doors_open,"%H:%M").time() if doors_open else None,
            leave_by_time=None if no_end else (dt.datetime.strptime(leave_by,"%H:%M").time() if leave_by else None),
            no_specified_end_time=no_end,
            creator_id=current_user.id
        )
        db.session.add(ev)
        db.session.flush()  # get id

        # Bring list checkboxes + other items
        selected = request.form.getlist("bring[]")
        other_text = request.form.get("bring_other","").strip()
        if other_text:
            selected.extend([x.strip() for x in other_text.split(",") if x.strip()])

        # If dry, filter alcohol/weed-ish labels out
        blocked = {"Alcohol","Weed","Beer","Wine","Liquor"}
        for label in selected:
            if ev.dry and label.strip() in blocked:
                continue
            db.session.add(ChecklistItem(event_id=ev.id, label=label.strip()))
        db.session.commit()
        flash("Event created!", "success")
        return redirect(url_for("event_detail", event_id=ev.id))
    # Render create with default list
    defaults = default_bring_items + ["Alcohol","Weed"]
    return render_template("create.html", defaults=defaults)

@app.route("/event/<int:event_id>")
def event_detail(event_id:int):
    ev = Event.query.get_or_404(event_id)
    # Determine potential attendees/busy for the date
    users = User.query.all()
    potential, busy = [], []
    ev_start, ev_end = ev.time_window()
    for u in users:
        awins = AvailabilityWindow.query.filter_by(user_id=u.id, date=ev.date).all()
        is_busy = any(w.is_unavailable for w in awins) if ev_end is None else False
        if ev_end is not None:
            for w in awins:
                if w.is_unavailable:
                    w_start = dt.datetime.combine(w.date, w.start_time)
                    w_end = dt.datetime.combine(w.date, w.end_time)
                    if not (w_end <= ev_start or w_start >= ev_end):
                        is_busy = True; break
        (busy if is_busy else potential).append(u)
    # RSVP status for current user
    my_rsvp = None
    if current_user.is_authenticated:
        my_rsvp = RSVP.query.filter_by(event_id=ev.id, user_id=current_user.id).first()
    return render_template("event.html", ev=ev, potential=potential, busy=busy, my_rsvp=my_rsvp)

@app.route("/rsvp/<int:event_id>/<status>", methods=["POST"])
@login_required
def rsvp(event_id:int, status:str):
    if status not in ("going","maybe","no"):
        abort(400)
    ev = Event.query.get_or_404(event_id)
    r = RSVP.query.filter_by(event_id=event_id, user_id=current_user.id).first()
    if not r:
        r = RSVP(event_id=event_id, user_id=current_user.id, status=status)
        db.session.add(r)
    else:
        r.status = status
    db.session.commit()
    return redirect(url_for("event_detail", event_id=event_id))

@app.route("/toggle_item/<int:item_id>", methods=["POST"])
@login_required
def toggle_item(item_id:int):
    item = ChecklistItem.query.get_or_404(item_id)
    # only creator can toggle
    if item.event.creator_id != current_user.id:
        abort(403)
    item.is_checked = not item.is_checked
    db.session.commit()
    return jsonify({"ok": True, "is_checked": item.is_checked})

@app.route("/schedule", methods=["GET","POST"])
@login_required
def schedule():
    if request.method == "POST":
        date_str = request.form["date"]
        start = request.form["start"]
        end = request.form["end"]
        if not date_str or not start or not end:
            flash("Please provide date, start, and end times.","error")
            return redirect(url_for("schedule"))
        aw = AvailabilityWindow(
            user_id=current_user.id,
            date=dt.datetime.strptime(date_str,"%Y-%m-%d").date(),
            start_time=dt.datetime.strptime(start,"%H:%M").time(),
            end_time=dt.datetime.strptime(end,"%H:%M").time(),
            is_unavailable=True
        )
        db.session.add(aw)
        db.session.commit()
        flash("Unavailability added.","success")
        return redirect(url_for("schedule"))
    wins = AvailabilityWindow.query.filter_by(user_id=current_user.id).order_by(AvailabilityWindow.date.asc(), AvailabilityWindow.start_time.asc()).all()
    return render_template("schedule.html", wins=wins)

@app.route("/delete_window/<int:win_id>", methods=["POST"])
@login_required
def delete_window(win_id:int):
    w = AvailabilityWindow.query.get_or_404(win_id)
    if w.user_id != current_user.id:
        abort(403)
    db.session.delete(w)
    db.session.commit()
    return redirect(url_for("schedule"))

@app.route("/profile")
@login_required
def profile():
    my_events = Event.query.filter_by(creator_id=current_user.id).order_by(Event.date.desc()).all()
    my_rsvps = RSVP.query.filter_by(user_id=current_user.id).all()
    return render_template("profile.html", my_events=my_events, my_rsvps=my_rsvps)

@app.route("/event/<int:event_id>/edit", methods=["GET","POST"])
@login_required
def edit_event(event_id:int):
    ev = Event.query.get_or_404(event_id)
    if ev.creator_id != current_user.id:
        abort(403)
    if request.method == "POST":
        ev.title = request.form["title"].strip()
        ev.date = dt.datetime.strptime(request.form["date"],"%Y-%m-%d").date()
        ev.description = request.form.get("description","").strip()
        ev.capacity = int(request.form.get("capacity","0") or 0)
        ev.dry = bool(request.form.get("dry"))
        doors_open = request.form.get("doors_open_time") or None
        leave_by = request.form.get("leave_by_time") or None
        no_end = bool(request.form.get("no_end"))
        ev.doors_open_time = dt.datetime.strptime(doors_open,"%H:%M").time() if doors_open else None
        ev.leave_by_time = None if no_end else (dt.datetime.strptime(leave_by,"%H:%M").time() if leave_by else None)
        ev.no_specified_end_time = no_end
        # replace checklist if provided
        if "bring[]" in request.form or "bring_other" in request.form:
            ChecklistItem.query.filter_by(event_id=ev.id).delete()
            selected = request.form.getlist("bring[]")
            other_text = request.form.get("bring_other","").strip()
            if other_text:
                selected.extend([x.strip() for x in other_text.split(",") if x.strip()])
            blocked = {"Alcohol","Weed","Beer","Wine","Liquor"}
            for label in selected:
                if ev.dry and label.strip() in blocked:
                    continue
                db.session.add(ChecklistItem(event_id=ev.id, label=label.strip()))
        db.session.commit()
        flash("Event updated.","success")
        return redirect(url_for("event_detail", event_id=ev.id))
    defaults = default_bring_items + ["Alcohol","Weed"]
    existing = [c.label for c in ev.checklist_items]
    return render_template("edit_event.html", ev=ev, defaults=defaults, existing=existing)

@app.route("/event/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id:int):
    ev = Event.query.get_or_404(event_id)
    if ev.creator_id != current_user.id:
        abort(403)
    db.session.delete(ev)
    db.session.commit()
    flash("Event deleted.","success")
    return redirect(url_for("profile"))



from sqlalchemy import text, inspect

def _bootstrap_migrations(app):
    """Create any new columns/tables if they don't exist (Postgres/SQLite safe)."""
    from extensions import db
    with app.app_context():
        eng = db.engine
        insp = inspect(eng)

        # Ensure required tables exist
        with eng.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS availability_window (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id),
                date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                is_unavailable BOOLEAN NOT NULL DEFAULT TRUE
            )
            """))
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS checklist_item (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES event(id),
                label TEXT NOT NULL,
                is_checked BOOLEAN NOT NULL DEFAULT FALSE,
                added_by_user_id INTEGER NULL REFERENCES "user"(id)
            )
            """))

        # Add missing columns on event
        cols = {c['name'] for c in insp.get_columns('event')}
        ddl = []
        if 'doors_open_time' not in cols:
            ddl.append("ALTER TABLE event ADD COLUMN IF NOT EXISTS doors_open_time TIME")
        if 'leave_by_time' not in cols:
            ddl.append("ALTER TABLE event ADD COLUMN IF NOT EXISTS leave_by_time TIME")
        if 'no_specified_end_time' not in cols:
            ddl.append("ALTER TABLE event ADD COLUMN IF NOT EXISTS no_specified_end_time BOOLEAN NOT NULL DEFAULT FALSE")
        if 'dry' not in cols:
            ddl.append("ALTER TABLE event ADD COLUMN IF NOT EXISTS dry BOOLEAN NOT NULL DEFAULT FALSE")
        if 'capacity' not in cols:
            ddl.append("ALTER TABLE event ADD COLUMN IF NOT EXISTS capacity INTEGER NOT NULL DEFAULT 0")

        if ddl:
            with eng.begin() as conn:
                for stmt in ddl:
                    conn.execute(text(stmt))

        # Unique constraint for RSVP on Postgres (best effort)
        try:
            if insp.dialect.name == 'postgresql':
                with eng.begin() as conn:
                    conn.execute(text("""
                    DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_event_user'
                    ) THEN
                        ALTER TABLE rsvp ADD CONSTRAINT uq_event_user UNIQUE (event_id, user_id);
                    END IF;
                    END $$;
                    """))
        except Exception:
            pass



@app.route('/health')
def health():
    return "ok", 200
