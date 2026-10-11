# AfterPass. Run `make help` for targets.
SHELL := /bin/bash
unexport VIRTUAL_ENV
UV := cd backend && uv run

.PHONY: help setup lint test smoke-apis check-winds detect fetch replay imagery qa smoke pm25 agent agent-test live serve-data web walkthrough a11y globe-assets build deploy publish-s3 deploy-web

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm install
	@test -f .env || echo "Note: copy .env.example to .env and add FIRMS_MAP_KEY"

lint: ## ruff + eslint
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

test: lint ## Lint, then run the backend and frontend unit tests
	$(UV) pytest -q
	cd frontend && npm run test

walkthrough: ## Record the full walkthrough (needs serve-data and web; `make agent` for the chat step)
	cd frontend && node scripts/walkthrough.mjs

a11y: ## Check every screen with axe at desktop and phone size (needs serve-data and web)
	cd frontend && node scripts/axe-check.mjs

globe-assets: ## Rebuild the hero globe's country outlines from Natural Earth
	$(UV) afterpass globe-assets

smoke-apis: ## Check FIRMS and Earth Search respond for Sangrur
	$(UV) python scripts/smoke_apis.py

check-winds: ## Check which Open-Meteo endpoints have 100 m wind and mixing height
	$(UV) python scripts/check_winds.py

detect: ## Detect burn scars for Sangrur, 1-15 Nov 2025, and render the quick-look
	$(UV) afterpass detect --district Sangrur --start 2025-11-01 --end 2025-11-15

fetch: ## Download and cache the 2025 season's imagery and FIRMS data
	$(UV) afterpass fetch --season 2025 --districts Sangrur,Bathinda,Firozpur

replay: ## Process the 2025 replay for the demo districts
	$(UV) afterpass replay --season 2025 --districts Sangrur,Bathinda,Firozpur

imagery: ## Render before/after crops for the top 20 villages
	$(UV) afterpass imagery --top 20 --season 2025

qa: ## Build the visual QA sheet (reports/qa_sheet.html)
	$(UV) afterpass validate --season 2025

smoke: ## Run the 2025 smoke replay: one 48-hour run per day, Delhi SAI and trails
	$(UV) afterpass smoke --season 2025

pm25: ## Compare the daily Delhi smoke index with observed PM2.5 (needs OPENAQ_API_KEY)
	$(UV) afterpass pm25 --season 2025

agent: ## Serve the agent locally on :8788 (calls the model; each question costs a little)
	$(UV) afterpass agent-serve

agent-test: ## Run the 10 scripted questions and save the transcript (calls the model)
	$(UV) afterpass agent-test

live: ## Process the 2026 season up to today
	$(UV) afterpass live

serve-data: ## Serve data/public on :8787 with CORS
	$(UV) python scripts/serve_data.py

web: ## Run the frontend dev server
	cd frontend && npm run dev

build: ## Build the frontend
	cd frontend && npm run build

deploy: ## Deploy the AWS stack to ap-southeast-2 (asks first; costs money)
	@echo "This creates or updates AWS resources in ap-southeast-2 and can cost money."
	@read -p "Type 'deploy' to continue: " ans && [ "$$ans" = "deploy" ] || (echo "Aborted."; exit 1)
	cd infra && sam validate --lint && sam build && sam deploy

publish-s3: ## Upload data/public to the data bucket (served by CloudFront)
	$(UV) afterpass publish --target s3

deploy-web: ## Build the frontend against the stack and upload it to Amplify Hosting
	$(UV) afterpass deploy-web
