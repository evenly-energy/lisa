#!/usr/bin/env python3

"""Generate coverage-badge.json for shields.io endpoint badge."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    # Use .lisa/ for coverage output to keep repo root clean
    output_dir = Path(".lisa")
    output_dir.mkdir(exist_ok=True)
    coverage_json = output_dir / "coverage.json"

    result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "tests/",
            "--cov",
            f"--cov-report=json:{coverage_json}",
            "-q",
        ],
        capture_output=True,
        text=True,
    )

    try:
        with open(coverage_json) as f:
            data = json.load(f)
        pct = round(data["totals"]["percent_covered"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        print(f"Could not read {coverage_json}")
        return 1

    if pct >= 80:
        color = "green"
    elif pct >= 60:
        color = "yellow"
    else:
        color = "red"

    badge = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{pct}%",
        "color": color,
    }

    with open("coverage-badge.json", "w") as f:
        json.dump(badge, f, indent=2)
        f.write("\n")

    print(f"Coverage badge updated: {pct}% ({color})")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
