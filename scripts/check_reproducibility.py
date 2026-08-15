"""
Reproducibility check for CI.
=============================

Replaces a byte-for-byte ``git diff`` on regenerated outputs, which turned out
to be the wrong test.

Why byte comparison was wrong
-----------------------------
The pipeline is bit-for-bit deterministic on a *given* machine — the generator
is seeded, and the chart HTML has its container id pinned so Plotly cannot
inject a random UUID. Two runs in the same environment produce identical
bytes, and that is worth having.

Across environments it is a different matter. Transcendental functions
(``exp``, ``log``) are permitted to differ by an ULP between library builds,
and the generator rounds durations to whole days — so a value sitting exactly
on a rounding boundary can land on a different integer, and that difference
then propagates through everything downstream. The pinned dependencies also do
not pin *their* dependencies: ``lifelines`` pulls ``autograd`` and
``formulaic``, whose versions can move under us.

A byte comparison cannot tell those harmless differences apart from a real
regression. It just fails, and a CI check that fails for reasons nobody can
act on gets ignored — which is worse than not having it.

What this checks instead
------------------------
    data/     numeric equality to a tight tolerance. This is the substantive
              claim: the same seed produces the same docket.
    results/  numeric equality to a looser tolerance. These come from
              iterative optimisers, so the last few decimals move. Checking
              them at all is new — the old byte check skipped them entirely.
    charts/   regenerated, non-empty, and carrying stable container ids.
              Deliberately NOT compared numerically: they are derived
              artefacts, and their content is already covered upstream.

Every comparison reports the largest deviation it found, so a passing run
still tells you how much drift there is.

Usage
-----
    python scripts/check_reproducibility.py <snapshot_dir>

where <snapshot_dir> holds copies of data/, results/ and charts/ taken
BEFORE the pipeline was re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# data/ is pure seeded generation: only libm-level drift is tolerable.
DATA_RTOL = 1e-12
# results/ come from iterative optimisers (Cox, AFT); convergence differs.
RESULTS_RTOL = 1e-6

failures: list[str] = []
notes: list[str] = []


def compare_csv(old: Path, new: Path, rtol: float) -> None:
    label = f"{new.parent.name}/{new.name}"

    try:
        a = pd.read_csv(old)
        b = pd.read_csv(new)
    except Exception as exc:                       # noqa: BLE001
        failures.append(f"{label}: could not read ({exc})")
        return

    if a.shape != b.shape:
        failures.append(f"{label}: shape changed {a.shape} -> {b.shape}")
        return
    if list(a.columns) != list(b.columns):
        failures.append(f"{label}: columns changed")
        return

    worst = 0.0
    worst_col = ""
    for col in a.columns:
        s_old, s_new = a[col], b[col]

        if pd.api.types.is_numeric_dtype(s_old) and pd.api.types.is_numeric_dtype(s_new):
            x = s_old.to_numpy(dtype=float)
            y = s_new.to_numpy(dtype=float)

            both_nan = np.isnan(x) & np.isnan(y)
            if not np.array_equal(np.isnan(x), np.isnan(y)):
                failures.append(f"{label}: missing-value pattern changed in '{col}'")
                return

            mask = ~both_nan
            if mask.any():
                denom = np.maximum(np.abs(x[mask]), 1e-30)
                rel = np.abs(x[mask] - y[mask]) / denom
                peak = float(rel.max())
                if peak > worst:
                    worst, worst_col = peak, col
                if peak > rtol:
                    failures.append(
                        f"{label}: column '{col}' differs by {peak:.3e} "
                        f"(tolerance {rtol:.0e})"
                    )
                    return
        else:
            if not s_old.astype(str).equals(s_new.astype(str)):
                failures.append(f"{label}: non-numeric column '{col}' changed")
                return

    if worst > 0:
        notes.append(f"  {label}: max relative deviation {worst:.3e} in '{worst_col}'")
    else:
        notes.append(f"  {label}: identical")


def check_charts() -> None:
    charts = sorted((ROOT / "charts").glob("chart_*.html"))
    if not charts:
        failures.append("charts/: no chart files were produced")
        return

    for path in charts:
        html = path.read_text(encoding="utf-8")
        if len(html) < 2_000:
            failures.append(f"charts/{path.name}: suspiciously small ({len(html)} bytes)")
        stable_id = f'id="chart-{path.stem}"'
        if stable_id not in html:
            failures.append(
                f"charts/{path.name}: missing stable container id — Plotly's "
                f"random UUID is back, and output is no longer reproducible"
            )
    notes.append(f"  charts/: {len(charts)} charts regenerated with stable ids")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    snapshot = Path(sys.argv[1]).resolve()
    if not snapshot.is_dir():
        print(f"snapshot directory not found: {snapshot}")
        return 2

    print("=" * 72)
    print("REPRODUCIBILITY CHECK")
    print("=" * 72)

    for folder, rtol in [("data", DATA_RTOL), ("results", RESULTS_RTOL)]:
        old_dir = snapshot / folder
        new_dir = ROOT / folder
        if not old_dir.is_dir():
            failures.append(f"{folder}/: no snapshot to compare against")
            continue

        print(f"\n{folder}/  (tolerance {rtol:.0e})")
        for old in sorted(old_dir.glob("*.csv")):
            new = new_dir / old.name
            if not new.exists():
                failures.append(f"{folder}/{old.name}: not regenerated")
                continue
            compare_csv(old, new, rtol)

        while notes:
            print(notes.pop(0))

    print("\ncharts/")
    check_charts()
    while notes:
        print(notes.pop(0))

    print("\n" + "=" * 72)
    if failures:
        print(f"FAILED — {len(failures)} problem(s):\n")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nIf these are genuine changes, re-run 'python run_all.py' locally")
        print("and commit the regenerated outputs.")
        return 1

    print("PASSED — the committed outputs reproduce within tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
