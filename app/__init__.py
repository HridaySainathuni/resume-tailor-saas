"""Resume Tailor SaaS — Flask app factory."""
import os

from flask import Flask, render_template
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI="sqlite:///resume_tailor.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    # Load config from env — SECRET_KEY must be set in production
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me-in-production")
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

    # --- Rate Limiting ---
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=["200 per hour"],
            storage_uri="memory://",
        )
        # Stricter limits on expensive endpoints
        @app.before_request
        def _attach_limiter():
            app.extensions["limiter"] = limiter

        limiter.limit("5 per minute")(lambda: None)  # placeholder

    except ImportError:
        limiter = None

    # --- Security Headers ---
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # --- Register Blueprints ---
    from app.api.auth import auth_bp
    from app.api.tailor import tailor_bp
    from app.api.billing import billing_bp
    from app.api.pages import pages_bp
    from app.api.account import account_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(tailor_bp, url_prefix="/api")
    app.register_blueprint(billing_bp, url_prefix="/billing")
    app.register_blueprint(account_bp)

    # --- Rate limit specific routes ---
    if limiter:
        limiter.limit("10 per minute")(tailor_bp)
        limiter.limit("20 per minute")(auth_bp)

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def rate_limited(e):
        return {"error": "Too many requests. Please slow down."}, 429

    with app.app_context():
        db.create_all()

    return app
