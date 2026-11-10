"""Tests for the keyword scorer."""
from app.services.keywords import extract_keywords, grade_score, score_resume


def test_extract_keywords_lowercases_and_removes_stop_words():
    result = extract_keywords("Python and the Developer with Python")
    assert result["python"] == 2
    assert "and" not in result
    assert "the" not in result
    assert "with" not in result


def test_extract_keywords_keeps_tech_tokens():
    result = extract_keywords("C++ and C# experience")
    assert result["c++"] == 1
    assert result["c#"] == 1


def test_score_perfect_match():
    result = score_resume("python flask sql", "python flask sql")
    assert result["score"] == 100
    assert result["grade"] == "Excellent"
    assert result["matched_count"] == result["total_jd_keywords"]


def test_score_no_match():
    result = score_resume("baking bread", "python flask sql")
    assert result["score"] == 0
    assert result["grade"] == "Needs Work"
    assert result["matched_count"] == 0


def test_score_partial_match_and_missing_list():
    result = score_resume("python", "python flask sql django")
    assert 0 < result["score"] < 100
    assert any(item["keyword"] == "python" for item in result["matched_keywords"])
    missing = {item["keyword"] for item in result["missing_keywords"]}
    assert {"flask", "sql", "django"} <= missing


def test_grade_boundaries():
    assert grade_score(80) == "Excellent"
    assert grade_score(79) == "Good"
    assert grade_score(60) == "Good"
    assert grade_score(59) == "Fair"
    assert grade_score(40) == "Fair"
    assert grade_score(39) == "Needs Work"
