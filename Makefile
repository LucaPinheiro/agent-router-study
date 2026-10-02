COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
LANGFUSE_PORT ?= 3300

.PHONY: up up-app down logs health test lint e2e

up:
	$(COMPOSE) up -d --wait

up-app:
	$(COMPOSE) --profile app up -d --build --wait

down:
	$(COMPOSE) --profile app down

logs:
	$(COMPOSE) --profile app logs -f --tail=100

health:
	@curl -fsS localhost:$(LANGFUSE_PORT)/api/public/health && echo
	@docker exec $$($(COMPOSE) ps -q app-redis) redis-cli ping
	@curl -fsS localhost:8765/healthz 2>/dev/null && echo || echo "mcp-server: not running (make up-app)"
	@curl -fsS localhost:8766/readyz 2>/dev/null && echo || echo "mcp-server-large: not running (make up-app)"

test:
	uv run pytest -q -m "not integration"

lint:
	uv run ruff check . && uv run ruff format --check .

e2e:
	uv run pytest -q -rs -m integration tests/integration tests/routers/test_router_live.py
