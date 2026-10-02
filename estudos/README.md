# Estudo: roteamento de skills e tools em agentes de IA

> Versão final. Protocolo pré-registrado na tag `prereg-v1` e executado uma única vez no split
> confirmatório `test_v2` (349 casos, pt-BR). Todo número destes capítulos vem das tabelas em
> [`docs/results/final/`](../docs/results/final/), geradas por
> `uv run python scripts/analysis/final_all.py`. Cada afirmação indica se é **confirmatória**
> (pré-registrada), **estimativa** ou **exploratória** (post hoc).
>
> **Fase 2** (capítulos [14](14-fase2-nuvem.md) e [15](15-fase2-catalogo-grande.md)): dois
> pré-registros novos, `prereg-v2a` (Parte A, modelos gerenciados no Bedrock, mesmo test-v2,
> tabelas em [`docs/results/addendum-a/`](../docs/results/addendum-a/)) e `prereg-v2` (Parte B,
> catálogo de 62 tools, split novo test-L com 300 casos, tabelas em
> [`docs/results/phase2-b/`](../docs/results/phase2-b/)). Os capítulos 01–13 mantêm os números da
> fase 1; as seções "Fase 2" acrescentadas neles apontam para essas tabelas.

**Em uma frase:** neste catálogo de 18 tools, o agente nativo que carrega a skill sozinho acertou
mais de ponta a ponta (55,6%) que o agente com roteador (45,8%; −9,7 pp [−13,5; −6,0]); no
roteamento isolado, o Jev via OpenRouter igualou o Sonnet 5 (84,7% vs 84,1%) a um sexto do custo,
e o regex escrito no dev caiu 32 pp no teste. **Na fase 2, com 62 tools**, não houve diferença
detectável de ponta a ponta entre roteado e nativo (57,0% vs 57,3%, scorer simétrico; sem diferença detectável: −0,3 pp [−4,0; 3,3], o IC inclui 0, sem afirmação direcional **[C, H1-L]**; equivalência não testada (S2 inconclusivo)) e saiu 10% mais
caro por turno com o cache de prompt do nativo; o Jev seguiu como o melhor roteador (84,9%), não
inferior ao Haiku 4.5. Resumo completo em [01](01-resumo-executivo.md).

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
| 14 | [Fase 2, Parte A: nuvem × local](14-fase2-nuvem.md) | Modelos gerenciados no Bedrock (Ministral, Nemotron, Cohere, Titan) contra os locais no catálogo de 18 tools: família A (`prereg-v2a`), latência com âncoras, custo, matriz enterprise atualizada e resumo do scorer simétrico |
| 15 | [Fase 2, Parte B: catálogo grande (62 tools)](15-fase2-catalogo-grande.md) | O roteador passa a valer a pena? Catálogo G1–G12, dev-L/test-L e auditoria, `prereg-v2` com o scorer simétrico, H1-L/H2-L/H3-L, acurácia, custo, latência, calibração e cobertura das cascatas, E9-fullskill, variância do executor, 18 × 62 tools (X1/X2) e o que mudou em relação à fase 1 |

As figuras ficam em [`figuras/`](figuras/): gráficos gerados a partir dos resultados recalculados
(`final-*.png`; os `final-x-*.png` são exploratórios; `final-a-*.png` e `final-b-*.png` são da
fase 2, Partes A e B) e prints do Langfuse (`langfuse-*.png`).

## Perguntas de pesquisa (de `docs/projeto.md`) e onde estão respondidas

1. Qual a acurácia de skill e de tool de cada estratégia isolada? → [05](05-resultados-roteamento.md)
2. Qual o custo por 1.000 requisições e a latência p50/p95 do roteamento? → [08](08-economia.md)
3. Uma cascata chega perto da acurácia do LLM a que fração do custo? → [06](06-cascatas.md)
4. Onde cada técnica erra: paráfrase, ambiguidade, multi-turno, fora de escopo? → [09](09-erros.md)
5. Qual o custo de manutenção de cada técnica quando entra uma tool nova? → [10](10-manutencao.md)

E a pergunta que organiza tudo, "vale ter roteador?", em [07](07-ponta-a-ponta.md) (18 tools) e
[15](15-fase2-catalogo-grande.md) (62 tools).

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

### Fase 2, Parte A (pré-registro `prereg-v2a`, família A com Holm)

| Hipótese | Resultado no test-v2 |
|---|---|
| **A1.** Ministral 3 8B gerenciado (E6m) não perde mais que 3 pp para o Qwen3-8B local (E6b) | Δ +2,3 pp [−2,0; 6,6], Holm p 0,0136: **não inferior** |
| **A2.** Nemotron Nano 9B v2 gerenciado (E6n) não perde mais que 3 pp para o E6b | Δ −2,9 pp [−7,4; 1,7], Holm p 0,4722: **não demonstrada** |
| **A3.** Cohere Embed v4 (E3c) − qwen3-embedding local (E3) | Δ −19,2 pp [−24,6; −14,0], Holm p 0,0004: **o local é melhor** |
| **A4.** Titan v2 (E3t) − qwen3-embedding local (E3) | Δ −17,8 pp [−23,2; −12,6], Holm p 0,0004: **o local é melhor** |

Fonte: [addendum-a/primary.md](../docs/results/addendum-a/primary.md); leitura no capítulo [14](14-fase2-nuvem.md).

### Fase 2, Parte B (pré-registro `prereg-v2`, test-L com 300 casos, catálogo de 62 tools)

Primárias (Holm entre H1-L, H2-L e H3-L):

| Hipótese | Resultado no test-L |
|---|---|
| **H1-L.** `e2e_success_sym` de E9-L − agente nativo E0-L (bilateral) | Δ −0,3 pp [−4,0; 3,3], Holm p 1: **sem diferença demonstrada**; custo por turno E9-L/E0-L 1,101 [1,014; 1,196] |
| **H2-L.** Ministral 3 8B (E6m) não perde mais que 3 pp para o Haiku 4.5 (E6) | Δ −2,7 pp [−7,0; 1,7], Holm p 0,8795: **não demonstrada**; p95 E6m/E6 0,262 [0,189; 0,283] |
| **H3-L.** Jev (E4) não perde mais que 3 pp para o Haiku 4.5 (E6) | Δ +2,9 pp [−0,7; 6,6], Holm p 0,0027: **não inferior** |

Secundárias (Holm dentro de cada família; S5 e S6 retiradas pela restrição "nenhum modelo local"):

| Hipótese | Resultado no test-L |
|---|---|
| S1. E9-L com todas as tools da skill − E9-L (e2e, > 0) | −0,3 pp [−2,7; 1,7]: **sem ganho** |
| S2. E9-L ≡ E0-L (±3 pp) nos 225 casos com as mesmas chamadas | +1,8 pp [0,4; 3,6]: **inconclusivo** |
| S3. Regex: test-L − dev-L | −26,4 pp [−32,0; −20,7] |
| S4. Embedding Titan − regex | +3,7 pp [−3,3; 10,3]: IC inclui 0 |
| S7. Sonda Titan − Jev | −25,9 pp [−31,7; −20,0]: **a sonda é pior** |

Fontes: [phase2-b/primary.md](../docs/results/phase2-b/primary.md) e
[phase2-b/secondary.md](../docs/results/phase2-b/secondary.md); leitura no capítulo
[15](15-fase2-catalogo-grande.md).
