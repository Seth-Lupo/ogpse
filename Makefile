.PHONY: all feasibility run validate test

all: feasibility run validate

feasibility:
	uv run ogpse feasibility

run:
	uv run ogpse run

validate:
	uv run ogpse validate

test:
	uv run pytest -q
