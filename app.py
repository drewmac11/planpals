from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///planpals.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    with app.app_context():
        db.create_all()

    from models import User, Event

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route('/')
    def index():
        events = Event.query.order_by(Event.date.asc()).all()
        return render_template('index.html', events=events)

    @app.route('/register', methods=['GET','POST'])
    def register():
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
            else:
                user = User(name=name, email=email, password_hash=generate_password_hash(password))
                db.session.add(user)
                db.session.commit()
                flash('Registration successful!', 'success')
                return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/login', methods=['GET','POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('index'))
            flash('Invalid credentials', 'error')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/create', methods=['GET','POST'])
    @login_required
    def create_event():
        if request.method == 'POST':
            title = request.form['title']
            date_str = request.form['date']
            desc = request.form['description']
            dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            e = Event(title=title, date=dt, description=desc, creator_id=current_user.id)
            db.session.add(e)
            db.session.commit()
            flash('Event created!', 'success')
            return redirect(url_for('index'))
        return render_template('create.html')

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
