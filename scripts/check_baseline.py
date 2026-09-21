"""Check that the quality ledger top row matches the actual test count.

Usage:
    python scripts/check_baseline.py

Exits 0 if the ledger is current, 1 if it's stale.
"""

import re
import subprocess
import sys


def get_actual_test_count() -> int:
    """Get the 'passed' count from pytest -q output (matches ledger convention)."""
    result = subprocess.run(
        ["uv", "run", "pytest", "-q"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    # pytest -q last line: "303 passed, 4 skipped, 2 warnings in 2.50s"
    match = re.search(r"(\d+) passed", result.stdout)
    if match:
        return int(match.group(1))
    return -1


def get_ledger_top_count() -> int:
    with open("开发文档/09-质量基线与门禁台账.md", encoding="utf-8") as f:
        content = f.read()
    # Find the first number in the table after the header
    # Pattern: | 2026-XX-XX | NNN |
    match = re.search(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(\d+)\s*\|", content, re.MULTILINE)
    if match:
        return int(match.group(1))
    return -1


def main():
    actual = get_actual_test_count()
    ledger = get_ledger_top_count()

    if actual < 0:
        print("WARNING: Could not determine actual test count")
        sys.exit(0)

    if ledger < 0:
        print("WARNING: Could not parse ledger top row")
        sys.exit(0)

    if actual == ledger:
        print(f"Baseline OK: ledger={ledger}, actual={actual}")
        sys.exit(0)

    print(f"BASELINE STALE: ledger says {ledger}, actual is {actual}")
    print(f"Update 开发文档/09-质量基线与门禁台账.md top row to {actual}")
    sys.exit(1)


if __name__ == "__main__":
    main()
