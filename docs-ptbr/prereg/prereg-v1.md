# Pré-registro prereg-v1: estudo de routing, split confirmatório test-v2

Status: congelado pela tag git anotada `prereg-v1` (local). Escrito antes de qualquer chamada em test-v2:
nenhum router, executor ou scorer viu um caso de test-v2. Fonte:
`.omc/reviews/methodology-final.md` §PRE-REGISTRATION, adaptado para test-v2 (B1 opção A),
`docs/decisions/2026-10-01-calibration-and-prompts.md` (vinculante), `.omc/plans/final-study-master.md`
Fases 4–5.

## 1. Artefatos congelados

| artefato | valor |
|---|---|
| código | o commit com a tag `prereg-v1` (`git rev-parse prereg-v1^{commit}`); a árvore está limpa na tag |
| dados confirmatórios | `data/dataset_test_v2.jsonl`, 349 casos, sha256 `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` (docs/dataset-card.md "Freeze": somente adjudicação automatizada) |
| dados de replicação expostos | `data/dataset_test_v1.jsonl` → `dataset_test.jsonl`, sha256 `994d20623384931f9bf06ab9f3ee7028397118b66a7ff0abd800bffeef543a77` (somente routers gratuitos) |
| dados de dev | `data/dataset_dev.jsonl`, sha256 `112fc7f0791e35cf1e250a40e362698212f029b4209b6ff7f33dc33717a8874a` (todo o tuning, seleção e thresholds) |
| hash de conteúdo do catálogo | `128584617807` (`Catalog.hash`, independente de protocolo; MCP fixado em 2026-07-28) |
| hash do scorer | `e0eef1fb0073` (`eval/scorers.py` + `eval/grounding.py`) |
| hash do prompt da run | `c61ad0a7b7f8` (`run_prompt_hash`: templates do executor + router) |
| manifesto da run | `config/study_manifest.yaml`, sha256 `9e4cdb2626213dbb805ae54b0218b7cedd96d81fff920befc2c2c46282836868`; cada entrada carrega seu `config_hash` / `prompt_hash` congelado, verificado por `study run-manifest` |
| seleção de prompt | `config/prompt_selection.yaml`, sha256 `3648a71d90c0c6583b4ab27ce6a1bc7e856b2f29249ce92551e3eb2d34d980fb` |
| thresholds de cascade | seção 4; gravados em `config/experiments/e7–e9 (+e12)` |
| bootstrap | seed 20260930, 10 000 reamostragens, bootstrap por cluster (caso) |

Auditoria de rótulos: os rótulos de test-v2 são a adjudicação **automatizada** da auditoria cega (duas famílias
de auditores não-Claude, docs/dataset-card.md). A revisão humana dos casos sinalizados (`data/audit/review.html`) é
opcional; se feita, é reportada como um **rescore separado** com seu próprio sha de dataset e nunca
substitui a análise pré-registrada.

Hashes por entrada (de `study run-manifest --dry-run` / `config_hash(load_settings(config,
patches=overrides))`):

| run | config | config_hash | prompt_hash |
|---|---|---|---|
| v2-e1-regex-routing-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e2-bm25-routing-r1 | e2_bm25.yaml | 7bb5a5960490 | c61ad0a7b7f8 |
| v2-e3-embedding-routing-r1 | e3_embedding.yaml | 1899b6f414a5 | c61ad0a7b7f8 |
| v2-e10-classifier-routing-r1 | e10_classifier.yaml | 616af886b783 | c61ad0a7b7f8 |
| v2-e11-hybrid-routing-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| v2-e1-regex-routing-repeat20 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e3-embedding-qwen06b-routing-r1 | e3_embedding_qwen06b.yaml | 98ef77240be7 | c61ad0a7b7f8 |
| v2-e3-embedding-bgem3-routing-r1 | e3_embedding_bgem3.yaml | 3b95fe4e6beb | c61ad0a7b7f8 |
| v2-shadow-tuned-routing-r3 | e9_regex_jev_llm.yaml | cc01e0b06bb2 | c61ad0a7b7f8 |
| v2-e4-jev-canonical-routing-r3 | e4_jev.yaml | acd7ff96155b | c61ad0a7b7f8 |
| v2-e5-sonnet-canonical-routing-r3 | e5_llm_sonnet.yaml | 40c93f91f270 | c61ad0a7b7f8 |
| v2-e7-tuned-routing-r3 | e7_regex_jev.yaml | 4fbfd7133b32 | c61ad0a7b7f8 |
| v2-e9-tuned-routing-r3 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e8-tuned-routing-r3 | e8_regex_llm.yaml | 755265ce73e0 | c61ad0a7b7f8 |
| v2-e6-haiku-canonical-routing-r1 | e6_llm_haiku.yaml | f6c0edce210b | c61ad0a7b7f8 |
| v2-e6-haiku-canonical-rep2-60 | e6_llm_haiku.yaml | f6c0edce210b | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-routing-r1 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-repeat50 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| lat-regex-b1 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b1 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b1 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b1 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b1 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b1 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b1 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b1 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b1 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b1 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b1 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b1 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b2 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b2 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b2 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b2 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b2 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b2 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b2 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b2 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b2 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b2 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b2 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b2 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b3 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b3 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b3 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b3 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b3 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b3 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b3 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b3 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b3 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b3 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b3 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b3 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| lat-regex-b4 | e1_regex.yaml | 91d9efe3e475 | c61ad0a7b7f8 |
| lat-bm25-b4 | e2_bm25.yaml | bdbfceae0945 | c61ad0a7b7f8 |
| lat-embedding-b4 | e3_embedding.yaml | e6caaa01f721 | c61ad0a7b7f8 |
| lat-classifier-b4 | e10_classifier.yaml | eb403445836f | c61ad0a7b7f8 |
| lat-hybrid-b4 | e11_hybrid.yaml | 499d0b3c58a4 | c61ad0a7b7f8 |
| lat-jev-b4 | e4_jev.yaml | 5cf75faa33f3 | c61ad0a7b7f8 |
| lat-sonnet-b4 | e5_llm_sonnet.yaml | 23e7f5214522 | c61ad0a7b7f8 |
| lat-haiku-b4 | e6_llm_haiku.yaml | 5535a7588de0 | c61ad0a7b7f8 |
| lat-e7-b4 | e7_regex_jev.yaml | b474017898cf | c61ad0a7b7f8 |
| lat-e8-b4 | e8_regex_llm.yaml | 0f40f0def5a3 | c61ad0a7b7f8 |
| lat-e9-b4 | e9_regex_jev_llm.yaml | 454cd4d5ae85 | c61ad0a7b7f8 |
| lat-qwen-b4 | e6b_llm_qwen3_local.yaml | 25f836f7b491 | c61ad0a7b7f8 |
| v2-e0-native-e2e-r1 | e0_native.yaml | 93c7c3ea1e02 | c61ad0a7b7f8 |
| v2-e9-tuned-e2e-r1 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e1-regex-e2e-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v2-e5-sonnet-canonical-e2e-r1 | e5_llm_sonnet.yaml | 40c93f91f270 | c61ad0a7b7f8 |
| v2-e7-tuned-e2e-r1 | e7_regex_jev.yaml | 4fbfd7133b32 | c61ad0a7b7f8 |
| v2-e6b-qwen-canonical-e2e-r1 | e6b_llm_qwen3_local.yaml | 903a4a1e56d3 | c61ad0a7b7f8 |
| v2-e0-native-e2e-rep2-60 | e0_native.yaml | 93c7c3ea1e02 | c61ad0a7b7f8 |
| v2-e9-tuned-e2e-rep2-60 | e9_regex_jev_llm.yaml | 8f5f721c9158 | c61ad0a7b7f8 |
| v2-e11-hybrid-e2e-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| rq5-test_v2-regex-base | e1_regex.yaml | 094189076dc4 | c61ad0a7b7f8 |
| rq5-test_v2-regex-zero | e1_regex.yaml | 369d4719b479 | c61ad0a7b7f8 |
| rq5-test_v2-regex-eng | e1_regex.yaml | 8136ba8c282c | c61ad0a7b7f8 |
| rq5-test_v2-regex-full | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| rq5-test_v2-bm25-base | e2_bm25.yaml | c8d6844e3901 | c61ad0a7b7f8 |
| rq5-test_v2-bm25-zero | e2_bm25.yaml | 7db75b6e764a | c61ad0a7b7f8 |
| rq5-test_v2-classifier-base | e10_classifier.yaml | 6194aad1119c | c61ad0a7b7f8 |
| rq5-test_v2-classifier-zero | e10_classifier.yaml | 77e7a5a727b2 | c61ad0a7b7f8 |
| rq5-test_v2-embedding-base | e3_embedding.yaml | 5418975870b9 | c61ad0a7b7f8 |
| rq5-test_v2-embedding-zero | e3_embedding.yaml | 46dc0103343b | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-base | e11_hybrid.yaml | af686213038b | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-zero | e11_hybrid.yaml | c1edc8996a71 | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-eng | e11_hybrid.yaml | 2eb0483c43a8 | c61ad0a7b7f8 |
| rq5-test_v2-hybrid-full | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |
| rq5-test_v2-jev-base | e4_jev.yaml | ea0f9ccdb142 | c61ad0a7b7f8 |
| rq5-test_v2-jev-zero | e4_jev.yaml | 888e3c0ba3c8 | c61ad0a7b7f8 |
| rq5-test_v2-haiku-base | e6_llm_haiku.yaml | 2d76d848e40b | c61ad0a7b7f8 |
| rq5-test_v2-haiku-zero | e6_llm_haiku.yaml | 8dd1d7028c32 | c61ad0a7b7f8 |
| rq5-test_v2-sonnet-base | e5_llm_sonnet.yaml | 9b17371e0cb3 | c61ad0a7b7f8 |
| rq5-test_v2-sonnet-zero | e5_llm_sonnet.yaml | dbd6461926df | c61ad0a7b7f8 |
| x-e4-jev-p6c-routing-r1 | e4_jev.yaml | 7e8c24a4c406 | c61ad0a7b7f8 |
| x-e12-hybrid-tuned-routing-r3 | e12_hybrid_jev_llm.yaml | feff62642c5e | c61ad0a7b7f8 |
| v1-e1-regex-routing-r1 | e1_regex.yaml | 2da827d0effb | c61ad0a7b7f8 |
| v1-e2-bm25-routing-r1 | e2_bm25.yaml | 7bb5a5960490 | c61ad0a7b7f8 |
| v1-e3-embedding-routing-r1 | e3_embedding.yaml | 1899b6f414a5 | c61ad0a7b7f8 |
| v1-e10-classifier-routing-r1 | e10_classifier.yaml | 616af886b783 | c61ad0a7b7f8 |
| v1-e11-hybrid-routing-r1 | e11_hybrid.yaml | 68cc177d37b0 | c61ad0a7b7f8 |

## 2. Routers e tracks

| exp | router | prompt (ambos os tracks) | mapa de calibração aplicado (regra de decisão `ece_cal < ece_raw`) |
|---|---|---|---|
| E5 | Sonnet 5 (Bedrock) | P0 | skill sim (0.111→0.091), tool não (0.036→0.056) |
| E6 | Haiku 4.5 (Bedrock) | P0 | nenhum (skill 0.058→0.063, tool 0.055→0.061) |
| E6b | Qwen3-8B q8_0 (Ollama, thinking desligado) | P0 | skill sim (0.045→0.041), tool sim (0.116→0.032) |
| E4 | Jev (OpenRouter) | P0 | skill sim (0.063→0.024), tool não (0.047→0.058) |

- A regra de um erro padrão (one-SE; CV 5-fold em dev, ITT) escolheu P0 para todos os modelos em ambos os tracks, e P0 como o
  prompt canônico sobre os quatro modelos (P0 80.2, P0+P4 81.2 de joint médio em CV). Portanto **track B
  (tuned) == track A (canônico)** para todo router do tipo LLM: não existe config `*_tuned` nem run
  duplicada. As alternativas por argmax (Sonnet/Haiku/Qwen P0+P4, Jev P0+P5/P6c) são sensibilidade
  apenas em dev (docs/prompt-apex.md); Jev P0+P6c é executado uma vez como variante exploratória de custo.
- Routers gratuitos: E1 regex, E2 BM25, E3 embedding (qwen3-embedding 8B; ablações com 0.6B e bge-m3),
  E10 classifier (linear probe), E11 hybrid (fusão convexa regex + classifier); configs e mapas
  conforme commitados (docs/tuning-effort.md).
- Cascades E7 (regex → Jev), E8 (regex → Sonnet), E9 (regex → Jev → Sonnet; Jev → Sonnet no
  estágio de tool) no track tuned (= P0); E12 (hybrid → Jev → Sonnet) exploratório.
- Cache de respostas: as decisões de Sonnet, Haiku, Qwen e Jev são cacheadas por (caso, rep, prompt
  renderizado). A shadow pass de test-v2 roda primeiro; E4, E5 e E7–E9 reutilizam suas amostras (pareadas por
  construção). As reps continuam sendo amostras independentes (o índice da rep faz parte da chave).

## 3. Unidade de análise e tratamento

- Unidade: o caso. Os scores são calculados como média das reps por caso antes de qualquer teste.
- ITT: um estágio de routing que falha (erro, falha de parse sem etapa que aceite) conta como **errado**, nunca como
  abstenção; a taxa de erro é reportada por run. A interseção sem erros é apenas uma sensibilidade.
- Fora de escopo: `__global__` + `escalate_to_human` conta como abstenção (`scorers.py`).
- Multi-label: qualquer rótulo aceitável conta. Somente o primeiro rótulo (`joint_first_label`) é uma
  sensibilidade; os rótulos de ambiguo são fracos (o auditor A aceitou 23/70), então ambiguo também é reportado
  separadamente.
- Métrica primária de routing: **acurácia joint top-1** (routing-only). Métrica primária e2e:
  **e2e_success** (decomposta em first_call_success / clarification_credited /
  recovered_credited).

## 4. Thresholds de cascade (D5)

Método, declarado antes da dev shadow run (results/freeze/DECISIONS.log, 2026-10-01T12:01:37-03:00):
**(a) máxima acurácia joint sujeita a custo de routing ≤ 0.5 × o custo por caso do Sonnet 5 P0 em dev**
(5.975 US$/1k → orçamento de US$ 0.0029875/caso), sobre o grid 0.50..0.99 com passo 0.01 por etapa não final,
empates → menor custo, depois thresholds mais altos; ajustado em todas as linhas de dev da dev shadow pass com as
configs finais (`freeze-dev-shadow-r1`, ITT), estimativa honesta por cross-fitting 5-fold. Justificativa:
o ponto de operação está atrelado ao co-primário de H1 (razão de custo < 0.5). A regra de precisão (b) é
reportada apenas como sensibilidade (instável por fold com n = 151).

| exp | pipeline de skill (min_confidence) | pipeline de tool | joint dev % | joint held-out CV % [IC 95%] | US$/1k routing CV |
|---|---|---|---|---|---|
| E7 | regex 0.81 → Jev | Jev | 79.5 | 78.8 [72.2, 85.4] | 0.865 |
| E8 | regex 0.88 → Sonnet (fallback: orçamento inviável, (a) sem restrição) | Sonnet | 78.8 | 78.1 [71.5, 84.8] | 5.14 |
| E9 | regex 0.88 → Jev 0.76 → Sonnet | Jev 0.50 → Sonnet | 80.1 | 77.5 [70.9, 84.1] | 1.28 |
| E12 (exploratório) | hybrid 0.83 → Jev 0.77 → Sonnet | Jev 0.50 → Sonnet | 80.1 | 78.1 [71.5, 84.8] | 1.19 |

Referências em dev (todas as linhas, sem ajuste; docs/results/cascade-thresholds-dev.md, fronteira de Pareto em
docs/results/cascade-pareto-dev.csv):

| exp | sempre o último (router final sozinho) | sempre o primeiro | etapa de parada oráculo | deferimento aleatório nas taxas de (a) | regra de precisão (b), CV |
|---|---|---|---|---|---|
| E7 | 76.8 @ 0.94 $/1k | 75.5 @ 0.82 | 80.8 @ 0.57 | 75.9 @ 0.85 | 76.2 @ 0.82 |
| E8 | 76.8 @ 5.92 | 74.2 @ 4.66 | 80.1 @ 3.71 | – | 74.2 @ 4.68 |
| E9 | 76.8 @ 6.86 | 75.5 @ 0.82 | 83.4 @ 0.88 | 76.1 @ 1.11 | 76.2 @ 0.94 |
| E12 | 76.8 @ 6.86 | 77.5 @ 0.79 | 83.4 @ 0.83 | 77.4 @ 0.98 | 77.5 @ 0.91 |

Proveniência da dev shadow: `freeze-dev-shadow-r1` (config/freeze_dev_manifest.yaml), 151/151
linhas, 0 erros, catálogo 128584617807, scorer e0eef1fb0073, código b76b3b1 + rascunhos não commitados apenas do
manifesto e deste documento (nenhuma mudança em src/config). Uma primeira tentativa foi FLAGGED (5 linhas,
3.3%, AWS ExpiredToken) e refeita do zero segundo a regra de operações; os arquivos sinalizados são
mantidos em results/freeze/superseded/. O fallback de E8 foi decidido após uma calibração de prévia
naquela tentativa sinalizada (registrado, docs/prereg/decisions-log.txt); E7/E9/E12 seguem a regra declarada
antes de qualquer linha da shadow.

## 5. Hipóteses

### Primárias (confirmatórias; Holm entre H1–H3; α = 0.05)

- **H1 (RQ3, não inferioridade da cascade).** Joint(E9) − Joint(E5 Sonnet) > −3 pp, onde E5 é a
  run canônica (= tuned, mesmos bytes de prompt). Decisão: o limite inferior do IC 95% bilateral do
  bootstrap pareado por cluster de Δ (unilateral 97.5%) excede −3 pp; p = sign-flip em nível de caso com
  deslocamento 0.03. Co-primário (estimação com IC): razão de US$/1k de routing E9/E5 (regime de cache observado)
  < 0.5.
- **H2 (RQ3, cascade com o gratuito primeiro).** Joint(E7) − Joint(E5) > −3 pp, mesmo teste.
- **H3 ("vale ter roteador?", e2e).** e2e_success(E9) − e2e_success(E0), Δ pareado bilateral com
  IC 95%; afirmação direcional apenas se o IC excluir 0 (MDE esperado ≈ 5–7 pp). Custo por turno
  E9/E0 com IC.

### Secundárias (Holm dentro de cada família)

- **S1 (prompt engineering).** Joint(tuned) − Joint(canonical) ≥ 0 por router LLM. Como a
  regra one-SE pré-declarada escolheu o mesmo prompt para ambos os tracks em todos os routers, Δ ≡ 0 por
  construção e **nenhum teste de S1 é executado em test-v2**; o achado é "o procedimento de seleção
  não encontrou tuning que valesse aplicar" (reportado com as estimativas aninhadas de dev e a sensibilidade
  por argmax). Isso é consequência da regra pré-declarada, não uma hipótese abandonada.
- **S2 (modelo vs modelo, track canônico).** Δ joint pareado para Haiku 4.5, Qwen3-8B e Jev vs
  Sonnet 5; TOST ±3 pp (inclusão do IC 90%); conclusões apenas "equivalente", "não equivalente" ou
  "inconclusivo".
- **S3 (generalização dev → test).** Joint em test-v2 menos joint de CV em dev para regex (dev 84.8,
  regras escritas em dev) e BM25 (dev fixo 55.7). Hipótese: gap do regex < 0. Magnitude com IC
  (IC do test; o número de dev é tratado como fixo).
- **S4 (léxico vs semântico).** Joint(E3 embedding) − Joint(E1 regex), bilateral.

### Somente estimação (ICs, sem testes)

Por estratégia: % de skill, % de tool condicional, recall@1/2/3, taxa de erro, taxa de rep-flip (Haiku 60,
Qwen 50, regex 20); ECE e Brier no test (brutos e calibrados em dev); custo/1k em três regimes
(cache quente observado, preço de tabela sem cache, taxa de acerto de cache modelada vs QPS com TTL de 5 min);
latência p50/p95 **somente do benchmark dedicado** (primeiro caso a frio e a quente reportados
separadamente); cobertura da cascade por etapa; precisão/recall de abstenção; decomposição e2e,
e2e_strict, args_invented, entity_grounded; variância do executor (E0, E9 em 60 casos); por
categoria, por tool, single vs multi-label; E10 classifier, E11 hybrid, E8, ablações de embedder.

### Exploratórias (rotuladas como tal)

Método alternativo de threshold (b) e toda a fronteira de Pareto de dev reexecutada na shadow de test-v2;
E12 (hybrid → Jev → Sonnet); variante de custo Jev P0+P6c; RQ5 leave-tools-out (`docs/rq5-design.md`,
não promovido); replicação de routers gratuitos em test-v1 (split exposto, checagem de contaminação);
ablações de top-k/histórico; análise do modelo servido para Jev; economia de contexto por variante de prompt.

## 6. Plano de execução, ordem e orçamento

Executado apenas por `uv run study run-manifest config/study_manifest.yaml` em ordem de prioridade com
`BUDGET__AWS_USD_CAP=85` (90 − 5 de margem) e `BUDGET__OPENROUTER_USD_CAP` = total de OpenRouter no ledger
no lançamento + 4.0 (saldo − 0.5). Orçamento no freeze: AWS gasto 17.6345 de 90,
OpenRouter 4.4031 de 9.

Totais (102 entradas; tabela por entrada em docs/prereg/estimates.md):

| | limite superior a priori (`study estimate`, sem cache) | esperado ($/caso de dev, compartilhamento de cache, e2e ×1.3) | teto |
|---|---|---|---|
| AWS (Bedrock) | 221.69 | 50.07 | 90 − 17.63 − 5 = **67.37** |
| OpenRouter | 0.00 (Jev não tem preço de tabela) | 1.68 | 9 − 4.40 − 0.5 = **4.10** |

O limite a priori assume ausência de cache e completions máximas (cada run e2e 25–27 US$); ele
não é uma previsão. O guard verifica cada run isoladamente antes de ela começar (custo medido quando
existem linhas da config, senão o limite): no gasto esperado toda run primária é admitida
sob o teto de 85 US$; a entrada e2e de menor prioridade (E11, 84) é a que o guard pode recusar.

## 7. Regras de operação, retry e abort (B6)

- Erros de infra: até 2 retries das linhas com erro, mesma config (`max_infra_retries: 2`).
- Uma run com > 2% de linhas com erro após os retries é FLAGGED: parar, corrigir a infraestrutura, refazer aquela
  run do zero (nunca corrigida parcialmente). Nunca reexecutar por qualquer outro motivo.
- O budget guard (custo medido por turno × turnos faltantes, senão o limite superior a priori) roda
  antes de toda run; uma run recusada é registrada como desvio e reportada como não executada. As runs
  nunca são reordenadas para caber no orçamento.
- Langfuse indisponível → o manifesto para antes de gastar (preflight).
- Runs locais (Qwen, embedder): um modelo Ollama residente, concorrência 1 para o Qwen.

## 8. Regras de parada e de desvio

- Nenhuma mudança de config, prompt, rótulo, threshold ou scorer após a primeira linha de test-v2.
- Todo desvio é anexado com timestamp a `docs/prereg/deviations.md` e reportado.
- Correções de rótulos encontradas após a run (incluindo a revisão humana opcional) são um
  rescore separado, nunca uma substituição da análise pré-registrada.
- Os resultados de test-v2 são analisados com `study report --manifest config/study_manifest.yaml
  --split test_v2` e os contrastes listados no manifesto (famílias H, S2, S4).
