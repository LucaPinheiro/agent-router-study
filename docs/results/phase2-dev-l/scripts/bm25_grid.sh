# Phase 2 (dev-L): the phase-1 D2 BM25 grids (results/phase2/bm25_grid1.json 512 pts, bm25_grid2.json
# 432 pts around grid-1's best), verbatim axes, on the large catalog. Usage: sh bm25_grid.sh 1|2 [fixed...]
if [ "$1" = 1 ]; then
uv run python scripts/analysis/tune_router.py config/experiments_l/e2_bm25_l.yaml --split dev_l --calibrate --calibrator both --concurrency 8 --top 15 --progress 0 \
 --grid strategies.bm25.index=utterance,option --grid strategies.bm25.aggregate=topk_sum,max --grid strategies.bm25.agg_k=2,3 \
 --grid strategies.bm25.analyzer=char,word --grid strategies.bm25.fold_accents=false,true --grid strategies.bm25.shots=true,false \
 --grid strategies.bm25.quotes=true,false --grid strategies.bm25.variant=okapi,l --grid strategies.bm25.k1=0.9,1.5 \
 --summary results/phase2l/bm25_grid1.json
else
shift
uv run python scripts/analysis/tune_router.py config/experiments_l/e2_bm25_l.yaml --split dev_l --calibrate --calibrator both --concurrency 8 --top 15 --progress 0 \
 --set strategies.bm25.index=utterance --set strategies.bm25.aggregate=topk_sum "$@" \
 --grid strategies.bm25.ngram_min=3,2 --grid strategies.bm25.ngram_max=5,6,4 --grid strategies.bm25.agg_k=4,2,3 \
 --grid strategies.bm25.k1=0.6,0.9,1.2 --grid strategies.bm25.b=0.5,0.75 --grid strategies.bm25.history_turns=2,0 \
 --grid strategies.bm25.fold_accents=false,true \
 --summary results/phase2l/bm25_grid2.json
fi
