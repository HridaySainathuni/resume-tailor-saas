"""Tailoring API routes. Thin handlers only: validation, service calls, responses."""
import io

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required

from app import db
from app.models import TailorResult
from app.services.exports import (
    build_docx,
    cover_letter_pdf_html,
    render_pdf,
    resume_pdf_html,
    safe_filename,
)
from app.services.job_import import fetch_job_posting
from app.services.keywords import score_resume
from app.services.llm import create_anthropic_client, generate_cover_letter_text, tailor_resume_text

tailor_bp = Blueprint("tailor", __name__)


def _get_tailor_input(data):
    resume = (data.get("resume") or "").strip()
    job_description = (data.get("job_description") or "").strip()
    job_title = (data.get("job_title") or "").strip()
    company = (data.get("company") or "").strip()
    return resume, job_description, job_title, company


def _get_result_or_404(result_id):
    result = TailorResult.query.filter_by(id=result_id, user_id=current_user.id).first()
    if not result:
        return None, (jsonify({"error": "Not found"}), 404)
    return result, None


@tailor_bp.route("/tailor", methods=["POST"])
@login_required
def tailor_resume():
    if not current_user.can_tailor():
        return jsonify({"error": "Please subscribe to continue. You've used all free tailors."}), 402
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    resume, job_description, job_title, company = _get_tailor_input(data)
    if not resume or not job_description:
        return jsonify({"error": "Resume and job description are required"}), 400
    if len(resume) > 15000 or len(job_description) > 10000:
        return jsonify({"error": "Input too long. Resume max 15000 chars, JD max 10000 chars."}), 400
    api_key = current_app.config["ANTHROPIC_API_KEY"]
    if not api_key:
        return jsonify({"error": "Service not configured"}), 500
    try:
        client = create_anthropic_client(api_key)
        tailored = tailor_resume_text(client, resume, job_description, job_title, company)
    except Exception:
        return jsonify({"error": "AI service error"}), 500
    result = TailorResult(
        user_id=current_user.id,
        job_title=job_title,
        company=company,
        original_resume=resume,
        job_description=job_description,
        tailored_resume=tailored,
    )
    db.session.add(result)
    if not current_user.is_subscribed:
        current_user.free_uses_remaining -= 1
    current_user.total_tailors += 1
    db.session.commit()
    return jsonify(
        {
            "tailored_resume": tailored,
            "result_id": result.id,
            "remaining_free": current_user.free_uses_remaining if not current_user.is_subscribed else None,
        }
    )


@tailor_bp.route("/history", methods=["GET"])
@login_required
def history():
    results = (
        TailorResult.query.filter_by(user_id=current_user.id)
        .order_by(TailorResult.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(
        [
            {
                "id": r.id,
                "job_title": r.job_title,
                "company": r.company,
                "has_cover_letter": bool(r.cover_letter),
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]
    )


@tailor_bp.route("/history/<int:result_id>", methods=["GET"])
@login_required
def get_result(result_id):
    result, error = _get_result_or_404(result_id)
    if error:
        return error
    return jsonify(
        {
            "id": result.id,
            "job_title": result.job_title,
            "company": result.company,
            "original_resume": result.original_resume,
            "job_description": result.job_description,
            "tailored_resume": result.tailored_resume,
            "cover_letter": result.cover_letter,
            "created_at": result.created_at.isoformat(),
        }
    )


@tailor_bp.route("/ats-score", methods=["POST"])
@login_required
def ats_score():
    """Score how well a resume matches a job description's keywords."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Resume and job description required"}), 400
    resume_text = (data.get("resume") or "").strip()
    jd_text = (data.get("job_description") or "").strip()
    if not resume_text or not jd_text:
        return jsonify({"error": "Resume and job description required"}), 400
    return jsonify(score_resume(resume_text, jd_text))


@tailor_bp.route("/cover-letter", methods=["POST"])
@login_required
def generate_cover_letter():
    if not current_user.can_tailor():
        return jsonify({"error": "Please subscribe to continue. You've used all free tailors."}), 402
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    resume, job_description, job_title, company = _get_tailor_input(data)
    result_id = data.get("result_id")
    if not resume or not job_description:
        return jsonify({"error": "Resume and job description are required"}), 400
    api_key = current_app.config["ANTHROPIC_API_KEY"]
    if not api_key:
        return jsonify({"error": "Service not configured"}), 500
    try:
        client = create_anthropic_client(api_key)
        cover_letter = generate_cover_letter_text(client, resume, job_description, job_title, company)
    except Exception:
        return jsonify({"error": "AI service error"}), 500
    if result_id:
        result = TailorResult.query.filter_by(id=result_id, user_id=current_user.id).first()
        if result:
            result.cover_letter = cover_letter
            db.session.commit()
    if not current_user.is_subscribed:
        current_user.free_uses_remaining -= 1
    current_user.total_tailors += 1
    db.session.commit()
    return jsonify(
        {
            "cover_letter": cover_letter,
            "remaining_free": current_user.free_uses_remaining if not current_user.is_subscribed else None,
        }
    )


@tailor_bp.route("/download-docx/<int:result_id>", methods=["GET"])
@login_required
def download_docx(result_id):
    result, error = _get_result_or_404(result_id)
    if error:
        return error
    try:
        buf = build_docx(result.tailored_resume, result.job_title, result.company)
    except ImportError:
        return jsonify({"error": "DOCX generation not available"}), 500
    filename = safe_filename(f"resume_{result.job_title or 'tailored'}_{result.company or 'resume'}.docx")
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


@tailor_bp.route("/download-cover-letter/<int:result_id>", methods=["GET"])
@login_required
def download_cover_letter_pdf(result_id):
    result, error = _get_result_or_404(result_id)
    if error:
        return error
    if not result.cover_letter:
        return jsonify({"error": "No cover letter found"}), 404
    try:
        pdf = render_pdf(cover_letter_pdf_html(result.cover_letter))
    except ImportError:
        return jsonify({"error": "PDF generation not available"}), 500
    filename = safe_filename(f"cover_letter_{result.job_title or 'application'}_{result.company or ''}.pdf")
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=filename)


@tailor_bp.route("/import-jd", methods=["POST"])
@login_required
def import_job_description():
    """Import a job description from a URL by extracting text content."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "URL is required"}), 400
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400
    try:
        return jsonify(fetch_job_posting(url))
    except ValueError:
        return jsonify({"error": "Invalid URL"}), 400
    except Exception:
        return jsonify({"error": "Could not fetch URL. Try pasting the job description directly."}), 400


@tailor_bp.route("/download-pdf/<int:result_id>", methods=["GET"])
@login_required
def download_pdf(result_id):
    result, error = _get_result_or_404(result_id)
    if error:
        return error
    try:
        pdf = render_pdf(resume_pdf_html(result.tailored_resume))
    except ImportError:
        return jsonify({"error": "PDF generation not available"}), 500
    filename = safe_filename(f"resume_{result.job_title or 'tailored'}_{result.company or 'resume'}.pdf")
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=filename)
