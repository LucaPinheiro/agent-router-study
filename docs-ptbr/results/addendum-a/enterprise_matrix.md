# Matriz de decisão enterprise com as opções gerenciadas (Parte A, test-v2, só roteamento)

> Tradução pt-BR de [`docs/results/addendum-a/enterprise_matrix.md`](../../../docs/results/addendum-a/enterprise_matrix.md). Números idênticos aos do original; em caso de divergência, vale o original em inglês.

ESTIMAÇÃO / descritivo (sem teste além da família A). Gerado por `scripts/analysis/addendum_a.py`.

## 1. Regra de qualificação pré-registrada (prereg-v2a §3)

Uma opção gerenciada **qualifica** num orçamento de latência quando o limite **superior** do IC 95% do seu p95 quente fica abaixo do orçamento **e** a sua conjunta não é inferior à do seu par local: para os modelos 8B, a regra de A1/A2 (limite inferior do IC 95% pareado de Δ > −3 pp); para os embedders, o IC de A3/A4 exclui uma perda maior que 3 pp (mesmo limite). E10c/E10t ficam fora da família A: a condição de acurácia deles usa o Δ de estimação contra a sonda local E10 (marcado). Orçamentos: os SLOs da matriz da fase 1.

**Ressalva de janela (prereg-v2a §3, obrigatória):** as linhas locais são os blocos lat-* da fase 1, medidos numa janela de tempo diferente da dos blocos da Parte A; o mesmo Mac (M5 Pro 48 GB) no lado local, Bedrock `sa-east-1` (Jev: OpenRouter) chamado desse Mac no lado gerenciado. A deriva é estimada pelas âncoras gerenciadas (Jev, Haiku 4.5) rodadas de novo nas duas janelas; é reportada, nunca subtraída.

| gerenciado | par local | base da acurácia | Δ conjunta pp vs par [IC 95%] | não inferior (lo > −3 pp) | p95 quente ms [IC 95%] (Parte A) | p95 < 50 ms | p95 < 500 ms | p95 < 2000 ms | p95 < 10000 ms | p95 quente do par ms [IC 95%] |
|---|---|---|---|---|---|---|---|---|---|---|
| E6m | E6b | A1 (confirmatório) | 2.3 [-2.0, 6.6] | sim | 1584 [1124, 1958] | não (p95) | não (p95) | **qualifica** | **qualifica** | 11983 [10394, 12264] (fase 1) |
| E6n | E6b | A2 (confirmatório) | -2.9 [-7.4, 1.7] | não | 1465 [1384, 1744] | não (p95, acurácia) | não (p95, acurácia) | não (acurácia) | não (acurácia) | 11983 [10394, 12264] (fase 1) |
| E3c | E3 | A3 (confirmatório) | -19.2 [-24.6, -14.0] | não | 1665 [1466, 2927] | não (p95, acurácia) | não (p95, acurácia) | não (p95, acurácia) | não (acurácia) | 710 [574, 1492] (fase 1) |
| E3t | E3 | A4 (confirmatório) | -17.8 [-23.2, -12.6] | não | 610 [416, 910] | não (p95, acurácia) | não (p95, acurácia) | não (acurácia) | não (acurácia) | 710 [574, 1492] (fase 1) |
| E10c | E10 | Δ de estimação vs E10 (sem teste) | -19.5 [-24.6, -14.6] | não | 1522 [1386, 2128] | não (p95, acurácia) | não (p95, acurácia) | não (p95, acurácia) | não (acurácia) | 1048 [635, 4634] (fase 1) |
| E10t | E10 | Δ de estimação vs E10 (sem teste) | -23.8 [-29.2, -18.3] | não | 506 [261, 907] | não (p95, acurácia) | não (p95, acurácia) | não (acurácia) | não (acurácia) | 1048 [635, 4634] (fase 1) |

Pares locais nos mesmos orçamentos (limite superior do IC do p95 abaixo do orçamento; janela da fase 1):

| par local | bloco lat | p95 quente ms [IC 95%] | p95 < 50 ms | p95 < 500 ms | p95 < 2000 ms | p95 < 10000 ms |
|---|---|---|---|---|---|---|
| E6b | E6b Qwen3-8B local | 11983 [10394, 12264] | não | no | não | no |
| E3 | E3 qwen3-emb 8B local | 710 [574, 1492] | não | no | cabe | fits |
| E10 | E10 sonda local | 1048 [635, 4634] | não | no | não | cabe |

### O que qualifica em cada orçamento de latência

- **p95 < 50 ms:** opções gerenciadas que qualificam pela regra do prereg-v2a: nenhuma; pares locais cujo limite superior do IC do p95 cabe (janela da fase 1): nenhum.
- **p95 < 500 ms:** opções gerenciadas que qualificam pela regra do prereg-v2a: nenhuma; pares locais cujo limite superior do IC do p95 cabe (janela da fase 1): nenhum.
- **p95 < 2000 ms:** opções gerenciadas que qualificam pela regra do prereg-v2a: E6m; pares locais cujo limite superior do IC do p95 cabe (janela da fase 1): E3.
- **p95 < 10000 ms:** opções gerenciadas que qualificam pela regra do prereg-v2a: E6m; pares locais cujo limite superior do IC do p95 cabe (janela da fase 1): E3, E10.

## 2. Lógica da matriz da fase 1 refeita com as opções gerenciadas acrescentadas

Mesma lógica de `docs/results/final/enterprise_matrix.md` (`final_enterprise.matrix`): para cada SLO de latência (p95 quente), teto de custo de roteamento (US$/1k, regime observado) e conjunta mínima (ITT), a configuração qualificada com a maior estimativa pontual de conjunta (empates: menor custo); as estimativas pontuais qualificam, `robust` = os ICs também cumprem as três restrições. Os candidatos da fase 1 mantêm os seus números da fase 1 (acurácia, custo e latência da janela da fase 1); os seis braços gerenciados usam as suas runs da Parte A e a latência da janela da Parte A (coluna de janela). Custo local contado como US$ 0 (hardware e energia fora); o custo do Jev é o preço reportado pelo OpenRouter.

**Ressalva de janela (prereg-v2a §3, obrigatória):** as linhas locais são os blocos lat-* da fase 1, medidos numa janela de tempo diferente da dos blocos da Parte A; o mesmo Mac (M5 Pro 48 GB) no lado local, Bedrock `sa-east-1` (Jev: OpenRouter) chamado desse Mac no lado gerenciado. A deriva é estimada pelas âncoras gerenciadas (Jev, Haiku 4.5) rodadas de novo nas duas janelas; é reportada, nunca subtraída.

### Candidatos

| config | onde | janela de latência | conjunta % [IC 95%] | p95 quente ms [IC 95%] | US$/1k observado [IC 95%] | US$/1k tabela sem cache |
|---|---|---|---|---|---|---|
| E4 Jev | API | fase 1 | 84.7 [81.0, 88.2] | 6851.1 [6303.0, 7531.2] | 0.8176 [0.7388, 0.9004] | 0.8176 |
| E6 Haiku 4.5 | API | fase 1 | 84.5 [80.5, 88.3] | 5918.7 [5026.7, 6861.0] | 5.2280 [5.1538, 5.2994] | 5.2280 |
| E5 Sonnet 5 | API | fase 1 | 84.1 [80.3, 87.8] | 10994.5 [9333.1, 13065.4] | 4.9805 [4.9086, 5.0519] | 11.8199 |
| E6m Ministral 3 8B (gerenciado) | API | Parte A | 82.2 [77.9, 86.2] | 1584.5 [1123.8, 1957.7] | 0.4413 [0.4342, 0.4484] | 0.4413 |
| E9 regex->Jev->Sonnet | API | fase 1 | 81.8 [77.8, 85.6] | 9892.1 [6902.6, 11874.4] | 0.9889 [0.8682, 1.1159] | 1.3510 |
| E8 regex->Sonnet | API | fase 1 | 81.5 [77.5, 85.3] | 7955.6 [7149.5, 14653.2] | 4.3514 [4.2582, 4.4484] | 10.1071 |
| E6b Qwen3-8B local | local | fase 1 | 79.9 [75.6, 84.0] | 11983.2 [10393.8, 12264.2] | 0.0000 [0.0000, 0.0000] | 0.0000 |
| E7 regex->Jev | API | fase 1 | 79.9 [75.8, 84.0] | 7128.9 [5785.1, 8469.8] | 0.7271 [0.6536, 0.8051] | 0.7271 |
| E6n Nemotron Nano 9B v2 (gerenciado) | API | Parte A | 77.1 [72.5, 81.4] | 1465.1 [1384.5, 1744.1] | 0.2225 [0.2201, 0.2248] | 0.2225 |
| E10 classificador (sonda) | local | fase 1 | 74.8 [70.2, 79.4] | 1048.1 [635.4, 4633.5] | 0.0000 [0.0000, 0.0000] | 0.0000 |
| E3 embedding (qwen3-emb 8B) | local | fase 1 | 73.6 [68.8, 78.2] | 710.2 [574.0, 1491.5] | 0.0000 [0.0000, 0.0000] | 0.0000 |
| E11 híbrido regex+classificador | local | fase 1 | 72.8 [67.9, 77.4] | 1036.7 [633.6, 4624.5] | 0.0000 [0.0000, 0.0000] | 0.0000 |
| E3t roteador Titan v2 (gerenciado) | API | Parte A | 55.9 [50.4, 61.0] | 609.6 [416.0, 910.0] | 0.0014 [0.0013, 0.0014] | 0.0014 |
| E10c sonda sobre vetores Cohere (gerenciado) | API | Parte A | 55.3 [50.1, 60.5] | 1522.3 [1386.3, 2127.9] | 0.0072 [0.0068, 0.0075] | 0.0072 |
| E3c roteador Cohere Embed v4 (gerenciado) | API | Parte A | 54.4 [49.3, 59.6] | 1665.0 [1465.5, 2926.5] | 0.0090 [0.0085, 0.0095] | 0.0090 |
| E1 regex | local | fase 1 | 52.7 [47.3, 57.9] | 0.4 [0.3, 0.5] | 0.0000 [0.0000, 0.0000] | 0.0000 |
| E10t sonda sobre vetores Titan (gerenciado) | API | Parte A | 51.0 [45.6, 56.2] | 506.4 [260.8, 906.6] | 0.0012 [0.0011, 0.0013] | 0.0012 |
| E2 BM25 | local | fase 1 | 49.0 [43.8, 54.2] | 7.2 [5.6, 8.2] | 0.0000 [0.0000, 0.0000] | 0.0000 |

### Acurácia conjunta mínima 75%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 500 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 2000 ms | nenhuma qualifica | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · robusto (também: E6n) | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · robusto (também: E6n) | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · robusto (também: E6n) |
| p95 < 10000 ms | nenhuma qualifica | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · robusto (também: E6n) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robusto (também: E7, E9, E6m, E6n) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robusto (também: E6, E7, E8, E9, E6m, E6n) |

### Acurácia conjunta mínima 80%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 500 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 2000 ms | nenhuma qualifica | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · não robusto | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · não robusto | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · não robusto |
| p95 < 10000 ms | nenhuma qualifica | **E6m** 82.2 [77.9, 86.2] · p95 1584 ms · US$ 0.44/1k · não robusto | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robusto (também: E9, E6m) | **E4** 84.7 [81.0, 88.2] · p95 6851 ms · US$ 0.82/1k · robusto (também: E6, E8, E9, E6m) |

### Acurácia conjunta mínima 85%

| SLO de latência \ teto de custo | <= US$ 0/1k | <= US$ 0.5/1k | <= US$ 2/1k | <= US$ 10/1k |
|---|---|---|---|---|
| p95 < 50 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 500 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 2000 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |
| p95 < 10000 ms | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica | nenhuma qualifica |

Células marcadas `nenhuma qualifica` são um resultado (nenhuma configuração medida cumpre as três restrições), não dado faltando.
