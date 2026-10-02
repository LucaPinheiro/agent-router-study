# Pré-registro prereg-v2a: adendo de nuvem (Parte A), split test-v2, catálogo de 18 tools

> Tradução pt-BR de [`docs/prereg/prereg-v2a.md`](../../docs/prereg/prereg-v2a.md). O original em inglês é o documento congelado na tag; em caso de divergência, vale ele.

Status: **CONGELADO** na tag git `prereg-v2a`, antes da primeira linha do test-v2 da Parte A. Nada abaixo
(configs, mapas de calibração, prompts, manifesto, scorers, catálogo) muda depois dessa linha
(prereg-v2 §8). A Parte B (catálogo grande) é pré-registrada separadamente (`prereg-v2-draft.md` → `prereg-v2.md`).
Plano: `.omc/plans/autopilot-impl.md` T2.4. Registro de ajuste no dev: `docs/tuning-effort-l.md` §A.

## 0. Herdado do prereg-v1 sem mudança

Unidade = caso, repetições tiradas a média por caso; ITT (uma falha de infra ou de parse conta como erro);
multirrótulo (qualquer rótulo aceitável, o primeiro rótulo como sensibilidade); fora de escopo = escalonamento
conta como abstenção; bootstrap pareado por cluster (caso), 10,000 reamostragens, seed 20260930; NI = limite
inferior do IC 95% bilateral mais um p-valor sign-flip com o deslocamento; bilateral = IC mais p-valor
sign-flip; Holm dentro da família; cache de respostas por (caso, rep, prompt renderizado); latência **só** do
benchmark dedicado; custo em três regimes; regras de operação, retentativa e aborto do prereg-v1 §7.

**Restrição da fase 2 (2026-10-01, vinculante):** nenhum modelo local roda (sem Qwen3-8B no Ollama, sem
qwen3-embedding local); OpenRouter só para o `typesafe/jev-router`; todo o resto no Bedrock.

## 1. Artefatos congelados

| artefato | valor |
|---|---|
| código | o commit marcado `prereg-v2a` |
| catálogo | perfil pequeno, `catalog_hash` **128584617807** (sem mudança desde a fase 1; verificado em toda linha pela análise) |
| dados | `data/dataset_test_v2.jsonl` sha256 `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` (349 casos, sem mudança); dev `data/dataset_dev.jsonl` `112fc7f0791e35cf1e250a40e362698212f029b4209b6ff7f33dc33717a8874a` |
| scorer de roteamento | `scorer_hash` legacy **e0eef1fb0073** (sem mudança). A Parte A é só roteamento: o scorer e2e sym (`5ad0f65296e4`) não é usado |
| prompt | `prompt_hash` **c61ad0a7b7f8** (P0; sem mudança de template, sem busca de prompt) |
| manifesto | `config/addendum_manifest.yaml`, sha256 registrado no §6 |
| ids de latência | `config/manifest/latency_test_v2_b{1..4}.ids` (arquivos da fase 1, 4 × 25 casos estratificados), prefixos de sha256 `ae81eacf2b492fc8`, `8fd97293c7683b86`, `48cdf829874e34eb`, `65b2efa0035d5d23` |
| limiares / calibração | escritos nas seis configs da Parte A (§5); nenhuma cascata na Parte A |
| trava de hashes da fase 1 | toda entrada de `config/study_manifest.yaml` / `study_manifest_explore.yaml` reproduz o seu `config_hash` e `prompt_hash` congelados na tag (conferido em 2026-10-01: 104 entradas, 0 divergências) |

### Config hashes por run (verificados pela guarda de versão do manifesto)

| run(s) | config | config_hash |
|---|---|---|
| `v2a-e3c-cohere-routing-r1` | `config/experiments/e3_embedding_cohere.yaml` | 56f1708d24de |
| `v2a-e3t-titan-routing-r1` | `config/experiments/e3_embedding_titan.yaml` | 73f81417a487 |
| `v2a-e10c-cohere-routing-r1` | `config/experiments/e10_classifier_cohere.yaml` | fc05bbd1c5aa |
| `v2a-e10t-titan-routing-r1` | `config/experiments/e10_classifier_titan.yaml` | 70374caa4b59 |
| `v2a-e6m-ministral-canonical-routing-r1`, `-repeat50` | `config/experiments/e6m_llm_ministral.yaml` | 0d8fbee553f3 |
| `v2a-e6n-nemotron-canonical-routing-r1`, `-repeat50` | `config/experiments/e6n_llm_nemotron.yaml` | efb00ce5b9f8 |
| `lat-a-e3c-b{1..4}` / `lat-a-e3t-b*` / `lat-a-e10c-b*` / `lat-a-e10t-b*` | mesmas configs + overrides de latência | dc14a444fd4b / 310f335fdb80 / ab5f1d2d0d13 / 6377e34f786e |
| `lat-a-e6m-b*` / `lat-a-e6n-b*` | mesmas configs + overrides de latência | 67e47f9c08e8 / 435d2cee8b41 |
| `lat-a-jev-b*` / `lat-a-haiku-b*` (âncoras gerenciadas) | `e4_jev.yaml` / `e6_llm_haiku.yaml` + overrides de latência | 5cf75faa33f3 / 5535a7588de0 (= os hashes de `lat-jev-b*` / `lat-haiku-b*` da fase 1: configs idênticas) |

### Linhas reaproveitadas da fase 1 (congeladas, só leitura; os braços locais de comparação)

| papel | arquivo (reescorado) | prefixo de sha256 |
|---|---|---|
| referência de A1/A2, E6b Qwen3-8B local, P0 canônico | `results/rescored/v2-e6b-qwen-canonical-routing-r1.jsonl` (config_hash 903a4a1e56d3) | 6a99aab7fc6b116d |
| referência de A3/A4, E3 qwen3-embedding 8B local | `results/rescored/v2-e3-embedding-routing-r1.jsonl` (1899b6f414a5) | 4c13be42cda91614 |
| par de estimação de E10c/E10t, sonda local | `results/rescored/v2-e10-classifier-routing-r1.jsonl` (616af886b783) | b14c2893e454ce80 |
| latência local | `results/rescored/lat-qwen-b*`, `lat-embedding-b*`, `lat-classifier-b*` (janela da fase 1) | – |
| deriva das âncoras gerenciadas | `results/rescored/lat-jev-b*`, `lat-haiku-b*` (janela da fase 1) | – |

## 2. Braços (catálogo pequeno, test-v2, 349 casos, só roteamento)

Roteadores gerenciados novos, todos no Bedrock `sa-east-1`, exceto onde indicado:
- **E3c**: roteador por embedding denso sobre o Cohere Embed v4 (`global.cohere.embed-v4:0`, perfil de
  inferência entre regiões; consultas `search_query`, documentos `search_document`).
- **E3t**: roteador por embedding denso sobre o Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024-d).
- **E10c / E10t**: sonda linear (regressão logística sobre frases do catálogo) sobre os vetores do Cohere / Titan.
- **E6m**: Ministral 3 8B (`mistral.ministral-3-8b-instruct`), P0, temperatura 0, tool nomeada forçada.
- **E6n**: Nemotron Nano 9B v2 (`nvidia.nemotron-nano-9b-v2`), P0, temperatura 0, raciocínio desligado (`/no_think`).

Braços de comparação (não rodados de novo): as linhas locais da fase 1 do §1, pareadas nos mesmos 349 casos. As
linhas de acurácia de Haiku/Jev/Sonnet da fase 1 são só contexto.

## 3. Hipóteses

### Família A (secundária, confirmatória para o adendo; Holm entre A1–A4; α = 0.05)

Conjunta = acurácia conjunta de roteamento top-1 (scorer legacy de roteamento), ITT, 1 rep por braço, pareada por caso.

- **A1 (NI, margem 3 pp).** Conjunta(E6m Ministral) − Conjunta(E6b Qwen3-8B local) > −3 pp.
- **A2 (NI, margem 3 pp).** Conjunta(E6n Nemotron) − Conjunta(E6b) > −3 pp.
- **A3 (bilateral).** Conjunta(E3c Cohere) − Conjunta(E3 qwen3-embedding local).
- **A4 (bilateral).** Conjunta(E3t Titan) − Conjunta(E3 local).

Expectativa no dev (não faz parte do teste; `docs/tuning-effort-l.md` §A): E6m 79.5, E6n 78.1 vs E6b 82.2 (CV no dev);
E3c 59.6, E3t 60.3 vs E3 77.5 (CV aninhada). Espera-se que A3/A4 sejam diferenças negativas grandes.

### Só estimação (ICs, sem testes)

- skill %, tool % condicional, recall@1/2/3 para todo braço novo; E10c/E10t vs a sonda local E10 e vs o seu
  próprio roteador por embedding (Δ pareado com IC);
- taxas de erro e de falha de parse por braço (ITT); taxa de mudança rep 1 vs rep 2 nos 50 casos estratificados (E6m, E6n);
- ECE e Brier, bruto e calibrado no dev;
- custo por 1k casos nos três regimes;
- **latência** p50/p95 com ICs por bootstrap, o primeiro caso frio de cada run à parte:
  - mesma janela: os seis braços novos vs as âncoras gerenciadas Jev e Haiku 4.5, rodadas de novo intercaladas por bloco;
  - outra janela: os seis braços novos vs os blocos locais da fase 1 (`lat-qwen`, `lat-embedding`, `lat-classifier`).
    **Ressalva (obrigatória onde aparecer):** janela de tempo diferente; o mesmo Mac (M5 Pro 48 GB) no lado local,
    Bedrock `sa-east-1` a partir desse Mac no lado gerenciado. A deriva é estimada como o Δ p50/p95 das âncoras
    gerenciadas entre os seus blocos da fase 1 e da Parte A; é reportada, nunca subtraída.

**Regra de decisão da matriz enterprise (descritiva).** Uma opção gerenciada "qualifica" num orçamento de latência
quando o limite superior do IC do seu p95 fica abaixo do orçamento **e** a sua conjunta não é inferior (regra de
A1/A2 para os modelos 8B; para os embedders, o IC de A3/A4 exclui uma perda maior que 3 pp) à do seu par local.

## 4. Métricas e scorers

Primária de roteamento: acurácia conjunta top-1 com o scorer legacy (`e0eef1fb0073`), sem mudança. Métricas
secundárias de roteamento como em `docs/metrics.md`. Nenhuma run e2e na Parte A.

## 5. Ajuste, limiares e calibração (só dev, congelados nas configs)

Todo o ajuste usou o split dev da fase 1 (151 casos), CV de 5 folds estratificada por categoria, seed 0; o test-v2
não foi lido. Os mapas de calibração (isotônico ou Platt pelo Brier da CV para os embedders; isotônico para os LLMs,
o procedimento de LLM da fase 1) só são escritos onde o ECE com ajuste cruzado é menor que o bruto (decisão de 2026-10-01).

| braço | procedimento | escolha congelada | conjunta dev [IC 95%] (aninhada) | mapas escritos |
|---|---|---|---|---|
| E3c | grade D1 de 324 pontos da fase 1; T pelo Brier calibrado | topk_vote k 5, T 0.1, histórico 2, shots, sem instrução | 59.6 [51.7, 67.5] | skill (Platt) + tool (isotônico) |
| E3t | igual | centroid, T 0.02, histórico 1, shots, sem instrução | 60.3 [52.3, 68.2] | skill (isotônico) + tool (Platt) |
| E10c | grade de sonda D4 de 64 pontos da fase 1 + refinamento de 8 pontos C × histórico | C 10, shots, descrição, sem instrução, histórico 0 | 53.6 [45.7, 61.6] / 56.3 [48.3, 64.2] | só tool (ECE de skill não é menor) |
| E10t | igual | C 0.1, shots, descrição, sem instrução, histórico 0 | 60.9 [53.0, 68.9] / 59.0 [51.0, 66.9] | skill + tool (isotônico) |
| E6m | só P0 (sem busca de prompt) | P0, T 0 | 79.5 [72.8, 86.1] | skill + tool (isotônico) |
| E6n | só P0 | P0, T 0, `/no_think` | 78.1 [71.5, 84.8] | skill + tool (isotônico) |

As taxas de falha de parse dos 8B no dev (Ministral 0.3% das chamadas, Nemotron 0.7%; linhas de erro 0.7% → 0 e 1.3%)
ficam abaixo de 2%: nenhuma correção só de formato foi usada.

## 6. Plano de runs, ordem e orçamento

Manifesto `config/addendum_manifest.yaml`, sha256 `177e374a8ee0f07303fc0244110c0ac5fa95f6b276d9006d30f2cdd54ac1149e`. Ordem de prioridade:

| prioridade | runs | casos × reps |
|---|---|---|
| 10 | E3c, E3t, E10c, E10t | 349 × 1 |
| 20 | E6m, E6n (P0 canônico) | 349 × 1 |
| 21 | E6m, E6n rep 2 em 50 casos estratificados (rep 1 = acerto de cache da run r1) | 50 × 2 |
| 70 | `lat-a-*`: blocos 1–4 × {E3c, E3t, E10c, E10t, E6m, E6n, Jev, Haiku}, intercalados por bloco, concorrência 1, caches de resposta desligados, `cache_dir` novo `.cache/latency-a` | 4 × 25 por braço |

`study run-manifest config/addendum_manifest.yaml --dry-run` no congelamento: toda entrada PLANNED, nenhum ABORT
(hashes e trilhas de prompt reproduzem), 0 linhas em disco.

**Orçamento.** Marca da fase 2 AWS 52.11 / OpenRouter 5.83 (`docs/prereg/phase2-budget.md`). Teto das runs da Parte A (plano T2.5):
`BUDGET__AWS_USD_CAP` = **54.11** (marca + 2.0) e o teto do OpenRouter = ledger no lançamento + **0.2**.
Esperado (custos por caso medidos no dev): 8B r1 + rep2 ≈ US$ 0.27; latência dos 8B ≈ 0.07; âncora Haiku ≈ 0.50; embeddings
(teste + latência + índices) ≈ 0.02; **AWS ≈ 0.86**; âncora Jev ≈ **OR 0.08**. A guarda roda antes de toda entrada; uma
entrada recusada é um desvio, reportada como não rodada, nunca reordenada. Ordem de corte se um teto for atingido: as âncoras
(menor prioridade) primeiro. Nota: a guarda precifica E10c/E10t como grátis (os embeddings de consulta da sonda no Bedrock não
são contados a priori); o custo real deles é uma fração de centavo por run.

## 7. Regras de parada e de desvio

Como no prereg-v2 §8: nenhuma mudança de configs, prompts, rótulos, mapas de calibração, catálogo ou scorers depois da primeira
linha do test-v2 da Parte A; até 2 retentativas das linhas de erro; uma run com > 2% de erros é FLAGGED e refeita do zero;
desvios acrescentados com timestamp a `docs/prereg/deviations-v2.md`.

## 8. Plano de análise

`scripts/analysis/addendum_all.py` → `docs/results/addendum/` (idempotente): família A com Holm; as tabelas de estimação
do §3; custo por 1k em três regimes; latência p50/p95 (caso frio à parte) para a comparação na mesma janela e a
comparação local entre janelas com a linha de deriva; a matriz local × gerenciado usando as linhas reaproveitadas da fase 1.
O `catalog_hash`, o `config_hash` e o `prompt_hash` de toda linha são verificados contra o §1.

## 9. Ameaças específicas da Parte A

- **Reuso do test-v2** (plano R10). Os analistas leram os erros da fase 1 no test-v2. Mitigação: os braços da Parte A
  foram ajustados só no dev, com as grades da fase 1 literais e sem regras manuais, e congelados aqui antes de qualquer
  linha nova do test-v2.
- **Braços locais de outra janela de tempo.** A acurácia não é afetada (linhas locais determinísticas, mesmos casos);
  a latência é (ver a ressalva do §3).
- **O Cohere é servido por um perfil de inferência entre regiões** (`global.`): o InvokeModel não informa a região
  que atendeu, então a latência dele inclui qualquer roteamento entre regiões que o Bedrock aplicou.
- **Deriva do Jev** (plano R9): os modelos atendidos podem ter mudado desde a fase 1; a âncora é rodada de novo, nunca reaproveitada.
