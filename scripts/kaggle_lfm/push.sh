#!/usr/bin/env bash
# Usage: scripts/kaggle_lfm/push.sh <bundle dir from build_bundle.py> [shards=2]
# Needs KAGGLE_API_TOKEN (or ~/.kaggle credentials). Creates/updates a PRIVATE dataset and starts one notebook per shard.
set -euo pipefail
BUNDLE="${1:?bundle dir}"; SHARDS="${2:-2}"
OWNER="${KAGGLE_OWNER:-almobinnahid}"; SLUG="mgeoai-lfm-bundle"
HERE="$(cd "$(dirname "$0")" && pwd)"
printf '{"title": "MGeoAI LFM bundle", "id": "%s/%s", "licenses": [{"name": "other"}]}\n' "$OWNER" "$SLUG" > "$BUNDLE/dataset-metadata.json"
if kaggle datasets status "$OWNER/$SLUG" >/dev/null 2>&1; then
  kaggle datasets version -p "$BUNDLE" -m "refresh" -r zip
else
  kaggle datasets create -p "$BUNDLE" -r zip
fi
for ((i = 0; i < SHARDS; i++)); do
  K="$BUNDLE/kernel$i"; rm -rf "$K"; mkdir -p "$K"
  sed -e "s/@@SHARDS@@/$SHARDS/" -e "s/@@SHARD@@/$i/" -e "s#@@DATASET@@#$SLUG#" "$HERE/kernel.py" > "$K/kernel.py"
  cat > "$K/kernel-metadata.json" <<J
{"id": "$OWNER/mgeoai-lfm-s$i", "title": "mgeoai-lfm-s$i", "code_file": "kernel.py", "language": "python",
 "kernel_type": "script", "is_private": true, "enable_gpu": true, "enable_tpu": false, "enable_internet": true,
 "dataset_sources": ["$OWNER/$SLUG"], "kernel_sources": [], "competition_sources": [], "model_sources": [],
 "machine_shape": "NvidiaTeslaT4"}
J
  kaggle kernels push -p "$K"
done
