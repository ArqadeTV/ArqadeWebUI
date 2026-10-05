#!/usr/bin/env bash
# Arqade one-line installer (macOS / Linux).
#   curl -fsSL https://__OWNER__.github.io/__REPO_NAME__/install.sh | bash
# Pass setup options after `-s --`:
#   curl -fsSL https://__OWNER__.github.io/__REPO_NAME__/install.sh | bash -s -- --full
# Env: ARQADE_DIR (default ~/ArqadeWebUI), ARQADE_BRANCH (default main)
set -euo pipefail

REPO="__REPO__"
DIR="${ARQADE_DIR:-$HOME/ArqadeWebUI}"
BRANCH="${ARQADE_BRANCH:-main}"

say()  { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$REPO" == */* && "$REPO" != __* ]] || fail "This copy of install.sh hasn't been published through GitHub Pages yet (placeholder repo)."

if [ -d "$DIR/.git" ] && command -v git >/dev/null 2>&1; then
  say "Updating existing install in $DIR"
  git -C "$DIR" pull --ff-only || say "Couldn't fast-forward; continuing with what's there."
elif [ -f "$DIR/setup.sh" ]; then
  say "Found an existing install in $DIR"
elif command -v git >/dev/null 2>&1; then
  say "Cloning https://github.com/$REPO into $DIR"
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO.git" "$DIR"
else
  command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 || fail "Need git, or curl + tar."
  say "Downloading https://github.com/$REPO ($BRANCH)"
  mkdir -p "$DIR"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz --strip-components=1 -C "$DIR"
fi

cd "$DIR"
exec bash setup.sh "$@" </dev/null
