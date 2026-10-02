# Pré-registro prereg-v2: catálogo grande (Parte B), split test-L, catálogo de 62 tools

> Tradução pt-BR de [`docs/prereg/prereg-v2.md`](../../docs/prereg/prereg-v2.md). O original em inglês é o documento congelado na tag; em caso de divergência, vale ele.

Status: **CONGELADO** na tag git `prereg-v2`, antes da primeira linha do test-L. Nada abaixo (configs,
limiares, mapas de calibração, prompts, catálogo, scorers, manifesto, arquivos de ids de caso, código de
análise) muda depois dessa linha (§8). A Parte A (adendo de nuvem no catálogo de 18 tools) é congelada
separadamente em `docs/prereg/prereg-v2a.md` (tag `prereg-v2a`). Rascunho de origem: `docs/prereg/prereg-v2-draft.md`.
Plano: `.omc/plans/autopilot-impl.md` T6.1. Registro de ajuste no dev-L: `docs/tuning-effort-l.md` §B,
`.omc/handoffs/p2-tuning.md`.

> O T4.3 está completo (commit e1e8683). Todo valor do test-L abaixo foi preenchido em 2026-10-02, antes da
> tag e antes de qualquer linha do test-L: o sha do dataset, os arquivos de ids de caso e o dry-run do test-L.

## 0. Herdado do prereg-v1 sem mudança

Unidade = caso, repetições tiradas a média por caso; ITT (uma falha de infra ou de parse conta como erro);
multirrótulo (qualquer rótulo aceitável, o primeiro rótulo como sensibilidade); fora de escopo =
escalonamento conta como abstenção; bootstrap pareado por cluster (caso), 10,000 reamostragens, seed
20260930; NI = limite inferior do IC 95% bilateral mais um p-valor sign-flip unilateral com o deslocamento;
equivalência = TOST (IC 90% dentro dos limites); bilateral = IC mais p-valor sign-flip; Holm dentro de cada
família; cache de respostas por (caso, rep, prompt renderizado); latência **só** do benchmark dedicado; custo
em três regimes; regras de operação, retentativa e aborto do prereg-v1 §7.

**Restrições da fase 2 (2026-10-02, vinculantes):**
- nenhum modelo local roda (sem Ollama: sem Qwen3-8B, sem qwen3-embedding local). Regex e BM25 são código de
  CPU, não modelos, e ficam;
- o OpenRouter é usado só para o `typesafe/jev-router`; todo o resto roda no Bedrock;
- o Sonnet 5 nunca é roteador sozinho no test-L. Ele aparece só como último passo das cascatas E9-L /
  E12-L e como executor e2e.

## 1. Artefatos congelados

| artefato | valor |
|---|---|
| código | o commit marcado `prereg-v2` |
| catálogo | perfil grande (`CATALOG_PROFILE=large`, mcp-server-large em :8766), `catalog_hash` **bc7cd75fce87** (62 tools, 10 skills + globais; conferido ao vivo no congelamento, 2026-10-02); `mcp_server/tools_list_large.json` sha256 `a0583726a351a862494c0f655b409c592e48c9a2f1c31ef43371b7ff63a88f07`. Perfil pequeno do X2: `catalog_hash` **128584617807** (sem mudança desde a fase 1), `tools_list.json` `a9776477226c398702032f7fdd05223fc0a013dfc68ebe0e8f749567e27aa123` |
| dados de dev | `data/dataset_dev_l.jsonl` sha256 `b02b3722f5c4e434dd97a4c6a4811ac18a1fd1945784a6375639acd0b376e238` (150 casos) |
| dados de teste | `data/dataset_test_l.jsonl` (300 casos, seed do gerador 20261009, auditado, adjudicação automática; commit e1e8683). **SHA DO DATASET TEST-L: `ae21a5dbce16eb90278612f7dbcf875cb6610b7b12a49cb6f7f57e503d680ff2`** |
| scorer de roteamento | `scorer_hash` legacy **e0eef1fb0073** (sem mudança; primário de roteamento, sensibilidade do e2e) |
| scorer e2e | `scorer_sym_hash` simétrico **5ad0f65296e4** (`src/routing_study/eval/scorers_sym.py`; primário do e2e) |
| prompt | `prompt_hash` **c61ad0a7b7f8** (P0; sem mudança de template, sem busca de prompt) |
| manifesto | `config/study_manifest_l.yaml`, sha256 `788fac3665ba82e06703a644f42e753f1413441dcc8d3395071d6d8ce8bc2e6b` (73 entradas) |
| ids de latência | `config/manifest/latency_test_l_b{1..4}.ids` (4 × 25 casos estratificados do test-L, `scripts/analysis/latency_ids.py --split test_l`). sha256 b1 `0d616311ff839cc822afa844a7c3dc59bdbe9c75618b41ec26d16b4194371dd5`, b2 `ded21cf01feb9d1246a3f7dc919e5e1ed6eb937cdfe2c14e6fe9241b7c6dce09`, b3 `2550bd1ec7443ed6d9cc1dbca393c6600a54a2ad804bb20c61159ec8c9a5ab86`, b4 `70723d6305a5b77a42e2267902fded0c5a8d9a14c4d68a77ac47cb64877465a4` |
| ids do X2 | `config/manifest/x2_test_l_orig.ids` (o subconjunto orig, `scripts/analysis/x2_orig_ids.py`; n ≥ 60 verificado). **n = 114** de 300 (≥ 60 vale), sha256 `42cba58577b41b0ebb379f3fe5867610ea8560e7276eb11a05d2546a4a952945` |
| limiares / calibração | escritos em `config/experiments_l/*.yaml` (§5); sem mudança depois dos commits de ajuste no dev-L (17b0637 e anteriores) |
| código de análise | `scripts/analysis/phase2_b.py`, escrito antes do test-L no commit **27cacee**. Na tag, a única diferença em relação a 27cacee é o bloco de constantes `TBD@freeze` (confirmações de catálogo/scorer, `MANIFEST_L_SHA`, `DEV_FIXED_L`, `S7_PROBE`, `S2_MIN_N` e `DATASET_SHA["test_l"]`). Verificação: `git diff 27cacee prereg-v2 -- scripts/analysis/phase2_b.py` |
| trava de hashes da fase 1 | `tests/test_phase1_hashes.py` verde na tag |

### Config hashes por run (verificados pela guarda de versão do manifesto)

Toda entrada do perfil grande também verifica `catalog_hash bc7cd75fce87`; toda entrada do X2 verifica
`128584617807`. O `prompt_hash` é `c61ad0a7b7f8` em todas. Os nomes `l-*` são os fixados no
`phase2_b.py`.

| run(s) | config | config_hash |
|---|---|---|
| `l-e1-regex-routing-r1`, `l-e1-regex-routing-repeat20` | `experiments_l/e1_regex_l.yaml` | 9edc10d85a4e |
| `l-e2-bm25-routing-r1` | `experiments_l/e2_bm25_l.yaml` | 047a16011d05 |
| `l-e3-embedding-routing-r1` | `experiments_l/e3_embedding_l.yaml` | 3cd09a609c93 |
| `l-e10-classifier-routing-r1` | `experiments_l/e10_classifier_l.yaml` | 61260135d35a |
| `l-e11-hybrid-routing-r1` | `experiments_l/e11_hybrid_l.yaml` | 0078bcc597f8 |
| `l-shadow-tuned-routing-r3` (conjunto shadow sem Sonnet) | `experiments_l/e9_regex_jev_llm_l.yaml` + override | ae7dda1ab390 |
| `l-e4-jev-canonical-routing-r3` | `experiments_l/e4_jev_l.yaml` | d8d2f8940050 |
| `l-e6-haiku-canonical-routing-r1`, `-rep2-60` | `experiments_l/e6_llm_haiku_l.yaml` | 8b7b8fb00143 |
| `l-e6m-ministral-canonical-routing-r1`, `-repeat50` | `experiments_l/e6m_llm_ministral_l.yaml` | 1ce8c6004c5f |
| `l-e6n-nemotron-canonical-routing-r1`, `-repeat50` | `experiments_l/e6n_llm_nemotron_l.yaml` | ae768b0a8656 |
| `l-e9-tuned-routing-r3`, `l-e9-tuned-e2e-r1`, `l-e9-tuned-e2e-rep2-60` | `experiments_l/e9_regex_jev_llm_l.yaml` | 8236c879738c |
| `l-e7-tuned-routing-r3` | `experiments_l/e7_regex_jev_l.yaml` | babfafa1bdae |
| `x-l-e12-hybrid-tuned-routing-r3` | `experiments_l/e12_hybrid_jev_llm_l.yaml` | fd13e06c82a4 |
| `l-e0-native-e2e-r1`, `l-e0-native-e2e-rep2-60` | `experiments_l/e0_native_l.yaml` | 93c7c3ea1e02 (¹) |
| `l-e9-fullskill-e2e-r1` | E9-L + `routing.tool.expose_top_k: 6` | 2741f7281d8b |
| `lat-l-{regex,bm25,embedding,classifier,hybrid}-b1..4` | E1/E2/E3/E10/E11-L + overrides de latência | d341905fd5ca / 09e347ca67bb / b57d9830966f / 8158869c2b7d / 31b1ccbfcf66 |
| `lat-l-{jev,haiku,e6m,e6n}-b1..4` | E4/E6/E6m/E6n-L + overrides de latência | bf67bc0d09bf / 170370d07bed / 127123dc6afa / 5afc47143514 |
| `lat-l-{e7,e9}-b1..4` | E7-L / E9-L + overrides de latência | 86b20f674287 / 987a841f839f |
| `l-x2-small-{e1,e2,e3,e10}-routing-r1` | `experiments/e1_regex`, `e2_bm25`, `e3_embedding_titan`, `e10_classifier_titan` | 2da827d0effb / 7bb5a5960490 / 73f81417a487 / 70374caa4b59 |
| `l-x2-small-{e4,e6m,e6}-routing-r1` | `experiments/e4_jev`, `e6m_llm_ministral`, `e6_llm_haiku` | acd7ff96155b / 0d8fbee553f3 / f6c0edce210b |

(¹) `mcp_url` não faz parte do `config_hash`, então o E0-L tem o mesmo `config_hash` do E0 da fase 1. Os dois
se distinguem pelo `catalog_hash` (verificado na entrada e em toda linha) e pelo nome da run.

Nota sobre a validação e2e no dev-L (T5.5): ela rodou com o `config_hash` f8c5522232cc do E9-L. O congelado
8236c879738c difere só nos blocos de BM25 e híbrido e nos seus mapas (commits c32c9ef e
5d7ffc6). A cascata do E9-L (regex 0.88 → Jev 0.76 → Sonnet; estágio de tool Jev 0.50 → Sonnet) não
usa esses blocos, e os seus limiares e mapas são idênticos.

## 2. Braços (catálogo grande, test-L, ~300 casos)

- **Roteadores livres (1 rep):**
  - E1 regex (regras escritas pelo agente, `config/regex_rules_l.yaml`);
  - E2 BM25;
  - E3 embedding denso no Bedrock Titan v2 (`amazon.titan-embed-text-v2:0`);
  - E10 sonda linear sobre os vetores do Titan v2;
  - E11 híbrido (regex + sonda convexo, α 0.5).

  O Titan v2 é o embedder do perfil grande (recomendação do dev da Parte A; `tuning-effort-l.md` §B). E3c
  (Cohere), E3t (≡ E3 aqui) e E10c **não** são, portanto, runs separadas no test-L, e o `phase2_b.py`
  os reporta como NÃO RODADOS.
- **LLMs / meta-roteadores (P0, trilha canônica):**
  - E4 Jev (`typesafe/jev-router`, OpenRouter), 3 reps;
  - E6 Haiku 4.5, 1 rep + rep 2 em 60 casos;
  - E6m Ministral 3 8B e E6n Nemotron Nano 9B v2 (raciocínio desligado), no Bedrock, 1 rep + rep 2 em
    50 casos cada.
- **Cascatas (trilha ajustada = P0; limiares do shadow do dev-L, regra (a)), 3 reps cada:**
  - E7-L: regex → Jev;
  - E9-L: regex → Jev → Sonnet 5;
  - E12-L: híbrido → Jev → Sonnet 5 (exploratório).
- **e2e (executor Sonnet 5), 1 rep:**
  - E0-L: nativo, sem roteador;
  - E9-L;
  - E9-L-fullskill: E9-L com todas as tools da skill roteada expostas (`expose_top_k` 6; as skills grandes
    têm 5–6 tools).
- **Não rodados (restrição):** E6b Qwen3-8B, E3 qwen3-embedding local, sonda E10 local e qualquer
  roteador Sonnet sozinho.

## 3. Hipóteses

Conjunta = acurácia conjunta de roteamento top-1 (scorer legacy de roteamento), ITT. `e2e_success_sym` = o
scorer e2e simétrico (§4). Pareado por caso. α = 0.05.

### Primárias (confirmatórias; Holm entre H1-L, H2-L, H3-L)

- **H1-L ("vale ter roteador?").** e2e_success_sym(E9-L) − e2e_success_sym(E0-L), bilateral,
  pareado, IC 95%. Afirmação direcional só se o IC excluir 0.
  - MDE esperado com n ≈ 300: cerca de 5.5–7.5 pp.
  - Prior de tamanho de efeito, escrito aqui e fora do teste: o reescore simétrico da fase 1 deu
    E9 − E0 = −3.2 [−6.0, −0.3] pp (EXPLORATÓRIO, `docs/results/phase1-sym/`). Na validação no dev-L
    (40 casos), o E9-L teve 60.0 sym e o E0-L 65.0.
  - Estimativa co-primária: a razão de custo por turno E9-L / E0-L (regime observado) com IC.
- **H2-L (LLM pequeno gerenciado vs LLM pequeno premium; reespecificada pela restrição de 2026-10-02).**
  Conjunta(E6m Ministral 3 8B) − Conjunta(E6 Haiku 4.5) > −3 pp (NI). Substitui o contraste
  Ministral × Qwen local do rascunho, já que nenhum braço local roda no test-L.
  - Estimativa co-primária: a razão de p95 de latência E6m / E6 do benchmark.
- **H3-L (meta-roteador barato vs LLM pequeno premium).** Conjunta(E4 Jev) − Conjunta(E6 Haiku 4.5) > −3 pp (NI).
  O E4 é a média de 3 reps por caso.

Uma primária cuja run falte ou não esteja COMPLETE é reportada como NÃO RODADA, nunca imputada. Ela entra no
Holm com p = 1, então o tamanho da família continua 3.

Expectativa no dev-L (fora dos testes; aninhada ou CV no dev-L): E9-L 86.0, E7-L 86.0, E4 86.7,
E6 84.0, E6m 78.7, E6n 73.3.

### Secundárias

- **Família S-e2e** (Holm dentro):
  - **S1.** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, unilateral. Confirma o
    D-002 da fase 1 num split novo.
  - **S2.** O mesmo contraste de H1-L, restrito aos casos em que os dois braços executaram as mesmas
    chamadas de negócio. Equivalência ±3 pp (TOST).
    - OQ-2 resolvida: se esse subconjunto tiver menos de 60 casos, S2 vira só estimação (IC 90%
      reportado) e entra no Holm com p = 1.
- **Família S-routing** (Holm dentro de S4, S7):
  - **S3** (magnitude com IC, não testada no Holm). Conjunta(E1 regex, test-L) − a conjunta fixa de CV
    no dev-L **82.7%** (depois da rodada do dev-L, otimista; `tuning-effort-l.md` §B).
  - **S4.** Conjunta(E3 embedding Titan) − Conjunta(E1 regex), bilateral.
  - **S7.** Conjunta(E10 sonda) − Conjunta(E4 Jev), bilateral. O E10 (Titan) é a única sonda do perfil
    grande, então é a "melhor sonda pré-declarada".
  - **Retiradas** pela restrição, fora da família: S5 (Cohere × embedding local) e S6
    (Nemotron × Qwen3-8B local). Os braços de referência delas são locais.

### Sensibilidade (reportada, não testada)

- H1-L com o scorer legacy assimétrico, lado a lado, com a contagem de casos em que o veredito
  difere.
- Conjunta só com o primeiro rótulo.
- A interseção sem erros.
- ambiguo reportado à parte.
- Casos sinalizados por humano excluídos.

### Só estimação (ICs, sem testes)

Por estratégia:
- skill %, tool % condicional, recall@1/2/3;
- taxas de erro e de falha de parse (ITT); taxas de mudança entre repetições (Haiku 60, 8B 50, regex 20);
- ECE e Brier (bruto e calibrado no dev-L);
- custo por 1k em três regimes;
- latência p50/p95 com o primeiro caso frio à parte (`lat-l-*`, só gerenciados e CPU);
- cobertura das cascatas por passo, incluindo **a cobertura do regex no seu limiar de 0.88**;
- precisão e recall da abstenção;
- a decomposição do e2e, `args_invented`, `entity_grounded` e a variância do executor (E0-L e E9-L
  em 60 casos);
- por categoria, por skill (original × nova) e por grupo confundível G1–G12.

E6n (Nemotron), E2, E11, E7-L e E12-L (exploratório) são braços de estimação.

### Exploratório: tamanho do catálogo, 18 × 62 tools

- **X1 (entre datasets, não pareado).** Conjunta(test-L) − Conjunta(test-v2) para cada estratégia presente
  nas duas fases (linhas do test-v2 da fase 1 ou da Parte A), com bootstraps independentes por split. A
  mesma comparação é feita para o e2e de E0/E9 com o scorer sym. A ressalva `CAVEAT_X` do `phase2_b.py` é
  impressa onde o X1 aparecer.
- **X2 (subconjunto pareado de tamanho de catálogo, estimação secundária).** O subconjunto orig é todo caso do
  test-L cujas tools aceitáveis estão todas entre as 18 originais, ou que é fora de escopo.
  - Ele é roteado pelas configs congeladas do perfil pequeno (E1, E2, E3 = Titan `e3_embedding_titan`,
    E10 = `e10_classifier_titan`, E4 Jev, E6m, E6 Haiku). A comparação é a run do perfil grande restrita aos
    mesmos casos. O resultado é um Δ conjunta pareado com IC por estratégia.
  - O E11 não roda no X2: o híbrido pequeno da fase 1 usa a sonda local.
- **X3.** Comportamento do cache do Haiku (dev-L: P0 ≈ 2.7k tokens < o mínimo de cache de 4,096, 0 leituras de cache).
- **X4.** Reescore sym da fase 1 (já reportado como exploratório).

## 4. Métricas e scorers

- **Primária de roteamento:** acurácia conjunta top-1, scorer legacy de roteamento `e0eef1fb0073`.
- **Primária do e2e:** `e2e_success_sym` (`scorers_sym.py`, `5ad0f65296e4`). A skill é atribuída
  pelo comportamento, de forma idêntica nos dois braços:
  1. a skill da primeira tool de negócio executada;
  2. senão, a skill da tool creditada por uma clarificação (inferida da pergunta);
  3. senão, só escalonamento ou abstenção do host → `__abstain__`;
  4. só chamadas globais → `__global__`;
  5. nenhuma ação → `__abstain__`.

  Sucesso = a skill atribuída é aceitável **e** (a primeira chamada está OK com args válidos e
  terminou, **ou** uma clarificação é creditada, **ou** uma chamada posterior recupera). O scorer nunca lê
  `native`, a skill ou a tool do roteador, nem `resolved_by` (testado em unidade).
- **Sensibilidade do e2e:** `e2e_success` legacy.
- Os dois scorers são aplicados aos mesmos bytes brutos. O `phase2_b.py` confere isso.

## 5. Ajuste, limiares e calibração (só dev-L, congelados em `config/experiments_l/`)

Todo o ajuste usou o dev-L (150 casos): CV de 5 folds estratificada por categoria, seed 0, estimativas aninhadas.
O test-L foi gerado depois de as configs ficarem finais (T4.3 depois do T5.5) e não foi lido.

| braço | escolha congelada | conjunta dev-L [IC 95%] | mapas escritos (skill / tool) |
|---|---|---|---|
| E1 regex | 298 regras (~0.5 h do timebox de 4 h + 2 h), histórico 2 | 82.7 [76.7, 88.7] (otimista) | Platt / Platt |
| E2 BM25 | utterance, topk_sum k 4, char 2–5, folding, shots, okapi k1 1.2 b 0.75, histórico 2 | 52.7 [44.7, 60.7] | ✓ / ✓ |
| E3 Titan | centroid, k 3, T 0.02, histórico 1, shots | 61.3 [53.3, 69.3] | – / ✓ |
| E10 sonda Titan | C 1000, shots, descrição, histórico 2 | 66.0 [58.0, 73.3] | – / ✓ |
| E11 híbrido | regex + classificador convexo, α 0.5 | 81.3 [75.3, 87.3] | ✓ / ✓ |
| E4 Jev | P0 | 86.7 [80.7, 92.0] | ✓ / – |
| E6 Haiku 4.5 | P0 | 84.0 [78.0, 89.3] | ✓ / – |
| E6m Ministral | P0, T 0 | 78.7 [72.0, 84.7] | ✓ / ✓ |
| E6n Nemotron | P0, T 0, `/no_think` | 73.3 [66.0, 80.0] | ✓ / ✓ |

- **Limiares das cascatas.** Regra (a) do prereg-v1 §4: a conjunta máxima sujeita a um custo de roteamento de
  no máximo 0.5 × o custo do Sonnet P0 no dev-L (orçamento US$ 0.003761 por caso). Grade 0.50..0.99, passo
  0.01. Ajustados no shadow do dev-L, que incluiu o Sonnet com 1 rep só no dev-L (OQ-1), e com
  ajuste cruzado. Resultados:
  - **E7-L:** regex 0.88.
  - **E9-L:** regex 0.88, Jev 0.76; estágio de tool Jev 0.50 (os mesmos valores da fase 1).
  - **E12-L:** híbrido 0.78, Jev 0.76; estágio de tool Jev 0.50.
  - Conjunta no dev-L com ajuste cruzado: E7-L 86.0, E9-L 86.0, E12-L 82.7.
  - Cobertura do estágio de skill do E9-L no dev-L: regex 70%, Jev 30%, Sonnet 0%.
- **Prompt.** P0 em tudo e nenhuma busca de prompt. Toda taxa de falha de parse no dev-L ficou abaixo de 2%,
  então nenhuma correção só de formato foi usada.
- **Calibração.** Um mapa só é mantido onde o ECE com ajuste cruzado fica abaixo do bruto.

## 6. Plano de runs, ordem e orçamento

Manifesto `config/study_manifest_l.yaml` (sha256 no §1): 73 entradas com `split: test_l`. A ordem de
prioridade segue a ordem de corte do plano (`autopilot-impl.md` §5). A guarda recusa runs e nunca as
reordena, então as prioridades mais baixas são as primeiras que um teto remove: variância do executor (B16),
depois E9-L-fullskill (B15), depois X2-Haiku (B18), depois latência (B17).

| prioridade | runs | casos × reps |
|---|---|---|
| 10 | E1, E2, E3, E10, E11 | 300 × 1 |
| 11 | repetição do E1 (determinismo) | 20 × 2 |
| 20 | shadow, decisor E9-L, conjunto {regex, bm25, embedding, classifier, hybrid, jev}, sem Sonnet no conjunto | 300 × 3 |
| 25 | E4 Jev | 300 × 3 (acertos de cache das amostras Jev do shadow) |
| 25 | E6 Haiku, E6m, E6n | 300 × 1 |
| 30 | E9-L, E7-L roteamento | 300 × 3 |
| 31 | E12-L roteamento (exploratório) | 300 × 3 |
| 40 | **E0-L e2e, E9-L e2e (H1-L)** | 300 × 1 |
| 50 | Haiku rep 2; E6m, E6n rep 2 (rep 1 = acerto de cache) | 60 × 2; 50 × 2 |
| 70 | blocos `lat-l-*` 1–4 × {regex, bm25, embedding, classifier, hybrid, jev, haiku, e6m, e6n, e7, e9}, intercalados por bloco, concorrência 1, caches desligados, `.cache/latency-l` novo | 4 × 25 por braço |
| 80 | X2 perfil pequeno: E1, E2, E3 (Titan), E10 (Titan), E4, E6m | subconjunto orig (114) × 1 |
| 81 | X2 perfil pequeno: E6 Haiku | subconjunto orig × 1 |
| 85 | E9-L-fullskill e2e (S1) | 300 × 1 |
| 90 | variância do executor E0-L, E9-L | 60 × 1 |

Mover o S1 da prioridade 45 do rascunho para 85 segue a ordem de corte do plano, que corta o B15 antes do
B18-Haiku e dos blocos de latência.

**Dry-run.**
- Num **substituto no dev-L** (2026-10-02; o mesmo manifesto com `split: dev_l` e arquivos de ids do dev-L), todas
  as 73 entradas deram PLAN com 0 ABORT: todo `config_hash`, `prompt_hash` e `catalog_hash`
  (grande e pequeno) reproduz.
- O **dry-run do test-L** é refeito depois do T4.3: `uv run study run-manifest config/study_manifest_l.yaml --dry-run`.
  **Resultado (2026-10-02, depois de e1e8683): 73 / 73 entradas PLAN, 0 ABORT, 0 chaves presentes (0 linhas em
  disco).** Todo `config_hash`, `prompt_hash` e `catalog_hash` reproduz no test-L, e todo arquivo de ids
  resolve dentro do split. O `prereg_hashes.py` foi rodado de novo e deixou o manifesto sem mudança.

### Orçamento

- **Marcas:** marca do ledger da fase 2 AWS 52.11 / OpenRouter 5.83 (`docs/prereg/phase2-budget.md`).
- **Tetos** (a atualização de restrição de 2026-10-02 substitui a fórmula do T6.2 do plano):
  - total da fase 2 na AWS ≤ US$ 40, então o teto do ledger da AWS é **92.11**
    (`BUDGET__AWS_USD_CAP=92.11`);
  - o teto do OpenRouter é **9.43** = 5.83 + 3.6 (`BUDGET__OPENROUTER_USD_CAP=9.43`).
- **Ledger no congelamento** (depois do T4.3): AWS 59.71 / OR 6.13. Isso deixa **32.40 AWS** e
  **3.30 OR** para este manifesto.

Custo esperado por item. Cada valor é um custo por caso no dev-L medido no T5.3–T5.5 multiplicado pelo
tamanho do test-L (300 casos; X2 = 114, o subconjunto orig):
- Haiku 7.18, Ministral 0.70, Nemotron 0.33 e Jev 1.28 US$ por 1k casos;
- roteamento do E9-L 1.03 por 1k (estágio de tool do Jev 0.95, fallback do Sonnet ≈ 0.11);
- e2e por caso: E0-L 0.0139 e E9-L 0.0165;
- perfil pequeno: Haiku 4.97, Ministral 0.45 e Jev 0.78 por 1k.

| prioridade / item | AWS US$ | OR US$ |
|---|---|---|
| 10 roteadores livres + vetores Titan do shadow | 0.01 | – |
| 20/25 shadow r3 + E4 Jev r3 (amostras Jev compartilhadas; +30% de erros do estágio de tool do decisor E9) | 0.10 | 1.41 |
| 25 E6 Haiku r1 (B10) | 2.15 | – |
| 25 E6m + E6n r1 (B11) | 0.31 | – |
| 30/31 E9-L, E7-L, E12-L r3 (Jev quase todo em acertos de cache; fallback do Sonnet) (B12) | 0.10 | 0.17 |
| 40 **E0-L e2e** (B13) | 4.16 | – |
| 40 **E9-L e2e** (B14) | 4.94 | – |
| 50 Haiku rep2-60 + 8B rep2-50 | 0.48 | – |
| 70 latência, 11 braços × 100, caches desligados (B17) | 0.83 | 0.33 |
| 80/81 X2 nos 114 casos orig (B18) | 0.62 | 0.09 |
| 85 E9-L-fullskill e2e (B15; +5% pela exposição maior de tools) | 5.18 | – |
| 90 variância do executor em 60 (B16) | 1.82 | – |
| **total esperado** | **20.71** | **2.00** |
| com 25% de contingência | 25.88 | 2.50 |
| disponível sob os tetos (ledger no congelamento) | 32.40 | 3.30 |

- **Pior caso do OR.** Se nenhum prompt do estágio de tool do Jev dos decisores E9-L / E7-L / E12-L fosse um
  acerto de cache, o OR chegaria a cerca de 3.3, o que iguala a folga do OR. As entradas de latência e de X2 do
  Jev seriam então as recusadas.
- **Os preços a priori da guarda não são um limite superior para dois itens:**
  - o Jev não tem preço de tabela, então o preço a priori da guarda para ele é 0;
  - o preço a priori do Haiku (2.6 por 1k) fica abaixo do medido, 7.18 por 1k.

  Os tetos do ledger por chamada acima garantem, portanto, essas duas contas. Uma run parada por
  `BudgetExceededError` é um desvio, reportada como não rodada (§8).

## 7. Regras de parada e de desvio

- Nenhuma mudança de configs, prompts, rótulos, limiares, mapas de calibração, catálogo, scorers, manifesto,
  arquivos de ids ou `phase2_b.py` depois da primeira linha do test-L.
- Erros de infra: até 2 retentativas das linhas de erro. Uma run com mais de 2% de erros é FLAGGED e
  refeita do zero, nunca remendada.
- **Parada por orçamento.** Se o delta da AWS na fase 2 chegar a US$ 38 (ledger 90.11), ou o OR chegar a 9.43,
  antes de toda run com prioridade ≤ 40 estar COMPLETE: parar e registrar um desvio. As primárias são reportadas
  com o que estiver COMPLETE. Uma primária incompleta é reportada como não rodada, nunca imputada. O
  delta nunca pode passar de AWS 40.
- **Parada por dados** (antes da tag, então não é desvio): se a auditoria do test-L sinalizar mais de 40% dos
  casos, ou o subconjunto orig tiver menos de 60 casos, parar e decidir (com registro) se regenera ou
  completa as vagas afetadas.
- Correções de rótulo depois da run vão para um reescore separado e nunca substituem a análise.
- Os desvios são acrescentados a `docs/prereg/deviations-v2.md` com timestamp.

## 8. Plano de análise

`uv run python scripts/analysis/phase2_b.py --manifest config/study_manifest_l.yaml` escreve
`docs/results/phase2-b/{primary,secondary,estimation,catalog_size}.{md,json}` e
`estudos/figuras/final-b-*.png`. É idempotente, e o `final_l_all.py` /
`docs/results/phase2/` do rascunho são este script (só nome).

- **Verificações de proveniência, que falham alto.** Em toda linha: hashes de catálogo, scorer, prompt e dataset,
  mais o split. Também conferidos:
  - um config hash por arquivo, igual ao valor congelado do manifesto;
  - os arquivos legacy e sym de uma run e2e reescorados a partir dos mesmos bytes brutos;
  - o dataset, o código do scorer, os snapshots de tools e os bytes do manifesto contra o §1.
- **Elegibilidade das runs.** Uma run só é analisada quando o log do manifesto diz COMPLETE.
- **Conteúdo das saídas:**
  - H1-L com os dois scorers;
  - todo número marcado [C], [E] ou [X];
  - as ressalvas de X1/X2 em toda tabela de tamanho de catálogo.
- **Relatório:** capítulos novos em pt-BR em `estudos/` mais o espelho em `docs/`. Os capítulos da fase 1 não são
  editados, a não ser por links.

## 9. Ameaças específicas da Parte B

- **Regex otimista.** As regras foram escritas lendo erros do dev-L. Os limiares do E9-L / E7-L
  dependem delas, e a cobertura do regex no test-L a 0.88 é reportada (S3).
- **Um embedder.** O Titan v2 foi escolhido no dev da Parte A. O Cohere não tem braço no test-L.
- **H2-L reespecificada.** Ela agora compara dois modelos gerenciados; a comparação com o 8B local existe só no
  test-v2 (Parte A).
- **Deriva do Jev** (plano R9). Os modelos atendidos são registrados por chamada.
- **Famílias de auditor/gerador** diferem das da fase 1 (gerador Bedrock Kimi K2.5; auditores gpt-oss-120b e
  DeepSeek v3.2). A qualidade dos rótulos é reportada pelo κ.
- **X1 não é efeito de tamanho** (§3). O X2 controla os casos, mas não o ajuste por catálogo.
