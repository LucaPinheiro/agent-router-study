# Estudo: roteamento de skills e tools em agentes de IA

> Rascunho estrutural. As seções marcadas com **[resultado]** são preenchidas só depois do run
> confirmatório no split `test_v2`, pré-registrado na tag `prereg-v1`. Nenhum número entra aqui
> antes disso.

## Documentos

| # | Documento | Conteúdo |
|---|---|---|
| 01 | [Resumo executivo](01-resumo-executivo.md) | A resposta em uma página e a recomendação por cenário **[resultado]** |
| 02 | [Metodologia](02-metodologia.md) | Domínio, agente, MCP, dataset, splits, auditoria de rótulos, pré-registro e estatística |
| 03 | [Estratégias de roteamento](03-estrategias.md) | Regex, BM25, embeddings, híbrido, classificador, LLMs, Jev e o que é estado da arte em cada um |
| 04 | [Engenharia de prompt: trilhas A e B](04-prompts.md) | Prompt canônico e prompt otimizado por modelo, variantes P0–P6 e economia de contexto |
| 05 | [Resultados de roteamento](05-resultados-roteamento.md) | Acurácia conjunta com IC, diferenças pareadas, equivalência, calibração e risco × cobertura **[resultado]** |
| 06 | [Cascatas](06-cascatas.md) | Limiares por validação cruzada e conformal, fronteira de Pareto, cobertura por passo e oráculo **[resultado]** |
| 07 | [Ponta a ponta](07-ponta-a-ponta.md) | Vale ter roteador? Decomposição do e2e, custo por turno e contexto **[resultado]** |
| 08 | [Custo, latência e contexto](08-economia.md) | Três regimes de custo, benchmark de latência, cache de prompt, local × API **[resultado]** |
| 09 | [Análise de erros](09-erros.md) | Por categoria, por tool, pares confundíveis, seed × sintético **[resultado]** |
| 10 | [Manutenção (pergunta 5)](10-manutencao.md) | Esforço para adicionar uma tool (leave-tools-out) **[resultado]** |
| 11 | [Matriz de decisão enterprise](11-matriz-enterprise.md) | Latência máxima × custo máximo × acurácia mínima → roteador recomendado **[resultado]** |
| 12 | [Ameaças à validade e limitações](12-limitacoes.md) | Exposição do test-v1, dados sintéticos, catálogo pequeno, Jev como meta-roteador |
| 13 | [Reprodutibilidade](13-reprodutibilidade.md) | Hashes, manifesto, comandos por tabela, ledger de gastos |

As evidências ficam em `estudos/figuras/`: prints do Langfuse capturados com Playwright e
gráficos gerados a partir dos resultados recalculados.

## Perguntas de pesquisa (de `docs/projeto.md`)

1. Qual a acurácia de skill e de tool de cada estratégia isolada?
2. Qual o custo por 1.000 requisições e a latência p50/p95 do roteamento?
3. Uma cascata chega perto da acurácia do LLM a que fração do custo?
4. Onde cada técnica erra: paráfrase, ambiguidade, multi-turno, fora de escopo?
5. Qual o custo de manutenção de cada técnica quando entra uma tool nova?

## Hipóteses pré-registradas (resumo; texto completo na tag `prereg-v1`)

- **H1.** A cascata E9 não perde mais que 3 pontos de acurácia conjunta para o Sonnet 5, e o
  custo de roteamento dela é menos da metade.
- **H2.** A cascata E7 (regex → Jev) não perde mais que 3 pontos para o Sonnet 5.
- **H3.** Diferença de `e2e_success` entre E9 e o agente nativo E0, com IC.
- **Secundárias:**
  - ganho de prompt da trilha B sobre a A, por modelo;
  - equivalência entre os LLMs (±3 pontos);
  - distância entre dev e teste do regex e do BM25;
  - léxico × semântico.
