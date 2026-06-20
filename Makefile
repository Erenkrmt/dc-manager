# =============================================================================
# Makefile – DC Trade Toolbox
# Common tasks for development and deployment.
# =============================================================================

.PHONY: help install dev streamlit api docker-build docker-up docker-down test clean env env-encrypt

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies (uv)
	pip install uv && uv sync

dev: ## Start both Streamlit + FastAPI for development
	python scripts/run.py

streamlit: ## Start only Streamlit (web UI)
	streamlit run src/web/app.py --server.port 8501

api: ## Start only FastAPI (REST API)
	uvicorn src.web.api:app --reload --host 0.0.0.0 --port 8000

docker-build: ## Build Docker image
	docker compose build

docker-up: ## Start all services (Docker)
	docker compose up -d

docker-up-db: ## Start with PostgreSQL (Docker)
	docker compose --profile db up -d

docker-down: ## Stop all services (Docker)
	docker compose down

docker-logs: ## Show logs
	docker compose logs -f

env: ## Decrypt .env.encrypted → .env (requires age key in ~/.config/sops/age/keys.txt)
	@bash scripts/setup_env.sh

env-encrypt: ## Encrypt .env → .env.encrypted (requires age key in ~/.config/sops/age/keys.txt)
	SOPS_AGE_KEY_FILE=$$HOME/.config/sops/age/keys.txt sops --encrypt --input-type dotenv --output-type dotenv .env > .env.encrypted
	@echo "✅ Encrypted .env → .env.encrypted"

test: ## Run tests
	python -m pytest tests/ -v

clean: ## Clean Python cache and data
	rm -rf __pycache__ .pytest_cache
	rm -rf src/__pycache__ src/*/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned cache files (data/dc_trade.db kept)"