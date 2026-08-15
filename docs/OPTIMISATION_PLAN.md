# litigation-court-analytics → hiring-ready

**A staged optimisation plan.**
Prepared 15 August 2026. Written against the repository as it actually stands today, after the test-suite/CI/README work already delivered.

---

## Read this before anything else

You asked how to enrich the dataset — court outcomes, jurisdiction metrics, damages distributions, judge and counsel performance indicators.

**Adding any of those to synthetic data makes the project weaker, not stronger.**

Right now the repo has one honest, well-managed flaw: the data is invented, and you say so four times. Every new synthetic column widens the surface area of things you made up while adding exactly zero evidential value. A "counsel performance indicator" you generated yourself is not a finding about counsel. It is a number you chose, dressed as a result. An interviewer who spots that will stop trusting the rest of the repository, including the parts that are genuinely good.

The statistical rigour is already above what the project needs. You fit Cox, tested the proportional-hazards assumption, found it violated on 7 of 11 covariates, and switched to AFT. That is better practice than most published legal analytics. **More statistics is not your gap. Real data is your gap**, and it is the only gap that matters.

So this plan inverts your ordering. Phase 1 is data provenance. Everything else is downstream of it, and the UI work in particular is worth roughly triple once the numbers underneath it are real.

---

## Phase 1 — Data & analytics

### The three tiers, cheapest first

You do not have to jump straight to real case-level data. There is a genuinely valuable intermediate step most people skip.

---

### Tier A — Calibrate the synthetic generator against published statistics

**Effort: about a day. Credibility gain: disproportionate.**

Your README currently says parameters are "plausible but **not calibrated** against published court statistics." That sentence is doing real damage, and you can delete it honestly.

The Ministry of Justice publishes [Civil Justice Statistics Quarterly](https://www.gov.uk/government/statistics/civil-justice-statistics-quarterly-january-to-march-2026/civil-justice-statistics-quarterly-january-to-march-2026) for England and Wales. From the January–March 2026 release:

| Real published figure | Q1 2026 | Your generator |
|---|---|---|
| Median time, issue → trial, small claims | **37.6 weeks** (~263 days) | not modelled |
| Median time, issue → trial, fast/intermediate/multi-track | **54.3 weeks** (~380 days) | Medium complexity ≈ 380 days |
| County Court claims issued in the quarter | **527,000** | — |
| Judgments that were **default** judgments | **94%** | **0%** |

Two things fall out of this immediately.

**First, your Medium-complexity baseline is already close to the real multi-track figure.** `COMPLEXITY_BASE_LOG_DAYS["Medium"] = 5.94` gives roughly 380 days, against a real 54.3 weeks. That is a coincidence you can convert into a citation. Re-anchor all three complexity baselines to published medians, cite the release, and note that the MoJ figure measures issue-to-*trial* while yours measures issue-to-*disposition* — different endpoints, and saying so is itself a mark of rigour.

**Second — and this is the important one — 94% of County Court judgments are default judgments.** Your generator models a world where every case is contested to a disposition. Real civil litigation at volume is overwhelmingly *undefended*: the defendant never shows up. Your docket contains no such cases at all.

That single fact is the most valuable thing in this section. It is a statement about how civil litigation actually works, it is citable, and fixing it is a concrete modelling change: add an `undefended` path where the claim terminates fast, recovery approaches the full claim, and no judge effect applies because no judicial discretion is exercised. Then note that a portfolio of *commercial* disputes is precisely the atypical slice where that does not hold — which is a legitimate reason your dataset looks different from the national picture, stated up front instead of discovered by a reader.

Deliverable: a `docs/calibration.md` that puts every generator parameter in a table next to the published figure it is anchored to, with a source link and an honest note where no published figure exists.

---

### Tier B — Real case-level data: the FJC Integrated Database

**Effort: one to two weeks. This is the change that makes the project real.**

The [FJC Integrated Database](https://www.fjc.gov/research/federal-court-cases-fjc-integrated-database-1979-present) holds civil, criminal, bankruptcy and appellate cases filed and terminated in the US federal courts **from 1979 to the present**. It is free, bulk-downloadable, and it maps onto your existing schema almost column for column.

| Your synthetic column | IDB equivalent |
|---|---|
| `filing_date` | filing date |
| `disposition_date` / `days_to_resolution` | termination date |
| `case_complexity` | proxy via nature-of-suit code and procedural progress |
| `court_venue` | district and office codes |
| `disposition_type` | disposition code |
| `final_awarded_amount_gbp` | amount received (sparse — see below) |
| `event_observed` | terminated vs pending |

Restrict to contract nature-of-suit codes and you have a real commercial-disputes docket with real filing dates, real terminations, and **real right-censoring** — pending cases genuinely are censored observations rather than ones you generated as censored. Your entire Kaplan-Meier and AFT apparatus transfers unchanged. That is the payoff for having built it properly: the method survives the data swap.

**Three gotchas, and the first one is severe.**

1. **Judge fields are deliberately blank.** [Free Law Project documents](https://free.law/idb-facts/) that judge identifiers are withheld from the IDB by policy of the Judicial Conference of the United States, set in 1995 and reaffirmed in 2003. **Your headline finding — the within-court judge variance — cannot be reproduced from the IDB at all.** Discovering this after two weeks of work would be demoralising. Discovering it now lets you plan around it: either source judge assignment separately from [CourtListener / RECAP](https://www.courtlistener.com/help/api/), which does carry docket-level judge information, or drop the judge analysis on real data and keep it in the synthetic module as an explicitly labelled methodological demonstration.
2. **Fields are truncated and the data lags.** Free Law Project notes many fields are artificially truncated, and the FJC receives quarterly updates roughly two months after quarter end. Build for staleness; state your snapshot date.
3. **Damages data is sparse and unreliable.** The amount fields are inconsistently populated. Do not build the financial-recovery analysis on them without first characterising the missingness — and if it is bad, say so and drop that section rather than reporting a number computed from 4% of rows.

Point 3 is an opportunity, not just a warning. A short section titled *"Why I could not compute recovery rates from real data"* — with the missingness figures to prove it — demonstrates more judgement than any chart you could produce instead.

---

### Tier C — Judge-level data, if you want the judicial analysis on real data

CourtListener/RECAP carries docket-level judge assignment. API access moved to rate-limited tiers in May 2026, with a **free EDU membership for students** — you qualify, so cost is not the blocker; volume and joining strategy are.

**Before you build this, read the next section. It is the most interesting legal question in your entire project.**

---

### The judicial-analytics problem — your best domain hook

In 2019 France enacted Article 33 of its justice reform act, which **criminalised the publication of judicial analytics that identify individual judges** — reusing judges' identity data to evaluate, analyse or predict their professional practices. Reported penalties run to five years' imprisonment. It remains, as far as I know, the strongest restriction of its kind in a major jurisdiction, and it was aimed squarely at products doing exactly what your `chart_judges.html` does.

*(I have verified this against multiple contemporaneous legal-press reports; before you assert it in writing, read Article 33 itself — you are the lawyer here, and a primary-source citation is worth more than my summary.)*

This is the single best piece of material in your project, because it lets you show legal knowledge **driving a technical decision** rather than decorating one:

- Your judges are already `JUD-01`…`JUD-10` with no names — a change made for one reason, which now has a much better one.
- The UK and US permit judicial analytics; France criminalises it. If you built this as a product, jurisdiction would determine whether a core feature is legal.
- So make anonymisation an **architectural property, not a convention**: a configuration flag, enforced by a test, that guarantees no individual judge is identifiable in any output. Then document *why*, with the citation.

That turns "I anonymised the judges" into "I designed for the most restrictive jurisdiction my tool could plausibly be used in, and here is the statute that sets the constraint." Very few candidates at any level can say that.

---

### Statistical rigour: four upgrades worth making

Your method is already strong. These are the genuine gaps, in priority order.

1. **Partial pooling for judge effects.** Ten judges with 150–300 motions each is the textbook case for a hierarchical model. Independent per-judge rates systematically overstate the extremes — the 42.0% and 7.9% figures are partly regression-to-the-mean artefacts. A random-effects logistic model shrinks them appropriately. This is the highest-value statistical addition available to you, and it *reduces* the drama of your headline finding, which is exactly why doing it is impressive.
2. **Calibration, not just discrimination.** Concordance of 0.780 says the model ranks cases well. It says nothing about whether "782 days" is *right*. Plot predicted against observed survival curves. Calibration is what anyone relying on the number actually needs.
3. **Sensitivity to the snapshot date.** Every censoring result depends on `AS_OF`. Re-run across several snapshot dates and show the conclusions hold. This is cheap and it directly answers the sharpest question an interviewer could ask.
4. **Competing risks.** Settlement, dismissal and trial judgment are not the same event, and treating "resolution" as one outcome hides that. A Fine–Gray or cause-specific hazard model treats them as competing risks. This is the most technically ambitious item here and the most defensible as *legally* motivated: settling and being dismissed are not the same thing happening to your client.

---

## Phase 2 — UI/UX and interactive features

### You already have this skill, in the repos you were about to hide

I looked at your other repositories. `fujian-chimes` is a Framer code component with live Web Audio synthesis, deployed at a public URL. `jass` renders flowers from 130+ individually animated hair-thin strands per petal. `kaleidoscope` and `teapot` are p5.js sketches.

That is a real, demonstrated ability to build sophisticated interactive front-ends — and it is precisely the capability your litigation project lacks. Right now those two things live in separate repos and neither benefits from the other. **The fix is not to hide the creative work. It is to point that ability at the litigation project.** A legal analytics dashboard built with the care that went into `fujian-chimes` would not look like a student project.

Keep them separate on your profile if you like; that is a presentation question. But you are not missing the front-end skill. You are missing the decision to spend it here.

### Architecture: static, no backend

Do not add a server. The right shape:

```
Python pipeline (unchanged)  →  results/*.json  →  static TS/React app  →  Vercel
     the analysis engine         the contract         the interface
```

The Python side keeps doing what it does well and gains an export step that writes JSON instead of only CSV. The front end is a static site that fetches those files. No API, no database, no hosting cost, no cold starts — and the analysis stays reproducible and inspectable, which is the thing that makes the repo credible in the first place.

### The four components worth building, in order

**1. Cohort explorer (build this first).**
Filter the docket by venue, complexity, claim band and filing period; every chart re-renders against the filtered cohort, with the sample size always visible. The reason this comes first is not visual — it is that **it makes censoring tangible**. Let the user drag the snapshot date and watch the naive median and the Kaplan-Meier median pull apart in real time. That interaction teaches the central point of your whole project in about four seconds, which no amount of README prose achieves.

**2. Client-side duration predictor — and it needs no backend at all.**

This is the technical insight that makes the whole thing tractable. A Log-Normal AFT model is a linear predictor in log-time:

```
log(T) = β'x + σ·ε
```

So the predicted median duration is simply `exp(β'x)`, and the survival curve is

```
S(t) = 1 − Φ( (log t − β'x) / σ )
```

Both are a dot product and a normal CDF. **Export your fitted coefficients and σ as a small JSON file and the entire predictive model runs in the browser in about thirty lines of JavaScript.** No Python service, no inference endpoint, no latency. The user moves sliders for complexity, venue and motion count; the survival curve redraws live.

**I verified this against your actual fitted model rather than assuming it.** Recomputing a prediction by hand from the exported coefficients, exactly as a browser would, against `lifelines`' own `predict_median` and `predict_survival_function`:

```
sigma = 0.410838
median   hand-computed  385.6948   lifelines  385.6948   difference  0.0
S(365)   hand-computed  0.553392   lifelines  0.553392   difference  1.11e-16
```

Identical to machine precision. Your entire predictive model serialises to **11 coefficients, an intercept and a sigma — 765 bytes of JSON.** There is no technical reason for a backend to exist in this project.

One caveat worth stating in the UI: point predictions from an AFT model are medians, not expectations, and the σ term means the spread around them is wide. Render the interval by default and make it hard to read the central estimate in isolation.

Add the confidence band, always. And label the output *"expected duration for a matter with these characteristics"* — never *"your case will take."*

**3. Judge variance panel — with the anonymisation constraint visible.**
Grant rates with Wilson intervals, ordered, panel rate marked, outliers highlighted only where the interval genuinely excludes the panel rate. Make the interval the visual hero: a wide interval on a small sample should *look* uncertain. Surface the jurisdiction note from Phase 1 in the interface itself, not buried in docs — a tooltip explaining why judges are anonymised, with the French statute cited, turns a chart into a product decision.

**4. Downloadable matter report.**
Select a cohort, export a two-page PDF: cohort definition, censoring-corrected duration estimates with intervals, recovery distribution, methodology note, data-provenance statement, generation date. Client-side generation, no server.

This is the component that reads as *legal tech* rather than *data science*, because it produces the artefact a legal team actually circulates. Make the provenance statement unmissable — a report that travels away from your repo must still disclose that its underlying data is synthetic.

### One thing not to build

Do not build a per-case outcome predictor — *"will I win?"* Three reasons, and being able to give them is worth more than the feature: your sample supports portfolio-level statements and not individual-case advice; predicting outcomes from case characteristics slides toward something a regulator would treat as legal advice; and it is the exact use case that got judicial analytics banned in France. Declining to build it, and explaining why, demonstrates the professional judgement that legal tech employers are actually screening for.

---

## Phase 3 — Architecture and technical polish

### Already done (delivered separately)

- 27-test suite: reproducibility, data integrity, methodological guarantees, README-to-results consistency. Mutation-tested — every test was verified capable of failing.
- CI that re-runs the pipeline and fails on stale committed outputs.
- Deterministic chart output (Plotly's random container id pinned).
- Fabricated judge names removed, with a test preventing their return.
- `Faker` dropped as an unused dependency.

### Next, in priority order

**1. Split generation from analysis properly.** Once real data arrives you will have two sources feeding one analysis layer. Restructure now, while it is cheap:

```
src/
├── sources/       synthetic.py, fjc_idb.py, courtlistener.py   → one canonical schema
├── analysis/      duration.py, recovery.py, judicial.py, survival.py
├── export/        tables.py, charts.py, web_json.py
└── schema.py      the contract every source must satisfy
```

The single most valuable file there is `schema.py`. Define the canonical case record once, validate every source against it, and swapping data sources becomes a config change rather than a rewrite. Do this *before* Phase 1 Tier B, not after.

**2. Edge cases that real data will force on you, and synthetic data hides.** Your generator produces impossibly clean data — the README admits it. Each of these is a real defect class:

- cases terminated the same day they were filed (zero duration breaks log-time models)
- termination dates before filing dates (real IDB rows have this)
- venue strings that differ by whitespace, case, or abbreviation
- the same case appearing twice after transfer between districts
- awards recorded in the wrong currency unit
- cases pending for longer than the observation window

Write the guards as tests first, then implement. Two of the six will fire on real data on day one.

**3. Dependency hygiene.** Your pins are fine — I incorrectly reported otherwise earlier; installed as your README instructs, they resolve cleanly. Worth adding: a `constraints.txt` for reproducible CI, and Dependabot so the pins do not silently rot.

**4. Type hints and a linter.** You are already using `from __future__ import annotations`. Add `ruff` and `mypy` to CI. For an AI-assisted codebase this matters more than usual: type errors are the failure mode that AI-generated code produces most reliably and reviewers catch least.

---

## Phase 4 — Documentation and storytelling

The rewritten README already covers problem statement, target user, data sources with links, architecture, the honest AI-assistance note, and *what I'd improve next*. Rather than restate it, here is the one thing to strengthen as the project grows.

### Make legal reasoning visibly cause technical decisions

You asked how to highlight that your legal knowledge drove the software logic. The answer is not a section headed *"My Legal Knowledge."* It is a consistent pattern, repeated, where a legal fact forces a code decision — stated in that order, with the code visible.

You now have five of these, and they are strong:

| Legal fact | Technical consequence |
|---|---|
| French Article 33 criminalises identifying judges in analytics | Anonymisation enforced by test, not convention |
| CPR 24.3 and FRCP 56(a) apply different summary-judgment tests | Grant rates compared within a court, never across jurisdictions |
| 94% of County Court judgments are default judgments | Undefended cases modelled as a distinct path with no judicial effect |
| Litigation data is generated by a process still running | Censoring handled by survival methods rather than dropping open cases |
| Settlement and dismissal are legally distinct outcomes | Competing-risks model rather than one undifferentiated "resolution" |

Put that table in the README under a heading like **"Where the law shaped the code."** It is the single highest-signal artefact you can put in front of a legal tech hiring manager, because the failure mode of the entire field is engineers building legal products without knowing any law. That table is the proof you are the other thing.

### Keep the AI-assistance note

It is a strength, not a confession — but only because it is paired with verification. The credibility comes from the pairing. Never let the note stand alone, and never quietly drop it as the project gets more impressive.

---

## Sequencing

| Order | Work | Rough effort | Why here |
|---|---|---|---|
| 1 | Tier A calibration + `docs/calibration.md` | ~1 day | Highest credibility per hour in the whole plan |
| 2 | Model undefended claims (the 94% finding) | 1–2 days | Best legal-domain signal available cheaply |
| 3 | `schema.py` + source/analysis/export split | 2–3 days | Must precede real data or you rewrite it twice |
| 4 | Partial pooling for judge effects | 2–3 days | Biggest statistical upgrade; makes findings *more* honest |
| 5 | JSON export + cohort explorer | ~1 week | First point at which it becomes a product |
| 6 | Client-side AFT predictor | 2–3 days | Highest impression-per-hour of any UI work |
| 7 | FJC IDB integration (Tier B) | 1–2 weeks | Transformative, but only on the structure from step 3 |
| 8 | Downloadable report + judge panel | ~1 week | Polish, once the data underneath is real |
| 9 | Calibration curves, snapshot sensitivity, competing risks | ongoing | Depth for interview conversations |

Steps 1–4 are roughly a week and take the project from *"good student work"* to *"this person understands their own limitations."* Steps 5–7 take it to *"this is a product built by someone who knows the law."*

---

## What I would check, if I were hiring you

In this order, in about ten minutes:

1. **Does the README tell me what is real?** Yours does, in the first screen. Most do not. You pass a filter here that eliminates most candidates.
2. **Do the numbers in the README match the outputs?** Yours are tested. Almost nobody does this.
3. **Is there anything that only a lawyer would have done?** The "where the law shaped the code" table answers this in fifteen seconds.
4. **What happens when I run it?** It runs, and CI proves it runs on a machine that is not yours.
5. **Does the candidate know what is wrong with it?** Your Limitations section is the strongest part of the repository. Do not let it get shorter as the project gets better.

Point 5 is the one to protect. The instinct to publish the flaws alongside the findings is rarer than any technical skill in this plan, and it is the thing that will actually get you hired.

---

## Sources

- [Civil Justice Statistics Quarterly: January to March 2026 — GOV.UK](https://www.gov.uk/government/statistics/civil-justice-statistics-quarterly-january-to-march-2026/civil-justice-statistics-quarterly-january-to-march-2026)
- [Federal Court Cases: FJC Integrated Database 1979 to Present — Federal Judicial Center](https://www.fjc.gov/research/federal-court-cases-fjc-integrated-database-1979-present)
- [Facts about FJC's Integrated Database — Free Law Project](https://free.law/idb-facts/) (judge fields withheld; truncation; quarterly lag)
- [CourtListener APIs, Webhooks, and Bulk Legal Data](https://www.courtlistener.com/help/api/)
- [Full CourtListener Data Access via API Now Included with Membership — Free Law Project](https://free.law/2026/05/07/api-included-in-memberships/) (free EDU membership)
- [France bans publishing of judicial analytics and prompts criminal penalty — ABA Journal](https://www.abajournal.com/news/article/france-bans-and-creates-criminal-penalty-for-judicial-analytics)
- [Publication of "Judicial Analytics" a criminal offence in France — Article 33 of Justice Reform Act — SCC Times](https://www.scconline.com/blog/post/2019/06/12/publication-of-judicial-analytics-a-criminal-offence-in-france-article-33-of-justice-reform-act/)
- [CPR Part 24 — legislation.gov.uk](https://www.legislation.gov.uk/uksi/1998/3132/part/24)
- [FRCP Rule 56 — Cornell LII](https://www.law.cornell.edu/rules/frcp/rule_56)
