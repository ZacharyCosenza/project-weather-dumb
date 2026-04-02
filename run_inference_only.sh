#!/bin/bash
set -euo pipefail
cd /app
TODAY=$(date +%Y-%m-%d)
echo "[$(date)] Hourly inference for $TODAY"
kedro run --pipeline data_engineering --params "end_date=$TODAY"
kedro run --pipeline inference
echo "[$(date)] Hourly inference done"
