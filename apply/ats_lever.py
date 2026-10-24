"""
ats_lever.py
Fills and submits Lever application forms.
Lever URL pattern: jobs.lever.co/{company}/{id}
Apply page: jobs.lever.co/{company}/{id}/apply
"""

import os
import sys
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apply.question_answerer import answer_question
from apply.submit_guard import pre_submit_check


async def apply_lever(page: Page, url: str, profile: dict,
                      resume_path: str, api_key: str = "",
                      dry_run: bool = True) -> str:
    """
    Fill and optionally submit a Lever application form.
    Returns status string.
    """
    personal = profile.get("personal", {})

    try:
        # Lever apply URL: jobs.lever.co/{company}/{id}/apply
        apply_url = url.rstrip("/")
        if not apply_url.endswith("/apply"):
            apply_url = apply_url + "/apply"

        await page.goto(apply_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)

        # Check if we're on the apply page
        form = await page.query_selector(
            "form[action*='applications'], .application-form, "
            "#application-form, .postings-btn-wrapper"
        )
        if not form:
            # Maybe we need to click Apply first
            apply_btn = await page.query_selector(
                "a[href*='/apply'], a:has-text('Apply'), "
                "button:has-text('Apply for this job')"
            )
            if apply_btn:
                await apply_btn.click()
                await page.wait_for_timeout(2000)

        print(f"      📝 Filling Lever form...")
        filled_fields = []

        # --- Full Name (Lever uses a single name field) ---
        name_field = await page.query_selector(
            "input[name='name'], input[name='cards[0][field0]'], "
            "input[placeholder*='Full name' i], input[placeholder*='name' i]"
        )
        if name_field and personal.get("name"):
            await name_field.fill(personal["name"])
            filled_fields.append(f"name={personal['name']}")

        # --- Email ---
        email_field = await page.query_selector(
            "input[name='email'], input[name='cards[0][field1]'], "
            "input[type='email'], input[placeholder*='email' i]"
        )
        if email_field and personal.get("email"):
            await email_field.fill(personal["email"])
            filled_fields.append(f"email={personal['email']}")

        # --- Phone ---
        phone_field = await page.query_selector(
            "input[name='phone'], input[name='cards[0][field2]'], "
            "input[type='tel'], input[placeholder*='phone' i]"
        )
        if phone_field and personal.get("phone"):
            await phone_field.fill(personal["phone"])
            filled_fields.append("phone=***")

        # --- Current Company ---
        company_field = await page.query_selector(
            "input[name='org'], input[name='cards[0][field3]'], "
            "input[placeholder*='company' i], input[placeholder*='organization' i], "
            "input[placeholder*='Current company' i]"
        )
        if company_field:
            work_exp = profile.get("work_experience", [])
            current_company = work_exp[0].get("company", "") if work_exp else ""
            if current_company:
                await company_field.fill(current_company)
                filled_fields.append(f"company={current_company}")

        # --- Resume Upload ---
        resume_input = await page.query_selector(
            "input[type='file'][name*='resume'], "
            "input[type='file'][name*='cards'], "
            "input[type='file']:first-of-type"
        )
        if resume_input and resume_path and os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            await page.wait_for_timeout(1000)
            filled_fields.append(f"resume={os.path.basename(resume_path)}")

        # --- LinkedIn URL ---
        linkedin_field = await page.query_selector(
            "input[name*='linkedin'], input[placeholder*='linkedin' i], "
            "input[aria-label*='LinkedIn' i], "
            "input[name='urls[LinkedIn]'], input[name*='urls']"
        )
        if linkedin_field and personal.get("linkedin"):
            linkedin_url = personal["linkedin"]
            if not linkedin_url.startswith("http"):
                linkedin_url = f"https://{linkedin_url}"
            await linkedin_field.fill(linkedin_url)
            filled_fields.append("linkedin=filled")

        # --- GitHub URL ---
        github_field = await page.query_selector(
            "input[name*='github'], input[placeholder*='github' i], "
            "input[name='urls[GitHub]'], input[name*='portfolio']"
        )
        if github_field and personal.get("github"):
            github_url = personal["github"]
            if not github_url.startswith("http"):
                github_url = f"https://{github_url}"
            await github_field.fill(github_url)
            filled_fields.append("github=filled")

        # --- Additional URLs (generic URL fields) ---
        url_fields = await page.query_selector_all(
            "input[name*='urls'][placeholder*='url' i], "
            "input[placeholder='https://']"
        )
        for url_field in url_fields:
            current_val = await url_field.input_value()
            if not current_val and personal.get("github"):
                github_url = personal["github"]
                if not github_url.startswith("http"):
                    github_url = f"https://{github_url}"
                await url_field.fill(github_url)
                break

        # --- Additional Information / Cover Letter textarea ---
        additional_field = await page.query_selector(
            "textarea[name*='comments'], textarea[name*='additional'], "
            "textarea[placeholder*='Additional' i], textarea[name*='cover']"
        )
        if additional_field:
            current = await additional_field.input_value()
            if not current:
                summary = profile.get("summary", "")
                if summary:
                    await additional_field.fill(summary)
                    filled_fields.append("additional_info=filled")

        # --- Handle custom question cards ---
        await _fill_lever_custom_questions(page, profile, api_key, filled_fields)

        print(f"      ✅ Filled {len(filled_fields)} fields: {', '.join(filled_fields)}")

        blocked = await pre_submit_check(page)
        if blocked:
            return blocked

        # --- Submit or Dry Run ---
        if dry_run:
            print(f"      🏃 DRY RUN — form filled but NOT submitted")
            return "dry_run_success"

        submit_btn = await page.query_selector(
            "button[type='submit'], button:has-text('Submit application'), "
            "button:has-text('Submit'), input[type='submit']"
        )
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

            # Check for success
            success = await page.query_selector(
                "[class*='success'], [class*='confirmation'], "
                "h2:has-text('Thank'), h3:has-text('Thank'), "
                "h2:has-text('Application submitted'), "
                "div:has-text('Your application has been submitted')"
            )
            if success:
                return "applied"

            # Check for errors
            error = await page.query_selector("[class*='error'], [class*='invalid']")
            if error:
                error_text = await error.inner_text()
                print(f"      ❌ Form error: {error_text[:100]}")
                return "failed_form_error"

            # No clear success/error — don't claim it was submitted
            return "unconfirmed"
        else:
            return "skipped_no_submit_button"

    except PlaywrightTimeout:
        return "failed_timeout"
    except Exception as e:
        print(f"      ❌ Lever error: {e}")
        return f"failed_{str(e)[:50]}"


async def _fill_lever_custom_questions(page: Page, profile: dict, api_key: str,
                                        filled_fields: list):
    """Fill custom question cards in Lever forms."""
    # Lever wraps custom questions in card sections
    cards = await page.query_selector_all(
        ".application-question, .custom-question, "
        "[class*='question-card'], .postings-form__section"
    )

    for card in cards:
        try:
            label = await card.query_selector("label, .field-label, .question-label, legend")
            if not label:
                continue
            question_text = await label.inner_text()
            question_text = question_text.strip()
            if not question_text or len(question_text) < 5:
                continue

            # Skip standard fields
            standard = ["name", "email", "phone", "resume", "linkedin", "company"]
            if any(s in question_text.lower() for s in standard):
                continue

            # Try text input / textarea
            text_input = await card.query_selector(
                "textarea, input[type='text'], "
                "input:not([type='file']):not([type='hidden'])"
                ":not([type='submit']):not([type='checkbox']):not([type='radio'])"
            )
            if text_input:
                current = await text_input.input_value()
                if not current:
                    answer = answer_question(question_text, profile, api_key)
                    if answer is None:
                        continue
                    if answer:
                        await text_input.fill(answer)
                        filled_fields.append(f"q:{question_text[:30]}...")
                continue

            # Try select dropdown
            select = await card.query_selector("select")
            if select:
                current_val = await select.input_value()
                if not current_val:
                    options = await select.query_selector_all("option")
                    if len(options) > 1:
                        answer = answer_question(question_text, profile, api_key)
                        if answer:
                            for opt in options[1:]:
                                opt_text = await opt.inner_text()
                                if answer.lower() in opt_text.lower() or opt_text.lower() in answer.lower():
                                    val = await opt.get_attribute("value")
                                    if val:
                                        await select.select_option(value=val)
                                        filled_fields.append(f"select:{question_text[:20]}")
                                        break
                            else:
                                # No answer matched a real option — leave it
                                # unanswered rather than guessing.
                                filled_fields.append(f"select:{question_text[:20]}=UNANSWERED")

        except Exception:
            continue
