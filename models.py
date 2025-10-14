from sqlalchemy import func, UniqueConstraint
from flask_login import UserMixin
from extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now())

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.Text, default='')
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    capacity = db.Column(db.Integer)  # optional max attendees
    checklist = db.Column(db.Text, default='')  # newline-separated items

    def rsvp_counts(self):
        yes = RSVP.query.filter_by(event_id=self.id, status='yes').count()
        maybe = RSVP.query.filter_by(event_id=self.id, status='maybe').count()
        no = RSVP.query.filter_by(event_id=self.id, status='no').count()
        return yes, maybe, no

    def is_full(self):
        if self.capacity and self.capacity > 0:
            yes = RSVP.query.filter_by(event_id=self.id, status='yes').count()
            return yes >= self.capacity
        return False

class RSVP(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'event_id', name='uniq_user_event'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default='yes')  # yes / no / maybe
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
