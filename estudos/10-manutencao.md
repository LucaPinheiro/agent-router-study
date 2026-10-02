# 10 · Manutenção: quanto custa adicionar uma tool (pergunta 5)

> **Exploratório [X]** (não promovido a hipótese no pré-registro). Desenho em
> [docs/rq5-design.md](../docs/rq5-design.md); tabela do test-v2 em
> [estimation.md §K](../docs/results/final/estimation.md), gerada por `study rq5`.

## 1. Desenho: leave-tools-out

Três tools ficam de fora do catálogo, uma por skill, escolhidas entre as mais confundíveis:
`get_refund_status`, `reschedule_delivery` e `generate_return_label`. Nada muda no servidor MCP:
um filtro em tempo de execução tira as tools do catálogo que os roteadores veem.

| Condição | Catálogo | Regras de regex | O que mede |
|---|---|---|---|
| **base** | sem as 3 tools | regras de produção menos as dessas tools | o "antes" |
| **zero** | completo | nada novo para o regex | adicionar a tool só com descrição e exemplos no catálogo |
| **eng** | completo | base + regras novas, escritas com tempo limitado | adicionar a tool com engenharia de regras |
| **full** | completo | regras de produção | o estado atual (referência, só regex e híbrido) |

As regras `eng` foram escritas por um **agente de IA (Claude)**, não por um humano, com limite de
20 minutos e acesso só ao texto do catálogo. Ele tinha lido as regras originais ao montar a
separação base/original: o `eng` pode estar otimista.

Casos **afetados** = os que têm uma das tools retiradas entre os rótulos aceitáveis (48 no
test-v2); **outros** = o resto. Para os roteadores livres, os 301 outros casos; para Jev, Haiku e
Sonnet (pagos), uma amostra de 60.

## 2. Resultado no test-v2 [X]

| Estratégia | Cond. | Conjunta afetados (48) | Previu tool nova | Conjunta outros | Δ outros (pp) | Casos "roubados" |
|---|---|---|---|---|---|---|
| regex | base | 10,4 | 0,0 | 53,8 | – | 0 |
| regex | zero | 10,4 | 0,0 | 53,8 | +0,0 | 0 |
| regex | eng | **50,0** | 39,6 | 53,5 | −0,3 | 2 |
| regex | full | 45,8 | 35,4 | 53,8 | +0,0 | 2 |
| BM25 | zero | 54,2 | 54,2 | 48,2 | −3,0 | 11 |
| embedding | zero | **89,6** | 75,0 | 71,1 | −3,7 | 9 |
| classificador | zero | 83,3 | 68,8 | 73,4 | −1,7 | 10 |
| híbrido | zero | 58,3 | 45,8 | 73,8 | −0,7 | 1 |
| híbrido | eng | 66,7 | 54,2 | 73,1 | −1,3 | 2 |
| híbrido | full | 66,7 | 54,2 | 73,8 | −0,7 | 1 |
| Jev | zero | 93,8 | 81,2 | 76,7 (n=60) | +0,0 | 0 |
| Haiku 4.5 | zero | **95,8** | 85,4 | 75,0 (n=60) | −3,3 | 0 |
| Sonnet 5 | zero | 93,8 | 87,5 | 80,0 (n=60) | +3,3 | 0 |

No base, todas as estratégias ficam entre 0 e 16,7% nos afetados (só acertam por um segundo
rótulo aceitável). Fonte: [estimation.md §K](../docs/results/final/estimation.md) (tabela completa
com base de cada estratégia, perdidos/ganhos e erros).

## 3. Esforço

- **Entrada do catálogo** (comum a todas as estratégias): 18 linhas de descrição, 12 exemplos,
  15 palavras-chave para as 3 tools.
- **Regex `eng`:** 30 linhas, 17 regras, 5 definições, 1,2 min de relógio do agente.
- **Regex `full` (produção):** 17 linhas, 8 regras, 2 definições; tempo não registrado (iterado
  no dev).
- **Re-treino** (medido no dev): índice BM25 0,009 s, classificador 0,087 s, embedding dos 15
  textos novos a frio 4,29 s; LLM e Jev 0 s (o prompt é refeito a partir do catálogo)
  ([rq5-design.md](../docs/rq5-design.md)).

## 4. Leitura

- **Com esforço zero**, os roteadores guiados pelo catálogo absorvem a tool nova: LLMs e Jev
  acertam 94–96% dos afetados, embedding 89,6%, classificador 83,3%. A regressão nos outros casos
  fica entre −3,7 e +3,3 pp, com 0 a 11 casos "roubados" pela tool nova.
- **O regex não enxerga a tool nova sem regras novas** (10,4% = base). Com regras escritas em
  ~1 minuto ele vai a 50,0%; as regras de produção chegam a 45,8%. **No teste, as regras novas
  do agente superaram as de produção**, mas as duas ficam muito abaixo dos roteadores semânticos.
  No dev, o `full` chegava a 88,5% ([rq5-design.md](../docs/rq5-design.md)): o mesmo padrão de
  superajuste do capítulo [05](05-resultados-roteamento.md).
- O **híbrido** segue o membro regex e fica abaixo do classificador sozinho (66,7 vs 83,3 nos
  afetados).

**Resposta à pergunta 5:** em manutenção, a escolha é entre estratégias guiadas pelo catálogo
(custo marginal ≈ escrever a descrição e os exemplos da tool) e regras (custo por tool, e que
não generalizam). É um estudo de caso: 3 tools, um engenheiro que é um agente de IA, um limite
de tempo.
