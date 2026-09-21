"""Offline command tests for per-row response files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import Mock

import post_csv_to_calc
import pytest


def write_csv(path: Path, identifiers: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as source:
        writer = csv.DictWriter(
            source,
            fieldnames=[
                "car_id",
                "asset_id",
                "row_id",
                "businessUsePercentage",
                "formOfFinance",
            ],
        )
        writer.writeheader()
        for identifier in identifiers:
            writer.writerow(
                {
                    **identifier,
                    "businessUsePercentage": "80",
                    "formOfFinance": "leased",
                }
            )


def arguments(source: Path, output: Path) -> list[str]:
    return [
        "--calculator",
        "fbt-car-operating-cost",
        "--period",
        "fy2026",
        "--input",
        str(source),
        "--output-dir",
        str(output),
    ]


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "identifiers",
    [
        [{"car_id": "car1"}, {"car_id": "car1"}],
        [{"asset_id": "asset1"}, {"asset_id": "asset1"}],
        [{"row_id": "id1"}, {"row_id": "id1"}],
        [{"car_id": "shared"}, {"asset_id": "shared"}],
        [{}, {"car_id": "row1"}],
        [{"car_id": "row2"}, {}],
        [{"car_id": "car1"}, {"car_id": "./car1"}],
    ],
)
def test_duplicate_outputs_fail_before_processing(
    tmp_path,
    monkeypatch,
    capsys,
    identifiers,
    dry_run,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "responses"
    write_csv(source, identifiers)
    post = Mock(return_value=(200, {"taxable_value": 20}))
    monkeypatch.setattr(post_csv_to_calc, "_post_json", post)
    argv = arguments(source, output) + (["--dry-run"] if dry_run else [])

    assert post_csv_to_calc.main(argv) == 2

    post.assert_not_called()
    assert not output.exists()
    captured = capsys.readouterr()
    assert "rows 1 and 2" in captured.err
    assert "output file" in captured.err
    assert "unique" in captured.err
    assert not captured.out


def test_late_duplicate_preserves_existing_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.csv"
    output = tmp_path / "responses"
    output.mkdir()
    previous = output / "car1.response.json"
    previous.write_text("previous result", encoding="utf-8")
    write_csv(source, [{"car_id": "car1"}, {"car_id": "car2"}, {"car_id": "car2"}])
    post = Mock(return_value=(200, {"taxable_value": 20}))
    monkeypatch.setattr(post_csv_to_calc, "_post_json", post)

    assert post_csv_to_calc.main(arguments(source, output)) == 2

    post.assert_not_called()
    assert previous.read_text(encoding="utf-8") == "previous result"
    assert list(output.iterdir()) == [previous]
    assert "rows 2 and 3" in capsys.readouterr().err


@pytest.mark.parametrize("dry_run", [False, True])
def test_unique_outputs_preserve_names_and_payloads(tmp_path, monkeypatch, dry_run):
    source = tmp_path / "input.csv"
    output = tmp_path / "responses"
    write_csv(
        source,
        [
            {"car_id": "car1", "asset_id": "ignored", "row_id": "ignored"},
            {"asset_id": "asset2", "row_id": "ignored"},
            {"row_id": "custom3"},
            {},
        ],
    )
    post = Mock(return_value=(200, {"taxable_value": 20}))
    monkeypatch.setattr(post_csv_to_calc, "_post_json", post)
    argv = arguments(source, output) + (["--dry-run"] if dry_run else [])

    assert post_csv_to_calc.main(argv) == 0

    if dry_run:
        post.assert_not_called()
        assert not output.exists()
        return
    assert post.call_count == 4
    assert len(list(output.iterdir())) == 4
    for index, identifier in enumerate(["car1", "asset2", "custom3", "row4"], start=1):
        envelope = json.loads((output / f"{identifier}.response.json").read_text("utf-8"))
        assert envelope["row"] == index
        assert envelope["row_id"] == identifier
        assert envelope["request_body"] == {
            "businessUsePercentage": 80,
            "formOfFinance": "leased",
        }
        assert envelope["response_status"] == 200
        assert envelope["response_body"] == {"taxable_value": 20}
