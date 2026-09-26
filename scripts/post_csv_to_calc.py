#!/usr/bin/env python3
"""
post_csv_to_calc.py — reference implementation of the ClawDog Kit pipeline.

Reads a CSV (one calculation per row), builds the JSON request per the
calculator's input schema, POSTs to the live clawdog-calculator-api on
Cloud Run, and writes the response as a JSON file alongside the CSV.

Dependency-free: only Python 3.10+ stdlib (csv, json, urllib, argparse,
pathlib). The whole point is that ANY agent on ANY machine can run this
without `pip install` — drop it in, run it.

The script is the *reference* impl, not the only impl. Ports to Node, Go,
Ruby, etc. are welcome under scripts/. As long as the wire shape matches
the calc-api's OpenAPI schema, your port is correct.

Exit codes:
    0  all rows succeeded (HTTP 200)
    1  one or more rows failed (HTTP 4xx/5xx); per-row .response.json
       files still written so you can inspect what came back
    2  malformed CSV, invalid row values/arguments or local input/output failure
    3  network failure (timeout, DNS failure, TLS error) — distinct from
       a structured 5xx so retry-loops can distinguish

Usage:
    python3 scripts/post_csv_to_calc.py \
        --calculator fbt-car-operating-cost \
        --period fy2026 \
        --input templates/fbt-car-operating-cost/sample.csv \
        --output-dir _runs/fbt-fy2026/

Or for one-off testing without writing files anywhere:
    python3 scripts/post_csv_to_calc.py \
        --calculator fbt-car-operating-cost \
        --period fy2026 \
        --input templates/fbt-car-operating-cost/sample.csv \
        --dry-run
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration — the canonical URI table.
#
# Keeping this in the script (vs deriving from `GET /v1/calculators` at
# runtime) is a deliberate choice: the kit ships a known-good mapping for
# the calculators it documents. If a new calculator lands on the calc-api
# that this script doesn't know about, the user can supply --calc-uri /
# --period-uri overrides; otherwise we want predictable behaviour.
# ---------------------------------------------------------------------------

API_BASE_URL = "https://fbt-calculator-api-8340695160.australia-southeast1.run.app"

CALC_URI_MAP: dict[str, str] = {
    "fbt-car-operating-cost": "urn:sbrm:calculator:fbt:car-operating-cost",
}

PERIOD_URI_MAP: dict[tuple[str, str], str] = {
    ("fbt-car-operating-cost", "fy2026"): "urn:sbrm:period:fbt:fy2026",
}

# Fields that are NOT part of the calculator input — these are user-side
# CSV bookkeeping columns that the script strips before building the
# request body.
RESERVED_CSV_COLUMNS: frozenset[str] = frozenset({
    "car_id",
    "asset_id",
    "row_id",
    "notes",
    "comments",
})

WINDOWS_RESERVED_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
})

# Field-type coercion table. The CSV layer is text-only; we cast back to
# the type the calc-api's pydantic model expects. Unknown fields pass
# through as strings (the calc-api will 422 on shape mismatch with a clear
# error message — better than silently sending garbage).
FIELD_TYPE_HINTS: dict[str, str] = {
    "businessUsePercentage": "number",
    "employeeContribution":  "number",
    "formOfFinance":         "string",
    "leasePayments":         "number",
    "fuelRepairsServicing":  "number",
    "registrationInsurance": "number",
    "noPrivateUseReduction": "number",
    "acquisitionDate":       "string",
    "acquisitionCost":       "number",
    "openingDepreciatedValue": "number",
    "daysHeldInFBTYear":     "integer",
    "deemedTotal":           "number",
    # Depreciation-audit fields (will activate when that template promotes
    # out of _coming-soon/):
    "transitionDate":        "string",
    "method":                "string",
    "originalCost":          "number",
    "currentBookAccumDep":   "number",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce(value: str, hint: str) -> Any:
    """Cast a CSV cell to the type the calc-api expects.

    Empty cells map to ``None`` (= "field not present" — the calc-api
    treats this as "use the schema default" for optional fields).
    """
    v = value.strip()
    if v == "":
        return None
    if hint == "integer":
        return int(v)
    if hint == "number":
        # int values pass through as int; float otherwise. Both serialise
        # cleanly to JSON numbers.
        if "." in v or "e" in v.lower():
            result = float(v)
        else:
            try:
                return int(v)
            except ValueError:
                result = float(v)
        if not math.isfinite(result):
            raise ValueError("numeric fields must be finite")
        return result
    # default: string
    return v


def _row_to_payload(row: dict[str, str]) -> dict[str, Any]:
    """Turn a CSV row (str->str) into a request body (str->typed)."""
    payload: dict[str, Any] = {}
    for key, raw in row.items():
        if key in RESERVED_CSV_COLUMNS:
            continue
        if raw is None:
            continue
        hint = FIELD_TYPE_HINTS.get(key, "string")
        coerced = _coerce(raw, hint)
        if coerced is None:
            # omit absent fields entirely so the calc-api uses its default
            continue
        payload[key] = coerced
    return payload


def _output_filename(row_id: str) -> str:
    """Validate a response filename for common Windows and Unix filesystems."""
    filename = f"{row_id}.response.json"
    stem = filename.split(".", 1)[0].rstrip(" ").upper()
    if (
        any(ord(char) < 32 or char in '<>:"/\\|?*' for char in filename)
        or stem in WINDOWS_RESERVED_NAMES
        or len(filename.encode("utf-8")) > 255
    ):
        raise ValueError("identifier is not a portable response filename")
    return filename


def _save_response(path: Path, envelope: dict[str, Any]) -> None:
    """Replace an earlier response only after the new response is fully written."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".clawdog-", suffix=".tmp", delete=False,
        ) as fh:
            temporary = Path(fh.name)
            json.dump(envelope, fh, indent=2)
        temporary.replace(path)
    except BaseException:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise


def _build_endpoint(calc_alias: str, period_alias: str) -> tuple[str, str]:
    """Resolve --calculator/--period aliases to encoded URIs + the full URL."""
    calc_uri = CALC_URI_MAP.get(calc_alias)
    if calc_uri is None:
        known = ", ".join(sorted(CALC_URI_MAP.keys())) or "(none)"
        raise SystemExit(
            f"unknown calculator alias {calc_alias!r}. "
            f"Known aliases: {known}. "
            f"For a calculator the kit doesn't know, supply --calc-uri / "
            f"--period-uri directly."
        )
    period_uri = PERIOD_URI_MAP.get((calc_alias, period_alias))
    if period_uri is None:
        known = ", ".join(
            sorted(k[1] for k in PERIOD_URI_MAP if k[0] == calc_alias)
        ) or "(none)"
        raise SystemExit(
            f"unknown period alias {period_alias!r} for calculator "
            f"{calc_alias!r}. Known periods: {known}."
        )
    return calc_uri, period_uri


def _build_url(api_base: str, calc_uri: str, period_uri: str) -> str:
    enc_calc = urllib.parse.quote(calc_uri, safe="")
    enc_period = urllib.parse.quote(period_uri, safe="")
    return f"{api_base.rstrip('/')}/v1/calculators/{enc_calc}/{enc_period}"


def _post_json(url: str, body: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any] | str]:
    """POST JSON, return (status, parsed-json-or-raw-text)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "clawdog-kit/0.1.0 (+https://github.com/lodgeit-labs/clawdog-kit)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            text = resp.read().decode("utf-8")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = text
            return status, parsed
    except urllib.error.HTTPError as e:
        # 4xx / 5xx with a body — preserve the structured body if any.
        status = e.code
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = text
        return status, parsed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="POST a CSV of calculator inputs against clawdog-calculator-api.",
        epilog=(
            "Default API base: " + API_BASE_URL + ". Override with --api-base "
            "if you're running the calc-api locally or against a staging surface."
        ),
    )
    parser.add_argument("--calculator", required=True,
                        help="Calculator alias, e.g. fbt-car-operating-cost.")
    parser.add_argument("--period", required=True,
                        help="Period alias, e.g. fy2026.")
    parser.add_argument("--input", required=True, type=Path,
                        help="Path to a CSV file with one row per calculation.")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory to write per-row JSON responses. "
                             "Default: alongside the input CSV.")
    parser.add_argument("--api-base", default=API_BASE_URL,
                        help="API base URL (default: production calc-api).")
    parser.add_argument("--calc-uri", default=None,
                        help="Override calc URI directly (skip --calculator alias lookup).")
    parser.add_argument("--period-uri", default=None,
                        help="Override period URI directly (skip --period alias lookup).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build + print payloads but do NOT POST. No files written.")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="Per-request timeout in seconds (default: 60).")
    args = parser.parse_args(argv)

    try:
        input_exists = args.input.is_file()
    except OSError as exc:
        print(f"ERROR: cannot inspect input CSV: {exc}", file=sys.stderr)
        return 2
    if not input_exists:
        print(f"ERROR: input CSV not found: {args.input}", file=sys.stderr)
        return 2

    if args.calc_uri and args.period_uri:
        calc_uri, period_uri = args.calc_uri, args.period_uri
    else:
        calc_uri, period_uri = _build_endpoint(args.calculator, args.period)

    url = _build_url(args.api_base, calc_uri, period_uri)

    out_dir = args.output_dir if args.output_dir else args.input.parent
    if not args.dry_run:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"ERROR: cannot create output directory: {exc}", file=sys.stderr)
            return 2

    failures = 0
    rows_processed = 0
    network_failures = 0
    output_ids: set[str] = set()

    try:
        with args.input.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh, strict=True)
            if reader.fieldnames is None:
                print(f"ERROR: CSV has no header row: {args.input}", file=sys.stderr)
                return 2
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                print("ERROR: CSV header names must be unique", file=sys.stderr)
                return 2
            for idx, row in enumerate(reader, start=1):
                if None in row or any(value is None for value in row.values()):
                    print(f"ERROR: row {idx} does not match the CSV header width", file=sys.stderr)
                    return 2
                row_id = (
                    row.get("car_id")
                    or row.get("asset_id")
                    or row.get("row_id")
                    or f"row{idx}"
                )
                try:
                    filename = _output_filename(row_id)
                except ValueError:
                    print(f"ERROR: row {idx} identifier is not a portable filename", file=sys.stderr)
                    return 2
                if row_id.casefold() in output_ids:
                    print(f"ERROR: row {idx} repeats an output identifier", file=sys.stderr)
                    return 2
                output_ids.add(row_id.casefold())
                try:
                    payload = _row_to_payload(row)
                except ValueError:
                    print(f"ERROR: row {idx} contains an invalid numeric value", file=sys.stderr)
                    return 2

                if args.dry_run:
                    print(f"--- row {idx} ({row_id}) — DRY RUN ---")
                    print(f"  POST {url}")
                    print(f"  body: {json.dumps(payload, indent=2)}")
                    rows_processed += 1
                    continue

                try:
                    status, body = _post_json(url, payload, timeout=args.timeout)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    print(f"  row {idx} ({row_id}): NETWORK FAILURE — {exc}", file=sys.stderr)
                    network_failures += 1
                    rows_processed += 1
                    continue

                out_path = out_dir / filename
                envelope = {
                    "row": idx,
                    "row_id": row_id,
                    "request_url": url,
                    "request_body": payload,
                    "response_status": status,
                    "response_body": body,
                }
                try:
                    _save_response(out_path, envelope)
                except OSError as exc:
                    print(
                        f"ERROR: row {idx} response received but could not be saved: {exc}. "
                        "Earlier rows may already have been processed; check them before retrying.",
                        file=sys.stderr,
                    )
                    return 2

                if 200 <= status < 300:
                    taxable = (
                        body.get("taxable_value")
                        if isinstance(body, dict) else None
                    )
                    print(f"  row {idx} ({row_id}): HTTP {status}  →  taxable_value={taxable}  →  {out_path}")
                else:
                    failures += 1
                    err_summary = ""
                    if isinstance(body, dict):
                        detail = body.get("detail")
                        if isinstance(detail, dict):
                            err_summary = detail.get("error") or str(detail)[:120]
                        elif isinstance(detail, list):
                            err_summary = "; ".join(
                                f"{d.get('loc',[''])[-1]}:{d.get('msg','')}" for d in detail
                            )[:160]
                        else:
                            err_summary = str(detail)[:120]
                    print(
                        f"  row {idx} ({row_id}): HTTP {status}  →  {err_summary}  →  {out_path}",
                        file=sys.stderr,
                    )

                rows_processed += 1

    except csv.Error as exc:
        print(f"ERROR: malformed CSV: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot read input CSV: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"Processed {rows_processed} row(s); failures={failures}; network_failures={network_failures}")
    if network_failures:
        return 3
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
