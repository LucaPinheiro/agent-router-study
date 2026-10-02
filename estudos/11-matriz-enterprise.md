# 11 · Matriz de decisão enterprise

> Fonte: [enterprise_matrix.md](../docs/results/final/enterprise_matrix.md) (gerada de
> estimation.md). **[E]** estimativa, sem teste: os vencedores de cada célula não são
> "significativamente melhores" que os vizinhos (ver capítulos [05](05-resultados-roteamento.md)
> e [06](06-cascatas.md)).

> **Fase 2:** a matriz com as opções gerenciadas do Bedrock (Ministral, Nemotron, Cohere, Titan)
> está em [addendum-a/enterprise_matrix.md](../docs/results/addendum-a/enterprise_matrix.md), lida
> no capítulo [14 §7](14-fase2-nuvem.md#7-leitura-enterprise-atualizada-e). A principal mudança: com
> SLO p95 < 2 s e teto ≥ US$ 0,5/1k, o Ministral 3 8B gerenciado (E6m) qualifica com 82,2%. A matriz
> abaixo é a da fase 1 e continua valendo para os candidatos da fase 1.

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
