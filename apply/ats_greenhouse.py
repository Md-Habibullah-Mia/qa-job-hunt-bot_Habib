"""
ats_greenhouse.py
Fills and submits Greenhouse application forms.
Greenhouse URL pattern: boards.greenhouse.io/{company}/jobs/{id}
"""

import os
import sys
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apply.question_answerer import answer_question
from apply.submit_guard import pre_submit_check


async def apply_greenhouse(page: Page, url: str, profile: dict,
                           resume_path: str, api_key: str = "",
                           dry_run: bool = True) -> str:
    """
    Fill and optionally submit a Greenhouse application form.
    Returns status string.
    """
    personal = profile.get("personal", {})
    name_parts = personal.get("name", "").split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    try:
        # Navigate to the application page
        # Greenhouse job URLs: boards.greenhouse.io/{company}/jobs/{id}
        # Add #app_form to go directly to the form
        if "/jobs/" in url and "#" not in url:
            url = url.rstrip("/") + "#app_form"

        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)

        # Check if we're on a valid Greenhouse page
        form = await page.query_selector("#application_form, form[action*='applications'], #application")
        if not form:
            # Maybe we're on the job description page, look for Apply button
            apply_btn = await page.query_selector("a[href*='#app'], a:has-text('Apply'), button:has-text('Apply')")
            if apply_btn:
                await apply_btn.click()
                await page.wait_for_timeout(2000)
                form = await page.query_selector("#application_form, form[action*='applications'], #application")

        if not form:
            return "skipped_no_form"

        print(f"      📝 Filling Greenhouse form...")
        filled_fields = []

        # --- First Name ---
        first_name_field = await page.query_selector(
            "#first_name, input[name='job_application[first_name]'], "
            "input[autocomplete='given-name'], input[id*='first_name']"
        )
        if first_name_field and first_name:
            await first_name_field.fill(first_name)
            filled_fields.append(f"first_name={first_name}")

        # --- Last Name ---
        last_name_field = await page.query_selector(
            "#last_name, input[name='job_application[last_name]'], "
            "input[autocomplete='family-name'], input[id*='last_name']"
        )
        if last_name_field and last_name:
            await last_name_field.fill(last_name)
            filled_fields.append(f"last_name={last_name}")

        # --- Email ---
        email_field = await page.query_selector(
            "#email, input[name='job_application[email]'], "
            "input[type='email'], input[autocomplete='email']"
        )
        if email_field and personal.get("email"):
            await email_field.fill(personal["email"])
            filled_fields.append(f"email={personal['email']}")

        # --- Phone ---
        phone_field = await page.query_selector(
            "#phone, input[name='job_application[phone]'], "
            "input[type='tel'], input[autocomplete='tel']"
        )
        if phone_field and personal.get("phone"):
            await phone_field.fill(personal["phone"])
            filled_fields.append("phone=***")

        # --- Resume Upload ---
        resume_input = await page.query_selector(
            "input[type='file'][id*='resume'], input[type='file'][name*='resume'], "
            "input[type='file']:first-of-type"
        )
        if resume_input and resume_path and os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            await page.wait_for_timeout(1000)
            filled_fields.append(f"resume={os.path.basename(resume_path)}")

        # --- LinkedIn URL ---
        linkedin_field = await page.query_selector(
            "input[name*='linkedin'], input[id*='linkedin'], "
            "input[placeholder*='linkedin' i], input[aria-label*='LinkedIn' i]"
        )
        if linkedin_field and personal.get("linkedin"):
            linkedin_url = personal["linkedin"]
            if not linkedin_url.startswith("http"):
                linkedin_url = f"https://{linkedin_url}"
            await linkedin_field.fill(linkedin_url)
            filled_fields.append("linkedin=filled")

        # --- GitHub / Portfolio URL ---
        github_field = await page.query_selector(
            "input[name*='github'], input[id*='github'], "
            "input[placeholder*='github' i], input[name*='portfolio'], "
            "input[name*='website'], input[placeholder*='portfolio' i]"
        )
        if github_field and personal.get("github"):
            github_url = personal["github"]
            if not github_url.startswith("http"):
                github_url = f"https://{github_url}"
            await github_field.fill(github_url)
            filled_fields.append("github=filled")

        # --- Location ---
        location_field = await page.query_selector(
            "input[name*='location'], input[id*='location'], "
            "input[placeholder*='location' i], input[placeholder*='city' i]"
        )
        if location_field and personal.get("location"):
            await location_field.fill(personal["location"])
            filled_fields.append("location=filled")

        # --- Handle custom questions ---
        await _fill_custom_questions(page, profile, api_key, filled_fields)

        # --- Handle dropdowns (select elements) ---
        await _fill_dropdowns(page, profile, api_key, filled_fields)

        print(f"      ✅ Filled {len(filled_fields)} fields: {', '.join(filled_fields)}")

        blocked = await pre_submit_check(page)
        if blocked:
            return blocked

        # --- Submit or Dry Run ---
        if dry_run:
            print(f"      🏃 DRY RUN — form filled but NOT submitted")
            return "dry_run_success"

        # Find and click submit button
        submit_btn = await page.query_selector(
            "input[type='submit'][value*='Submit'], "
            "button[type='submit'], "
            "input[type='submit'], "
            "button:has-text('Submit Application'), "
            "button:has-text('Submit')"
        )
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

            # Check for success
            success = await page.query_selector(
                ".flash-success, [class*='success'], [class*='confirmation'], "
                "h1:has-text('Thank'), h2:has-text('Thank'), "
                "h1:has-text('Application'), p:has-text('received')"
            )
            if success:
                return "applied"

            # Check for errors
            error = await page.query_selector(
                ".flash-error, [class*='error'], [class*='invalid']"
            )
            if error:
                error_text = await error.inner_text()
                print(f"      ❌ Form error: {error_text[:100]}")
                return f"failed_form_error"

            # No clear success/error — don't claim it was submitted
            return "unconfirmed"
        else:
            return "skipped_no_submit_button"

    except PlaywrightTimeout:
        return "failed_timeout"
    except Exception as e:
        print(f"      ❌ Greenhouse error: {e}")
        return f"failed_{str(e)[:50]}"


async def _fill_custom_questions(page: Page, profile: dict, api_key: str,
                                  filled_fields: list):
    """Fill custom text/textarea questions using AI."""
    # Find question containers — Greenhouse wraps them in field divs
    question_fields = await page.query_selector_all(
        ".field, .custom-question, [class*='custom-question'], "
        "[data-field-type='custom']"
    )

    for field in question_fields:
        try:
            # Get the label/question text
            label = await field.query_selector("label, .field__label")
            if not label:
                continue
            question_text = await label.inner_text()
            question_text = question_text.strip()
            if not question_text or len(question_text) < 5:
                continue

            # Skip if it's a standard field we already handled
            standard = ["first name", "last name", "email", "phone", "resume", "linkedin"]
            if any(s in question_text.lower() for s in standard):
                continue

            # Find the input/textarea in this field
            text_input = await field.query_selector(
                "textarea, input[type='text'], input:not([type='file']):not([type='hidden'])"
                ":not([type='submit']):not([type='checkbox']):not([type='radio'])"
            )
            if not text_input:
                continue

            # Check if already has a value
            current = await text_input.input_value()
            if current:
                continue

            # Get answer
            answer = answer_question(question_text, profile, api_key)
            if answer is None:  # Skip sensitive questions
                continue
            if answer:
                await text_input.fill(answer)
                filled_fields.append(f"q:{question_text[:30]}...")

        except Exception:
            continue


async def _fill_dropdowns(page: Page, profile: dict, api_key: str,
                           filled_fields: list):
    """Handle select dropdowns in the form."""
    selects = await page.query_selector_all("select:not([style*='display: none'])")

    for select in selects:
        try:
            # Get label for this select
            select_id = await select.get_attribute("id")
            label_text = ""
            if select_id:
                label = await page.query_selector(f"label[for='{select_id}']")
                if label:
                    label_text = await label.inner_text()

            # Check if already selected (not on default/placeholder)
            current_val = await select.input_value()
            if current_val:
                continue

            options = await select.query_selector_all("option")
            if len(options) <= 1:
                continue

            # Try to pick the best option
            if label_text:
                answer = answer_question(label_text, profile, api_key)
                if answer:
                    # Try to match answer to an option
                    for opt in options[1:]:
                        opt_text = await opt.inner_text()
                        if answer.lower() in opt_text.lower() or opt_text.lower() in answer.lower():
                            val = await opt.get_attribute("value")
                            if val:
                                await select.select_option(value=val)
                                filled_fields.append(f"select:{label_text[:20]}")
                                break
                    else:
                        # No answer matched a real option — leave it on the
                        # placeholder rather than guessing (a wrong dropdown
                        # value can misrepresent a real applicant).
                        filled_fields.append(f"select:{label_text[:20]}=UNANSWERED")
            # else: no label found — can't know what this field is asking,
            # so it's left unanswered rather than guessed.

        except Exception:
            continue
