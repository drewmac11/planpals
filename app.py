import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from sqlalchemy import func, text
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
login_manager = LoginManager()

def database_url():
    url = os.getenv("DATABASE_URL", "sqlite:///planpals.db")
    return url.replace("postgres://", "postgresql://")

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    with app.app_context():
        db.create_all()
        try:
            db.session.execute(text("""
                ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS capacity INTEGER;
                ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS dry BOOLEAN DEFAULT FALSE;
                ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS start_time TIME;
                ALTER TABLE IF EXISTS event ADD COLUMN IF NOT EXISTS end_time TIME;
                CREATE TABLE IF NOT EXISTS checklist_item (
                    id SERIAL PRIMARY KEY,
                    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    checked BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS rsvp (
                    id SERIAL PRIMARY KEY,
                    event_id INTEGER REFERENCES event(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE,
                    status VARCHAR(10) NOT NULL,
                    UNIQUE(event_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS busy_block (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    start_time TIME,
                    end_time TIME
                );
            """))
            db.session.commit()
        except Exception:
            db.session.rollback()

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/readyz")
    def readyz():
        try:
            db.session.execute(text("SELECT 1"))
            return "ready", 200
        except Exception as e:
            return ("db not ready", 503)

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow()}

    @app.route("/")
    def index():
        try:
            events = Event.query.order_by(Event.date.asc().nullslast()).all()
        except Exception as e:
            # Return a lightweight page so proxy gets 200 and you can open the app
            return render_template("minimal.html", msg="Database not reachable yet."), 200
        enriched = []
        for e in events:
            yes_names, maybe_names, no_names = e.rsvp_name_lists()
            enriched.append((e, yes_names, maybe_names, no_names))
        return render_template("index.html", events_data=enriched)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip() or "John Doe"
            email = request.form.get("email", "").strip().lower()
            pw = request.form.get("password", "")
            if not email or not pw:
                flash("Email and password are required.", "error")
                return redirect(url_for("register"))
            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "error")
                return redirect(url_for("register"))
            user = User(name=name, email=email, password_hash=generate_password_hash(pw))
            db.session.add(user); db.session.commit()
            flash("Registration successful. Please sign in.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            pw = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, pw):
                login_user(user)
                return redirect(request.args.get("next") or url_for("index"))
            flash("Invalid credentials.", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            new_name = request.form.get("name", "").strip()
            if new_name:
                current_user.name = new_name
                db.session.commit()
                flash("Name updated.", "success")
            else:
                flash("Name cannot be empty.", "error")
            return redirect(url_for("profile"))
        rows = Event.query.filter_by(creator_id=current_user.id).order_by(Event.date.asc().nullslast()).all()
        return render_template("profile.html", events=rows)

    def parse_time(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%H:%M").time()
        except ValueError:
            return None

    def preset_checklist(eid):
        labels = ["Chairs","Snacks","Non-alcoholic drinks","Water","Plates/Cups","Utensils","Cooler/Ice","Games","Blankets","First aid kit","Alcohol","Weed"]
        for lab in labels:
            db.session.add(ChecklistItem(event_id=eid, label=lab))
        db.session.commit()

    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create_event():
        if request.method == "POST":
            title = request.form.get("title", "").strip() or "Untitled"
            description = request.form.get("description", "").strip()
            date_str = request.form.get("date", "").strip()
            start_str = request.form.get("start_time", "").strip()
            end_str = request.form.get("end_time", "").strip()
            capacity = request.form.get("capacity", "").strip()
            dry = request.form.get("dry") == "on"

            ev_date = None
            if date_str:
                try:
                    ev_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    ev_date = None

            ev = Event(
                title=title,
                description=description,
                date=ev_date,
                start_time=parse_time(start_str),
                end_time=parse_time(end_str),
                capacity=int(capacity) if capacity.isdigit() else None,
                dry=dry,
                creator_id=current_user.id
            )
            db.session.add(ev); db.session.commit()

            if request.form.get("include_checklist") == "on":
                preset_checklist(ev.id)
            other = request.form.get("other_item", "").strip()
            if other:
                db.session.add(ChecklistItem(event_id=ev.id, label=other)); db.session.commit()

            flash("Event created.", "success")
            return redirect(url_for("event_detail", event_id=ev.id))

        friends = User.query.all()
        return render_template("create.html", friends=friends)

    @app.route("/event/<int:event_id>")
    def event_detail(event_id):
        e = Event.query.get_or_404(event_id)
        yes, maybe, no = e.rsvp_counts()
        my = None
        if current_user.is_authenticated:
            r = RSVP.query.filter_by(event_id=e.id, user_id=current_user.id).first()
            my = r.status if r else None
        items = ChecklistItem.query.filter_by(event_id=e.id).order_by(ChecklistItem.id.asc()).all()
        return render_template("event.html", e=e, yes=yes, maybe=maybe, no=no, my=my, items=items)

    @app.route("/event/<int:event_id>/rsvp/<string:status>", methods=["POST"])
    @login_required
    def rsvp(event_id, status):
        if status not in ("yes","maybe","no"):
            flash("Invalid RSVP.", "error")
            return redirect(url_for("event_detail", event_id=event_id))
        e = Event.query.get_or_404(event_id)
        rec = RSVP.query.filter_by(event_id=e.id, user_id=current_user.id).first()
        if not rec:
            rec = RSVP(event_id=e.id, user_id=current_user.id, status=status)
            db.session.add(rec)
        else:
            rec.status = status
        db.session.commit()
        return redirect(url_for("event_detail", event_id=e.id))

    @app.route("/event/<int:event_id>/toggle/<int:item_id>", methods=["POST"])
    @login_required
    def toggle_item(event_id, item_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can modify the checklist.", "error")
            return redirect(url_for("event_detail", event_id=e.id))
        it = ChecklistItem.query.filter_by(id=item_id, event_id=event_id).first_or_404()
        it.checked = not it.checked
        db.session.commit()
        return redirect(url_for("event_detail", event_id=e.id))

    @app.route("/event/<int:event_id>/edit", methods=["GET","POST"])
    @login_required
    def edit_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can edit this event.", "error")
            return redirect(url_for("event_detail", event_id=e.id))
        if request.method == "POST":
            e.title = request.form.get("title", "").strip() or e.title
            e.description = request.form.get("description", "").strip()
            date_str = request.form.get("date", "").strip()
            start_str = request.form.get("start_time", "").strip()
            end_str = request.form.get("end_time", "").strip()
            capacity = request.form.get("capacity", "").strip()
            e.dry = request.form.get("dry") == "on"
            e.date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
            e.start_time = parse_time(start_str)
            e.end_time = parse_time(end_str)
            e.capacity = int(capacity) if capacity.isdigit() else None
            db.session.commit()
            flash("Event updated.", "success")
            return redirect(url_for("event_detail", event_id=e.id))
        return render_template("edit.html", e=e)

    @app.route("/event/<int:event_id>/delete", methods=["POST"])
    @login_required
    def delete_event(event_id):
        e = Event.query.get_or_404(event_id)
        if e.creator_id != current_user.id:
            flash("Only the organizer can delete this event.", "error")
            return redirect(url_for("event_detail", event_id=e.id))
        db.session.delete(e); db.session.commit()
        flash("Event deleted.", "success")
        return redirect(url_for("profile"))

    @app.route("/schedule", methods=["GET","POST"])
    @login_required
    def schedule():
        if request.method == "POST":
            sd = request.form.get("start_date"); ed = request.form.get("end_date")
            st = request.form.get("start_time"); et = request.form.get("end_time")
            if sd and ed:
                bb = BusyBlock(
                    user_id=current_user.id,
                    start_date=datetime.strptime(sd, "%Y-%m-%d").date(),
                    end_date=datetime.strptime(ed, "%Y-%m-%d").date(),
                    start_time=parse_time(st),
                    end_time=parse_time(et),
                )
                db.session.add(bb); db.session.commit()
                flash("Busy time saved.", "success")
            return redirect(url_for("schedule"))
        blocks = BusyBlock.query.filter_by(user_id=current_user.id).order_by(BusyBlock.start_date.asc()).all()
        return render_template("schedule.html", blocks=blocks)

    @app.route("/schedule/<int:block_id>/delete", methods=["POST"])
    @login_required
    def delete_block(block_id):
        bb = BusyBlock.query.filter_by(id=block_id, user_id=current_user.id).first_or_404()
        db.session.delete(bb); db.session.commit()
        flash("Removed.", "success")
        return redirect(url_for("schedule"))

    return app

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now())

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    date = db.Column(db.Date, nullable=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    dry = db.Column(db.Boolean, default=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    def rsvp_counts(self):
        yes = db.session.scalar(db.select(func.count()).select_from(RSVP).where(RSVP.event_id==self.id, RSVP.status=="yes"))
        maybe = db.session.scalar(db.select(func.count()).select_from(RSVP).where(RSVP.event_id==self.id, RSVP.status=="maybe"))
        no = db.session.scalar(db.select(func.count()).select_from(RSVP).where(RSVP.event_id==self.id, RSVP.status=="no"))
        return (yes or 0, maybe or 0, no or 0)

    def rsvp_name_lists(self):
        def names_for(status):
            q = db.session.execute(db.select(User.name).join(RSVP, RSVP.user_id==User.id).where(RSVP.event_id==self.id, RSVP.status==status).order_by(User.name.asc()))
            return [row[0].split(" ")[0] for row in q]
        return names_for("yes"), names_for("maybe"), names_for("no")

class RSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(10), nullable=False)

class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"))
    label = db.Column(db.Text, nullable=False)
    checked = db.Column(db.Boolean, default=False)

class BusyBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
