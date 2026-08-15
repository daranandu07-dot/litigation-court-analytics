"""
Litigation & Court Data Analytics — web dashboard export
========================================================

Builds a single self-contained HTML dashboard at ``web/index.html``.

Why a single file with the data inlined
---------------------------------------
No build step, no bundler, no server, no ``fetch``. The page works when opened
straight off disk *and* when served from GitHub Pages, and it cannot fall out of
sync with the analysis because the pipeline regenerates it.

The interesting part: the whole predictive model ships in the page
----------------------------------------------------------------
A Log-Normal AFT model is a linear predictor in log-time:

    log(T) = b'x + sigma * eps

so the predicted median duration is ``exp(b'x)`` and the survival function is

    S(t) = 1 - PHI( (log t - b'x) / sigma )

— a dot product and a normal CDF. Both are a few lines of JavaScript. Exporting
the fitted coefficients and sigma is therefore enough to run the entire model in
the browser: no inference endpoint, no Python service, no latency. The payload
is under a kilobyte.

The censoring slider is the point of the whole dashboard
--------------------------------------------------------
Every case carries its filing day and, if it closed, its disposition day. That
lets the page recompute Kaplan-Meier from scratch at any snapshot date at or
before the real one, so a viewer can *drag the observation date backwards and
watch the naive median and the KM median pull apart*. The censoring bias this
project is about stops being a paragraph and becomes something you do with your
hand.

The slider cannot move forwards past the real snapshot, because for cases still
open we do not know when they would have closed — which is exactly the problem
being illustrated.

Usage
-----
    python src/export_web.py

Output
------
    web/index.html
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import numpy as np
import pandas as pd
from lifelines import LogNormalAFTFitter

DATA_FILE = ROOT / "data" / "litigation_court_data.csv"
RESULTS_DIR = ROOT / "results"
TEMPLATE = ROOT / "src" / "dashboard_template.html"
OUTPUT = ROOT / "web" / "index.html"

EPOCH = pd.Timestamp("2022-01-01")
COMPLEXITY_ORDER = ["Low", "Medium", "High"]


def fit_aft(df: pd.DataFrame):
    """Refit the Log-Normal AFT with exactly the covariates analysis.py uses.

    The covariate set deliberately excludes `disposition_type` and
    `summary_judgment_granted` — both are realised at the moment a case ends,
    so including them would predict the outcome from the outcome. A test
    asserts the exported coefficients match results/aft_time_ratios.csv, so
    this refit cannot silently drift from the published model.
    """
    cox_df = df[["days_to_resolution", "event_observed", "case_complexity",
                 "court_venue", "log_claim", "num_interlocutory_motions",
                 "summary_judgment_filed"]].copy()
    cox_df["summary_judgment_filed"] = cox_df["summary_judgment_filed"].astype(int)
    cox_df = pd.get_dummies(cox_df, columns=["case_complexity", "court_venue"],
                            drop_first=True, dtype=float)

    fitter = LogNormalAFTFitter().fit(
        cox_df, duration_col="days_to_resolution", event_col="event_observed"
    )
    mu = fitter.params_["mu_"]
    sigma = float(np.exp(fitter.params_["sigma_"]["Intercept"]))
    features = [c for c in cox_df.columns
                if c not in ("days_to_resolution", "event_observed")]

    return {
        "intercept": float(mu["Intercept"]),
        "sigma": sigma,
        "features": features,
        "coef": {f: float(mu[f]) for f in features},
        "concordance": float(fitter.concordance_index_),
    }


def build_payload() -> dict:
    df = pd.read_csv(DATA_FILE, parse_dates=["filing_date", "disposition_date"])

    # MUST match analysis.py's load(): complexity is an ORDERED categorical
    # there, so get_dummies(drop_first=True) drops "Low" and the model is
    # expressed relative to low complexity. Read as a plain object column,
    # pandas sorts alphabetically instead and drops "High" — which silently
    # inverts the reference level and produces a model that looks fine and
    # predicts the wrong thing. A test now compares the exported coefficients
    # against results/aft_time_ratios.csv, which is how this was caught.
    df["case_complexity"] = pd.Categorical(
        df["case_complexity"], categories=COMPLEXITY_ORDER, ordered=True
    )
    df["log_claim"] = np.log(df["claim_amount_gbp"])

    venues = sorted(df["court_venue"].unique())
    venue_idx = {v: i for i, v in enumerate(venues)}
    dispositions = ["Settled", "Dismissed", "Trial Judgment"]
    disp_idx = {d: i for i, d in enumerate(dispositions)}

    file_day = (df["filing_date"] - EPOCH).dt.days.to_numpy()
    res_day = np.where(
        df["event_observed"] == 1,
        (df["disposition_date"] - EPOCH).dt.days.to_numpy(),
        -1,
    )
    as_of_day = int((pd.Timestamp("2026-06-30") - EPOCH).days)

    cases = {
        "venue": [int(venue_idx[v]) for v in df["court_venue"]],
        "cx": [int(COMPLEXITY_ORDER.index(c)) for c in df["case_complexity"]],
        "claim": [int(round(v)) for v in df["claim_amount_gbp"]],
        "motions": [int(v) for v in df["num_interlocutory_motions"]],
        "file": [int(v) for v in file_day],
        "res": [int(v) if v == v else -1 for v in np.nan_to_num(res_day, nan=-1)],
        "disp": [int(disp_idx[d]) if isinstance(d, str) else -1
                 for d in df["disposition_type"]],
        "door": [1 if str(d) == "True" else 0 for d in df["settled_at_trial_door"]],
    }

    judges = pd.read_csv(RESULTS_DIR / "judge_grant_rates.csv")
    panel_rate = float(
        df.loc[df["summary_judgment_filed"], "summary_judgment_granted"].mean()
    )

    populations = pd.read_csv(RESULTS_DIR / "population_comparison.csv")

    return {
        "meta": {
            "n": int(len(df)),
            "as_of_day": as_of_day,
            "epoch": EPOCH.strftime("%Y-%m-%d"),
            "min_file_day": int(file_day.min()),
            "max_file_day": int(file_day.max()),
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
        "venues": venues,
        "complexities": COMPLEXITY_ORDER,
        "dispositions": dispositions,
        "cases": cases,
        "aft": fit_aft(df),
        "judges": judges.to_dict(orient="records"),
        "panel_rate": panel_rate,
        "populations": populations.to_dict(orient="records"),
    }


def main() -> None:
    payload = build_payload()
    template = TEMPLATE.read_text(encoding="utf-8")

    if "/*__DATA__*/" not in template:
        raise SystemExit("template is missing the /*__DATA__*/ placeholder")

    # separators= keeps the inlined payload compact; sort_keys keeps the output
    # byte-stable so the reproducibility check stays meaningful.
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    html = template.replace("/*__DATA__*/", blob)

    os.makedirs(OUTPUT.parent, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")

    size_kb = len(html.encode("utf-8")) / 1024
    aft = payload["aft"]
    print(f"  [saved] {OUTPUT}  ({size_kb:.0f} KB)")
    print(f"  model shipped to the browser: {len(aft['features'])} coefficients "
          f"+ intercept + sigma = "
          f"{len(json.dumps(aft).encode('utf-8'))} bytes")
    print(f"  cases inlined: {payload['meta']['n']:,}")


if __name__ == "__main__":
    main()
