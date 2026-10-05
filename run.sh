#!/usr/bin/env bash
# Start Arqade (after ./setup.sh). Extra args go to `python -m arqade`, e.g. ./run.sh --port 9000
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./setup.sh first." >&2; exit 1; }
exec .venv/bin/python -m arqade "$@"
