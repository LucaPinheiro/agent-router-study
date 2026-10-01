# Tuning effort per strategy (dev only)

Every number here comes from `data/dataset_dev.jsonl` (151 cases), 5-fold CV stratified by
category, seed 0 (`scripts/analysis/tune_router.py`, `scripts/analysis/fit_hybrid.py`). The
test splits were never read. "Nested" = per fold, the grid point that is best on the other 4
folds is scored on the held-out fold: an estimate of the tuning procedure. "Fixed" = the
committed config scored fold by fold; it was chosen on the same data, so it is optimistic.
Calibration maps are fitted on train folds and scored on the held-out fold. With
`--calibrator both`, isotonic vs Platt is chosen per level by the pooled held-out Brier score.

A "dev pass" scores every dev case at both stages once. Local routers make no paid call;
query embeddings are local (Ollama) and cached per query text, so a grid only re-embeds when
the query text changes (instruction or history).

## Effort ledger

| strategy | configs evaluated | dev passes | notes |
|---|---|---|---|
| regex | 2-point history grid (apex-free) | ~2 + rule edits | Rules were hand-written while reading dev errors. The CV covers only history settings, so 84.8 joint is optimistic; see `.omc/handoffs/apex-free.md`. |
| bm25 (D2) | 1 baseline + 512 (grid 1) + 432 (grid 2) + 1 final = 946 | 946 | Grid 1: index {option, utterance} × aggregate {max, top-k-sum} × k {2,3} × analyzer {word, char} × accent folding × shots × quotes × {Okapi, BM25L} × k1 {0.9, 1.5}. Grid 2 refines around grid 1's best: ngram range, k, k1, b, history, folding. No LLM expansion (no budget); only deterministic catalog expansion. |
| embedding (D1) | 1 baseline + 324 (grid) + 4 (temperature/calibrator) + 1 final = 330; + 2 × 4 for the alternative embedders | 338 (9 distinct query texts × 302 embeds) | Grid: similarity {max_example, centroid, topk_vote} × top_k {3,5} × T {0.02, 0.05, 0.1} × instruction {none, generic, task} × history {0,1,2} × shots. T does not change accuracy; it was picked by calibrated CV Brier. |
| hybrid (D3) | 1 baseline RRF (old members) + 1 RRF (tuned members) + 77 convex (7 member sets × 11 alphas) + 33 convex without regex + 2 stacker fits (3 L2 values, inner CV) + 1 final | ~120 | The stacker is fitted per outer fold on train folds and scored through the real pipeline on the held-out fold. |
| classifier (D4) | 1 default + 144 TF-IDF (features × C × shots × quotes × description × history) + 64 probe (C × shots × description × instruction × history) + 8 probe refinement (C {0.1..3} × history) + 1 final = 218 | 218 | Trained per option set on catalog utterances only. |

## Before → after (dev, 5-fold CV)

skill/tool/joint are means over the folds for the fixed config. The ECE and Brier columns read
raw → calibrated, using the calibrator chosen by CV. p50 is ms per case (skill + tool stage).
Local inference on Apple silicon: compare these latencies with each other only, not with
hosted APIs.

| router | config | skill | tool | joint (fixed) | joint (nested) | skill ECE / Brier | tool ECE / Brier | p50 ms |
|---|---|---|---|---|---|---|---|---|
| bm25 | before (HEAD b80bf72, current catalog) | 54.3 | 40.4 | 40.4 ± 8.1 | 40.4 | 0.161→0.104 / 0.212→0.201 | 0.258→0.055 / 0.303→0.238 | 0.1 |
| bm25 | after | 72.2 | 56.3 | 55.7 ± 7.9 | **46.4** (grid 1) / 51.0 (grid 2) | 0.466→0.071 / 0.384→0.170 | 0.289→0.065 / 0.319→0.235 | 1.9 |
| embedding | before (qwen3-embedding 8B, max_example, T 0.05) | 74.2 | 67.5 | 66.2 ± 6.0 | 66.2 | 0.104→0.037 / 0.183→0.178 | 0.098→0.072 / 0.213→0.209 | 370 |
| embedding | after | 88.1 | 82.1 | 78.8 ± 6.8 | **77.5** | 0.063→0.040 / 0.099→0.100 | 0.121→0.083 / 0.153→0.141 | 371 |
| embedding | ablation: qwen3-embedding:0.6b | 76.8 | 64.3 | 62.9 ± 2.3 | 62.9 | 0.097→0.035 / 0.172→0.169 | 0.234→0.053 / 0.257→0.207 | 103 |
| embedding | ablation: bge-m3 | 82.2 | 68.9 | 67.6 ± 3.7 | 67.6 | 0.078→0.049 / 0.137→0.135 | 0.115→0.074 / 0.182→0.182 | 159 |
| hybrid | before (RRF, BM25 + embedding, old members) | 62.3 | 51.0 | 51.0 ± 12.3 | 51.0 | 0.143→0.057 / 0.196→0.178 | 0.106→0.108 / 0.206→0.207 | 370 |
| hybrid | RRF baseline, tuned members | 77.5 | 62.3 | 61.6 ± 6.5 | 61.6 | 0.130→0.076 / 0.167→0.155 | 0.247→0.075 / 0.271→0.199 | 371 |
| hybrid | logistic stacker (regex, bm25, embedding) | – | – | – | 80.1 ± 6.0 | ECE 0.061 / Brier 0.090 (held-out) | ECE 0.130 / Brier 0.146 | ~371 |
| hybrid | convex without regex (best of bm25 / embedding / classifier sets) | – | – | – | 77.5 | – | – | ~371 |
| hybrid | after: convex, regex + classifier, alpha 0.5 | 93.4 | 86.8 | 85.5 ± 6.4 | **83.5** | 0.135→0.012 / 0.091→0.059 | 0.147→0.061 / 0.124→0.098 | 373 |
| classifier | TF-IDF word+char + LR (default) | 64.9 | 46.4 | 41.1 ± 8.2 | 39.1 (144-point grid) | 0.192→0.057 / 0.240→0.171 | 0.188→0.132 / 0.288→0.241 | 0.9 |
| classifier | after: linear probe on qwen3 vectors | 86.8 | 78.2 | 77.5 ± 6.1 | **76.2** (64-point) / 76.8 (refinement) | 0.290→0.037 / 0.186→0.102 | 0.391→0.085 / 0.313→0.163 | 373 |

`study run -c <cfg> --split dev --mode routing-only --concurrency 1` with the committed
configs reproduces the fixed numbers (see `.omc/handoffs/phase2-routers.md`).

## What moved the numbers

- **Embedding**
  - Centroid similarity: +4 to +12 joint over max_example (best point per instruction).
  - Task instruction: generic or no instruction costs 4 to 10 points.
  - Query = last 2 turns + message: +4.6 joint on the 8B model (+2 to +3 on the
    alternative embedders). With all D1 changes together, multiturno skill accuracy goes from 33 to 87.
  - Catalog shots (a skill's tool examples as skill utterances): about +1.
  - top-k vote (kNN) is 4 points below centroid.
  - Softmax T changes only the confidence, which calibration then re-maps.
  - The 8B embedder beats bge-m3 by 10 points and qwen3-0.6b by 15, at about 2.3× and 3.6×
    their latency.
- **BM25**
  - The two big levers are the utterance-level index (with top-k-sum aggregation) and char
    3-5-grams (grid 1 nested: +6 overall).
  - The shots expansion is selected in every top configuration.
  - With an utterance corpus, Okapi IDF is no longer degenerate: Okapi ≥ BM25L.
  - BM25 is still the weakest router. Its tool stage reaches high precision only at very low
    coverage.
- **Hybrid**
  - RRF stays a near-fixed rule and is worse than embedding alone.
  - Convex fusion of calibrated distributions without regex at best equals the embedding
    router: BM25 adds nothing.
  - The whole fusion gain (+6 nested) comes from the regex member. Its rules were written
    while reading dev errors, so this gain must be confirmed on test.
  - The logistic stacker (80.1) is below the simpler convex fusion (83.5), and its L2 pick is
    unstable across folds.
- **Learned deferral** (`hybrid.deferral_features` / `fit_deferral`, a FrugalGPT-style
  logistic model over member confidences, margins and agreement). On the skill stage it
  predicts whether regex is correct with CV AUROC 0.737, against 0.754 for regex's own
  calibrated confidence: no gain at this n (135 decisions). Keep the single-confidence gate
  and treat the learned scorer as a hypothesis to check on the shadow pass.
- **Classifier**
  - TF-IDF + LR on about 5–20 catalog utterances per class is weak (39 nested): the lexical
    "learned rules" baseline does not beat hand-written regex.
  - A linear probe on the frozen qwen3 vectors (query with instruction, utterances without)
    matches the tuned embedding router (76–77 nested). It is the open, vendor-free classifier
    row to set against Jev.
