"""
cover_note.py
Writes a short cover note per top-matched job with Gemini, using only facts
from resume_profile.json. Shown on the dashboard (copy for manual applies) and
used as the "additional information" text in auto-apply forms.
"""

import json
import time

import google.generativeai as genai

from matcher.job_matcher import GEMINI_MODEL


def _profile_facts(profile: dict) -> str:
    work = [
        f"- {w.get('title')} at {w.get('company')} ({w.get('duration')}): {w.get('description', '')[:600]}"
        for w in profile.get("work_experience", [])[:3]
    ]
    return "\n".join([
        f"Name: {profile.get('personal', {}).get('name', '')}",
        f"Headline: {profile.get('headline', '')}",
        f"Summary: {profile.get('summary', '')}",
        f"Skills: {json.dumps(profile.get('tech_skills', {}))}",
        "Recent experience:",
        *work,
        f"Achievements: {json.dumps(profile.get('achievements', []))}",
    ])


def generate_cover_notes(jobs: list, profile: dict, api_key: str,
                         limit: int = 10, min_score: int = 75) -> int:
    """
    Add job["cover_note"] to the best-scoring jobs, in place.
    Returns how many notes were written.
    """
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        print("   ℹ️ No Gemini key — skipping cover notes")
        return 0

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    facts = _profile_facts(profile)
    targets = sorted(
        (j for j in jobs if j.get("match_score", 0) >= min_score and j.get("source") != "manual"),
        key=lambda j: j.get("match_score", 0), reverse=True,
    )[:limit]

    written = 0
    for job in targets:
        prompt = f"""Write a short cover note (90-130 words) from this candidate to the hiring team.

CANDIDATE FACTS (use ONLY these — never invent employers, numbers, tools or certifications):
{facts}

JOB:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description: {(job.get('description') or '')[:2000]}

Rules:
- First line addresses the role by name. No "Dear Hiring Manager", no subject line, no sign-off name.
- Pick the 2-3 candidate facts that best fit THIS job's requirements and say how they map.
- Plain, confident, specific. No buzzwords like "passionate", "synergy", "rockstar".
- If the job needs something the candidate lacks, don't claim it.
- Return only the note text."""
        try:
            text = model.generate_content(prompt).text.strip()
            if text:
                job["cover_note"] = text
                written += 1
        except Exception as e:
            print(f"   ⚠️ Cover note failed for {job.get('title', '?')[:40]}: {str(e)[:80]}")
        time.sleep(1)

    print(f"   📝 Cover notes written: {written}/{len(targets)}")
    return written
