#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

TODAY=$(date +%Y-%m-%d)
echo "[$(date)] Starting hourly refresh for $TODAY"

kedro run --pipeline data_engineering --params "end_date=$TODAY"
kedro run --pipeline data_science
kedro run --pipeline inference

echo "[$(date)] Done"
