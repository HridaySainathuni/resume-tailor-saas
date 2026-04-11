"""Core tailoring API — sends resume + job description to Claude."""
import io
import re
from collections import Counter
from html import escape

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required

import anthropic

from app import db
from app.models import TailorResult

tailor_bp = Blueprint("tailor", __name__)

COVER_LETTER_PROMPT = """You are an expert cover letter writer. Write a compelling, personalized cover letter for this job application.

Rules:
1. Use the resume to draw out relevant achievements and experience — never fabricate
2. Open with a strong hook specific to the company/role, not a generic opener
3. Show genuine enthusiasm and knowledge of the company when possible
4. Connect the candidate's experience to the job requirements naturally
5. Keep it concise — 3-4 paragraphs, under 400 words
6. Professional but conversational tone — not stiff or robotic
7. End with a confident call-to-action
8. Output ONLY the cover letter text, no commentary or labels
9. Do NOT include placeholder brackets like [Your Name] — write it ready to send"""

# Common stop words to exclude from keyword matching
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "not", "no", "so", "if",
    "as", "it", "its", "we", "our", "you", "your", "they", "their",
    "this", "that", "these", "those", "from", "about", "into", "through",
    "during", "before", "after", "above", "below", "up", "down", "out",
    "off", "over", "under", "again", "further", "then", "once", "all",
    "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "than", "too", "very", "just", "also", "well", "etc",
    "ability", "able", "experience", "work", "working", "role", "team",
    "including", "responsibilities", "requirements", "preferred",
    "qualifications", "strong", "excellent", "required",
}

SYSTEM_PROMPT = """You are an expert resume writer and career coach. Your job is to tailor a resume to a specific job description.

Rules:
1. Keep ALL truthful experience — never fabricate or exaggerate
2. Reorder bullet points to prioritize relevant experience
3. Mirror keywords and phrases from the job description naturally
4. Quantify achievements where possible
5. Adjust the professional summary to target this specific role
6. Remove or de-emphasize irrelevant details
7. Keep formatting clean and ATS-friendly
8. Output ONLY the tailored resume text, no commentary"""


@tailor_bp.route("/tailor", methods=["POST"])
@login_required
def tailor_resume():
    if not current_user.can_tailor():
        return jsonify({"error": "Please subscribe to continue. You've used all free tailors."}), 402

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    resume = data.get("resume", "").strip()
    job_description = data.get("job_description", "").strip()
    job_title = data.get("job_title", "").strip()
    company = data.get("company", "").strip()

    if not resume or not job_description:
        return jsonify({"error": "Resume and job description are required"}), 400

    if len(resume) > 15000 or len(job_description) > 10000:
        return jsonify({"error": "Input too long. Resume max 15000 chars, JD max 10000 chars."}), 400

    api_key = current_app.config["ANTHROPIC_API_KEY"]
    if not api_key:
        return jsonify({"error": "Service not configured"}), 500

    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = f"""Here is my current resume:

---
{resume}
---

Here is the job description I'm applying to:

Job Title: {job_title or 'Not specified'}
Company: {company or 'Not specified'}

---
{job_description}
---

Please tailor my resume for this specific role."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        tailored = message.content[0].text
    except Exception as e:
        return jsonify({"error": f"AI service error: {str(e)}"}), 500

    # Save result
    result = TailorResult(
        user_id=current_user.id,
        job_title=job_title,
        company=company,
        original_resume=resume,
        job_description=job_description,
        tailored_resume=tailored,
    )
    db.session.add(result)

    # Decrement free uses if not subscribed
    if not current_user.is_subscribed:
        current_user.free_uses_remaining -= 1
    current_user.total_tailors += 1
    db.session.commit()

    return jsonify({
        "tailored_resume": tailored,
        "result_id": result.id,
        "remaining_free": current_user.free_uses_remaining if not current_user.is_subscribed else None,
    })


@tailor_bp.route("/history", methods=["GET"])
@login_required
def history():
    results = (
        TailorResult.query
        .filter_by(user_id=current_user.id)
        .order_by(TailorResult.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([
        {
            "id": r.id,
            "job_title": r.job_title,
            "company": r.company,
            "has_cover_letter": bool(r.cover_letter),
            "created_at": r.created_at.isoformat(),
        }
        for r in results
    ])


@tailor_bp.route("/history/<int:result_id>", methods=["GET"])
@login_required
def get_result(result_id):
    result = TailorResult.query.filter_by(id=result_id, user_id=current_user.id).first()
    if not result:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": result.id,
        "job_title": result.job_title,
        "company": result.company,
        "original_resume": result.original_resume,
        "job_description": result.job_description,
        "tailored_resume": result.tailored_resume,
        "cover_letter": result.cover_letter,
        "created_at": result.created_at.isoformat(),
    })


def _extract_keywords(text: str) -> Counter:
    """Extract meaningful keywords from text."""
    words = re.findall(r'[a-z][a-z+#.-]{1,30}', text.lower())
    return Counter(w for w in words if w not in _STOP_WORDS)


@tailor_bp.route("/ats-score", methods=["POST"])
@login_required
def ats_score():
    """Score how well a resume matches a job description's keywords."""
    data = request.get_json()
    resume_text = data.get("resume", "").strip()
    jd_text = data.get("job_description", "").strip()

    if not resume_text or not jd_text:
        return jsonify({"error": "Resume and job description required"}), 400

    jd_keywords = _extract_keywords(jd_text)
    resume_keywords = _extract_keywords(resume_text)

    # Get top JD keywords (most frequent = most important)
    top_jd = jd_keywords.most_common(40)

    matched = []
    missing = []
    for keyword, count in top_jd:
        if keyword in resume_keywords:
            matched.append({"keyword": keyword, "jd_count": count,
                            "resume_count": resume_keywords[keyword]})
        else:
            missing.append({"keyword": keyword, "jd_count": count})

    total = len(top_jd)
    match_count = len(matched)
    score = int((match_count / total * 100)) if total > 0 else 0

    # Grade
    if score >= 80:
        grade = "Excellent"
    elif score >= 60:
        grade = "Good"
    elif score >= 40:
        grade = "Fair"
    else:
        grade = "Needs Work"

    return jsonify({
        "score": score,
        "grade": grade,
        "matched_keywords": matched[:20],
        "missing_keywords": missing[:15],
        "total_jd_keywords": total,
        "matched_count": match_count,
    })


@tailor_bp.route("/cover-letter", methods=["POST"])
@login_required
def generate_cover_letter():
    """Generate a cover letter from resume + job description."""
    if not current_user.can_tailor():
        return jsonify({"error": "Please subscribe to continue. You've used all free tailors."}), 402

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    resume = data.get("resume", "").strip()
    job_description = data.get("job_description", "").strip()
    job_title = data.get("job_title", "").strip()
    company = data.get("company", "").strip()
    result_id = data.get("result_id")

    if not resume or not job_description:
        return jsonify({"error": "Resume and job description are required"}), 400

    api_key = current_app.config["ANTHROPIC_API_KEY"]
    if not api_key:
        return jsonify({"error": "Service not configured"}), 500

    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = f"""Here is my resume:

---
{resume}
---

Here is the job I'm applying to:

Job Title: {job_title or 'Not specified'}
Company: {company or 'Not specified'}

---
{job_description}
---

Please write a cover letter for this application."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=COVER_LETTER_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        cover_letter = message.content[0].text
    except Exception as e:
        return jsonify({"error": f"AI service error: {str(e)}"}), 500

    # If there's an existing tailor result, attach the cover letter to it
    if result_id:
        result = TailorResult.query.filter_by(id=result_id, user_id=current_user.id).first()
        if result:
            result.cover_letter = cover_letter
            db.session.commit()

    # Decrement free uses if not subscribed
    if not current_user.is_subscribed:
        current_user.free_uses_remaining -= 1
    current_user.total_tailors += 1
    db.session.commit()

    return jsonify({
        "cover_letter": cover_letter,
        "remaining_free": current_user.free_uses_remaining if not current_user.is_subscribed else None,
    })


@tailor_bp.route("/download-docx/<int:result_id>", methods=["GET"])
@login_required
def download_docx(result_id):
    """Generate and download a DOCX of the tailored resume."""
    result = TailorResult.query.filter_by(
        id=result_id, user_id=current_user.id).first()
    if not result:
        return jsonify({"error": "Not found"}), 404

    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        return jsonify({"error": "DOCX generation not available"}), 500

    doc = Document()

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    # Set narrow margins
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    lines = result.tailored_resume.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph("")
        elif stripped.isupper() and len(stripped) < 60:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(stripped)
            run.bold = True
            run.font.size = Pt(12)
            # Add bottom border effect via spacing
            p.paragraph_format.space_after = Pt(4)
        elif stripped.startswith("- ") or stripped.startswith("• "):
            p = doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"resume_{result.job_title or 'tailored'}_{result.company or 'resume'}.docx"
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


@tailor_bp.route("/download-cover-letter/<int:result_id>", methods=["GET"])
@login_required
def download_cover_letter_pdf(result_id):
    """Generate and download a PDF of the cover letter."""
    result = TailorResult.query.filter_by(
        id=result_id, user_id=current_user.id).first()
    if not result or not result.cover_letter:
        return jsonify({"error": "No cover letter found"}), 404

    try:
        from weasyprint import HTML
    except ImportError:
        return jsonify({"error": "PDF generation not available"}), 500

    paragraphs = result.cover_letter.split("\n")
    html_parts = []
    for line in paragraphs:
        line = line.strip()
        if not line:
            html_parts.append("<br>")
        else:
            html_parts.append(f"<p>{escape(line)}</p>")

    body_html = "\n".join(html_parts)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<style>
    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.7;
        color: #222;
        max-width: 650px;
        margin: 50px auto;
        padding: 0 30px;
    }}
    p {{ margin: 8px 0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

    pdf = HTML(string=full_html).write_pdf()

    filename = f"cover_letter_{result.job_title or 'application'}_{result.company or ''}.pdf"
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@tailor_bp.route("/import-jd", methods=["POST"])
@login_required
def import_job_description():
    """Import a job description from a URL by extracting text content."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400

    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ResumeTailor/1.0)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return jsonify({"error": "Could not fetch URL. Try pasting the job description directly."}), 400

    # Strip HTML tags to get text
    import re as _re
    # Remove script and style tags and their content
    text = _re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
    # Remove HTML tags
    text = _re.sub(r'<[^>]+>', '\n', text)
    # Decode HTML entities
    from html import unescape
    text = unescape(text)
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    text = '\n'.join(lines)

    # Truncate to reasonable length
    if len(text) > 10000:
        text = text[:10000]

    # Try to extract title from HTML
    title_match = _re.search(r'<title[^>]*>(.*?)</title>', html, _re.IGNORECASE | _re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    title = unescape(title)

    return jsonify({
        "text": text,
        "title": title[:200] if title else "",
        "company": "",
    })


@tailor_bp.route("/download-pdf/<int:result_id>", methods=["GET"])
@login_required
def download_pdf(result_id):
    """Generate and download a PDF of the tailored resume."""
    result = TailorResult.query.filter_by(
        id=result_id, user_id=current_user.id).first()
    if not result:
        return jsonify({"error": "Not found"}), 404

    try:
        from weasyprint import HTML
    except ImportError:
        return jsonify({"error": "PDF generation not available"}), 500

    # Convert resume text to styled HTML
    resume_lines = result.tailored_resume.split("\n")
    html_parts = []
    for line in resume_lines:
        line = line.strip()
        if not line:
            html_parts.append("<br>")
        elif line.isupper() and len(line) < 60:
            html_parts.append(f"<h2>{line}</h2>")
        elif line.startswith("- ") or line.startswith("• "):
            html_parts.append(f"<li>{line[2:]}</li>")
        else:
            html_parts.append(f"<p>{line}</p>")

    resume_html = "\n".join(html_parts)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<style>
    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #222;
        max-width: 700px;
        margin: 40px auto;
        padding: 0 20px;
    }}
    h2 {{
        font-size: 12pt;
        border-bottom: 1px solid #333;
        padding-bottom: 3px;
        margin-top: 16px;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    p {{ margin: 3px 0; }}
    li {{
        margin: 2px 0 2px 20px;
        list-style-type: disc;
    }}
    br {{ margin: 6px 0; }}
</style>
</head>
<body>
{resume_html}
</body>
</html>"""

    pdf = HTML(string=full_html).write_pdf()

    filename = f"resume_{result.job_title or 'tailored'}_{result.company or 'resume'}.pdf"
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
