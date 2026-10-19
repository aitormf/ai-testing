#!/usr/bin/env bash
# scripts/check.sh: full verification. Must pass before anything is considered done.
# Run by people, by the agent (Stop hook) and by CI: one single definition of "done".
set -euo pipefail

echo "▶ format";        uv run ruff format --check .
echo "▶ lint";          uv run ruff check .
echo "▶ types";         uv run mypy
echo "▶ architecture";  uv run lint-imports
echo "▶ tests";         uv run pytest --cov
echo "✔ all green"
