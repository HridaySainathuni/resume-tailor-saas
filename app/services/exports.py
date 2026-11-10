"""Document export: DOCX and PDF rendering for tailored resumes and cover letters.

These functions take plain text and return bytes or HTML. They do
not read the database or the request.
"""
import io
import re
from html import escape


def safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def build_docx(tailored_resume: str, job_title: str = "", company: str = "") -> io.BytesIO:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    doc = Document()
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    for line in tailored_resume.split("\n"):
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph("")
        elif stripped.isupper() and len(stripped) < 60:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(stripped)
            run.bold = True
            run.font.size = Pt(12)
            p.paragraph_format.space_after = Pt(4)
        elif stripped.startswith("- ") or stripped.startswith("• "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def resume_text_to_html(tailored_resume: str) -> str:
    parts = []
    for line in tailored_resume.split("\n"):
        line = line.strip()
        if not line:
            parts.append("<br>")
        elif line.isupper() and len(line) < 60:
            parts.append(f"<h2>{escape(line)}</h2>")
        elif line.startswith("- ") or line.startswith("• "):
            parts.append(f"<li>{escape(line[2:])}</li>")
        else:
            parts.append(f"<p>{escape(line)}</p>")
    return "\n".join(parts)


def cover_letter_text_to_html(cover_letter: str) -> str:
    parts = []
    for line in cover_letter.split("\n"):
        line = line.strip()
        if not line:
            parts.append("<br>")
        else:
            parts.append(f"<p>{escape(line)}</p>")
    return "\n".join(parts)


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


def resume_pdf_html(tailored_resume: str) -> str:
    body = resume_text_to_html(tailored_resume)
    return f"""<!DOCTYPE html>
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
{body}
</body>
</html>"""


def cover_letter_pdf_html(cover_letter: str) -> str:
    body = cover_letter_text_to_html(cover_letter)
    return f"""<!DOCTYPE html>
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
{body}
</body>
</html>"""
