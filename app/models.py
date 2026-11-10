"""Database models."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import DateTime, TypeDecorator
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def _utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store datetimes as naive UTC in the database, return aware UTC in Python.

    SQLite drops timezone info, so a plain DateTime(timezone=True) column
    comes back naive and breaks aware comparisons. This type converts
    aware values to naive UTC on write and re-attaches UTC on read, so
    code always works with timezone-aware datetimes.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(UTCDateTime, default=_utcnow)

    # Stripe
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    is_subscribed = db.Column(db.Boolean, default=False)
    subscription_end = db.Column(UTCDateTime)

    # Usage
    free_uses_remaining = db.Column(db.Integer, default=3)  # 3 free tailors
    total_tailors = db.Column(db.Integer, default=0)

    # Password reset
    reset_token_hash = db.Column(db.String(255))
    reset_token_expiry = db.Column(UTCDateTime)

    tailors = db.relationship("TailorResult", backref="user", lazy="dynamic")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def can_tailor(self) -> bool:
        # Column defaults only apply on insert, so a new unsaved user
        # has None here. Treat None as the documented default of 3 uses.
        remaining = self.free_uses_remaining if self.free_uses_remaining is not None else 3
        return bool(self.is_subscribed) or remaining > 0

    def generate_reset_token(self) -> str:
        """Generate a password reset token valid for 1 hour."""
        token = secrets.token_urlsafe(32)
        self.reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
        self.reset_token_expiry = _utcnow() + timedelta(hours=1)
        return token

    @staticmethod
    def verify_reset_token(token: str):
        """Find user by valid reset token."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        user = User.query.filter_by(reset_token_hash=token_hash).first()
        if user and user.reset_token_expiry and user.reset_token_expiry > _utcnow():
            return user
        return None


class TailorResult(db.Model):
    __tablename__ = "tailor_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_title = db.Column(db.String(500))
    company = db.Column(db.String(255))
    original_resume = db.Column(db.Text, nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    tailored_resume = db.Column(db.Text, nullable=False)
    cover_letter = db.Column(db.Text)
    created_at = db.Column(UTCDateTime, default=_utcnow)

    __table_args__ = (
        db.Index("ix_tailor_results_user_id_created_at", "user_id", "created_at"),
    )
