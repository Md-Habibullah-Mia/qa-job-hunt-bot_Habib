"""
job_matcher.py - Software QA domain classification, AI-driven matching & career growth
"""

import google.generativeai as genai
import json
import os
import sys
import time
import re
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

# --- Domain Classification Signals ---

STRONG_SOFTWARE_QA_TITLES = [
    "qa automation engineer",
    "qa automation lead",
    "qa automation",
    "sdet",
    "software development engineer in test",
    "software test engineer",
    "software qa engineer",
    "qa engineer",
    "automation test engineer",
    "automation tester",
    "test automation engineer",
    "senior qa engineer",
    "senior sdet",
    "qa lead",
    "test lead",
    "software quality engineer",
    "automation lead",
    "software engineer in test",
    "test engineer",
    "qa analyst",
    "sqa engineer",
    "sqa",
    "lead sdet",
    "principal sdet",
    "automation engineer",
    "software tester",
    "automation test lead",
    "software engineer ii - automation tester",
    "software engineer - automation tester",
    "qa specialist",
    "quality assurance automation",
]

# Keywords that, on their own, prove a job is specifically about software
# testing/QA — not just "a tech job" (Salesforce, DevOps, backend dev, etc.
# also mention git/jira/javascript/api all the time).
STRONG_QA_TECH_KEYWORDS = [
    "selenium", "playwright", "cypress", "webdriver", "appium",
    "cucumber", "testng", "junit", "jest", "rest assured", "restassured",
    "postman", "api automation", "ui automation", "e2e testing", "e2e automation",
    "end-to-end testing", "automated testing",
    "k6", "jmeter", "pytest", "robot framework", "specflow", "karate",
    "pom", "page object model", "test automation", "software testing",
    "api testing", "regression testing", "load testing", "performance testing",
    "accessibility testing", "visual regression", "bdd", "tdd", "unit testing",
    "integration testing", "test plan", "test case", "test strategy",
    "web automation", "mobile automation", "api test", "backend testing",
    "frontend testing"
]

# Generic language/tooling mentions. Common across almost every tech role,
# so they only support an existing QA signal — they never qualify a job as
# software_qa by themselves.
GENERIC_SUPPORT_KEYWORDS = [
    "ci/cd testing", "ci/cd", "github actions", "jenkins", "java",
    "typescript", "javascript", "python", "bug tracking", "jira", "git",
    "software quality",
]

# Kept for backwards compatibility with anything importing this name.
SOFTWARE_QA_TECH_KEYWORDS = STRONG_QA_TECH_KEYWORDS + GENERIC_SUPPORT_KEYWORDS

NON_SOFTWARE_QA_KEYWORDS = [
    "apparel", "garment", "garments", "textile", "textiles", "footwear",
    "shoe", "shoes", "clothing", "fabric", "fabrics", "knitwear", "woven",
    "yarn", "spinning", "dyeing", "sewing", "leather", "merchandise quality",
    "sourcing quality", "manufacturing", "factory", "factories", "supplier quality",
    "supplier management", "supplier audit", "factory audit", "production quality",
    "product inspection", "quality inspector", "qc inspector", "inspection company",
    "aql", "capa", "manufacturing process", "production process", "raw material",
    "raw materials", "finished goods", "production line", "factory compliance",
    "supplier onboarding", "third-party inspection", "reimbursement", "sales returns",
    "physical product quality", "plant quality", "gmp", "haccp", "fda compliance",
    "food safety", "warehouse quality", "chemical quality", "automotive assembly",
    "heavy industry", "garment manufacturing", "iso 9001 audit", "sampling standard"
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
    Supports the current resume_profile.json schema as well as older test_frameworks field.
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

    return list(dict.fromkeys(skills))


def classify_job_domain(job: dict) -> dict:
    """
    Deterministically classify whether a job is Software QA vs Non-Software QA (manufacturing, apparel, etc.)
    Returns:
        {
            "job_domain": "software_qa" | "non_software_qa" | "mixed" | "unknown",
            "domain_confidence": int (0-100),
            "domain_reason": str,
            "matched_software_signals": list,
            "matched_non_software_signals": list
        }
    """
    title = (job.get("title") or "").lower().strip()
    description = (job.get("description") or "").lower().strip()
    full_text = f"{title} {description}"

    title_software_signals = [kw for kw in STRONG_SOFTWARE_QA_TITLES if kw in title]
    desc_strong_signals = [kw for kw in STRONG_QA_TECH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', full_text)]
    desc_generic_signals = [kw for kw in GENERIC_SUPPORT_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', full_text)]
    # Only strong, QA-specific signals qualify a job as software_qa on their
    # own. Generic ones (git, jira, javascript, ci/cd...) show up in almost
    # any tech role and must not be enough by themselves — see the Omega CRM
    # "Salesforce Marketing Cloud Platform Manager" false-positive.
    desc_software_signals = desc_strong_signals
    desc_all_signals = desc_strong_signals + desc_generic_signals

    title_non_software_signals = [kw for kw in NON_SOFTWARE_QA_KEYWORDS if kw in title]
    desc_non_software_signals = [kw for kw in NON_SOFTWARE_QA_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', full_text)]

    software_score = len(title_software_signals) * 3 + len(desc_strong_signals) + len(desc_generic_signals) * 0.5
    non_software_score = len(title_non_software_signals) * 4 + len(desc_non_software_signals)

    # 1. Non-software title indicators without software titles
    if title_non_software_signals and not title_software_signals:
        return {
            "job_domain": "non_software_qa",
            "domain_confidence": 98,
            "domain_reason": f"Non-software QA title indicators: {', '.join(title_non_software_signals[:3])}",
            "matched_software_signals": desc_software_signals[:3],
            "matched_non_software_signals": (title_non_software_signals + desc_non_software_signals)[:5]
        }

    # 2. Manufacturing / apparel / supplier quality indicators in description without software tech signals
    if non_software_score >= 2 and len(desc_software_signals) == 0:
        return {
            "job_domain": "non_software_qa",
            "domain_confidence": 95,
            "domain_reason": f"Manufacturing/apparel quality indicators found without software testing context: {', '.join(desc_non_software_signals[:4])}",
            "matched_software_signals": [],
            "matched_non_software_signals": desc_non_software_signals[:5]
        }

    # 3. Heavy non-software signals overriding minor generic text
    if non_software_score >= 3 and non_software_score > software_score * 2:
        return {
            "job_domain": "non_software_qa",
            "domain_confidence": 90,
            "domain_reason": f"Predominantly manufacturing/supplier quality role: {', '.join(desc_non_software_signals[:4])}",
            "matched_software_signals": desc_software_signals[:3],
            "matched_non_software_signals": desc_non_software_signals[:5]
        }

    # 4. Confirmed Software QA role
    if title_software_signals or len(desc_software_signals) >= 2:
        reasons = []
        if title_software_signals:
            reasons.append(f"Title matches Software QA: {title_software_signals[0]}")
        if desc_software_signals:
            reasons.append(f"Software tech stack: {', '.join(desc_software_signals[:4])}")
        return {
            "job_domain": "software_qa",
            "domain_confidence": 95 if (title_software_signals and desc_software_signals) else 85,
            "domain_reason": " · ".join(reasons),
            "matched_software_signals": (title_software_signals + desc_software_signals)[:5],
            "matched_non_software_signals": desc_non_software_signals[:3]
        }

    # 5. Generic QA title with ambiguity
    if any(kw in title for kw in ["quality assurance", "quality engineer", "qa manager", "qa team lead", "qa specialist"]):
        if non_software_score > 0:
            return {
                "job_domain": "non_software_qa",
                "domain_confidence": 85,
                "domain_reason": f"Generic QA title with physical/manufacturing indicators: {', '.join(desc_non_software_signals[:3])}",
                "matched_software_signals": [],
                "matched_non_software_signals": desc_non_software_signals[:3]
            }
        return {
            "job_domain": "unknown",
            "domain_confidence": 50,
            "domain_reason": "Generic QA title without distinct software or manufacturing signals",
            "matched_software_signals": [],
            "matched_non_software_signals": []
        }

    return {
        "job_domain": "unknown",
        "domain_confidence": 40,
        "domain_reason": "Insufficient domain signals",
        "matched_software_signals": desc_software_signals[:3],
        "matched_non_software_signals": desc_non_software_signals[:3]
    }


def title_based_score(job: dict, profile: dict) -> dict:
    domain_result = classify_job_domain(job)
    job_domain = domain_result.get("job_domain", "unknown")
    domain_conf = domain_result.get("domain_confidence", 50)
    domain_reason = domain_result.get("domain_reason", "")

    # Hard rejection for non-software QA roles
    if job_domain == "non_software_qa":
        return {
            "match_score": 0,
            "match_reasons": ["Non-software QA domain (manufacturing/apparel/supplier quality)"],
            "missing_skills": [],
            "nice_to_have_present": [],
            "recommendation": "REJECT",
            "recommendation_reason": domain_reason or "Non-software QA domain",
            "seniority_match": False,
            "remote_type": "not_specified",
            "job_domain": "non_software_qa",
            "domain_confidence": domain_conf,
            "domain_reason": domain_reason,
            "scored_by": "domain_filter_fallback"
        }

    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()
    score = 0
    reasons = []
    missing = []

    # Domain bonus: only given if verified software QA
    if job_domain == "software_qa" or any(kw in title for kw in STRONG_SOFTWARE_QA_TITLES):
        score += 50
        reasons.append("Job title / description matches Software QA & Automation domain")
    elif any(kw in title for kw in ["quality assurance", "quality engineer", "qa analyst"]):
        score += 15
        reasons.append("Generic QA title (unconfirmed software testing domain)")

    exp = profile.get("experience_years", 0)

    if exp >= 4 and any(w in title for w in ["senior", "lead", "principal", "architect", "manager", "staff"]):
        score += 20
        reasons.append(f"Seniority level matches your {exp}+ years experience")
    elif not any(w in title for w in ["senior", "lead", "junior", "principal"]):
        score += 15
        reasons.append("Mid-level position matches your profile")

    profile_skills = get_profile_skills(profile)

    for skill in profile_skills:
        skill_str = str(skill).lower()
        if len(skill_str) >= 3 and (skill_str in title or skill_str in description):
            score += 10
            reasons.append(f"{skill} matches your profile")
            break

    skill_names = [str(skill).strip().lower() for skill in profile_skills]

    def has_skill(skill_keywords):
        return any(
            keyword.lower() in skill_names
            or any(keyword.lower() in skill for skill in skill_names)
            for keyword in skill_keywords
        )

    if not has_skill(["cypress"]):
        missing.append("Cypress")

    if not has_skill(["playwright", "playwright test", "microsoft playwright"]):
        missing.append("Playwright")

    if not has_skill(["k6", "grafana k6", "k6 performance testing"]):
        missing.append("K6 performance testing")

    is_verified_software = (job_domain == "software_qa" or any(kw in title for kw in STRONG_SOFTWARE_QA_TITLES))
    final_score = min(score, 85) if is_verified_software else min(score, 35)
    rec = "APPLY" if final_score >= 50 else ("MAYBE" if final_score >= 35 else "REJECT")

    return {
        "match_score": final_score,
        "match_reasons": reasons or ["QA role matching your profile"],
        "missing_skills": missing[:3],
        "nice_to_have_present": [],
        "recommendation": rec,
        "recommendation_reason": "Title and skill matching (deterministic fallback)",
        "seniority_match": True,
        "remote_type": "not_specified",
        "job_domain": job_domain,
        "domain_confidence": domain_conf,
        "domain_reason": domain_reason,
        "scored_by": "title_fallback"
    }


def match_job_to_profile(job: dict, profile: dict, model) -> dict:
    # 1. Deterministic domain pre-check
    domain_result = classify_job_domain(job)
    if domain_result.get("job_domain") == "non_software_qa" and domain_result.get("domain_confidence", 0) >= 90:
        job.update({
            "match_score": 0,
            "match_reasons": ["Non-software QA domain (manufacturing/apparel/supplier quality)"],
            "missing_skills": [],
            "nice_to_have_present": [],
            "recommendation": "REJECT",
            "recommendation_reason": domain_result.get("domain_reason", "Non-software QA domain"),
            "seniority_match": False,
            "remote_type": "not_specified",
            "job_domain": "non_software_qa",
            "domain_confidence": domain_result.get("domain_confidence", 95),
            "domain_reason": domain_result.get("domain_reason", ""),
            "scored_by": "deterministic_domain_guard"
        })
        print(f"      🚫 Domain rejected (non-software): {domain_result['domain_reason']}")
        return job

    tech_skills = profile.get("tech_skills", {})
    profile_summary = {
        "experience_years": profile.get("experience_years", 0),
        "current_level": profile.get("current_level", "mid"),
        "job_titles": profile.get("job_titles", []),
        "test_automation": tech_skills.get("test_automation", tech_skills.get("test_frameworks", [])),
        "programming_languages": tech_skills.get("programming_languages", []),
        "api_testing": tech_skills.get("api_testing", []),
        "performance_testing": tech_skills.get("performance_testing", []),
        "ci_cd": tech_skills.get("ci_cd", []),
        "testing": tech_skills.get("testing", []),
        "qa_practices": tech_skills.get("qa_practices", []),
        "tools": tech_skills.get("tools", []),
        "methodologies": tech_skills.get("methodologies", []),
    }

    description = job.get("description", "").strip()

    if len(description) < 100:
        print("      ℹ️ Short description — title fallback")
        job.update(title_based_score(job, profile))
        return job

    prompt = f"""You are an expert Software Quality Engineering Recruiter evaluating a candidate for a job opening.

CANDIDATE PROFILE:
- Role: Senior Software QA / SDET / Test Automation Engineer
- Total Experience: {profile.get('experience_years', 13)} years
- Candidate Skills:
{json.dumps(profile_summary, indent=2)}

JOB DETAILS:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Description:
{description[:2500]}

EVALUATION INSTRUCTIONS:
STEP 1: CLASSIFY JOB DOMAIN
- Classify as "software_qa" ONLY if the role's primary responsibility is Software QA / SDET / Test Automation / Quality Engineering (writing/running/maintaining tests, test frameworks, automation suites, QA processes for software).
- Classify as "non_software_qa" for EVERY other role, including but not limited to: non-software physical manufacturing, apparel, garment, textile, footwear, factory inspection, supplier audit, or product quality roles; AND any other software/tech/business role whose primary focus is NOT testing — e.g. Salesforce/CRM/Marketing Cloud administrator or platform manager, general software/backend/frontend developer, DevOps/SRE/infrastructure engineer, product manager, business analyst, data analyst/scientist, project manager, scrum master, sales/marketing/HR/recruiting roles, solutions architect, or any role where testing is only a minor mentioned responsibility rather than the job's purpose.
- CRITICAL: Candidate is strictly looking for Software Quality Engineering / SDET roles. Do NOT classify a job as "software_qa" just because it is a tech job or mentions Git/JIRA/API/JavaScript/testing in passing — the JOB TITLE and PRIMARY PURPOSE must be QA/testing/automation. Any job that fails this MUST be classified as "non_software_qa" with match_score = 0 and recommendation = "REJECT".

STEP 2: SCORE (ONLY IF software_qa)
- Software QA Technical & Automation Match (Selenium, Playwright, Java, TypeScript, API, CI/CD, Seniority): Primary weight (60%)
- Remote Eligibility (Worldwide Remote, Asia/Bangladesh Remote, Work from Anywhere): High weight (40%)
- Single-country restrictions (e.g. US Only, UK only work authorization): adjust score accordingly.
- Base Rule: Legitimate Software QA role + QA candidate = minimum base score 50.

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "job_domain": "software_qa",
  "domain_confidence": 95,
  "domain_reason": "Role focuses on Playwright, Selenium and API automation for software applications",
  "match_score": 75,
  "match_reasons": ["Software QA automation role", "Strong technical match on Playwright and Selenium"],
  "missing_skills": ["Cypress", "K6"],
  "nice_to_have_present": ["JIRA"],
  "recommendation": "APPLY",
  "recommendation_reason": "Strong core match for senior automation role",
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

        job_domain = match_data.get("job_domain", domain_result.get("job_domain", "software_qa"))
        domain_conf = int(match_data.get("domain_confidence", domain_result.get("domain_confidence", 80)))
        domain_reason = match_data.get("domain_reason", domain_result.get("domain_reason", ""))

        # HARD DOMAIN GUARD: If Gemini or our deterministic classifier detects non_software_qa
        if job_domain == "non_software_qa" or domain_result.get("job_domain") == "non_software_qa":
            match_score = 0
            rec = "REJECT"
            reasons = ["Non-software QA domain (manufacturing/apparel/supplier quality)"]
            rec_reason = domain_reason or "Non-software QA domain"
        else:
            match_score = int(match_data.get("match_score", 0))
            rec = match_data.get("recommendation", "MAYBE")
            reasons = match_data.get("match_reasons", [])
            rec_reason = match_data.get("recommendation_reason", "")

        job.update({
            "match_score": match_score,
            "match_reasons": reasons,
            "missing_skills": match_data.get("missing_skills", []),
            "nice_to_have_present": match_data.get("nice_to_have_present", []),
            "recommendation": rec,
            "recommendation_reason": rec_reason,
            "seniority_match": match_data.get("seniority_match", False),
            "remote_type": match_data.get("remote_type", "not_specified"),
            "job_domain": job_domain,
            "domain_confidence": domain_conf,
            "domain_reason": domain_reason,
            "scored_by": "gemini",
        })

        print(
            f"      ✅ Score: {job['match_score']}% ({job['recommendation']}) [{job['job_domain']}]"
        )

    except Exception as e:
        print(f"      ⚠️ Gemini error: {str(e)[:80]} — title fallback")
        job.update(title_based_score(job, profile))

    return job


def batch_match_jobs(jobs: list, min_score: int = 0) -> list:
    config = load_config()
    profile = load_profile()
    api_key = config.get("api_keys", {}).get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")

    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        print(f"   ℹ️  Gemini key not set — using domain & title fallback for {len(jobs)} jobs...")
        matched = []
        filtered_non_software = 0
        for job in jobs:
            matched_job = dict(job)
            matched_job.update(title_based_score(job, profile))
            if matched_job.get("job_domain") == "non_software_qa" or matched_job.get("recommendation") == "REJECT" or matched_job.get("match_score", 0) == 0:
                filtered_non_software += 1
                continue
            if matched_job.get("match_score", 0) >= min_score:
                matched.append(matched_job)
        matched.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        if filtered_non_software > 0:
            print(f"   🚫 Filtered out {filtered_non_software} non-software QA / low match jobs")
        print(f"\n✅ Matched: {len(matched)} Software QA jobs (score >= {min_score}%)")
        return matched

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    matched = []
    filtered_non_software = 0

    print(f"🤖 Matching {len(jobs)} jobs with Gemini AI ({GEMINI_MODEL})...")

    for i, job in enumerate(jobs, 1):
        print(f"   [{i}/{len(jobs)}] {job.get('title', '?')[:40]} @ {job.get('company', '?')[:20]}...")
        matched_job = match_job_to_profile(job, profile, model)

        if matched_job.get("job_domain") == "non_software_qa" or matched_job.get("recommendation") == "REJECT" or matched_job.get("match_score", 0) == 0:
            filtered_non_software += 1
            continue

        if matched_job.get("match_score", 0) >= min_score:
            matched.append(matched_job)

        if i % 10 == 0:
            print("   ⏳ Rate limit pause 3s...")
            time.sleep(3)

    matched.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    if filtered_non_software > 0:
        print(f"   🚫 Filtered out {filtered_non_software} non-software QA / low match jobs")
    print(f"\n✅ Matched: {len(matched)} Software QA jobs (score >= {min_score}%)")
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