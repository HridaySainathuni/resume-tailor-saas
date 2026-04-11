"""Resume Tailor SaaS — Flask app factory."""
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY="change-me",
        SQLALCHEMY_DATABASE_URI="sqlite:///resume_tailor.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    # Load config from env
    import os
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", app.config["SECRET_KEY"])
    db_url = os.getenv("DATABASE_URL", app.config["SQLALCHEMY_DATABASE_URI"])
    # Fix Heroku/Render postgres:// -> postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY", "")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    app.config["STRIPE_PRICE_ID"] = os.getenv("STRIPE_PRICE_ID", "")
    app.config["STRIPE_WEBHOOK_SECRET"] = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    app.config["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.tailor import tailor_bp
    from app.api.billing import billing_bp
    from app.api.pages import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(tailor_bp, url_prefix="/api")
    app.register_blueprint(billing_bp, url_prefix="/billing")

    with app.app_context():
        db.create_all()

    return app
