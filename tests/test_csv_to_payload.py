"""Hermetic unit tests for CSV → JSON payload coercion in post_csv_to_calc.

These tests do NOT hit the network. They exercise the script's type-coercion
+ reserved-column-stripping + URL-building logic against fixed inputs.

The live-API smoke is a separate test (`test_live_smoke.py`), opt-in via
the CLAWDOG_KIT_RUN_LIVE_SMOKE env var.
"""
from __future__ import annotations

import importlib

import pytest

post_csv_to_calc = importlib.import_module("post_csv_to_calc")


class TestRowToPayload:
    """`_row_to_payload` is the load-bearing CSV → JSON converter."""

    def test_empty_cells_become_absent(self) -> None:
        row = {
            "businessUsePercentage": "80",
            "employeeContribution": "",          # empty → absent
            "formOfFinance": "owned",
            "leasePayments": "",
            "openingDepreciatedValue": "",
            "acquisitionCost": "35000",
            "acquisitionDate": "2024-04-01",
            "daysHeldInFBTYear": "366",
            "notes": "some note",                 # reserved → stripped
            "car_id": "CAR-001",                  # reserved → stripped
        }
        payload = post_csv_to_calc._row_to_payload(row)

        assert "employeeContribution" not in payload
        assert "leasePayments" not in payload
        assert "openingDepreciatedValue" not in payload
        assert "notes" not in payload
        assert "car_id" not in payload

        assert payload["businessUsePercentage"] == 80
        assert payload["formOfFinance"] == "owned"
        assert payload["acquisitionCost"] == 35000
        assert payload["acquisitionDate"] == "2024-04-01"
        assert payload["daysHeldInFBTYear"] == 366

    def test_decimal_cells_coerce_to_float(self) -> None:
        row = {
            "businessUsePercentage": "78.5",
            "formOfFinance": "owned",
            "fuelRepairsServicing": "4500.25",
            "acquisitionCost": "35000.00",
        }
        payload = post_csv_to_calc._row_to_payload(row)
        # 78.5 must remain a float, not collapse to 78
        assert payload["businessUsePercentage"] == 78.5
        assert isinstance(payload["businessUsePercentage"], float)
        # 4500.25 must remain a float
        assert payload["fuelRepairsServicing"] == 4500.25
        assert isinstance(payload["fuelRepairsServicing"], float)
        # 35000.00 may coerce to int OR float (both serialise cleanly);
        # what matters is JSON-compatibility
        assert payload["acquisitionCost"] in (35000, 35000.0)

    def test_integer_field_stays_integer(self) -> None:
        row = {
            "businessUsePercentage": "80",
            "formOfFinance": "owned",
            "daysHeldInFBTYear": "366",
        }
        payload = post_csv_to_calc._row_to_payload(row)
        assert payload["daysHeldInFBTYear"] == 366
        assert isinstance(payload["daysHeldInFBTYear"], int)

    def test_unknown_field_passes_through_as_string(self) -> None:
        """Schema-driven kit: unknown CSV columns pass through to the API.

        The API will 422 on shape mismatch with a clear error — better than
        silently dropping fields the user might have meant.
        """
        row = {
            "businessUsePercentage": "80",
            "formOfFinance": "owned",
            "futureField": "some-value",
        }
        payload = post_csv_to_calc._row_to_payload(row)
        assert payload["futureField"] == "some-value"

    def test_reserved_columns_are_stripped(self) -> None:
        row = {
            "businessUsePercentage": "80",
            "formOfFinance": "owned",
            "car_id": "CAR-001",
            "asset_id": "A-001",
            "row_id": "1",
            "notes": "anything",
            "comments": "more text",
        }
        payload = post_csv_to_calc._row_to_payload(row)
        for stripped in ("car_id", "asset_id", "row_id", "notes", "comments"):
            assert stripped not in payload


class TestBuildEndpoint:
    """`_build_endpoint` resolves --calculator / --period aliases to URIs."""

    def test_fbt_car_oc_fy2026(self) -> None:
        calc_uri, period_uri = post_csv_to_calc._build_endpoint(
            "fbt-car-operating-cost", "fy2026"
        )
        assert calc_uri == "urn:sbrm:calculator:fbt:car-operating-cost"
        assert period_uri == "urn:sbrm:period:fbt:fy2026"

    def test_unknown_calculator_raises(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            post_csv_to_calc._build_endpoint("does-not-exist", "fy2026")
        assert "unknown calculator alias" in str(excinfo.value)

    def test_unknown_period_for_known_calculator_raises(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            post_csv_to_calc._build_endpoint("fbt-car-operating-cost", "fy9999")
        assert "unknown period alias" in str(excinfo.value)


class TestBuildUrl:
    """URN colons MUST URL-encode as %3A."""

    def test_url_encoding_of_urns(self) -> None:
        url = post_csv_to_calc._build_url(
            "https://example.invalid",
            "urn:sbrm:calculator:fbt:car-operating-cost",
            "urn:sbrm:period:fbt:fy2026",
        )
        # The URL fragment between /v1/calculators/ and /<period> must contain
        # %3A for every URN colon. Failing to encode would misroute on the
        # FastAPI path parameter parser.
        assert "%3A" in url
        assert "urn:sbrm" not in url  # the raw colons must NOT appear
        assert url.startswith("https://example.invalid/v1/calculators/")
        # The colons before "//" in https:// don't count; check the path side
        path = url.split("://", 1)[1].split("/", 1)[1]  # strip scheme + host
        assert ":" not in path
