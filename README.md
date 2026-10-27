# Resume Tailor

A web app that rewrites your resume for a specific job posting using Claude.

You paste in your resume and a job description. The app reorders and rewords your existing experience to match what the role is asking for, without adding anything that isn't already on your resume. It can also write a matching cover letter and show which keywords from the posting your resume is missing.

## Features

- **Resume tailoring:** rewrites your resume for one job description, prioritizing the most relevant experience and using the posting's language where it fits.
- **Cover letter generation:** writes a cover letter from your resume and the job description, ready to send with no placeholders.
- **Keyword match score:** compares the most frequent keywords in the job description against your resume and lists what matches and what is missing.
- **Import from URL:** pulls the text of a job posting from a link so you don't have to copy and paste it.
- **Export:** downloads the tailored resume as PDF or Word, and the cover letter as PDF.
- **History:** saves past tailoring results so you can come back to them.
- **Accounts and billing:** sign up, log in, reset your password, export or delete your data. Three free uses, then a Stripe subscription.

## Tech stack

- **Backend:** Python, Flask, Flask-Login, Flask-SQLAlchemy, Flask-Limiter
- **AI:** Anthropic API (Claude)
- **Database:** PostgreSQL in production, SQLite locally
- **Payments:** Stripe Checkout, customer portal, and webhooks
- **Documents:** WeasyPrint for PDF, python-docx for Word
- **Deployment:** Docker and Gunicorn on Render

## Project structure

```
app/
  api/
    tailor.py     # tailoring, cover letters, keyword scoring, exports, URL import
    auth.py       # signup, login, password reset
    account.py    # password change, data export, account deletion
    billing.py    # Stripe checkout, portal, and webhooks
    pages.py      # landing, dashboard, and legal pages
  models.py       # User and TailorResult models
  templates/      # Jinja HTML pages
  static/         # CSS and JavaScript
run.py            # entry point
Dockerfile
render.yaml       # Render deployment config
```

## Running locally

1. Clone the repo and install dependencies:

   ```bash
   git clone https://github.com/HridaySainathuni/resume-tailor-saas.git
   cd resume-tailor-saas
   pip install -r requirements.txt
   ```

2. Copy the example environment file and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   | --- | --- |
   | `SECRET_KEY` | Random string used by Flask for sessions |
   | `DATABASE_URL` | Defaults to a local SQLite file |
   | `ANTHROPIC_API_KEY` | Your Anthropic API key |
   | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` | Stripe keys (test keys work) |
   | `STRIPE_PRICE_ID` | The Stripe price for the subscription |
   | `STRIPE_WEBHOOK_SECRET` | Secret for verifying Stripe webhooks |

3. Start the app:

   ```bash
   python run.py
   ```

   The app runs at http://localhost:5000.

WeasyPrint needs a few system libraries (Pango and Cairo) for PDF export. The Dockerfile installs them, so running with Docker is the easiest option if PDF export fails locally.

## Deployment

The repo includes a `render.yaml` that sets up a Docker web service and a Postgres database on Render. Connect the repo in Render, add the environment variables above, and deploy.

## Next steps

- Turn tailoring into an agent that researches the company before writing.
- Add a check that compares the output against the original resume to catch anything the model added that wasn't there.
- Use past applications as context so later results improve.
