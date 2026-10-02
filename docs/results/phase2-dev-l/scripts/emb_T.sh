# Phase 2 (dev-L): softmax T of the Titan embedding router by calibrated CV Brier (accuracy-neutral), as phase 1 / Part A.
. results/phase2l/budget.env
for T in 0.02 0.05 0.1; do
uv run python scripts/analysis/tune_router.py config/experiments_l/e3_embedding_l.yaml --split dev_l --calibrate --calibrator both --concurrency 2 --progress 0 \
 --set 'strategies.embedding.model=amazon.titan-embed-text-v2:0' --set strategies.embedding.similarity=centroid --set strategies.embedding.top_k=3 \
 --set strategies.embedding.history_turns=1 --set strategies.embedding.shots=true --set strategies.embedding.query_instruction=null \
 --set strategies.embedding.softmax_temperature=$T --summary results/phase2l/emb_titan_T$T.json > results/phase2l/emb_titan_T$T.log 2>&1
done
