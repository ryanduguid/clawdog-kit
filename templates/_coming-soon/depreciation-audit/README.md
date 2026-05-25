# `depreciation-audit` — Coming Soon

> *Status: route exists at the calc-api surface but is not yet end-to-end deployable. Engine deployment + cross-engine routing generalisation are tracked under Open Thread #44 (Phase 3c.4) on the upstream `lodgeit-labs/clawdog-calculator-api` roadmap.*

## What it will do

Cross-check ledger-side accumulated depreciation against the accounting-method projection (prime cost or diminishing value) at a supplied transition date. Surfaces a variance flag against the Brain-canon variance threshold shipped in the SBRM rate-tables.

**Target endpoint:**

```
POST /v1/calculators/depreciation/audit/urn%3Asbrm%3Aperiod%3Adepreciation%3Afy2026
```

**Target input shape** (per the calc-api's `DepreciationAuditInput` schema):

```json
{
  "transitionDate": "2024-07-01",
  "method": "dvmethod",
  "assetsToAudit": [
    {
      "assetId": "A001",
      "assetName": "Office Desk",
      "purchaseDate": "2020-07-01",
      "originalCost": 1200.0,
      "taxMethod": "dvmethod",
      "currentBookAccumDep": 800.0
    }
  ]
}
```

Note the multi-row shape — one POST audits many assets in a batch. This is the obvious case where a CSV template per asset row pays off; once the endpoint is live, the kit will ship a `template.csv` mirroring the asset-row schema.

## Why it's not ready today

Two upstream gaps:

1. **No deployed depreciation Prolog engine** — the calc-api's depreciation route looks up `DEPRECIATION_PROLOG_URL` from the environment and falls back to `http://localhost:8082` if unset. The Cloud Run service does not currently have that variable wired and there is no `depreciation-engine` Cloud Run service to point it at. Calling the endpoint today returns HTTP 500.
2. **Engine + route generalisation** — the calc-api currently has two parallel HTTP clients (one for FBT, one for depreciation) with two env vars. OT #44 (Phase 3c.4) collapses these into a single PrologClient with route-based dispatch, which is the cleaner substrate for going live.

Both gaps are LodgeiT Labs upstream work, sequenced in the calc-api roadmap.

## When this folder gets promoted

When the engine is deployed AND OT #44 closes (or earlier, if the engine is deployed under the parallel-client design first), this folder graduates to `templates/depreciation-audit/`. Watch:

- `lodgeit-labs/clawdog-calculator-api` releases
- The `GET /v1/calculators` endpoint — when depreciation calls start returning HTTP 200 reliably, the kit promotes
- This kit's `CHANGELOG.md` (or first-class release notes) when 0.1.x → 0.2.x

## Workaround for today

If you need depreciation calculations now and can run Prolog locally, the engine code is at `lodgeit-labs/Depreciation_Transforms`. The FBT path's chained-DV mechanics (used by `urn:sbrm:calculator:fbt:car-operating-cost`) cover the car-specific depreciation case via the OT #81 work; general accounting depreciation is the gap.

For most users, the right answer today is *"wait for the kit to graduate this folder"*.
