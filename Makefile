# AfterPass. Run `make help` for targets.
SHELL := /bin/bash
unexport VIRTUAL_ENV
UV := cd backend && uv run

.PHONY: help setup lint test smoke-apis check-winds detect fetch replay imagery imagery-migrate qa smoke pm25 agent agent-test live serve-data web walkthrough a11y globe-assets build deploy publish-s3 deploy-web pipeline-run schedule-on schedule-off destroy seed-cache

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

imagery: ## Render before/after crops for the top 20 villages (SEASON=2026 for the live season)
	$(UV) afterpass imagery --top 20 --season $(or $(SEASON),2025)

imagery-migrate: ## One-off: move crops from imagery/{village}/ to imagery/2025/{village}/
	$(UV) afterpass imagery-migrate --season 2025

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

REGION := ap-southeast-2
# Where failure emails go: ALERT_EMAIL in .env, so the address stays out of the repository.
ALERT_EMAIL := $(shell grep -s '^ALERT_EMAIL=' .env | cut -d= -f2)

deploy: ## Deploy the AWS stack to ap-southeast-2 (asks first; costs money)
	@echo "This creates or updates AWS resources in $(REGION) and can cost money."
	@read -p "Type 'deploy' to continue: " ans && [ "$$ans" = "deploy" ] || (echo "Aborted."; exit 1)
	@test -n "$(ALERT_EMAIL)" || (echo "Set ALERT_EMAIL in .env first."; exit 1)
	cd infra && sam validate --lint && sam build && sam deploy --parameter-overrides AlertEmail=$(ALERT_EMAIL)

pipeline-run: ## Start one full run of the live pipeline on AWS (about $0.30)
	aws stepfunctions start-execution --region $(REGION) --input '{"mode": "full"}' \
		--state-machine-arn $$(aws cloudformation describe-stacks --region $(REGION) --stack-name afterpass \
			--query "Stacks[0].Outputs[?OutputKey=='PipelineArn'].OutputValue" --output text)

schedule-on: ## Switch on the daily 19:12 and 07:12 IST runs (costs about $0.30 a day)
	$(UV) afterpass schedules --state on

schedule-off: ## Switch the daily runs off
	$(UV) afterpass schedules --state off

destroy: ## Delete the AWS stack (asks first). The data bucket is kept; empty and delete it by hand.
	@read -p "Type 'destroy' to delete the afterpass stack in $(REGION): " ans && [ "$$ans" = "destroy" ] || (echo "Aborted."; exit 1)
	cd infra && sam delete --stack-name afterpass --region $(REGION) --no-prompts

publish-s3: ## Upload data/public to the data bucket (served by CloudFront)
	$(UV) afterpass publish --target s3

deploy-web: ## Build the frontend against the stack and upload it to Amplify Hosting
	$(UV) afterpass deploy-web

seed-cache: ## Upload the pipeline's small reference files to the data bucket
	$(UV) afterpass seed-cache
