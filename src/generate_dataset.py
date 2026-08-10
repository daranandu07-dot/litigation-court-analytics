"""
Litigation & Court Data Analytics — Phase 1: Synthetic Dataset Generation
========================================================================

Business problem
----------------
"Analyzing Litigation Bottlenecks, Judge Motion-Grant Variances, and Settlement
Predictors in Commercial Contract Disputes."

This script generates a 5,000-row synthetic docket of commercial contract
disputes. The data is *engineered to contain recoverable signal* so that the
Phase 2 statistical models have something real to find:

  1. BOTTLENECKS      - venue and complexity shift the duration distribution.
  2. JUDGE VARIANCE   - each judge carries a fixed log-odds random effect on
                        summary-judgment grants, including two deliberate
                        outliers (one grant-prone, one grant-averse).
  3. SETTLEMENT       - disposition probabilities depend on complexity, claim
                        size, and whether summary judgment was granted.
  4. CENSORING        - cases whose modelled disposition date falls after the
                        AS_OF snapshot date are left OPEN and right-censored.
                        This is what makes Kaplan-Meier / Cox meaningful in
                        Phase 2 rather than a trivial ECDF.

IMPORTANT — this is synthetic data. Parameters are plausible-looking but are
NOT calibrated against any published court statistics. It demonstrates method,
not empirical fact. See the "Data provenance" note in the README.

Usage
-----
    pip install -r requirements.txt
    python src/generate_dataset.py

Output
------
    data/litigation_court_data.csv
"""

from __future__ import annotations

import os

from pathlib import Path

# Resolve paths relative to the repository root, not the working
# directory, so the scripts run correctly from anywhere.
ROOT = Path(__file__).resolve().parents[1]

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

SEED = 42
N_CASES = 5_000

FILING_START = pd.Timestamp("2022-01-01")
FILING_END = pd.Timestamp("2025-12-31")

# Snapshot date for the analysis. Cases not resolved by this date are OPEN
# and become right-censored observations in the survival model.
AS_OF = pd.Timestamp("2026-06-30")

OUTPUT_DIR = ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "litigation_court_data.csv"

rng = np.random.default_rng(SEED)
fake = Faker("en_GB")
Faker.seed(SEED)

# ---------------------------------------------------------------------------
# REFERENCE DIMENSIONS
# ---------------------------------------------------------------------------

# Venue -> (sampling weight, log-duration offset)
# Positive offset = slower venue. Offsets are in log-days.
VENUES = {
    "London Commercial Court":        (0.24,  0.00),
    "High Court — Chancery Division": (0.18,  0.14),
    "High Court — KBD (TCC)":         (0.13,  0.22),
    "US District Court — S.D.N.Y.":   (0.16, -0.06),
    "US District Court — N.D. Cal.":  (0.11,  0.09),
    "Singapore International Comm.":  (0.10, -0.18),
    "Dubai International Fin. Centre": (0.08, -0.11),
}

VENUE_NAMES = list(VENUES.keys())
VENUE_WEIGHTS = np.array([v[0] for v in VENUES.values()], dtype=float)
VENUE_WEIGHTS /= VENUE_WEIGHTS.sum()
VENUE_DURATION_OFFSET = {k: v[1] for k, v in VENUES.items()}

COMPLEXITY_LEVELS = ["Low", "Medium", "High"]
COMPLEXITY_WEIGHTS = [0.38, 0.42, 0.20]

# Baseline log-days to resolution by complexity (exp -> ~250 / ~380 / ~570 days)
COMPLEXITY_BASE_LOG_DAYS = {"Low": 5.52, "Medium": 5.94, "High": 6.34}

# Effect of complexity on the log-odds of a summary-judgment GRANT.
# Complex cases have more genuine triable issues -> harder to win on SJ.
COMPLEXITY_SJ_EFFECT = {"Low": 0.45, "Medium": 0.00, "High": -0.55}

N_JUDGES = 10

# Judges are NESTED WITHIN VENUES — a judge sits in exactly one court, as in
# reality. Seat counts roughly track each venue's share of the caseload.
#
# JUD-01 (grant-prone) and JUD-02 (grant-averse) are deliberately seated in the
# SAME court. That gives Phase 2 a clean within-venue contrast: two judges on
# the same bench hearing comparable cases with opposite summary-judgment
# postures, which cannot be explained away as a venue effect.
JUDGE_SEATS = {
    "London Commercial Court":        ["JUD-01", "JUD-02"],
    "High Court — Chancery Division": ["JUD-03", "JUD-04"],
    "High Court — KBD (TCC)":         ["JUD-05"],
    "US District Court — S.D.N.Y.":   ["JUD-06", "JUD-07"],
    "US District Court — N.D. Cal.":  ["JUD-08"],
    "Singapore International Comm.":  ["JUD-09"],
    "Dubai International Fin. Centre": ["JUD-10"],
}


def build_judge_panel() -> pd.DataFrame:
    """Ten judges, each seated in one venue, each with a fixed random effect
    on summary-judgment grant log-odds.

    Two judges are hard-coded as outliers so that Phase 2's variance analysis
    has an unambiguous signal to detect. The remaining eight are drawn from a
    normal distribution around zero.
    """
    effects = rng.normal(loc=0.0, scale=0.42, size=N_JUDGES)
    effects[0] = 1.35   # notably grant-prone ("rocket docket" judge)
    effects[1] = -1.25  # notably grant-averse (prefers a full trial record)

    # Judicial effect on case pace, independent of summary-judgment posture.
    pace = rng.normal(loc=0.0, scale=0.10, size=N_JUDGES)

    judge_ids = [f"JUD-{i + 1:02d}" for i in range(N_JUDGES)]
    seat_of = {j: v for v, js in JUDGE_SEATS.items() for j in js}

    return pd.DataFrame(
        {
            "judge_id": judge_ids,
            "judge_name": [f"Hon. {fake.last_name()}" for _ in range(N_JUDGES)],
            "court_venue": [seat_of[j] for j in judge_ids],
            "sj_effect": effects,
            "pace_effect": pace,
        }
    )


JUDGES = build_judge_panel()

# Fail at import time if the seating chart and the venue list ever drift apart.
assert set(JUDGE_SEATS) == set(VENUE_NAMES), "every venue must have a bench"
assert sum(len(v) for v in JUDGE_SEATS.values()) == N_JUDGES, "seat count mismatch"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def draw_claim_amounts(n: int) -> np.ndarray:
    """Right-skewed log-normal claim values, bounded to £50k–£10m.

    Resampling (rather than clipping) preserves the shape of the distribution
    inside the bounds instead of piling probability mass on the two endpoints.
    """
    lo, hi = 50_000.0, 10_000_000.0
    out = np.empty(n)
    remaining = np.arange(n)
    while remaining.size:
        draw = rng.lognormal(mean=13.15, sigma=1.05, size=remaining.size)
        ok = (draw >= lo) & (draw <= hi)
        out[remaining[ok]] = draw[ok]
        remaining = remaining[~ok]
    return np.round(out, 2)


# ---------------------------------------------------------------------------
# GENERATION
# ---------------------------------------------------------------------------

def generate() -> pd.DataFrame:
    n = N_CASES

    # --- Case characteristics ---------------------------------------------
    court_venue = rng.choice(VENUE_NAMES, size=n, p=VENUE_WEIGHTS)

    # Assign each case to a judge who actually sits in that venue, drawn
    # uniformly from that court's bench (i.e. random docket allocation).
    judge_pos = {jid: i for i, jid in enumerate(JUDGES["judge_id"])}
    judge_idx = np.empty(n, dtype=int)
    for venue, bench in JUDGE_SEATS.items():
        mask = court_venue == venue
        seats = np.array([judge_pos[j] for j in bench])
        judge_idx[mask] = rng.choice(seats, size=int(mask.sum()))

    judge_id = JUDGES["judge_id"].to_numpy()[judge_idx]
    judge_sj_effect = JUDGES["sj_effect"].to_numpy()[judge_idx]
    judge_pace_effect = JUDGES["pace_effect"].to_numpy()[judge_idx]

    case_complexity = rng.choice(COMPLEXITY_LEVELS, size=n, p=COMPLEXITY_WEIGHTS)

    filing_span = (FILING_END - FILING_START).days
    filing_date = FILING_START + pd.to_timedelta(
        rng.integers(0, filing_span + 1, size=n), unit="D"
    )

    # Court-style reference: CC-<filing year>-<sequence within that year>
    filing_year = filing_date.year.to_numpy()
    seq = pd.Series(filing_year).groupby(filing_year).cumcount() + 1
    case_id = [f"CC-{y}-{s:04d}" for y, s in zip(filing_year, seq)]

    claim_amount = draw_claim_amounts(n)
    log_claim_z = (np.log(claim_amount) - np.log(claim_amount).mean()) / np.log(
        claim_amount
    ).std()

    # --- Interlocutory motions --------------------------------------------
    # Poisson rate rises with complexity and (mildly) with claim size.
    motion_lambda = (
        pd.Series(case_complexity).map({"Low": 1.1, "Medium": 2.3, "High": 4.0}).to_numpy()
        + 0.35 * np.clip(log_claim_z, -2, 3)
    )
    num_interlocutory_motions = rng.poisson(np.clip(motion_lambda, 0.2, None))

    # --- Summary judgment --------------------------------------------------
    sj_file_logit = (
        -0.55
        + 0.30 * log_claim_z
        + 0.12 * num_interlocutory_motions
        + pd.Series(case_complexity).map({"Low": 0.25, "Medium": 0.0, "High": -0.15}).to_numpy()
    )
    summary_judgment_filed = rng.random(n) < sigmoid(sj_file_logit)

    sj_grant_logit = (
        -1.05
        + judge_sj_effect
        + pd.Series(case_complexity).map(COMPLEXITY_SJ_EFFECT).to_numpy()
        - 0.18 * log_claim_z
        - 0.06 * num_interlocutory_motions
    )
    summary_judgment_granted = summary_judgment_filed & (
        rng.random(n) < sigmoid(sj_grant_logit)
    )

    # --- Disposition type --------------------------------------------------
    # Multinomial over [Settled, Dismissed, Trial Judgment] via softmax-style
    # utilities. A granted SJ overwhelmingly ends the case by dismissal.
    u_settled = (
        1.55
        + 0.22 * log_claim_z
        + pd.Series(case_complexity).map({"Low": -0.10, "Medium": 0.10, "High": 0.30}).to_numpy()
        + 0.05 * num_interlocutory_motions
    )
    u_dismissed = 0.60 - 0.15 * log_claim_z + 3.20 * summary_judgment_granted
    u_trial = -0.15 + 0.18 * log_claim_z + 0.30 * (case_complexity == "High")

    utils = np.column_stack([u_settled, u_dismissed, u_trial])
    probs = np.exp(utils)
    probs /= probs.sum(axis=1, keepdims=True)

    # Vectorised categorical sampling via the Gumbel-max trick.
    gumbel = -np.log(-np.log(rng.random(probs.shape)))
    choice_idx = np.argmax(np.log(probs) + gumbel, axis=1)
    disposition_type = np.array(["Settled", "Dismissed", "Trial Judgment"])[choice_idx]

    # --- Time to resolution -------------------------------------------------
    log_days = (
        pd.Series(case_complexity).map(COMPLEXITY_BASE_LOG_DAYS).to_numpy()
        + pd.Series(court_venue).map(VENUE_DURATION_OFFSET).to_numpy()
        + judge_pace_effect
        + 0.055 * num_interlocutory_motions
        + 0.10 * summary_judgment_filed
        - 0.38 * summary_judgment_granted          # a granted SJ ends it early
        + 0.11 * np.clip(log_claim_z, -2, 3)
        + pd.Series(disposition_type)
        .map({"Settled": 0.0, "Dismissed": -0.22, "Trial Judgment": 0.46})
        .to_numpy()
        + rng.normal(0.0, 0.33, size=n)
    )
    true_duration = np.clip(np.round(np.exp(log_days)), 30, None).astype(int)

    # --- Right-censoring at the snapshot date ------------------------------
    modelled_disposition = filing_date + pd.to_timedelta(true_duration, unit="D")
    resolved = modelled_disposition <= AS_OF

    days_to_resolution = np.where(
        resolved, true_duration, (AS_OF - filing_date).days
    ).astype(int)

    disposition_date = pd.Series(modelled_disposition).where(pd.Series(resolved))

    case_status = np.where(resolved, "Resolved", "Ongoing")
    disposition_type_final = pd.Series(disposition_type).where(pd.Series(resolved))
    event_observed = resolved.astype(int)  # lifelines convention: 1 = event

    # --- Financial outcome --------------------------------------------------
    final_award = np.zeros(n)

    settled = resolved & (disposition_type == "Settled")
    # Recovery ratio ~ Beta(2.2, 4.0) -> mean ≈ 0.35, long left tail.
    ratio_settled = rng.beta(2.2, 4.0, size=n)
    ratio_settled *= 1.0 + 0.10 * (case_complexity == "Low")   # cleaner liability
    ratio_settled -= 0.05 * summary_judgment_granted           # weakened position
    final_award = np.where(
        settled, claim_amount * np.clip(ratio_settled, 0.01, 0.95), final_award
    )

    # Dismissed -> claimant recovers nothing.
    # Trial judgment -> bimodal: ~32% defendant verdicts (zero), else strong award.
    trial = resolved & (disposition_type == "Trial Judgment")
    defendant_win = rng.random(n) < 0.32
    ratio_trial = rng.beta(3.0, 2.0, size=n)
    final_award = np.where(
        trial & ~defendant_win,
        claim_amount * np.clip(ratio_trial, 0.02, 1.00),
        final_award,
    )
    final_award = np.where(trial & defendant_win, 0.0, final_award)
    final_award = np.where(resolved, np.round(final_award, 2), np.nan)

    # --- Assemble -----------------------------------------------------------
    df = pd.DataFrame(
        {
            "case_id": case_id,
            "court_venue": court_venue,
            "judge_id": judge_id,
            "filing_date": filing_date,
            "case_complexity": pd.Categorical(
                case_complexity, categories=COMPLEXITY_LEVELS, ordered=True
            ),
            "claim_amount_gbp": claim_amount,
            "num_interlocutory_motions": num_interlocutory_motions,
            "summary_judgment_filed": summary_judgment_filed,
            "summary_judgment_granted": summary_judgment_granted,
            "disposition_type": disposition_type_final,
            "disposition_date": disposition_date,
            "days_to_resolution": days_to_resolution,
            "final_awarded_amount_gbp": final_award,
            # --- additions beyond the requested schema, required for survival
            #     analysis in Phase 2. Drop these two columns if you want the
            #     literal schema only.
            "case_status": case_status,
            "event_observed": event_observed,
        }
    )

    return df.sort_values("filing_date").reset_index(drop=True)


def validate(df: pd.DataFrame) -> None:
    """Fail loudly if the generated data violates its own logic."""
    assert len(df) == N_CASES, "row count mismatch"
    assert df["case_id"].is_unique, "duplicate case ids"
    assert df["claim_amount_gbp"].between(50_000, 10_000_000).all(), "claim out of range"
    assert not (df["summary_judgment_granted"] & ~df["summary_judgment_filed"]).any(), \
        "SJ granted without being filed"

    # Each judge must sit in exactly one court.
    seats = df.groupby("judge_id")["court_venue"].nunique()
    assert (seats == 1).all(), f"judge sitting in multiple venues: {seats[seats > 1]}"
    assert df["judge_id"].nunique() == N_JUDGES, "not every judge received cases"

    resolved = df["case_status"] == "Resolved"
    assert df.loc[resolved, "disposition_type"].notna().all(), "resolved case with no disposition"
    assert df.loc[~resolved, "disposition_date"].isna().all(), "ongoing case has disposition date"

    delta = (df.loc[resolved, "disposition_date"] - df.loc[resolved, "filing_date"]).dt.days
    assert (delta == df.loc[resolved, "days_to_resolution"]).all(), \
        "days_to_resolution does not reconcile with dates"

    dismissed = df["disposition_type"] == "Dismissed"
    assert (df.loc[dismissed, "final_awarded_amount_gbp"] == 0).all(), \
        "dismissed case with a non-zero award"
    print("[OK] All integrity checks passed.")


def summarise(df: pd.DataFrame) -> None:
    print(f"\nRows: {len(df):,}   Columns: {df.shape[1]}")
    print(f"Filing window: {df['filing_date'].min():%Y-%m-%d} → {df['filing_date'].max():%Y-%m-%d}")
    print(f"Snapshot (AS_OF): {AS_OF:%Y-%m-%d}")

    censored = (df["case_status"] == "Ongoing").mean()
    print(f"Right-censored (still open): {censored:.1%}")

    print("\nDisposition mix (resolved only):")
    print(df["disposition_type"].value_counts(normalize=True).round(3).to_string())

    print("\nMedian days to resolution by complexity (resolved only):")
    res = df[df["case_status"] == "Resolved"]
    print(res.groupby("case_complexity", observed=True)["days_to_resolution"]
            .median().to_string())

    print("\nSummary-judgment grant rate by judge (of motions filed):")
    filed = df[df["summary_judgment_filed"]]
    rates = (filed.groupby(["court_venue", "judge_id"])["summary_judgment_granted"]
                  .agg(["mean", "size"])
                  .rename(columns={"mean": "grant_rate", "size": "motions"}))
    print(rates.assign(grant_rate=lambda d: d["grant_rate"].round(3))
               .sort_values(["court_venue", "grant_rate"], ascending=[True, False])
               .to_string())

    print(f"\nClaim amount — median £{df['claim_amount_gbp'].median():,.0f} | "
          f"mean £{df['claim_amount_gbp'].mean():,.0f} | "
          f"p95 £{df['claim_amount_gbp'].quantile(0.95):,.0f}")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data = generate()
    validate(data)
    summarise(data)

    data.to_csv(OUTPUT_FILE, index=False)
    # Reference table of the bench. The latent effect columns are dropped —
    # Phase 2 must recover them from the data, not read them off a lookup.
    JUDGES.drop(columns=["sj_effect", "pace_effect"]).to_csv(
        os.path.join(OUTPUT_DIR, "judge_reference.csv"), index=False
    )

    print(f"\nWritten → {OUTPUT_FILE}")
