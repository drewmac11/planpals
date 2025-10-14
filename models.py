from __future__ import annotations
import datetime as dt
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship, mapped_column, Mapped
from extensions import db

class User(UserMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow, nullable=False)

    events = relationship("Event", back_populates="creator", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Event(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    date: Mapped[dt.date] = mapped_column(nullable=False, index=True)
    description: Mapped[str] = mapped_column(default="")
    capacity: Mapped[int] = mapped_column(default=0)
    dry: Mapped[bool] = mapped_column(default=False)

    doors_open_time: Mapped[dt.time | None] = mapped_column(nullable=True)
    leave_by_time: Mapped[dt.time | None] = mapped_column(nullable=True)
    no_specified_end_time: Mapped[bool] = mapped_column(default=False, nullable=False)

    creator_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow, nullable=False)

    creator = relationship("User", back_populates="events")
    rsvps = relationship("RSVP", back_populates="event", cascade="all, delete-orphan")
    checklist_items = relationship("ChecklistItem", back_populates="event", cascade="all, delete-orphan")

    def time_window(self):
    # Compute start/end datetimes using date + optional times; robust to NULLs.
    start_t = getattr(self, 'doors_open_time', None) or time(0, 0)
    dt_start = datetime.combine(self.date, start_t)
    if getattr(self, 'leave_by_time', None):
        dt_end = datetime.combine(self.date, self.leave_by_time)
    elif getattr(self, 'no_specified_end_time', False):
        dt_end = dt_start + timedelta(hours=4)
    else:
        dt_end = dt_start
    return dt_start, dt_end
        return dt_start, datetime.combine(self.date, self.leave_by_time)

class RSVP(db.Model):
    __table_args__ = (UniqueConstraint("event_id","user_id", name="uq_event_user"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(default="maybe")  # going, maybe, no

    event = relationship("Event", back_populates="rsvps")
    user = relationship("User")

class AvailabilityWindow(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    date: Mapped[dt.date] = mapped_column(nullable=False, index=True)
    start_time: Mapped[dt.time] = mapped_column(nullable=False)
    end_time: Mapped[dt.time] = mapped_column(nullable=False)
    is_unavailable: Mapped[bool] = mapped_column(default=True, nullable=False)

    user = relationship("User")

class ChecklistItem(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(nullable=False)
    is_checked: Mapped[bool] = mapped_column(default=False, nullable=False)
    added_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    event = relationship("Event", back_populates="checklist_items")
    added_by_user = relationship("User")

default_bring_items = [
    "Chairs","Snacks","Water","Ice","Cups","Plates","Napkins","Games","Music speaker",
    "Cooled drinks","Dessert","Sunscreen","Blankets","Paper towels","Trash bags"
]
