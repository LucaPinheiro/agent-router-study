# 01 · Resumo executivo

> Todos os números vêm de `docs/results/final/` (gerados por `scripts/analysis/final_all.py`)
> sobre o split confirmatório **test-v2** (349 casos, pt-BR, pré-registro `prereg-v1`).
> Intervalos: IC 95% por bootstrap pareado por caso (10 mil reamostragens, seed 20260930).
> **[C]** = confirmatório (pré-registrado); **[E]** = estimativa; **[X]** = exploratório (post hoc).

## A resposta

**Neste catálogo (18 tools, 3 skills) não vale a pena colocar um roteador na frente do agente.**
O agente nativo (E0, Sonnet 5 chamando `load_skill` sozinho) resolveu **55,6%** dos turnos de
ponta a ponta, contra **45,8%** da cascata roteada E9 (regex → Jev → Sonnet): diferença de
**−9,7 pp [−13,5; −6,0]**, Holm p = 0,0003 **[C]** ([primary.md](../docs/results/final/primary.md), H3).
O roteador economiza só ~9% por turno (razão de custo E9/E0 = **0,909 [0,859; 0,960]**).

No roteamento isolado, as cascatas também não provaram o que prometiam: E9 ficou a −2,4 pp
[−5,4; 0,7] do Sonnet 5 e E7 (regex → Jev) a −4,2 pp [−7,8; −0,6]. A **não inferioridade
(margem 3 pp) não foi demonstrada** para nenhuma das duas **[C]**. A cascata E9 custa um quinto
do Sonnet sozinho (razão 0,199 [0,174; 0,224]) **[C, co-primária]**, mas o Jev sozinho (E4) já
chega a 84,7% [81,0; 88,2] por US$ 0,82 por mil casos **[E]**.

## Recomendação por cenário

| Cenário | Recomendação | Por quê (tabela de origem) |
|---|---|---|
| Catálogo pequeno (≲ 20 tools), qualidade de ponta a ponta importa | **Agente nativo (E0)**, sem roteador | E0 55,6% vs melhor roteado 50,7% (E5) e 45,8% (E9) no e2e ([estimation.md §J](../docs/results/final/estimation.md)) |
| Precisa de um roteador (governança, auditoria da decisão, catálogo crescendo), latência p95 < 10 s | **Jev sozinho (E4)** | 84,7% conjunta a US$ 0,82/1k, p95 6,9 s; melhor célula da matriz ([enterprise_matrix.md](../docs/results/final/enterprise_matrix.md)) |
| Sem chamada externa, custo zero de API | **Qwen3-8B local (E6b)** se p95 ~12 s for aceitável; **classificador (E10)** se precisar de p95 ~1 s | 79,9% e 74,8% conjunta ([estimation.md §A, §D](../docs/results/final/estimation.md)) |
| Latência p95 < 2 s com acurácia ≥ 75% | **Nenhuma configuração testada atende** | todas as células "none qualifies" ([enterprise_matrix.md](../docs/results/final/enterprise_matrix.md)) |
| Regex como primeira camada | **Não recomendado como decisor geral** | 84,8% no dev → 52,7% no teste (−32,1 pp) **[C, S3]** |

Detalhes por caso de uso no capítulo [11](11-matriz-enterprise.md).

## Números principais

| Resultado | Valor [IC 95%] | Status | Fonte |
|---|---|---|---|
| H1: conjunta E9 − Sonnet 5 | −2,4 pp [−5,4; 0,7]; NI **não** demonstrada | C | [primary.md](../docs/results/final/primary.md) |
| H1 co-primária: custo de roteamento E9/E5 | 0,199 [0,174; 0,224] | C | idem |
| H2: conjunta E7 − Sonnet 5 | −4,2 pp [−7,8; −0,6]; NI **não** demonstrada | C | idem |
| H3: e2e_success E9 − E0 | −9,7 pp [−13,5; −6,0]; Holm p 0,0003 | C | idem |
| H3: custo por turno E9/E0 | 0,909 [0,859; 0,960] | C | idem |
| S1: ganho de engenharia de prompt | nenhum: P0 escolhido nas duas trilhas para os 4 LLMs | C (degenerado) | [secondary.md](../docs/results/final/secondary.md) |
| S2: Haiku / Qwen / Jev ≡ Sonnet (±3 pp)? | inconclusivo / inconclusivo / equivalente pelo IC, mas não após Holm (p 0,131) | C | idem |
| S3: regex teste − dev | −32,1 pp [−37,5; −26,9] | C | idem |
| S4: embedding − regex | +20,9 pp [15,2; 26,6] | C | idem |
| Melhor conjunta | E4 Jev 84,7 [81,0; 88,2]; E6 Haiku 84,5; E5 Sonnet 84,1 | E | [estimation.md §A](../docs/results/final/estimation.md) |
| D-002: expor todas as tools da skill roteada (E9) | e2e 48,1% (+2,3 pp [0,0; 4,6] vs E9), ainda −7,4 pp [−11,5; −3,4] vs E0 | X | [exploratory_e2e.md](../docs/results/final/exploratory_e2e.md) |
| Por que o roteado perde para o nativo | 22 dos 40 casos em que só o E0 acerta têm **as mesmas chamadas** do E0; o E9 falha porque o rótulo de skill do roteador não é aceito | X | idem |

![E2E decomposição](figuras/final-e2e-decomposition.png)

*Figura 1. `e2e_success` por configuração, decomposto em primeira chamada, clarificação e
recuperação; barra = IC 95% do total (fonte: estimation.md §J).*

## O que não deu certo (resultados nulos e negativos)

- **Regex não generaliza:** escrito lendo os erros do dev, cai de 84,8% para 52,7% no teste **[C]**.
- **Cascatas não mostraram não inferioridade** ao Sonnet (H1, H2) **[C]**.
- **Engenharia de prompt não rendeu nada mensurável:** a regra de um erro-padrão escolheu P0 para
  Sonnet, Haiku, Jev e Qwen; a trilha otimizada ficou igual à canônica **[C]**.
- **Equivalência entre LLMs ficou inconclusiva** depois de Holm **[C]**.
- **Haiku não é mais barato que Sonnet** por caso roteado (US$ 5,23 vs 4,98/1k observados),
  porque o prompt do Haiku fica abaixo do mínimo de cache do Bedrock **[E]**.
- **O roteador piora o agente de ponta a ponta** (H3) **[C]**. A análise exploratória sugere
  que mais da metade da diferença vem de como o rótulo de skill do roteador é pontuado, e não
  do comportamento do executor (capítulo [07](07-ponta-a-ponta.md)). Essa hipótese precisa de
  um split novo para virar conclusão.

Custo total do estudo final (ledger): US$ 34,48 Bedrock + US$ 1,43 OpenRouter
([13](13-reprodutibilidade.md)).
