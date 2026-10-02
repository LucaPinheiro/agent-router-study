# Phase 2 (dev-L): the phase-1 D3 convex-fusion grid (results/phase2/hyb_convex.json: 7 member sets x
# 11 alphas), verbatim axes, members with their dev-L tuned blocks and maps (Titan embedder).
. results/phase2l/budget.env
uv run python scripts/analysis/tune_router.py config/experiments_l/e11_hybrid_l.yaml --split dev_l --calibrate --calibrator both --concurrency 2 --top 15 --progress 0 \
 --set strategies.hybrid.fusion=convex \
 --grid-list "strategies.hybrid.members=[[regex, classifier], [regex, embedding], [regex, embedding, classifier], [regex, bm25, embedding], [regex, bm25, embedding, classifier], [embedding, classifier], [bm25, embedding]]" \
 --grid strategies.hybrid.alpha=0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1 \
 --summary results/phase2l/hyb_convex.json
