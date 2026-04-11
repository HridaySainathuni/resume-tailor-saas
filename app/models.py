"""Database models."""
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Stripe
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    is_subscribed = db.Column(db.Boolean, default=False)
    subscription_end = db.Column(db.DateTime)

    # Usage
    free_uses_remaining = db.Column(db.Integer, default=3)  # 3 free tailors
    total_tailors = db.Column(db.Integer, default=0)

    tailors = db.relationship("TailorResult", backref="user", lazy="dynamic")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def can_tailor(self) -> bool:
        return self.is_subscribed or self.free_uses_remaining > 0


class TailorResult(db.Model):
    __tablename__ = "tailor_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_title = db.Column(db.String(500))
    company = db.Column(db.String(255))
    original_resume = db.Column(db.Text, nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    tailored_resume = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
