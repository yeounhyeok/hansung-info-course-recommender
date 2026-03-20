#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

load_env
activate_venv

cd "$REPO_DIR"
python3 "$SCRIPTS_DIR/roadmap_generator.py" "$@"
