"""Order-invariance gate for feature 025 (calibrated probability display).

Captures the ENGINE-OUTPUT ranked job_id sequence per employee — not a DB
re-sort, because reranker saturation creates exact score ties whose DB
ordering is nondeterministic (research.md R5).

    python ../specs/025-calibrated-probability-display/capture_order.py before
    python ../specs/025-calibrated-probability-display/capture_order.py after

`before` writes order_before.json next to this script.
`after` re-captures, diffs, prints a per-employee verdict, exits 1 on ANY
sequence mismatch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import django  # noqa: E402
import os  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import logging  # noqa: E402

logging.disable(logging.WARNING)

SNAP = Path(__file__).parent / "order_before.json"


def capture() -> dict[str, list[int]]:
    from apps.employees.matching import rematch_employee
    from apps.employees.models import Employee

    out: dict[str, list[int]] = {}
    for emp in Employee.objects.filter(is_parse_failed=False).exclude(skills=[]).order_by("id"):
        results = rematch_employee(emp, top_k=100)
        out[str(emp.id)] = [r["job_id"] for r in results]
        print(f"  #{emp.id} {emp.full_name}: {len(results)} jobs", file=sys.stderr)
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "before":
        SNAP.write_text(json.dumps(capture(), indent=1))
        print(f"snapshot → {SNAP}")
        return 0
    if mode == "after":
        before = json.loads(SNAP.read_text())
        after = capture()
        bad = 0
        for emp_id, seq in before.items():
            new = after.get(emp_id, [])
            if new == seq:
                print(f"  ✓ employee {emp_id}: order IDENTICAL ({len(seq)} jobs)")
            else:
                bad += 1
                first = next((i for i, (a, b) in enumerate(zip(seq, new)) if a != b), min(len(seq), len(new)))
                print(f"  ✗ employee {emp_id}: MISMATCH at position {first} "
                      f"(before={seq[first] if first < len(seq) else '∅'} "
                      f"after={new[first] if first < len(new) else '∅'})")
        print("ORDER-INVARIANCE:", "PASS" if bad == 0 else f"FAIL ({bad} employees)")
        return 0 if bad == 0 else 1
    print("usage: capture_order.py before|after")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
