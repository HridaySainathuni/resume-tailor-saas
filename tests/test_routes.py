"""Route smoke tests. No live Anthropic or Stripe calls are made."""
from unittest.mock import patch

from app import db
from app.models import TailorResult
from tests.test_services import FakeClient


def test_landing_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200


def test_dashboard_redirects_when_logged_out(client):
    response = client.get("/dashboard")
    assert response.status_code == 302


def test_signup_creates_user_and_logs_in(client, app):
    response = client.post(
        "/auth/signup",
        data={"email": "new@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        from app.models import User

        assert User.query.filter_by(email="new@example.com").first() is not None


def test_login_with_wrong_password_stays_on_login_page(client):
    response = client.post("/auth/login", data={"email": "x@example.com", "password": "wrong"})
    assert response.status_code == 200


def test_ats_score_requires_login(client):
    response = client.post("/api/ats-score", json={"resume": "python", "job_description": "python"})
    assert response.status_code in (302, 401)


def test_ats_score_returns_score_for_logged_in_user(auth_client):
    response = auth_client.post(
        "/api/ats-score", json={"resume": "python flask", "job_description": "python flask sql"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["score"] > 0
    assert data["grade"] in ("Excellent", "Good", "Fair", "Needs Work")


def test_ats_score_rejects_empty_input(auth_client):
    response = auth_client.post("/api/ats-score", json={"resume": "", "job_description": ""})
    assert response.status_code == 400


def test_history_is_empty_then_lists_a_result(auth_client, app, user):
    response = auth_client.get("/api/history")
    assert response.status_code == 200
    assert response.get_json() == []
    with app.app_context():
        db.session.add(
            TailorResult(
                user_id=user.id,
                original_resume="r",
                job_description="j",
                tailored_resume="t",
                job_title="Engineer",
            )
        )
        db.session.commit()
    response = auth_client.get("/api/history")
    assert len(response.get_json()) == 1


def test_tailor_without_api_key_returns_service_not_configured(auth_client):
    response = auth_client.post(
        "/api/tailor", json={"resume": "my resume", "job_description": "the job"}
    )
    assert response.status_code == 500
    assert response.get_json()["error"] == "Service not configured"


def test_tailor_with_mocked_llm_saves_result(auth_client, app):
    with patch("app.api.tailor.create_anthropic_client", return_value=FakeClient("TAILORED TEXT")):
        auth_client.application.config["ANTHROPIC_API_KEY"] = "test-key"
        response = auth_client.post(
            "/api/tailor",
            json={"resume": "my resume", "job_description": "the job", "job_title": "Engineer"},
        )
    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()
    assert data["tailored_resume"] == "TAILORED TEXT"
    assert data["result_id"] is not None
    with app.app_context():
        assert TailorResult.query.count() == 1


def test_cover_letter_with_mocked_llm(auth_client):
    with patch("app.api.tailor.create_anthropic_client", return_value=FakeClient("COVER LETTER")):
        auth_client.application.config["ANTHROPIC_API_KEY"] = "test-key"
        response = auth_client.post(
            "/api/cover-letter", json={"resume": "my resume", "job_description": "the job"}
        )
    assert response.status_code == 200
    assert response.get_json()["cover_letter"] == "COVER LETTER"


def test_import_jd_rejects_bad_url(auth_client):
    response = auth_client.post("/api/import-jd", json={"url": "not-a-url"})
    assert response.status_code == 400


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_404_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
