import json

import post_csv_to_calc
import pytest


@pytest.mark.parametrize(
    "contents,expected_posts",
    [
        ("businessUsePercentage,businessUsePercentage,formOfFinance\n80,20,owned\n", 0),
        ("businessUsePercentage,formOfFinance\n80,owned,extra\n", 0),
        ("businessUsePercentage,formOfFinance\n80\n", 0),
        ("businessUsePercentage,formOfFinance\nNaN,owned\n", 0),
        ("businessUsePercentage,formOfFinance\n1e999,owned\n", 0),
        ("businessUsePercentage,formOfFinance\ninvalid,owned\n", 0),
        ("car_id,businessUsePercentage,formOfFinance\n../escape,80,owned\n", 0),
        ("car_id,businessUsePercentage,formOfFinance\n..\\escape,80,owned\n", 0),
        ("car_id,businessUsePercentage,formOfFinance\nC:escape,80,owned\n", 0),
        ("car_id,businessUsePercentage,formOfFinance\nCAR,80,owned\ncar,20,owned\n", 1),
    ],
)
def test_rejects_invalid_csv_before_posting_affected_row(
    tmp_path, monkeypatch, contents, expected_posts
):
    source = tmp_path / "input.csv"
    source.write_text(contents, encoding="utf-8")
    outside = tmp_path / "escape.response.json"
    outside.write_text("preserve", encoding="utf-8")
    posted = []

    def post(url, payload, *, timeout):
        posted.append(payload)
        return 200, {"taxable_value": 0}

    monkeypatch.setattr(post_csv_to_calc, "_post_json", post)
    result = post_csv_to_calc.main([
        "--calculator", "fbt-car-operating-cost", "--period", "fy2026",
        "--input", str(source), "--output-dir", str(tmp_path / "out"),
    ])
    assert result == 2
    assert len(posted) == expected_posts
    assert outside.read_text(encoding="utf-8") == "preserve"
    if expected_posts:
        response = json.loads((tmp_path / "out" / "CAR.response.json").read_text())
        assert response["request_body"]["businessUsePercentage"] == 80
