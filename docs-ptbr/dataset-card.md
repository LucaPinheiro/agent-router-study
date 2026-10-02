# Dataset card: benchmark de routing (test-v1, test-v2)

## Splits

| Split | Arquivo | n | Papel |
| --- | --- | --- | --- |
| dev | `data/dataset_dev.jsonl` | 151 | somente tuning (regex, exemplos, thresholds, prompts) |
| test-v1 (exposto) | `data/dataset_test.jsonl` | 349 | lido uma vez antes de os routers serem re-tunados (revisão de metodologia B1); replicação e checagem de contaminação apenas com os routers gratuitos |
| **test-v2** | `data/dataset_test_v2.jsonl` | 349 | **o único split confirmatório** |

O test-v2 existe porque o test-v1 foi exposto (B1, opção A). Ele foi gerado depois que todos os artefatos
de tuning foram escritos, por um modelo não-Claude, apenas a partir das specs do gerador: nenhum texto de test-v1 ou de dev
foi mostrado ao gerador. test-v1 e dev foram usados somente como referências de dedupe.

## Autoria dos casos "seed" (revisão M3)

`data/seed.jsonl` (104 casos, 66 deles em test-v1) foi escrito pelo **Claude Opus 5.5
(Anthropic)**, atuando como agente de código: o commit `fd2c218` ("feat(data): add 104 hand-written
seed cases", 2026-09-29) carrega o trailer `Co-Authored-By: Claude Opus 5.5`, e
`data/README.md` afirma que nenhum humano os escreveu ou revisou. O seed é, portanto,
**texto da família Claude**, a mesma família dos routers Sonnet e Haiku. Isso viola a regra
"gerado por um modelo de família diferente da do router" para test-v1 e dev; toda
acurácia de test-v1 deve ser reportada estratificada por `source`. O test-v2 **não tem casos seed**: todos os
349 são `source: "synthetic_v2"`, escritos por `google/gemini-2.5-flash`.

## Geração do test-v2

`scripts/dataset/generate_v2.py` (metadados: `data/generation_meta_v2.json`; log de rejeição por item:
`data/audit/generation_v2_log.jsonl`).

- Gerador: `google/gemini-2.5-flash` via OpenRouter, temperatura 0.9, reasoning effort low,
  os mesmos templates de prompt, filtros de rótulo e regras de argumentos do test-v1
  (`scripts/dataset/generate.py`), **nova seed 20260930** (test-v1: 20260929).
- Cotas por categoria idênticas às do test-v1: direto 105, parafrase 87, ambiguo 70, multiturno 35,
  fora_escopo 35, adversarial 17.
- Estratificação por tool: direto/parafrase/multiturno têm cota por tool (os restos rotacionam
  sobre uma ordem embaralhada de tools), de modo que toda tool tem 12 ou 13 casos single-label; ambiguo é dividido
  igualmente entre os 8 grupos confundíveis (9 ou 8), fora_escopo entre os 5 tópicos (7 cada),
  adversarial entre os 4 tipos de ataque (5/4/4/4).
- Consistência com o mock DB: o cliente de cada item e os ids de pedido oferecidos ao gerador são sorteados
  entre pedidos cujo estado (arquétipo de `mcp_server/MOCK_DB_NOTES.md`, `compatible_tools`) permite que
  a tool alvo seja concluída (para ambiguo: a primeira tool do grupo). Mencionar qualquer outro id de pedido
  rejeita o item. Os ids de pedido sempre pertencem ao cliente do caso.
- Rótulos: `acceptable_skills` derivado de `acceptable_tools`; os conjuntos de rótulos de ambiguo vêm da
  spec do grupo; fora_escopo é `__abstain__` (opcionalmente `escalate_to_human`); args usam apenas nomes reais
  de parâmetros de uma tool aceitável (`mcp_server/tools_list.json`). Política adversarial
  (`data/README.md`): `tool_by_name` aceita primeiro a tool nomeada, mantendo os rótulos do gerador
  como alternativas; um item `decoy` não pode aceitar a tool nomeada; injection e abuse são
  `__abstain__`/`escalate_to_human`.
- Dedupe e vazamento, com todos os slots rejeitados regenerados:
  - texto normalizado exato, ou razão de `SequenceMatcher` >= 0.9, contra todos os 500 casos existentes
    (seed + synthetic = dev + test-v1);
  - o mesmo contra toda unidade de texto do catálogo visível ao router (títulos de tools, descrições e
    exemplos `_meta` em `tools_list.json`, os três `SKILL.md`, o `instructions.md` do servidor,
    os fragmentos de prompt do router), comparado por turno do usuário;
  - cosseno semântico >= 0.9 com o embedder local `qwen3-embedding:8b-q8_0` (Ollama, via o
    `EmbeddingsClient` do projeto) contra os mesmos dois conjuntos de referência;
  - `SequenceMatcher` > 0.85 dentro do test-v2 (como no test-v1).
- Todo caso: `source: "synthetic_v2"`, `reviewed: false`.

## Auditoria cega de rótulos (revisão B2)

`scripts/dataset/audit.py`. Dois modelos auditores de duas famílias diferentes, nenhum Claude
(família dos routers) nem Google (família do gerador), ambos via OpenRouter:

- **A: `openai/gpt-5.6-luna`** (OpenAI)
- **B: `deepseek/deepseek-v4-pro`** (DeepSeek)

Cada auditor julga cada caso de forma independente, em lotes de 5 casos embaralhados, com saída
JSON estruturada (JSON schema estrito). Ele vê a conversa, os `acceptable_tools` e `args` gold,
o catálogo completo de tools visível ao router e a política de rotulagem. Ele nunca vê a
categoria do caso, a fonte, o outro auditor ou qualquer saída de router. Por caso, ele retorna:
`gold_acceptable` (Y/N), `wrong_tools`, `missing_alternatives`, `proposed_tools` (melhor primeiro),
`out_of_scope`, `escalation_acceptable`, `args_correct`, `proposed_args`, `rationale`.

Conjuntos auditados: todos os 349 casos de test-v2 e o subconjunto B2 de test-v1 (182 casos: todos os casos
adversarial, fora_escopo e ambiguo mais 28/23/9 sorteados de direto/parafrase/multiturno
com seed 20260930; ids em `data/audit/test_v1_subset_ids.json`). Os resultados da auditoria de test-v1 são
escritos apenas em `data/audit/`; `data/dataset_test.jsonl` nunca é editado.

### Regra de adjudicação (pré-declarada, fixada antes de qualquer chamada de auditoria)

Por caso, duas dimensões independentes:

1. **Tools.** Ambos os auditores aceitam o gold -> **manter**. Ambos o rejeitam e propõem a mesma correção
   (o mesmo conjunto de `proposed_tools` e a mesma primeira tool) -> **aplicar a correção**. Qualquer outra
   combinação (um aceita e o outro rejeita, ou ambos rejeitam com correções diferentes) -> **sinalizar**.
2. **Args.** Ambos dizem `args_correct` -> manter. Ambos dizem errado e propõem os mesmos args
   (nomes iguais, valores iguais após trim e lowercase) -> aplicar. Caso contrário -> sinalizar.

Um caso é **sinalizado** se qualquer dimensão for sinalizada, ou se uma correção aplicada for inválida
(tool desconhecida, ou um arg que não é parâmetro de uma tool aceitável). Casos sinalizados mantêm seu
gold original até que um humano decida. Alternativas faltantes que ambos os auditores propõem em um caso
aceito são registradas (`label_audit.both_missing_alternatives`), mas **não** aplicadas.

No test-v2 o resultado é gravado no campo `label_audit` de cada linha:
`{decision: keep|fixed|flagged, reasons, auditors, original?, both_missing_alternatives?}`.
`original` guarda o `expected` pré-auditoria sempre que o gold mudou, de modo que pontuar com os
rótulos originais continua possível (`study rescore` é offline). Os resultados de test-v1 vão para
`data/audit/adjudication_test_v1_subset.jsonl` apenas.

Estatísticas reportadas (`data/audit/summary.json`): concordância bruta e kappa de Cohen entre os
auditores em `gold_acceptable`, `args_correct`, `out_of_scope`, `escalation_acceptable` e na
primeira tool proposta; para cada auditor contra o gold: concordância em fora de escopo e escalonamento
(gold: `__abstain__` / `escalate_to_human` em `acceptable_tools`), kappa da primeira tool, a taxa com
que sua primeira tool está no conjunto gold, e a taxa de aceitação do gold com IC 95% de Wilson.

### Revisão humana dos casos sinalizados

`data/audit/review.html` é uma página autocontida (sem assets externos) que lista todo caso
sinalizado de ambos os splits com o gold e os dois vereditos. Por caso, escolha `keep_gold`, `apply_a`,
`apply_b`, `custom` (tools, melhor primeiro, + JSON de args) ou `drop`, e então **Export decisions JSON**.
Formato do arquivo de decisões:

```json
{
  "format": "label-decisions/v1",
  "dataset": "data/dataset_test_v2.jsonl",
  "dataset_sha256": "<sha of the file the page was built from>",
  "exported_at": "2026-10-01T12:00:00Z",
  "decisions": [
    {"split": "test_v2", "id": "v2-ambiguo-004", "decision": "custom",
     "acceptable_tools": ["request_refund", "cancel_order"], "args": {"order_id": "O0031"},
     "note": "optional"},
    {"split": "test_v1_subset", "id": "syn-adversarial-003", "decision": "keep_gold", "note": ""}
  ]
}
```

`acceptable_tools`/`args` estão presentes apenas para `custom`. Aplique com
`uv run python scripts/dataset/audit.py apply-decisions <file>`: as linhas de test-v2 recebem o gold
decidido, `reviewed: true`, `label_audit.human_decision` (e `original` quando o gold mudou);
`drop` remove a linha. As decisões de test-v1 são ignoradas pelo comando (mantidas para a análise
de replicação). **Aplicar decisões muda o sha256 do test-v2: re-congele-o abaixo antes da
tag de pré-registro.**

## Resultados da geração do test-v2

De `data/generation_meta_v2.json` e `data/audit/overlap_report.json`.

| Categoria | direto | parafrase | ambiguo | multiturno | fora_escopo | adversarial | total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test-v1 | 105 | 87 | 70 | 35 | 35 | 17 | 349 |
| test-v2 | 105 | 87 | 70 | 35 | 35 | 17 | 349 |

Por tool, gold antes da auditoria (any = listada em `acceptable_tools`, first = rótulo preferido;
`any` do test-v1 entre parênteses):

| Tool | any | first | | Tool | any | first |
| --- | --- | --- | --- | --- | --- | --- |
| get_customer_profile | 14 (7) | 14 | | get_payment_status | 22 (17) | 22 |
| search_help_center | 22 (24) | 22 | | generate_boleto_second_copy | 13 (15) | 13 |
| escalate_to_human | 47 (41) | 13 | | request_refund | 40 (48) | 22 |
| get_order_status | 30 (37) | 30 | | get_refund_status | 22 (20) | 13 |
| track_shipment | 31 (31) | 13 | | dispute_charge | 22 (31) | 22 |
| update_delivery_address | 13 (11) | 13 | | check_return_eligibility | 21 (19) | 13 |
| reschedule_delivery | 13 (16) | 13 | | create_return_request | 30 (40) | 21 |
| cancel_order | 31 (34) | 22 | | generate_return_label | 13 (14) | 13 |
| create_exchange | 23 (30) | 14 | | open_warranty_claim | 22 (18) | 13 |
| `__abstain__` | 43 (37) | 43 | | | | |

Mínimo por tool: 13 (test-v1: 7). Após as correções acordadas da auditoria, a contagem mínima de primeiro rótulo
continua >= 8 para toda tool (`tests/test_dataset.py`).

- Rejeições em 117 chamadas ao gerador: 95 divergências de rótulo/spec, 22 pedidos não oferecidos (na maioria
  itens `abuse` que citam o pedido de outro cliente), 7 nomes de arg inventados, 104 quase-duplicatas
  semânticas dos 500 casos existentes (cosseno >= 0.9), 1 quase-duplicata semântica de uma
  unidade do catálogo, 0 ocorrências léxicas, 144 itens excedentes acima da cota. Os slots rejeitados foram regenerados
  (9 rodadas).
- Sobreposição final do test-v2: máximo léxico de 0.775 vs os 500 casos e 0.636 vs o catálogo;
  máximo semântico de 0.900 (abaixo do threshold, 0 casos >= 0.9) vs os 500 casos e 0.869 vs o
  catálogo; 0 sobreposição de ids. Dentro do test-v2, 18 casos têm um vizinho semântico mais próximo >= 0.9
  (redundância, não vazamento; dedupe intra-conjunto apenas léxico).
- Checagem de vazamento commitada dos splits mais antigos contra o catálogo (revisão minor 2): test-v1
  máximo léxico 0.893 (0 >= 0.95), semântico 4 casos >= 0.9 (máx. 0.914); dev máximo léxico 0.896,
  semântico 4 casos >= 0.9 (máx. 0.956).
- Mock DB (sha de `mock_db.json` nos metadados): 283 casos referenciam um pedido; em 279 deles
  a primeira tool gold é concluída no estado do pedido. Conflitos (nenhuma tool aceitável é concluída):
  `v2-adversarial-001`, `-003`, `-004` (pedidos de tool nomeada em pedidos cujo estado rejeita a
  ação; mantidos, a decisão do router continua bem definida). O mock DB foi construído apenas a partir de
  dev/test-v1; se for regenerado com o test-v2, verifique esses números novamente.
- Substituição post-hoc (2026-10-01): `tests/test_leakage.py` (mais estrito: contenção integral de uma
  unidade do catálogo com >= 4 palavras por turno do usuário) sinalizou `v2-direto-025` ("Boa noite, onde está o pacote
  do O0047? ...", que contém a unidade de descrição de `track_shipment` "onde está o pacote"). O
  slot foi regenerado no lugar (`generate_v2.py --replace v2-direto-025`: mesmo id, categoria e
  tool alvo; novo texto "O0049. Rastreia pra mim."), reauditado por ambos os auditores (keep), e seus
  vereditos antigos movidos para `data/audit/verdicts_superseded.jsonl`. O `overlap.py` agora aplica as
  próprias unidades e a regra léxica do teste de vazamento (`leak_rules()` carrega `tests/test_leakage.py`) e
  o caminho de substituição também verifica cosseno >= 0.9 por turno do usuário contra suas unidades de >= 4 palavras, de modo que
  a geração e o teste do repo não possam mais discordar. Custo da correção: US$0.0052.
- Custo: US$1.642 para a geração, incluindo US$0.67 de uma primeira execução que quebrou em uma
  completion vazia antes de gravar qualquer coisa (o código agora salva toda saída paga em
  `generation_v2_raw.jsonl` e `--resume` a reproduz).

## Resultados da auditoria

De `data/audit/summary.json`. Kappa é o kappa de Cohen; o kappa da primeira tool é multiclasse.

| | test-v2 (n=349) | subconjunto test-v1 (n=182) |
| --- | --- | --- |
| A vs B, gold aceitável: concordância / kappa | 0.900 / 0.662 | 0.824 / 0.599 |
| A vs B, args corretos | 0.848 / 0.519 | 0.885 / 0.487 |
| A vs B, fora de escopo | 0.989 / 0.941 | 0.984 / 0.949 |
| A vs B, escalonamento aceitável | 0.974 / 0.886 | 0.929 / 0.707 |
| A vs B, primeira tool proposta | 0.914 / 0.908 | 0.841 / 0.825 |
| A: taxa de gold aceitável [IC 95%] | 0.785 [0.739, 0.825] | 0.615 [0.543, 0.683] |
| B: taxa de gold aceitável [IC 95%] | 0.857 [0.816, 0.890] | 0.769 [0.703, 0.825] |
| A vs gold: kappa de fora de escopo / escalonamento / primeira tool | 0.930 / 0.910 / 0.848 | 0.966 / 0.601 / 0.747 |
| B vs gold: kappa de fora de escopo / escalonamento / primeira tool | 0.902 / 0.903 / 0.854 | 0.983 / 0.682 / 0.824 |
| A / B primeira tool no conjunto gold | 0.911 / 0.888 | 0.896 / 0.929 |
| Decisões keep / fixed / flagged | 214 / 27 / 108 | 96 / 18 / 68 |

Decisões do test-v2 por categoria (keep/fixed/flagged): direto 79/6/20, parafrase 52/10/25,
ambiguo 15/6/49, multiturno 23/4/8, fora_escopo 34/0/1, adversarial 11/1/5.

Leitura:

- Ambos os auditores aceitam o test-v2 com mais frequência que o subconjunto do test-v1 (o subconjunto dá peso excessivo às
  categorias difíceis, então compare por categoria em `summary.json`).
- **ambiguo é o ponto fraco**: o auditor A aceita apenas 23/70 conjuntos de rótulos ambíguos do test-v2
  (B: 44/70); 49 das 108 sinalizações são casos ambíguos. Isso sustenta a revisão M4 (o crédito multi-label
  é generoso): reporte a acurácia single-label e somente do primeiro rótulo junto com a métrica principal.
- Muitas sinalizações de args (verificadas por amostragem, não contadas) são divergências pedantes em valores de texto livre (`query`,
  `reason`, `details`) ou grafias de enum; args só são pontuados quando não vazios, então isso importa
  apenas para as métricas e2e/de args.
- A regra pré-declarada foi aplicada sem alterações: nenhum threshold ou regra foi editado após ver
  os vereditos.

## Freeze

sha256 após a adjudicação automatizada (antes de qualquer decisão humana). Um arquivo de decisões humanas
aplicado com `audit.py apply-decisions` muda o sha do dataset: atualize esta tabela (o teste
`test_v2_frozen_sha256_matches_dataset_card` falha até que ela seja atualizada).

| Arquivo | sha256 |
| --- | --- |
| `data/dataset_test_v2.jsonl` | `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` |
| `data/generation_meta_v2.json` | `55004fe4b32012a9dd26a21f6db025bdd901293a6571fdca8451538c4ba6a122` |
| `data/audit/test_v1_subset_ids.json` | `d022eb07f9566e19e8c4b8520741cb5c43ecd90514b3fefd446ed1c107500efc` |
| `data/audit/verdicts_test_v2_A.jsonl` | `2d9ed6aca25cc7c471b47106c1cca3dc6b092f6dc57525f6d085ca491081a9ea` |
| `data/audit/verdicts_test_v2_B.jsonl` | `c99d8ea98adefd0df9c19934846c2102ad6514ea203323e64baabdbe2896bb3e` |
| `data/audit/verdicts_test_v1_subset_A.jsonl` | `59beba96e0835efb0c7c5a6c036636fe441f70c4c85d4d9b2c62e04b3fc4b5fa` |
| `data/audit/verdicts_test_v1_subset_B.jsonl` | `05a21b3862e18a7ec562cb076294e3ab7388b2ba44911873bbf74bcc3bb50a1d` |
| `data/audit/adjudication_test_v2.jsonl` | `a7107bd0506f5936e636ba45fe0d5d50dd7a69b86f5f21649045eb2bb15ae898` |
| `data/audit/adjudication_test_v1_subset.jsonl` | `2f38b5bba3b09aa8c4e48e7d8439824297dc3e4048251a7513f2a1952e6c10db` |
| `data/audit/summary.json` | `a79094092a2f0a58f2091d744f9b8bda6f6407ef27d9d2bd044522f11efd4973` |
| `data/audit/overlap_report.json` | `f7c7ee4f2d58193ab04edb6f0329652c39251d038b4d957ab589f98d4815f2a9` |
| `data/audit/generation_v2_raw.jsonl` | `df5e0702c31da54760df591f3de03755d470b73f82b21421235edcf1df863779` |
| `data/audit/verdicts_superseded.jsonl` | `9645480421a0141d11d20dff87fe94e4e2950638ec867e4cac16bffa94e86820` |
| `data/audit/generation_v2_log.jsonl` | `1e81ca808e35946ee7971e8d76a8119dff4bdc080028d90ca9b81ed8cdeee9e7` |

`data/audit/review.html` é regenerado por `adjudicate` (ele embute um timestamp) e não é congelado.
