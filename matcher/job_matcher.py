"""
job_matcher.py - Gemini job matching with reliable local skill-gap fallback
"""

import google.generativeai as genai
import json
import os
import sys
import time
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "config.json"
)

PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "resume_profile.json"
)

GEMINI_MODEL = "gemini-3.6-flash"

QA_TITLE_KEYWORDS = [
    "qa automation",
    "test automation",
    "sdet",
    "quality assurance",
    "selenium",
    "playwright",
    "cypress",
    "appium",
    "software tester",
    "automation engineer",
    "quality engineer",
    "test engineer",
    "qa engineer",
    "qa analyst",
    "automation tester",
    "software testing",
    "qa lead"
]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def load_profile():
    with open(PROFILE_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def clean_json_response(raw: str) -> str:
    raw = raw.strip()

    if "```" in raw:
        lines = raw.split("\n")
        cleaned = [
            line
            for line in lines
            if not line.strip().startswith("```")
        ]
        raw = "\n".join(cleaned)

    return raw.strip()


def get_profile_skills(profile: dict) -> list:
    """
    Return all profile skills as one normalized list.

    Supports the current resume_profile.json schema as well as
    the older test_frameworks field.
    """

    skills = []

    tech_skills = profile.get("tech_skills", {})

    if not isinstance(tech_skills, dict):
        return skills

    skill_groups = [
        "test_automation",
        "test_frameworks",
        "programming_languages",
        "api_testing",
        "performance_testing",
        "ci_cd",
        "testing",
        "qa_practices",
        "tools",
        "methodologies",
    ]

    for group in skill_groups:
        values = tech_skills.get(group, [])

        if isinstance(values, list):
            skills.extend(
                str(value).strip()
                for value in values
                if value
            )

    # Remove duplicates while preserving order
    return list(dict.fromkeys(skills))


def title_based_score(job: dict, profile: dict) -> dict:
    title = job.get("title", "").lower()

    score = 0
    reasons = []
    missing = []

    if any(kw in title for kw in QA_TITLE_KEYWORDS):
        score += 50
        reasons.append("Job title matches QA/Testing domain")

    exp = profile.get("experience_years", 0)

    if exp >= 4 and any(
        w in title
        for w in ["senior", "lead", "principal"]
    ):
        score += 20
        reasons.append("Seniority level matches your experience")

    elif not any(
        w in title
        for w in ["senior", "lead", "junior", "principal"]
    ):
        score += 15
        reasons.append("Mid-level position matches your profile")

    profile_skills = get_profile_skills(profile)

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
            or any(
                keyword.lower() in skill
                for skill in skill_names
            )
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
        "match_reasons": reasons or [
            "QA role matching your profile"
        ],
        "missing_skills": missing[:3],
        "nice_to_have_present": [],
        "recommendation": "APPLY" if score >= 50 else "MAYBE",
        "recommendation_reason": "Title-based match",
        "seniority_match": True,
        "remote_type": "not_specified",
        "scored_by": "title_fallback"
    }


def match_job_to_profile(job: dict, profile: dict, model) -> dict:
    tech_skills = profile.get("tech_skills", {})

    profile_summary = {
        "experience_years": profile.get("experience_years", 0),
        "current_level": profile.get("current_level", "mid"),
        "job_titles": profile.get("job_titles", []),

        "test_automation": tech_skills.get(
            "test_automation",
            tech_skills.get("test_frameworks", [])
        ),

        "programming_languages": tech_skills.get(
            "programming_languages",
            []
        ),

        "api_testing": tech_skills.get(
            "api_testing",
            []
        ),

        "performance_testing": tech_skills.get(
            "performance_testing",
            []
        ),

        "ci_cd": tech_skills.get(
            "ci_cd",
            []
        ),

        "testing": tech_skills.get(
            "testing",
            []
        ),

        "qa_practices": tech_skills.get(
            "qa_practices",
            []
        ),

        "tools": tech_skills.get(
            "tools",
            []
        ),

        "methodologies": tech_skills.get(
            "methodologies",
            []
        ),
    }

    description = job.get("description", "").strip()

    if len(description) < 100:
        print(
            "      ℹ️ Short description — title fallback"
        )
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

            m = re.search(
                r'\{.*\}',
                raw,
                re.DOTALL
            )

            match_data = (
                json.loads(m.group())
                if m
                else {}
            )

        job.update({
            "match_score": int(
                match_data.get("match_score", 0)
            ),

            "match_reasons": match_data.get(
                "match_reasons",
                []
            ),

            "missing_skills": match_data.get(
                "missing_skills",
                []
            ),

            "nice_to_have_present": match_data.get(
                "nice_to_have_present",
                []
            ),

            "recommendation": match_data.get(
                "recommendation",
                "MAYBE"
            ),

            "recommendation_reason": match_data.get(
                "recommendation_reason",
                ""
            ),

            "seniority_match": match_data.get(
                "seniority_match",
                False
            ),

            "remote_type": match_data.get(
                "remote_type",
                "not_specified"
            ),

            "scored_by": "gemini",
        })

        print(
            f"      ✅ Score: "
            f"{job['match_score']}% "
            f"({job['recommendation']})"
        )

    except Exception as e:
        print(
            f"      ⚠️ Gemini error: "
            f"{str(e)[:80]} — title fallback"
        )

        job.update(
            title_based_score(job, profile)
        )

    return job


def batch_match_jobs(
    jobs: list,
    min_score: int = 0
) -> list:

    config = load_config()
    profile = load_profile()

    api_key = config["api_keys"]["gemini_api_key"]

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        GEMINI_MODEL
    )

    matched = []

    print(
        f"🤖 Matching {len(jobs)} jobs "
        f"with Gemini AI ({GEMINI_MODEL})..."
    )

    for i, job in enumerate(jobs, 1):

        print(
            f"   [{i}/{len(jobs)}] "
            f"{job.get('title', '?')[:40]} "
            f"@ {job.get('company', '?')[:20]}..."
        )

        matched_job = match_job_to_profile(
            job,
            profile,
            model
        )

        if matched_job.get(
            "match_score",
            0
        ) >= min_score:
            matched.append(matched_job)

        if i % 10 == 0:
            print(
                "   ⏳ Rate limit pause 3s..."
            )
            time.sleep(3)

    matched.sort(
        key=lambda x: x.get(
            "match_score",
            0
        ),
        reverse=True
    )

    print(
        f"\n✅ Matched: {len(matched)} jobs "
        f"(score >= {min_score}%)"
    )

    return matched


def build_skill_gap_fallback(
    all_jobs: list,
    profile: dict
) -> dict:
    """
    Local deterministic skill-gap analysis.

    Used when Gemini is unavailable, quota is exceeded,
    or Gemini returns invalid JSON.
    """

    profile_skills = {
        skill.lower().strip()
        for skill in get_profile_skills(profile)
    }

    def has_skill(*keywords):
        for keyword in keywords:

            keyword = keyword.lower().strip()

            if any(
                keyword == skill
                or keyword in skill
                for skill in profile_skills
            ):
                return True

        return False

    # Collect missing skills from matched jobs
    all_missing = []

    for job in all_jobs:

        missing = job.get(
            "missing_skills",
            []
        )

        if isinstance(missing, list):

            all_missing.extend(
                str(skill).strip()
                for skill in missing
                if skill
            )

    missing_counts = Counter(
        all_missing
    ).most_common(15)

    skill_catalog = {

        "Cypress": {
            "aliases": ["cypress"],
            "reason": (
                "Frequently requested modern "
                "JavaScript E2E automation framework."
            ),
            "learning_time": "2-4 weeks",
            "resource": "https://www.cypress.io/"
        },

        "Playwright": {
            "aliases": ["playwright"],
            "reason": (
                "High-value modern cross-browser "
                "automation framework."
            ),
            "learning_time": "1-2 weeks",
            "resource": "https://playwright.dev/"
        },

        "K6": {
            "aliases": [
                "k6",
                "grafana k6"
            ],
            "reason": (
                "Useful for modern performance "
                "and load testing."
            ),
            "learning_time": "1 week",
            "resource": "https://k6.io/docs/"
        },

        "Docker": {
            "aliases": ["docker"],
            "reason": (
                "Useful for containerized "
                "CI/CD test execution."
            ),
            "learning_time": "2-3 days",
            "resource": "https://docs.docker.com/"
        },

        "API Contract Testing": {
            "aliases": [
                "api contract testing",
                "contract testing"
            ],
            "reason": (
                "Useful for API-first and "
                "microservice testing."
            ),
            "learning_time": "1 week",
            "resource": "https://docs.pact.io/"
        },
    }

    skill_recommendations = []

    for skill_name, info in skill_catalog.items():

        # Never recommend a skill already present
        # in the user's profile.
        if has_skill(*info["aliases"]):
            continue

        observed_count = 0

        for missing_skill, count in missing_counts:

            missing_lower = (
                missing_skill.lower()
            )

            if (
                skill_name.lower()
                in missing_lower
                or missing_lower
                in skill_name.lower()
                or any(
                    alias in missing_lower
                    or missing_lower in alias
                    for alias in info["aliases"]
                )
            ):
                observed_count = count
                break

        if observed_count > 0:

            reason = (
                f"{info['reason']} "
                f"Observed in {observed_count} "
                f"matched job(s)."
            )

        else:

            reason = info["reason"]

        skill_recommendations.append({
            "skill": skill_name,
            "reason": reason,
            "learning_time": info["learning_time"],
            "resources": [
                info["resource"]
            ]
        })

    skill_recommendations = (
        skill_recommendations[:5]
    )

    if not skill_recommendations:

        skill_recommendations = [
            {
                "skill": "AI Testing",
                "reason": (
                    "Useful next-step specialization "
                    "for senior QA engineers."
                ),
                "learning_time": "2-4 weeks",
                "resources": [
                    "https://platform.openai.com/docs"
                ]
            }
        ]

    return {
        "critical_skills_to_learn":
            skill_recommendations,

        "trending_in_qa": [
            "AI-powered testing",
            "Shift-left testing",
            "API contract testing",
            "AI-assisted test generation"
        ],

        "certifications_recommended": [
            {
                "cert": (
                    "ISTQB Advanced "
                    "Test Automation Engineer"
                ),
                "reason": (
                    "Relevant for senior automation "
                    "and test architecture roles."
                ),
                "url": "https://www.istqb.org/"
            }
        ],

        "quick_wins": [
            "Strengthen Playwright with TypeScript",
            "Build GitHub Actions CI/CD test pipelines",
            "Add Docker basics to test execution",
            "Create one k6 performance-testing project"
        ],

        "career_advice": (
            f"With "
            f"{profile.get('experience_years', 13)} "
            "years of QA experience and existing "
            "Playwright, Selenium, TypeScript, "
            "API testing, K6 and CI/CD skills, "
            "focus on senior-level automation "
            "architecture, AI-assisted testing, "
            "performance engineering and modern "
            "test frameworks."
        )
    }


def generate_skill_gap_analysis(
    all_jobs: list,
    profile: dict,
    api_key: str
) -> dict:
    """
    Generate AI-powered skill-gap analysis.

    If Gemini is unavailable, rate-limited, or returns
    invalid JSON, use the local deterministic fallback.
    """

    # No API key -> local fallback
    if (
        not api_key
        or api_key == "YOUR_GEMINI_API_KEY_HERE"
    ):

        print(
            "   ℹ️ Gemini API key unavailable — "
            "using local skill-gap analysis"
        )

        return build_skill_gap_fallback(
            all_jobs,
            profile
        )

    # Collect missing skills observed in jobs
    all_missing = []

    for job in all_jobs[:20]:

        missing = job.get(
            "missing_skills",
            []
        )

        if isinstance(missing, list):

            all_missing.extend(
                str(skill).strip()
                for skill in missing
                if skill
            )

    missing_counts = Counter(
        all_missing
    ).most_common(15)

    candidate_skills = get_profile_skills(
        profile
    )

    prompt = f"""
You are a senior QA career coach.

Candidate:
- Experience: {profile.get('experience_years', 13)} years
- Current level: {profile.get('current_level', 'Senior QA Engineer')}
- Skills: {json.dumps(candidate_skills)}

Observed missing skills from matched jobs:
{json.dumps(missing_counts)}

IMPORTANT:
- Do NOT recommend a skill that the candidate already has.
- The candidate already has any skills appearing in the provided skill list.
- Prioritize skills repeatedly requested by matched jobs.
- Keep recommendations realistic for a senior QA engineer.

Return ONLY valid JSON. No markdown.

{{
  "critical_skills_to_learn": [
    {{
      "skill": "Cypress",
      "reason": "Why this skill matters",
      "learning_time": "2-4 weeks",
      "resources": ["https://www.cypress.io/"]
    }}
  ],
  "trending_in_qa": [
    "AI-powered testing",
    "Shift-left testing"
  ],
  "certifications_recommended": [
    {{
      "cert": "ISTQB Advanced Test Automation Engineer",
      "reason": "Why it is useful",
      "url": "https://www.istqb.org/"
    }}
  ],
  "quick_wins": [
    "Specific actionable improvement"
  ],
  "career_advice": "Personalized advice for this candidate."
}}
"""

    try:

        genai.configure(
            api_key=api_key
        )

        model = genai.GenerativeModel(
            GEMINI_MODEL
        )

        response = model.generate_content(
            prompt
        )

        if (
            not response
            or not getattr(
                response,
                "text",
                None
            )
        ):
            raise ValueError(
                "Gemini returned an empty response"
            )

        raw = clean_json_response(
            response.text
        )

        result = json.loads(raw)

        if not isinstance(result, dict):
            raise ValueError(
                "Gemini returned a non-object JSON response"
            )

        if "critical_skills_to_learn" not in result:
            raise ValueError(
                "Missing critical_skills_to_learn"
            )

        print(
            "   ✅ Skill gap analysis "
            "generated by Gemini"
        )

        return result

    except Exception as e:

        error_text = str(e)

        if (
            "429" in error_text
            or "quota" in error_text.lower()
        ):

            print(
                "   ⚠️ Gemini quota exceeded — "
                "using local skill-gap fallback"
            )

        else:

            print(
                f"   ⚠️ Gemini skill-gap error: "
                f"{error_text[:150]} — "
                "using local fallback"
            )

        return build_skill_gap_fallback(
            all_jobs,
            profile
        )