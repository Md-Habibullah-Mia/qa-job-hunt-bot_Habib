"""
question_answerer.py
Uses Gemini AI to answer custom application form questions.
Hardcoded answers for common questions, AI for free-text.
"""

import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GEMINI_MODEL = "gemini-flash-latest"

# Common questions with pattern-based answers.
# Work-authorization and sponsorship answers depend on the country the job is
# in, and a wrong one is a false statement on the application — so they are
# left unanswered (None). The form then can't be submitted and the job is
# marked for manual apply instead.
COMMON_PATTERNS = {
    r"(authorized|authorised|legally|eligible|right to work).*(work|employ)": None,
    r"(require|need).*(sponsor|visa)": None,
    r"(willing|open).*(relocat|move)": "yes",
    r"(willing|open).*(travel)": "yes",
    r"(18|legal age|older)": "yes",
    r"(background check|drug test)": "yes",
    r"(start|join|available).*(immediately|when|date)": "Immediately / 2 weeks notice",
    r"(gender|pronoun)": None,  # Skip sensitive questions
    r"(race|ethnic|disability|veteran)": None,  # Skip EEO questions
}


def answer_common_question(question_text: str, profile: dict) -> str | None:
    """
    Try to answer common application questions from profile data.
    Returns None if the question isn't a common pattern.
    """
    q = question_text.lower().strip()

    # Pattern matching for yes/no questions
    for pattern, answer in COMMON_PATTERNS.items():
        if re.search(pattern, q):
            return answer

    # Experience years
    if re.search(r"(years?|yrs?).*(experience|professional)", q):
        return str(profile.get("experience_years", 3))

    # Salary expectations
    if re.search(r"(salary|compensation|pay|ctc)", q):
        return "Open to discuss based on the role and responsibilities"

    # Current location / city
    if re.search(r"(current|your).*(location|city|address)", q):
        return profile.get("personal", {}).get("location", "")

    # LinkedIn
    if re.search(r"linkedin", q):
        linkedin = profile.get("personal", {}).get("linkedin", "")
        if linkedin and not linkedin.startswith("http"):
            linkedin = f"https://{linkedin}"
        return linkedin

    # GitHub / portfolio
    if re.search(r"(github|portfolio|website|personal.*url)", q):
        github = profile.get("personal", {}).get("github", "")
        if github and not github.startswith("http"):
            github = f"https://{github}"
        return github

    # Current company / employer
    if re.search(r"(current|present).*(company|employer|organization)", q):
        work_exp = profile.get("work_experience", [])
        if work_exp:
            return work_exp[0].get("company", "")
        return ""

    # Current job title
    if re.search(r"(current|present).*(title|role|position|designation)", q):
        work_exp = profile.get("work_experience", [])
        if work_exp:
            return work_exp[0].get("title", "")
        return profile.get("job_titles", [""])[0]

    # Notice period
    if re.search(r"(notice period|notice)", q):
        return "2 weeks"

    # How did you hear about us
    if re.search(r"(hear|learn|find|know).*(about|us|role|position|company)", q):
        return "Job board"

    return None


def answer_with_gemini(question_text: str, profile: dict, api_key: str) -> str:
    """
    Use Gemini AI to generate a contextual answer for a custom question.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)

        skills_flat = []
        for category, items in profile.get("tech_skills", {}).items():
            if isinstance(items, list):
                skills_flat.extend(items)

        prompt = f"""You are filling out a job application form for a QA Automation Engineer position.
Answer this application question concisely and professionally (1-3 sentences max).

Candidate Profile:
- Name: {profile.get('personal', {}).get('name', '')}
- Experience: {profile.get('experience_years', 3)} years
- Level: {profile.get('current_level', 'mid')}
- Key Skills: {', '.join(skills_flat[:15])}
- Summary: {profile.get('summary', '')}

Question: {question_text}

Rules:
- Be concise and professional
- Don't make up specific numbers or facts not in the profile
- If it's a yes/no question, answer yes/no first then briefly explain
- Keep answer under 200 characters if possible
- Return ONLY the answer text, nothing else"""

        response = model.generate_content(prompt)
        answer = response.text.strip()
        # Trim to reasonable length
        if len(answer) > 500:
            answer = answer[:497] + "..."
        return answer

    except Exception as e:
        print(f"      ⚠️ Gemini Q&A error: {e}")
        return ""


def answer_question(question_text: str, profile: dict, api_key: str = "") -> str | None:
    """
    Main entry point. Tries common patterns first, then Gemini AI.
    Returns None for questions that should be skipped (EEO, sensitive).
    Returns empty string if unable to answer.
    """
    if not question_text or len(question_text.strip()) < 3:
        return ""

    # Try common patterns first (free, fast)
    common = answer_common_question(question_text, profile)
    if common is not None:
        return common

    # Fall back to Gemini AI
    if api_key:
        return answer_with_gemini(question_text, profile, api_key)

    return ""
