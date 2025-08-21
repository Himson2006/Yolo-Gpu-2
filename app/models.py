from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# Initialize SQLAlchemy (usually done once in your app factory)
# db = SQLAlchemy(app)  # if you create the app here
# If you register models via application factory pattern, import db from your __init__.py
from app import db

class Event(db.Model):
    __tablename__ = 'events'

    event_id = db.Column(db.String(64), primary_key=True)
    device_id = db.Column(db.String(64), nullable=False)
    timestamp_start_utc = db.Column(db.DateTime(timezone=False), nullable=False)
    timestamp_end_utc = db.Column(db.DateTime(timezone=False), nullable=False)
    video_duration_seconds = db.Column(db.Float, nullable=False)
    primary_species = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    remote_video_path = db.Column(db.String(256), nullable=True)
    remote_json_path = db.Column(db.String(256), nullable=True)

    # Relationship to detections
    detections = db.relationship(
        'Detection',
        backref='event',
        cascade='all, delete-orphan',
        lazy='joined',
        uselist=False
    )

class Detection(db.Model):
    __tablename__ = 'detections'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.String(64),
        db.ForeignKey('events.event_id', ondelete='CASCADE'),
        nullable=False,
        unique = True
    )
    detection_json = db.Column(JSONB, nullable=False)
    classes_detected = db.Column(ARRAY(db.String(64)), nullable=False)
    max_count_per_frame = db.Column(JSONB, nullable=False)

    def __repr__(self):
        return f"<Detection {self.id} for Event {self.event_id}>"