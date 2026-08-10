# Data-Driven Litigation Strategy: Reducing Case Duration and Predicting Exposure in Commercial Disputes

**Advisory memorandum** · Litigation Analytics · Prepared for General Counsel and Heads of Litigation
**Basis:** 5,000 commercial contract disputes across seven international courts, filed 2022–2025

---

## The problem

Litigation budgets are built on closed cases. That is the wrong sample. The matters that are still running are disproportionately the slow, expensive ones — and by excluding them, standard duration estimates systematically understate exposure.

This analysis corrects for that using survival methods borrowed from clinical research, which treat unresolved matters as *ongoing* rather than *absent*. The correction is not marginal.

---

## What the data shows

**1. Conventional duration estimates understate high-complexity exposure by roughly five months.**

Measuring only closed cases puts the median high-complexity dispute at **635 days**. Correcting for still-open matters puts it at **782 days** — an understatement of **147 days**. At **94.7%** still open at one year and **55.7%** still open at two, more than half of complex matters outlive the budget cycle they were provisioned in.

> *[Embed: chart_survival.html]*

**2. Scope drives duration far more than forum does.**

High-complexity matters run **2.38x longer** than low-complexity ones (95% CI 2.28–2.49). The gap between the fastest and slowest court is **1.52x**. Controlling what is pleaded is a stronger lever than choosing where to plead it.

> *[Embed: chart_duration.html]*

**3. Interlocutory motions signal drift, not progress.**

Each additional motion is associated with a **6.8% longer** case. Procedural activity intended to narrow issues is, in aggregate, a leading indicator of matters that are getting away from the team.

**4. Judicial assignment is a measurable risk factor, and the variance is large.**

Summary-judgment grant rates range from **7.9% to 42.0%** across the bench (χ² = 131.9, p ≈ 5×10⁻²⁴). The decisive comparison is within a single court: two judges on the **same bench**, hearing the same case mix under identical rules, differ by **5.3x** (p ≈ 8×10⁻²⁰). Jurisdiction cannot explain that. The assigned judge is doing the work.

> *[Embed: chart_judges.html]*

**5. Expected recovery is roughly a quarter of the amount claimed — and trial is not a free option.**

Portfolio-wide recovery is **£0.269 per £1 claimed**. Settlement returns **37.4%** of claim value; trial judgment returns a comparable average of **36.3%** — but with a **36% chance of recovering nothing at all**. Equal expected value, materially worse variance.

> *[Embed: chart_financial.html]*

---

## Recommendations

| # | Action | Rationale |
|---|---|---|
| 1 | Reserve against **censoring-corrected** durations | Closed-case averages under-reserve complex matters by ~5 months |
| 2 | Treat **scope control** as the primary duration lever | 2.38x complexity penalty vs. 1.52x venue spread |
| 3 | Trigger partner review at a **motion-count threshold** | Motion volume tracks drift; cheap early warning |
| 4 | Track **judge-level grant rates with confidence intervals** | 5x within-bench variance; a rate without an interval is not evidence |
| 5 | Price settlement on **variance, not just expected value** | Trial carries a 36% total-loss tail at equivalent mean recovery |

---

## Method

Kaplan-Meier survival estimation and Log-Normal accelerated failure time modelling (**concordance 0.780**), Wilson score intervals and two-proportion tests for judicial variance, chi-square homogeneity testing across the bench. Outcome variables realised at disposition were excluded from duration models to prevent leakage. The Cox proportional-hazards model was fitted, **failed its Schoenfeld residual test**, and was accordingly superseded by AFT specifications — reported here rather than omitted.

Full methodology, code, and result tables: [github.com/daranandu07-dot/litigation-court-analytics](https://github.com/daranandu07-dot/litigation-court-analytics)

---

> **Note on data.** This analysis runs on a **synthetic dataset** generated for methodological demonstration. Parameters are plausible but are not calibrated against published court statistics, and no figure describes any real court, judge, or case. The contribution here is the analytical framework — applied to a firm's own matter data, the same pipeline produces genuine findings.
