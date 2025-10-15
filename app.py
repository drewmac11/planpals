import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecretkey")

    # ✅ Database configuration (use DATABASE_URL from Railway)
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///planpals.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    # ----------------- MODELS -----------------
    class User(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        email = db.Column(db.String(150), unique=True, nullable=False)
        password_hash = db.Column(db.String(255), nullable=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class Event(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(200), nullable=False)
        description = db.Column(db.Text)
        date = db.Column(db.Date, nullable=False)
        start_time = db.Column(db.Time)
        end_time = db.Column(db.Time)
        capacity = db.Column(db.Integer, nullable=False)
        checklist = db.Column(db.Text, default="")
        dry = db.Column(db.Boolean, default=False)
        creator_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ----------------- ROUTES -----------------
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

            hashed_pw = generate_password_hash(password)
            new_user = User(name=name, email=email, password_hash=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully!", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form["email"]
            password = request.form["password"]
            user = User.query.filter_by(email=email).first()

            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for("index"))
            else:
                flash("Invalid credentials", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/create", methods=["GET", "POST"])
    @login_required
    def create():
        if request.method == "POST":
            title = request.form["title"]
            description = request.form.get("description", "")
            date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            start_time = datetime.strptime(request.form["start_time"], "%H:%M").time() if request.form.get("start_time") else None
            end_time = datetime.strptime(request.form["end_time"], "%H:%M").time() if request.form.get("end_time") else None
            capacity = int(request.form["capacity"])
            dry = "dry" in request.form
            checklist = request.form.get("checklist", "")

            event = Event(
                title=title,
                description=description,
                date=date,
                start_time=start_time,
                end_time=end_time,
                capacity=capacity,
                dry=dry,
                checklist=checklist,
                creator_id=current_user.id,
            )
            db.session.add(event)
            db.session.commit()
            flash("Event created successfully!", "success")
            return redirect(url_for("index"))

        return render_template("create.html")

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            current_user.name = request.form["name"]
            db.session.commit()
            flash("Profile updated!", "success")
            return redirect(url_for("profile"))

        user_events = Event.query.filter_by(creator_id=current_user.id).all()
        return render_template("profile.html", user=current_user, events=user_events)

    # ----------------- INITIALIZE DATABASE -----------------
    with app.app_context():
        db.create_all()

    return app


# ✅ Railway entry point
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app = create_app()
    app.run(host="0.0.0.0", port=port)
