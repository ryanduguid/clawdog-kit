"""End-to-end smoke against the LIVE clawdog-calculator-api.

OPT-IN. Set environment variable ``CLAWDOG_KIT_RUN_LIVE_SMOKE=1`` to run.
By default these tests SKIP, so CI on a fresh clone stays hermetic + fast.

What we assert: for each canonical example input under
``templates/fbt-car-operating-cost/examples/*.input.json``, the live API
returns an HTTP 200 response whose ``taxable_value`` matches the
corresponding ``*.output.json`` taxable_value to within 0.01 AUD.

We deliberately do NOT assert byte-equality on the full response — rate-
table content_hashes are version-stable but trace internals may shift
across calc-api alpha revisions. ``taxable_value`` is the load-bearing
output; if it matches, the kit is in working order.

If this test FAILS on a fresh clone with the env var set, that is a real
regression somewhere (either the kit's example fixtures are stale, or the
calc-api has drifted from its documented behaviour). Open an issue with
the diff between the expected and actual taxable_value.
"""
from __future__ import annotations

import importlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

post_csv_to_calc = importlib.import_module("post_csv_to_calc")

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "templates" / "fbt-car-operating-cost" / "examples"

SHOULD_RUN = os.environ.get("CLAWDOG_KIT_RUN_LIVE_SMOKE") == "1"


def _example_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for inp in sorted(EXAMPLES_DIR.glob("*.input.json")):
        out = inp.with_name(inp.name.replace(".input.json", ".output.json"))
        if out.exists():
            pairs.append((inp, out))
    return pairs


@pytest.mark.skipif(
    not SHOULD_RUN,
    reason="CLAWDOG_KIT_RUN_LIVE_SMOKE not set; live network smoke is opt-in",
)
@pytest.mark.parametrize(
    "input_path,expected_output_path",
    _example_pairs(),
    ids=lambda p: p.stem.replace(".input", "").replace(".output", ""),
)
def test_example_matches_live_api(input_path: Path, expected_output_path: Path) -> None:
    request_body = json.loads(input_path.read_text(encoding="utf-8"))
    expected = json.loads(expected_output_path.read_text(encoding="utf-8"))

    url = post_csv_to_calc._build_url(
        post_csv_to_calc.API_BASE_URL,
        "urn:sbrm:calculator:fbt:car-operating-cost",
        "urn:sbrm:period:fbt:fy2026",
    )
    status, body = post_csv_to_calc._post_json(url, request_body, timeout=60.0)

    assert status == 200, (
        f"Live API returned {status} for {input_path.name}. "
        f"Body: {body!r}. "
        f"If the calc-api is healthy, this means the kit example has drifted "
        f"or the input schema changed."
    )
    assert isinstance(body, dict), f"non-JSON response body: {body!r}"
    actual_tv = body.get("taxable_value")
    expected_tv = expected.get("taxable_value")
    assert actual_tv is not None, f"response missing taxable_value: {body!r}"
    assert expected_tv is not None, f"fixture missing taxable_value: {expected!r}"

    actual_amount = Decimal(str(actual_tv))
    expected_amount = Decimal(str(expected_tv))
    assert actual_amount.is_finite() and expected_amount.is_finite()
    assert abs(actual_amount - expected_amount) < Decimal("0.01"), (
        f"taxable_value drift for {input_path.name}: "
        f"expected ~{expected_tv}, got {actual_tv}"
    )

    # Every captured example reports rate provenance, including the leased path's
    # gross-up and FBT-rate entries.
    manifest = body.get("manifest")
    assert isinstance(manifest, dict), f"missing manifest block: {body!r}"
    rate_uris = manifest.get("rate_table_uris", [])
    assert isinstance(rate_uris, list), f"manifest.rate_table_uris not a list: {manifest!r}"
    assert rate_uris, f"manifest has no rate provenance: {manifest!r}"

    # Defence-in-depth: every URI carries sha256 content_hash, per the
    # provenance discipline. If any URI in the list lacks sha256, that's a
    # calc-api regression.
    for entry in rate_uris:
        assert isinstance(entry, dict), f"rate_uri entry not a dict: {entry!r}"
        assert entry.get("hash_algorithm") == "sha256", (
            f"non-sha256 hash algorithm in manifest: {entry!r}"
        )
        assert isinstance(entry.get("content_hash"), str), (
            f"missing/non-string content_hash: {entry!r}"
        )

    # Defence-in-depth: advisory block must be present (statutory framing).
    advisory = body.get("advisory")
    assert isinstance(advisory, dict), f"missing advisory block: {body!r}"
    assert advisory.get("registered_agent_required") is True
    assert advisory.get("jurisdiction") == "AU"
