# Estudo de prompt dos roteadores: trilha canônica (A) e trilha ajustada por modelo (B)

Plano: `.omc/plans/prompt-apex.md` (decisão do usuário em 2026-09-30). Todo roteador do tipo LLM é avaliado
com um prompt compartilhado (a trilha **canônica**) e com o seu próprio melhor prompt (a trilha
**ajustada**, *tuned*). Os dois prompts foram escolhidos no split de dev. A trilha canônica é a tabela principal do
estudo: com o prompt fixo, uma diferença entre roteadores vem do modelo. A
trilha ajustada mostra o teto de cada roteador e quanto a engenharia de prompt acrescenta por modelo.

| roteador | experimento | modelo | onde roda |
|---|---|---|---|
| llm (Sonnet 5) | E5 | `global.anthropic.claude-sonnet-5` | Bedrock |
| llm (Haiku 4.5) | E6 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock |
| llm_local (Qwen3-8B) | E6b | `qwen3:8b-q8_0` (num_ctx 8192) | Ollama |
| jev | E4 | `typesafe/jev-router` | OpenRouter |

## Status: seleção D6 sobre o código corrigido (2026-10-01): Sonnet 5, Haiku 4.5, Jev, Qwen3-8B

A seleção está em `config/prompt_selection.yaml`, escrita por
`scripts/analysis/select_prompts.py` e aplicada a `config/experiments` por
`apply_prompt_selection.py` segundo as regras de
`docs/decisions/2026-10-01-calibration-and-prompts.md`. O Qwen3-8B (E6b) foi adicionado com o mesmo
procedimento (seção "Qwen3-8B (E6b)" abaixo) e a escolha canônica foi recalculada sobre os quatro
modelos: **P0 nas duas trilhas para todos os modelos**, então a trilha B == trilha A em todos os casos e não existe
cópia `*_tuned.yaml`.

### Qwen3-8B (E6b), mesmo procedimento (2026-10-01)

`--concurrency 1`, um modelo Ollama residente (`qwen3:8b-q8_0`, num_ctx 8192, thinking desligado),
ITT, arquivos `results/prompt_apex_v2/e6b_{r1,r2,full}.json`.

- **Rodada 1** (subconjunto de 60 casos, os 8 modificadores isolados): podados P0+P6c (78.3, 0/4 vs P0),
  P0+P2k2 (81.7, 1/3) e P0+P5 (81.7, 1/3), cada um abaixo de −1 SE do líder do subconjunto, P0+P3 (86.7).
  Mantidos: P0 85.0, P0+P1 85.0, P0+P3 86.7, P0+P4 86.7, P0+P6 83.3.
- **Rodada 2** (líder P3 combinado com cada um dos outros sobreviventes): P0+P3+P4 83.3, P0+P3+P1 85.0,
  P0+P3+P6 83.3; nenhum podado.
- **Dev completo, reduzido pelo lead (orçamento de tempo; results/freeze/DECISIONS.log)**: só P0, P0+P3 e
  P0+P4. P0+P5 foi iniciado como candidato canônico, mas travou 6,5 h num deadlock do lado do cliente
  e foi encerrado; ele já tinha sido podado para o Qwen na rodada 1. P0+P1, P0+P6 e as combinações da rodada 2
  não rodaram no dev completo (truncados por orçamento, como o P6 do Haiku).

| variante | CV joint | b+/c− vs P0 | p50 ms | tok saída | err % |
|---|---|---|---|---|---|
| P0 | 82.2 ± 3.8 | 0/0 | 10017 | 76 | 0.0 |
| P0+P3 | 82.1 ± 5.8 | 2/2 | 9919 | 78 | 0.0 |
| P0+P4 | 84.2 ± 5.1 | 8/5 | 10839 | 104 | 0.0 |

- **Ajustada = P0** (regra de um SE; P0+P4 está +2.0 dentro de um SE, 8/5 discordantes). Joint em CV aninhada
  81.5 ± 3.2 (escolhe P0 ×4, P0+P4 ×1). Sensibilidade com argmax puro: P0+P4.
- **Calibração**: ECE com cross-fitting skill 0.045 → 0.041, tool 0.116 → 0.032, então os dois mapas
  são aplicados (regra de decisão `ece_cal < ece_raw`).
- **Canônica sobre os quatro modelos** (candidatos = variantes rodadas no dev completo para todos os modelos):
  P0 80.2, P0+P4 81.2 → **P0** (um SE; todo fold aninhado escolhe P0). P0+P5 não é candidato
  da regra de quatro modelos porque não rodou no dev completo do Qwen; nos três modelos em que
  rodou, ficou em 79.5 contra 79.5 do P0 (um SE → P0), então não pode mudar a escolha.

**Por que a primeira passada foi descartada.** Três bugs a enviesaram, então nenhum de seus números é reaproveitado:

- Erros de throttling do Bedrock foram pontuados como abstenções, o que podou P2k2, P3 e P4 do Haiku.
- O guia de skills do P1 renderizava regras falsas (corrigido em 3c9e261).
- O tuner enviava `loaded_skill=None` em `__global__` (corrigido em 69209dd).

O texto do catálogo também mudou (F8 e F10, hash do catálogo `785db6efc779` → `33f89f3db4f5`). Isso
mudou todos os prompts, então todas as decisões foram pagas de novo.

### Resultado: P0 nas duas trilhas para os três modelos

| modelo | canônica | ajustada | joint em CV aninhada (ajustada) | melhor bruto no dev completo (não selecionado) |
|---|---|---|---|---|
| Sonnet 5 | P0 | P0 | 77.5 ± 9.8 | P0+P4 80.2 (5 casos ganhos, 1 perdido vs P0) |
| Haiku 4.5 | P0 | P0 | 81.5 ± 3.8 | P0+P4 83.5 (3 ganhos, 2 perdidos) |
| Jev | P0 | P0 | 78.2 ± 9.4 | P0+P5 80.9 (8/4); P0+P6c 80.9 (6/2) |

- **Nenhum modificador supera o P0 por mais de um erro padrão** (5 folds × 151 casos). A regra de um SE
  portanto mantém o prompt mais simples todas as vezes.
  - O SE da melhor variante fica entre 2.2 e 6.2 pontos: Haiku 2.2, Sonnet 3.7, Jev 6.2 (P5).
  - O maior ganho no dev completo é de +2.7 pontos (Sonnet com P4). Ele vem de 6 casos discordantes,
    5 a 1, então um teste exato de sinais dá p ≈ 0.22.
- **Trilha canônica.** Os candidatos são as variantes rodadas no dev completo para todos os modelos: P0, P4
  e P5. A média de CV joint delas nos três modelos é P0 79.5, P0+P4 80.2 e P0+P5 79.5. P0 está
  dentro de um SE e é o mais simples, e cada fold externo da CV aninhada também escolhe P0.
- **A trilha ajustada é igual à trilha canônica para os três modelos.** Com essa regra, a engenharia
  de prompt não acrescenta nada mensurável em 151 casos. Esse é o achado para a RQ "ajustada vs
  canônica".
- **Sensibilidade: argmax puro em vez da regra de um SE** (CV aninhada, melhor média por fold):

  | modelo | joint em CV aninhada | escolhas |
  |---|---|---|
  | Sonnet | 80.2 ± 7.5 | P4 nos 5 folds |
  | Haiku | 82.2 ± 3.2 | P4 em 4 folds |
  | Jev | 78.9 ± 10.4 | P5 e P6c |

  Se o lead preferir a regra de argmax, de maior variância, a trilha ajustada seria Sonnet P0+P4
  e Haiku P0+P4. O YAML registra `raw_best` para isso.
- **Custo do Jev.** P0+P6c (ranking compacto) custa 35% menos que P0 ($0.60 contra $0.93 por 1k
  casos), reduz o p50 em 20% (4.0 s contra 5.0 s) e o p95 em 35%, com acurácia igual ou melhor
  (80.9 contra 78.2). Ele não é selecionado porque acrescenta um modificador e o ganho está dentro de
  um SE. É a escolha mais barata a se ter em mente para uma variante de custo de E4/E7.

### Por modelo × trilha (dev completo, 151 casos; seleção conforme escrita no YAML)

As colunas:

- joint em CV aninhada: o procedimento de seleção, executado dentro da CV;
- CV joint fixa: a variante escolhida sozinha;
- ECE: com cross-fitting, com o mapa ajustado em 4 folds e aplicado ao fold separado;
- $/1k: o custo de roteamento por 1000 casos (chamada de skill + tool);
- tokens estáticos e de leitura de cache: por chamada de roteamento.

| modelo | trilha | variante | joint em CV aninhada | CV joint fixa | ECE skill bruto→cal | ECE tool bruto→cal | $/1k | p50 / p95 ms | tok estáticos | tok lidos do cache | err % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Sonnet 5 | canônica | P0 | 77.5 ± 9.8 | 77.5 ± 9.8 | 0.111→0.091 | 0.036→0.056 | 5.97 | 5640 / 9403 | 2119 | 1746 | 0.0 |
| Sonnet 5 | ajustada | P0 | 77.5 ± 9.8 | 77.5 ± 9.8 | 0.111→0.091 | 0.036→0.056 | 5.97 | 5640 / 9403 | 2119 | 1746 | 0.0 |
| Haiku 4.5 | canônica | P0 | 82.8 ± 3.3 | 82.8 ± 3.3 | 0.058→0.063 | 0.055→0.061 | 5.32 | 3319 / 5066 | 1826 | 0 | 0.0 |
| Haiku 4.5 | ajustada | P0 | 81.5 ± 3.8 | 82.8 ± 3.3 | 0.058→0.063 | 0.055→0.061 | 5.32 | 3319 / 5066 | 1826 | 0 | 0.0 |
| Jev | canônica | P0 | 78.2 ± 9.4 | 78.2 ± 9.4 | 0.063→0.024 | 0.047→0.058 | 0.93 | 5006 / 12455 | 1107 | 784 | 0.7 |
| Jev | ajustada | P0 | 78.2 ± 9.4 | 78.2 ± 9.4 | 0.063→0.024 | 0.047→0.058 | 0.93 | 5006 / 12455 | 1107 | 784 | 0.7 |

- **Calibração.** Mapas isotônicos por estágio são ajustados em todo o dev e escritos no YAML.
  Com cross-fitting, eles ajudam só em alguns casos:
  - ajudam o estágio de skill do Sonnet (0.111 → 0.091) e o estágio de skill do Jev (0.063 → 0.024);
  - pioram levemente o estágio de tool do Sonnet (0.036 → 0.056), o Haiku (0.058/0.055 → 0.063/0.061)
    e o estágio de tool do Jev (0.047 → 0.058). Essas confianças brutas já estão bem calibradas, e
    151 casos são poucos demais para o mapa.

  O lead decide se aplica um mapa a um estágio em que ele piora. O YAML tem `ece_raw` e
  `ece_cal` por estágio.
- Erros (ITT): no máximo 1 linha com falha por ponto do dev completo (0.7%), todas falhas de parse que
  persistiram depois das novas tentativas. Uma variante teve mais de 2% de linhas com falha: Jev P0 no subconjunto
  (2 de 60). Toda grade do Jev e do Sonnet com alguma falha foi re-executada antes da pontuação. O cache de
  respostas serve os sucessos, então só as falhas foram pagas de novo. A primeira passada de cada run é mantida
  como `*_pass1.json`.

### Log da busca (o que rodou, e em quais casos)

O procedimento para cada modelo:

1. A rodada 1 rodou num subconjunto estratificado de 60 casos com seed 0. Ela pontuou o P0 e cada
   modificador isolado: P1, P2k2, P3, P4, P5, P6 e P6c.
   - O Bedrock rodou primeiro P0, P6c, P1, P2k2, P3 e P4.
   - P6 e P5 foram adicionados depois, quando o orçamento permitiu. Seus veredictos são no mesmo
     subconjunto.
2. A poda usou só os casos sem erro para todas as variantes da rodada. Uma variante
   só foi descartada quando sua diferença pareada de joint em relação ao líder do subconjunto ficou abaixo de −1 SE,
   onde SE = sd(diferença por caso)/√n. P0 nunca é descartado.
3. A rodada 2 combinou os modificadores que sobreviveram. Só o Jev teve mais de um, e rodou
   P6c+P5 e P6c+P2k2.
4. Os sobreviventes foram para o dev completo, onde só os 91 casos restantes são novos.
5. Os candidatos canônicos são as variantes que sobreviveram em pelo menos 2 dos 3 modelos: P0, P4
   e P5. Eles rodaram no dev completo para todos os modelos, incluindo o Jev P4, que tinha sido podado no
   subconjunto do próprio Jev.
6. Truncado por orçamento: o P6 do Haiku sobreviveu ao seu subconjunto, mas não rodou no dev completo, porque o
   orçamento do Bedrock tinha acabado. No subconjunto ele ficou em 80.0 contra 83.3 do P0, 1 ganho e 3 perdidos.

"b+/c−" conta os casos discordantes contra o P0: a variante certa e o P0 errado, depois o
inverso.

### Variantes no dev completo por modelo (CV joint de ponto fixo; discordantes vs P0 = (+, −))

| modelo | variante | CV joint | b+/c− vs P0 | $/1k | p50 ms | tok saída | err % |
|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 77.5 ± 9.8 | 0/0 | 5.97 | 5640 | 157 | 0.0 |
| Sonnet 5 | P0+P4 | 80.2 ± 7.5 | 5/1 | 6.46 | 6126 | 195 | 0.0 |
| Sonnet 5 | P0+P5 | 76.9 ± 7.4 | 4/5 | 5.34 | 5733 | 156 | 0.7 |
| Haiku 4.5 | P0 | 82.8 ± 3.3 | 0/0 | 5.32 | 3319 | 148 | 0.0 |
| Haiku 4.5 | P0+P4 | 83.5 ± 4.5 | 3/2 | 5.70 | 3793 | 175 | 0.0 |
| Haiku 4.5 | P0+P5 | 80.8 ± 5.2 | 1/4 | 5.40 | 3389 | 148 | 0.0 |
| Jev | P0 | 78.2 ± 9.4 | 0/0 | 0.93 | 5006 | 225 | 0.7 |
| Jev | P0+P6c | 80.9 ± 9.6 | 6/2 | 0.60 | 4010 | 118 | 0.0 |
| Jev | P0+P4 | 76.9 ± 9.7 | 5/7 | 0.83 | 5336 | 223 | 0.7 |
| Jev | P0+P1 | 78.9 ± 11.9 | 3/2 | 0.96 | 5370 | 230 | 0.0 |
| Jev | P0+P2k2 | 80.1 ± 8.9 | 5/2 | 0.91 | 4823 | 209 | 0.0 |
| Jev | P0+P5 | 80.9 ± 12.5 | 8/4 | 0.77 | 5498 | 230 | 0.0 |
| Jev | P0+P6c+P5 | 78.9 ± 11.6 | 7/6 | 0.50 | 4429 | 116 | 0.0 |

### Poda no subconjunto (60 casos, sem erro para todas as variantes)

| modelo | variante | joint | Δ vs líder | SE | podada | b+/c− vs P0 | erros |
|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 79.7 | -5.1 | 2.9 | não | -/- | 0 |
| Sonnet 5 | P0+P6c | 81.4 | -3.4 | 2.4 | sim | 2/1 | 0 |
| Sonnet 5 | P0+P1 | 79.7 | -5.1 | 2.9 | sim | 2/2 | 0 |
| Sonnet 5 | P0+P2k2 | 78.0 | -6.8 | 3.3 | sim | 1/2 | 0 |
| Sonnet 5 | P0+P3 | 79.7 | -5.1 | 2.9 | sim | 1/1 | 0 |
| Sonnet 5 | P0+P4 | 84.8 | 0.0 | 0.0 | não | 3/0 | 0 |
| Sonnet 5 | P0+P6 | 81.4 | -3.4 | 2.4 | sim | 2/1 | 0 |
| Sonnet 5 | P0+P5 | 83.0 | -1.7 | 1.7 | não | 3/1 | 1 |
| Haiku 4.5 | P0 | 83.3 | 0.0 | 0.0 | não | -/- | 0 |
| Haiku 4.5 | P0+P6c | 78.3 | -5.0 | 3.7 | sim | 1/4 | 0 |
| Haiku 4.5 | P0+P1 | 78.3 | -5.0 | 2.8 | sim | 0/3 | 0 |
| Haiku 4.5 | P0+P2k2 | 80.0 | -3.3 | 2.3 | sim | 0/2 | 0 |
| Haiku 4.5 | P0+P3 | 80.0 | -3.3 | 2.3 | sim | 0/2 | 0 |
| Haiku 4.5 | P0+P4 | 83.3 | 0.0 | 2.4 | não | 1/1 | 0 |
| Haiku 4.5 | P0+P6 | 80.0 | -3.3 | 3.3 | não | 1/3 | 0 |
| Haiku 4.5 | P0+P5 | 81.7 | -1.7 | 2.9 | não | 1/2 | 0 |
| Jev | P0 | 79.7 | -5.1 | 3.8 | não | -/- | 0 |
| Jev | P0+P6c | 84.8 | 0.0 | 0.0 | não | 5/1 | 0 |
| Jev | P0+P6 | 79.7 | -5.1 | 3.8 | sim | 1/0 | 0 |
| Jev | P0+P1 | 81.4 | -3.4 | 3.4 | não | 1/0 | 0 |
| Jev | P0+P2k2 | 81.4 | -3.4 | 4.2 | não | 2/1 | 0 |
| Jev | P0+P3 | 76.3 | -8.5 | 4.4 | sim | 2/3 | 0 |
| Jev | P0+P4 | 78.0 | -6.8 | 3.3 | sim | 1/2 | 1 |
| Jev | P0+P5 | 81.4 | -3.4 | 3.4 | não | 3/1 | 0 |
| Jev | P0+P6c+P5 | 81.0 | -3.5 | 3.5 | não | 2/1 | 1 |
| Jev | P0+P6c+P2k2 | 77.6 | -6.9 | 4.2 | sim | 1/2 | 0 |

Canônica sobre Sonnet 5, Haiku 4.5, Jev: **P0** (melhor bruto P0+P4); média de CV joint por candidato: P0 79.5, P0+P4 80.2, P0+P5 79.5; média aninhada 79.5 (escolhas P0, P0, P0, P0, P0).
Recalculada com o Qwen3-8B (quatro modelos): **P0** (melhor bruto P0+P4); P0 80.2, P0+P4 81.2; média aninhada 80.2 (escolhas P0 ×5).

### Formato de saída e economia de contexto (por chamada de roteamento)

| modelo | variante | n | tok de prompt (estático / dinâmico) | cache leitura / escrita | tok saída | $/1k | p50 / p95 do caso ms | p50 da tool ms |
|---|---|---|---|---|---|---|---|---|
| Sonnet 5 | P0 | 151 | 2229 (2119 / 111) | 1746 / 209 | 157 | 5.97 | 5640 / 9403 | 3481 |
| Sonnet 5 | P0+P4 | 151 | 2302 (2196 / 106) | 1887 / 141 | 195 | 6.46 | 6126 / 8602 | 3658 |
| Sonnet 5 | P0+P6c | 60 | 2148 (2041 / 108) | 1697 / 172 | 75 | 4.15 | 4526 / 6417 | 2292 |
| Haiku 4.5 | P0 | 151 | 1917 (1826 / 92) | 0 / 0 | 148 | 5.32 | 3319 / 5066 | 2177 |
| Haiku 4.5 | P0+P4 | 151 | 1978 (1886 / 92) | 0 / 0 | 175 | 5.70 | 3793 / 5311 | 2417 |
| Haiku 4.5 | P0+P6c | 60 | 1855 (1760 / 94) | 0 / 0 | 64 | 4.35 | 2483 / 3827 | 1329 |
| Jev | P0 | 151 | 1157 (1107 / 50) | 784 / 31 | 225 | 0.93 | 5006 / 12455 | 2932 |
| Jev | P0+P6c | 151 | 1043 (997 / 46) | 676 / 40 | 118 | 0.60 | 4010 / 8143 | 1721 |
| Jev | P0+P1 | 151 | 1460 (1409 / 51) | 1019 / 36 | 230 | 0.96 | 5370 / 11116 | 2913 |

- **Os tokens de saída dominam a conta.** O ranking compacto (P6c) corta pela metade os tokens de saída, reduz
  o custo em 18–38% e reduz o p50 do estágio de tool em 33–41%.
  - Nos subconjuntos do Bedrock ele ainda perdeu acurácia contra o líder. O Haiku P0+P6c teve 1
    ganho e 4 perdidos contra o P0, então foi podado.
- **P4 (rationale) custa +7–8% ($) e +9–14% de p50** pelos seus +0.7 a +2.7 pontos.
- **Caching.**
  - O Sonnet 5 lê cerca de 78–82% do seu prompt do cache.
  - O Haiku 4.5 nunca alcança seu mínimo de 4096 tokens para cache.
  - O upstream do Jev (OpenRouter) agora reporta leituras de cache de cerca de 68% do seu prompt.
  - O P1 acrescenta cerca de 300–400 tokens estáticos por chamada. No Sonnet, eles são leituras do cache.

### Gasto desta passada (deltas do ledger)

- **Bedrock: $7.93 da franquia de $8.** O ledger foi de $9.658 para $17.589, com
  `BUDGET__AWS_USD_CAP=17.658`.
  - As rodadas no subconjunto custaram cerca de $4.9 (8 variantes × 2 modelos).
  - O dev completo custou cerca de $3.0 (P0, P4 e P5 × 2 modelos, 91 casos novos cada).
- **OpenRouter (só Jev): $0.92 da franquia de $1.** A linha `typesafe/jev-router` foi
  de $0.9555 para $1.8774.
  - Outros workers gastaram no OpenRouter ao mesmo tempo, então o cap de env foi redefinido antes de cada
    lançamento para o total atual deles mais o que ainda restava da franquia do Jev.
- Cache de respostas: toda decisão bem-sucedida está em `.cache/responses`, então re-executar qualquer
  comando abaixo sai de graça.

### Adicionando o Qwen3-8B (lead) e recalculando a escolha canônica

```bash
C=config/experiments/e6b_llm_qwen3_local.yaml; O=results/prompt_apex_v2
uv run python scripts/analysis/tune_router.py $C --concurrency 1 --preload --subset 60 \
    --prompt-variant "P0,P0+P6c,P0+P1,P0+P2k2,P0+P3,P0+P4,P0+P6,P0+P5" --out $O/e6b_r1.json
# poda (regra acima; select_prompts.py imprime os veredictos), depois dev completo para os sobreviventes
# E para os candidatos canônicos P0, P0+P4, P0+P5:
uv run python scripts/analysis/tune_router.py $C --concurrency 1 --preload \
    --prompt-variant "P0,P0+P4,P0+P5,<survivors>" --out $O/e6b_full.json
uv run python scripts/analysis/select_prompts.py --md docs/results/prompt-selection.md \
    --runs "Sonnet 5=global.anthropic.claude-sonnet-5" $O/e5_r1.json $O/e5_full.json $O/e5_full_p5.json \
    --runs "Haiku 4.5=global.anthropic.claude-haiku-4-5-20251001-v1:0" $O/e6_r1.json $O/e6_full.json $O/e6_full_p5.json \
    --runs "Jev=typesafe/jev-router" $O/e4_r1.json $O/e4_r2.json $O/e4_full.json $O/e4_full_r2.json \
    --runs "Qwen3-8B=qwen3:8b-q8_0" $O/e6b_r1.json $O/e6b_full.json
```

A escolha canônica é recalculada sobre as variantes rodadas no dev completo para todos os modelos informados.
Se os sobreviventes do Qwen acrescentarem uma variante que dois modelos mantiveram, rode-a no dev completo para os outros
modelos também (o Jev é barato; o Bedrock precisa de orçamento), ou deixe-a fora dos candidatos canônicos
e registre isso.

## Como reproduzir

```bash
source results/prompt_apex_v2/env.sh   # caps: gasto do ledger no início + 8 (AWS) / + 1 (OpenRouter)
# rodada 1 no subconjunto de 60 casos (Jev: adicione --set strategies.jev.cache=true)
uv run python scripts/analysis/tune_router.py config/experiments/e5_llm_sonnet.yaml \
    --prompt-variant "P0,P0+P6c,P0+P1,P0+P2k2,P0+P3,P0+P4,P0+P6,P0+P5" --subset 60 \
    --out results/prompt_apex_v2/e5_r1.json
# sobreviventes + candidatos canônicos no dev completo (os casos do subconjunto vêm do cache)
uv run python scripts/analysis/tune_router.py config/experiments/e5_llm_sonnet.yaml \
    --prompt-variant "P0,P0+P4" --out results/prompt_apex_v2/e5_full.json
# seleção + calibração + tabelas (grátis); depois o lead aplica às configs
uv run python scripts/analysis/select_prompts.py --runs ... (see above)
uv run python scripts/analysis/apply_prompt_selection.py
```

Re-executar um comando tenta de novo só as linhas que falharam; os sucessos vêm do cache. Os runs do Bedrock
são sequenciais: primeiro o Sonnet, depois o Haiku. O Jev rodou em paralelo a eles, porque é um
provedor diferente.

## Método

**Dados.** Só `data/dataset_dev.jsonl` (151 casos) é lido. O split de teste nunca foi aberto.
As mensagens few-shot vêm do catálogo MCP (`_meta.examples` de cada tool); nenhuma vem
do dataset.

**Protocolo.** Validação cruzada com 5 folds, estratificada por categoria, com seed 0. Um roteador não tem
estado ajustado em dados, então cada variante é pontuada uma vez em cada caso de dev e depois resumida
por fold. Um estágio com falha é um erro e é pontuado como errado (ITT).

- "CV joint fixa" é a média ± desvio padrão sobre os 5 folds de uma variante.
- A **regra de um SE** escolhe entre as variantes:
  1. melhor = a maior média;
  2. candidatos = toda variante com média de pelo menos melhor − SE(melhor), onde SE é o
     sd dos folds/√5;
  3. entre os candidatos, o menor número de tokens modificadores, depois o menor $/1k, depois P0. Um empate
     vai para o P0.
- A trilha **ajustada** aplica a regra por modelo.
- A trilha **canônica** aplica a regra à média por fold entre os modelos, entre as variantes rodadas
  no dev completo para todos os modelos.
- "Joint em CV aninhada" é a estimativa honesta do procedimento: rodar a regra em 4 folds e pontuar
  sua escolha no fold separado.

**Mesmas entradas para todos os roteadores:**

- texto das opções vindo do catálogo (hash do catálogo `33f89f3db4f5`);
- uma janela de histórico de 4 turnos;
- `max_tokens` 512;
- reasoning desligado (thinking do Qwen desligado via `reasoning_effort: none`);
- `allow_abstain: false`, então pedidos fora de escopo vão para `__global__` → `escalate_to_human`,
  o que o scorer aceita para um gold `__abstain__` (ver `route_scores`).

Assimetrias documentadas:

- O Sonnet 5 no Bedrock não aceita `temperature`. Haiku e Qwen rodam com 0.
- O Bedrock usa tool use forçado. O Ollama usa uma gramática json_schema estrita.
- O Jev não aceita structured output nem parâmetros. Ele recebe o mesmo prompt mais o formato
  da resposta descrito como JSON simples, e um parser tolerante com uma nova tentativa corretiva.
- O Jev não é determinístico. Suas decisões de tuning foram cacheadas (`cache: true` apenas no harness),
  então cada variante é uma amostra.

## Espaço de variantes

Uma variante é um valor de config, `prompt_variant: "P0+P3"`: tokens unidos por `+` e aplicados da esquerda
para a direita. Os templates ficam em `src/routing_study/prompts/routers/`:

- `variants.yaml` mapeia cada token para seus switches;
- `en.yaml` contém o texto em inglês; `pt.yaml`, o texto em pt-BR (P5).

`TEMPLATE_HASH` cobre os três arquivos e faz parte do `prompt_hash` do run. A string da variante
faz parte do `config_hash`.

| token | o que muda |
|---|---|
| P0 | Base: regras → `<options>` (id, descrição, até 5 exemplos do catálogo) → `<loaded_skill>` / `<history>` / `<message>`. Structured output com um `enum` de ids. Confiança = "probabilidade de a escolha estar correta". Estágio de tool: escolha + confiança + todas as outras opções ranqueadas com sua confiança. **P0 é o prompt de antes do estudo, byte a byte** (um teste garante isso), então decisões P0 mais antigas continuam válidas. |
| P1 | `<guide>`: as cláusulas DON'T USE FOR do catálogo, literalmente, como "not X: situation (use Y)". Só são mantidas as cláusulas cujo alvo está no conjunto de opções atual. No estágio de skill, os alvos de tool são reescritos como skills e as cláusulas da mesma skill são descartadas. |
| P2k1 / P2k2 | `<examples>`: k mensagens do catálogo por opção como demonstrações resolvidas (`"message" -> id`), em round-robin sobre as opções. Elas são retiradas das listas de exemplos inline, então nada aparece duas vezes. O estágio de skill usa os exemplos das tools da skill, o que lhe dá texto novo. |
| P3 | Regras de escopo explícitas. Skill: o que `__global__` cobre (uma pessoa, perguntas de política sem pedido, o próprio perfil, assuntos fora dos domínios), e um pedido vago sobre um pedido vai para o seu domínio. Tool: preferir a tool específica de ação ou consulta, e usar as de uso geral só quando nenhuma tool específica serve. |
| P4 | Um campo `rationale` (no máximo 15 palavras) antes da decisão. Seus tokens contam no custo e na latência. |
| P5 | Instruções em pt-BR (o texto das opções já é pt-BR de qualquer forma). |
| P6 | Estágio de tool: `ranking: [{id, score}]`, top 3, o melhor primeiro. Escolha = primeiro id; confiança = seu score. |
| P6c | Estágio de tool, compacto: `ranking: [id, id, id]` + uma `confidence` para o primeiro id (só ids; as alternativas recebem 0.0). |
| k2 | Top-2 em vez de top-3 para P6 / P6c. |

O estágio de skill sempre responde `{choice, confidence}`, mais `rationale` sob P4. Os formatos de
saída se aplicam só ao estágio de tool: é o estágio que o host expõe como top-k, e o
estágio em que a latência local é dominada pelo tamanho da saída. O prefixo estático (regras, opções,
guia, exemplos) é a system message inteira. Ele é enviado como um `cachePoint` do Bedrock, e o Ollama
o reaproveita pelo seu cache de prefixo KV.

## Economia de contexto (como ler as colunas)

- `prompt` é a média de tokens de prompt por chamada de roteamento, conforme o provedor os reporta.
- `static` / `dyn` dividem esse total pelos caracteres renderizados do prefixo de sistema versus a
  mensagem do usuário. É uma estimativa, porque os provedores reportam um total único.
- `cache r/w` é a média de tokens de leitura / escrita de cache por chamada:
  - o Sonnet 5 faz cache do prefixo de ~2k tokens e lê cerca de 85% do prompt do cache;
  - o Haiku 4.5 precisa de 4096 tokens antes que um cache point tenha efeito, e nenhuma variante chega lá;
  - o Ollama não reporta seu reaproveitamento de prefixo.
- `out` é a média de tokens de saída por chamada.
- `$/1k` é o custo de roteamento por 1000 casos (chamada de skill + tool). Ele usa o custo original mesmo
  quando a decisão veio do cache.
- `p50 / p95` é a latência do caso (skill + tool). `tool p50` é só a chamada do estágio de tool.
- O ECE usa 10 bins, sobre a confiança bruta, nas decisões que foram tomadas.
