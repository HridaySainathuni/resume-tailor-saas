"""Resume Tailor SaaS — Flask app factory."""
from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"], storage_uri="memory://")


def create_app(config_class=Config, config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if config_overrides:
        app.config.update(config_overrides)
    if not app.config.get("TESTING"):
        config_class.validate()

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    from app.api.account import account_bp
    from app.api.auth import auth_bp
    from app.api.billing import billing_bp
    from app.api.pages import pages_bp
    from app.api.tailor import tailor_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(tailor_bp, url_prefix="/api")
    app.register_blueprint(billing_bp, url_prefix="/billing")
    app.register_blueprint(account_bp)

    limiter.limit("10 per minute")(tailor_bp)
    limiter.limit("20 per minute")(auth_bp)

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
