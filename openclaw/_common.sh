#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
OPENCLAW_ENV="$HOME/.openclaw/.env"

# Some deployments vendor the skill into a different directory layout (e.g. OpenClaw skills/).
# Detect where the python scripts live.
SCRIPTS_DIR=""
if [[ -d "$REPO_DIR/hansung-info/scripts" ]]; then
  SCRIPTS_DIR="$REPO_DIR/hansung-info/scripts"
elif [[ -d "$REPO_DIR/scripts" ]]; then
  SCRIPTS_DIR="$REPO_DIR/scripts"
else
  echo "Could not find scripts directory (expected hansung-info/scripts or scripts)" >&2
  exit 4
fi

load_env() {
  if [[ -f "$OPENCLAW_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$OPENCLAW_ENV"
    set +a
  fi

  if [[ -z "${HANSUNG_INFO_ID:-}" || -z "${HANSUNG_INFO_PASSWORD:-}" ]]; then
    echo "Missing env vars: HANSUNG_INFO_ID / HANSUNG_INFO_PASSWORD" >&2
    echo "Tip: put them in $OPENCLAW_ENV" >&2
    exit 2
  fi
}

activate_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    echo "Venv not found at $VENV_DIR" >&2
    echo "Run: bash openclaw/setup.sh" >&2
    exit 3
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
}
