# Part A (phase-2 addendum): the phase-1 D1 324-point grid (results/phase2/emb_grid1.sh), verbatim
# axes, on the Bedrock embedders. Dev only. Usage: sh results/phase2a/emb_grid.sh cohere|titan
v=$1
uv run python scripts/analysis/tune_router.py config/experiments/e3_embedding_$v.yaml --calibrate --calibrator both --concurrency 2 --top 15 \
 --grid strategies.embedding.similarity=max_example,centroid,topk_vote --grid strategies.embedding.top_k=3,5 \
 --grid strategies.embedding.softmax_temperature=0.02,0.05,0.1 \
 --grid-list 'strategies.embedding.query_instruction=[null, "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:", "Instruct: Given a customer-service message in Brazilian Portuguese, retrieve the support option that handles it\nQuery:"]' \
 --grid strategies.embedding.history_turns=0,1,2 --grid strategies.embedding.shots=false,true \
 --summary results/phase2a/emb_${v}_grid.json
