# Prioritize Worldwide Remote & Bangladesh Remote Jobs
## Visa Sponsorship as a Secondary Attribute

Re-architect job categorization, scraping, AI matching, report generation, and dashboard UI so that:

1. **Remote Worldwide** is a primary job category.
2. **Remote Bangladesh** is a primary job category.
3. **Visa Sponsorship** is treated as a secondary boolean attribute (`sponsorship: true`).
4. Visa sponsorship must not become a primary job category.
5. No India-specific category, search, filter, badge, statistic, or logic should remain.
6. Existing pipeline functionality must remain stable.
7. The `working-v1-2026-08-13` branch must not be modified.

---

# Implementation Status

## Already Implemented

- ✅ `config/resume_profile.json` updated with the current 13+ years / Senior QA profile.
- ✅ `experience_years` is set to `13`.
- ✅ `current_level` is set to `"senior"`.
- ✅ GitHub Actions workflow includes Playwright Chromium installation.
- ✅ GitHub Actions dashboard update/push flow has been stabilized.
- ✅ Feature branch `feature/updateSkills_Timezone-push` is being used for the current work.
- ✅ Manual GitHub Actions run on the feature branch completed successfully.

## Remaining Implementation

- ⬜ Worldwide Remote primary categorization
- ⬜ Bangladesh Remote primary categorization
- ⬜ Sponsorship as a secondary boolean attribute
- ⬜ Scraper updates
- ⬜ Main pipeline category handling
- ⬜ Job statistics updates
- ⬜ Gemini AI matching/scoring updates
- ⬜ Email report updates
- ⬜ Dashboard UI updates
- ⬜ India-reference cleanup
- ⬜ Automated category verification
- ⬜ Final end-to-end verification

---

# 1. Scrapers

## 1.1 `scrapers/linkedin_scraper.py`

### Worldwide Remote Searches

Replace `sponsorship_worldwide` search configurations with high-intent worldwide remote searches:

- `"QA Automation Engineer remote worldwide"`
- `"SDET remote worldwide"`
- `"Test Automation Engineer remote worldwide"`
- `"Software Test Engineer remote worldwide"`
- `"QA Lead remote worldwide"`
- `"QA Automation Engineer work from anywhere"`

Requirements:

- Ensure `f_WT=2` (Remote filter) is applied.
- Remove location constraints for worldwide remote searches.
- Assign:

```python
"category": "remote_worldwide"
"type": "Remote Worldwide"