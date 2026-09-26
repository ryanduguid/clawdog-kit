# ClawDog Kit

> *An agent-driven calculator kit for Australian tax & accounting. Built by LodgeiT Labs Foundation. Stage 1: FBT car operating-cost.*

ClawDog is a neurosymbolic accounting & tax engine. The **ClawDog Kit** is how humans (and their agents) feed real data into it.

This repo ships:

1. **CSV templates** that an accountant — or an accountant's agent — can fill in.
2. **A reference Python script** that reads those CSVs and POSTs them to the live ClawDog Calculator API.
3. **Voice-neutral agent instructions** so an LLM agent (Claude, ChatGPT, Cursor, your own MCP host) can drive the whole loop end-to-end without further hand-holding.
4. **Expected-output examples** so you can verify your wiring before trusting any computed value.

The kit talks to the public ClawDog Calculator API at:

```
https://fbt-calculator-api-8340695160.australia-southeast1.run.app
```

— a Cloud Run service in `australia-southeast1` operated by LodgeiT Labs Foundation. The API is read-side calculation only; no client data is persisted by the calculator.

---

## What's covered today

| Calculator | Status | Template | Engine |
|---|---|---|---|
| **FBT — Car (Operating Cost Method)** for FBT FY2026 | ✅ live + smoke-verified | [`templates/fbt-car-operating-cost/`](templates/fbt-car-operating-cost/) | Prolog (toolkit-shaped) on Cloud Run |
| FBT — Car (Statutory Formula Method) | 🔄 engine ships toolkit-shaped math; not yet wrapped at the calc-api surface | [`templates/_coming-soon/`](templates/_coming-soon/) | — |
| Depreciation — Audit (Prime Cost / Diminishing Value) | 🔄 route exists; engine deployment pending (tracking) | [`templates/_coming-soon/depreciation-audit/`](templates/_coming-soon/depreciation-audit/) | — |
| Div 7A loan calculator | 🔄 not yet onboarded to the calc-api surface | — | — |
| FBT non-car benefits (C / D / E / F / G / J / K / L / M / N / P) | 🔄 ATO taxonomy mapped; surface-by-surface onboarding queued | — | — |

Stage 1 deliberately covers exactly one calculator end-to-end. The point is to demonstrate the **pattern** — agents read templates, fill data, call the API, render results — not to be exhaustive. Adding a second calculator is purely additive: a new subdirectory under `templates/`, a couple of paragraphs in `AGENT_INSTRUCTIONS.md`, a new example. The agent contract stays stable.

---

## Quickstart (for humans)

```bash
git clone https://github.com/lodgeit-labs/clawdog-kit.git
cd clawdog-kit

# Smoke the live API with the canonical FBT example, no Python install needed:
curl -sS -X POST -H 'Content-Type: application/json' \
  -d @templates/fbt-car-operating-cost/examples/owned_modern_tier_full_year.input.json \
  'https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026'
```

The [expected response](templates/fbt-car-operating-cost/examples/owned_modern_tier_full_year.output.json) has a `taxable_value` of `"1905.05"` AUD.

**To run from CSV:**

```bash
python3 scripts/post_csv_to_calc.py \
  --calculator fbt-car-operating-cost \
  --period fy2026 \
  --input templates/fbt-car-operating-cost/sample.csv
```

The script rejects duplicate headers, rows with the wrong number of cells, invalid numeric values and unsafe or repeated output identifiers. It converts known fields, forwards unknown fields to the API for validation, and writes each response next to the CSV. An invalid later row stops processing with exit code 2; earlier responses remain available.

Local read or save failures also return exit code 2. If a response arrives but cannot be saved, the script stops and reports that distinction. Check processed rows before retrying. An existing response file is replaced only after the new response is fully written.

---

## Quickstart (for agents)

Read **[`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md)** first. It is the contract. It tells your agent:

- which calculators are covered + which URI to call
- what CSV schemas look like (column names, types, mutually-exclusive fields)
- what response shape to expect
- what to do when the API returns a structured error
- which fields are computed-by-the-engine vs supplied-by-the-user
- what NOT to invent (do not type a statutory percentage; the calculator looks it up from the period)

The instructions file is voice-neutral and copy-pasteable into a system prompt.

---

## What this kit is not

- **Not tax advice.** ClawDog Kit produces calculator outputs. Outputs reflect the period-scoped statutory rate-tables cited in each response's `manifest` block; statute may have changed since the rate-table was last anchored. The API itself returns this disclaimer in every response's `advisory` block. Consult a registered tax agent before relying on these numbers for any return, position, or advice provided to a third party. Statutory framing: TAA 1953 s284-15 (false or misleading statements) and the Tax Agent Services Act 2009 (registered-agent requirement).
- **Not a UI.** The kit is the *data layer*. A future kit will ship richer surfaces — schema-driven web widgets (the GL Playground), conversational entry through MCP elicitation, an Office.js Excel add-in. Today: CSVs + an agent contract.
- **Not multi-tenant.** The calculator API is public + unauthenticated by design (read-side calculation; no client data persisted). If you need per-firm data isolation, you bring your own client + agent + storage. The calculator is a stateless function.
- **Not a substitute for the engine repos.** The FBT engine itself lives at `lodgeit-labs/LodgeiT_FBT`; the depreciation engine at `lodgeit-labs/Depreciation_Transforms`. This kit is a thin contract over the calc-api wrapper, which is itself a REST + provenance wrapper over those Prolog engines.

---

## Architecture in one diagram

```
   ┌───────────────────────────────────────────────────┐
   │ Human + their agent (LLM, Cursor, MCP host, etc.) │
   └─────────────┬─────────────────────────────────────┘
                 │ reads CSV templates + AGENT_INSTRUCTIONS.md
                 ▼
   ┌───────────────────────────────────────────────────┐
   │ THIS KIT — clawdog-kit                            │
   │   templates/    CSV schemas + examples            │
   │   scripts/      reference Python impl             │
   │   examples/     end-to-end walk-throughs          │
   └─────────────┬─────────────────────────────────────┘
                 │ HTTPS POST (JSON)
                 ▼
   ┌───────────────────────────────────────────────────┐
   │ clawdog-calculator-api  (Cloud Run, AU-southeast1)│
   │   • validates input schema                        │
   │   • dispatches to Prolog engine                   │
   │   • wraps response with rate-table manifest       │
   │   • surfaces statutory advisory block             │
   └─────────────┬─────────────────────────────────────┘
                 │ internal HTTP
                 ▼
   ┌───────────────────────────────────────────────────┐
   │ Per-calculator Prolog engine (Cloud Run sibling)  │
   │   e.g. fbt-engine for FBT car operating-cost      │
   │   ships toolkit-shaped math + statute references  │
   └───────────────────────────────────────────────────┘
```

Every response carries a `manifest.rate_table_uris[]` list with `sha256` content-hashes — so you can verify which statutory rate-tables were applied, and notice when they change.

---

## Versioning + stability promise

The calc-api lives at `0.1.0a0` (alpha). The kit lives at `0.1.0` (Stage 1).

**Stability promises during alpha:**

- The `urn:sbrm:calculator:fbt:car-operating-cost` calculator URI is stable.
- The `urn:sbrm:period:fbt:fy2026` period URI is stable.
- The input schema field names (`businessUsePercentage`, `acquisitionCost`, etc.) are stable.
- The response shape (`taxable_value`, `trace`, `manifest`, `advisory` top-level keys) is stable.
- The `manifest.rate_table_uris[].sha256` discipline is stable.

**NOT promised during alpha:**

- Engine implementation details (the `trace` block's interior field names may evolve).
- Rate-table content (if statute changes, content_hashes will change; that's the *point*).
- Coverage scope (we're adding calculators).

When we hit 1.0 the calc-api API will lock fully. The kit will follow semantic versioning thereafter.

---

## Contributing

Issues + PRs welcome at `github.com/lodgeit-labs/clawdog-kit`.

**Especially welcome:**

- Additional CSV examples for edge cases (statutory changes, unusual benefit configurations)
- Translations of `AGENT_INSTRUCTIONS.md` into agent prompts that work well with particular LLMs
- Reference implementations in other languages (the Python script is the canonical example; ports to Node, Go, Ruby, etc. are welcome under `scripts/`)
- Bug reports: if an output doesn't match what your tax-agent says it should, open an issue with the input and the response — the calc-api ships toolkit-shaped math and any divergence is a real signal

**Less welcome until 1.0:**

- Schema-extension PRs (the schema is owned by the calc-api repo upstream; changes there propagate here)
- New calculator wrappers (we're sequencing these deliberately — open an issue first)

---

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

## Project home

- **Kit:** [github.com/lodgeit-labs/clawdog-kit](https://github.com/lodgeit-labs/clawdog-kit) (this repo)
- **Calc API:** [github.com/lodgeit-labs/clawdog-calculator-api](https://github.com/lodgeit-labs/clawdog-calculator-api)
- **ClawDog showcase:** [lodgeit.org/clawdog/](https://lodgeit.org/clawdog/)
- **Parent:** [LodgeiT Labs Foundation](https://github.com/lodgeit-labs)
