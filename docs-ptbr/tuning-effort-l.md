# Esforço de tuning, fase 2 (só dev / dev-L)

> Tradução pt-BR de [`docs/tuning-effort-l.md`](../docs/tuning-effort-l.md). Em caso de divergência, vale o original em inglês.

Mesmo protocolo da fase 1 (`docs/tuning-effort.md`): CV de 5 folds estratificada por categoria, seed 0
(`scripts/analysis/tune_router.py`). "Aninhado" = em cada fold, o ponto da grade que é o melhor nos
outros 4 folds é pontuado no fold separado (uma estimativa do procedimento de ajuste). "Fixo" = a
config commitada pontuada em todo o dev (escolhida nos mesmos dados, otimista). Os ICs são o
bootstrap pareado por caso do prereg-v1 (10,000 reamostragens, seed 20260930) sobre as linhas
separadas reunidas. Os mapas de calibração são ajustados nos folds de treino e pontuados no fold
separado; com `--calibrator both` o mapa (isotônico ou Platt) é escolhido por nível pelo Brier
reunido dos folds separados, e **só é escrito na config se o seu ECE com ajuste cruzado for menor
que o ECE bruto** (`docs/decisions/2026-10-01-calibration-and-prompts.md`, prereg-v2 §5). Os
splits de teste nunca foram lidos.

## §A. Parte A: adendo de nuvem no catálogo de 18 tools (dev da fase 1, 151 casos)

Só as seis estratégias novas são ajustadas; toda estratégia da fase 1 é reaproveitada como
congelada. Logs e JSON por ponto: `results/phase2a/` (no gitignore); os JSONs de resumo são
copiados para `docs/results/addendum-dev/`. Restrição da fase 2: nenhum modelo local rodou em
nada disto.

### Registro de esforço

| estratégia | configs avaliadas | passadas no dev | tempo de relógio | chamadas pagas | notas |
|---|---|---|---|---|---|
| E3c Cohere Embed v4 | 324 (grade D1 da fase 1, literal) + 3 (T pelo Brier calibrado) + 1 `study run` final = 328 | 328 (9 textos de consulta distintos × 151 embutidos uma vez; cache de vetores) | ~3 min | ~US$ 0.004 | Script da grade `results/phase2a/emb_grid.sh` = `results/phase2/emb_grid1.sh` com a config trocada. Os prefixos de instrução no estilo Qwen da grade ficam como estão (mesma grade); o Cohere também recebe seu próprio `input_type` (search_query / search_document). |
| E3t Titan v2 | 324 + 3 + 1 = 328 | 328 | ~1.5 min | ~US$ 0.001 | Como o E3c. |
| E10c sonda sobre Cohere | 64 (grade de sonda D4 da fase 1) + 8 (refinamento C × histórico em torno do melhor da grade de 64: C ∈ {0.1, 0.3, 1, 3} × melhor C, outros eixos no melhor da grade de 64) + 1 final + 1 `study run` = 74 | 74 | ~30 s | < US$ 0.001 | O refinamento da fase 1 foi {0.1, 0.3, 1, 3} em torno do melhor C = 1; as mesmas razões são usadas em torno do melhor C deste modelo (100 → {10, 30, 100, 300}). |
| E10t sonda sobre Titan | 64 + 8 (melhor C = 1 → {0.1, 0.3, 1, 3}) + 1 + 1 = 74 | 74 | ~30 s | < US$ 0.001 | Como o E10c. |
| E6m Ministral 3 8B | 1 (só P0; sem busca de prompt) + calibração | 1 (a run no dev do coordenador, cache de respostas) | – | ~US$ 0.07 (run no dev) | Mapas isotônicos (o procedimento de LLM da fase 1, `select_prompts.py`). |
| E6n Nemotron Nano 9B v2 | 1 (P0, `/no_think`) + calibração | 1 | – | ~US$ 0.03 (run no dev) | Como o E6m. |

Tempo humano/de agente: cerca de 1 h de tempo de agente para os seis, quase todo esperando as duas
grades. Nenhuma regra escrita, nenhuma leitura de erros do dev para editar algo: toda escolha é um
argmax de grade ou a regra de calibração pré-declarada.

### Antes → depois (dev, CV de 5 folds)

skill/tool são a config fixa em todo o dev. ECE e Brier leem bruto → calibrado (ajuste cruzado).
p50/p95 são ms por caso (estágio de skill + tool) como gravados no dev, onde as chamadas ao Bedrock
rodaram com concorrência 2 do Mac em São Paulo para `sa-east-1`: **não** é a latência do benchmark
(essa vem só dos blocos `lat-a-*` de `config/addendum_manifest.yaml`).

| roteador | config | skill | tool | conjunta fixa [IC 95%] | conjunta aninhada [IC 95%] | ECE / Brier skill | ECE / Brier tool | mapa escrito | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| E3c Cohere v4 | antes (primeiro ponto da grade: max_example, T 0.02, sem histórico, sem shots, sem instrução) | 62.3 | 47.7 | 47.7 | – | 0.219 (bruto) | 0.353 (bruto) | – | 570 / 1424 |
| E3c Cohere v4 | **depois**: topk_vote k 5, T 0.1, histórico 2, shots, sem instrução | 73.5 | 62.9 | 62.9 [55.0, 70.9] | **59.6 [51.7, 67.5]** | 0.069→0.047 / 0.167→0.169 (Platt) | 0.120→0.050 / 0.224→0.207 (isotônico) | skill + tool | 562 / 1382 |
| E3t Titan v2 | antes (mesmo ponto de base) | 58.9 | 45.0 | 44.4 | – | 0.215 (bruto) | 0.367 (bruto) | – | 138 / 358 |
| E3t Titan v2 | **depois**: centroid, T 0.02, histórico 1, shots, sem instrução | 73.5 | 61.6 | 60.3 [52.3, 68.2] | **60.3 [52.3, 68.2]** | 0.094→0.070 / 0.172→0.172 (isotônico) | 0.225→0.061 / 0.233→0.183 (Platt) | skill + tool | 136 / 226 |
| E10c sonda (Cohere) | **depois**: C 10, shots, descrição, sem instrução, histórico 0 | 68.9 | 60.9 | 57.0 [49.0, 64.9] | **53.6 [45.7, 61.6]** (64 pontos) / 56.3 [48.3, 64.2] (refinamento) | 0.103→0.103 / 0.200→0.192 (isotônico) | 0.230→0.121 / 0.256→0.198 (isotônico) | só tool (ECE de skill 0.1027→0.1028: não é menor) | 568 / 1359 |
| E10t sonda (Titan) | **depois**: C 0.1, shots, descrição, sem instrução, histórico 0 | 70.9 | 62.3 | 60.9 [53.0, 68.2] | **60.9 [53.0, 68.9]** (64 pontos) / 59.0 [51.0, 66.9] (refinamento) | 0.441→0.070 / 0.397→0.179 (isotônico) | 0.440→0.219 / 0.454→0.234 (isotônico) | skill + tool | 135 / 215 |
| E6m Ministral 3 8B | P0, T 0 | 88.7 | 80.8 | 79.5 [72.8, 86.1] (CV); 78.8 [72.2, 85.4] no ITT do `study run` (1 linha de erro, recuperada numa retentativa posterior) | = fixa (um ponto) | 0.093→0.041 / 0.104→0.089 (isotônico) | 0.142→0.029 / 0.170→0.144 (isotônico) | skill + tool | 1008 / 1174 |
| E6n Nemotron Nano 9B v2 | P0, T 0, `/no_think` | 86.8 | 78.8 | 78.1 [71.5, 84.8] | = fixa (um ponto) | 0.061→0.012 / 0.106→0.103 (isotônico) | 0.146→0.092 / 0.177→0.162 (isotônico) | skill + tool | 1553 / 2310 |

Pares locais da fase 1 no mesmo dev (de `docs/tuning-effort.md` e `config/prompt_selection.yaml`):
qwen3-embedding 8B E3 aninhado 77.5, sonda local E10 76.2–76.8, Qwen3-8B E6b 82.2 (CV).

### Roteadores 8B: custo do P0 completo e verificação de falhas de parse (T0.3 / T2.3)

| modelo | tokens de prompt por chamada (média) | tokens de saída por chamada | US$ por 1k casos (skill + tool) | falhas de parse (chamadas) | linhas de erro (ITT, erradas) |
|---|---|---|---|---|---|
| Ministral 3 8B | 1,167 | 79 | 0.449 | 1 / 302 (0.3%) na primeira passada; 0 depois da retentativa | 1 / 151 (0.7%) → 0 |
| Nemotron Nano 9B v2 | 1,340 | 69 | 0.226 | 2 / 302 (0.7%) | 2 / 151 (1.3%) |

Os dois ficam abaixo do limite de 2%, então **nenhuma correção só de formato** foi aplicada. O
prompt P0 real tem cerca de 1.2–1.3k tokens por chamada, não os 2.3k supostos no plano §5: a
estimativa por caso do plano (Ministral 0.00085, Nemotron 0.00035) está cerca de 2× / 1.5× alta,
então o A3 (test-v2 8B ×2, 399 casos) sai por cerca de US$ 0.27 em vez de 0.50.

### O que moveu os números

- **Os embedders gerenciados ficam muito abaixo do qwen3-embedding 8B local nesta tarefa**
  (aninhado 59.6 / 60.3 contra 77.5). A diferença está nos dois estágios e é maior em
  `fora_escopo` no Cohere (13% de conjunta).
- Shots são escolhidos para os dois embedders (como para o qwen3); o histórico ajuda (Cohere 2
  turnos, Titan 1).
- Nenhum prefixo de instrução vence para nenhum dos dois: o prefixo no estilo Qwen
  `Instruct: …\nQuery:` custa 5–15 pontos aos dois modelos. É o esperado (eles não foram
  ajustados a instruções desse jeito); a grade foi mantida idêntica à da fase 1 de propósito.
- O Cohere prefere voto kNN (`topk_vote`, k 5) a centroid, ao contrário do qwen3 e do Titan.
- As sondas não superam o seu próprio roteador por embedding (E10c 53.6–56.3 contra E3c 59.6;
  E10t 59.0–60.9 contra E3t 60.3), ao contrário da sonda local, que igualou o roteador local.
- Os LLMs 8B gerenciados ficam a 3–4 pontos do Qwen3-8B local no dev (79.5 / 78.1 contra 82.2);
  a família A testa essa diferença no test-v2 com margem de NI de 3 pp.

## §B. Catálogo grande (62 tools, 10 skills; dev-L)

### regex (E1-L): regras só a partir do catálogo, antes de qualquer leitura do dev-L (T5.1, parte 1)

`config/regex_rules_l.yaml` foi escrito só a partir do catálogo: descrições das tools, trechos de
WHEN TO USE, exemplos e keywords em `_meta` (`mcp_server/tools_list_large.json`), as regras de
desambiguação dos SKILL.md e a tabela G1–G12 de `docs/catalog-large.md`. **Nenhum arquivo de
dataset foi lido** (o dev-L ainda não existia; nenhum split da fase 1 foi aberto). A rodada de
erros do dev-L vem depois e é registrada numa linha separada.

| passo | o quê | tempo de relógio do agente | humano | passadas no dev | chamadas pagas |
|---|---|---|---|---|---|
| regras do catálogo | base = regras da fase 1 copiadas sem mudança; supressores nas originais; regras para 7 skills novas, 42 tools novas, 2 globais novas; 2 rodadas de correção nas verificações dentro da amostra abaixo | ~0.4 h (2026-10-02 00:13–00:35) | 0 | 0 | 0 (US$ 0) |
| rodada do dev-L | leitura dos 68 erros de conjunta das regras só de catálogo no dev-L (`tune_router.py --split dev_l --errors`), depois 2 lotes de edição + 2 reexecuções da CV; só acréscimos (regras marcadas `dev-L round`) | 2026-10-02 00:39:56–00:43:46 pelos carimbos de `date` (tempo de agente) | 0 | 4 (2 pontos cada, histórico 0/2) | 0 (US$ 0) |

Timebox (plano §3, risco R1): 4 h para todo o esforço de regex. Usado até aqui: ~0.4 h, então
restam ~3.6 h para a rodada de erros do dev-L; o R1 permite mais uma rodada registrada de 2 h
depois da CV do dev-L e nada além disso.

**Contagem de regras** (padrões; um padrão pode ser uma alternância):

| | ids de opção | regras | das quais supressores (< 0) | defs |
|---|---|---|---|---|
| fase 1 (`regex_rules.yaml`, 18 tools) | 22 | 79 | 7 | 30 |
| grande (`regex_rules_l.yaml`, 62 tools) | 73 (10 skills + `__global__` + 62 tools) | 235 (91 no estágio de skill, 144 no de tool) | 64 | 46 |
| – herdadas da fase 1, sem mudança | 22 | 79 | 7 | 30 (OFF_SCOPE editado, ver abaixo) |
| – acrescentadas aos 22 ids originais | | 43 | 39 | |
| – ids novos (7 skills, 42 tools, 2 globais) | 51 | 113 | 18 | 16 novas |

Arquivo: 478 linhas (fase 1: 181).

**Decisões.**

- *As regras positivas originais não foram tocadas.* As 79 regras da fase 1 são idênticas byte a
  byte. Nos ids originais acrescentei só supressores (G1–G12), as duas regras das globais novas em
  `__global__` (mudança de contato, protocolo) e uma regra de escalate_to_human ("esqueci a senha
  / não consigo entrar", o exemplo que a camada do perfil grande acrescenta). Nos 71 exemplos do
  catálogo compartilhados com a fase 1, as regras do perfil grande roteiam exatamente o mesmo
  conjunto que as regras da fase 1 roteiam no catálogo pequeno (54/71 contra 55/72; **0
  regressões, 0 ganhos**). Isso mantém as tools originais comparáveis entre catálogos. Os erros que
  sobram nas tools originais são erros da fase 1, deixados para a rodada do dev-L.
- *OFF_SCOPE editado.* "nota fiscal" e "preços" estão no escopo do catálogo grande
  (`docs/catalog-large.md` §3), então foram retirados, e "senha|login|atacado|estoque" foram
  acrescentados (descrição de escalate_to_human no perfil grande).
- *Os supressores carregam as regras G1–G12 no estágio de skill.* O estágio de tool só oferece as
  tools de uma skill + as 5 globais, então um grupo entre skills é decidido no estágio de skill. O
  "marcador de domínio" de cada grupo é um def (CARD, SUB, TECH, SELLER, INVOICE, RECEIPT, PROMO,
  PRICE_DROP, LOYALTY, DEBT, CONTACT, PROTOCOL). A skill original que divide o gatilho recebe um
  supressor (-0.6 ou -1.0) nesse marcador: por exemplo pedidos_logistica −1.0 em SUB/TECH (G4,
  G5), pagamentos_reembolsos −1.0 em CARD/SELLER (G1, G2) e em cashback/pontos (G3),
  trocas_devolucoes −1.0 em TECH (G7) e em CNPJ/"nota de devolução"/recusa do vendedor (G10). As
  tools originais recebem os mesmos supressores no estágio de tool (por exemplo cancel_order,
  dispute_charge, track_shipment), caso uma skill roteada errado as ofereça.
- *Seguir as regras dos SKILL.md ao pé da letra onde são assimétricas.* G10: uma devolução simples
  de produto de vendedor parceiro continua create_return_request (marketplace −0.6 em "devolver",
  a menos que haja "recusou"); só uma recusa vai para open_seller_mediation. G7: "ainda está na
  garantia?" continua check_return_eligibility; "até quando vai a garantia" / "garantia estendida"
  vai para check_extended_warranty.
- *Tokens no formato do catálogo.* Códigos de cupom (`[a-z]{3,}\d{2,3}`, por exemplo CASA50) e de
  vale-presente (`presente-…`) são marcadores PROMO; "nota 5" fica fora do marcador INVOICE
  (rate_seller). Bens de assinatura citados no catálogo (ração, fraldas, cápsulas, refil) são uma
  dica de 0.6.

**Verificações dentro da amostra (frases do catálogo; as regras foram escritas contra elas, então
são um piso de cobertura, não uma estimativa de acurácia).** Ponta a ponta = estágio de skill sobre
11 opções, depois estágio de tool sobre as tools da skill + 5 globais; empate ou nenhum match é
erro.

| verificação | acertos |
|---|---|
| exemplos de `_meta`, todas as 62 tools (248) | 231 (93.1%); toda tool ≥ 2/4 |
| – as 44 tools novas (176) | 176 (100%) |
| – as 18 tools originais (72) | 55 (76.4%) = regras da fase 1 no catálogo pequeno |
| trechos de WHEN TO USE (121) | 118 (97.5%); os 3 erros são tools originais |
| exemplos do frontmatter dos SKILL.md, estágio de skill (50) | 50 (100%) |
| sondas G1–G12 escritas a partir das regras dos SKILL.md (34) | 34 (100%) |

Por skill (exemplos de `_meta`): assinaturas, assistencia_tecnica, cartao_loja_crediario,
fidelidade_cashback, marketplace_vendedores, notas_fiscais_cadastro e promocoes_precos 24/24
cada; `__global__` 19/20; trocas_devolucoes 16/20; pagamentos_reembolsos 15/20;
pedidos_logistica 13/20.

Espere uma queda grande no dev-L: o regex da fase 1 perdeu 32 pp do dev para o teste, e estas
regras não viram nenhuma frase de usuário. Testes: `tests/routers/test_regex_rules_l.py` (≥ 2
exemplos por tool, os testes de frases da fase 1 nos conjuntos de opções grandes, uma sonda por
tool de G1–G12).

#### Rodada do dev-L (T5.1 parte 2): o que mudou e o que rendeu

A rodada leu os erros do dev-L uma vez, então o seu número de CV é otimista, como a linha do regex
da fase 1: a CV só reescolhe `history_turns`, e as regras foram escritas nos mesmos casos.

- Regras 235 → 298 (supressores 64 → 93), defs 46 → 48 (`INJECT`: injeção de prompt / ação em
  massa → `__global__` + escalate_to_human; `NO_REPLY`: "aguardo retorno" não é devolução).
  Arquivo 478 → 554 linhas. As 79 regras positivas da fase 1 continuam idênticas byte a byte.
- Marcadores de catálogo ampliados: prefixos de id de entidade do contrato do mock DB grande
  (ASS-, OS-, VALE-, prefixos de protocolo ATD/NFC/MED/AJC/CCL; códigos de promoção), "cartão de
  vocês / fatura do cartão / TX-…" → cartão da loja, "comprova…/comprobatório" → comprovante,
  "documento fiscal", "pontinhos/patente/bonificação" → fidelidade, "terceiro/de quem estou
  comprando/lojão" → vendedor, fora de escopo "parceria/seguidores/representação
  comercial/revenda/emprego".
- Correções no estágio de tool em tools novas (bloquear × contestar, saldo × resgate de
  vale-presente, reagendar visita técnica, etiqueta de devolução "adesivo", reenvio de nota
  "retransmissão", denúncia × contato com vendedor, pausa "congelar").

| | skill | tool | conjunta (fixa = aninhada aqui) [IC 95%] | ECE skill bruto→cal | ECE tool bruto→cal |
|---|---|---|---|---|---|
| regras só do catálogo | 69.3 | 58.0 | 54.7 [46.7, 62.7] | 0.115 | 0.229 |
| depois da rodada do dev-L | 89.3 | 83.3 | **82.7 [76.7, 88.7]** (otimista) | 0.110→0.058 (Platt) | 0.214→0.082 (Platt) |

Os erros que sobram são quase todos multiturno ("e o outro?") e ambiguo; por categoria depois da
rodada: direto 86.7, parafrase 81.1, ambiguo 66.7, multiturno 53.3, fora_escopo 86.7,
adversarial 75.0 (conjunta, primeiro lote de edição). Timebox usado: ~0.5 h do orçamento de
4 h (+2 h).

### Outras estratégias no dev-L (T5.1–T5.3)

Embedder: **Titan v2** para E3-L/E10-L/E11-L, pela recomendação da Parte A (a CV no dev empata
com o Cohere dentro do ruído, ~4× mais rápido, ~6× mais barato); nenhum modelo local. Logs e JSON
por ponto: `results/phase2l/` (no gitignore); os scripts das grades estão lá (`bm25_grid.sh`,
`emb_grid.sh`, `emb_T.sh`, `probe.sh`, `llm_p0.sh`). Blocos ajustados:
`docs/results/phase2-dev-l/tuned_blocks.yaml`, aplicados com
`scripts/analysis/apply_tuned_l.py`. Mapas escritos só quando o ECE com ajuste cruzado é menor
que o bruto.

| estratégia | configs avaliadas (passadas no dev-L) | tempo de relógio | pago | conjunta aninhada [IC 95%] | conjunta fixa | ECE skill bruto→cal | ECE tool bruto→cal | mapa | p50 / p95 ms | US$/1k casos |
|---|---|---|---|---|---|---|---|---|---|---|
| E2 BM25 grade 1 | 512 | 4.5 min | 0 | 50.0 [42.0, 58.0] | 54.7 | – | – | – | 8 / 17 | 0 |
| E2 BM25 grade 2 (em torno do melhor da grade 1: char, shots, sem aspas, okapi) | 432 | ~1.5 h (o host dormiu) | 0 | **52.7 [44.7, 60.7]** | 56.0 | 0.511→0.065 (Platt) | 0.346→0.106 (Platt) | skill + tool | 19 / 37 | 0 |
| E11 híbrido, convexo (7 conjuntos de membros × 11 alphas) | 77 | ~40 min | embeddings em cache | **81.3 [75.3, 87.3]**: regex + classificador, alpha 0.5 (igual à fase 1) | 82.7 | 0.112→0.040 (Platt) | 0.116→0.042 (isotônico) | skill + tool | – | ≈0.003 |
| E11 stacker logístico (regex, bm25, embedding; `fit_hybrid.py`) | 3 valores de L2, CV interna | ~2 min | em cache | 80.0 ± 8.7 (abaixo do convexo: não usado) | – | – | – | – | – | – |
| E3 embedding Titan | 324 (grade D1 literal) + 3 (T pelo Brier calibrado: T 0.02) | ~2 min + 1 min | ~US$ 0.002 | 61.3 [53.3, 69.3] | 64.7 | 0.083→0.118 | 0.186→0.133 (isotônico) | só tool | 161 / 250 | ≈0.003 |
| E10 sonda sobre Titan | 64 (grade D4) + 8 (C {100,300,1000,3000} × histórico) | ~1 min | < US$ 0.001 | 66.0 [58.0, 73.3] (as duas) | 66.7 | 0.060→0.090 | 0.115→0.085 (isotônico) | só tool | 176 / 395 | ≈0.003 |
| E6 Haiku 4.5, P0 | 1 | ~4 min | US$ 1.08 | 84.0 [78.0, 89.3] | 84.0 | 0.065→0.038 | 0.070→0.106 | só skill | 3651 / 4870 | 7.18 |
| E6m Ministral 3 8B, P0 | 1 | ~3 min | US$ 0.10 | 78.7 [72.0, 84.7] | 78.7 | 0.145→0.076 | 0.148→0.059 | skill + tool | 841 / 1341 | 0.70 |
| E6n Nemotron Nano 9B v2, P0 | 1 | ~3 min | US$ 0.05 | 73.3 [66.0, 80.0] | 73.3 | 0.156→0.101 | 0.199→0.022 | skill + tool | 1397 / 1936 | 0.33 |
| E4 Jev, P0 | 1 | ~4 min | US$ 0.19 (OR) | 86.7 [80.7, 92.0] | 86.7 | 0.057→0.029 | 0.023→0.047 | só skill | 3620 / 7629 | 1.28 |
| Sonnet 5 P0 (só shadow, OQ-1) | 1 | ~4 min | US$ 1.13 | 84.0 [78.0, 89.3] | 84.0 | 0.123→0.022 | 0.047→0.037 | skill + tool | 5840 / 10058 | 7.52 |

- **Falhas de parse:** Ministral 2/300 chamadas (2 linhas, 1.3% ITT), Jev 1, Sonnet 1, Haiku e
  Nemotron 0: todos os modelos abaixo de 2%, então **nenhuma correção só de formato**.
- **Cache do Haiku (X3):** 0 leituras de cache: o prompt P0 grande tem ~2.7k tokens por chamada,
  abaixo do mínimo de cache do Haiku de 4,096 tokens. O Sonnet (mínimo de 1,024) lê ~2.6k tokens
  em cache por chamada.
- p50/p95 são latências de ajuste no dev-L com concorrência 2–4, **não** o benchmark.

- **Adiamento aprendido** (`fit_hybrid.py`, estágio de skill, P(regex certo)): AUROC na CV de 0.654
  para o aprendido contra 0.732 para a própria confiança calibrada do regex; como na fase 1, fica a
  porta de confiança única.

### Limiares das cascatas (T5.4)

Shadow no dev-L `freeze-dev-l-shadow-r1` (`config/freeze_dev_l_manifest.yaml`, E9-L decidindo,
conjunto shadow regex/bm25/embedding/llm(Sonnet)/jev/hybrid/classifier, Sonnet com 1 rep só no
dev-L, conforme OQ-1): 150/150, 0 erros; as chamadas de Sonnet e Jev foram acertos do cache de
respostas das passadas do T5.3 e de um shadow de aquecimento com os mesmos blocos de roteamento do
E9-L. Regra (a) do prereg-v1 §4: conjunta máxima sujeita a custo de roteamento ≤ 0.5 × o custo
por caso do Sonnet P0 no dev-L (7.522/1k → **US$ 0.003761/caso**), grade 0.50..0.99, ajuste
cruzado de 5 folds. Relatórios: `docs/results/phase2-dev-l/cascade-thresholds-dev-l.md`.

| cascata | limiares (regra (a)) | conjunta dev | conjunta CV separada [IC 95%] | US$/1k roteamento CV | cobertura do estágio de skill por passo (dev) |
|---|---|---|---|---|---|
| E7-L regex → Jev | regex 0.88 | 86.7 | 86.0 [80.0, 91.3] | 1.04 | regex 105/150 (70%), Jev 45 |
| E8-L regex → Sonnet | orçamento inviável → fallback da fase 1, (a) sem restrição: regex 0.88 | 83.3 | 83.3 [77.3, 88.7] | 6.40 | – |
| E9-L regex → Jev → Sonnet | regex 0.88, Jev 0.76 / tool Jev 0.50 | 86.7 | **86.0 [80.0, 91.3]** | 1.06 | regex 105 (70%), Jev 45, Sonnet 0 |
| E12-L híbrido → Jev → Sonnet | híbrido 0.78, Jev 0.76 / tool Jev 0.50 | 84.0 | 82.7 [76.0, 88.7] | 1.07 | híbrido 118 (79%), Jev 32 |

Referências (E9-L, dev): sempre Sonnet 80.0 a US$ 8.82/1k; sempre o primeiro 80.0; oráculo 88.7;
adiamento aleatório nas mesmas taxas 80.3. Os limiares do E9-L são iguais aos da fase 1.

### Validação e2e (T5.5)

`config/dev_l_e2e_manifest.yaml`: E0-L e E9-L nos mesmos 40 casos estratificados do dev-L
(`config/manifest/dev_l_e2e_validation_40.ids`), executor Sonnet 5, 1 rep. As duas runs COMPLETE,
0 linhas de erro; toda linha tem um score simétrico (nenhum `None`), 0 chamadas a tools
desconhecidas.

| braço | e2e legacy [IC 95%] | e2e sym [IC 95%] | skill (legacy / sym) | US$/turno faturado | US$/turno do estudo | resolved_by |
|---|---|---|---|---|---|---|
| E0-L nativo | 60.0 [45.0, 75.0] | 65.0 [50.0, 80.0] | 87.5 / 80.0 | 0.0139 | 0.0139 | nativo 40 |
| E9-L | 57.5 [42.5, 72.5] | 60.0 [45.0, 75.0] | 92.5 / 77.5 | 0.0165 | 0.0178 | regex 28, Jev 12 |

- **Correção de scorer encontrada aqui** (09c1d12): `rescore_file` pontuava linhas dos splits
  grandes contra o `tools_list.json` de 18 tools, então toda chamada a uma tool nova era uma tool
  desconhecida; o E0-L lia 22.5% no legacy. O snapshot padrão agora é por split
  (`dev_l`/`test_l` → `tools_list_large.json`).
- **Custo por turno, medido** (substitui o multiplicador ×1.25 do plano §5): E0-L 0.0139 (plano
  0.0113; o smoke de 0.029 eram escritas de cache em 5 turnos), E9-L 0.0165 faturado (plano
  0.0090). Para o test-L (300): B13 E0-L ≈ US$ 4.2 (plano 3.39), B14 E9-L ≈ US$ 5.0 (plano 2.69),
  B15 ≈ 5.0, B16 (60+60) ≈ 1.8.
- O guarda de orçamento do `study run` recusou o E9-L pelo seu limite a priori (US$ 3.11 > 2.95
  restantes); o manifesto rodou primeiro um lote de 10 casos, depois o resto pelo custo medido
  (US$ 0.67 projetados).
- O 10º caso do primeiro lote travou durante uma suspensão do host; a run foi morta e retomada por
  (caso, rep) pelo manifesto de 40 ids: nenhuma linha de erro de infra ficou.
