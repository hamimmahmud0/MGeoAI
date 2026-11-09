#!/usr/bin/env bash
# Reproduce the same-accident grouping benchmark end to end.
#
#   DEEPSEEK_API_KEY=... scripts/run_grouping_benchmark.sh /path/to/extraction-root [--yes] [more mgeoai options]
#
# Without --yes it only checks the data and prints the token/cost projection.
# The extraction root must contain articles/, labels/ and runs/<deepseek ... __meta>/ (the model
# extraction used as one of the inputs). Results land in <root>/matching/. See docs/GROUPING_BENCHMARK.md.
set -euo pipefail
ROOT="${1:?usage: $0 <extraction-root> [--yes] [options]}"
shift || true
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
if [[ " $* " == *" --yes "* ]] && [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is not set" >&2; exit 2
fi
for need in articles labels; do
  [[ -d "$ROOT/$need" ]] || { echo "missing $ROOT/$need" >&2; exit 2; }
done
if ! ls -d "$ROOT"/runs/deepseek__deepseek-flash__markdown__txt__meta >/dev/null 2>&1; then
  echo "missing $ROOT/runs/deepseek__deepseek-flash__markdown__txt__meta (needed for the 'model fields' inputs)" >&2; exit 2
fi
exec .venv/bin/mgeoai x group-benchmark --root "$ROOT" "$@"
