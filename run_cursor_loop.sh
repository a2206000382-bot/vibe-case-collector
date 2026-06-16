#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

if command -v python >/dev/null 2>&1; then
  python vibe_case_collector.py --loop
else
  python3 vibe_case_collector.py --loop
fi
