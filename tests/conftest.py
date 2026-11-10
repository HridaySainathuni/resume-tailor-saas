"""Test fixtures: an app with an in-memory database and a logged-in user."""
import pytest

from app import create_app, db
from app.config import TestingConfig
from app.models import User


@pytest.fixture()
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    with app.app_context():
        user = User(email="test@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        # Load the attributes tests need, then detach so the object
        # stays usable after the context (and its session) closes.
        _ = (user.id, user.created_at, user.email)
        db.session.expunge(user)
        return user


@pytest.fixture()
def auth_client(client, user):
    client.post("/auth/login", data={"email": "test@example.com", "password": "password123"})
    return client
