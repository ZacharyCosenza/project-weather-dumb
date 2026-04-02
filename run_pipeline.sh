#!/bin/bash
set -euo pipefail
cd /app
TODAY=$(date +%Y-%m-%d)
echo "[$(date)] Nightly pipeline: fetch + retrain + inference for $TODAY"
kedro run --pipeline data_engineering --params "end_date=$TODAY"
kedro run --pipeline data_science
kedro run --pipeline inference
echo "[$(date)] Nightly pipeline done"
