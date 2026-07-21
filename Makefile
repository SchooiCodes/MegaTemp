.PHONY: run test lint lint-fix format check format-check clean docker-build docker-run release

# Default Python interpreter
PYTHON ?= python3

run:
	$(PYTHON) main.py

test:
	$(PYTHON) -m pytest --tb=short -k "not test_main_verbose_flag" -v

lint:
	ruff check .

lint-fix:
	ruff check --fix .

format:
	ruff format .

check: lint format-check test

format-check:
	ruff format --check .

clean:
	rm -rf credentials/ tmp/ loop_state.json dist/ build/ *.spec
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

docker-build:
	docker build -t megatem .

docker-run:
	docker run -it --cap-add=SYS_ADMIN -v ./credentials:/app/credentials megatem

release:
	git tag -f v1.3.0 HEAD && git push origin v1.3.0 --force
