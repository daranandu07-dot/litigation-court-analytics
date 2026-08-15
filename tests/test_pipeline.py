"""
Test suite for the litigation analytics pipeline.
=================================================

Why this exists
---------------
This project was built with heavy AI assistance. That makes it fast to write
and easy to write *plausibly wrong*: code that runs, produces numbers, and is
quietly incorrect. Reading the diff is not enough to catch that.

These tests are the check. They fall into four groups, in increasing order of
how much they would embarrass me if they failed:

  1. REPRODUCIBILITY  - the committed data really is what the script produces.
  2. INTEGRITY        - the data obeys the rules the domain imposes on it.
  3. METHOD           - the two methodological claims the README makes are
                        actually true of the fitted models (no outcome
                        leakage; censoring correction moves estimates in the
                        direction claimed).
  4. HONESTY          - every headline number in the README reconciles with
                        the committed result tables. If I edit prose without
                        re-running the pipeline, this fails.

Group 4 is the one worth stealing. A README is the part of a repo most likely
to drift away from the truth, because it is the part not executed by anything.

Run:
    pip install -r requirements-dev.txt
    pytest -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import generate_dataset as gd  # noqa: E402

DATA = ROOT / "data"
RESULTS = ROOT / "results"
CHARTS = ROOT / "charts"

# Tolerance for comparing floats that have made a round trip through CSV.
TOL = 1e-9


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def committed() -> pd.DataFrame:
    """The dataset as committed to the repository."""
    return pd.read_csv(
        DATA / "litigation_court_data.csv",
        parse_dates=["filing_date", "disposition_date"],
    )


@pytest.fixture(scope="session")
def regenerated() -> pd.DataFrame:
    """A fresh generation, reproducing module-load order exactly.

    ``generate_dataset`` draws from a module-level Generator, and importing the
    module already consumes draws (``build_judge_panel`` runs at import). To
    reproduce what ``python src/generate_dataset.py`` produces, both the
    Generator and the judge panel have to be rebuilt in the same order.
    """
    gd.rng = np.random.default_rng(gd.SEED)
    gd.JUDGES = gd.build_judge_panel()
    return gd.generate()


@pytest.fixture(scope="session")
def headline() -> dict:
    return json.loads((RESULTS / "headline_metrics.json").read_text())


@pytest.fixture(scope="session")
def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. REPRODUCIBILITY
# ---------------------------------------------------------------------------

def test_seed_produces_the_committed_dataset(committed, regenerated):
    """The CSV in the repo is exactly what the generator produces today.

    Guards the most common silent failure in a data repo: results committed
    from a version of the script that no longer exists.
    """
    assert len(regenerated) == len(committed)
    assert list(regenerated.columns) == list(committed.columns)

    for col in ["case_id", "court_venue", "judge_id", "case_complexity",
                "disposition_type", "case_status"]:
        pd.testing.assert_series_equal(
            regenerated[col].astype(object).where(regenerated[col].notna()),
            committed[col].astype(object).where(committed[col].notna()),
            check_names=False, check_dtype=False,
        )

    for col in ["claim_amount_gbp", "days_to_resolution",
                "num_interlocutory_motions", "final_awarded_amount_gbp"]:
        np.testing.assert_allclose(
            regenerated[col].to_numpy(dtype=float),
            committed[col].to_numpy(dtype=float),
            rtol=0, atol=0.005, equal_nan=True,
        )


def test_generation_is_deterministic_within_a_process():
    """Two generations from the same seed state agree."""
    def once():
        gd.rng = np.random.default_rng(gd.SEED)
        gd.JUDGES = gd.build_judge_panel()
        return gd.generate()

    a, b = once(), once()
    pd.testing.assert_frame_equal(a, b)


def test_charts_have_stable_container_ids():
    """Chart HTML must not embed a fresh random UUID on every render.

    Plotly's default is a random div id, which makes byte-identical output
    impossible and floods version control with meaningless diffs. ``save()``
    overrides it with an id derived from the filename.
    """
    uuid_re = re.compile(
        r'id="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"'
    )
    charts = sorted(CHARTS.glob("chart_*.html"))
    assert charts, "no chart files found"

    for path in charts:
        html = path.read_text(encoding="utf-8")
        assert not uuid_re.search(html), f"{path.name} still has a random div id"
        assert f'id="chart-{path.stem}"' in html, f"{path.name} missing stable id"


# ---------------------------------------------------------------------------
# 2. INTEGRITY
# ---------------------------------------------------------------------------

def test_generator_invariants_hold(regenerated):
    """The generator's own assertions pass (SJ logic, date reconciliation,
    one-venue-per-judge, dismissals recovering nothing)."""
    gd.validate(regenerated)


def test_every_judge_sits_in_exactly_one_venue(committed):
    seats = committed.groupby("judge_id")["court_venue"].nunique()
    assert (seats == 1).all()
    assert committed["judge_id"].nunique() == gd.N_JUDGES


def test_open_cases_have_no_outcome(committed):
    """A case that has not ended cannot have an ending."""
    open_cases = committed["case_status"] == "Ongoing"
    assert open_cases.any(), "no censored cases — survival analysis would be trivial"
    assert committed.loc[open_cases, "disposition_type"].isna().all()
    assert committed.loc[open_cases, "disposition_date"].isna().all()
    assert committed.loc[open_cases, "final_awarded_amount_gbp"].isna().all()
    assert (committed.loc[open_cases, "event_observed"] == 0).all()


def test_summary_judgment_cannot_be_granted_unless_filed(committed):
    impossible = committed["summary_judgment_granted"] & ~committed["summary_judgment_filed"]
    assert not impossible.any()


def test_awards_never_exceed_claims(committed):
    """A claimant cannot recover more than was claimed on these facts."""
    resolved = committed["final_awarded_amount_gbp"].notna()
    assert (
        committed.loc[resolved, "final_awarded_amount_gbp"]
        <= committed.loc[resolved, "claim_amount_gbp"] + TOL
    ).all()


def test_no_invented_judge_names():
    """The bench roster must not carry human-looking names.

    Fabricated grant rates attached to realistic surnames is an avoidable bad
    habit in a legal repository. This test stops it coming back.
    """
    roster = pd.read_csv(DATA / "judge_reference.csv")
    assert "judge_name" not in roster.columns
    assert not any(str(c).lower().endswith("name") for c in roster.columns)
    flat = roster.astype(str).to_numpy().ravel()
    assert not any("Hon." in v for v in flat)


# ---------------------------------------------------------------------------
# 3. METHOD
# ---------------------------------------------------------------------------

FORBIDDEN_COVARIATES = ["disposition_type", "summary_judgment_granted"]


@pytest.mark.parametrize("table", ["cox_hazard_ratios.csv", "aft_time_ratios.csv"])
def test_duration_models_contain_no_outcome_leakage(table):
    """Variables realised *at* disposition must not predict time *to*
    disposition. Including them would use the outcome to predict the outcome —
    the single most common invisible error in this kind of work.
    """
    covariates = pd.read_csv(RESULTS / table, index_col=0).index.astype(str)
    for banned in FORBIDDEN_COVARIATES:
        assert not covariates.str.contains(banned).any(), (
            f"{banned} leaked into {table}"
        )


def test_censoring_correction_increases_duration_estimates(headline):
    """The project's central claim.

    Cases still open are disproportionately the slow ones, so dropping them
    understates duration. The Kaplan-Meier median must therefore sit at or
    above the naive resolved-only median in every stratum, and the gap must
    widen with complexity.
    """
    strata = headline["km_survival"]
    for s in strata:
        assert s["km_median_days"] >= s["naive_median_days"], s["complexity"]
        assert s["bias_days"] >= 0

    by_level = {s["complexity"]: s["bias_days"] for s in strata}
    assert by_level["High"] > by_level["Medium"] > by_level["Low"]


def test_survival_probabilities_are_monotonically_decreasing(headline):
    """S(t) is a survival function: it cannot increase with time."""
    for s in headline["km_survival"]:
        assert 0 <= s["S_720"] <= s["S_540"] <= s["S_365"] <= 1, s["complexity"]


def test_judge_grant_rates_recompute_from_raw_data(committed):
    """The published per-judge table is derivable from the raw CSV."""
    published = pd.read_csv(RESULTS / "judge_grant_rates.csv").set_index("judge_id")
    filed = committed[committed["summary_judgment_filed"]]
    recomputed = (
        filed.groupby("judge_id")["summary_judgment_granted"]
        .agg(motions="size", granted="sum")
    )
    recomputed["grant_rate"] = recomputed["granted"] / recomputed["motions"]

    for jid, row in published.iterrows():
        assert recomputed.loc[jid, "motions"] == row["motions"]
        assert recomputed.loc[jid, "granted"] == row["granted"]
        assert recomputed.loc[jid, "grant_rate"] == pytest.approx(row["grant_rate"])


def test_wilson_intervals_are_well_formed():
    """A confidence interval must contain its own point estimate and stay
    inside [0, 1]. The normal approximation fails this near the boundaries;
    Wilson is used precisely because it does not.
    """
    j = pd.read_csv(RESULTS / "judge_grant_rates.csv")
    assert (j["ci_low"] >= 0).all() and (j["ci_high"] <= 1).all()
    assert (j["ci_low"] <= j["grant_rate"]).all()
    assert (j["grant_rate"] <= j["ci_high"]).all()


def test_outlier_flag_means_interval_excludes_the_panel_rate(committed):
    j = pd.read_csv(RESULTS / "judge_grant_rates.csv")
    panel = committed.loc[committed["summary_judgment_filed"],
                          "summary_judgment_granted"].mean()
    expected = (j["ci_low"] > panel) | (j["ci_high"] < panel)
    assert (j["outlier"] == expected).all()


def test_recovery_figures_recompute_from_raw_data(committed):
    published = pd.read_csv(RESULTS / "recovery_by_disposition.csv", index_col=0)
    resolved = committed[committed["event_observed"] == 1]

    for disposition, row in published.iterrows():
        sub = resolved[resolved["disposition_type"] == disposition]
        assert len(sub) == row["n"]
        aggregate = sub["final_awarded_amount_gbp"].sum() / sub["claim_amount_gbp"].sum()
        assert aggregate == pytest.approx(row["aggregate_recovery"], rel=1e-6)


def test_dismissals_recover_nothing(committed):
    """Not a statistical result — a definitional one. If it ever fails, the
    disposition logic is broken rather than the finding being interesting."""
    dismissed = committed[committed["disposition_type"] == "Dismissed"]
    assert len(dismissed) > 0
    assert (dismissed["final_awarded_amount_gbp"] == 0).all()


# ---------------------------------------------------------------------------
# 4. HONESTY — README claims must match committed results
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def test_readme_judge_spread_matches_results(readme):
    j = pd.read_csv(RESULTS / "judge_grant_rates.csv")
    assert _pct(j["grant_rate"].max()) in readme
    assert _pct(j["grant_rate"].min()) in readme


def test_readme_km_medians_match_results(readme, headline):
    for s in headline["km_survival"]:
        assert f"{int(s['km_median_days'])} d" in readme, s["complexity"]


def test_readme_censoring_bias_matches_results(readme, headline):
    high = next(s for s in headline["km_survival"] if s["complexity"] == "High")
    assert str(int(high["bias_days"])) in readme
    assert str(int(high["naive_median_days"])) in readme


def test_readme_portfolio_recovery_matches_results(readme):
    rec = pd.read_csv(RESULTS / "recovery_by_disposition.csv", index_col=0)
    portfolio = rec["total_awarded_gbp"].sum() / rec["total_claimed_gbp"].sum()
    assert f"{portfolio:.3f}".lstrip("0") in readme or _pct(portfolio) in readme


def test_readme_case_counts_match_results(readme):
    rec = pd.read_csv(RESULTS / "recovery_by_disposition.csv", index_col=0)
    total = int(rec["n"].sum())
    assert f"{total:,}" in readme


def test_every_time_ratio_quoted_in_the_readme_is_real(readme):
    """Stronger than 'the right number appears somewhere'.

    An earlier version of this test only checked that the correct value was
    present, so editing one of several occurrences of a figure went unnoticed.
    This one goes the other way: it collects *every* value in the README that
    is written like a time ratio and requires each to exist in the fitted
    model output. An invented or stale figure fails wherever it is written.
    """
    aft = pd.read_csv(RESULTS / "aft_time_ratios.csv", index_col=0)
    permitted = set()
    for col in ["time_ratio", "tr_low", "tr_high"]:
        permitted |= {f"{v:.2f}" for v in aft[col]}

    quoted = set(re.findall(r"(\d\.\d{2})x", readme))
    invented = quoted - permitted
    assert not invented, (
        f"README quotes time ratio(s) {sorted(invented)} that appear nowhere "
        f"in results/aft_time_ratios.csv"
    )


def test_readme_headline_time_ratio_matches_results(readme):
    aft = pd.read_csv(RESULTS / "aft_time_ratios.csv", index_col=0)
    high = aft.loc["case_complexity_High", "time_ratio"]
    assert f"{high:.2f}x" in readme


def test_readme_does_not_overclaim_reproducibility(readme):
    """An earlier draft claimed outputs were 'byte-identical on every run'.
    That was false while Plotly embedded random div ids. The claim is now
    true — but only because ``save()`` pins them, so this test ties the prose
    to the code that makes it honest.
    """
    if "byte-identical" in readme:
        source = (ROOT / "src" / "charts.py").read_text(encoding="utf-8")
        assert "div_id=" in source, (
            "README claims byte-identical output but charts.py does not pin "
            "the Plotly container id"
        )


# ---------------------------------------------------------------------------
# 5. THE GENERAL CIVIL COMPARISON COHORT
# ---------------------------------------------------------------------------
# This cohort exists to be compared against published national statistics, so
# the tests check it against those figures directly. Tolerances are loose
# because the model is stochastic and the published figures are themselves
# rounded — but they are tight enough to catch a parameter being edited.

import generate_general_civil as gc  # noqa: E402


@pytest.fixture(scope="session")
def general() -> pd.DataFrame:
    return pd.read_csv(DATA / "general_civil_claims.csv")


def test_general_cohort_invariants_hold(general):
    gc.validate(general)


def test_defence_rate_matches_published_figure(general):
    """[MoJ] 72,000 of 527,000 County Court claims defended in Q1 2026 = 13.7%.

    The published figure is written out as a literal here ON PURPOSE. An
    earlier version of this test compared the data against
    ``gc.DEFENCE_RATE``, which made it self-referential: editing the constant
    edited the expectation too, and the test passed while the model drifted
    away from the statistic it claims to be calibrated to. A calibration test
    has to encode the external figure independently or it is checking nothing.
    """
    published = 72_000 / 527_000                     # 0.1366
    assert general["defended"].mean() == pytest.approx(published, abs=0.01)


def test_calibration_constants_still_match_their_published_sources():
    """Guards the constants themselves against silent edits."""
    assert gc.DEFENCE_RATE == pytest.approx(72_000 / 527_000, abs=1e-6)
    assert gc.TRIAL_RATE_GIVEN_DEFENDED == pytest.approx(13_000 / 72_000, abs=1e-6)
    assert gc.DEFAULT_JUDGMENT_RATE_GIVEN_UNDEFENDED == pytest.approx(
        (0.94 * 256_000) / 455_000, abs=1e-6
    )
    assert gc.SMALL_CLAIMS_TRIAL_DAYS == pytest.approx(37.6 * 7)
    assert gc.MULTI_TRACK_TRIAL_DAYS == pytest.approx(54.3 * 7)
    # CPR 10.3 — 14 days to acknowledge service.
    assert gc.MIN_DAYS_TO_DEFAULT_JUDGMENT == 14


def test_default_judgments_are_94_percent_of_judgments(general):
    """[MoJ] 94% of the 256,000 judgments given were default judgments.

    This is the test that caught the original modelling error: assuming every
    undefended claim produces a default judgment pushed this to 97.4%.
    """
    resolved = general[general["event_observed"] == 1]
    judgments = resolved[resolved["disposition_type"].isin(
        ["Default Judgment", "Trial Judgment"]
    )]
    share = (judgments["disposition_type"] == "Default Judgment").mean()
    assert share == pytest.approx(0.94, abs=0.02)


def test_default_judgment_respects_the_cpr_acknowledgment_period(general):
    """CPR 10.3 gives a defendant 14 days to acknowledge service, and default
    judgment under CPR Part 12 is not available until that period expires. No
    default judgment may therefore be entered sooner.
    """
    dj = general[general["disposition_type"] == "Default Judgment"]
    assert len(dj) > 0
    assert (dj["days_to_resolution"] >= gc.MIN_DAYS_TO_DEFAULT_JUDGMENT).all()


def test_only_undefended_claims_end_administratively(general):
    """A defended claim cannot end in a default judgment — that is what being
    defended means."""
    resolved = general[general["event_observed"] == 1]
    defended = resolved[resolved["defended"]]
    assert set(defended["disposition_type"]) <= {"Settled", "Trial Judgment"}

    undefended = resolved[~resolved["defended"]]
    assert set(undefended["disposition_type"]) <= {
        "Default Judgment", "Paid or discontinued"
    }


def test_default_judgment_is_entered_for_the_sum_claimed(general):
    dj = general[general["disposition_type"] == "Default Judgment"]
    np.testing.assert_allclose(
        dj["final_awarded_amount_gbp"].to_numpy(dtype=float),
        dj["claim_amount_gbp"].to_numpy(dtype=float),
        rtol=1e-9,
    )


def test_population_comparison_separates_the_two_cohorts():
    """The comparison must show what it claims: the commercial docket has no
    administrative disposals at all, and the general cohort is dominated by
    them. If this ever fails, the comparison has stopped meaning anything.
    """
    cmp = pd.read_csv(RESULTS / "population_comparison.csv").set_index("population")

    assert cmp.loc["Commercial disputes", "administrative_share"] == 0.0
    assert cmp.loc["General civil claims", "administrative_share"] > 0.80

    # Restricting the general cohort to defended claims must close most of the
    # duration gap — that is the composition argument the section rests on.
    all_claims = cmp.loc["General civil claims", "km_median_days"]
    defended = cmp.loc["General civil — defended only", "km_median_days"]
    commercial = cmp.loc["Commercial disputes", "km_median_days"]
    assert defended > 3 * all_claims
    assert defended < commercial


def test_readme_discloses_synthetic_data(readme):
    """Non-negotiable. The disclosure is what makes everything else defensible."""
    lowered = readme.lower()
    assert "synthetic" in lowered
    head = lowered[:3000]
    assert "synthetic" in head, "synthetic-data disclosure must be near the top"
