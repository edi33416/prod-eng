.PHONY: lint typecheck test integration coverage test-pg check all clean up down dev

lint:
	ruff check .
	ruff format --check .

typecheck:
	pyright src/

test:
	pytest tests/unit/ -v

integration:
	pytest tests/integration/ -v

coverage:
	pytest tests/ --cov --cov-report=term-missing

TEST_DATABASE_URL ?= postgresql://test:test@localhost:5433/bookshelf_test

test-pg:
	docker compose -f docker-compose.test.yml up -d --wait
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) pytest tests/; \
	status=$$?; docker compose -f docker-compose.test.yml down; exit $$status

check: lint typecheck
	@echo "Static checks passed."

all: lint typecheck test integration coverage
	@echo ""
	@echo "All checks passed. Ready to merge."

clean:
	rm -rf htmlcov .coverage .pytest_cache

up:
	docker compose up -d --build

down:
	docker compose down

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
