#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

python3 -V

if ! python3 -c 'import venv' >/dev/null 2>&1; then
  echo "Python venv module not available." >&2
  echo "Ubuntu: sudo apt-get install -y python3-venv" >&2
  exit 10
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt

echo "OK: venv ready. Next: bash openclaw/login_refresh.sh" 
