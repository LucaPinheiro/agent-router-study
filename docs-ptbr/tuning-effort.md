# Esforço de tuning por estratégia (somente dev)

Todo número aqui vem de `data/dataset_dev.jsonl` (151 casos), CV 5-fold estratificado por
categoria, seed 0 (`scripts/analysis/tune_router.py`, `scripts/analysis/fit_hybrid.py`). Os
splits de teste nunca foram lidos. "Aninhado" = por fold, o ponto do grid que é o melhor nos outros 4
folds é pontuado no fold retido: uma estimativa do procedimento de tuning. "Fixo" = a
config commitada pontuada fold a fold; ela foi escolhida com os mesmos dados, então é otimista.
Os mapas de calibração são ajustados nos folds de treino e pontuados no fold retido. Com
`--calibrator both`, isotônico vs Platt é escolhido por nível pelo Brier score retido agregado.

Um "dev pass" pontua cada caso dev nos dois estágios uma vez. Roteadores locais não fazem chamada paga;
os embeddings de query são locais (Ollama) e ficam em cache por texto de query, então um grid só re-embeda quando
o texto da query muda (instrução ou histórico).

## Registro de esforço

| estratégia | configs avaliadas | dev passes | notas |
|---|---|---|---|
| regex | grid de histórico de 2 pontos (apex-free) | ~2 + edições de regras | As regras foram escritas à mão enquanto se liam os erros do dev. O CV cobre só as settings de histórico, então 84.8 de joint é otimista; ver `.omc/handoffs/apex-free.md`. |
| bm25 (D2) | 1 baseline + 512 (grid 1) + 432 (grid 2) + 1 final = 946 | 946 | Grid 1: index {option, utterance} × aggregate {max, top-k-sum} × k {2,3} × analyzer {word, char} × accent folding × shots × quotes × {Okapi, BM25L} × k1 {0.9, 1.5}. O grid 2 refina em torno do melhor do grid 1: ngram range, k, k1, b, histórico, folding. Sem expansão por LLM (sem orçamento); só expansão determinística a partir do catálogo. |
| embedding (D1) | 1 baseline + 324 (grid) + 4 (temperatura/calibrador) + 1 final = 330; + 2 × 4 para os embedders alternativos | 338 (9 textos de query distintos × 302 embeds) | Grid: similarity {max_example, centroid, topk_vote} × top_k {3,5} × T {0.02, 0.05, 0.1} × instruction {none, generic, task} × history {0,1,2} × shots. T não muda a acurácia; foi escolhido pelo Brier de CV calibrado. |
| hybrid (D3) | 1 baseline RRF (membros antigos) + 1 RRF (membros ajustados) + 77 convexas (7 conjuntos de membros × 11 alphas) + 33 convexas sem regex + 2 fits do stacker (3 valores de L2, CV interno) + 1 final | ~120 | O stacker é ajustado por fold externo nos folds de treino e pontuado pelo pipeline real no fold retido. |
| classifier (D4) | 1 default + 144 TF-IDF (features × C × shots × quotes × description × history) + 64 probe (C × shots × description × instruction × history) + 8 refinamento do probe (C {0.1..3} × history) + 1 final = 218 | 218 | Treinado por conjunto de opções apenas com as utterances do catálogo. |

## Antes → depois (dev, CV 5-fold)

skill/tool/joint são médias sobre os folds para a config fixa. As colunas de ECE e Brier se leem
bruto → calibrado, usando o calibrador escolhido pelo CV. p50 é ms por caso (estágio de skill + tool).
Inferência local em Apple silicon: compare essas latências só entre si, não com
APIs hospedadas.

| roteador | config | skill | tool | joint (fixo) | joint (aninhado) | skill ECE / Brier | tool ECE / Brier | p50 ms |
|---|---|---|---|---|---|---|---|---|
| bm25 | antes (HEAD b80bf72, catálogo atual) | 54.3 | 40.4 | 40.4 ± 8.1 | 40.4 | 0.161→0.104 / 0.212→0.201 | 0.258→0.055 / 0.303→0.238 | 0.1 |
| bm25 | depois | 72.2 | 56.3 | 55.7 ± 7.9 | **46.4** (grid 1) / 51.0 (grid 2) | 0.466→0.071 / 0.384→0.170 | 0.289→0.065 / 0.319→0.235 | 1.9 |
| embedding | antes (qwen3-embedding 8B, max_example, T 0.05) | 74.2 | 67.5 | 66.2 ± 6.0 | 66.2 | 0.104→0.037 / 0.183→0.178 | 0.098→0.072 / 0.213→0.209 | 370 |
| embedding | depois | 88.1 | 82.1 | 78.8 ± 6.8 | **77.5** | 0.063→0.040 / 0.099→0.100 | 0.121→0.083 / 0.153→0.141 | 371 |
| embedding | ablação: qwen3-embedding:0.6b | 76.8 | 64.3 | 62.9 ± 2.3 | 62.9 | 0.097→0.035 / 0.172→0.169 | 0.234→0.053 / 0.257→0.207 | 103 |
| embedding | ablação: bge-m3 | 82.2 | 68.9 | 67.6 ± 3.7 | 67.6 | 0.078→0.049 / 0.137→0.135 | 0.115→0.074 / 0.182→0.182 | 159 |
| hybrid | antes (RRF, BM25 + embedding, membros antigos) | 62.3 | 51.0 | 51.0 ± 12.3 | 51.0 | 0.143→0.057 / 0.196→0.178 | 0.106→0.108 / 0.206→0.207 | 370 |
| hybrid | baseline RRF, membros ajustados | 77.5 | 62.3 | 61.6 ± 6.5 | 61.6 | 0.130→0.076 / 0.167→0.155 | 0.247→0.075 / 0.271→0.199 | 371 |
| hybrid | stacker logístico (regex, bm25, embedding) | – | – | – | 80.1 ± 6.0 | ECE 0.061 / Brier 0.090 (retido) | ECE 0.130 / Brier 0.146 | ~371 |
| hybrid | convexa sem regex (melhor dos conjuntos bm25 / embedding / classifier) | – | – | – | 77.5 | – | – | ~371 |
| hybrid | depois: convexa, regex + classifier, alpha 0.5 | 93.4 | 86.8 | 85.5 ± 6.4 | **83.5** | 0.135→0.012 / 0.091→0.059 | 0.147→0.061 / 0.124→0.098 | 373 |
| classifier | TF-IDF word+char + LR (default) | 64.9 | 46.4 | 41.1 ± 8.2 | 39.1 (grid de 144 pontos) | 0.192→0.057 / 0.240→0.171 | 0.188→0.132 / 0.288→0.241 | 0.9 |
| classifier | depois: linear probe sobre vetores qwen3 | 86.8 | 78.2 | 77.5 ± 6.1 | **76.2** (64 pontos) / 76.8 (refinamento) | 0.290→0.037 / 0.186→0.102 | 0.391→0.085 / 0.313→0.163 | 373 |

`study run -c <cfg> --split dev --mode routing-only --concurrency 1` com as
configs commitadas reproduz os números fixos (ver `.omc/handoffs/phase2-routers.md`).

## O que moveu os números

- **Embedding**
  - Similaridade por centroide: +4 a +12 de joint sobre max_example (melhor ponto por instrução).
  - Instrução de tarefa: instrução genérica ou nenhuma custa de 4 a 10 pontos.
  - Query = últimos 2 turnos + mensagem: +4.6 de joint no modelo 8B (+2 a +3 nos
    embedders alternativos). Com todas as mudanças do D1 juntas, a acurácia de skill em multiturno vai de 33 para 87.
  - Shots do catálogo (os exemplos das tools de uma skill como utterances da skill): cerca de +1.
  - O voto top-k (kNN) fica 4 pontos abaixo do centroide.
  - O T do softmax muda só a confiança, que a calibração então remapeia.
  - O embedder 8B supera o bge-m3 em 10 pontos e o qwen3-0.6b em 15, com cerca de 2.3× e 3.6×
    a latência deles.
- **BM25**
  - As duas grandes alavancas são o índice no nível de utterance (com agregação top-k-sum) e os
    3-5-gramas de caracteres (grid 1 aninhado: +6 no geral).
  - A expansão por shots é selecionada em todas as configurações do topo.
  - Com um corpus de utterances, o IDF Okapi deixa de ser degenerado: Okapi ≥ BM25L.
  - O BM25 continua sendo o roteador mais fraco. Seu estágio de tool só atinge alta precisão com cobertura
    muito baixa.
- **Hybrid**
  - O RRF continua sendo uma regra quase fixa e é pior que o embedding sozinho.
  - A fusão convexa de distribuições calibradas sem regex, no máximo, empata com o roteador de
    embedding: o BM25 não acrescenta nada.
  - Todo o ganho da fusão (+6 aninhado) vem do membro regex. Suas regras foram escritas
    enquanto se liam os erros do dev, então esse ganho precisa ser confirmado no teste.
  - O stacker logístico (80.1) fica abaixo da fusão convexa, mais simples (83.5), e sua escolha de L2 é
    instável entre os folds.
- **Deferral aprendido** (`hybrid.deferral_features` / `fit_deferral`, um modelo logístico
  no estilo FrugalGPT sobre as confianças, margens e concordância dos membros). No estágio de skill, ele
  prevê se o regex está correto com AUROC de CV 0.737, contra 0.754 da própria confiança
  calibrada do regex: nenhum ganho com este n (135 decisões). Mantenha o gate de confiança única
  e trate o scorer aprendido como uma hipótese a checar no shadow pass.
- **Classifier**
  - TF-IDF + LR sobre cerca de 5–20 utterances do catálogo por classe é fraco (39 aninhado): o baseline léxico de
    "regras aprendidas" não supera o regex escrito à mão.
  - Um linear probe sobre os vetores qwen3 congelados (query com instrução, utterances sem)
    empata com o roteador de embedding ajustado (76–77 aninhado). É a linha de classifier aberta e sem fornecedor
    a contrapor ao Jev.
