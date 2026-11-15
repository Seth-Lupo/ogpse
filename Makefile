.PHONY: all feasibility run validate summary test

all: feasibility run validate summary

feasibility:
	uv run ogpse feasibility

run:
	uv run ogpse run

validate:
	uv run ogpse validate

test:
	uv run pytest -q

summary:
	uv run ogpse summary
