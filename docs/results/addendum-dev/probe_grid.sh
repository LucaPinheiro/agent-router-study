# Part A: the phase-1 D4 probe grid (results/phase2/clf_probe_grid.json: 64 points, fixed probe,
# quotes=false, history_weight=0.3), verbatim axes. Dev only. Usage: sh probe_grid.sh cohere|titan
v=$1
uv run python scripts/analysis/tune_router.py config/experiments/e10_classifier_$v.yaml --calibrate --calibrator both --concurrency 2 --top 15 \
 --grid strategies.classifier.c=1,10,100,1000 --grid strategies.classifier.shots=false,true \
 --grid strategies.classifier.description=false,true --grid strategies.classifier.probe_instruction=false,true \
 --grid strategies.classifier.history_turns=0,2 \
 --summary results/phase2a/probe_${v}_grid.json
