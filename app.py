from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, time
import os

# --- App setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# --- Database setup ---
db_url = os.environ.get("DATABASE_URL", "sqlite:///planpals.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --- Login manager setup ---
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    schedule = db.Column(db.Text, default="")  # JSON-encoded schedule string

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    dry_gathering = db.Column(db.Boolean, default=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Create tables if not exist ---
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print("⚠️ Database initialization failed:", e)

# --- Routes ---
@app.route("/")
def index():
    events = Event.query.order_by(Event.date.asc()).all()
    return render_template("index.html", events=events)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for("register"))
        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for("index"))
        flash("Invalid login.")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.")
    return redirect(url_for("index"))

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form["title"]
        desc = request.form["description"]
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        dry = "dry_gathering" in request.form
        event = Event(
            title=title,
            description=desc,
            date=date,
            start_time=datetime.strptime(start_time, "%H:%M").time() if start_time else None,
            end_time=datetime.strptime(end_time, "%H:%M").time() if end_time else None,
            dry_gathering=dry,
            creator_id=current_user.id
        )
        db.session.add(event)
        db.session.commit()
        flash("Event created successfully!")
        return redirect(url_for("index"))
    return render_template("create.html")

@app.route("/profile")
@login_required
def profile():
    my_events = Event.query.filter_by(creator_id=current_user.id).all()
    return render_template("profile.html", events=my_events)

@app.route("/healthz")
def healthz():
    return "OK", 200

@app.route("/readyz")
def readyz():
    return "READY", 200


# --- Run ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
