"""
linkedin_scraper.py
Scrapes LinkedIn Jobs for QA/SDET positions.
Handles 3 categories: sponsorship, India remote, worldwide remote.
Uses Playwright for browser automation.
"""

import asyncio
import json
import os
import sys
import time
import random
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.remote_scraper import classify_remote_scope

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


# --- LinkedIn Search Configurations for QA Engineer ---

SEARCH_CONFIGS = {
    "sponsorship_worldwide": [
        {"keywords": "QA Automation Engineer visa sponsorship", "location": "United States", "remote": False},
        {"keywords": "SDET visa sponsorship relocation", "location": "United Kingdom", "remote": False},
        {"keywords": "Test Automation Engineer sponsorship", "location": "Germany", "remote": False},
        {"keywords": "QA Engineer sponsorship", "location": "Canada", "remote": False},
        {"keywords": "QA Automation Engineer relocation", "location": "Australia", "remote": False},
        {"keywords": "Software Test Engineer visa", "location": "Netherlands", "remote": False},
        {"keywords": "QA Engineer sponsorship", "location": "Singapore", "remote": False},
        {"keywords": "Test Automation Engineer visa sponsorship", "location": "Dubai", "remote": False},
    ],
    "india_remote": [
        {"keywords": "QA Automation Engineer remote", "location": "India", "remote": True},
        {"keywords": "SDET remote work from home", "location": "India", "remote": True},
        {"keywords": "Test Automation Engineer remote India", "location": "India", "remote": True},
        {"keywords": "QA Engineer remote", "location": "Bangalore, Karnataka, India", "remote": True},
    ],
    "remote_worldwide": [
        {"keywords": "QA Automation Engineer", "location": "", "remote": True},
        {"keywords": "SDET remote worldwide", "location": "", "remote": True},
        {"keywords": "Test Automation Engineer remote", "location": "", "remote": True},
        {"keywords": "Software Test Engineer remote", "location": "", "remote": True},
        {"keywords": "QA Lead remote", "location": "", "remote": True},
    ]
}


async def scrape_linkedin_jobs(category: str, max_jobs: int = 50) -> list:
    """
    Scrape LinkedIn jobs for a given category.
    category: 'sponsorship_worldwide' | 'india_remote' | 'remote_worldwide'
    """
    config = load_config()
    jobs = []
    searches = SEARCH_CONFIGS.get(category, [])

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        # Try to login if credentials available
        li_email = config["linkedin"].get("email", "")
        li_pass = config["linkedin"].get("password", "")

        if li_email and li_pass and li_email != "your.linkedin@email.com":
            await linkedin_login(context, li_email, li_pass)

        for search in searches[:3]:  # Limit searches per run
            if len(jobs) >= max_jobs:
                break

            search_jobs = await search_linkedin(context, search, category, max_jobs=20)
            jobs.extend(search_jobs)
            await asyncio.sleep(random.uniform(3, 7))  # Polite delay

        await browser.close()

    # Deduplicate by job URL
    seen = set()
    unique_jobs = []
    for job in jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_jobs.append(job)

    return unique_jobs


async def linkedin_login(context, email: str, password: str):
    """Login to LinkedIn."""
    page = await context.new_page()
    try:
        await page.goto("https://www.linkedin.com/login", wait_until="networkidle")
        await page.fill("#username", email)
        await page.fill("#password", password)
        await page.click('[type="submit"]')
        await page.wait_for_timeout(3000)
        print("✅ LinkedIn login successful")
    except Exception as e:
        print(f"⚠️ LinkedIn login failed: {e} - continuing without login")
    finally:
        await page.close()


async def search_linkedin(context, search_config: dict, category: str, max_jobs: int = 20) -> list:
    """Search LinkedIn and extract job listings."""
    page = await context.new_page()
    jobs = []

    try:
        # Build LinkedIn jobs search URL (works without login too)
        keywords = search_config["keywords"].replace(" ", "%20")
        location = search_config.get("location", "").replace(" ", "%20").replace(",", "%2C")
        remote_filter = "&f_WT=2" if search_config.get("remote") else ""
        date_filter = "&f_TPR=r86400"  # Last 24 hours - change r86400 to r604800 for 7 days

        if location:
            url = f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location={location}{remote_filter}{date_filter}&sortBy=DD"
        else:
            url = f"https://www.linkedin.com/jobs/search/?keywords={keywords}{remote_filter}{date_filter}&sortBy=DD"

        print(f"   🔍 Searching: {search_config['keywords']} in {search_config.get('location', 'worldwide')}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Scroll to load more jobs
        for _ in range(3):
            await page.keyboard.press("End")
            await page.wait_for_timeout(1500)

        # Extract job cards
        job_cards = await page.query_selector_all(".job-search-card, .jobs-search__results-list li, .base-card")

        for card in job_cards[:max_jobs]:
            try:
                job = await extract_job_card(card, category)
                if job:
                    jobs.append(job)
            except Exception:
                continue

        print(f"   ✅ Found {len(jobs)} jobs")

    except PlaywrightTimeout:
        print(f"   ⚠️ Timeout on LinkedIn search")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
    finally:
        await page.close()

    return jobs


async def extract_job_card(card, category: str) -> dict:
    """Extract data from a LinkedIn job card."""
    try:
        title_el = await card.query_selector(".base-search-card__title, h3.job-search-card__title")
        company_el = await card.query_selector(".base-search-card__subtitle, h4.base-search-card__subtitle")
        location_el = await card.query_selector(".job-search-card__location, .base-search-card__metadata span")
        link_el = await card.query_selector("a.base-card__full-link, a[href*='/jobs/view/']")
        date_el = await card.query_selector("time")

        title = await title_el.inner_text() if title_el else ""
        company = await company_el.inner_text() if company_el else ""
        location = await location_el.inner_text() if location_el else ""
        url = await link_el.get_attribute("href") if link_el else ""
        date_posted = await date_el.get_attribute("datetime") if date_el else str(datetime.now().date())

        if not title or not url:
            return None

        # Clean URL (remove tracking params)
        if "?" in url:
            url = url.split("?")[0]

        final_category = category

        if category == "remote_worldwide":
            # A "remote worldwide" search can still return a listing
            # hard-restricted to one country (e.g. "Remote - USA") —
            # trust the card's own scraped location over the search
            # bucket. sponsorship_worldwide/india_remote searches are
            # intentionally geo-targeted, so leave those as-is.
            scope = classify_remote_scope(location)
            if scope == "country_restricted":
                return None
            final_category = scope

        return {
            "id": url.split("/")[-1] if url else "",
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "url": url.strip(),
            "source": "linkedin",
            "category": final_category,
            "date_posted": date_posted,
            "scraped_at": datetime.now().isoformat(),
            "description": "",  # Will be fetched during matching if needed
            "type": _get_type_label(final_category),
            "easy_apply": False,  # Will check during apply step
        }
    except Exception:
        return None


def _get_type_label(category: str) -> str:
    labels = {
        "sponsorship_worldwide": "Outside India (Sponsorship)",
        "india_remote": "India Remote",
        "remote_worldwide": "Remote Worldwide",
        "bangladesh_remote": "Bangladesh Remote",
    }
    return labels.get(category, category)


async def fetch_job_description(url: str) -> str:
    """Fetch full job description from LinkedIn job page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            desc_el = await page.query_selector(".description__text, .show-more-less-html__markup")
            if desc_el:
                return await desc_el.inner_text()
        except Exception:
            pass
        finally:
            await browser.close()
    return ""


# Synchronous wrapper for use in main.py
def scrape_all_categories(max_jobs: int = 50) -> dict:
    """Scrape all three categories. Returns dict with category -> jobs."""
    results = {}
    for category in SEARCH_CONFIGS.keys():
        print(f"\n📋 Scraping category: {category}")
        jobs = asyncio.run(scrape_linkedin_jobs(category, max_jobs))
        results[category] = jobs
        print(f"   Total: {len(jobs)} unique jobs found")
    return results
