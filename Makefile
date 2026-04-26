# =============================================================================
# Project VIA / Aegis — developer Makefile
# =============================================================================
# Targets are POSIX-shell-friendly and assume `docker compose` v2 is on PATH.
# On Windows, use Git Bash, WSL, or run the equivalent commands manually.
# =============================================================================

COMPOSE        ?= docker compose
COMPOSE_FILE   ?= docker-compose.yml
PYTEST         ?= python -m pytest
TEST_DIR       ?= tests
DB_URL         ?= postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis

# Default target prints help.
.DEFAULT_GOAL := help

.PHONY: help build up down restart migrate ps logs test drift clean nuke

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

build:  ## Build all service images.
	$(COMPOSE) build --pull

up:  ## Bring up the full stack (builds if needed, applies migrations).
	$(COMPOSE) up -d --build
	$(MAKE) migrate

down:  ## Stop and remove all containers (volumes preserved).
	$(COMPOSE) down --remove-orphans

restart: down up  ## Down + up.

migrate:  ## Apply DB migrations using the Flyway one-shot service.
	$(COMPOSE) --profile migrate run --rm db-migrate

ps:  ## Show container status.
	$(COMPOSE) ps

logs:  ## Tail logs for all services (use `make logs SVC=auth-service` for one).
ifdef SVC
	$(COMPOSE) logs -f $(SVC)
else
	$(COMPOSE) logs -f
endif

test:  ## Run the pytest suite (assumes stack is up).
	$(PYTEST) $(TEST_DIR) -v

drift:  ## Run the schema-drift CI guard against Sprint-baselined tables.
	python infra/db/schema_drift_check.py \
		--db "$(DB_URL)" \
		--only audit_engagements \
		--only risks \
		--only risk_assessments \
		--only risk_score_history

clean:  ## Stop containers and remove dangling images.
	$(COMPOSE) down --remove-orphans
	docker image prune -f

nuke:  ## DESTROYS all volumes (postgres data, kafka data, vault, minio). Confirm.
	@printf 'Type YES to wipe all volumes: '; \
	read ans; \
	if [ "$$ans" = "YES" ]; then \
		$(COMPOSE) down -v --remove-orphans; \
	else \
		echo "Aborted."; \
	fi
