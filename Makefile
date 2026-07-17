.PHONY: help up down up-kafka logs ps build clean test lint-layers setup

COMPOSE      = docker compose
COMPOSE_KAFKA = docker compose -f docker-compose.yml -f docker-compose.kafka.yml
ENV_FILE      = .env

help:        ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup:       ## First-time setup: copy .env, pull images
	@if [ ! -f .env ]; then cp .env.local .env; echo "Created .env — add your OPENAI_API_KEY"; fi
	$(COMPOSE) pull --ignore-pull-failures || true

up:          ## Start all services (Kafka runs in SYNC_MODE — no broker needed)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  ✅ AI Tutor Agent running"
	@echo "  🌐  App:       http://localhost"
	@echo "  🤖  LLM GW:   http://localhost:18000/docs"
	@echo "  📦  MinIO:     http://localhost:9101  (admin/minioadmin)"
	@echo "  🗄️   PG:        localhost:5432"
	@echo "  🔴  Redis:     localhost:6379"
	@echo "  🌲  Weaviate:  http://localhost:18080"
	@echo ""
	@echo "  Run 'make logs' to follow logs"

up-kafka:    ## Start all services including real Kafka broker
	@sed -i '' 's/KAFKA_SYNC_MODE=true/KAFKA_SYNC_MODE=false/' .env || true
	$(COMPOSE_KAFKA) up -d --build

down:        ## Stop all services
	$(COMPOSE) down

down-volumes: ## Stop all services and delete volumes (WIPES DATA)
	$(COMPOSE) down -v

logs:        ## Follow logs from all services
	$(COMPOSE) logs -f --tail=50

logs-%:      ## Follow logs from a specific service (e.g. make logs-llm-gateway)
	$(COMPOSE) logs -f --tail=50 $*

ps:          ## Show service status
	$(COMPOSE) ps

build:       ## Rebuild all images without cache
	$(COMPOSE) build --no-cache

restart-%:   ## Restart a specific service (e.g. make restart-chat-orchestrator)
	$(COMPOSE) restart $*

shell-%:     ## Open a shell in a running service container
	$(COMPOSE) exec $* /bin/sh

test:        ## Run all Python unit tests locally (no Docker)
	@for svc in services/llm-gateway services/embedding-service services/rag-pipeline \
	  services/content-ingestion services/chat-orchestrator services/agent-reasoning \
	  services/confidence-grader libs/kafka libs/vector-db libs/auth libs/cache \
	  libs/logging libs/metrics; do \
	  echo ""; \
	  echo "=== Testing $$svc ==="; \
	  if [ -f $$svc/.venv/bin/pytest ]; then \
	    cd $$svc && .venv/bin/python -m pytest --tb=short -q 2>&1 | tail -5; cd -; \
	  else \
	    echo "  (no venv — run: cd $$svc && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"; \
	  fi; \
	done

migrate:     ## Run database migrations
	$(COMPOSE) exec postgres psql -U ai_tutor -d ai_tutor -f /docker-entrypoint-initdb.d/seeds/001_roles.sql
	$(COMPOSE) exec postgres psql -U ai_tutor -d ai_tutor -f /docker-entrypoint-initdb.d/seeds/002_admin_config.sql

health:      ## Check health of all services
	@echo "Checking service health..."
	@for url in \
	  "http://localhost/health|API Gateway" \
	  "http://localhost:18000/api/internal/llm/health|LLM Gateway" \
	  "http://localhost:8001/api/internal/embeddings/health|Embedding Svc" \
	  "http://localhost:8002/health|RAG Pipeline" \
	  "http://localhost:8003/health|Content Ingestion" \
	  "http://localhost:8004/health|Chat Orchestrator" \
	  "http://localhost:8005/health|Agent Reasoning" \
	  "http://localhost:8006/health|Confidence Grader" \
	  "http://localhost:18080/v1/.well-known/ready|Weaviate"; do \
	  endpoint=$$(echo $$url | cut -d'|' -f1); \
	  name=$$(echo $$url | cut -d'|' -f2); \
	  status=$$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 $$endpoint); \
	  if [ "$$status" = "200" ]; then \
	    echo "  ✅  $$name"; \
	  else \
	    echo "  ❌  $$name (HTTP $$status)"; \
	  fi; \
	done

clean:       ## Remove all containers, images, and volumes
	$(COMPOSE) down -v --rmi local

lint-layers: ## Check architectural layer violations across all services and libs (REQ-009)
	@echo "Checking architectural layer contracts via import-linter..."
	@echo "Install dev deps first: pip install -r dev-requirements.txt"
	@echo ""
	@FAILED=0; \
	for svc in services/chat-orchestrator services/llm-gateway services/rag-pipeline \
	  services/embedding-service services/content-ingestion services/content-management \
	  services/agent-reasoning services/confidence-grader services/admin-config \
	  services/analytics services/assessment services/audit services/learner-profile; do \
	  svc_name=$$(basename $$svc); \
	  echo "--- $$svc_name ---"; \
	  result=$$(cd $$svc && PYTHONPATH=src lint-imports --config ../../.importlinter 2>&1); \
	  if echo "$$result" | grep -q "KEPT\|Broken\|ERROR"; then \
	    echo "$$result" | grep -E "KEPT|Broken|ERROR|Violation"; \
	    FAILED=$$((FAILED + 1)); \
	  else \
	    echo "  ✅ No violations"; \
	  fi; \
	done; \
	for lib in libs/auth libs/cache libs/kafka libs/logging libs/metrics libs/vector-db; do \
	  lib_name=$$(basename $$lib); \
	  echo "--- lib:$$lib_name ---"; \
	  result=$$(cd $$lib && PYTHONPATH=src lint-imports --config ../../.importlinter 2>&1); \
	  if echo "$$result" | grep -q "KEPT\|Broken\|ERROR"; then \
	    echo "$$result" | grep -E "KEPT|Broken|ERROR|Violation"; \
	    FAILED=$$((FAILED + 1)); \
	  else \
	    echo "  ✅ No violations"; \
	  fi; \
	done; \
	echo ""; \
	if [ "$$FAILED" -gt 0 ]; then \
	  echo "❌ $$FAILED service(s) have layer violations — see above"; \
	  exit 1; \
	else \
	  echo "✅ All architectural layer contracts satisfied"; \
	fi
