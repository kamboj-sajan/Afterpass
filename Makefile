# AfterPass. Run `make help` for targets.
SHELL := /bin/bash
unexport VIRTUAL_ENV
UV := cd backend && uv run

.PHONY: help setup lint test smoke-apis detect replay live serve-data web build deploy

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm install
	@test -f .env || echo "Note: copy .env.example to .env and add FIRMS_MAP_KEY"

lint: ## ruff + eslint
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

test: lint ## Lint, then run pytest
	$(UV) pytest -q

smoke-apis: ## Check FIRMS and Earth Search respond for Sangrur
	$(UV) python scripts/smoke_apis.py

detect: ## Detect burn scars for Sangrur, 1-15 Nov 2025, and render the quick-look
	$(UV) afterpass detect --district Sangrur --start 2025-11-01 --end 2025-11-15

replay: ## Process the 2025 replay for the demo districts
	$(UV) afterpass replay --season 2025 --districts Sangrur,Bathinda,Firozpur

live: ## Process the 2026 season up to today
	$(UV) afterpass live

serve-data: ## Serve data/public on :8787 with CORS
	$(UV) python scripts/serve_data.py

web: ## Run the frontend dev server
	cd frontend && npm run dev

build: ## Build the frontend
	cd frontend && npm run build

deploy: ## Deploy the AWS stack (asks first; costs money)
	@echo "This creates AWS resources in us-west-2 and can cost money."
	@read -p "Type 'deploy' to continue: " ans && [ "$$ans" = "deploy" ] || (echo "Aborted."; exit 1)
	@echo "Not implemented yet (Phase 6)."
