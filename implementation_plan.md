# Implementation Plan — Software QA Domain Filtering & Job Match Accuracy

## 1. Objective

Improve the job-matching system so that it identifies **Software QA / SQA / Automation / SDET / Testing roles** accurately while preventing unrelated Quality Assurance roles from being treated as suitable software QA positions.

### Current Problem

A job such as:

> **Quality Assurance Team Leader — Lojas Renner S.A.**

was considered relevant because the title contains **“Quality Assurance”**.

However, the actual job is focused on:

* Apparel / footwear / retail quality
* Factory audits
* Supplier quality
* Manufacturing inspections
* AQL
* CAPA
* QC inspectors
* Supplier onboarding
* Third-party inspection companies
* Manufacturing quality KPIs

This is **not Software QA**.

---

# 2. Core Design Change

Do **not** rely on generic QA keywords alone.

The matcher should determine:

```text
Is this a Software QA / Testing role?
        |
        +---- YES → Continue normal matching
        |
        +---- NO → Reject / heavily penalize
```

The domain decision should happen **before the final match score is accepted**.

---

# 3. Add Software QA Positive Signals

Create a dedicated list for strong software-testing indicators.

Example categories:

### Strong Software QA titles

* QA Automation Engineer
* QA Automation
* SDET
* Software Development Engineer in Test
* Software Test Engineer
* Software QA Engineer
* QA Engineer
* Automation Test Engineer
* Automation Tester
* Test Automation Engineer
* Senior QA Engineer
* Senior SDET
* QA Lead
* QA Automation Lead
* Test Lead
* Software Quality Engineer

### Strong Software QA technologies

* Selenium
* Playwright
* Cypress
* WebDriver
* Appium
* Cucumber
* TestNG
* JUnit
* Jest
* Rest Assured
* Postman
* API automation
* UI automation
* E2E testing
* automated testing
* CI/CD testing
* GitHub Actions
* Jenkins
* Java
* TypeScript
* JavaScript
* Python

These should increase confidence that “QA” means **software QA**.

---

# 4. Add Non-Software QA / Manufacturing Exclusion Signals

Create a separate exclusion list for roles where “Quality Assurance” means manufacturing/product/supplier quality.

### Manufacturing / physical-product QA signals

* apparel
* garment
* textile
* footwear
* manufacturing
* factory
* supplier quality
* supplier management
* supplier audit
* factory audit
* production quality
* product inspection
* quality inspector
* QC inspector
* inspection company
* AQL
* manufacturing process
* production process
* raw material
* finished goods
* production line
* factory compliance
* merchandise quality
* sourcing quality
* supplier onboarding
* third-party inspection
* reimbursement
* sales returns
* physical product quality

### Important rule

A generic title such as:

> Quality Assurance Team Leader

must **NOT automatically receive the Software QA +50 bonus**.

If the description contains strong manufacturing/supplier/factory signals, it should be classified as:

```text
non_software_qa
```

and rejected from the software QA matching pipeline.

---

# 5. Introduce Explicit Domain Classification

Add a deterministic classification function, for example:

```text
classify_job_domain(job)
```

Possible results:

```text
software_qa
non_software_qa
mixed
unknown
```

### Classification logic

#### Software QA

If strong software-testing signals are present:

```text
SDET
Playwright
Selenium
test automation
API automation
software testing
UI automation
CI/CD
```

→ `software_qa`

#### Non-software QA

If strong manufacturing/physical-product signals are present:

```text
factory
apparel
textile
supplier quality
AQL
inspection
manufacturing
QC inspector
```

→ `non_software_qa`

#### Mixed / ambiguous

If the title is generic:

```text
Quality Assurance Manager
Quality Engineer
QA Team Leader
```

and there is not enough evidence:

→ `unknown` or `mixed`

Do not automatically treat it as software QA.

---

# 6. Fix the Existing Title-Based Fallback

The current fallback gives a large score when a QA keyword appears in the title.

This needs to change.

### Current behavior

```text
"quality assurance" in title
        ↓
+50
```

### New behavior

```text
Generic QA title
        ↓
Check description/domain
        ↓
Software QA evidence?
    YES → continue
    NO  → reject / low score
```

The fallback should remain deterministic because it is used when Gemini is unavailable or when the description is too short.

The existing code already uses `title_based_score()` for short descriptions and Gemini failures, so this protection must also exist in the fallback path.

---

# 7. Strengthen the Gemini Matching Prompt

Update the Gemini prompt so that Gemini understands:

> The candidate is a Software QA / SQA / Automation professional.

Gemini must explicitly determine:

```json
{
  "job_domain": "software_qa",
  "domain_confidence": 95,
  "domain_reason": "The role focuses on Selenium, Playwright, API automation and CI/CD testing"
}
```

For an apparel/manufacturing QA role:

```json
{
  "job_domain": "non_software_qa",
  "domain_confidence": 98,
  "domain_reason": "The role focuses on factory audits, supplier quality, AQL and manufacturing inspections"
}
```

---

# 8. Add a Hard Domain Guard

After Gemini returns the result, apply a deterministic guard.

### If:

```text
job_domain == non_software_qa
```

then:

```text
match_score = 0
recommendation = "REJECT"
```

and add:

```text
"Non-software QA domain"
```

to the reason.

This is important because the AI should **not be able to override an obvious domain mismatch**.

---

# 9. Handle Generic “Quality Engineer” Carefully

`Quality Engineer` is especially dangerous because it can mean:

### Software

> Software Quality Engineer
> Quality Engineer — Test Automation

or:

### Manufacturing

> Quality Engineer — Manufacturing
> Supplier Quality Engineer
> Factory Quality Engineer

Therefore:

```text
Quality Engineer
```

alone should NOT be enough to classify a job as software QA.

The surrounding title + description must determine the domain.

---

# 10. Keep Legitimate Software QA Jobs Safe

The new filter must NOT accidentally reject jobs such as:

### JPMorganChase

**Software Engineer II - Automation Tester**

This is clearly a software testing role because the description contains:

* Selenium WebDriver
* Playwright
* TypeScript
* Java
* UI automation
* POM
* API
* CI/CD
* accessibility testing
* visual regression testing

Therefore it should remain a strong match.

The same applies to:

* SDET
* QA Automation Engineer
* Senior QA Engineer
* QA Automation Lead
* Software Test Engineer
* Automation Tester

---

# 11. Add Domain Information to Job Output

Each matched job should contain something like:

```json
{
  "job_domain": "software_qa",
  "domain_confidence": 94
}
```

For rejected jobs:

```json
{
  "job_domain": "non_software_qa",
  "domain_confidence": 97,
  "recommendation": "REJECT"
}
```

This makes the matching decision transparent.

---

# 12. Reporter Changes

The report should continue showing only useful jobs in the main matched section.

Do not pollute the report with manufacturing QA jobs.

Optionally, maintain a small internal rejection statistic:

```text
Non-software QA filtered: 7
```

This is useful for validating the new filter.

Do not show unnecessary rejected-job details in the normal daily report.

---

# 13. Test Cases

Before considering the change complete, test these categories.

### Must MATCH

1. Senior QA Automation Engineer
2. Senior SDET
3. Software Development Engineer in Test
4. Automation Tester
5. QA Automation Lead
6. Software QA Engineer
7. JPMorganChase — Software Engineer II - Automation Tester

### Must NOT MATCH

1. Apparel Quality Assurance
2. Garment QA Manager
3. Factory Quality Engineer
4. Supplier Quality Engineer
5. Manufacturing Quality Assurance
6. Quality Control Inspector
7. Textile Quality Manager
8. Factory Audit / Quality Manager
9. Lojas Renner — Quality Assurance Team Leader

### Ambiguous cases

1. Quality Engineer
2. Quality Assurance Manager
3. QA Team Leader
4. Quality Specialist

These must be decided using the job description rather than the title alone.

---

# 14. Regression Protection

Do not rewrite the existing matcher unnecessarily.

Preserve:

* Gemini matching
* title fallback
* skill-gap analysis
* scoring
* recommendation generation
* remote-type detection
* existing job scraping
* daily report generation

The new domain filter should be inserted as a controlled layer around the existing matching logic.

---

# 15. Files Expected to Change

Primary:

```text
matcher/job_matcher.py
```

Potentially:

```text
reporter/report_generator.py
```

Tests should be added/updated if the repository already has a test structure.

Do NOT modify:

```text
config/resume_profile.json
```

The personal resume profile remains local and ignored by Git.

---

# 16. Validation Process

After implementation:

### Step 1 — Syntax check

```powershell
python -m py_compile matcher/job_matcher.py
```

### Step 2 — Run local job matcher

Run the normal project command and inspect:

* total scanned
* total matched
* top scores
* rejected domain classifications

### Step 3 — Specifically verify known examples

Confirm:

```text
JPMorganChase Automation Tester → MATCH
Lojas Renner Quality Assurance Team Leader → REJECT
```

### Step 4 — Run GitHub Actions

Push the change to the feature branch and verify that the daily workflow still completes successfully.

### Step 5 — Review the report

The final report should contain mostly:

```text
Software QA
SDET
Automation
Testing
SQA
```

and should no longer promote:

```text
Factory QA
Apparel QA
Supplier QA
Manufacturing QA
```

as high-match software QA jobs.

---

# 17. Success Criteria

The implementation is successful when:

* Generic “Quality Assurance” titles no longer automatically receive a high score.
* Manufacturing/apparel/supplier QA jobs are filtered out.
* Genuine Software QA/SDET/Automation jobs continue to receive high scores.
* JPMorganChase-style software automation roles remain matched.
* The existing Gemini fallback continues working.
* The daily GitHub Actions workflow remains successful.
* No personal `resume_profile.json` data is committed.
* Existing scraper and reporting functionality remains intact.

## Final Principle

The matcher should answer this question **before asking “How well does this job match Habibullah?”**:

> **“Is this actually a Software QA job?”**

Only after that answer is `software_qa` should the normal skill/seniority/experience matching take place.
