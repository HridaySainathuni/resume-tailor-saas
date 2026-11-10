"""Keyword scoring for the ATS match feature.

Pure functions: no Flask, no database, no network. The scorer ranks
the most frequent keywords in the job description and checks which
ones appear in the resume.
"""
import re
from collections import Counter

STOP_WORDS = {
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

TOP_KEYWORDS = 40
MAX_MATCHED_SHOWN = 20
MAX_MISSING_SHOWN = 15


def extract_keywords(text: str) -> Counter:
    """Extract meaningful keywords from text, lowercased, stop words removed."""
    words = re.findall(r"[a-z][a-z+#.-]{1,30}", text.lower())
    return Counter(w for w in words if w not in STOP_WORDS)


def grade_score(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Needs Work"


def score_resume(resume_text: str, job_description_text: str) -> dict:
    """Score how well a resume matches a job description's keywords."""
    jd_keywords = extract_keywords(job_description_text)
    resume_keywords = extract_keywords(resume_text)
    top_jd = jd_keywords.most_common(TOP_KEYWORDS)

    matched = []
    missing = []
    for keyword, count in top_jd:
        if keyword in resume_keywords:
            matched.append(
                {"keyword": keyword, "jd_count": count, "resume_count": resume_keywords[keyword]}
            )
        else:
            missing.append({"keyword": keyword, "jd_count": count})

    total = len(top_jd)
    match_count = len(matched)
    score = int((match_count / total * 100)) if total > 0 else 0

    return {
        "score": score,
        "grade": grade_score(score),
        "matched_keywords": matched[:MAX_MATCHED_SHOWN],
        "missing_keywords": missing[:MAX_MISSING_SHOWN],
        "total_jd_keywords": total,
        "matched_count": match_count,
    }
