#!/usr/bin/env bash
# Arqade setup for macOS / Linux.
#   ./setup.sh             standard install (UI + PyTorch + TensorFlow + Transformers + ONNX + GGUF ...)
#   ./setup.sh --lite      UI only (fast); add libraries later from the Libraries tab
#   ./setup.sh --full      every supported AI library (large; failures are skipped, not fatal)
#   ./setup.sh --no-run    install but don't launch
set -euo pipefail
cd "$(dirname "$0")"

PROFILE=standard
RUN=1
for arg in "$@"; do
  case "$arg" in
    --lite) PROFILE=lite ;;
    --standard) PROFILE=standard ;;
    --full) PROFILE=full ;;
    --no-run) RUN=0 ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# Prefer 3.12/3.11 (best wheel coverage for TensorFlow & friends), accept anything >= 3.9.
PY=""
for cand in python3.12 python3.11 python3.13 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    PY="$cand"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.9+ not found. Install it (https://www.python.org/downloads/ or your package manager) and re-run."
say "Using $($PY --version) ($(command -v "$PY"))"

if [ ! -x .venv/bin/python ]; then
  say "Creating virtual environment (.venv)"
  "$PY" -m venv .venv || fail "venv failed. On Debian/Ubuntu run: sudo apt install python3-venv"
fi
VPY=.venv/bin/python

say "Upgrading pip"
"$VPY" -m pip install --disable-pip-version-check -q --upgrade pip

say "Installing the UI (core)"
"$VPY" -m pip install --disable-pip-version-check -q -r requirements-core.txt

if [ "$PROFILE" != "lite" ]; then
  say "Installing AI libraries (profile: $PROFILE) - this can take a while"
  "$VPY" scripts/install_all.py --profile "$PROFILE" || say "Some optional libraries failed; Arqade still works."
fi

say "Setup complete 🎉"
if [ "$RUN" = 1 ]; then
  exec "$VPY" -m arqade
else
  echo "Start it any time with:  ./run.sh"
fi
