"""Page routes — landing, dashboard, etc."""
from flask import Blueprint, render_template
from flask_login import current_user, login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def landing():
    if current_user.is_authenticated:
        return render_template("dashboard.html", user=current_user)
    return render_template("landing.html")


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)
