"""
Litigation & Court Data Analytics — comparison cohort: general civil claims
===========================================================================

Why this file exists
--------------------
The main docket in this repository models *commercial* disputes: claims of
£50,000 to £10,000,000 between represented parties, all of which are defended.
That population is real, but it is a tiny and deeply unrepresentative slice of
civil litigation.

The national picture looks nothing like it. In England & Wales in Q1 2026
[MoJ]:

    527,000 County Court claims issued
     72,000 defended                     ->  13.7% defence rate
    256,000 judgments, of which 94% were DEFAULT judgments
     13,000 trials

So roughly six in seven civil claims are never defended at all. The defendant
does not file an acknowledgment of service, the deadline expires, and judgment
is entered administratively. No hearing, no judge exercising discretion, no
summary judgment, no settlement negotiation. Most civil litigation is not
litigation in any adversarial sense — it is bulk debt recovery.

This module generates that population so the two can be compared directly.

The point of the comparison
---------------------------
"How long does a civil claim take?" has no single answer, and the difference
between the two cohorts is almost entirely COMPOSITION rather than speed. A
defended claim in this cohort takes a comparable time to a commercial dispute.
The national median is short only because it is dominated by cases that end
without anyone defending them.

Quoting a national average duration to a commercial client is therefore
meaningless — and it is exactly the kind of number that ends up in a pitch
deck. Demonstrating why is the purpose of this cohort.

Procedural grounding
--------------------
The duration floor for an undefended claim is not arbitrary. Under CPR 10.3 a
defendant has 14 days after service to file an acknowledgment of service, and
CPR 15.4 extends the period for filing a defence to 28 days where an
acknowledgment is filed. Default judgment under CPR Part 12 is not available
until the relevant period has expired. No claim in this cohort therefore
resolves in fewer than 14 days.

    [MoJ] Civil Justice Statistics Quarterly, England & Wales,
          January to March 2026 (Ministry of Justice)

IMPORTANT — this is synthetic data, like everything else in this repository.
See docs/calibration.md for which parameters are anchored to published figures
and which are modelling choices.

Usage
-----
    python src/generate_general_civil.py

Output
------
    data/general_civil_claims.csv
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

SEED = 42
N_CLAIMS = 20_000

FILING_START = pd.Timestamp("2022-01-01")
FILING_END = pd.Timestamp("2025-12-31")
AS_OF = pd.Timestamp("2026-06-30")

OUTPUT_DIR = ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "general_civil_claims.csv"

rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# CALIBRATION — see docs/calibration.md
# ---------------------------------------------------------------------------

# [MoJ] 72,000 of 527,000 claims defended in Q1 2026.
DEFENCE_RATE = 72_000 / 527_000                    # 0.1366

# [MoJ] 13,000 trials against 72,000 defended claims. Crude ratio across the
# same quarter rather than a tracked cohort, so treated as approximate.
TRIAL_RATE_GIVEN_DEFENDED = 13_000 / 72_000        # 0.1806

# [MoJ] DERIVED, and the least obvious figure in this file.
#
# 256,000 judgments were given, of which 94% were default judgments — so
# 240,640 default judgments against 455,000 undefended claims. Only 52.9% of
# undefended claims therefore produce a judgment at all.
#
# The other 47% are paid, settled or discontinued without any judgment being
# entered. A claimant who issues proceedings and is paid the following week
# does not go on to ask the court for judgment. An earlier version of this
# module assumed undefended meant default judgment, which pushed defaults to
# 97.4% of all judgments against a published 94%. The gap was the tell.
DEFAULT_JUDGMENT_RATE_GIVEN_UNDEFENDED = (0.94 * 256_000) / 455_000   # 0.529

# [MoJ] Median time from claim issue to trial, Q1 2026.
SMALL_CLAIMS_TRIAL_DAYS = 37.6 * 7                 # 263.2
MULTI_TRACK_TRIAL_DAYS = 54.3 * 7                  # 380.1

# Small claims track limit. Determines which published median applies.
SMALL_CLAIMS_LIMIT_GBP = 10_000

# CPR 10.3 — 14 days to acknowledge service. CPR Part 12 default judgment is
# not available before the relevant period expires, so this is a hard floor.
MIN_DAYS_TO_DEFAULT_JUDGMENT = 14

# NOT CALIBRATED. No published median exists for time from issue to entry of
# default judgment. Reasoned from the procedural floor above plus court
# administration time. Documented as a modelling choice in docs/calibration.md.
DEFAULT_JUDGMENT_MEDIAN_DAYS = 52

# NOT CALIBRATED. Claims paid or discontinued without judgment. Faster than a
# default judgment, since no court step is required at all.
PAID_OR_DISCONTINUED_MEDIAN_DAYS = 33

# NOT CALIBRATED. Defended claims that do not reach trial settle or are
# discontinued partway through the timetable.
SETTLE_FRACTION_OF_TRIAL_TIMELINE = 0.60


def draw_claim_amounts(n: int) -> np.ndarray:
    """County Court money claims, heavily weighted to low values.

    Calibrated in shape rather than to a published distribution: the MoJ does
    not publish a claim-value distribution. The target is that roughly
    three-quarters of claims fall within the small claims limit, which is
    consistent with small claims dominating the caseload by volume.
    """
    lo, hi = 100.0, 100_000.0
    out = np.empty(n)
    remaining = np.arange(n)
    while remaining.size:
        draw = rng.lognormal(mean=7.9, sigma=1.35, size=remaining.size)
        ok = (draw >= lo) & (draw <= hi)
        out[remaining[ok]] = draw[ok]
        remaining = remaining[~ok]
    return np.round(out, 2)


def generate() -> pd.DataFrame:
    n = N_CLAIMS

    filing_span = (FILING_END - FILING_START).days
    filing_date = FILING_START + pd.to_timedelta(
        rng.integers(0, filing_span + 1, size=n), unit="D"
    )
    filing_year = filing_date.year.to_numpy()
    seq = pd.Series(filing_year).groupby(filing_year).cumcount() + 1
    claim_id = [f"GC-{y}-{s:05d}" for y, s in zip(filing_year, seq)]

    claim_amount = draw_claim_amounts(n)
    small_claim = claim_amount <= SMALL_CLAIMS_LIMIT_GBP

    # --- Is the claim defended? --------------------------------------------
    # Larger claims are defended more often — a defendant facing £40,000 has
    # more reason to instruct solicitors than one facing £400. The size effect
    # is centred so the overall rate still lands on the published 13.7%.
    log_amt_z = (np.log(claim_amount) - np.log(claim_amount).mean()) / np.log(claim_amount).std()

    # Solve the intercept so that the AVERAGE defence probability lands on the
    # published rate. Setting the intercept to logit(0.137) directly does not
    # work: the sigmoid is non-linear, so averaging over the claim-size term
    # pulls the realised rate above the target (an instance of Jensen's
    # inequality). An earlier version made exactly that mistake and produced a
    # 15.2% defence rate against a published 13.7%.
    size_term = 0.55 * log_amt_z

    def realised_rate(intercept: float) -> float:
        return float(np.mean(1.0 / (1.0 + np.exp(-(intercept + size_term)))))

    lo, hi = -6.0, 2.0
    for _ in range(60):                     # bisection; converges well past float precision
        mid = (lo + hi) / 2
        if realised_rate(mid) < DEFENCE_RATE:
            lo = mid
        else:
            hi = mid
    defence_intercept = (lo + hi) / 2

    defended = rng.random(n) < 1.0 / (1.0 + np.exp(-(defence_intercept + size_term)))

    # --- Disposition --------------------------------------------------------
    # Undefended -> about half produce a default judgment; the rest are paid,
    #               settled or discontinued with no judgment entered at all.
    # Defended   -> a minority reach trial; the rest settle or discontinue.
    default_judgment = ~defended & (
        rng.random(n) < DEFAULT_JUDGMENT_RATE_GIVEN_UNDEFENDED
    )
    paid_or_discontinued = ~defended & ~default_judgment
    reaches_trial = defended & (rng.random(n) < TRIAL_RATE_GIVEN_DEFENDED)
    settles = defended & ~reaches_trial

    disposition_type = np.where(
        default_judgment, "Default Judgment",
        np.where(paid_or_discontinued, "Paid or discontinued",
                 np.where(reaches_trial, "Trial Judgment", "Settled")),
    )

    # --- Time to resolution -------------------------------------------------
    # Trial cases are anchored to the published track medians. Everything else
    # is expressed as a fraction of, or floor above, those anchors.
    trial_anchor = np.where(small_claim, SMALL_CLAIMS_TRIAL_DAYS, MULTI_TRACK_TRIAL_DAYS)

    noise = rng.normal(0.0, 0.42, size=n)

    log_days = np.where(
        default_judgment,
        np.log(DEFAULT_JUDGMENT_MEDIAN_DAYS - MIN_DAYS_TO_DEFAULT_JUDGMENT),
        np.where(
            paid_or_discontinued,
            np.log(PAID_OR_DISCONTINUED_MEDIAN_DAYS),
            np.where(
                reaches_trial,
                np.log(trial_anchor),
                np.log(trial_anchor * SETTLE_FRACTION_OF_TRIAL_TIMELINE),
            ),
        ),
    ) + noise

    # The CPR 10.3 floor applies only to DEFAULT JUDGMENT, which cannot be
    # entered until the acknowledgment period has expired. A defendant who
    # simply pays on receipt of the claim form is under no such constraint and
    # can end the matter in days — so no floor is imposed on that path.
    raw = np.exp(log_days)
    true_duration = np.where(default_judgment, raw + MIN_DAYS_TO_DEFAULT_JUDGMENT, raw)
    true_duration = np.clip(np.round(true_duration), 1, None).astype(int)

    # --- Right-censoring ----------------------------------------------------
    modelled_disposition = filing_date + pd.to_timedelta(true_duration, unit="D")
    resolved = modelled_disposition <= AS_OF

    days_to_resolution = np.where(resolved, true_duration, (AS_OF - filing_date).days).astype(int)
    disposition_date = pd.Series(modelled_disposition).where(pd.Series(resolved))
    case_status = np.where(resolved, "Resolved", "Ongoing")
    disposition_final = pd.Series(disposition_type).where(pd.Series(resolved))
    event_observed = resolved.astype(int)

    # --- Financial outcome --------------------------------------------------
    # A default judgment is entered for the sum claimed. That is a judgment,
    # NOT money received: enforcing against a defendant who never engaged with
    # the proceedings is a separate problem, and this dataset does not model
    # enforcement at all. See the limitation noted in docs/calibration.md.
    award = np.zeros(n)
    award = np.where(default_judgment, claim_amount, award)

    # NOT CALIBRATED. "Paid or discontinued" mixes two opposite outcomes — a
    # claim paid in full, and a claim abandoned for nothing — which the
    # published statistics do not separate. Modelled as a wide distribution
    # skewed towards recovery, and flagged in docs/calibration.md.
    ratio_paid = rng.beta(4.0, 2.0, size=n)
    award = np.where(paid_or_discontinued,
                     claim_amount * np.clip(ratio_paid, 0.0, 1.0), award)

    ratio_settled = rng.beta(2.5, 3.0, size=n)
    award = np.where(settles, claim_amount * np.clip(ratio_settled, 0.01, 0.95), award)

    claimant_wins = rng.random(n) < 0.62
    ratio_trial = rng.beta(3.0, 2.0, size=n)
    award = np.where(reaches_trial & claimant_wins,
                     claim_amount * np.clip(ratio_trial, 0.02, 1.00), award)
    award = np.where(reaches_trial & ~claimant_wins, 0.0, award)
    award = np.where(resolved, np.round(award, 2), np.nan)

    df = pd.DataFrame(
        {
            "claim_id": claim_id,
            "filing_date": filing_date,
            "claim_amount_gbp": claim_amount,
            "track": np.where(small_claim, "Small claims", "Fast/multi-track"),
            "defended": defended,
            "disposition_type": disposition_final,
            "disposition_date": disposition_date,
            "days_to_resolution": days_to_resolution,
            "final_awarded_amount_gbp": award,
            "case_status": case_status,
            "event_observed": event_observed,
        }
    )
    return df.sort_values("filing_date").reset_index(drop=True)


def validate(df: pd.DataFrame) -> None:
    assert len(df) == N_CLAIMS, "row count mismatch"
    assert df["claim_id"].is_unique, "duplicate claim ids"

    # Default judgment cannot be entered before the CPR 10.3 acknowledgment
    # period expires. This constraint binds only on that path — a defendant who
    # pays on receipt is under no such restriction.
    dj_rows = df["disposition_type"] == "Default Judgment"
    assert (df.loc[dj_rows, "days_to_resolution"] >= MIN_DAYS_TO_DEFAULT_JUDGMENT).all(), \
        "default judgment entered before the CPR 10.3 acknowledgment period expired"
    assert (df["days_to_resolution"] >= 1).all(), "non-positive duration"

    resolved = df["case_status"] == "Resolved"
    assert df.loc[resolved, "disposition_type"].notna().all(), "resolved case with no disposition"
    assert df.loc[~resolved, "disposition_date"].isna().all(), "ongoing case has a disposition date"

    # Only defended claims can settle or be tried; only undefended claims can
    # end in default judgment. This is the definitional core of the cohort.
    defended_dispositions = set(
        df.loc[resolved & df["defended"], "disposition_type"].unique()
    )
    assert defended_dispositions <= {"Settled", "Trial Judgment"}, \
        f"defended claim with an impossible disposition: {defended_dispositions}"
    undefended = df.loc[resolved & ~df["defended"], "disposition_type"].unique()
    assert set(undefended) <= {"Default Judgment", "Paid or discontinued"}, \
        f"undefended claim with an impossible disposition: {set(undefended)}"

    # A default judgment is entered for the full sum claimed.
    dj = resolved & (df["disposition_type"] == "Default Judgment")
    assert np.allclose(df.loc[dj, "final_awarded_amount_gbp"],
                       df.loc[dj, "claim_amount_gbp"]), \
        "default judgment not entered for the sum claimed"

    print("[OK] All integrity checks passed.")


def summarise(df: pd.DataFrame) -> None:
    res = df[df["event_observed"] == 1]
    print(f"\nRows: {len(df):,}")
    print(f"Defence rate: {df['defended'].mean():.1%}  (published: {DEFENCE_RATE:.1%})")
    print(f"Right-censored (still open): {(df['case_status'] == 'Ongoing').mean():.1%}")

    print("\nDisposition mix (resolved):")
    print((res["disposition_type"].value_counts(normalize=True) * 100).round(1).to_string())

    dj_share = (res["disposition_type"] == "Default Judgment").mean()
    judgments = res[res["disposition_type"].isin(["Default Judgment", "Trial Judgment"])]
    dj_of_judgments = (judgments["disposition_type"] == "Default Judgment").mean()
    print(f"\nDefault judgments as a share of all judgments: {dj_of_judgments:.1%}"
          f"  (published: 94%)")
    print(f"Default judgments as a share of all disposals:  {dj_share:.1%}")

    print("\nMedian days to resolution:")
    print(f"  All claims:      {res['days_to_resolution'].median():>6.0f}")
    print(f"  Undefended only: {res.loc[~res['defended'], 'days_to_resolution'].median():>6.0f}")
    print(f"  Defended only:   {res.loc[res['defended'], 'days_to_resolution'].median():>6.0f}")

    print("\nMedian days to trial, defended claims reaching trial:")
    tr = res[res["disposition_type"] == "Trial Judgment"]
    print(tr.groupby("track")["days_to_resolution"].median().to_string())
    print(f"  published anchors: Small claims {SMALL_CLAIMS_TRIAL_DAYS:.0f} d, "
          f"Fast/multi {MULTI_TRACK_TRIAL_DAYS:.0f} d")

    print(f"\nClaim amount — median £{df['claim_amount_gbp'].median():,.0f} | "
          f"share within small claims limit: {(df['claim_amount_gbp'] <= SMALL_CLAIMS_LIMIT_GBP).mean():.1%}")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = generate()
    validate(data)
    summarise(data)
    data.to_csv(OUTPUT_FILE, index=False)
    print(f"\nWritten → {OUTPUT_FILE}")
