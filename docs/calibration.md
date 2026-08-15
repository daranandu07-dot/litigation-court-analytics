# Calibration against published court statistics

**What this document is:** every parameter in `src/generate_dataset.py` that could be anchored to a published figure, every parameter that could not, and the reasoning in both directions.

**Why it exists:** the README used to say the generator's parameters were "plausible but not calibrated against published court statistics." That sentence was honest, and it was also a gap that could be closed. This is the closing of it — including the parts that stayed open.

Last reviewed: 15 August 2026.

## Sources

| Tag | Source | Period |
|---|---|---|
| **[MoJ]** | [Civil Justice Statistics Quarterly, England & Wales](https://www.gov.uk/government/statistics/civil-justice-statistics-quarterly-january-to-march-2026/civil-justice-statistics-quarterly-january-to-march-2026) — Ministry of Justice | January–March 2026 |
| **[CC]** | [Commercial Court Annual Report](https://www.judiciary.uk/guidance-and-resources/commercial-court-annual-report-2023-24/) — Courts and Tribunals Judiciary | 2023–24 |

---

## 1. Anchored to published figures

### 1.1 Settlement at the door of the court — `TRIAL_DOOR_SETTLEMENT_RATE = 0.57`

**Published figure [CC]:** the Commercial Court listed 95 trials in 2023-24 and heard 41. That is **57% of listed trials settling before the court sat.** The London Circuit Commercial Court shows the same pattern (30 of 52 contested, so 42% settled), and the Admiralty Court is more extreme still (89% of 19 listed trials resolved before judgment).

**What the model did before:** a case allocated to "Trial Judgment" always produced a trial judgment. Reaching a listing was treated as identical to being adjudicated.

**Why that was wrong:** it overstated how often commercial disputes are actually decided by a judge, by roughly a factor of two. It also erased a category that matters enormously for reserving — the case that runs the entire trial timetable, incurs almost the entire cost, and then settles on the courthouse steps.

**The change:** 57% of trial-listed cases are re-routed to `Settled`, flagged in a new `settled_at_trial_door` column, and carry a duration offset of 0.40 in log-days against the full trial offset of 0.46 — they settle just short of the hearing, not months before it.

**Effect on the docket:**

| | Before | After |
|---|---|---|
| Trial judgments (resolved) | 297 (7.7%) | 128 (3.3%) |
| Settlements | 2,304 | 2,483 (of which **175** at the trial door) |
| Median duration, ordinary settlement | — | 395 days |
| Median duration, settlement at the door | — | **530 days** |
| Median duration, trial judgment | — | 486 days |

The middle row is the point. A door settlement takes **135 days longer than an ordinary settlement** and is indistinguishable from it in the `disposition_type` column. Anyone reserving from disposition type alone would systematically under-provision this group.

**Cross-check:** the resulting 3.3% trial-judgment rate can be compared crudely against 41 trials heard from 743 claims issued in the Commercial Court in 2023-24, which is 5.5%. These are different cohorts — claims issued in a year are not the claims tried in that year — so this is an order-of-magnitude sanity check, not a match. The model sits below the crude real figure, which is the conservative direction.

### 1.2 Docket scale — `N_CASES = 5,000` over four filing years

**Published figure [CC]:** 743 new claims issued in the Commercial Court in 2023-24; **1,082** across the Commercial Court and London Circuit Commercial Court together.

**Model:** 5,000 cases over the 2022–2025 filing window is 1,250 per year.

**Assessment:** within 16% of the real combined figure. The docket is the right order of magnitude for a London commercial disputes portfolio rather than an arbitrary round number. Left unchanged; the difference is well inside the year-to-year variation in the published series.

### 1.3 International venue mix

**Published figure [CC]:** approximately **75%** of the Commercial Court's work involved international disputes in 2023-24, consistent with prior years.

**Model:** seven venues across four jurisdictions, with non-English courts carrying 45% of the sampling weight.

**Assessment:** the published figure concerns the nationality of *parties* in an English court, whereas the model varies the *court itself*. These are not the same measurement, so this is a directional justification for a multi-jurisdiction docket rather than a numeric anchor. Recorded here so the reasoning is visible rather than assumed.

---

## 2. Compared but deliberately not anchored

### 2.1 Duration — the model runs slower than the published median, on purpose

**Published figure [MoJ]:** median time from claim issue to trial, fast/intermediate/multi-track combined: **54.3 weeks (380 days)**. That is the fastest such figure since the series began in 2022.

**Model:** median duration for a Medium-complexity case reaching trial judgment: **596 days**, or 1.57x the published figure.

**Why this gap is not corrected:**

The MoJ figure combines three tracks. Fast track covers claims up to £25,000 and intermediate track up to £100,000, and by volume these dominate the combined statistic. Multi-track alone — the only track a £50,000–£10,000,000 commercial dispute would be allocated to — is slower, and Commercial Court work is slower again. The Commercial Court's average trial length alone is 9 days [CC].

So a commercial docket sitting **above** the combined multi-track median is directionally correct. Forcing the model down to 380 days to match a published number would produce a worse model that cited a better source.

**What is honestly unknown:** the *size* of the gap. Neither the MoJ nor the Commercial Court publishes a multi-track-only or Commercial-Court-only median time to trial. 1.57x is a modelling choice constrained from below by a real figure, not a measurement. If a published Commercial Court duration median appears in a future annual report, this is the first parameter to revisit.

**Status: bounded below by published data, not calibrated to it.**

### 2.2 Small claims — deliberately unused

**Published figure [MoJ]:** median time from issue to trial, small claims track: 37.6 weeks (263 days).

**Not used.** The small claims track is capped at £10,000. This docket's smallest claim is £50,000. Anchoring any part of a commercial disputes model to small-claims timings would be citing a real number about the wrong population, which is worse than citing nothing. Recorded here so that the omission is visibly deliberate.

### 2.3 Default judgments — the biggest divergence in the model, and why it stays

**Published figures [MoJ]:** of 527,000 County Court claims in Q1 2026, only 72,000 were defended — a **13.7% defence rate**. Of 256,000 judgments, **94% were default judgments**. Just 13,000 trials took place.

**Model:** every case is contested. There are no undefended claims at all.

This is the largest single divergence between the model and published national statistics, and it is worth being explicit that it is a choice rather than an oversight.

Those national figures are dominated by high-volume undefended debt recovery — a creditor issues a claim, the debtor never files a defence, judgment enters automatically. That is most of civil litigation by count and almost none of it by value or legal interest. A portfolio of £50,000+ commercial contract disputes between represented parties is precisely the atypical slice where the 94% figure does not hold: these defendants have counsel, and they defend.

**So the divergence is correct for the modelled population — but it means no figure in this repository should be compared against national County Court statistics.** The model describes a deliberately unrepresentative tail.

A useful extension would be to model both populations and show how different they are. That is noted in the README's *What I'd improve next*.

---

## 3. Not calibrated — no published figure exists

Listed so that the absence is documented rather than discovered.

| Parameter | Model value | Why there is no anchor |
|---|---|---|
| `COMPLEXITY_BASE_LOG_DAYS` | 5.52 / 5.94 / 6.34 | No court publishes duration broken down by case complexity. Complexity is itself a modelling construct, not a court-recorded field. |
| Judge `sj_effect` (σ = 0.42, two outliers at ±1.35/−1.25) | — | No jurisdiction in this docket publishes per-judge summary-judgment grant rates. In France, doing so would be a criminal offence (see README). |
| Judge `pace_effect` (σ = 0.10) | — | Same. |
| Recovery ratios | Beta(2.2, 4.0) settled; Beta(3.0, 2.0) trial | Settlement terms are overwhelmingly confidential. No published distribution exists and, in the nature of settlement, one is unlikely to. |
| Defendant win rate at trial | 32% | Not published for commercial claims in the venues modelled. |
| `num_interlocutory_motions` | Poisson, λ = 1.1 / 2.3 / 4.0 | Interlocutory application counts are not published in a comparable form. |
| Claim amount distribution | Log-normal, £50k–£10m | Claim values are not published in aggregate for the Commercial Court. |
| `VENUE_DURATION_OFFSET` | ±0.22 log-days | Would require comparable cross-jurisdiction duration statistics, which do not exist in a common definition. |
| Censoring rate | 22.2% (emergent) | Not set directly — it falls out of the filing window and `AS_OF`. No published equivalent, since courts report on disposals rather than open-case age profiles. |

**Nine of the model's parameter groups remain modelling choices.** Three are anchored. That ratio is the honest headline of this exercise, and it is a better sentence for the README than either "uncalibrated" or an implied "calibrated" that would not survive scrutiny.

---

## 4. What changed in the published results

Re-running the pipeline after the trial-door calibration moved every headline figure. The test suite caught all six stale README claims automatically, which is what it is for.

| Figure | Before | After |
|---|---|---|
| Trial judgments (resolved) | 297 | 128 |
| Settlements | 2,304 | 2,483 |
| Portfolio recovery | 26.9% | 26.7% |
| KM median, High complexity | 782 d | 759 d |
| Censoring bias, High complexity | 147 d | 130 d |
| AFT time ratio, High complexity | 2.38x | 2.31x |
| Log-rank χ² | 2,180 | 2,213 |

Nothing qualitative changed. Complexity still dominates duration, censoring still biases naive estimates downward, judges still differ within a bench. **The conclusions survived a material change to the data-generating process**, which is a mild form of sensitivity analysis and worth more than any individual number in the table above.

---

---

## 5. The general civil cohort — `src/generate_general_civil.py`

§2.3 above explains why the commercial docket has no undefended claims, and noted that modelling the national population separately would be the highest-value remaining item. That is now done.

### 5.1 Anchored parameters

| Parameter | Value | Published anchor |
|---|---|---|
| `DEFENCE_RATE` | 13.66% | 72,000 of 527,000 claims defended [MoJ] |
| `TRIAL_RATE_GIVEN_DEFENDED` | 18.06% | 13,000 trials against 72,000 defended claims [MoJ] |
| `DEFAULT_JUDGMENT_RATE_GIVEN_UNDEFENDED` | 52.9% | **Derived** — see below |
| `SMALL_CLAIMS_TRIAL_DAYS` | 263.2 | 37.6 weeks median issue→trial, small claims [MoJ] |
| `MULTI_TRACK_TRIAL_DAYS` | 380.1 | 54.3 weeks median issue→trial, fast/intermediate/multi [MoJ] |
| `MIN_DAYS_TO_DEFAULT_JUDGMENT` | 14 | CPR 10.3 acknowledgment of service period |

Realised against published, after generation:

| Measure | Model | Published |
|---|---|---|
| Defence rate | 13.8% | 13.7% |
| Default judgments as a share of all judgments | 95.3% | 94% |
| Default judgment share of disposals | 46.0% | 45.7% (derived) |
| Paid or discontinued | 40.7% | 40.7% (derived) |
| Settled (defended) | 11.1% | 11.2% (derived) |
| Trial judgment | 2.3% | 2.5% (derived) |

### 5.2 Two calibration errors this exercise caught

Both were found by comparing model output against a published figure rather than against what I expected to see. Recording them because the process is the point.

**Error 1 — "undefended" is not the same as "default judgment."**

The first version routed every undefended claim to a default judgment. That produced defaults at **97.4%** of all judgments against a published 94%. Small gap, real cause.

Working the published arithmetic backwards: 94% of 256,000 judgments is 240,640 default judgments, against 455,000 undefended claims. **Only 52.9% of undefended claims produce a judgment at all.** The other 47% are paid, settled or discontinued without any judgment being entered — a claimant paid the week after issuing does not go on to ask the court for judgment.

That is a substantive fact about civil litigation which the model would have missed entirely, and the only reason it surfaced was a three-point discrepancy in a ratio.

**Error 2 — the sigmoid does not commute with the mean.**

Defence probability rises with claim size. Setting the intercept to `logit(0.137)` and adding a size term produced a realised defence rate of **15.2%**, not 13.7%: averaging a non-linear function over a covariate does not give the function of the average (Jensen's inequality). The intercept is now solved by bisection so the *realised* rate matches the published one.

### 5.3 Not calibrated in this cohort

| Parameter | Why not |
|---|---|
| `DEFAULT_JUDGMENT_MEDIAN_DAYS` (52) | No published median for time from issue to entry of default judgment. Reasoned from the CPR 10.3 floor plus court administration time. |
| `PAID_OR_DISCONTINUED_MEDIAN_DAYS` (33) | Not published, and the category mixes two opposite outcomes. |
| `SETTLE_FRACTION_OF_TRIAL_TIMELINE` (0.60) | No published figure for when in the timetable defended claims settle. |
| Claim amount distribution | The MoJ does not publish a claim-value distribution. Shape targeted so ~83% fall within the small claims limit. |
| Recovery on "paid or discontinued" | Mixes full payment with total abandonment; the published statistics do not separate them. |

### 5.4 A limitation worth stating plainly

**A default judgment is a judgment, not money.** Entering judgment against a defendant who never engaged with the proceedings is one thing; enforcing it is another, and enforcement is where a large share of default judgments fail. This cohort records the full sum claimed as the award on that path and **does not model enforcement at all**. Any recovery figure derived from it is therefore a paper figure, and should not be read as cash collected.

---

## 6. Next calibration steps

1. **Model enforcement outcomes** on the default judgment path (§5.4). Currently the single largest overstatement in the general cohort.
2. **Recovery rates** — settlement terms are confidential, but litigation funders publish aggregate return statistics that may support a loose anchor.
3. **Re-check the MoJ series each quarter.** The Q1 2026 multi-track figure was the fastest since 2022; a single quarter is not a trend, and anchoring to a fast quarter would embed an optimistic bias.
4. **Replace anchoring with real data entirely** — see `docs/OPTIMISATION_PLAN.md`.
