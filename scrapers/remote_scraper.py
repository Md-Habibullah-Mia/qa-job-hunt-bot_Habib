"""
remote_scraper.py

Remote and Bangladesh-focused job scraper for QA/SDET roles.

Categories:
    - remote_worldwide
    - bangladesh_remote
    - sponsorship_worldwide

Sources:
    - Remotive
    - Arbeitnow
    - Jobicy
    - Indeed worldwide RSS
    - LinkedIn public search
    - Bdjobs

Features:
    - QA/SDET keyword filtering
    - Full job-description enrichment
    - Deduplication
    - Multiple search strategies
    - Polite request delays
"""

import json
import os
import sys
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


REQUEST_TIMEOUT = 20
DESCRIPTION_TIMEOUT = 15
REQUEST_DELAY = 1.5


# ─────────────────────────────────────────────────────────────
# QA / SDET filtering
# ─────────────────────────────────────────────────────────────

QA_KEYWORDS = [
    "qa",
    "quality assurance",
    "quality analyst",
    "quality engineer",
    "software tester",
    "software testing",
    "test engineer",
    "test analyst",
    "test automation",
    "automation engineer",
    "automation tester",
    "automation testing",
    "sdet",
    "selenium",
    "playwright",
    "cypress",
    "appium",
    "testng",
    "cucumber",
    "bdd",
    "api testing",
    "api tester",
    "qa analyst",
    "qa lead",
    "test lead",
    "automation lead",
    "software quality",
]


def is_qa_job(title: str, description: str = "") -> bool:
    """
    Return True when title/description appears relevant to QA/SDET.
    """
    text = f"{title} {description}".lower()

    return any(keyword in text for keyword in QA_KEYWORDS)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def clean_html(html_text: str) -> str:
    """
    Convert HTML into clean plain text.
    """
    if not html_text:
        return ""

    try:
        soup = BeautifulSoup(html_text, "lxml")

        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        text = soup.get_text(separator=" ", strip=True)

        text = re.sub(r"\s+", " ", text)

        return text[:5000]

    except Exception:
        return str(html_text)[:5000]


def safe_get(url: str, **kwargs):
    """
    Safe GET wrapper.
    """
    try:
        kwargs.setdefault("headers", HEADERS)
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)

        return requests.get(url, **kwargs)

    except requests.RequestException:
        return None


def make_job_id(source: str, url: str) -> str:
    """
    Generate stable-ish job ID from source and URL.
    """
    return f"{source}_{abs(hash(url)) % 1000000}"


def normalize_url(url: str) -> str:
    """
    Remove unnecessary tracking parameters.
    """
    if not url:
        return ""

    url = url.strip()

    if "?" in url:
        url = url.split("?")[0]

    if "#" in url:
        url = url.split("#")[0]

    return url.rstrip("/")


def build_job(
    *,
    source: str,
    title: str,
    company: str = "",
    location: str = "",
    url: str = "",
    description: str = "",
    category: str = "remote_worldwide",
    job_type: str = "Remote Worldwide",
    date_posted: str = "",
    salary: str = "",
    sponsorship: bool = False,
) -> dict:
    """
    Build a consistent job object used throughout the project.
    """

    url = normalize_url(url)

    return {
        "id": make_job_id(source, url or f"{title}_{company}"),
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "url": url,
        "description": clean_html(description),
        "source": source,
        "category": category,
        "type": job_type,
        "sponsorship": sponsorship,
        "date_posted": date_posted or str(datetime.now().date()),
        "scraped_at": datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# Full description enrichment
# ─────────────────────────────────────────────────────────────

def fetch_full_description(url: str, source: str) -> str:
    """
    Fetch the full job description from the original job page.
    """

    if not url or url == "#":
        return ""

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=DESCRIPTION_TIMEOUT,
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "lxml")

        selectors = {
            "remotive": [
                ".job-description",
                "#job-description",
                ".description",
            ],
            "arbeitnow": [
                ".job-description",
                ".prose",
                "article",
            ],
            "jobicy": [
                ".job-description",
                ".job-description-content",
                "article",
            ],
            "indeed": [
                "#jobDescriptionText",
                ".jobsearch-jobDescriptionText",
            ],
            "linkedin": [
                ".description__text",
                ".show-more-less-html__markup",
            ],
            "bdjobs": [
                ".job-description",
                ".job-details",
                ".details",
                "#job_description",
                "[class*='job-description']",
                "[class*='jobDescription']",
            ],
            "default": [
                ".job-description",
                "#job-description",
                ".description",
                ".job-details",
                ".job-detail",
                ".job-description-content",
                "article",
                "main",
                "[class*='description']",
                "[class*='jobDescription']",
            ],
        }

        source_selectors = (
            selectors.get(source, [])
            + selectors["default"]
        )

        seen_selectors = set()

        for selector in source_selectors:
            if selector in seen_selectors:
                continue

            seen_selectors.add(selector)

            try:
                element = soup.select_one(selector)

                if not element:
                    continue

                text = element.get_text(
                    separator=" ",
                    strip=True,
                )

                text = re.sub(r"\s+", " ", text)

                if len(text) >= 200:
                    return text[:5000]

            except Exception:
                continue

        # Fallback to main content.
        for tag in ["main", "article"]:
            try:
                element = soup.select_one(tag)

                if element:
                    text = element.get_text(
                        separator=" ",
                        strip=True,
                    )

                    text = re.sub(r"\s+", " ", text)

                    if len(text) >= 200:
                        return text[:5000]

            except Exception:
                continue

    except Exception:
        pass

    return ""


def enrich_jobs_with_descriptions(
    jobs: list,
    max_fetch: int = 40,
) -> list:
    """
    Fetch complete descriptions for jobs where the initial
    description is missing or too short.
    """

    needs_fetch = [
        job
        for job in jobs
        if len(job.get("description", "")) < 300
    ]

    print(
        f"   🔍 Fetching full descriptions for "
        f"{min(len(needs_fetch), max_fetch)} jobs..."
    )

    enriched_count = 0

    for job in needs_fetch[:max_fetch]:

        url = job.get("url", "")
        source = job.get("source", "default")

        if not url or url == "#":
            continue

        description = fetch_full_description(
            url,
            source,
        )

        if description:
            job["description"] = description
            job["description_enriched"] = True
            enriched_count += 1

        time.sleep(0.5)

    print(
        f"   ✅ Enriched {enriched_count} job descriptions"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# LinkedIn public search
# ─────────────────────────────────────────────────────────────

def scrape_linkedin_public() -> list:
    """
    Scrape LinkedIn public job search.

    Searches:
        - Worldwide remote
        - Bangladesh remote
        - Sponsorship roles
    """

    jobs = []
    seen = set()

    searches = [
        # Worldwide remote
        (
            "QA Automation Engineer",
            "",
            "remote_worldwide",
            "",
        ),
        (
            "Test Automation Engineer",
            "",
            "remote_worldwide",
            "",
        ),
        (
            "SDET remote",
            "",
            "remote_worldwide",
            "",
        ),
        (
            "QA Engineer remote",
            "",
            "remote_worldwide",
            "",
        ),

        # Bangladesh remote
        (
            "QA Automation Engineer",
            "Bangladesh",
            "bangladesh_remote",
            "106982328",
        ),
        (
            "SDET",
            "Bangladesh",
            "bangladesh_remote",
            "106982328",
        ),
        (
            "Software QA Engineer",
            "Bangladesh",
            "bangladesh_remote",
            "106982328",
        ),
        (
            "Test Automation Engineer",
            "Bangladesh",
            "bangladesh_remote",
            "106982328",
        ),

        # Sponsorship
        (
            "QA Automation Engineer visa sponsorship",
            "United States",
            "sponsorship_worldwide",
            "103644278",
        ),
        (
            "SDET visa sponsorship",
            "United Kingdom",
            "sponsorship_worldwide",
            "101165590",
        ),
        (
            "Test Automation Engineer sponsorship",
            "Germany",
            "sponsorship_worldwide",
            "101282230",
        ),
        (
            "QA Engineer visa sponsorship",
            "Canada",
            "sponsorship_worldwide",
            "101174742",
        ),
        (
            "QA Automation Engineer sponsorship",
            "Australia",
            "sponsorship_worldwide",
            "101452733",
        ),
    ]

    for (
        search_term,
        location,
        category,
        geo_id,
    ) in searches:

        try:
            params = {
                "keywords": search_term,
                "f_WT": "2",
                "f_TPR": "r86400",
                "position": "1",
                "pageNum": "0",
            }

            if geo_id:
                params["geoId"] = geo_id

            query_string = "&".join(
                f"{key}={quote(str(value))}"
                for key, value in params.items()
            )

            url = (
                "https://www.linkedin.com/jobs/search?"
                + query_string
            )

            print(
                f"   🔍 LinkedIn: {search_term}"
                f"{' | ' + location if location else ' | Worldwide'}"
            )

            response = requests.get(
                url,
                headers={
                    **HEADERS,
                    "Referer": "https://www.linkedin.com/jobs/",
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                time.sleep(2)
                continue

            soup = BeautifulSoup(
                response.text,
                "lxml",
            )

            cards = (
                soup.select("div.base-card")
                or soup.select(
                    "li.jobs-search-results__list-item"
                )
                or soup.select(".job-search-card")
                or soup.select("[data-entity-urn]")
            )

            for card in cards[:25]:

                title_el = (
                    card.select_one(
                        "h3.base-search-card__title"
                    )
                    or card.select_one("h3")
                    or card.select_one(
                        ".job-search-card__title"
                    )
                )

                company_el = (
                    card.select_one(
                        "h4.base-search-card__subtitle"
                    )
                    or card.select_one("h4")
                    or card.select_one(
                        ".job-search-card__company-name"
                    )
                )

                location_el = (
                    card.select_one(
                        ".job-search-card__location"
                    )
                    or card.select_one(
                        ".base-search-card__metadata"
                    )
                )

                link_el = card.select_one(
                    "a[href*='/jobs/view/']"
                )

                title = (
                    title_el.get_text(strip=True)
                    if title_el
                    else ""
                )

                company = (
                    company_el.get_text(strip=True)
                    if company_el
                    else ""
                )

                job_location = (
                    location_el.get_text(strip=True)
                    if location_el
                    else location
                )

                job_url = (
                    link_el.get("href", "")
                    if link_el
                    else ""
                )

                job_url = normalize_url(job_url)

                if (
                    not title
                    or not job_url
                    or job_url in seen
                ):
                    continue

                if not is_qa_job(title):
                    continue

                seen.add(job_url)

                job_type = {
                    "bangladesh_remote": "Bangladesh Remote",
                    "sponsorship_worldwide": (
                        "Sponsorship Worldwide"
                    ),
                    "remote_worldwide": (
                        "Remote Worldwide"
                    ),
                }.get(
                    category,
                    "Remote Worldwide",
                )

                jobs.append(
                    build_job(
                        source="linkedin",
                        title=title,
                        company=company,
                        location=job_location,
                        url=job_url,
                        description=(
                            f"{title} at {company}. "
                            f"Location: {job_location}."
                        ),
                        category=category,
                        job_type=job_type,
                    )
                )

            time.sleep(2.5)

        except Exception as error:
            print(
                f"   ⚠️ LinkedIn '{search_term}': "
                f"{error}"
            )

            time.sleep(2)

    print(
        f"   ✅ LinkedIn: {len(jobs)} QA jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Bdjobs
# ─────────────────────────────────────────────────────────────

def scrape_bdjobs() -> list:
    """
    Scrape Bdjobs for Bangladesh QA/SDET opportunities.

    Uses public search pages and multiple QA search terms.
    """

    jobs = []
    seen = set()

    searches = [
        "qa automation engineer",
        "software qa engineer",
        "qa engineer",
        "test automation engineer",
        "software tester",
        "sdet",
        "quality assurance",
        "automation tester",
    ]

    for query in searches:

        try:
            encoded_query = quote(query)

            search_urls = [
                (
                    "https://jobs.bdjobs.com/jobsearch.asp?"
                    f"fcatId=8&txtsearch={encoded_query}"
                ),
                (
                    "https://jobs.bdjobs.com/jobsearch.asp?"
                    f"txtsearch={encoded_query}"
                ),
            ]

            response = None

            for search_url in search_urls:
                response = requests.get(
                    search_url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 200:
                    break

            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.text,
                "lxml",
            )

            # Bdjobs has changed markup over time.
            # Try several common card patterns.
            cards = (
                soup.select(".norm-jobs-wrapper")
                or soup.select(".job-list")
                or soup.select(".job-item")
                or soup.select(
                    "[class*='job-list']"
                )
                or soup.select(
                    "[class*='jobList']"
                )
            )

            # If cards are unavailable, inspect job links.
            if not cards:
                links = soup.select(
                    "a[href*='jobdetails']"
                )

                for link in links[:30]:

                    title = link.get_text(
                        " ",
                        strip=True,
                    )

                    href = link.get(
                        "href",
                        "",
                    )

                    if (
                        not title
                        or not href
                        or not is_qa_job(title)
                    ):
                        continue

                    job_url = urljoin(
                        "https://jobs.bdjobs.com/",
                        href,
                    )

                    job_url = normalize_url(
                        job_url
                    )

                    if job_url in seen:
                        continue

                    seen.add(job_url)

                    jobs.append(
                        build_job(
                            source="bdjobs",
                            title=title,
                            company="",
                            location="Bangladesh",
                            url=job_url,
                            description=(
                                f"{title}. "
                                "Bangladesh job opportunity."
                            ),
                            category="bangladesh_remote",
                            job_type="Bangladesh Remote",
                        )
                    )

                time.sleep(2)
                continue

            for card in cards[:25]:

                title_el = (
                    card.select_one(
                        "h3 a"
                    )
                    or card.select_one(
                        "h2 a"
                    )
                    or card.select_one(
                        "h4 a"
                    )
                    or card.select_one(
                        "a[href*='jobdetails']"
                    )
                    or card.select_one("a")
                )

                company_el = (
                    card.select_one(
                        ".comp-name"
                    )
                    or card.select_one(
                        ".company-name"
                    )
                    or card.select_one(
                        "[class*='company']"
                    )
                )

                location_el = (
                    card.select_one(
                        ".loc"
                    )
                    or card.select_one(
                        ".location"
                    )
                    or card.select_one(
                        "[class*='location']"
                    )
                )

                if not title_el:
                    continue

                title = title_el.get_text(
                    " ",
                    strip=True,
                )

                company = (
                    company_el.get_text(
                        " ",
                        strip=True,
                    )
                    if company_el
                    else ""
                )

                location = (
                    location_el.get_text(
                        " ",
                        strip=True,
                    )
                    if location_el
                    else "Bangladesh"
                )

                href = title_el.get(
                    "href",
                    "",
                )

                if not href:
                    link = card.select_one(
                        "a[href*='jobdetails']"
                    )

                    if link:
                        href = link.get(
                            "href",
                            "",
                        )

                if not href or not title:
                    continue

                job_url = urljoin(
                    "https://jobs.bdjobs.com/",
                    href,
                )

                job_url = normalize_url(
                    job_url
                )

                if (
                    not job_url
                    or job_url in seen
                    or not is_qa_job(title)
                ):
                    continue

                seen.add(job_url)

                jobs.append(
                    build_job(
                        source="bdjobs",
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        description=(
                            f"{title} at {company}. "
                            f"Location: {location}."
                        ),
                        category="bangladesh_remote",
                        job_type="Bangladesh Remote",
                    )
                )

            time.sleep(2)

        except Exception as error:
            print(
                f"   ⚠️ Bdjobs '{query}': "
                f"{error}"
            )

    print(
        f"   ✅ Bdjobs: {len(jobs)} Bangladesh QA jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Remotive
# ─────────────────────────────────────────────────────────────

def scrape_remotive() -> list:
    """
    Scrape Remotive remote jobs.
    """

    jobs = []
    seen = set()

    categories = [
        "software-dev",
        "qa",
        "testing",
        "devops-sysadmin",
    ]

    for category in categories:

        try:
            url = (
                "https://remotive.com/api/remote-jobs"
                f"?category={category}&limit=100"
            )

            response = safe_get(url)

            if not response or response.status_code != 200:
                continue

            data = response.json()

            for job in data.get("jobs", []):

                job_id = str(
                    job.get("id", "")
                )

                if job_id in seen:
                    continue

                title = job.get(
                    "title",
                    "",
                )

                description = clean_html(
                    job.get(
                        "description",
                        "",
                    )
                )

                if not is_qa_job(
                    title,
                    description[:1000],
                ):
                    continue

                job_url = normalize_url(
                    job.get("url", "")
                )

                if not job_url:
                    continue

                seen.add(job_id)

                jobs.append(
                    build_job(
                        source="remotive",
                        title=title,
                        company=job.get(
                            "company_name",
                            "",
                        ),
                        location=job.get(
                            "candidate_required_location",
                            "Worldwide",
                        ),
                        url=job_url,
                        description=description,
                        category="remote_worldwide",
                        job_type="Remote Worldwide",
                        date_posted=job.get(
                            "publication_date",
                            "",
                        ),
                        salary=job.get(
                            "salary",
                            "",
                        ),
                    )
                )

            time.sleep(1)

        except Exception as error:
            print(
                f"   ⚠️ Remotive {category}: "
                f"{error}"
            )

    print(
        f"   ✅ Remotive: {len(jobs)} QA jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Arbeitnow
# ─────────────────────────────────────────────────────────────

def scrape_arbeitnow() -> list:
    """
    Scrape Arbeitnow jobs.

    Visa sponsorship jobs are classified separately.
    """

    jobs = []
    seen = set()

    try:

        for page_number in range(1, 4):

            url = (
                "https://www.arbeitnow.com/"
                "api/job-board-api"
                f"?page={page_number}"
            )

            response = safe_get(url)

            if not response or response.status_code != 200:
                break

            data = response.json().get(
                "data",
                [],
            )

            if not data:
                break

            for job in data:

                title = job.get(
                    "title",
                    "",
                )

                description = clean_html(
                    job.get(
                        "description",
                        "",
                    )
                )

                if not is_qa_job(
                    title,
                    description[:1000],
                ):
                    continue

                job_url = normalize_url(
                    job.get("url", "")
                )

                if (
                    not job_url
                    or job_url in seen
                ):
                    continue

                seen.add(job_url)

                sponsorship = bool(
                    job.get(
                        "visa_sponsorship",
                        False,
                    )
                )

                if sponsorship:
                    category = (
                        "sponsorship_worldwide"
                    )

                    job_type = (
                        "Sponsorship Worldwide"
                    )
                else:
                    category = (
                        "remote_worldwide"
                    )

                    job_type = (
                        "Remote Worldwide"
                    )

                jobs.append(
                    build_job(
                        source="arbeitnow",
                        title=title,
                        company=job.get(
                            "company_name",
                            "",
                        ),
                        location=job.get(
                            "location",
                            "Worldwide",
                        ),
                        url=job_url,
                        description=description,
                        category=category,
                        job_type=job_type,
                        sponsorship=sponsorship,
                    )
                )

            time.sleep(1)

    except Exception as error:
        print(
            f"   ⚠️ Arbeitnow: {error}"
        )

    print(
        f"   ✅ Arbeitnow: {len(jobs)} QA jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Jobicy
# ─────────────────────────────────────────────────────────────

def scrape_jobicy() -> list:
    """
    Scrape Jobicy remote QA jobs.
    """

    jobs = []
    seen = set()

    tags = [
        "qa",
        "testing",
        "quality-assurance",
        "test-automation",
        "sdet",
        "selenium",
        "software-testing",
        "automation",
    ]

    for tag in tags:

        try:

            url = (
                "https://jobicy.com/api/v2/"
                f"remote-jobs?tag={tag}&count=50"
            )

            response = safe_get(url)

            if not response or response.status_code != 200:
                continue

            data = response.json()

            for job in data.get(
                "jobs",
                [],
            ):

                job_id = str(
                    job.get("id", "")
                )

                if job_id in seen:
                    continue

                title = job.get(
                    "jobTitle",
                    "",
                )

                description = clean_html(
                    job.get(
                        "jobDescription",
                        "",
                    )
                )

                if not title:
                    continue

                if not is_qa_job(
                    title,
                    description[:1000],
                ):
                    continue

                job_url = normalize_url(
                    job.get("url", "")
                )

                if not job_url:
                    continue

                seen.add(job_id)

                jobs.append(
                    build_job(
                        source="jobicy",
                        title=title,
                        company=job.get(
                            "companyName",
                            "",
                        ),
                        location=job.get(
                            "jobGeo",
                            "Worldwide",
                        ),
                        url=job_url,
                        description=description,
                        category="remote_worldwide",
                        job_type="Remote Worldwide",
                        date_posted=job.get(
                            "pubDate",
                            "",
                        ),
                    )
                )

            time.sleep(1)

        except Exception as error:
            print(
                f"   ⚠️ Jobicy {tag}: "
                f"{error}"
            )

    print(
        f"   ✅ Jobicy: {len(jobs)} QA jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Indeed Worldwide RSS
# ─────────────────────────────────────────────────────────────

def scrape_indeed_worldwide_rss() -> list:
    """
    Scrape selected worldwide Indeed RSS feeds.

    Focus:
        - US
        - UK
        - Canada
        - Australia
        - Germany
    """

    jobs = []
    seen = set()

    searches = [
        (
            "qa+automation+engineer+visa+sponsorship",
            "US",
            "sponsorship_worldwide",
        ),
        (
            "sdet+visa+sponsorship",
            "US",
            "sponsorship_worldwide",
        ),
        (
            "qa+automation+engineer+remote",
            "US",
            "remote_worldwide",
        ),
        (
            "test+automation+engineer+remote",
            "GB",
            "remote_worldwide",
        ),
        (
            "sdet+remote",
            "GB",
            "remote_worldwide",
        ),
        (
            "qa+automation+engineer+remote",
            "CA",
            "remote_worldwide",
        ),
        (
            "test+automation+engineer+remote",
            "AU",
            "remote_worldwide",
        ),
        (
            "qa+automation+engineer+remote",
            "DE",
            "remote_worldwide",
        ),
    ]

    domains = {
        "US": "www.indeed.com",
        "GB": "uk.indeed.com",
        "CA": "ca.indeed.com",
        "AU": "au.indeed.com",
        "DE": "de.indeed.com",
    }

    country_names = {
        "US": "United States",
        "GB": "United Kingdom",
        "CA": "Canada",
        "AU": "Australia",
        "DE": "Germany",
    }

    for (
        query,
        country,
        category,
    ) in searches:

        try:

            domain = domains.get(
                country,
                "www.indeed.com",
            )

            url = (
                f"https://{domain}/rss"
                f"?q={query}"
                "&jt=fulltime"
                "&sort=date"
            )

            response = requests.get(
                url,
                headers={
                    **HEADERS,
                    "Accept": (
                        "application/rss+xml,*/*"
                    ),
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                continue

            root = ET.fromstring(
                response.content
            )

            items = root.findall(".//item")

            for item in items[:15]:

                title = (
                    item.findtext(
                        "title",
                        "",
                    )
                    .strip()
                )

                link = (
                    item.findtext(
                        "link",
                        "",
                    )
                    .strip()
                )

                description = clean_html(
                    item.findtext(
                        "description",
                        "",
                    )
                )

                if (
                    not title
                    or not link
                    or link in seen
                    or not is_qa_job(
                        title,
                        description,
                    )
                ):
                    continue

                seen.add(link)

                company_element = item.find(
                    "{http://www.indeed.com/about/feed}"
                    "company"
                )

                company = (
                    company_element.text.strip()
                    if company_element is not None
                    and company_element.text
                    else ""
                )

                country_name = country_names.get(
                    country,
                    country,
                )

                if category == (
                    "sponsorship_worldwide"
                ):
                    job_type = (
                        "Sponsorship Worldwide"
                    )
                else:
                    job_type = (
                        "Remote Worldwide"
                    )

                jobs.append(
                    build_job(
                        source="indeed",
                        title=title,
                        company=company,
                        location=(
                            f"{country_name} (Remote)"
                        ),
                        url=link,
                        description=description,
                        category=category,
                        job_type=job_type,
                        date_posted=item.findtext(
                            "pubDate",
                            str(datetime.now().date()),
                        ),
                        sponsorship=(
                            category
                            == "sponsorship_worldwide"
                        ),
                    )
                )

            time.sleep(1.5)

        except Exception as error:
            print(
                f"   ⚠️ Indeed {country}: "
                f"{error}"
            )

    print(
        f"   ✅ Indeed Worldwide: "
        f"{len(jobs)} jobs"
    )

    return jobs


# ─────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────

def deduplicate(jobs: list) -> list:
    """
    Remove duplicate jobs using URL first and ID second.
    """

    seen = set()
    unique_jobs = []

    for job in jobs:

        url = normalize_url(
            job.get("url", "")
        )

        key = url or job.get(
            "id",
            "",
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        unique_jobs.append(job)

    return unique_jobs


# ─────────────────────────────────────────────────────────────
# Main scraper
# ─────────────────────────────────────────────────────────────

def scrape_all_remote_boards() -> dict:
    """
    Run all remote/Bangladesh/sponsorship scrapers.

    Returns:

        {
            "remote_worldwide": [...],
            "bangladesh_remote": [...],
            "sponsorship_worldwide": [...]
        }
    """

    print(
        "\n🌐 Scraping remote and Bangladesh job boards..."
    )

    results = {
        "remote_worldwide": [],
        "bangladesh_remote": [],
        "sponsorship_worldwide": [],
    }

    # ─────────────────────────────────────────
    # Worldwide remote sources
    # ─────────────────────────────────────────

    print(
        "\n  📍 Remotive..."
    )

    for job in scrape_remotive():
        category = job.get(
            "category",
            "remote_worldwide",
        )

        if category not in results:
            category = "remote_worldwide"

        results[category].append(job)

    print(
        "  📍 Arbeitnow..."
    )

    for job in scrape_arbeitnow():
        category = job.get(
            "category",
            "remote_worldwide",
        )

        if category not in results:
            category = "remote_worldwide"

        results[category].append(job)

    print(
        "  📍 Jobicy..."
    )

    for job in scrape_jobicy():
        results["remote_worldwide"].append(
            job
        )

    print(
        "  📍 Indeed Worldwide..."
    )

    for job in scrape_indeed_worldwide_rss():

        category = job.get(
            "category",
            "remote_worldwide",
        )

        if category not in results:
            category = "remote_worldwide"

        results[category].append(job)

    # ─────────────────────────────────────────
    # LinkedIn
    # ─────────────────────────────────────────

    print(
        "\n  📍 LinkedIn public search..."
    )

    for job in scrape_linkedin_public():

        category = job.get(
            "category",
            "remote_worldwide",
        )

        if category not in results:
            category = "remote_worldwide"

        results[category].append(job)

    # ─────────────────────────────────────────
    # Bangladesh
    # ─────────────────────────────────────────

    print(
        "\n  📍 Bdjobs..."
    )

    results["bangladesh_remote"].extend(
        scrape_bdjobs()
    )

    # ─────────────────────────────────────────
    # Deduplicate
    # ─────────────────────────────────────────

    print(
        "\n  🧹 Deduplicating jobs..."
    )

    for category in results:

        results[category] = deduplicate(
            results[category]
        )

    # ─────────────────────────────────────────
    # Description enrichment
    # ─────────────────────────────────────────

    print(
        "\n  🔍 Enriching job descriptions..."
    )

    for category in results:

        if not results[category]:
            continue

        results[category] = (
            enrich_jobs_with_descriptions(
                results[category],
                max_fetch=30,
            )
        )

    # ─────────────────────────────────────────
    # Final statistics
    # ─────────────────────────────────────────

    print("\n📊 Final scraper statistics:")

    for category, jobs in results.items():

        print(
            f"   {category}: {len(jobs)} jobs"
        )

    total = sum(
        len(jobs)
        for jobs in results.values()
    )

    print(
        f"\n🎯 Total: {total} jobs ready "
        "for AI matching"
    )

    return results


# ─────────────────────────────────────────────────────────────
# Direct execution
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    results = scrape_all_remote_boards()

    print("\n✅ Scraping completed.")

    for category, jobs in results.items():
        print(
            f"{category}: {len(jobs)} jobs"
        )