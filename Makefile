# clawdog-kit — Makefile
#
# Targets:
#   make help              show this list
#   make test              hermetic unit tests (no network)
#   make test-live         run unit tests AND the live-API smoke
#   make smoke             one-off curl against the live API with the canonical example
#   make sample-run        run the reference script against templates/.../sample.csv
#   make ruff              lint (only if ruff is installed; otherwise skipped)
#   make clean             remove caches + sample-run outputs
#
# Dependency-free by design: stdlib only. `pytest` is the one optional dev dep.

PY ?= python3
SAMPLE_CSV := templates/fbt-car-operating-cost/sample.csv
SAMPLE_OUT := _runs/sample
CANONICAL_INPUT := templates/fbt-car-operating-cost/examples/owned_modern_tier_full_year.input.json
CALC_API := https://fbt-calculator-api-8340695160.australia-southeast1.run.app
CALC_URI := urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost
PERIOD_URI := urn%3Asbrm%3Aperiod%3Afbt%3Afy2026

.PHONY: help test test-live smoke sample-run ruff clean

help:
	@echo "clawdog-kit make targets:"
	@echo "  make test          hermetic unit tests (no network)"
	@echo "  make test-live     run unit tests AND the live-API smoke (network required)"
	@echo "  make smoke         one-off curl against the live API with the canonical example"
	@echo "  make sample-run    run the reference script against $(SAMPLE_CSV)"
	@echo "  make ruff          lint (only if ruff is installed; otherwise skipped)"
	@echo "  make clean         remove caches + sample-run outputs"

test:
	$(PY) -m pytest -q

test-live:
	CLAWDOG_KIT_RUN_LIVE_SMOKE=1 $(PY) -m pytest -q

smoke:
	@echo "POSTing canonical example to $(CALC_API)..."
	@curl -sS -X POST -H 'Content-Type: application/json' \
	    -d @$(CANONICAL_INPUT) \
	    '$(CALC_API)/v1/calculators/$(CALC_URI)/$(PERIOD_URI)' \
	    | $(PY) -m json.tool

sample-run:
	@mkdir -p $(SAMPLE_OUT)
	$(PY) scripts/post_csv_to_calc.py \
	    --calculator fbt-car-operating-cost \
	    --period fy2026 \
	    --input $(SAMPLE_CSV) \
	    --output-dir $(SAMPLE_OUT)

ruff:
	@if command -v ruff >/dev/null 2>&1; then \
	    ruff check scripts/ tests/; \
	else \
	    echo "ruff not installed; skipping. Install with: pip install ruff"; \
	fi

clean:
	rm -rf .pytest_cache _runs
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
