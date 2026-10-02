#!/usr/bin/env bash
# Final study runs come from the pre-registered run manifest (F11), not from this script:
# priority order, version guard (prompt track, frozen config/prompt hashes), measured-cost
# budget check, resume by (case, rep) (a paid partial is never deleted), completion at <= 2%
# errors with at most 2 infra retries (else flagged). See src/routing_study/eval/manifest.py.
#
# Usage: scripts/run_study.sh [MANIFEST] [study run-manifest options, e.g. --dry-run --only NAME]
set -euo pipefail
cd "$(dirname "$0")/.."

MANIFEST="${1:-config/study_manifest.yaml}"
[[ $# -gt 0 ]] && shift
make health
exec uv run study run-manifest "$MANIFEST" "$@"
