.PHONY: test lint typecheck fmt check

test:
	pytest

lint:
	ruff check chatcore tests

typecheck:
	mypy chatcore

fmt:
	ruff check --fix chatcore tests

check: lint typecheck test
