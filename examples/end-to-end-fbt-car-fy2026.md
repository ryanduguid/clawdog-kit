# End-to-end walkthrough — FBT FY2026 car fleet

> *A complete worked example. An accountant has 3 cars in a fleet for FY2026 (1 April 2025 – 31 March 2026). They want the operating-cost-method taxable values. Either they or their LLM agent walks through this.*

---

## The setup

The accountant tells their agent:

> *"I need the FBT Car Operating Cost taxable values for my three cars for FY2026. Here's what I have:*
>
> *Car 1: 2024 Toyota Camry, bought new 1 April 2024 for $35,000. Held all year (366 days). 80% business use. Employee contributed $1,000 post-tax. $4,500 fuel/repairs/servicing, $1,200 rego/insurance.*
>
> *Car 2: 2022 Mazda 3, opening WDV at start of FBT year is $22,000. Held all year. 60% business use. $500 employee contribution. $3,200 fuel/repairs/servicing, $900 rego/insurance.*
>
> *Car 3: 2025 Tesla Model 3 on a 36-month operating lease. Lease payments $18,000 for the year. 100% business use. $5,200 fuel/repairs/servicing, $1,400 rego/insurance."*

---

## Step 1 — Agent reads the kit

The agent reads:

1. `AGENT_INSTRUCTIONS.md` at the repo root — the contract.
2. `templates/fbt-car-operating-cost/README.md` — the calculator-specific schema.
3. `templates/fbt-car-operating-cost/template.csv` — the column header.

The agent now knows:

- The calculator URI: `urn:sbrm:calculator:fbt:car-operating-cost`
- The period URI for FY2026: `urn:sbrm:period:fbt:fy2026`
- The CSV column shape (13 columns + 1 `notes` column)
- The `acquisitionCost` vs `openingDepreciatedValue` mutual-exclusion rule
- The `leased` path doesn't use either; it uses `leasePayments` directly

---

## Step 2 — Agent maps the human's input onto the CSV schema

The agent realises:

- **Car 1** has `acquisitionCost` ($35,000) + `acquisitionDate` (2024-04-01). Use the **chained-DV path**. Leave `openingDepreciatedValue` blank.
- **Car 2** has `openingDepreciatedValue` ($22,000) but no acquisition date. Use the **legacy path** (`deemed_dispatch=computed`). Leave `acquisitionCost` blank.
- **Car 3** is `leased` ($18,000 lease payments). Use the **leased path** (`deemed_dispatch=skipped_leased`). Leave both `acquisitionCost` and `openingDepreciatedValue` blank.

The agent composes (or asks the human to confirm) the following CSV:

```csv
car_id,businessUsePercentage,employeeContribution,formOfFinance,leasePayments,fuelRepairsServicing,registrationInsurance,noPrivateUseReduction,acquisitionDate,acquisitionCost,openingDepreciatedValue,daysHeldInFBTYear,deemedTotal,notes
CAMRY-001,80,1000,owned,,4500,1200,0,2024-04-01,35000,,366,,2024 Toyota Camry
MAZDA-002,60,500,owned,,3200,900,0,,,22000,366,,2022 Mazda 3 (opening WDV path)
TESLA-003,100,0,leased,18000,5200,1400,0,,,,366,,Tesla Model 3 (operating lease)
```

The agent saves this as `_runs/fbt-fy2026-fleet.csv` (under the gitignored `_runs/` tree).

---

## Step 3 — Agent runs the kit

```bash
python3 scripts/post_csv_to_calc.py \
  --calculator fbt-car-operating-cost \
  --period fy2026 \
  --input _runs/fbt-fy2026-fleet.csv \
  --output-dir _runs/fbt-fy2026/
```

The agent gets (writing to stderr/stdout):

```
  row 1 (CAMRY-001): HTTP 200  →  taxable_value=1909.89  →  _runs/fbt-fy2026/CAMRY-001.response.json
  row 2 (MAZDA-002): HTTP 200  →  taxable_value=4106.67  →  _runs/fbt-fy2026/MAZDA-002.response.json
  row 3 (TESLA-003): HTTP 200  →  taxable_value=0.0     →  _runs/fbt-fy2026/TESLA-003.response.json

Processed 3 row(s); failures=0; network_failures=0
```

Exit code 0.

---

## Step 4 — Agent presents results

```
FBT Car Operating Cost — FY2026 fleet summary
─────────────────────────────────────────────────────────────

CAMRY-001 (2024 Toyota Camry)
  Taxable value: AUD 1,909.89
  Dispatch path: computed_chained (OT #81 chained-DV walk from $35,000 acquisition on 2024-04-01)
  Working:
    Deemed total       $8,849.43  (deemed depreciation $6,580.48 + deemed interest $2,268.95)
    Operating costs    $5,700.00  (fuel/repairs/servicing $4,500 + rego/insurance $1,200)
    Total              $14,549.43
    Business-use reduction  $11,639.54  (80% of total)
    TV before contribution  $2,909.89
    Employee contribution   $1,000.00
    Taxable value           $1,909.89

MAZDA-002 (2022 Mazda 3)
  Taxable value: AUD 4,106.67
  Dispatch path: computed (legacy single-year path from supplied OpeningWDV $22,000)
  Working:
    Deemed total       $7,416.67  (deemed depreciation $5,515.07 + deemed interest $1,901.60)
    Operating costs    $4,100.00
    Total              $11,516.67
    Business-use reduction  $6,910.00  (60% of total)
    TV before contribution  $4,606.67
    Employee contribution   $500.00
    Taxable value           $4,106.67

TESLA-003 (Tesla Model 3 — operating lease)
  Taxable value: AUD 0.00
  Dispatch path: skipped_leased (no deemed amounts on leased vehicles)
  Working:
    Lease payments     $18,000.00
    Operating costs    $6,600.00  (fuel/repairs/servicing $5,200 + rego/insurance $1,400)
    Total              $24,600.00
    Business-use reduction  $24,600.00  (100% of total)
    Taxable value           $0.00

─────────────────────────────────────────────────────────────
Fleet total: AUD 6,016.56
```

---

## Step 5 — Agent surfaces provenance

```
Statutory rate-tables applied (per FY2026 SBRM bundle):
  • urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates
      sha256: 4d3a9e54d740de8df7961758d8f588cf76d3a37a638075b82b2811ddb3ad95df
  • urn:sbrm:rate:fbt:fy2026:benchmark-interest
      sha256: 1f9b83a89e9dd8a2b0c5484063818f9a8f1380be231d073c412382b99896580c
  • urn:sbrm:rate:fbt:fy2026:days-in-year
      sha256: 1786274a6a9dd3cc9a9edb2092f071bc2dd042c369a98603867036c74b4cfc87
  • urn:sbrm:rate:fbt:fy2026:days-in-year-by-fy
      sha256: 8f63d3bd1685acca00717d88cc262c79c731286cfc98a19bdb6c1b2648c8baca

(CAMRY-001 used all four. MAZDA-002 used the first three. TESLA-003 used none — leased path skipped deemed amounts.)
```

---

## Step 6 — Agent presents the advisory verbatim

> *This is calculator output, not advice. Consult a registered tax agent before relying on these numbers for any return, position, or advice provided to a third party. Calculator outputs reflect the period-scoped statutory rate-tables cited in the manifest block; statute may have changed since the rate-table was last anchored. Statutory framing: TAA 1953 s284-15 (false or misleading statements; penalty bands escalate with culpability) and the Tax Agent Services Act 2009 (registered-agent requirement).*
>
> Jurisdiction: AU. Registered tax agent required: Yes.

---

## What just happened

- The accountant described their fleet in natural language.
- The agent translated that description into the kit's CSV schema, honouring the calculator's domain rules (`acquisitionCost` vs `openingDepreciatedValue`; `leased` skips deemed amounts).
- The kit's reference script POSTed each row to the live calc-api.
- The agent presented the headline numbers, the working, the rate-table provenance, and the statutory advisory.
- The accountant has 3 calculated FBT taxable values, plus the audit trail to take to a registered tax agent.

The agent at no point typed a statutory percentage, invented a rate, or computed an intermediate value itself. The calc-api ships the math; the kit ships the contract.

---

## Variants the agent should handle

- **The accountant adds a 4th car halfway through.** Agent appends a row to the CSV; re-runs the script. New row gets POSTed; existing rows' outputs are overwritten (idempotent).
- **The accountant's data has typos** (e.g. `formOfFinance=onwed`). The script POSTs anyway; the calc-api returns 422 with a clear field/message; the script writes the 422 to `<car_id>.response.json` and exit code is 1. The agent reads the error, fixes the typo, re-runs.
- **The calc-api returns a 5xx.** The script writes the structured error (if present) or bare HTML (if not) to `<car_id>.response.json` and exit code is 1. The agent surfaces the issue to the human; does NOT silently retry.
- **The user wants the response in their own UI.** The script's per-row `.response.json` is the canonical artefact; the user's UI reads from there. (A future kit revision will ship richer renderers — see the kit's roadmap.)
