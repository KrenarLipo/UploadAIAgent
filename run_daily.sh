#!/usr/bin/env bash
# Daily job: upload every kit not yet online (see auto_upload.py) and log to logs/<date>.log.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs
log="logs/$(date +%F).log"
status=0
.venv/bin/python auto_upload.py "$@" >>"$log" 2>&1 || status=$?
echo "=== exit $status" >>"$log"
exit "$status"
