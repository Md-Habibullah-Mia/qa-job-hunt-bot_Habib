"""
report_generator.py - Fixed: accepts dashboard_url parameter
"""

import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_score_color(score):
    if score >= 80: return "#16a34a"
    elif score >= 60: return "#d97706"
    else: return "#6b7280"

def get_score_bg(score):
    if score >= 80: return "#f0fdf4"
    elif score >= 60: return "#fffbeb"
    else: return "#f9fafb"

def get_score_label(score):
    if score >= 80: return "🔥 Excellent"
    elif score >= 60: return "👍 Good"
    elif score >= 40: return "🤔 Fair"
    else: return "💡 Possible"

def get_category_style(category):
    styles = {
        "sponsorship_worldwide": {
            "icon": "✈️",
            "title": "Outside Bangladesh — Visa Sponsorship",
            "color": "#16a34a",
            "bg": "#f0fdf4",
            "border": "#86efac"
        },
        "remote_worldwide": {
            "icon": "🌎",
            "title": "Remote — Worldwide",
            "color": "#7c3aed",
            "bg": "#f5f3ff",
            "border": "#c4b5fd"
        },
    }

    return styles.get(
        category,
        {
            "icon": "💼",
            "title": category,
            "color": "#374151",
            "bg": "#f9fafb",
            "border": "#e5e7eb"
        }
    )

def build_job_card(job):
    score = job.get("match_score", 0)
    score_color = get_score_color(score)
    score_bg = get_score_bg(score)
    score_label = get_score_label(score)
    reasons = job.get("match_reasons", [])[:3]
    missing = job.get("missing_skills", [])[:3]
    url = job.get("url", "#")
    title = job.get("title", "N/A")
    company = job.get("company", "N/A")
    location = job.get("location", "")
    source = job.get("source", "").upper()
    salary = job.get("salary", "") or ""
    category = job.get("category", "")
    sponsorship = job.get("sponsorship", False) or category == "sponsorship_worldwide"

    badges = ""
    if sponsorship:
        badges += '<span style="display:inline-block;background:#dcfce7;color:#166534;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px;">✈️ VISA/SPONSOR</span>'
    if "remote" in job.get("type","").lower() or "remote" in location.lower():
        badges += '<span style="display:inline-block;background:#ede9fe;color:#6d28d9;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;margin:2px;">🏠 REMOTE</span>'
    if source:
        badges += f'<span style="display:inline-block;background:#f3f4f6;color:#6b7280;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;margin:2px;">{source}</span>'

    reasons_html = ""
    if reasons:
        items = "".join([f'<li style="margin:3px 0;font-size:13px;color:#374151;">✅ {r}</li>' for r in reasons])
        reasons_html = f'<div style="flex:1;min-width:160px;"><p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;">Why You Match</p><ul style="margin:0;padding-left:16px;">{items}</ul></div>'

    missing_html = ""
    if missing:
        items = "".join([f'<li style="margin:3px 0;font-size:13px;color:#6b7280;">❌ {m}</li>' for m in missing])
        missing_html = f'<div style="flex:1;min-width:160px;"><p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;">Skill Gaps</p><ul style="margin:0;padding-left:16px;">{items}</ul></div>'

    salary_html = f'<span style="color:#6b7280;font-size:13px;"> · 💰 {salary}</span>' if salary else ""

    return f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:20px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;">
    <div style="flex:1;min-width:200px;">
      <a href="{url}" style="font-size:16px;font-weight:700;color:#1d4ed8;text-decoration:none;">{title}</a>
      <div style="margin-top:4px;font-size:13px;color:#4b5563;">🏢 <strong>{company}</strong>{f' · 📍 {location}' if location else ''}{salary_html}</div>
      <div style="margin-top:7px;">{badges}</div>
    </div>
    <div style="background:{score_bg};border:2px solid {score_color};border-radius:12px;padding:8px 14px;text-align:center;min-width:72px;flex-shrink:0;">
      <div style="font-size:24px;font-weight:800;color:{score_color};">{score}%</div>
      <div style="font-size:11px;color:{score_color};font-weight:600;">{score_label}</div>
    </div>
  </div>
  {f'<div style="display:flex;gap:14px;margin-top:14px;flex-wrap:wrap;">{reasons_html}{missing_html}</div>' if reasons_html or missing_html else ""}
  <div style="margin-top:14px;">
    <a href="{url}" style="display:inline-block;background:#1d4ed8;color:#fff;padding:9px 20px;border-radius:8px;font-size:13px;font-weight:700;text-decoration:none;">Apply Now →</a>
  </div>
</div>"""


def build_skill_gap_html(skill_gap):
    if not skill_gap or "error" in skill_gap:
        return '<p style="color:#6b7280;font-size:14px;">Skill gap analysis unavailable today.</p>'

    critical = skill_gap.get("critical_skills_to_learn", [])
    trending = skill_gap.get("trending_in_qa", [])
    certs = skill_gap.get("certifications_recommended", [])
    quick_wins = skill_gap.get("quick_wins", [])
    advice = skill_gap.get("career_advice", "")

    advice_html = f'<div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:20px;font-size:14px;color:#1e40af;line-height:1.6;">{advice}</div>' if advice else ""

    skills_html = ""
    for skill in critical[:4]:
        resources = " · ".join(skill.get("resources", [])[:2])
        skills_html += f"""<div style="border:1px solid #fde68a;background:#fffbeb;border-radius:10px;padding:12px 14px;margin:7px 0;">
          <div style="font-size:14px;font-weight:700;color:#92400e;">📚 {skill.get('skill','')}</div>
          <div style="font-size:13px;color:#374151;margin-top:3px;">{skill.get('reason','')}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:3px;">⏱️ {skill.get('learning_time','')}{f' · 🔗 {resources}' if resources else ''}</div>
        </div>"""

    trending_html = ""
    if trending:
        pills = "".join([f'<span style="display:inline-block;background:#f3e8ff;color:#7c3aed;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;margin:3px;">{t}</span>' for t in trending[:6]])
        trending_html = f'<div style="margin-top:16px;"><p style="font-size:12px;font-weight:700;color:#374151;text-transform:uppercase;margin-bottom:7px;">🔥 Trending in QA</p>{pills}</div>'

    quick_html = ""
    if quick_wins:
        items = "".join([f'<li style="margin:5px 0;font-size:13px;">⚡ {w}</li>' for w in quick_wins[:4]])
        quick_html = f'<div style="margin-top:16px;"><p style="font-size:12px;font-weight:700;color:#374151;text-transform:uppercase;margin-bottom:7px;">Quick Wins</p><ul style="margin:0;padding-left:18px;">{items}</ul></div>'

    cert_html = ""
    if certs:
        items = "".join([f'<li style="margin:5px 0;font-size:13px;">🏆 <strong>{c.get("cert","")}</strong> — {c.get("reason","")}</li>' for c in certs[:3]])
        cert_html = f'<div style="margin-top:16px;"><p style="font-size:12px;font-weight:700;color:#374151;text-transform:uppercase;margin-bottom:7px;">Certifications</p><ul style="margin:0;padding-left:18px;">{items}</ul></div>'

    return advice_html + skills_html + trending_html + quick_html + cert_html


def generate_report(matched_jobs: dict, applied_results: list, skill_gap: dict, total_scraped: int, dashboard_url: str = "") -> str:
    """Generate HTML email report. dashboard_url is optional."""
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    time_str = datetime.now().strftime("%I:%M %p IST")

    all_jobs = [j for jobs in matched_jobs.values() for j in jobs]
    total_matched = len(all_jobs)
    total_applied = len([r for r in applied_results if r.get("status") == "applied"])
    excellent = len([j for j in all_jobs if j.get("match_score", 0) >= 80])

    # Dashboard button
    dashboard_btn = ""
    if dashboard_url:
        dashboard_btn = f"""
        <div style="text-align:center;margin:20px 0;">
          <a href="{dashboard_url}" style="display:inline-block;background:linear-gradient(135deg,#1e40af,#6d28d9);color:#fff;padding:14px 32px;border-radius:50px;font-size:15px;font-weight:800;text-decoration:none;box-shadow:0 4px 14px rgba(29,78,216,0.4);">
            🌐 View All {total_matched} Jobs on Dashboard →
          </a>
          <p style="color:#9ca3af;font-size:12px;margin-top:8px;">Searchable · Filterable · Saves your favourites</p>
        </div>"""

    # Category sections — show top 10 per category in email
    category_sections = ""
    for category, jobs in matched_jobs.items():
        if not jobs:
            continue
        style = get_category_style(category)
        cards = "".join([build_job_card(j) for j in jobs[:10]])
        more = ""
        if len(jobs) > 10:
            more = f'<p style="text-align:center;color:#6b7280;font-size:13px;padding:8px 0;">+{len(jobs)-10} more in this category — <a href="{dashboard_url}" style="color:#2563eb;">view on dashboard</a></p>' if dashboard_url else f'<p style="text-align:center;color:#6b7280;font-size:13px;">+{len(jobs)-10} more jobs</p>'

        category_sections += f"""
        <div style="margin:24px 0;">
          <div style="background:{style['bg']};border:1px solid {style['border']};border-radius:12px;padding:12px 18px;margin-bottom:14px;">
            <span style="font-size:18px;">{style['icon']}</span>
            <span style="font-size:16px;font-weight:700;color:{style['color']};margin-left:8px;">{style['title']}</span>
            <span style="font-size:13px;color:#6b7280;margin-left:8px;">— {len(jobs)} jobs</span>
          </div>
          {cards}
          {more}
        </div>"""

    skill_gap_html = build_skill_gap_html(skill_gap)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<div style="max-width:660px;margin:0 auto;padding:20px 16px 40px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e40af,#6d28d9);border-radius:20px;padding:28px;text-align:center;margin-bottom:16px;">
    <div style="font-size:34px;margin-bottom:6px;">🤖</div>
    <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800;">Daily Job Hunt Report</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">{date_str} · {time_str}</p>
    <p style="margin:3px 0 0;color:rgba(255,255,255,0.6);font-size:12px;">QA Automation Engineer · Worldwide Search</p>
  </div>

  <!-- Stats -->
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">
    <div style="background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="font-size:28px;font-weight:800;color:#2563eb;">{total_scraped}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;font-weight:600;">SCANNED</div>
    </div>
    <div style="background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="font-size:28px;font-weight:800;color:#7c3aed;">{total_matched}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;font-weight:600;">MATCHED</div>
    </div>
    <div style="background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="font-size:28px;font-weight:800;color:#16a34a;">{excellent}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;font-weight:600;">EXCELLENT</div>
    </div>
    <div style="background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="font-size:28px;font-weight:800;color:#d97706;">{total_applied}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;font-weight:600;">APPLIED</div>
    </div>
  </div>

  <!-- Dashboard button -->
  {dashboard_btn}

  <!-- Jobs -->
  <div style="background:#fff;border-radius:20px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:14px;">
    {category_sections if category_sections else '<p style="text-align:center;color:#6b7280;padding:20px;">No jobs matched today. Bot will try again tomorrow at 9AM IST.</p>'}
  </div>

  <!-- Skill Gap -->
  <div style="background:#fff;border-radius:20px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:14px;">
    <h2 style="margin:0 0 16px;font-size:18px;color:#1f2937;border-bottom:2px solid #f3f4f6;padding-bottom:10px;">🧠 Skill Gap Analysis & Career Growth</h2>
    {skill_gap_html}
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding:16px;color:#94a3b8;font-size:12px;">
    🤖 QA Job Hunt Bot · Gemini AI (Free) · Next run: tomorrow 9:00 AM IST
  </div>

</div>
</body>
</html>"""
