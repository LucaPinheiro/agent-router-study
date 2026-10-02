# 11 · Matriz de decisão enterprise

> Fonte: [enterprise_matrix.md](../docs/results/final/enterprise_matrix.md) (gerada de
> estimation.md). **[E]** estimativa, sem teste: os vencedores de cada célula não são
> "significativamente melhores" que os vizinhos (ver capítulos [05](05-resultados-roteamento.md)
> e [06](06-cascatas.md)).

> **Fase 2:** a matriz com as opções gerenciadas do Bedrock (Ministral, Nemotron, Cohere, Titan)
> está em [addendum-a/enterprise_matrix.md](../docs/results/addendum-a/enterprise_matrix.md), lida
> no capítulo [14 §7](14-fase2-nuvem.md#7-leitura-enterprise-atualizada-e). A principal mudança: com
> SLO p95 < 2 s e teto ≥ US$ 0,5/1k, o Ministral 3 8B gerenciado (E6m) qualifica com 82,2%. A matriz
> abaixo é a da fase 1 e continua valendo para os candidatos da fase 1. A **matriz final**, com as
> opções gerenciadas e a dimensão do tamanho do catálogo (18 × 62 tools, Parte B), está na
> [seção 6](#6-fase-2-matriz-final-com-opções-gerenciadas-e-tamanho-do-catálogo).

## 1. Como ler

Para cada combinação de SLO de latência (p95 quente, benchmark `lat-*`), teto de custo de
roteamento (US$ por mil casos, regime observado) e acurácia conjunta mínima, a matriz mostra a
configuração qualificada com a maior acurácia. "Robusto" = os ICs 95% também cumprem as três
restrições. A acurácia é de **roteamento** (routing-only), não de ponta a ponta.

## 2. Candidatos

| Config | Onde | Conjunta % [IC 95%] | p95 ms | US$/1k |
|---|---|---|---|---|
| E4 Jev | API | 84,7 [81,0; 88,2] | 6.851 | 0,818 |
| E6 Haiku 4.5 | API | 84,5 [80,5; 88,3] | 5.919 | 5,228 |
| E5 Sonnet 5 | API | 84,1 [80,3; 87,8] | 10.994 | 4,981 |
| E9 regex → Jev → Sonnet | API | 81,8 [77,8; 85,6] | 9.892 | 0,989 |
| E8 regex → Sonnet | API | 81,5 [77,5; 85,3] | 7.956 | 4,351 |
| E6b Qwen3-8B | local | 79,9 [75,6; 84,0] | 11.983 | 0 |
| E7 regex → Jev | API | 79,9 [75,8; 84,0] | 7.129 | 0,727 |
| E10 classificador | local | 74,8 [70,2; 79,4] | 1.048 | 0 |
| E3 embedding | local | 73,6 [68,8; 78,2] | 710 | 0 |
| E11 híbrido | local | 72,8 [67,9; 77,4] | 1.037 | 0 |
| E1 regex | local | 52,7 [47,3; 57,9] | 0,4 | 0 |
| E2 BM25 | local | 49,0 [43,8; 54,2] | 7,2 | 0 |

## 3. Matriz (acurácia mínima 75% e 80%)

| SLO p95 \ teto de custo | US$ 0 | ≤ US$ 0,5 | ≤ US$ 2 | ≤ US$ 10 |
|---|---|---|---|---|
| < 50 ms | nenhuma | nenhuma | nenhuma | nenhuma |
| < 500 ms | nenhuma | nenhuma | nenhuma | nenhuma |
| < 2 s | nenhuma | nenhuma | nenhuma | nenhuma |
| < 10 s | nenhuma | nenhuma | **E4 Jev** 84,7%, robusto | **E4 Jev** 84,7%, robusto |

A tabela é a mesma para os pisos de 75% e 80%; com piso de **85%, nenhuma célula qualifica**.
"Nenhuma" é resultado, não dado faltando. Alternativas qualificadas nas células de E4: E7 e E9
(≤ US$ 2), E6, E7, E8 e E9 (≤ US$ 10) no piso de 75%; no piso de 80% o E7 sai das duas. Fonte: [enterprise_matrix.md](../docs/results/final/enterprise_matrix.md).

**Fora da grade:** a melhor opção local (US$ 0) é o E6b Qwen 79,9% com p95 de 12 s (acima do SLO de
10 s); abaixo de 2 s de p95, a melhor local é o E10 classificador, 74,8% (logo abaixo do piso de 75%).

## 4. Orientação por caso de uso

As recomendações abaixo combinam a matriz com o resultado de ponta a ponta (capítulo
[07](07-ponta-a-ponta.md)). São leituras deste estudo (um domínio, 18 tools), não regras gerais.

| Caso de uso | Recomendação | Base |
|---|---|---|
| **Agente conversacional com catálogo pequeno (≲ 20 tools)** | Sem roteador: deixe o executor carregar a skill (E0) | H3: E0 55,6% vs E9 45,8% **[C]** |
| **Precisa registrar/auditar a decisão de roteamento** (compliance, roteamento entre times) | E4 Jev, ou Sonnet se o Jev não for aceitável por política de fornecedor | 84–85% conjunta; Jev 6× mais barato |
| **Dados não podem sair da rede** | E6b Qwen3-8B local se a latência de ~10–12 s couber; senão E10 classificador (~1 s) | 79,9% / 74,8%; US$ 0 de API |
| **Tempo real (p95 < 2 s)** | Nenhum roteador testado chega a 75%. Use o classificador local como triagem e aceite ~75%, ou não roteie | matriz acima |
| **Catálogo que muda com frequência** | Roteadores guiados pelo catálogo (embedding, classificador, LLM, Jev); evite regex | RQ5: zero esforço leva a 83–96% nos casos da tool nova **[X]** |
| **Volume alto, custo de API dominante** | E4 Jev (P0+P6c reduz ~25% do custo, exploratório) | US$ 0,61–0,82/1k |
| **Tráfego baixo em Bedrock** | Cuidado com o cache: o Sonnet sobe de 4,95 para 7,69 US$/1k a 0,01 QPS (modelo); Haiku não tem cache neste tamanho de prompt | capítulo [08](08-economia.md) |
| **Primeira camada barata numa cascata** | Híbrido ou classificador, não regex | E12 83,0% **[X]**; regex sem ponto com risco ≤ 5% |

## 5. Limites da matriz

- Latência de uma máquina e uma rede, concorrência 1; a latência de API inclui fila no provedor.
- Custo local = 0 (hardware e energia fora).
- O custo do Jev é o reportado pelo OpenRouter; o produto pode mudar de preço e de modelos atendidos.
- A acurácia é de roteamento. Para o agente inteiro, o capítulo 07 mostra que nenhum roteador
  superou o nativo.

## 6. Fase 2: matriz final, com opções gerenciadas e tamanho do catálogo

> Fontes: fase 1 e Parte A, acima e no capítulo [14 §7](14-fase2-nuvem.md#7-leitura-enterprise-atualizada-e);
> Parte B (62 tools), [phase2-b/estimation.md §A e §D](../docs/results/phase2-b/estimation.md) e
> [phase2-b/primary.md](../docs/results/phase2-b/primary.md). **[E]**: o `phase2_b.py` não gera
> uma matriz; as células de 62 tools abaixo aplicam à mão a mesma regra da seção 1 (piso de
> acurácia conjunta, p95 quente do benchmark `lat-l-*`, custo observado) aos números dessas
> tabelas. Restrição da fase 2: nenhum modelo local; por isso o lado de 62 tools só tem opções de
> CPU, Bedrock e Jev.

### 6.1 Candidatos no catálogo de 62 tools (test-L)

| Config | Onde | Conjunta % [IC 95%] | p95 ms [IC 95%] | US$/1k [IC 95%] |
|---|---|---|---|---|
| E4 Jev | OpenRouter | 84,9 [81,1; 88,4] | 9193 [7450; 10554] | 0,977 [0,855; 1,109] |
| E9-L regex → Jev → Sonnet | OpenRouter + Bedrock | 82,7 [78,6; 86,6] | 9552 [7659; 12719] | 1,003 [0,859; 1,160] |
| E7-L regex → Jev | CPU + OpenRouter | 82,6 [78,3; 86,4] | 7542 [6735; 8858] | 0,864 [0,747; 0,996] |
| E6 Haiku 4.5 | Bedrock | 82,0 [77,7; 86,0] | 5278 [4881; 7287] | 7,154 [7,067; 7,240] |
| E6m Ministral 3 8B | Bedrock | 79,3 [74,7; 84,0] | 1383 [1360; 1410] | 0,694 [0,685; 0,704] |
| E6n Nemotron Nano 9B v2 | Bedrock | 73,0 [68,0; 78,0] | 1510 [1482; 1595] | 0,324 [0,320; 0,327] |
| E11 híbrido regex + sonda Titan | CPU + Bedrock | 62,3 [56,7; 67,7] | 277 [256; 351] | 0,000 |
| E3 embedding Titan v2 | Bedrock | 60,0 [54,7; 65,7] | 567 [206; 596] | 0,002 |
| E10 sonda sobre Titan | Bedrock | 59,0 [53,3; 64,7] | 280 [258; 355] | 0,002 |
| E1 regex | CPU | 56,3 [50,7; 62,0] | 2,04 [1,84; 2,49] | 0 |
| E2 BM25 | CPU | 50,3 [44,7; 56,0] | 28 [24; 32] | 0 |

O E12-L (híbrido → Jev → Sonnet, 83,0%) não tem bloco de latência e fica fora da grade.

### 6.2 Matriz com 62 tools (piso de 75%)

| SLO p95 \ teto de custo | US$ 0 | ≤ US$ 0,5 | ≤ US$ 2 | ≤ US$ 10 |
|---|---|---|---|---|
| < 50 ms | nenhuma | nenhuma | nenhuma | nenhuma |
| < 500 ms | nenhuma | nenhuma | nenhuma | nenhuma |
| < 2 s | nenhuma | nenhuma | **E6m** 79,3%, não robusto (IC inferior 74,7) | **E6m** 79,3%, não robusto |
| < 10 s | nenhuma | nenhuma | **E4 Jev** 84,9%, não robusto (IC do p95 até 10,6 s); robusto: E7-L 82,6% | **E4 Jev** 84,9%, não robusto; robustos: E6 82,0%, E7-L 82,6% |

Com piso de **80%**, a linha "< 2 s" fica vazia e o E4 continua nas duas células de "< 10 s",
sem alternativa robusta (os ICs inferiores do E7-L e do E6 ficam abaixo de 80). Com piso de
**85%**, nenhuma célula qualifica (o Jev fica em 84,9).

### 6.3 O que muda entre 18 e 62 tools

| Célula / pergunta | 18 tools (fase 1 + Parte A) | 62 tools (Parte B) |
|---|---|---|
| < 2 s, até US$ 2 | E6m Ministral 82,2%, robusto (piso 75%) | E6m Ministral 79,3%, **não robusto**; nada no piso de 80% |
| < 10 s, até US$ 2 | E4 Jev 84,7%, robusto | E4 Jev 84,9%, **não robusto** no p95 (cauda mais longa, prompt maior) |
| < 500 ms | nada com ≥ 75% | nada com ≥ 75% (melhor: E11, 62,3%) |
| Roteador vs nativo, ponta a ponta | nativo melhor (H3) **[C]** | sem diferença detectável: −0,3 pp [−4,0; 3,3], o IC inclui 0, sem afirmação direcional **[C, H1-L]**; equivalência não testada (S2 inconclusivo) |
| Custo por turno do roteado / nativo | 0,909 **[C]** | 1,101 **[C]** |

### 6.4 Orientação final por tamanho de catálogo e caso de uso

| Situação | Recomendação | Base |
|---|---|---|
| **Catálogo pequeno (≲ 20 tools), qualidade do agente** | Sem roteador (E0) | H3 **[C]**; inalterado |
| **Catálogo grande (~60 tools), qualidade do agente** | Sem roteador (E0), o padrão mais simples: com 62 tools o roteador não mostrou perda detectável de ponta a ponta e custou 10% mais por turno; roteador só se houver outro motivo | H1-L: sem diferença detectável: −0,3 pp [−4,0; 3,3], o IC inclui 0, sem afirmação direcional **[C, H1-L]**; equivalência não testada (S2 inconclusivo); custo 1,101× **[C]** |
| **Qualquer tamanho, decisão de roteamento auditável** | E4 Jev sozinho | 84,7% (18) e 84,9% (62); não inferior ao Haiku com 62 tools **[C, H3-L]**; cobertura a risco ≤ 5%: com 62 tools, 68,7%, a maior (cascatas do Jev: E7-L 67,9%, E9-L 67,3%, E12-L 64,9%); com 18 tools, 55,9%, abaixo do Sonnet (61,5%) e do E8 (59,6%) **[E]** |
| **Qualquer tamanho, p95 < 2 s, sem modelo local** | E6m Ministral 3 8B no Bedrock | 82,2% com 18 tools **[C, A1]**; 79,3% com 62 tools, abaixo do Haiku sem NI demonstrada **[C, H2-L]** |
| **Sem cache de prompt no executor** (outro provedor, tráfego esparso) | O roteador passa a economizar com 62 tools | 24,46 vs 39,95 US$/1k turnos sem cache **[E]** |
| **Executor com teto de contexto** | Roteador top-2 | 10.067 vs 18.254 tokens de prompt por turno com 62 tools **[E]** |
| **Embedding / sonda gerenciados como roteador** | Não recomendado | 51–56% com 18 tools **[C, A3/A4]**; 59–60% com 62 **[E]**; a sonda perde 25,9 pp para o Jev **[C, S7]** |
| **Regex como primeira camada** | Só atrás de um limiar alto e com o Jev atrás | cobre 60% do test-L a 91,1% de acerto de skill, mas cai 26,4 pp como decisor único **[C, S3]** |
| **Catálogo crescendo** | Medir antes: no mesmo conjunto de casos, 44 tools confundíveis a mais custaram 9,6 pp ao Jev | X2 **[X]**, capítulo [15 §11](15-fase2-catalogo-grande.md#11-18--62-tools-o-tamanho-do-catálogo-x) |

