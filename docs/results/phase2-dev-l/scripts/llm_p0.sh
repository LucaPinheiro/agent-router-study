# Phase 2 (dev-L): LLM routers at P0 only (no prompt search), 1 rep, isotonic maps by 5-fold CV
# (the phase-1 / Part-A LLM procedure). Usage: sh llm_p0.sh <config stem> <concurrency>
. results/phase2l/budget.env
uv run python scripts/analysis/tune_router.py config/experiments_l/$1.yaml --split dev_l --calibrate --calibrator isotonic \
 --concurrency $2 --progress 25 --errors --out results/phase2l/$1_dev.json --summary results/phase2l/$1_summary.json
