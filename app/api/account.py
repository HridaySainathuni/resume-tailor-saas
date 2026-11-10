"""Account settings routes — password change, data export, account deletion."""
from datetime import datetime, timezone

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from app import db
from app.models import TailorResult, User

account_bp = Blueprint("account", __name__)


@account_bp.route("/account")
@login_required
def settings():
    return render_template("account.html", user=current_user)


@account_bp.route("/account/change-password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_user.check_password(current_pw):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("account.settings"))

    if len(new_pw) < 8:
        flash("New password must be at least 8 characters.", "error")
        return redirect(url_for("account.settings"))

    if new_pw != confirm_pw:
        flash("New passwords don't match.", "error")
        return redirect(url_for("account.settings"))

    current_user.set_password(new_pw)
    db.session.commit()
    flash("Password updated successfully.", "success")
    return redirect(url_for("account.settings"))


@account_bp.route("/account/export")
@login_required
def export_data():
    results = (
        TailorResult.query
        .filter_by(user_id=current_user.id)
        .order_by(TailorResult.created_at.desc())
        .all()
    )

    data = {
        "account": {
            "email": current_user.email,
            "created_at": current_user.created_at.isoformat(),
            "total_tailors": current_user.total_tailors,
            "is_subscribed": current_user.is_subscribed,
        },
        "tailored_resumes": [
            {
                "id": r.id,
                "job_title": r.job_title,
                "company": r.company,
                "original_resume": r.original_resume,
                "job_description": r.job_description,
                "tailored_resume": r.tailored_resume,
                "cover_letter": r.cover_letter,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    response = jsonify(data)
    response.headers["Content-Disposition"] = "attachment; filename=resumetailor_export.json"
    return response


@account_bp.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    password = request.form.get("password", "")

    if not current_user.check_password(password):
        flash("Incorrect password. Account not deleted.", "error")
        return redirect(url_for("account.settings"))

    # Delete all tailor results first
    TailorResult.query.filter_by(user_id=current_user.id).delete()

    # Delete user
    user = db.session.get(User, current_user.id)
    db.session.delete(user)
    db.session.commit()

    logout_user()
    flash("Your account has been permanently deleted.", "success")
    return redirect(url_for("pages.landing"))
