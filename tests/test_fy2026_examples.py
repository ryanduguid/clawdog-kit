"""Keep the full-year examples aligned with the stated FBT period."""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "templates/fbt-car-operating-cost"
FULL_YEAR_DAYS = (date(2026, 4, 1) - date(2025, 4, 1)).days


@pytest.mark.parametrize("name,expected", [
    ("owned_modern_tier_full_year", "1905.05"),
    ("owned_opening_wdv", "4098.56"),
    ("leased", "0.00"),
])
def test_full_year_examples(name, expected):
    payload = json.loads((TEMPLATE / "examples" / f"{name}.input.json").read_text(encoding="utf-8"))
    response = json.loads((TEMPLATE / "examples" / f"{name}.output.json").read_text(encoding="utf-8"))
    assert payload["daysHeldInFBTYear"] == FULL_YEAR_DAYS == 365
    assert Decimal(str(response["taxable_value"])) == Decimal(expected)


def test_sample_uses_the_full_year():
    with (TEMPLATE / "sample.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 3
    assert all(int(row["daysHeldInFBTYear"]) == FULL_YEAR_DAYS for row in rows)


def test_walkthrough_lists_every_manifest_entry():
    walkthrough = (TEMPLATE.parents[1] / "examples/end-to-end-fbt-car-fy2026.md").read_text(encoding="utf-8")
    for path in (TEMPLATE / "examples").glob("*.output.json"):
        response = json.loads(path.read_text(encoding="utf-8"))
        for entry in response["manifest"]["rate_table_uris"]:
            assert entry["uri"] in walkthrough
            assert entry["content_hash"] in walkthrough
