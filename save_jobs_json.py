"""
save_jobs_json.py
Saves all matched jobs for the GitHub Pages dashboard.

With DASHBOARD_PASSWORD set (GitHub secret), the data is written encrypted to
docs/jobs.enc.json and the plain docs/jobs.json is removed — GitHub Pages is
public, so anything unencrypted there can be read by anyone with the link.
Without it (local runs), plain docs/jobs.json is written as before.
"""
import base64
import hashlib
import json
import os
from datetime import datetime

# Must match the dashboard's decrypt code in docs/index.html
PBKDF2_ITERATIONS = 250_000


def encrypt_payload(data: dict, password: str) -> dict:
    """AES-256-GCM with a PBKDF2-SHA256 key, readable by the browser's WebCrypto."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32)
    plaintext = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)  # tag appended, as WebCrypto expects
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"v": 1, "iter": PBKDF2_ITERATIONS, "salt": b64(salt), "iv": b64(iv), "data": b64(ciphertext)}


def save_jobs_for_dashboard(matched_jobs: dict, skill_gap: dict, total_scraped: int):
    """Save jobs to docs/jobs.json for GitHub Pages dashboard."""
    # Ensure docs directory exists
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    output_path = os.path.join(docs_dir, "jobs.json")

    try:
        import pytz
        bd_tz = pytz.timezone("Asia/Dhaka")
        now_bd = datetime.now(bd_tz)
    except Exception:
        from datetime import timezone, timedelta
        now_bd = datetime.now(timezone(timedelta(hours=6)))

    all_jobs = []
    # Preserve ordering: 1. Remote Worldwide, 2. Bangladesh Remote, 3. Outside Bangladesh Visa Sponsorship
    ORDERED_CATEGORIES = ["remote_worldwide", "bangladesh_remote", "sponsorship_worldwide"]
    ordered_keys = [k for k in ORDERED_CATEGORIES if k in matched_jobs] + [k for k in matched_jobs if k not in ORDERED_CATEGORIES]

    for category in ordered_keys:
        for job in matched_jobs.get(category, []):
            job_copy = dict(job)
            job_copy["category"] = job_copy.get("category") or category
            all_jobs.append(job_copy)

    # Sort by match score descending within dashboard view
    all_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    output = {
        "generated_at": now_bd.isoformat(),
        "total_scraped": total_scraped,
        "total_matched": len(all_jobs),
        "jobs": all_jobs,
        "skill_gap": skill_gap or {},
        "stats": {
            "excellent": len([j for j in all_jobs if j.get("match_score", 0) >= 80]),
            "good": len([j for j in all_jobs if 60 <= j.get("match_score", 0) < 80]),
            "remote_worldwide": len([j for j in all_jobs if j.get("category") == "remote_worldwide"]),
            "bangladesh_remote": len([j for j in all_jobs if j.get("category") in ("bangladesh_remote", "Bangladesh_remote")]),
            "sponsorship": len([j for j in all_jobs if j.get("category") == "sponsorship_worldwide" or j.get("sponsorship", False) or j.get("visa_sponsorship", False)]),
        }
    }

    password = os.environ.get("DASHBOARD_PASSWORD", "")
    try:
        if password:
            enc_path = os.path.join(docs_dir, "jobs.enc.json")
            with open(enc_path, "w", encoding="utf-8") as f:
                json.dump(encrypt_payload(output, password), f)
            if os.path.exists(output_path):
                os.remove(output_path)
            output_path = enc_path
        else:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print("   ⚠️ DASHBOARD_PASSWORD secret not set — dashboard data is PUBLIC")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, default=str, ensure_ascii=False)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"   💾 Saved {os.path.basename(output_path)} — {len(all_jobs)} jobs ({size_kb:.1f} KB)")
        print(f"   📁 Full path: {output_path}")
    except Exception as e:
        print(f"   ❌ Failed to save jobs.json: {e}")
        raise
