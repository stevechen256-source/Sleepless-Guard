#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "${1:-}" = '--dry-run' ]; then
  exec /usr/bin/python3 "$ROOT/scripts/manage.py" install --dry-run
fi
[ "$#" -eq 0 ] || { echo 'Usage: ./install.sh [--dry-run]' >&2; exit 1; }
"$ROOT/build.sh"
exec /usr/bin/python3 "$ROOT/scripts/manage.py" install
