#!/usr/bin/env bash
# Recreate every report from the public dataset. No API key and no article text needed.
# Usage: scripts/reproduce_reports.sh [hf-dataset-slug-or-local-folder] [output-dir]
set -euo pipefail
DATASET="${1:-hamimmahmud0/mgeoai-road-accident-news}"
OUTPUT="${2:-reproduced}"
mgeoai x reproduce --dataset "$DATASET" --output "$OUTPUT"
echo "Open $OUTPUT/grouping_report.html and $OUTPUT/model_vs_annotators.html"
