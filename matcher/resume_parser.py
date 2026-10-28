"""
resume_parser.py
Parses your resume PDF using Google Gemini AI (FREE) and generates a structured profile JSON.
Run once: python matcher/resume_parser.py --resume /path/to/resume.pdf

Get your FREE Gemini API key at: https://aistudio.google.com
Free tier: 15 requests/min, 1500 requests/day — more than enough!
"""

import google.generativeai as genai
import json
import fitz  # PyMuPDF
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "resume_profile.json")


def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def clean_json_response(raw: str) -> str:
    """Strip markdown code fences from Gemini response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw.strip()


def parse_resume_with_gemini(resume_text: str, api_key: str) -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.6-flash")

    prompt = f"""You are a resume parser specialized in QA/Test Automation Engineering roles.

Parse this resume and extract ALL information into a structured JSON profile.

Resume Text:
{resume_text}

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "personal": {{
    "name": "Full Name",
    "email": "email",
    "phone": "phone",
    "location": "City, Country",
    "linkedin": "url or null",
    "github": "url or null"
  }},
  "summary": "2-3 sentence professional summary",
  "experience_years": 5,
  "current_level": "junior|mid|senior|lead|principal",
  "job_titles": ["QA Automation Engineer", "SDET"],
  "tech_skills": {{
    "test_frameworks": ["Selenium", "Playwright", "Cypress", "Appium", "TestNG", "JUnit", "PyTest"],
    "programming_languages": ["Python", "Java", "JavaScript"],
    "api_testing": ["Postman", "RestAssured", "Karate"],
    "performance_testing": ["JMeter", "Gatling", "K6"],
    "ci_cd": ["Jenkins", "GitHub Actions", "GitLab CI"],
    "cloud": ["AWS", "Azure", "GCP"],
    "databases": ["MySQL", "PostgreSQL", "MongoDB"],
    "version_control": ["Git"],
    "project_management": ["JIRA", "TestRail", "Zephyr"],
    "mobile_testing": ["Appium"],
    "other": []
  }},
  "soft_skills": ["Communication", "Leadership"],
  "work_experience": [
    {{
      "company": "Company Name",
      "title": "Job Title",
      "duration": "Jan 2021 - Present",
      "years": 3.0,
      "description": "Key achievements and responsibilities",
      "technologies": ["Selenium", "Python"]
    }}
  ],
  "education": [
    {{
      "degree": "B.Tech Computer Science",
      "institution": "University Name",
      "year": 2019
    }}
  ],
  "certifications": ["ISTQB Foundation"],
  "domains_tested": ["E-commerce", "Banking", "Healthcare"],
  "methodologies": ["Agile", "Scrum", "BDD", "TDD"],
  "languages_spoken": ["English", "Hindi"],
  "achievements": ["Reduced test execution time by 60%"]
}}

Return ONLY the JSON. No markdown, no explanation."""

    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="Parse resume with Gemini AI (Free)")
    parser.add_argument("--resume", required=True, help="Path to resume PDF")
    args = parser.parse_args()

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    api_key = config["api_keys"]["gemini_api_key"]
    if api_key == "YOUR_GEMINI_API_KEY_HERE":
        print("❌ Please set your Gemini API key in config/config.json")
        print("   Get free key at: https://aistudio.google.com")
        sys.exit(1)

    print(f"📄 Reading resume: {args.resume}")
    resume_text = extract_text_from_pdf(args.resume)

    print("🤖 Parsing with Gemini AI (Free)...")
    profile = parse_resume_with_gemini(resume_text, api_key)

    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

    print(f"✅ Profile saved to: {PROFILE_PATH}")
    print(f"\n📊 Extracted Profile Summary:")
    print(f"   Name: {profile['personal']['name']}")
    print(f"   Level: {profile['current_level']}")
    print(f"   Experience: {profile['experience_years']} years")
    print(f"   Key Skills: {', '.join(profile['tech_skills'].get('test_frameworks', [])[:5])}")
    print(f"   Languages: {', '.join(profile['tech_skills'].get('programming_languages', []))}")


if __name__ == "__main__":
    main()
