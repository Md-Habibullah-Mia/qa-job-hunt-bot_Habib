"""
linkedin_scraper.py

Scrapes LinkedIn Jobs for QA/SDET positions.

Categories:
    - sponsorship_worldwide
    - bangladesh_remote
    - remote_worldwide

Uses Playwright for browser automation.
"""

import asyncio
import json
import os
import sys
import random
from datetime import datetime
from urllib.parse import quote

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeout,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "config.json",
)


def load_config():
    """Load application configuration."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------------------
# LinkedIn Search Configurations
# -------------------------------------------------------------------

SEARCH_CONFIGS = {
    "sponsorship_worldwide": [
        {
            "keywords": "QA Automation Engineer visa sponsorship",
            "location": "United States",
            "remote": False,
        },
        {
            "keywords": "SDET visa sponsorship relocation",
            "location": "United Kingdom",
            "remote": False,
        },
        {
            "keywords": "Test Automation Engineer sponsorship",
            "location": "Germany",
            "remote": False,
        },
        {
            "keywords": "QA Engineer sponsorship",
            "location": "Canada",
            "remote": False,
        },
        {
            "keywords": "QA Automation Engineer relocation",
            "location": "Australia",
            "remote": False,
        },
        {
            "keywords": "Software Test Engineer visa",
            "location": "Netherlands",
            "remote": False,
        },
        {
            "keywords": "QA Engineer sponsorship",
            "location": "Singapore",
            "remote": False,
        },
        {
            "keywords": "Test Automation Engineer visa sponsorship",
            "location": "Dubai",
            "remote": False,
        },
    ],

    "bangladesh_remote": [
        {
            "keywords": "QA Automation Engineer remote",
            "location": "Bangladesh",
            "remote": True,
        },
        {
            "keywords": "SDET remote",
            "location": "Bangladesh",
            "remote": True,
        },
        {
            "keywords": "Test Automation Engineer remote",
            "location": "Bangladesh",
            "remote": True,
        },
        {
            "keywords": "QA Engineer remote",
            "location": "Bangladesh",
            "remote": True,
        },
        {
            "keywords": "Software QA Engineer remote",
            "location": "Bangladesh",
            "remote": True,
        },
        {
            "keywords": "QA Automation remote work from home",
            "location": "Bangladesh",
            "remote": True,
        },
    ],

    "remote_worldwide": [
        {
            "keywords": "QA Automation Engineer remote",
            "location": "",
            "remote": True,
        },
        {
            "keywords": "SDET remote worldwide",
            "location": "",
            "remote": True,
        },
        {
            "keywords": "Test Automation Engineer remote",
            "location": "",
            "remote": True,
        },
        {
            "keywords": "Software Test Engineer remote",
            "location": "",
            "remote": True,
        },
        {
            "keywords": "QA Lead remote",
            "location": "",
            "remote": True,
        },
        {
            "keywords": "Senior QA Engineer remote",
            "location": "",
            "remote": True,
        },
    ],
}


# -------------------------------------------------------------------
# Main LinkedIn scraper
# -------------------------------------------------------------------

async def scrape_linkedin_jobs(
    category: str,
    max_jobs: int = 50,
) -> list:
    """
    Scrape LinkedIn jobs for a given category.

    category:
        sponsorship_worldwide
        bangladesh_remote
        remote_worldwide
    """

    config = load_config()
    jobs = []

    searches = SEARCH_CONFIGS.get(category, [])

    if not searches:
        print(f"⚠️ No LinkedIn search configuration for: {category}")
        return []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={
                "width": 1280,
                "height": 800,
            },
        )

        # -----------------------------------------------------------
        # Optional LinkedIn login
        # -----------------------------------------------------------

        linkedin_config = config.get("linkedin", {})

        li_email = linkedin_config.get("email", "")
        li_pass = linkedin_config.get("password", "")

        if (
            li_email
            and li_pass
            and li_email != "your.linkedin@email.com"
        ):
            await linkedin_login(
                context,
                li_email,
                li_pass,
            )

        # -----------------------------------------------------------
        # Execute searches
        # -----------------------------------------------------------

        # Keep the existing safety limit.
        for search in searches[:4]:

            if len(jobs) >= max_jobs:
                break

            search_jobs = await search_linkedin(
                context,
                search,
                category,
                max_jobs=min(20, max_jobs - len(jobs)),
            )

            jobs.extend(search_jobs)

            await asyncio.sleep(
                random.uniform(3, 7)
            )

        await browser.close()

    # ---------------------------------------------------------------
    # Deduplicate
    # ---------------------------------------------------------------

    seen = set()
    unique_jobs = []

    for job in jobs:

        url = job.get("url", "").strip()

        if url and url not in seen:
            seen.add(url)
            unique_jobs.append(job)

    return unique_jobs[:max_jobs]


# -------------------------------------------------------------------
# LinkedIn login
# -------------------------------------------------------------------

async def linkedin_login(
    context,
    email: str,
    password: str,
):
    """Login to LinkedIn if credentials are available."""

    page = await context.new_page()

    try:

        await page.goto(
            "https://www.linkedin.com/login",
            wait_until="networkidle",
            timeout=30000,
        )

        await page.fill(
            "#username",
            email,
        )

        await page.fill(
            "#password",
            password,
        )

        await page.click(
            '[type="submit"]'
        )

        await page.wait_for_timeout(3000)

        print("   ✅ LinkedIn login successful")

    except Exception as e:

        print(
            f"   ⚠️ LinkedIn login failed: {e}"
            " - continuing without login"
        )

    finally:

        await page.close()


# -------------------------------------------------------------------
# LinkedIn search
# -------------------------------------------------------------------

async def search_linkedin(
    context,
    search_config: dict,
    category: str,
    max_jobs: int = 20,
) -> list:
    """Search LinkedIn and extract job listings."""

    page = await context.new_page()
    jobs = []

    try:

        keywords = quote(
            search_config.get("keywords", "")
        )

        location = quote(
            search_config.get("location", "")
        )

        remote_filter = (
            "&f_WT=2"
            if search_config.get("remote")
            else ""
        )

        # Last 24 hours
        date_filter = "&f_TPR=r86400"

        if location:

            url = (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}"
                f"&location={location}"
                f"{remote_filter}"
                f"{date_filter}"
                "&sortBy=DD"
            )

        else:

            url = (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}"
                f"{remote_filter}"
                f"{date_filter}"
                "&sortBy=DD"
            )

        print(
            f"   🔍 Searching: "
            f"{search_config.get('keywords', '')} "
            f"in "
            f"{search_config.get('location') or 'worldwide'}"
        )

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await page.wait_for_timeout(2000)

        # -----------------------------------------------------------
        # Scroll
        # -----------------------------------------------------------

        for _ in range(3):

            await page.keyboard.press("End")

            await page.wait_for_timeout(1500)

        # -----------------------------------------------------------
        # Job cards
        # -----------------------------------------------------------

        job_cards = await page.query_selector_all(
            ".job-search-card, "
            ".jobs-search__results-list li, "
            ".base-card"
        )

        for card in job_cards[:max_jobs]:

            try:

                job = await extract_job_card(
                    card,
                    category,
                )

                if job:
                    jobs.append(job)

            except Exception:
                continue

        print(
            f"   ✅ Found {len(jobs)} jobs"
        )

    except PlaywrightTimeout:

        print(
            "   ⚠️ Timeout on LinkedIn search"
        )

    except Exception as e:

        print(
            f"   ⚠️ LinkedIn search error: {e}"
        )

    finally:

        await page.close()

    return jobs


# -------------------------------------------------------------------
# Extract job card
# -------------------------------------------------------------------

async def extract_job_card(
    card,
    category: str,
) -> dict:
    """Extract data from a LinkedIn job card."""

    try:

        title_el = await card.query_selector(
            ".base-search-card__title, "
            "h3.job-search-card__title"
        )

        company_el = await card.query_selector(
            ".base-search-card__subtitle, "
            "h4.base-search-card__subtitle"
        )

        location_el = await card.query_selector(
            ".job-search-card__location, "
            ".base-search-card__metadata span"
        )

        link_el = await card.query_selector(
            "a.base-card__full-link, "
            "a[href*='/jobs/view/']"
        )

        date_el = await card.query_selector(
            "time"
        )

        title = (
            await title_el.inner_text()
            if title_el
            else ""
        )

        company = (
            await company_el.inner_text()
            if company_el
            else ""
        )

        location = (
            await location_el.inner_text()
            if location_el
            else ""
        )

        url = (
            await link_el.get_attribute("href")
            if link_el
            else ""
        )

        date_posted = (
            await date_el.get_attribute("datetime")
            if date_el
            else str(datetime.now().date())
        )

        if not title or not url:
            return None

        # Remove LinkedIn tracking parameters.
        if "?" in url:
            url = url.split("?")[0]

        return {
            "id": url.rstrip("/").split("/")[-1],

            "title": title.strip(),

            "company": company.strip(),

            "location": location.strip(),

            "url": url.strip(),

            "source": "linkedin",

            "category": category,

            "date_posted": date_posted,

            "scraped_at": datetime.now().isoformat(),

            "description": "",

            "type": _get_type_label(category),

            "easy_apply": False,
        }

    except Exception:

        return None


# -------------------------------------------------------------------
# Category labels
# -------------------------------------------------------------------

def _get_type_label(category: str) -> str:

    labels = {
        "sponsorship_worldwide":
            "Outside Bangladesh (Sponsorship)",

        "bangladesh_remote":
            "Bangladesh Remote",

        "remote_worldwide":
            "Remote Worldwide",
    }

    return labels.get(
        category,
        category,
    )


# -------------------------------------------------------------------
# Fetch LinkedIn job description
# -------------------------------------------------------------------

async def fetch_job_description(
    url: str,
) -> str:
    """Fetch full job description from LinkedIn."""

    if not url:
        return ""

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=20000,
            )

            await page.wait_for_timeout(2000)

            desc_el = await page.query_selector(
                ".description__text, "
                ".show-more-less-html__markup"
            )

            if desc_el:

                return await desc_el.inner_text()

        except Exception:

            pass

        finally:

            await browser.close()

    return ""


# -------------------------------------------------------------------
# Synchronous wrapper
# -------------------------------------------------------------------

def scrape_all_categories(
    max_jobs: int = 50,
) -> dict:
    """
    Scrape all LinkedIn categories.

    Returns:
        {
            "sponsorship_worldwide": [],
            "bangladesh_remote": [],
            "remote_worldwide": []
        }
    """

    results = {}

    for category in SEARCH_CONFIGS.keys():

        print(
            f"\n📋 LinkedIn category: {category}"
        )

        jobs = asyncio.run(
            scrape_linkedin_jobs(
                category,
                max_jobs,
            )
        )

        results[category] = jobs

        print(
            f"   Total: {len(jobs)} unique jobs found"
        )

    return results