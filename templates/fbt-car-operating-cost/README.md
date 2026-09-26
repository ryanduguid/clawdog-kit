# `fbt-car-operating-cost` — Template

> *FBT Car Benefit, Operating Cost Method, for FBT FY2026 (1 April 2025 – 31 March 2026).*

This template wraps the live calculator:

- **`calc_uri`:** `urn:sbrm:calculator:fbt:car-operating-cost`
- **`period_uri`:** `urn:sbrm:period:fbt:fy2026`
- **Endpoint:** `POST /v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026`

One row of `template.csv` = one car's FBT input. The reference script (`scripts/post_csv_to_calc.py`) reads each row, builds the JSON request, POSTs it, and writes the response JSON.

---

## CSV columns

| Column | Required? | Type | Description |
|---|---|---|---|
| `car_id` | recommended | string | Your own identifier for this car. Echoed back in the per-row output filename. NOT sent to the API. |
| `businessUsePercentage` | **YES** | number 0–100 | Business-use percentage. Decimal allowed. Clamped to [0, 100] by the engine. |
| `employeeContribution` | optional | number ≥ 0 | Post-tax employee contribution toward the benefit (AUD). Default `0`. |
| `formOfFinance` | **YES** | enum | One of `owned`, `hire_purchase`, `leased`, `unspecified`. Drives which fields the engine expects. |
| `leasePayments` | conditional | number ≥ 0 | Lease payments for the period (AUD). Required when `formOfFinance=leased`; blank/zero otherwise. |
| `fuelRepairsServicing` | recommended | number ≥ 0 | Fuel + repairs + servicing for the period (AUD). |
| `registrationInsurance` | recommended | number ≥ 0 | Registration + insurance for the period (AUD). |
| `noPrivateUseReduction` | optional | number ≥ 0 | No-private-use reduction (AUD). Default `0`. |
| `acquisitionDate` | conditional | ISO date (`YYYY-MM-DD`) | When the car was first held. Drives deemed-depreciation-tier dispatch (modern / middle / old). Required when using `acquisitionCost`. |
| `acquisitionCost` | conditional | number ≥ 0 | Original acquisition cost (AUD). Mutually exclusive with `openingDepreciatedValue`. When supplied with `acquisitionDate`, the engine chained-walks DV across each intervening FBT year (`deemed_dispatch=computed_chained`). |
| `openingDepreciatedValue` | conditional | number ≥ 0 | Opening DV at start of FBT year (AUD). Mutually exclusive with `acquisitionCost`. Used when the human already knows the DV and doesn't want the engine to compute it from acquisition cost (`deemed_dispatch=computed`). |
| `daysHeldInFBTYear` | recommended | integer 1–366 | Days the car was held in the FBT year (FY2026: 366 days; leap year). |
| `deemedTotal` | optional | number ≥ 0 | Override the engine's computed deemed total. Leave blank to let the engine compute. |
| `notes` | optional | free text | Your notes. NOT sent to the API. |

**Empty cells are treated as "field not present"** — the engine applies its default (`employeeContribution: 0`, `daysHeldInFBTYear: 365` if missing, etc.). Don't insert `0` where you mean "not applicable" — the script converts empty cells to `null`/absent in the JSON body.

---

## The `acquisitionCost` vs `openingDepreciatedValue` rule

You must supply **exactly one** of these for `owned` and `hire_purchase` finance forms:

- **`acquisitionCost` + `acquisitionDate`** — the engine chain-walks the DV from acquisition cost across each FBT year between then and now, using each year's actual days-in-year and applicable rate. This is the **OT #81 chained-DV path**; trace shows `deemed_dispatch: "computed_chained"`. Use this when you have the ATO-shaped original cost and date but don't have the year-end DVs handy.
- **`openingDepreciatedValue`** — you tell the engine the opening DV at the start of the FBT year; the engine computes a single year's deemed amounts from there. Trace shows `deemed_dispatch: "computed"`. Use this when you already have the carried-forward DV (e.g. from last year's FBT return).

Supplying BOTH returns a `422 Unprocessable Entity` with a field-conflict error. Supplying NEITHER on `owned`/`hire_purchase` returns a different `422`.

For `leased`, **neither** is used — the engine takes `leasePayments` directly. Trace shows `deemed_dispatch: "skipped_leased"`.

---

## Examples

Each example below is a complete input/output pair captured against the live calc-api. Use them to verify your wiring before trusting any of your own computed numbers.

### Example 1 — Owned, modern tier, full year (OT #81 chained-DV path)

- Input: [`examples/owned_modern_tier_full_year.input.json`](examples/owned_modern_tier_full_year.input.json)
- Output: [`examples/owned_modern_tier_full_year.output.json`](examples/owned_modern_tier_full_year.output.json)

Acquisition cost $35,000 on 2024-04-01; held the full FBT year (366 days, leap year); 80% business use; $1,000 employee contribution; $4,500 fuel/repairs/servicing; $1,200 rego/insurance.

**Expected headline:** `taxable_value: 1909.89` (AUD).
**Expected dispatch:** `deemed_dispatch: "computed_chained"`.

Compute by hand to sanity-check: deemed total $8,849.43 + ops $5,700 = $14,549.43; business-use reduction 80% × $14,549.43 = $11,639.54; TV before operating $2,909.89; minus $1,000 employee contribution = $1,909.89. Matches.

### Example 2 — Owned, explicit OpeningWDV (legacy path)

- Input: [`examples/owned_opening_wdv.input.json`](examples/owned_opening_wdv.input.json)
- Output: [`examples/owned_opening_wdv.output.json`](examples/owned_opening_wdv.output.json)

`openingDepreciatedValue: 22000` from a 2022-04-01 acquisition; 60% business use; $500 employee contribution.

**Expected headline:** `taxable_value: 4106.67` (AUD).
**Expected dispatch:** `deemed_dispatch: "computed"`.

### Example 3 — Leased (deemed amounts skipped)

- Input: [`examples/leased.input.json`](examples/leased.input.json)
- Output: [`examples/leased.output.json`](examples/leased.output.json)

`formOfFinance: "leased"`; `leasePayments: 18000`; 100% business use.

**Expected headline:** `taxable_value: 0.00` (AUD).
**Expected dispatch:** `deemed_dispatch: "skipped_leased"`.

Sanity check: ops = $18,000 + $5,200 + $1,400 = $24,600; business-use reduction at 100% = $24,600; net = 0. Matches.

---

## Running the template

### One-off curl (manual test)

```bash
curl -sS -X POST -H 'Content-Type: application/json' \
  -d @examples/owned_modern_tier_full_year.input.json \
  'https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026' \
  | python3 -m json.tool
```

### Batch via CSV

```bash
# From the repo root:
python3 scripts/post_csv_to_calc.py \
  --calculator fbt-car-operating-cost \
  --period fy2026 \
  --input templates/fbt-car-operating-cost/sample.csv \
  --output-dir _runs/fbt-fy2026/
```

The script writes one JSON file per row, named `<car_id>.response.json`, into `--output-dir` (gitignored by default). Identifiers must be unique without regard to case and must not contain `/`, `\` or `:`. Invalid rows stop processing with exit code 2; earlier responses remain available.

---

## Reading the response

See [`AGENT_INSTRUCTIONS.md`](../../AGENT_INSTRUCTIONS.md) at repo root for the canonical contract. Headline fields:

- `taxable_value` — the FBT taxable value, AUD.
- `trace.deemed_dispatch` — which path the engine used.
- `trace.business_use_reduction`, `trace.deemed_total`, etc. — the working.
- `manifest.rate_table_uris[]` — the statutory rate-table content_hashes anchored to this calculation.
- `advisory` — the registered-agent disclaimer + statutory_basis (TAA 1953 / Tax Agent Services Act 2009). Present verbatim.

---

## When this template will change

- **Statutory rate updates** (between FBT years, or mid-year amendments): the calc-api's underlying rate-tables get updated. The kit's content_hashes in example outputs will change. The CSV column shape stays stable.
- **Schema extensions** at the calc-api: if a new input field becomes useful (e.g. s.8A EV exemption parameters got their own field in OT #79), the template gains a new column. Old rows still work; the new column is optional or has a sensible default.
- **Breaking changes**: bumped to a new period URI. The kit will ship a new template under `templates/fbt-car-operating-cost-fy2027/` (or similar); the FY2026 template stays for historical recomputation.

You can always discover the live schema with `GET /v1/calculators` + `GET /openapi.json` against the calc-api.
