"""Run the full pipeline end to end: generate -> analyse -> visualise.

    python run_all.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGES = [
    ("Generating synthetic docket", "generate_dataset.py"),
    ("Running statistical analysis", "analysis.py"),
    ("Building interactive charts", "charts.py"),
]

for label, script in STAGES:
    print(f"\n{'=' * 70}\n{label}  ({script})\n{'=' * 70}")
    result = subprocess.run([sys.executable, str(ROOT / "src" / script)])
    if result.returncode != 0:
        sys.exit(f"\nFAILED at {script} (exit {result.returncode})")

print(f"\nPipeline complete. Open {ROOT / 'charts' / 'index.html'} to preview.")
