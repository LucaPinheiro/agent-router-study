# Phase 2 (dev-L): the phase-1 D1 324-point embedding grid (results/phase2/emb_grid1.sh), verbatim axes,
# on Bedrock Titan v2 (the Part-A choice: ties Cohere within noise, ~4x faster, ~6x cheaper).
uv run python scripts/analysis/tune_router.py config/experiments_l/e3_embedding_l.yaml --split dev_l --calibrate --calibrator both --concurrency 2 --top 15 --progress 0 \
 --set 'strategies.embedding.model=amazon.titan-embed-text-v2:0' \
 --grid strategies.embedding.similarity=max_example,centroid,topk_vote --grid strategies.embedding.top_k=3,5 \
 --grid strategies.embedding.softmax_temperature=0.02,0.05,0.1 \
 --grid-list 'strategies.embedding.query_instruction=[null, "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:", "Instruct: Given a customer-service message in Brazilian Portuguese, retrieve the support option that handles it\nQuery:"]' \
 --grid strategies.embedding.history_turns=0,1,2 --grid strategies.embedding.shots=false,true \
 --summary results/phase2l/emb_titan_grid.json
