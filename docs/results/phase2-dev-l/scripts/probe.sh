# Phase 2 (dev-L): the phase-1 D4 probe grid (64 pts) and refinement (8 pts: C x history around the
# 64-grid best), verbatim axes, on Titan v2 vectors; the query goes through the tuned dev-L Titan block.
# Usage: sh probe.sh grid | sh probe.sh refine <probe_instruction> <shots> <description> <c-list>
. results/phase2l/budget.env
EMB="--set strategies.embedding.model=amazon.titan-embed-text-v2:0 --set strategies.embedding.similarity=centroid --set strategies.embedding.top_k=3 --set strategies.embedding.softmax_temperature=0.02 --set strategies.embedding.history_turns=1 --set strategies.embedding.shots=true --set strategies.embedding.query_instruction=null"
if [ "$1" = grid ]; then
uv run python scripts/analysis/tune_router.py config/experiments_l/e10_classifier_l.yaml --split dev_l --calibrate --calibrator both --concurrency 2 --top 15 --progress 0 $EMB \
 --set strategies.classifier.model=probe --set strategies.classifier.quotes=false --set strategies.classifier.history_weight=0.3 \
 --grid strategies.classifier.c=1,10,100,1000 --grid strategies.classifier.shots=false,true \
 --grid strategies.classifier.description=false,true --grid strategies.classifier.probe_instruction=false,true \
 --grid strategies.classifier.history_turns=0,2 \
 --summary results/phase2l/probe_titan_grid.json
else
uv run python scripts/analysis/tune_router.py config/experiments_l/e10_classifier_l.yaml --split dev_l --calibrate --calibrator both --concurrency 2 --top 15 --progress 0 $EMB \
 --set strategies.classifier.model=probe --set strategies.classifier.quotes=false --set strategies.classifier.history_weight=0.3 \
 --set strategies.classifier.probe_instruction=$2 --set strategies.classifier.shots=$3 --set strategies.classifier.description=$4 \
 --grid strategies.classifier.c=$5 --grid strategies.classifier.history_turns=0,2 \
 --summary results/phase2l/probe_titan_refine.json
fi
