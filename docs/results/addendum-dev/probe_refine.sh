# Part A: the phase-1 D4 probe refinement (results/phase2/clf_probe_grid2.json: 8 points, C around
# the 64-grid best x history), other axes fixed at the 64-grid best point. Dev only.
# Usage: sh probe_refine.sh <v> <probe_instruction> <c-list>
v=$1
uv run python scripts/analysis/tune_router.py config/experiments/e10_classifier_$v.yaml --calibrate --calibrator both --concurrency 2 --top 15 \
 --set strategies.classifier.shots=true --set strategies.classifier.description=true \
 --set strategies.classifier.probe_instruction=$2 \
 --grid strategies.classifier.c=$3 --grid strategies.classifier.history_turns=0,2 \
 --summary results/phase2a/probe_${v}_refine.json
