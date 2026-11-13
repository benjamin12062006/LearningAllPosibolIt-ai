# Servicio de IA de KTSU. Comandos del plan 01 («Comandos»).
.PHONY: install dev check lint format test test-qdrant test-google qdrant-up qdrant-down token

install:
	uv sync --locked

dev:
	uv run uvicorn --factory ktsu_ai.bootstrap.app:create_app_from_environment \
		--host 127.0.0.1 --port 8090 --reload --no-access-log

check: lint test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy
	uv run lint-imports

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

test:
	uv run pytest

test-qdrant:
	scripts/qdrant/qdrant.sh test

# Llama a Vertex AI con textos inventados (usa GOOGLE_CLOUD_PROJECT del .env).
test-google:
	TEST_GOOGLE_EMBEDDINGS=1 uv run pytest -m google

qdrant-up:
	scripts/qdrant/qdrant.sh up

qdrant-down:
	scripts/qdrant/qdrant.sh down

# Token para AI_SERVICE_TOKEN (el mismo en el .env de la API Nest).
token:
	@uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
