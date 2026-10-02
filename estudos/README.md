# Estudo: roteamento de skills e tools em agentes de IA

> Versão final. Protocolo pré-registrado na tag `prereg-v1` e executado uma única vez no split
> confirmatório `test_v2` (349 casos, pt-BR). Todo número destes capítulos vem das tabelas em
> [`docs/results/final/`](../docs/results/final/), geradas por
> `uv run python scripts/analysis/final_all.py`. Cada afirmação indica se é **confirmatória**
> (pré-registrada), **estimativa** ou **exploratória** (post hoc).

**Em uma frase:** neste catálogo de 18 tools, o agente nativo que carrega a skill sozinho acertou
mais de ponta a ponta (55,6%) que o agente com roteador (45,8%; −9,7 pp [−13,5; −6,0]); no
roteamento isolado, o Jev via OpenRouter igualou o Sonnet 5 (84,7% vs 84,1%) a um sexto do custo,
e o regex escrito no dev caiu 32 pp no teste. Resumo completo em [01](01-resumo-executivo.md).

## Documentos

| # | Documento | Conteúdo |
|---|---|---|
| 01 | [Resumo executivo](01-resumo-executivo.md) | A resposta em uma página, recomendação por cenário e números com IC |
| 02 | [Metodologia](02-metodologia.md) | Domínio, agente, MCP, dataset, splits, auditoria de rótulos, pré-registro, desvios e estatística |
| 03 | [Estratégias de roteamento](03-estrategias.md) | Regex, BM25, embeddings, híbrido, classificador, LLMs, Jev, cascatas e o estado da arte de cada um |
| 04 | [Engenharia de prompt: trilhas A e B](04-prompts.md) | Variantes P0–P6, seleção por um erro-padrão (P0 em tudo), variante de custo do Jev e economia de contexto |
| 05 | [Resultados de roteamento](05-resultados-roteamento.md) | Acurácia conjunta, H1/H2, equivalência (S2), dev → teste (S3), léxico × semântico (S4), calibração, risco × cobertura, replicação no test-v1 |
| 06 | [Cascatas](06-cascatas.md) | Limiares escolhidos no dev, resultado no teste, cobertura por passo, oráculo e adiamento aleatório |
| 07 | [Ponta a ponta](07-ponta-a-ponta.md) | H3 (vale ter roteador?), decomposição do e2e, D-002 (todas as tools expostas) e análise de erros roteado × nativo |
| 08 | [Custo, latência e contexto](08-economia.md) | Três regimes de custo, benchmark de latência, local × API, assimetria de cache, tokens de contexto |
| 09 | [Análise de erros](09-erros.md) | Por categoria, por tool, rótulo único × múltiplo, pares confundidos, modelos atendidos pelo Jev |
| 10 | [Manutenção (pergunta 5)](10-manutencao.md) | Esforço para adicionar uma tool (leave-tools-out), exploratório |
| 11 | [Matriz de decisão enterprise](11-matriz-enterprise.md) | Latência × custo × acurácia mínima → roteador, e orientação por caso de uso |
| 12 | [Ameaças à validade e limitações](12-limitacoes.md) | Exposição do test-v1, superajuste ao dev, dados sintéticos, assimetria do scorer e2e, catálogo pequeno, Jev como meta-roteador |
| 13 | [Reprodutibilidade](13-reprodutibilidade.md) | Hashes, manifesto, comandos por tabela, ledger de gastos |

As figuras ficam em [`figuras/`](figuras/): gráficos gerados a partir dos resultados recalculados
(`final-*.png`; os `final-x-*.png` são exploratórios) e prints do Langfuse (`langfuse-*.png`).

## Perguntas de pesquisa (de `docs/projeto.md`) e onde estão respondidas

1. Qual a acurácia de skill e de tool de cada estratégia isolada? → [05](05-resultados-roteamento.md)
2. Qual o custo por 1.000 requisições e a latência p50/p95 do roteamento? → [08](08-economia.md)
3. Uma cascata chega perto da acurácia do LLM a que fração do custo? → [06](06-cascatas.md)
4. Onde cada técnica erra: paráfrase, ambiguidade, multi-turno, fora de escopo? → [09](09-erros.md)
5. Qual o custo de manutenção de cada técnica quando entra uma tool nova? → [10](10-manutencao.md)

E a pergunta que organiza tudo, "vale ter roteador?", em [07](07-ponta-a-ponta.md).

## Hipóteses pré-registradas e resultado

| Hipótese | Resultado no test-v2 |
|---|---|
| **H1.** E9 não perde mais que 3 pp de conjunta para o Sonnet 5, a menos da metade do custo | Δ −2,4 pp [−5,4; 0,7]: **não inferioridade não demonstrada**; custo 0,199× |
| **H2.** E7 (regex → Jev) não perde mais que 3 pp para o Sonnet 5 | Δ −4,2 pp [−7,8; −0,6]: **não demonstrada** |
| **H3.** `e2e_success` de E9 − agente nativo E0 | −9,7 pp [−13,5; −6,0], Holm p 0,0003: **o nativo é melhor** |
| S1. Ganho da trilha de prompt otimizada sobre a canônica | Degenerado: P0 escolhido nas duas trilhas para os quatro LLMs |
| S2. Equivalência ±3 pp entre LLMs e Sonnet | Haiku e Qwen inconclusivos; Jev equivalente pelo IC, **não** após Holm |
| S3. Distância dev → teste do regex e do BM25 | Regex −32,1 pp [−37,5; −26,9]; BM25 −6,7 pp [−11,9; −1,5] |
| S4. Léxico × semântico | Embedding − regex = +20,9 pp [15,2; 26,6] |

Fontes: [primary.md](../docs/results/final/primary.md) e [secondary.md](../docs/results/final/secondary.md).
