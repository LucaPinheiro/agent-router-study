#!/usr/bin/env bash
# Full study on the held-out test split. Resumable: a run is skipped only when its results
# file is complete (rows == cases x reps); the runner writes <name>.jsonl.partial and renames
# it at the end, so a crash leaves no complete-looking file (review M3). An incomplete file is
# moved aside and the run redone. Usage: scripts/run_study.sh [TAG]   (TAG defaults to today)
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-$(date +%Y%m%d)}"
SPLIT=test
LOG="results/study-${TAG}.log"
mkdir -p results

CASES="$(grep -c . "data/dataset_${SPLIT}.jsonl")"

run() {  # run <name> <args...>   (args must include --reps N)
  local name="$1"; shift
  local reps=1 prev="" a
  for a in "$@"; do [[ "$prev" == "--reps" ]] && reps="$a"; prev="$a"; done
  local file="results/${name}.jsonl" want=$((CASES * reps))
  if [[ -f "$file" ]]; then
    local rows; rows="$(grep -c . "$file" || true)"
    if [[ "$rows" -eq "$want" ]]; then
      echo "skip ${name} (done: ${rows} rows)" | tee -a "$LOG"; return
    fi
    echo "incomplete ${name}: ${rows}/${want} rows, moved aside" | tee -a "$LOG"
    mv "$file" "${file}.incomplete-$(date +%s)"
  fi
  echo "=== $(date -Iseconds) ${name}" | tee -a "$LOG"
  # --overwrite only replaces a leftover .partial of a crashed attempt
  uv run study run --split "$SPLIT" --run-name "$name" --overwrite "$@" 2>&1 | tail -3 \
    | tee -a "$LOG"
}

make health >>"$LOG" 2>&1

# 1) routing-only, 3 reps: one shadow pass records every strategy (E1-E6 decisions);
#    Haiku is its own strategy config; cascades E7-E9 also run for real.
run "${TAG}-shadow-routing-r3" -c config/experiments/e9_regex_jev_llm.yaml \
  --mode routing-only --routing-mode shadow --reps 3
run "${TAG}-e6-routing-r3" -c config/experiments/e6_llm_haiku.yaml --mode routing-only --reps 3
for e in e7_regex_jev e8_regex_llm e9_regex_jev_llm; do
  run "${TAG}-${e}-routing-r3" -c "config/experiments/${e}.yaml" --mode routing-only --reps 3
done

# 2) end-to-end with the executor, 1 rep, every configuration
for f in config/experiments/e*.yaml; do
  e="$(basename "$f" .yaml)"
  run "${TAG}-${e}-e2e-r1" -c "$f" --mode e2e --reps 1
done

echo "=== $(date -Iseconds) done" | tee -a "$LOG"
