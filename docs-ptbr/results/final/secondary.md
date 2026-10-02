# Análises secundárias (prereg-v1 S1-S4) no test-v2

Mesmo maquinário de primary.md (bootstrap pareado por cluster, 10k, seed 20260930; p sign-flip; Holm dentro da família). ITT (uma linha com erro conta como errada). Linhas com erro após o rescore: E4 2; E4-P6c 1 (todas as demais 0).

## S1 (prompt engineering, tuned - canonical): DEGENERADA por construção

A regra de um erro-padrão (one-SE) pré-declarada (CV de 5 folds no dev, ITT) selecionou P0 para ambas as trilhas de todo router do tipo LLM, então tuned == canonical byte a byte e Δ ≡ 0: **nenhum teste de S1 é executado no test-v2** (pré-registrado, não uma hipótese descartada). Achado: *o procedimento de seleção não encontrou nenhum ajuste de prompt que valesse a pena aplicar*. Evidência do dev (config/prompt_selection.yaml, docs/prompt-apex.md):

| modelo | canonical | tuned | joint % de CV aninhada (tuned) média ± DP | escolhas dos folds externos aninhados | sensibilidade argmax simples (só dev) |
|---|---|---|---|---|---|
| Sonnet 5 | P0 | P0 | 77.5 ± 9.8 | P0, P0, P0, P0, P0 | P0+P4 |
| Haiku 4.5 | P0 | P0 | 81.5 ± 3.8 | P0+P4, P0, P0, P0, P0 | P0+P4 |
| Jev | P0 | P0 | 78.2 ± 9.4 | P0, P0, P0, P0, P0 | P0+P5 |
| Qwen3-8B | P0 | P0 | 81.5 ± 3.2 | P0, P0, P0+P4, P0, P0 | P0+P4 |

Considerando os quatro modelos, os candidatos canônicos no dev completo tiveram joint médio de CV P0 80.2, P0+P4 81.2 (a regra one-SE manteve P0). As alternativas argmax são sensibilidades apenas do dev e não foram executadas no test-v2 (exceto Jev P0+P6c, variante exploratória de custo; ver estimation.md, se estiver completo).

## S2 (modelo vs modelo, trilha canonical): TOST ±3 pp vs Sonnet 5 (E5)

| id | run | referência | tipo | n casos | Δ pp [IC 95%] | McNemar nível de caso | p TOST (máx. dos 2 unilaterais) | p Holm (S2) | rejeita @0.05 | veredito (IC 90% dentro de ±3 pp) |
|---|---|---|---|---|---|---|---|---|---|---|
| S2 Haiku 4.5 | E6 | E5 | equivalence (margem 3 pp) | 349 | 0.4 [-2.9, 3.6] | 20/17 p=0.743 | 0.06189 | 0.1311 | não | inconclusivo |
| S2 Qwen3-8B | E6b | E5 | equivalence (margem 3 pp) | 349 | -4.2 [-8.1, -0.2] | 21/34 p=0.105 | 0.7233 | 0.7233 | não | inconclusivo |
| S2 Jev | E4 | E5 | equivalence (margem 3 pp) | 349 | 0.6 [-2.1, 3.2] | 16/13 p=0.711 | 0.0437 | 0.1311 | não | equivalente |

ICs pareados de 90% usados para o veredito TOST: S2 Haiku 4.5: -2.4 a 3.1 pp; S2 Qwen3-8B: -7.5 a -0.9 pp; S2 Jev: -1.6 a 2.8 pp.

Nota: E6 Haiku e E6b Qwen têm 1 rep, E5 tem 3 (médias por caso); o Δ pareado é sobre os 349 casos compartilhados.

Leitura: a conclusão pré-registrada é a regra de inclusão no IC pareado de 90% não ajustado. Sob Holm dentro de S2 (α family-wise 0.05), um par é declarado equivalente apenas se seu p TOST, ajustado por Holm, for < 0.05. Onde os dois divergem (a regra do IC diz equivalente, p Holm ≥ 0.05), a leitura conservadora é *equivalência não estabelecida após controle de multiplicidade*; ambos são mostrados e nenhum é preferido post hoc.

Sensibilidade de S2: casos sem erro em ambas as runs (349, 349, 347 casos)

| id | run | referência | tipo | n casos | Δ pp [IC 95%] | McNemar nível de caso | p TOST (máx. dos 2 unilaterais) | p Holm (S2) | rejeita @0.05 | veredito (IC 90% dentro de ±3 pp) |
|---|---|---|---|---|---|---|---|---|---|---|
| S2 Haiku 4.5 | E6 | E5 | equivalence (margem 3 pp) | 349 | 0.4 [-2.9, 3.6] | 20/17 p=0.743 | 0.06189 | 0.1238 | não | inconclusivo |
| S2 Qwen3-8B | E6b | E5 | equivalence (margem 3 pp) | 349 | -4.2 [-8.1, -0.2] | 21/34 p=0.105 | 0.7233 | 0.7233 | não | inconclusivo |
| S2 Jev | E4 | E5 | equivalence (margem 3 pp) | 347 | 0.5 [-2.2, 3.2] | 16/13 p=0.711 | 0.0343 | 0.1029 | não | equivalente |

## S3 (generalização dev -> test): joint do test-v2 - joint de CV do dev

Os números do dev são fixados pela pré-registração (regex 84.8 = joint no dev das regras escritas no dev; BM25 55.7 = joint no dev com configuração fixa); o IC é o IC de bootstrap de cluster do test-v2 deslocado pelo valor fixo do dev (incerteza do dev ignorada, conforme pré-registrado). Hipótese: gap do regex < 0.

| router | joint % no dev | joint % no test-v2 [IC 95%] | gap pp [IC 95%] | veredito |
|---|---|---|---|---|
| regex (regras escritas no dev) | 84.8 | 52.7 [47.3, 57.9] | -32.1 [-37.5, -26.9] | gap < 0 (IC do test inteiramente abaixo do dev) |
| BM25 (dev fixo) | 55.7 | 49.0 [43.8, 54.2] | -6.7 [-11.9, -1.5] | gap < 0 (IC do test inteiramente abaixo do dev) |

## S4 (léxico vs semântico): E3 embedding - E1 regex, bilateral

| id | run | referência | tipo | n casos | Δ pp [IC 95%] | McNemar nível de caso | p sign-flip | p Holm (S4, 1 teste) | rejeita @0.05 | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| S4 embedding - regex | E3 | E1 | two_sided | 349 | 20.9 [15.2, 26.6] | 96/23 p=8.54e-12 | 9.999e-05 | 9.999e-05 | sim | IC exclui 0 |
