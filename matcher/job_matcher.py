"""
job_matcher.py - Fixed: uses gemini-2.0-flash (current free model)
"""

import google.generativeai as genai
import json
import os
import sys
import time
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "resume_profile.json")

GEMINI_MODEL = "gemini-2.0-flash"  # Current free tier model

QA_TITLE_KEYWORDS = [
    "qa automation", "test automation", "sdet", "quality assurance",
    "selenium", "playwright", "cypress", "appium", "software tester",
    "automation engineer", "quality engineer", "test engineer", "qa engineer",
    "qa analyst", "automation tester", "software testing", "qa lead"
]


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_profile():
    with open(PROFILE_PATH) as f:
        return json.load(f)


def clean_json_response(raw: str) -> str:
    raw = raw.strip()
    if "```" in raw:
        lines = raw.split("\n")
        cleaned = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(cleaned)
    return raw.strip()


def title_based_score(job: dict, profile: dict) -> dict:
    title = job.get("title", "").lower()
    score = 0
    reasons = []
    missing = []

    if any(kw in title for kw in QA_TITLE_KEYWORDS):
        score += 50
        reasons.append("Job title matches QA/Testing domain")

    exp = profile.get("experience_years", 0)
    if exp >= 4 and any(w in title for w in ["senior", "lead", "principal"]):
        score += 20
        reasons.append("Seniority level matches your experience")
    elif not any(w in title for w in ["senior", "lead", "junior", "principal"]):
        score += 15
        reasons.append("Mid-level position matches your profile")

    profile_skills = []
    tech_skills = profile.get("tech_skills", {})

    for skill_group in tech_skills.values():
        if isinstance(skill_group, list):
            profile_skills.extend(skill_group)

    for skill in profile_skills:
        if str(skill).lower() in title:
            score += 10
            reasons.append(f"{skill} mentioned in title")
            break

    skill_names = [
        str(skill).strip().lower()
        for skill in profile_skills
    ]

    def has_skill(skill_keywords):
        """Return whether any skill keyword or alias is in the profile."""
        return any(
            keyword.lower() in skill_names
            or any(keyword.lower() in skill for skill in skill_names)
            for keyword in skill_keywords
        )

    if not has_skill(["cypress"]):
        missing.append("Cypress")

    if not has_skill([
        "playwright",
        "playwright test",
        "microsoft playwright",
    ]):
        missing.append("Playwright")

    if not has_skill([
        "k6",
        "grafana k6",
        "k6 performance testing",
    ]):
        missing.append("K6 performance testing")

    return {
        "match_score": min(score, 85),
        "match_reasons": reasons or ["QA role matching your profile"],
        "missing_skills": missing[:3],
        "nice_to_have_present": [],
        "recommendation": "APPLY" if score >= 50 else "MAYBE",
        "recommendation_reason": "Title-based match",
        "seniority_match": True,
        "remote_type": "not_specified",
        "scored_by": "title_fallback"
    }


def match_job_to_profile(job: dict, profile: dict, model) -> dict:
    profile_summary = {
        "experience_years": profile.get("experience_years", 0),
        "current_level": profile.get("current_level", "mid"),
        "job_titles": profile.get("job_titles", []),
        "test_frameworks": profile["tech_skills"].get("test_frameworks", []),
        "programming_languages": profile["tech_skills"].get("programming_languages", []),
        "api_testing": profile["tech_skills"].get("api_testing", []),
        "ci_cd": profile["tech_skills"].get("ci_cd", []),
        "methodologies": profile.get("methodologies", []),
    }

    description = job.get("description", "").strip()
    if len(description) < 100:
        print(f"      ℹ️  Short description — title fallback")
        job.update(title_based_score(job, profile))
        return job

    prompt = f"""You are a QA job recruiter. Score this candidate vs job.

CANDIDATE:
{json.dumps(profile_summary, indent=2)}

JOB:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Description: {description[:2000]}

Rules: QA role + QA candidate = minimum score 50.

Return ONLY JSON, no markdown:
{{
  "match_score": 75,
  "match_reasons": ["Has Selenium", "Java matches"],
  "missing_skills": ["Cypress", "K6"],
  "nice_to_have_present": ["JIRA"],
  "recommendation": "APPLY",
  "recommendation_reason": "Strong core match",
  "seniority_match": true,
  "remote_type": "fully_remote"
}}"""

    try:
        response = model.generate_content(prompt)
        raw = clean_json_response(response.text)
        try:
            match_data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            match_data = json.loads(m.group()) if m else {}

        job.update({
            "match_score": int(match_data.get("match_score", 0)),
            "match_reasons": match_data.get("match_reasons", []),
            "missing_skills": match_data.get("missing_skills", []),
            "nice_to_have_present": match_data.get("nice_to_have_present", []),
            "recommendation": match_data.get("recommendation", "MAYBE"),
            "recommendation_reason": match_data.get("recommendation_reason", ""),
            "seniority_match": match_data.get("seniority_match", False),
            "remote_type": match_data.get("remote_type", "not_specified"),
            "scored_by": "gemini",
        })
        print(f"      ✅ Score: {job['match_score']}% ({job['recommendation']})")

    except Exception as e:
        print(f"      ⚠️  Gemini error: {str(e)[:80]} — title fallback")
        job.update(title_based_score(job, profile))

    return job


def batch_match_jobs(jobs: list, min_score: int = 0) -> list:
    config = load_config()
    profile = load_profile()
    api_key = config["api_keys"]["gemini_api_key"]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    matched = []
    print(f"🤖 Matching {len(jobs)} jobs with Gemini AI ({GEMINI_MODEL})...")

    for i, job in enumerate(jobs, 1):
        print(f"   [{i}/{len(jobs)}] {job.get('title','?')[:40]} @ {job.get('company','?')[:20]}...")
        matched_job = match_job_to_profile(job, profile, model)
        if matched_job.get("match_score", 0) >= min_score:
            matched.append(matched_job)
        if i % 10 == 0:
            print(f"   ⏳ Rate limit pause 3s...")
            time.sleep(3)

    matched.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    print(f"\n✅ Matched: {len(matched)} jobs (score >= {min_score}%)")
    return matched


def generate_skill_gap_analysis(all_jobs: list, profile: dict, api_key: str) -> dict:
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return {
            "critical_skills_to_learn": [
                {"skill": "Cypress", "reason": "High demand in QA automation", "learning_time": "2-4 weeks", "resources": ["https://www.cypress.io/"]},
                {"skill": "Playwright", "reason": "Modern fast web automation framework", "learning_time": "1-2 weeks", "resources": ["https://playwright.dev/"]}
            ],
            "trending_in_qa": ["AI Testing", "Playwright", "CI/CD Pipelines"],
            "certifications_recommended": [
                {"cert": "ISTQB Advanced Test Automation Engineer", "reason": "Boosts career prospects for senior roles", "url": "https://www.istqb.org/"}
            ],
            "quick_wins": ["Learn K6 performance testing", "Add Docker to test pipelines"],
            "career_advice": "Focus on modern web automation frameworks (Playwright/Cypress) to maximize remote opportunities."
        }

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    all_missing = []
    for job in all_jobs[:20]:
        all_missing.extend(job.get("missing_skills", []))
    missing_counts = Counter(all_missing).most_common(15)
    if not missing_counts:
        missing_counts = [("Cypress", 5), ("Playwright", 4), ("K6", 3), ("Docker", 3)]

    prompt = f"""QA career coach. {profile.get('experience_years', 3)} years exp candidate.
Skills: {', '.join(profile['tech_skills'].get('test_frameworks', []) + profile['tech_skills'].get('programming_languages', []))}
Frequently missing: {json.dumps(missing_counts)}

Return ONLY JSON, no markdown:
{{
  "critical_skills_to_learn": [
    {{"skill": "Cypress", "reason": "High demand", "learning_time": "2-4 weeks", "resources": ["cypress.io/docs"]}}
  ],
  "trending_in_qa": ["AI testing", "Shift-left"],
  "certifications_recommended": [
    {{"cert": "ISTQB Advanced", "reason": "Senior roles", "url": "istqb.org"}}
  ],
  "quick_wins": ["Learn K6 - 1 week", "Add Docker - 3 days"],
  "career_advice": "Personalized advice."
}}"""

    try:
        raw = clean_json_response(model.generate_content(prompt).text)
        return json.loads(raw)
    except Exception as e:
        print(f"⚠️ Skill gap error: {e}")
        return {
            "critical_skills_to_learn": [
                {"skill": "Cypress", "reason": "Modern JS framework, high demand", "learning_time": "2-4 weeks", "resources": ["cypress.io/docs"]},
                {"skill": "Playwright", "reason": "Microsoft automation tool", "learning_time": "2-3 weeks", "resources": ["playwright.dev"]},
                {"skill": "K6", "reason": "Performance testing tool", "learning_time": "1 week", "resources": ["k6.io/docs"]},
            ],
            "trending_in_qa": ["AI-powered testing", "Shift-left testing", "API contract testing"],
            "certifications_recommended": [{"cert": "ISTQB Advanced", "reason": "Valued for senior roles", "url": "istqb.org"}],
            "quick_wins": ["Add Docker basics to profile", "Learn GitHub Actions CI/CD"],
            "career_advice": f"With {profile.get('experience_years',5)} years Selenium/Java experience, focus on Playwright or Cypress to expand globally."
        }
