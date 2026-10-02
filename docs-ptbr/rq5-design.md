# RQ5 — custo de manutenção de adicionar uma tool (desenho leave-tools-out)

Responde à RQ5 / à métrica "Esforço" de `docs/projeto.md` ("linhas de config e horas para
adicionar uma tool nova") e fecha o ponto M2 da revisão de metodologia (`.omc/reviews/methodology-final.md`).
Item do plano: D7 de `.omc/plans/final-study-master.md`. Status: **exploratório** (não é uma das
hipóteses pré-registradas H1–H3 / S1–S4, a menos que seja promovida no pré-registro).

## Tools retidas (held-out)

Uma por skill, incluindo o membro mais confundível de cada par:

| Tool | Skill | Por quê | casos dev | casos test-v2 |
| --- | --- | --- | --- | --- |
| `get_refund_status` | pagamentos_reembolsos | confundível com `request_refund` / `get_payment_status` (mesmo vocabulário: reembolso, estorno, caiu) | 9 (6 multi-rótulo com `get_payment_status`) | 22 (9 multi-rótulo) |
| `reschedule_delivery` | pedidos_logistica | confundível com `update_delivery_address` / `track_shipment` (vocabulário de prazo de entrega) | 10 | 13 |
| `generate_return_label` | trocas_devolucoes | confundível com `create_return_request` (mesmo episódio de devolução) | 7 | 13 |

As contagens são feitas apenas pelo rótulo gold (`expected.acceptable_tools`). Nenhuma alternativa foi necessária: cada skill
tem uma tool retida com ≥7 casos dev e ≥13 casos test-v2.

## Mecanismo (nada muda no servidor MCP)

1. **Filtro de catálogo em runtime** — settings `catalog.exclude_tools: [...]`, aplicado em
   `routing_study/catalog.py` (`fetch_catalog` → `Catalog.without`) depois do fetch do servidor e
   depois da checagem de consistência de `allowed-tools` do SKILL.md. Ele remove as tools de `tools/list`,
   e os exemplos do frontmatter da skill que são cópias literais dos exemplos `_meta` de uma tool excluída.
   Tudo o que deriva do catálogo acompanha automaticamente: os
   `RouteOption`s de skill/tool, os shots de skill (round-robin sobre as tools restantes), as cláusulas DON'T USE FOR
   que apontavam para uma tool excluída (descartadas, já que `avoid_clauses` mantém só tools conhecidas),
   os schemas de tools do executor e o `catalog_hash`. A chave de cache do Redis carrega a exclusão,
   então um catálogo reduzido nunca sobrescreve o completo.
2. **Overlay de regex** — `strategies.regex.overlay_paths: [...]` mescla arquivos de regras extras sobre
   `rules_path` (os `defs` do overlay são anexados depois dos defs base; as regras do overlay são anexadas por id
   de opção). O `config_hash` cobre os bytes do overlay e a exclusão do catálogo.
   - `config/rq5/regex_rules_base.yaml`: as regras de produção **menos tudo o que existe
     por causa das tools retidas**: suas três listas de regras do estágio de tool, as regras do estágio de skill
     cujo vocabulário é específico delas (`{{RESCHEDULE}}` → pedidos_logistica, `{{LABEL}}`
     e `post(ar|agem)` → trocas_devolucoes) e os defs `RESCHEDULE` / `LABEL`.
     `get_refund_status` não tem regra própria no estágio de skill (seu vocabulário, `{{REFUND}}`, é
     compartilhado com `request_refund`).
   - `config/rq5/regex_overlay_original.yaml`: exatamente as regras removidas. Um teste unitário verifica
     que base + este overlay é igual ao `config/regex_rules.yaml` de produção (mesmas regras
     expandidas por opção), para que a divisão não possa divergir silenciosamente.
   - `config/rq5/regex_overlay_engineered.yaml`: regras novas para as três tools, escritas pelo
     engenheiro sob um timebox (ver abaixo).
3. **Overrides do manifest** — uma entrada do manifest pode carregar `overrides: {dotted.key: value}` aplicados
   sobre o YAML do seu experimento (mesmo mecanismo dos patches de env `ROUTING__…`), de modo que um único arquivo
   de config sirva a todas as condições e o version guard faça o hash das settings já com o patch.

## Condições (por estratégia)

| Condição | Catálogo | Regras de regex | O que mede |
| --- | --- | --- | --- |
| **base** | 3 tools excluídas | `regex_rules_base.yaml` | o estado "antes"; o que acontece com os casos das tools retidas quando a tool não existe |
| **zero** (adição com esforço zero) | completo | `regex_rules_base.yaml` (o regex **não** ganha nada novo) | adicionar a tool só com a descrição de catálogo + exemplos/keywords `_meta`; BM25 / embedding / classifier / LLM / Jev reindexam ou refazem o prompt a partir do catálogo |
| **eng** (adição com engenharia) | completo | base + `regex_overlay_engineered.yaml` | adicionar a tool mais regras de regex com timebox; as outras estratégias não precisam de trabalho extra, então para elas eng ≡ zero |
| **full** (referência, só regex e híbrido) | completo | regras de produção | o estado atual: regras escritas ao longo de muitas iterações, com acesso ao dev (e, para alguns supressores, depois de o test-v1 ter sido lido — B1) |

Para BM25, embedding, classifier, LLM e Jev, eng e zero são a mesma rodada (não há esforço extra
possível sem mudar o catálogo, e o texto do catálogo é a entrada de esforço zero). O híbrido
(regex + classifier, fusão convexa) roda nas quatro condições porque seu membro regex
muda.

### Condição do engenheiro: notas de transparência

- O engenheiro é um **agente de IA** (Claude, a mesma sessão que implementou o harness), não
  um humano. Linhas e docs o rotulam como "agent-written rules, timeboxed".
- Entradas permitidas: as entradas de catálogo das três tools (descrição, WHEN TO USE, exemplos `_meta`
  e keywords), os playbooks do SKILL.md e as regras / defs base existentes. **Não permitido**:
  mensagens de dev ou de teste. As regras, portanto, não são ajustadas no dev, e os números de dev da
  condição eng são uma estimativa held-out para elas.
- Declaração de contaminação: o agente leu as regras de produção originais dessas tools enquanto
  construía a divisão base/original, antes de escrever as engenheiradas. As regras engenheiradas podem
  ter sido influenciadas por elas; isso enviesa eng em direção a full (otimista para o regex).
- Esforço registrado no cabeçalho do overlay: minutos de relógio (timestamps de início/fim), timebox,
  linhas que não são comentário, regras e defs.

## Métricas (por estratégia × condição)

Conjuntos de casos, só a partir dos rótulos gold (H = as 3 tools retidas):

- **affected**: `acceptable_tools ∩ H ≠ ∅` (dev 26, test-v2 48). Casos multi-rótulo cuja outra
  tool aceitável continua existindo (ex.: `get_payment_status`) ainda podem acertar em base.
- **other**: todos os casos restantes.

Reportado:

- acurácia conjunta / de skill / de tool nos affected (base, zero, eng, full) — o número principal da RQ5 é
  a conjunta nos affected, zero vs eng vs base;
- `pred∈H`: fração dos casos affected cuja tool prevista é uma tool retida (recall da nova
  tool, agnóstico a multi-rótulo);
- regressões nos casos other, relativas a base: `lost` = conjunta correta em base e errada depois
  da adição, `won` = o inverso, Δ líquido da conjunta (pp); mais `stolen` = casos other roteados para uma
  tool retida depois da adição (falsos positivos da nova tool);
- esforço: autoria do catálogo (linhas de descrição + exemplos `_meta` + keywords das 3 tools,
  comum a todas as estratégias), linhas / regras / defs / minutos de regex (eng), segundos de re-treino
  (construção do índice BM25, fit do classifier, embedding dos textos das novas opções com cache
  de vetores frio; LLM/Jev: 0 s — o prompt é reconstruído a partir do catálogo).

Linhas de erro (falhas de infraestrutura) contam como erradas (ITT), como em todo o estudo.

## Rodadas

`study rq5` monta a tabela a partir das linhas reavaliadas do manifest (`--manifest`, nomes de rodada
`rq5-<split>-<strategy>-<condition>`) e, com `--retrain`, mede os segundos de re-treino.

- **dev, grátis** (`config/rq5_dev_manifest.yaml`): regex, bm25, embedding, classifier, hybrid ×
  base / zero / eng (+ full para regex/hybrid); todos os 151 casos dev. Esta é a validação
  end-to-end do harness.
- **test-v2, grátis** (em `config/study_manifest.yaml`, seção 10): a mesma matriz em todos os 349
  casos test-v2.
- **test-v2, pago** (seção 10): Jev, Haiku 4.5 e Sonnet (trilha de prompt canônica: só o texto
  do catálogo, sem few-shots ajustados que possam codificar esforço específico da tool), routing-only, 1 rep,
  base e zero, nos 48 casos affected do test-v2 + uma amostra de regressão estratificada de 60 casos
  dos casos other (`config/manifest/rq5_test_v2.ids`, 108 ids, gerada por
  `scripts/analysis/rq5_ids.py` só a partir de ids/categorias/rótulos). As entradas zero reutilizam o
  cache de respostas da rep 1 das rodadas canônicas principais (mesmo caso, rep e prompt) e custam ~0
  quando essas rodam antes.

## Limitações

- As descrições das skills e os corpos dos SKILL.md ainda mencionam a capacidade retida em base (só
  os exemplos duplicados literalmente são removidos). A acurácia de skill em base nos casos affected é, portanto,
  um pouco otimista; isso subestima o ganho da adição no nível da skill.
- Os mapas de calibração do regex e os pesos de fusão do híbrido foram ajustados no dev com as regras completas; eles
  não são reajustados por condição (a acurácia no modo single não depende deles).
- 3 tools, um engenheiro (um agente de IA), um timebox: um estudo de caso de custo de manutenção, não uma
  estimativa populacional.

## Validação no dev (estratégias grátis, 2026-09-30)

`uv run study run-manifest config/rq5_dev_manifest.yaml` e depois
`uv run study rq5 config/rq5_dev_manifest.yaml --retrain config/experiments/e10_classifier.yaml`
(o Langfuse estava inacessível, então as rodadas usaram `LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY=`;
o tracing não afeta as linhas). 151 casos dev por rodada, 0 erros. O dev é onde as regras de regex de
produção (`full`), a fusão do híbrido e os hiperparâmetros de todo roteador grátis foram ajustados, então
`full` e os níveis absolutos são otimistas aqui; o overlay engenheirado NÃO foi ajustado no dev.

Retidas: `get_refund_status`, `reschedule_delivery`, `generate_return_label`. affected = casos com uma tool retida entre as tools aceitáveis; other = o restante. Δ other / lost / won são pareados com `base` (conjunta, casos other); stolen = casos other roteados para uma tool retida. Erros contam como errados (ITT).

| strategy | cond | n aff | joint aff | skill aff | pred∈H aff | n other | joint other | lost | won | Δ other (pp) | stolen | errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | base | 26 | 3.8 | 80.8 | 0.0 | 125 | 56.0 | – | – | – | 0 | 0 |
| bm25 | zero | 26 | 61.5 | 88.5 | 61.5 | 125 | 54.4 | 4 | 2 | -1.6 | 6 | 0 |
| classifier | base | 26 | 15.4 | 80.8 | 0.0 | 125 | 77.6 | – | – | – | 0 | 0 |
| classifier | zero | 26 | 80.8 | 88.5 | 65.4 | 125 | 76.8 | 3 | 2 | -0.8 | 3 | 0 |
| embedding | base | 26 | 15.4 | 88.5 | 0.0 | 125 | 76.8 | – | – | – | 0 | 0 |
| embedding | zero | 26 | 88.5 | 96.2 | 76.9 | 125 | 76.8 | 2 | 2 | +0.0 | 2 | 0 |
| hybrid | base | 26 | 15.4 | 84.6 | 0.0 | 125 | 84.8 | – | – | – | 0 | 0 |
| hybrid | zero | 26 | 65.4 | 88.5 | 50.0 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| hybrid | eng | 26 | 84.6 | 96.2 | 69.2 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| hybrid | full | 26 | 88.5 | 96.2 | 73.1 | 125 | 84.8 | 2 | 2 | +0.0 | 1 | 0 |
| regex | base | 26 | 15.4 | 88.5 | 0.0 | 125 | 84.0 | – | – | – | 0 | 0 |
| regex | zero | 26 | 15.4 | 88.5 | 0.0 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |
| regex | eng | 26 | 76.9 | 96.2 | 61.5 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |
| regex | full | 26 | 88.5 | 96.2 | 73.1 | 125 | 84.0 | 0 | 0 | +0.0 | 0 | 0 |

### Esforço de adicionar as 3 tools

- Entrada de catálogo (input de toda estratégia, a adição com esforço zero): 18 linhas de descrição, 12 exemplos, 15 keywords.
- Regex, engenheirado (`eng`): 30 linhas, 17 regras, 5 defs, 1.2 min de relógio (timebox de 20 min; agente de IA (Claude Opus): regras escritas pelo agente, com timebox; não é um engenheiro humano).
- Regex, produção (`full`, referência): 17 linhas, 8 regras, 2 defs; minutos não registrados (iterado no dev).
- Regex, esforço zero: nada novo (a tool é inalcançável pelo regex).
- Re-treino após a adição (s): índice BM25 0.009, fit do classifier 0.087, embedding de 15 novos textos de opção (frio) 4.29; híbrido = fit do classifier + regex (0); LLM/Jev 0 (prompt reconstruído a partir do catálogo).

Leitura (dev, exploratória):

- Sem a tool, toda estratégia só acerta os casos affected por meio de um segundo
  rótulo aceitável (4/26 casos multi-rótulo de reembolso/pagamento; BM25 1/26).
- Adição com esforço zero: os roteadores guiados pelo catálogo recuperam a maior parte dos casos affected (embedding
  88.5, classifier 80.8, BM25 61.5) sem regressão mensurável nos outros 125 casos
  (Δ −1.6 a 0 pp; 2–6 casos roubados pelas novas tools). O regex fica no nível de base: as novas
  tools são inalcançáveis.
- Adição com engenharia: 17 regras escritas pelo agente (1.2 minuto-agente, entradas só do catálogo) levam o regex
  de 15.4 para 76.9 de conjunta nos casos affected, com zero regressões; as regras de produção
  (`full`, escritas no dev ao longo de muitas iterações) chegam a 88.5. O híbrido acompanha seu membro regex
  (65.4 zero → 84.6 eng → 88.5 full).
- O custo de re-treino é desprezível para todo roteador guiado pelo catálogo (BM25 9 ms, fit do classifier
  87 ms, 4.3 s para embedar os 15 novos textos de opção a frio no qwen3-embedding:8b local).

## Estimativa paga (test-v2, 108 casos × 1 rep por rodada)

| rodada | `study estimate` | $/1k medido no dev → esta rodada |
| --- | --- | --- |
| rq5-test_v2-jev-base | $0.00 (sem preço de tabela para `typesafe/jev-router`) | $0.93 → $0.10 |
| rq5-test_v2-haiku-base | $0.37 (medido) / $0.28 (a priori) | $5.32 → $0.57 |
| rq5-test_v2-sonnet-base | $0.56 (a priori) | $5.97 → $0.64 |
| três rodadas `*-zero` | cache hits da rep 1 das rodadas canônicas principais | ~$0 (pior caso, rodando primeiro: igual a base) |

Esperado ≈ US$1.3; pior caso (rodadas zero sem cache) ≈ US$2.6, dentro do teto de US$3. O
limite a priori assume 900 tokens de prompt por chamada de roteamento; os prompts medidos têm ~1.1–2.2k
tokens, então a coluna medida no dev é a realista.
