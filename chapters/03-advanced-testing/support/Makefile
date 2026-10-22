.PHONY: lint typecheck test integration coverage check all clean

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

check: lint typecheck
	@echo "Static checks passed."

all: lint typecheck test integration coverage
	@echo ""
	@echo "All checks passed. Ready to merge."

clean:
	rm -rf htmlcov .coverage .pytest_cache
