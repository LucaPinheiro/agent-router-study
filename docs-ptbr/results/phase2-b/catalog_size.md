# Tamanho do catálogo, 18 × 62 tools [X] (EXPLORATÓRIO) no `test_l`

> Tradução pt-BR de [`docs/results/phase2-b/catalog_size.md`](../../../docs/results/phase2-b/catalog_size.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

Gerado por `scripts/analysis/phase2_b.py`. Conjunta = conjunta top-1 (scorer legacy de roteamento); e2e = `e2e_success_sym` (as duas fases reescoradas com o mesmo scorer simétrico), com o legacy ao lado.

## X1. Entre datasets, não pareado [X]

**Ressalva (obrigatória, prereg-v2 §3 X1):** os datasets diferem: casos, conjuntos de rótulos e texto do catálogo diferentes. Eles compartilham a família do gerador, as proporções de categoria e o procedimento de deduplicação, mas a dificuldade dos casos não é controlada. Os roteadores são reajustados por catálogo, então Δ mede *sistema com 18 tools × sistema com 62 tools*, não um efeito puro de tamanho. As acurácias absolutas não são estimativas de produção.

Bootstraps por cluster independentes por split (10k cada; seeds 20260930 e 20260931); Δ = L − test-v2.

### Conjunta de roteamento

**Ressalva (obrigatória, prereg-v2 §3 X1):** os datasets diferem: casos, conjuntos de rótulos e texto do catálogo diferentes. Eles compartilham a família do gerador, as proporções de categoria e o procedimento de deduplicação, mas a dificuldade dos casos não é controlada. Os roteadores são reajustados por catálogo, então Δ mede *sistema com 18 tools × sistema com 62 tools*, não um efeito puro de tamanho. As acurácias absolutas não são estimativas de produção.

| estratégia | run test-v2 | conjunta % L [IC] | conjunta % test-v2 [IC] | Δ L − test-v2 pp [IC] (não pareado) |
|---|---|---|---|---|
| E1 | v2-e1-regex-routing-r1 (n=349) | 56.3 [50.7, 62.0] (n=300) | 52.7 [47.3, 57.9] | 3.6 [-4.3, 11.2] |
| E2 | v2-e2-bm25-routing-r1 (n=349) | 50.3 [44.7, 56.0] (n=300) | 49.0 [43.8, 54.2] | 1.3 [-6.5, 9.2] |
| E3 | v2a-e3t-titan-routing-r1 (n=349) | 60.0 [54.7, 65.7] (n=300) | 55.9 [50.4, 61.0] | 4.1 [-3.4, 11.6] |
| E10 | v2a-e10t-titan-routing-r1 (n=349) | 59.0 [53.3, 64.7] (n=300) | 51.0 [45.6, 56.2] | 8.0 [0.3, 15.6] |
| E11 | v2-e11-hybrid-routing-r1 (n=349) | 62.3 [56.7, 67.7] (n=300) | 72.8 [67.9, 77.4] | -10.4 [-17.8, -3.3] |
| E4 | v2-e4-jev-canonical-routing-r3 (n=349) | 84.9 [81.1, 88.4] (n=300) | 84.7 [81.0, 88.2] | 0.2 [-5.1, 5.4] |
| E6 | v2-e6-haiku-canonical-routing-r1 (n=349) | 82.0 [77.7, 86.0] (n=300) | 84.5 [80.5, 88.3] | -2.5 [-8.3, 3.2] |
| E6m | v2a-e6m-ministral-canonical-routing-r1 (n=349) | 79.3 [74.7, 84.0] (n=300) | 82.2 [77.9, 86.2] | -2.9 [-9.1, 3.2] |
| E6n | v2a-e6n-nemotron-canonical-routing-r1 (n=349) | 73.0 [68.0, 78.0] (n=300) | 77.1 [72.5, 81.4] | -4.1 [-10.8, 2.5] |
| E7 | v2-e7-tuned-routing-r3 (n=349) | 82.6 [78.3, 86.4] (n=300) | 79.9 [75.8, 84.0] | 2.6 [-3.3, 8.3] |
| E9 | v2-e9-tuned-routing-r3 (n=349) | 82.7 [78.6, 86.6] (n=300) | 81.8 [77.8, 85.6] | 0.9 [-4.9, 6.5] |
| E12 | - | 83.0 [79.0, 86.9] | - | sem contraparte no test-v2 |

### Sucesso e2e

**Ressalva (obrigatória, prereg-v2 §3 X1):** os datasets diferem: casos, conjuntos de rótulos e texto do catálogo diferentes. Eles compartilham a família do gerador, as proporções de categoria e o procedimento de deduplicação, mas a dificuldade dos casos não é controlada. Os roteadores são reajustados por catálogo, então Δ mede *sistema com 18 tools × sistema com 62 tools*, não um efeito puro de tamanho. As acurácias absolutas não são estimativas de produção.

| braço | scorer | e2e % L [IC] | e2e % test-v2 [IC] | Δ pp [IC] (não pareado) |
|---|---|---|---|---|
| E0 | sym | 57.3 [51.7, 62.7] | 56.2 [50.7, 61.3] | 1.2 [-6.5, 8.9] |
| E0 | legacy | 54.7 [49.0, 60.3] | 55.6 [50.1, 60.7] | -0.9 [-8.6, 6.8] |
| E9 | sym | 57.0 [51.3, 62.3] | 53.0 [47.6, 58.2] | 4.0 [-3.6, 11.5] |
| E9 | legacy | 51.3 [45.7, 57.0] | 45.8 [40.4, 51.0] | 5.5 [-2.0, 13.0] |
| E9-full | sym | 56.7 [51.0, 62.3] | 55.0 [49.6, 60.2] | 1.7 [-6.0, 9.1] |
| E9-full | legacy | 51.7 [46.0, 57.3] | 48.1 [43.0, 53.3] | 3.5 [-4.2, 11.2] |

## X2. Subconjunto pareado de tamanho de catálogo [X] (estimação secundária)

**Ressalva (X2):** mesmos casos, mas cada perfil tem seu próprio ajuste (dev × dev-L) e texto de catálogo; Δ isola o efeito das 44 tools confundíveis adicionadas, nos casos que o catálogo pequeno consegue responder, para sistemas ajustados por catálogo.

Subconjunto orig do `test_l`: **114** de 300 casos (toda tool aceitável entre as 18 da fase 1, ou fora de escopo). Run do perfil pequeno = `l-x2-small-<key>-routing-r1` (catálogo 128584617807) nesses casos; grande = o braço principal restrito a eles. Bootstrap pareado por cluster sobre os casos compartilhados.

| estratégia | conjunta 62 tools % no orig [IC] | conjunta 18 tools % no orig [IC] | casos pareados | Δ 62 − 18 pp [IC] | leitura |
|---|---|---|---|---|---|
| E1 | 50.9 [42.1, 59.6] | 43.9 [35.1, 53.5] | 114 | 7.0 [0.9, 13.2] | Δ > 0 |
| E2 | 26.3 [18.4, 35.1] | 43.0 [34.2, 51.8] | 114 | -16.7 [-25.4, -7.9] | Δ < 0: 62 tools custam acurácia |
| E3 | 43.9 [35.1, 53.5] | 51.8 [42.1, 60.5] | 114 | -7.9 [-15.8, 0.0] | IC inclui 0 |
| E10 | 46.5 [37.7, 55.3] | 59.6 [50.9, 68.4] | 114 | -13.2 [-21.1, -6.1] | Δ < 0: 62 tools custam acurácia |
| E11 | 48.2 [39.5, 57.9] | - | - | - | **NÃO RODADA** (falta a run do perfil pequeno) |
| E4 | 77.2 [69.9, 84.2] | 86.8 [80.7, 93.0] | 114 | -9.6 [-14.6, -5.0] | Δ < 0: 62 tools custam acurácia |
| E6m | 78.1 [70.2, 85.1] | 83.3 [76.3, 89.5] | 114 | -5.3 [-10.5, 0.0] | IC inclui 0 |
| E6 | 77.2 [69.3, 85.1] | 80.7 [73.7, 87.7] | 114 | -3.5 [-7.9, 0.9] | IC inclui 0 |

### Conjunta do perfil grande no subconjunto orig × nos casos de tools novas (descritivo; casos diferentes)

| estratégia | subconjunto orig % [IC] | casos de tools novas % [IC] |
|---|---|---|
| E1 | 50.9 [42.1, 59.6] | 59.7 [52.7, 66.7] |
| E2 | 26.3 [18.4, 35.1] | 65.1 [58.1, 71.5] |
| E3 | 43.9 [35.1, 53.5] | 69.9 [63.4, 76.3] |
| E10 | 46.5 [37.7, 55.3] | 66.7 [59.7, 73.1] |
| E11 | 48.2 [39.5, 57.9] | 71.0 [64.5, 77.4] |
| E4 | 77.2 [69.9, 84.2] | 89.6 [85.5, 93.4] |
| E6 | 77.2 [69.3, 85.1] | 84.9 [79.6, 89.8] |
| E6m | 78.1 [70.2, 85.1] | 80.1 [74.2, 85.5] |
| E6n | 65.8 [57.0, 74.6] | 77.4 [71.5, 83.3] |
| E7 | 75.7 [67.8, 83.0] | 86.7 [82.1, 91.0] |
| E9 | 76.3 [68.4, 83.6] | 86.6 [81.7, 90.9] |
| E12 | 75.7 [67.8, 83.0] | 87.5 [83.0, 91.6] |

## X3. Cache de prompt do Haiku 4.5 com o prompt maior [X]

| chamadas de estágio | tokens de prompt médios | chamadas ≥ 4 096 tokens % | chamadas com leitura de cache % | chamadas com escrita de cache % | US$/1k observado [IC] | US$/1k tabela sem cache [IC] |
|---|---|---|---|---|---|---|
| 600 | 2732 | 0.0 | 0.0 | 0.0 | 7.154 [7.067, 7.240] | 7.154 [7.067, 7.240] |

## X4. Reescore simétrico da fase 1 [X]

Já rodado antes do congelamento e reportado como exploratório em `docs/results/phase1-sym/exploratory_e2e_sym.md` (nunca reclassificado).
