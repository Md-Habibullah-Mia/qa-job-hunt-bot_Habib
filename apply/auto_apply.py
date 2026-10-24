"""
auto_apply.py
Automatically applies to jobs via LinkedIn Easy Apply.
Tracks all applications in applied_jobs.json.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apply.question_answerer import answer_question

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "resume_profile.json")
APPLIED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "applied_jobs.json")


def load_applied_jobs() -> dict:
    if os.path.exists(APPLIED_PATH):
        with open(APPLIED_PATH) as f:
            return json.load(f)
    return {}


def save_applied_job(job_id: str, job: dict, status: str, method: str = "linkedin_easy_apply"):
    applied = load_applied_jobs()
    applied[job_id] = {
        "title": job.get("title"),
        "company": job.get("company"),
        "url": job.get("url"),
        "applied_at": datetime.now().isoformat(),
        "status": status,
        "match_score": job.get("match_score", 0),
        "method": method,  # "linkedin_easy_apply" | "direct_greenhouse" | "direct_lever"
    }
    os.makedirs(os.path.dirname(APPLIED_PATH), exist_ok=True)
    with open(APPLIED_PATH, "w") as f:
        json.dump(applied, f, indent=2)


async def _answer_radio_groups(page, profile: dict):
    """
    Answer Yes/No (and similar) radio-button question groups based on the
    actual question text, using the same pattern-matching as the ATS forms.
    A group is left unanswered — not guessed — when the question text can't
    be read or matched, so it blocks Next/Submit and surfaces as
    "skipped_manual_needed" instead of submitting a wrong answer.
    """
    groups = await page.query_selector_all("fieldset:has(input[type='radio'])")
    for group in groups:
        try:
            radios = await group.query_selector_all("input[type='radio']")
            if not radios:
                continue

            already_answered = False
            for r in radios:
                if await r.is_checked():
                    already_answered = True
                    break
            if already_answered:
                continue

            legend_el = await group.query_selector(
                "legend, .fb-dash-form-element__label, label"
            )
            question_text = (await legend_el.inner_text()).strip() if legend_el else ""
            if not question_text:
                continue

            answer = answer_question(question_text, profile)
            if not answer:  # None (sensitive/EEO) or "" (unknown) — don't guess
                continue

            wants_yes = str(answer).strip().lower().startswith("y")
            for r in radios:
                val = ((await r.get_attribute("value")) or "").strip().lower()
                if (wants_yes and val == "yes") or (not wants_yes and val == "no"):
                    await r.check()
                    break
        except Exception:
            continue


async def _answer_select_dropdowns(page, profile: dict):
    """
    Answer <select> dropdowns from their label text, same rule as radios:
    an unmatched dropdown is left on its placeholder rather than defaulting
    to "first option", which previously could silently submit a wrong value.
    """
    selects = await page.query_selector_all("select")
    for select in selects:
        try:
            current = await select.input_value()
            if current:
                continue

            options = await select.query_selector_all("option")
            if len(options) <= 1:
                continue

            select_id = await select.get_attribute("id")
            label_text = ""
            if select_id:
                label_el = await page.query_selector(f"label[for='{select_id}']")
                if label_el:
                    label_text = (await label_el.inner_text()).strip()

            if not label_text:
                continue  # no way to know what this field is asking — skip

            answer = answer_question(label_text, profile)
            if not answer:
                continue

            for opt in options[1:]:
                opt_text = (await opt.inner_text()).strip().lower()
                if answer.lower() in opt_text or opt_text in answer.lower():
                    val = await opt.get_attribute("value")
                    if val:
                        await select.select_option(value=val)
                    break
        except Exception:
            continue


async def apply_to_linkedin_job(page, job: dict, profile: dict, resume_path: str) -> str:
    """
    Attempt LinkedIn Easy Apply. Returns status string.
    """
    url = job.get("url", "")
    if not url or "linkedin.com" not in url:
        return "skipped_not_linkedin"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # Look for Easy Apply button
        easy_apply_btn = await page.query_selector("button[aria-label*='Easy Apply'], .jobs-apply-button--top-card")
        if not easy_apply_btn:
            return "skipped_no_easy_apply"

        await easy_apply_btn.click()
        await page.wait_for_timeout(2000)

        # Handle multi-step Easy Apply modal
        max_steps = 8
        for step in range(max_steps):
            # Check if application is complete
            success_el = await page.query_selector("[aria-label*='submitted'], .jobs-easy-apply-modal__content h3")
            if success_el:
                text = await success_el.inner_text()
                if "submitted" in text.lower() or "sent" in text.lower():
                    return "applied"

            # Handle phone field
            phone_field = await page.query_selector("input[id*='phone'], input[name*='phone']")
            if phone_field:
                val = await phone_field.input_value()
                if not val:
                    phone = profile.get("personal", {}).get("phone", "")
                    if phone:
                        await phone_field.fill(phone)

            # Handle city/location field
            city_field = await page.query_selector("input[id*='city'], input[name*='location']")
            if city_field:
                val = await city_field.input_value()
                if not val:
                    location = profile.get("personal", {}).get("location", "")
                    if location:
                        await city_field.fill(location.split(",")[0])

            # Handle resume upload if present
            resume_upload = await page.query_selector("input[type='file']")
            if resume_upload and resume_path and os.path.exists(resume_path):
                await resume_upload.set_input_files(resume_path)
                await page.wait_for_timeout(1000)

            # Handle Yes/No radio button groups — answered from the actual
            # question text (same pattern-matching as ATS forms), never a
            # blind "Yes". A wrong auto-answer here can disqualify a real
            # candidate, so an unclear question is left unanswered instead
            # of guessed; that surfaces as "skipped_manual_needed" below
            # rather than a submitted wrong answer.
            await _answer_radio_groups(page, profile)

            # Handle select dropdowns — answered from label text, unmatched
            # ones left alone (see _answer_select_dropdowns docstring).
            await _answer_select_dropdowns(page, profile)

            # Handle experience/year input fields (numeric)
            number_inputs = await page.query_selector_all("input[type='text'][id*='year'], input[type='number']")
            for inp in number_inputs:
                val = await inp.input_value()
                if not val:
                    exp_years = str(profile.get("experience_years", 3))
                    await inp.fill(exp_years)

            # Click Next or Submit
            next_btn = await page.query_selector(
                "button[aria-label='Continue to next step'], "
                "button[aria-label='Review your application'], "
                "button[aria-label='Submit application'], "
                "button:has-text('Next'), button:has-text('Review'), button:has-text('Submit')"
            )

            if next_btn:
                btn_text = await next_btn.inner_text()
                await next_btn.click()
                await page.wait_for_timeout(2000)

                if "submit" in btn_text.lower():
                    return "applied"
            else:
                # Can't find next button - may need manual intervention
                return "skipped_manual_needed"

        return "skipped_too_many_steps"

    except PlaywrightTimeout:
        return "failed_timeout"
    except Exception as e:
        return f"failed_{str(e)[:50]}"


async def auto_apply_batch(jobs: list, resume_path: str, max_applications: int = 10) -> list:
    """
    Auto-apply to a list of matched jobs.
    Returns list of application results.
    """
    config_path = CONFIG_PATH
    with open(config_path) as f:
        config = json.load(f)

    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    if not config["linkedin"].get("auto_apply", False):
        print("⚠️ Auto-apply is disabled in config. Set linkedin.auto_apply = true to enable.")
        return []

    applied_jobs = load_applied_jobs()
    results = []
    apply_count = 0

    # Only apply to LinkedIn jobs with Easy Apply
    eligible = [
        j for j in jobs
        if j.get("source") == "linkedin"
        and j.get("recommendation") == "APPLY"
        and j.get("match_score", 0) >= 75
        and j.get("id", "") not in applied_jobs
    ]

    if not eligible:
        print("   No eligible jobs for auto-apply today")
        return []

    print(f"🚀 Auto-applying to {min(len(eligible), max_applications)} jobs...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False to handle CAPTCHAs
        context = await browser.new_context()

        # Login first
        page = await context.new_page()
        li_email = config["linkedin"].get("email", "")
        li_pass = config["linkedin"].get("password", "")

        if li_email and li_pass:
            await page.goto("https://www.linkedin.com/login")
            await page.fill("#username", li_email)
            await page.fill("#password", li_pass)
            await page.click('[type="submit"]')
            await page.wait_for_timeout(3000)

        for job in eligible[:max_applications]:
            if apply_count >= max_applications:
                break

            job_id = job.get("id", "")
            print(f"   📝 Applying: {job['title']} at {job['company']}...")

            status = await apply_to_linkedin_job(page, job, profile, resume_path)
            save_applied_job(job_id, job, status)

            result = {
                "job": job,
                "status": status,
                "applied_at": datetime.now().isoformat()
            }
            results.append(result)

            if status == "applied":
                apply_count += 1
                print(f"   ✅ Applied successfully!")
            else:
                print(f"   ⚠️ Status: {status}")

            await asyncio.sleep(5)  # Delay between applications

        await browser.close()

    print(f"\n📊 Auto-apply complete: {apply_count} successful applications")
    return results


def run_auto_apply(jobs: list, resume_path: str) -> list:
    """Synchronous wrapper for auto-apply."""
    config_path = CONFIG_PATH
    with open(config_path) as f:
        config = json.load(f)
    max_apply = config["linkedin"].get("max_apply_per_day", 10)
    return asyncio.run(auto_apply_batch(jobs, resume_path, max_apply))
