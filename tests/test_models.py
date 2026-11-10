"""Tests for the User and TailorResult models."""
from datetime import timedelta

from app import db
from app.models import TailorResult, User


def test_password_round_trip(app):
    with app.app_context():
        user = User(email="a@example.com")
        user.set_password("password123")
        assert user.check_password("password123")
        assert not user.check_password("wrong")


def test_can_tailor_uses_free_uses(app):
    with app.app_context():
        user = User(email="a@example.com")
        user.set_password("password123")
        assert user.can_tailor()
        user.free_uses_remaining = 0
        assert not user.can_tailor()
        user.is_subscribed = True
        assert user.can_tailor()


def test_reset_token_verifies_and_expires(app):
    with app.app_context():
        user = User(email="a@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        token = user.generate_reset_token()
        db.session.commit()
        assert User.verify_reset_token(token) is not None
        assert User.verify_reset_token("not-a-token") is None
        user.reset_token_expiry = user.reset_token_expiry - timedelta(hours=2)
        db.session.commit()
        assert User.verify_reset_token(token) is None


def test_created_at_is_timezone_aware(app, user):
    assert user.created_at is not None
    assert user.created_at.tzinfo is not None


def test_tailor_result_has_user_and_created_index(app, user):
    with app.app_context():
        result = TailorResult(
            user_id=user.id,
            original_resume="resume",
            job_description="job",
            tailored_resume="tailored",
        )
        db.session.add(result)
        db.session.commit()
        assert result.id is not None
        index_names = {index.name for index in TailorResult.__table__.indexes}
        assert "ix_tailor_results_user_id_created_at" in index_names
