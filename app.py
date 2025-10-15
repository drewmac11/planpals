import os
from datetime import datetime, date, time
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from sqlalchemy import text

db = SQLAlchemy()
login_manager = LoginManager()

def _convert_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
    raw_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = _convert_db_url(raw_url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "login"

    class User(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        email = db.Column(db.String(150), unique=True, nullable=False)
        password_hash = db.Column(db.String(255), nullable=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class Event(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(200), nullable=False)
        date = db.Column(db.Date, nullable=True)
        start_time = db.Column(db.Time, nullable=True)
        end_time = db.Column(db.Time, nullable=True)
        description = db.Column(db.Text, default="")
        capacity = db.Column(db.Integer, nullable=True)
        dry = db.Column(db.Boolean, default=False)
        checklist = db.Column(db.Text, default="")
        creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    class RSVP(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
        status = db.Column(db.String(10), default="maybe")
        __table_args__ = (db.UniqueConstraint('user_id','event_id', name='uq_user_event'),)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

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

    @app.route("/")
    def index():
        try:
            events = Event.query.order_by(Event.date.asc().nulls_last()).all()
        except Exception:
            events = []
        return render_template("index.html", events=events)

    @app.route("/register", methods=["GET","POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name","").strip() or "John Doe"
            email = request.form.get("email","").strip().lower()
            password = request.form.get("password","")
            if not email or not password:
                flash("Email and password required", "error")
                return redirect(url_for("register"))
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "error")
                return redirect(url_for("login"))
            from werkzeug.security import generate_password_hash
            u = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(u)
            db.session.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("auth.html", title="Register")

    @app.route("/login", methods=["GET","POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email","").strip().lower()
            password = request.form.get("password","")
            from werkzeug.security import check_password_hash
            u = User.query.filter_by(email=email).first()
            if not u or not check_password_hash(u.password_hash, password):
                flash("Invalid credentials", "error")
                return redirect(url_for("login"))
            login_user(u)
            return redirect(url_for("index"))
        return render_template("auth.html", title="Login")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/create", methods=["GET","POST"])
    @login_required
    def create_event():
        if request.method == "POST":
            title = request.form.get("title","").strip()
            date_str = request.form.get("date") or ""
            start_str = request.form.get("start_time") or ""
            end_str = request.form.get("end_time") or ""
            desc = request.form.get("description") or ""
            capacity = request.form.get("capacity") or None
            dry = request.form.get("dry","0") == "1"
            checklist = (request.form.get("checklist") or "").strip()

            d = None
            if date_str:
                try: d = datetime.strptime(date_str, "%Y-%m-%d").date()
                except: d = None

            st = None
            if start_str:
                try: st = datetime.strptime(start_str, "%H:%M").time()
                except: st = None

            et = None
            if end_str:
                try: et = datetime.strptime(end_str, "%H:%M").time()
                except: et = None

            cap = int(capacity) if capacity else None

            e = Event(title=title, date=d, start_time=st, end_time=et,
                      description=desc, capacity=cap, dry=dry, checklist=checklist,
                      creator_id=current_user.id)
            db.session.add(e)
            db.session.commit()
            flash("Event created", "success")
            return redirect(url_for("index"))
        return render_template("create.html")

    @app.route("/rsvp/<int:event_id>/<status>")
    @login_required
    def rsvp(event_id, status):
        status = status.lower()
        if status not in ("yes","no","maybe"):
            flash("Invalid RSVP", "error")
            return redirect(url_for("index"))
        ev = db.session.get(Event, event_id)
        if not ev:
            flash("Event not found", "error")
            return redirect(url_for("index"))
        r = db.session.execute(db.select(RSVP).filter_by(user_id=current_user.id, event_id=event_id)).scalar_one_or_none()
        if not r:
            r = RSVP(user_id=current_user.id, event_id=event_id, status=status)
            db.session.add(r)
        else:
            r.status = status
        db.session.commit()
        flash("RSVP updated", "success")
        return redirect(url_for("index"))

    @app.route("/profile", methods=["GET","POST"])
    @login_required
    def profile():
        if request.method == "POST":
            name = (request.form.get("name") or "").strip() or current_user.name
            current_user.name = name
            db.session.commit()
            flash("Profile updated", "success")
            return redirect(url_for("profile"))
        return render_template("profile.html")

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
