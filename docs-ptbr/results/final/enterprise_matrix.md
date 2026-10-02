# Matriz de decisão enterprise (test-v2, só routing)

Para cada SLO de latência (p95 warm, benchmark dedicado lat-*), teto de custo de routing (US$ por 1 000 casos, regime observado) e acurácia joint mínima (ITT), a configuração qualificada com a maior acurácia joint (empates: menor custo). A qualificação usa estimativas pontuais; `robust` = os ICs de 95% também satisfazem as três restrições (limite inferior do IC do joint >= piso, limite superior do IC do p95 < SLO, limite superior do IC do custo <= teto). Apenas estimação (sem teste); as diferenças pareadas entre os principais candidatos estão em primary.md / secondary.md e ficam, em sua maioria, dentro de poucos pp com ICs sobrepostos, então o vencedor de uma célula não é 'significativamente o melhor'.

Ressalvas: joint só de routing (não sucesso e2e: ver estimation.md J, onde toda configuração roteada fica abaixo do executor nativo E0); latência medida em uma máquina / uma rede com concorrência 1 (a latência de API inclui o enfileiramento do provedor); o custo de modelo local é contado como US$ 0 (hardware e energia excluídos); o custo do Jev é o preço reportado pelo OpenRouter (sem preço de tabela).

## Candidatos

| config | onde | joint % [IC 95%] | p95 warm ms [IC 95%] | US$/1k observado [IC 95%] | US$/1k tabela sem cache |
|---|---|---|---|---|---|
| E4 Jev | API | 84.7 [81.0, 88.2] | 6851.1 [6303.0, 7531.2] | 0.818 [0.739, 0.900] | 0.818 |
| E6 Haiku 4.5 | API | 84.5 [80.5, 88.3] | 5918.7 [5026.7, 6861.0] | 5.228 [5.154, 5.299] | 5.228 |
| E5 Sonnet 5 | API | 84.1 [80.3, 87.8] | 10994.5 [9333.1, 13065.4] | 4.981 [4.909, 5.052] | 11.820 |
| E9 regex->Jev->Sonnet | API | 81.8 [77.8, 85.6] | 9892.1 [6902.6, 11874.4] | 0.989 [0.868, 1.116] | 1.351 |
| E8 regex->Sonnet | API | 81.5 [77.5, 85.3] | 7955.6 [7149.5, 14653.2] | 4.351 [4.258, 4.448] | 10.107 |
| E6b Qwen3-8B local | local | 79.9 [75.6, 84.0] | 11983.2 [10393.8, 12264.2] | 0.000 [0.000, 0.000] | 0.000 |
| E7 regex->Jev | API | 79.9 [75.8, 84.0] | 7128.9 [5785.1, 8469.8] | 0.727 [0.654, 0.805] | 0.727 |
| E10 classifier (probe) | local | 74.8 [70.2, 79.4] | 1048.1 [635.4, 4633.5] | 0.000 [0.000, 0.000] | 0.000 |
| E3 embedding (qwen3-emb 8B) | local | 73.6 [68.8, 78.2] | 710.2 [574.0, 1491.5] | 0.000 [0.000, 0.000] | 0.000 |
| E11 hybrid regex+classifier | local | 72.8 [67.9, 77.4] | 1036.7 [633.6, 4624.5] | 0.000 [0.000, 0.000] | 0.000 |
| E1 regex | local | 52.7 [47.3, 57.9] | 0.4 [0.3, 0.5] | 0.000 [0.000, 0.000] | 0.000 |
| E2 BM25 | local | 49.0 [43.8, 54.2] | 7.2 [5.6, 8.2] | 0.000 [0.000, 0.000] | 0.000 |

## Acurácia joint mínima 75%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 500 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 2000 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 10000 ms | nenhuma se qualifica | nenhuma se qualifica | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (também: E7, E9) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (também: E6, E7, E8, E9) |

## Acurácia joint mínima 80%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 500 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 2000 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 10000 ms | nenhuma se qualifica | nenhuma se qualifica | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (também: E9) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robust (também: E6, E8, E9) |

## Acurácia joint mínima 85%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 500 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 2000 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |
| p95 < 10000 ms | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica | nenhuma se qualifica |

## Leitura

- Maior estimativa pontual de joint entre as configurações com benchmark: E4 Jev (84.7%).
- Melhor configuração local (US$ 0): E6b Qwen3-8B local 79.9% com p95 11983 ms; melhor local abaixo de p95 2 s: E10 classifier (probe) 74.8% com p95 1048 ms.
- Células marcadas como `nenhuma se qualifica` são um resultado (nenhuma configuração com benchmark atende às três restrições), não dados faltantes.
