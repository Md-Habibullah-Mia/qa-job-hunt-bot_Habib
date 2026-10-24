"""
submit_guard.py
Checks shared by the ATS form fillers, so a form is only submitted when it is
complete and the bot can tell whether the submission actually went through.
"""

from playwright.async_api import Page

CAPTCHA_SELECTOR = (
    "iframe[src*='hcaptcha'], iframe[src*='recaptcha'], "
    "iframe[title*='captcha' i], .h-captcha, .g-recaptcha"
)

REQUIRED_SELECTOR = (
    "input[required]:not([type='hidden']):not([type='submit']), "
    "textarea[required], select[required], "
    "input[aria-required='true'], textarea[aria-required='true'], "
    "select[aria-required='true']"
)


async def pre_submit_check(page: Page) -> str | None:
    """
    Return a skip status when the form must not be submitted, else None.
    Runs before the dry-run return too, so a dry run tells you whether a
    live run would really have been able to submit.
    """
    captcha = await page.query_selector(CAPTCHA_SELECTOR)
    if captcha and await captcha.is_visible():
        print("      🤖 Captcha on the form — needs manual apply")
        return "skipped_captcha"

    empty = []
    for field in await page.query_selector_all(REQUIRED_SELECTOR):
        try:
            if not await field.is_visible():
                continue
            input_type = (await field.get_attribute("type") or "").lower()
            if input_type in ("checkbox", "radio"):
                name = await field.get_attribute("name")
                if name and await page.query_selector(f"input[name='{name}']:checked"):
                    continue
                if not name and await field.is_checked():
                    continue
            elif input_type == "file":
                if await field.evaluate("el => el.files.length > 0"):
                    continue
            elif (await field.input_value()).strip():
                continue
            label = (await field.get_attribute("name")
                     or await field.get_attribute("id")
                     or await field.get_attribute("aria-label") or "?")
            empty.append(label)
        except Exception:
            continue

    if empty:
        print(f"      ✋ {len(empty)} required field(s) unanswered: {', '.join(empty[:4])}")
        return "skipped_manual_needed"
    return None
