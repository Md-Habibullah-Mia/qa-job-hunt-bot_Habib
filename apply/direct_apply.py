"""
direct_apply.py
Orchestrates direct applications to jobs that don't require login/account.
Supports Greenhouse and Lever ATS platforms.
Works on GitHub Actions (headless, no login needed).
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apply.auto_apply import load_applied_jobs, save_applied_job
from apply.ats_detect import resolve_apply_url, detect_ats_type
from apply.ats_greenhouse import apply_greenhouse
from apply.ats_lever import apply_lever

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "resume_profile.json")


async def direct_apply_batch(jobs: list, resume_path: str,
                              max_applications: int = 10,
                              min_score: int = 70,
                              dry_run: bool = True) -> list:
    """
    Auto-apply to jobs via direct ATS forms (no login required).
    Supports Greenhouse and Lever.
    """
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    api_key = config.get("api_keys", {}).get("gemini_api_key", "")
    applied_jobs = load_applied_jobs()
    # Older records were keyed by unstable IDs, so match on URL as well
    applied_urls = {rec.get("url") for rec in applied_jobs.values() if rec.get("url")}
    results = []
    apply_count = 0

    # Filter eligible jobs: non-LinkedIn, high score, APPLY recommendation, not already applied
    eligible = [
        j for j in jobs
        if j.get("source") != "linkedin"
        and j.get("recommendation") == "APPLY"
        and j.get("match_score", 0) >= min_score
        and j.get("id", "") not in applied_jobs
        and j.get("url", "") not in applied_urls
    ]

    if not eligible:
        print("   No eligible jobs for direct apply")
        return []

    mode_label = "DRY RUN" if dry_run else "LIVE"
    print(f"🎯 Direct Apply ({mode_label}): {min(len(eligible), max_applications)} jobs to process...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )

        page = await context.new_page()

        for job in eligible[:max_applications]:
            if apply_count >= max_applications:
                break

            job_id = job.get("id", "")
            job_url = job.get("url", "")
            source = job.get("source", "")
            score = job.get("match_score", 0)

            print(f"\n   📋 [{score}%] {job['title']} at {job['company']} ({source})")

            # Step 1: Resolve the actual ATS application URL
            print(f"      🔍 Resolving apply URL...")
            ats_url = await resolve_apply_url(page, job_url)

            if not ats_url:
                print(f"      ⏭️ No ATS form found — skipping")
                save_applied_job(job_id, job, "skipped_no_ats", method="direct")
                results.append({"job": job, "status": "skipped_no_ats", "ats_url": ""})
                continue

            # Step 2: Detect ATS type
            ats_type = detect_ats_type(ats_url)
            print(f"      🏢 ATS: {ats_type} → {ats_url[:80]}...")

            if ats_type == "unknown":
                print(f"      ⏭️ Unknown ATS — skipping")
                save_applied_job(job_id, job, "skipped_unknown_ats", method="direct")
                results.append({"job": job, "status": "skipped_unknown_ats", "ats_url": ats_url})
                continue

            # Step 3: Fill and submit the form — the job's own cover note
            # replaces the generic summary in "additional information" boxes
            job_profile = {**profile, "summary": job.get("cover_note") or profile.get("summary", "")}
            status = "failed"
            try:
                if ats_type == "greenhouse":
                    status = await apply_greenhouse(
                        page, ats_url, job_profile, resume_path,
                        api_key=api_key, dry_run=dry_run
                    )
                elif ats_type == "lever":
                    status = await apply_lever(
                        page, ats_url, job_profile, resume_path,
                        api_key=api_key, dry_run=dry_run
                    )
            except Exception as e:
                status = f"failed_{str(e)[:50]}"
                print(f"      ❌ Error: {e}")

            # Step 4: Save result
            method = f"direct_{ats_type}"
            save_applied_job(job_id, job, status, method=method)

            result = {
                "job": job,
                "status": status,
                "ats_type": ats_type,
                "ats_url": ats_url,
                "applied_at": datetime.now().isoformat(),
            }
            results.append(result)

            # "unconfirmed" was probably submitted, so it counts toward the cap
            if status in ("applied", "unconfirmed", "dry_run_success"):
                apply_count += 1
                emoji = {"applied": "✅", "unconfirmed": "❔"}.get(status, "🏃")
                print(f"      {emoji} {status}")
            else:
                print(f"      ⚠️ Status: {status}")

            # Human-like delay between applications
            await asyncio.sleep(5)

        await browser.close()

    applied = len([r for r in results if r["status"] == "applied"])
    dry_runs = len([r for r in results if r["status"] == "dry_run_success"])
    skipped = len([r for r in results if "skipped" in r["status"]])
    failed = len([r for r in results if "failed" in r["status"]])

    print(f"\n📊 Direct Apply Summary:")
    print(f"   ✅ Applied: {applied} | 🏃 Dry Run: {dry_runs} | ⏭️ Skipped: {skipped} | ❌ Failed: {failed}")

    return results


def run_direct_apply(jobs: list, resume_path: str) -> list:
    """Synchronous wrapper for direct apply."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    direct_config = config.get("direct_apply", {})

    if not direct_config.get("enabled", False):
        print("⚠️ Direct apply is disabled. Set direct_apply.enabled = true in config.")
        return []

    max_apply = direct_config.get("max_per_day", 10)
    min_score = direct_config.get("min_match_score", 70)
    dry_run = direct_config.get("dry_run", True)

    # Use resume path from config if not provided
    if not resume_path:
        resume_path = direct_config.get("resume_path", "")

    return asyncio.run(direct_apply_batch(
        jobs, resume_path,
        max_applications=max_apply,
        min_score=min_score,
        dry_run=dry_run
    ))
