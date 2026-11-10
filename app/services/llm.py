"""Anthropic calls for resume tailoring and cover letters.

This module owns the model name, the prompts, and the client. Routes
do not build prompts or call Anthropic directly, so a test can replace
the client with a fake without touching a route.
"""
import anthropic

TAILOR_MODEL = "claude-sonnet-4-20250514"
TAILOR_MAX_TOKENS = 4000
COVER_LETTER_MAX_TOKENS = 2000

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


def create_anthropic_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def build_tailor_prompt(resume: str, job_description: str, job_title: str, company: str) -> str:
    return f"""Here is my current resume:

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


def build_cover_letter_prompt(resume: str, job_description: str, job_title: str, company: str) -> str:
    return f"""Here is my resume:

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


def tailor_resume_text(client, resume: str, job_description: str, job_title: str, company: str) -> str:
    message = client.messages.create(
        model=TAILOR_MODEL,
        max_tokens=TAILOR_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_tailor_prompt(resume, job_description, job_title, company)}],
    )
    return message.content[0].text


def generate_cover_letter_text(client, resume: str, job_description: str, job_title: str, company: str) -> str:
    message = client.messages.create(
        model=TAILOR_MODEL,
        max_tokens=COVER_LETTER_MAX_TOKENS,
        system=COVER_LETTER_PROMPT,
        messages=[{"role": "user", "content": build_cover_letter_prompt(resume, job_description, job_title, company)}],
    )
    return message.content[0].text
