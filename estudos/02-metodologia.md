# 02 · Metodologia

> Versão final. O protocolo foi congelado na tag `prereg-v1` (commit `d14816e`) antes da
> primeira chamada no test-v2; o texto completo está em [prereg-v1.md](../docs/prereg/prereg-v1.md)
> e os desvios em [deviations.md](../docs/prereg/deviations.md).

## 1. O problema

Um agente em produção precisa, a cada mensagem, decidir **qual conjunto de capacidades** usar
(skill) e **qual ação** executar (tool). O padrão *agent-skill* resolve isso em dois estágios:

1. **Skill:** qual domínio a mensagem pertence, ou nenhum (fora de escopo: escalar ou abster);
2. **Tool:** dentro da skill escolhida (mais as tools globais), qual ação executar.

O executor, o LLM que preenche argumentos e responde ao cliente, só enxerga as tools que o
roteador liberou. O estudo compara **como decidir** esses dois estágios: com regras, busca
léxica, busca semântica, classificadores treinados, LLMs de uso geral e um modelo de decisão
comercial (Jev), isolados e em cascata.

## 2. Domínio e agente

- **Domínio:** pós-venda de e-commerce em português brasileiro. Foi escolhido porque o
  vocabulário das skills se sobrepõe de verdade: "quero meu dinheiro de volta do pedido que não
  chegou" toca pedidos, pagamentos e devoluções.
- **Catálogo:** 18 tools num servidor MCP (FastAPI + FastMCP, especificação 2026-07-28):
  - 3 globais: `get_customer_profile`, `search_help_center`, `escalate_to_human`;
  - 5 tools em cada uma das 3 skills (`pedidos_logistica`, `pagamentos_reembolsos`,
    `trocas_devolucoes`).

  `load_skill` fica no agente, porque carregar uma skill muda o que o agente expõe.
- **Fonte única:** o servidor MCP é a única fonte do catálogo. Descrições, exemplos, skills e
  políticas vêm dele, com cache em memória, depois no Redis, depois no servidor. Nenhuma
  estratégia tem informação privilegiada.
- **Mocks determinísticos:** os dados vêm de um banco fictício somente leitura, e as escritas
  devolvem recibos derivados dos argumentos. Assim, casos e repetições não se contaminam.
- **Agente:** grafo LangGraph de 5 nós (`ingest → route_skill → route_tool → agent ⇄ tools`),
  com checkpointer no Redis. Um único executor serve o agente nativo (E0), que chama
  `load_skill` sozinho, e os agentes roteados, em que o roteador decide o que expor.

## 3. Estratégias comparadas

Detalhes e comparação com o estado da arte no capítulo [03](03-estrategias.md).

| Família | Estratégias | Onde roda |
|---|---|---|
| Regras | Regex com pesos e supressores | Local |
| Busca léxica | BM25 com índice por exemplo do catálogo e n-gramas de caracteres 3–5 | Local |
| Busca semântica | `qwen3-embedding-8b` (Q8) | Local (Ollama) |
| Classificador treinado (E10) | Sonda linear sobre os vetores do `qwen3-embedding-8b`, treinada nos exemplos do catálogo | Local |
| Fusão (E11) | Híbrido: combinação convexa das confianças calibradas do regex e do classificador | Local |
| LLM de uso geral | Claude Sonnet 5 (E5), Claude Haiku 4.5 (E6) | AWS Bedrock |
| LLM local (E6b) | Qwen3-8B (Q8, raciocínio desligado) | Local (Ollama) |
| Modelo de decisão (E4) | `typesafe/jev-router` (**jev-router via OpenRouter**) | OpenRouter |

O `jev-router` do OpenRouter é um meta-roteador: cada chamada é atendida por um modelo que ele
escolhe. O estudo o avalia como classificador via prompt, e não pela API tipada nativa do Jev.
O E5b (Qwen3-32B local) foi planejado e retirado antes do pré-registro, por latência (~34 s no
p50 do estágio de tool no benchmark do dev); não há run dele.

**Cascatas.** O primeiro passo que passa do seu limiar decide:

| Experimento | Cascata |
|---|---|
| E7 | regex → Jev |
| E8 | regex → Sonnet |
| E9 | regex → Jev → Sonnet |
| E12 (exploratório) | híbrido → Jev → Sonnet |

## 4. Dados

- **Categorias:** direto, paráfrase, ambíguo entre skills, multi-turno, fora de escopo e
  adversarial. A distribuição é desenhada para expor fraquezas, não para imitar tráfego real.
- **Dev (151 casos):** o único split usado para ajustar regras, parâmetros, prompts,
  calibração e limiares.
- **Test-v1 (349 casos): exposto.** Foi usado num run preliminar cujos erros foram lidos antes
  da reotimização dos roteadores. Serve só para replicação e diagnóstico de contaminação,
  nunca como resultado confirmatório.
- **Test-v2 (349 casos): confirmatório.**
  - Gerado depois de todo o ajuste, com o mesmo gerador (`google/gemini-2.5-flash`, de outra
    família que os roteadores Claude), seed nova e as mesmas cotas por categoria.
  - Duplicatas removidas contra os 500 casos anteriores e contra todo texto do catálogo que os
    roteadores veem (léxico e semântico).
  - Usado **uma única vez**, depois do pré-registro. sha256
    `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66`.
- **Auditoria de rótulos:** cega, feita por dois modelos de famílias diferentes do Claude e do
  gerador (`openai/gpt-5.6-luna` e `deepseek/deepseek-v4-pro`), com regra de adjudicação declarada
  antes. No test-v2: κ = 0,662 na aceitação do gold e 0,908 na primeira tool proposta; decisões
  214 mantidos, 27 corrigidos, 108 sinalizados ([dataset-card.md](../docs/dataset-card.md)). A
  análise pré-registrada usa os rótulos da adjudicação automática. A revisão humana dos
  sinalizados era opcional e **não foi feita**; por isso não há rescore com rótulos humanos.
- **Rótulos múltiplos:** casos ambíguos aceitam mais de uma resposta correta. Como análise de
  sensibilidade, reportamos também a acurácia estrita, só com o primeiro rótulo.

## 5. Protocolo de ajuste (sempre no dev)

- **Validação cruzada:** 5 partes estratificadas por categoria, seed 0, com estimativa aninhada
  para o procedimento de escolha.
- **Engenharia de prompt,** em duas trilhas:
  - **A, canônica:** o mesmo prompt para todos os LLMs, escolhido pela média entre os modelos;
  - **B, otimizada:** o melhor prompt de cada modelo.

  Os exemplos no prompt vêm só do catálogo. Diferenças menores que um erro-padrão não
  justificam trocar de variante. **Resultado da seleção:** P0 nas duas trilhas para os quatro
  modelos, então a trilha B é idêntica à A (capítulo [04](04-prompts.md)).
- **Calibração:** mapa isotônico por estratégia e por estágio, ajustado nas partes de treino. É
  isso que torna comparáveis as confianças de naturezas diferentes (heurística, margem,
  similaridade, autoavaliação).
- **Limiares das cascatas:** máxima acurácia conjunta com custo ≤ 0,5 × o custo do Sonnet no
  dev, por *cross-fitting* em 5 partes, sobre o passe shadow do dev; a fronteira de Pareto
  completa e uma regra de precisão ficaram como sensibilidade (capítulo [06](06-cascatas.md)).
  O *conformal risk control* previsto no rascunho deu lugar a essa regra; a regra de precisão
  ficou só como sensibilidade por ser instável entre as partes com 151 casos
  ([prereg-v1.md §4](../docs/prereg/prereg-v1.md)).
- **Registro de esforço:** para cada estratégia, anotamos as configurações avaliadas, as
  passadas no dev e as horas humanas gastas.

## 6. Métricas

| Métrica | Definição |
|---|---|
| Acurácia conjunta (primária) | Skill e tool corretas no top-1 |
| Skill, tool condicional, recall@1/2/3 | Por estágio |
| Abstenção | Precisão e revocação em fora de escopo (escalar conta como abster) |
| Calibração | ECE com bins adaptativos, Brier, diagramas de confiabilidade |
| Classificação seletiva | Curva risco × cobertura, AURC, cobertura com no máximo 5% de erro |
| `e2e_success` (primária do e2e) | Decomposto em primeira chamada, clarificação creditada e recuperação creditada |
| Grounding de entidades, argumentos inventados | Diagnósticos do e2e |
| Custo | US$ por 1.000 requisições em três regimes: observado com cache, preço de tabela sem cache e modelo de taxa de acerto do cache |
| Latência | p50/p95/p99 de um benchmark dedicado (sem cache de respostas, intercalado, concorrência 1); fila e retentativas reportadas à parte; local e API em colunas separadas |
| Contexto | Tokens da parte fixa e da variável, leituras e escritas de cache |

## 7. Estatística

- **Unidade de análise:** o caso. As repetições são promediadas por caso.
- **Análise primária por intenção de tratar:** erro de infraestrutura conta como erro de
  roteamento. A taxa de erro é reportada. A interseção sem erros é só sensibilidade.
- **Intervalos de confiança:** bootstrap por caso, 10 mil reamostragens, seed 20260930, para
  valores e para diferenças pareadas.
- **Testes:** McNemar exato e permutação por sinal no nível do caso. Correção de Holm dentro de
  cada família pré-registrada. Equivalência (TOST, ±3 pontos) entre os LLMs.
- **Poder:** com 349 casos e discordância de 10–15% entre roteadores, a menor diferença
  detectável é de ~4,5–6 pontos (~7 com Holm). Comparamos os LLMs por equivalência, não por
  ranking.

## 8. Pré-registro e regras de parada

Congelados antes da primeira chamada no test-v2 (tag `prereg-v1`):

- hashes de código, configs, prompts, catálogo, scorer e dataset;
- limiares e o método que os escolheu;
- manifesto e ordem dos runs;
- hipóteses (H1–H3 primárias, S1–S4 secundárias) e a lista de estimativas.

Nenhuma config, prompt, rótulo ou scorer muda depois da primeira linha de teste.

**Regra de erros:** até 2 retentativas de erros de infraestrutura. Um run com mais de 2% de
erros é refeito do zero. Todo desvio é registrado com data e hora.

**O que aconteceu:** os 102 runs do manifesto terminaram COMPLETE; só o E4 Jev (2 linhas) e o
Jev P0+P6c (1 linha) tiveram erros depois do rescore, todos abaixo de 0,3%. Houve três desvios:
D-001 (correção de infraestrutura na checagem de modelos do Ollama), D-002 (dois runs
exploratórios com todas as tools da skill expostas, decididos depois de ver H3) e D-003
(infraestrutura do upload do test-v1 no Langfuse). Nenhum mudou config, prompt, rótulo ou scorer
dos runs pré-registrados.

## 9. Observabilidade

Cada turno é um trace no Langfuse local, com um span por nó do grafo e uma generation por
chamada paga (tokens e custo). Os spans de roteamento registram escolha, confiança, candidatos,
passo da cascata e se a estratégia decidiu ou só foi registrada. O span do servidor MCP aparece
como filho no mesmo trace, via `traceparent`.

Cada run é um experimento ligado ao dataset, com as notas como colunas. As figuras do estudo
combinam prints desses painéis com gráficos gerados a partir dos resultados recalculados.
