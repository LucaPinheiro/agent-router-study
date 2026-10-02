# 13 · Reprodutibilidade

## 1. Artefatos congelados

| Artefato | Valor |
|---|---|
| Código do pré-registro | tag `prereg-v1` → commit `d14816e` |
| Dataset confirmatório | `data/dataset_test_v2.jsonl`, 349 casos, sha256 `6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66` |
| Dataset de replicação (exposto) | `data/dataset_test_v1.jsonl` → `dataset_test.jsonl`, sha256 `994d20623384931f9bf06ab9f3ee7028397118b66a7ff0abd800bffeef543a77` |
| Dataset de ajuste | `data/dataset_dev.jsonl`, 151 casos, sha256 `112fc7f0791e35cf1e250a40e362698212f029b4209b6ff7f33dc33717a8874a` |
| Hash do catálogo | `128584617807` |
| Hash do scorer | `e0eef1fb0073` |
| Hash dos prompts do run | `c61ad0a7b7f8` |
| Manifesto principal | `config/study_manifest.yaml`, sha256 `9e4cdb2626213dbb805ae54b0218b7cedd96d81fff920befc2c2c46282836868` (102 entradas; `config_hash`/`prompt_hash` por entrada em [hashes.md](../docs/prereg/hashes.md)) |
| Manifesto exploratório (D-002) | `config/study_manifest_explore.yaml`, sha256 `93694326db6d32a1e9fa5bc16a71ba846dc15dd15589dc837fe822ff0147cf2b` (2 entradas) |
| Seleção de prompts | `config/prompt_selection.yaml`, sha256 `3648a71d90c0c6583b4ab27ce6a1bc7e856b2f29249ce92551e3eb2d34d980fb` |
| Bootstrap | seed 20260930, 10.000 reamostragens, por caso |

Fonte: [prereg-v1.md §1](../docs/prereg/prereg-v1.md). Desvios D-001 a D-003 em
[deviations.md](../docs/prereg/deviations.md): D-001 e D-003 são só de infraestrutura (sem efeito
na análise); D-002 são os dois runs exploratórios com todas as tools expostas.

## 2. Executar os runs

```bash
make up && make up-app            # Langfuse, Redis, servidor MCP
# Ollama local com qwen3:8b-q8_0, qwen3-embedding:8b-q8_0 (+ 0.6b, bge-m3 para as ablações)
# credenciais AWS (cadeia padrão do boto3, região sa-east-1) e OPENROUTER_API_KEY no .env

BUDGET__AWS_USD_CAP=85 uv run study run-manifest config/study_manifest.yaml
uv run study run-manifest config/study_manifest_explore.yaml     # D-002 (exploratório)
```

O `run-manifest` confere o `config_hash`/`prompt_hash` de cada entrada, verifica o orçamento antes
de cada run, retoma por (caso, repetição) e marca como FLAGGED um run com mais de 2% de erros
depois de 2 retentativas. Os logs ficam em `results/final/run-manifest.log` e
`results/final/run-manifest-explore.log`; o status final de cada run está em
[runs_status.md](../docs/results/final/runs_status.md). Com o cache de respostas
(`.cache/responses`) preenchido, repetir os runs não custa nada.

## 3. Regenerar a análise

```bash
uv run python scripts/analysis/final_all.py     # ~50 s; idempotente
```

Lê só `results/rescored/` (a única fonte de números), `results/final/run-manifest.log`, `config/`
e `docs/results/`. As figuras precisam de matplotlib, que não é dependência do projeto: o script
se reexecuta com `uv run --with matplotlib`.

| Tabela / figura | Arquivo | Módulo |
|---|---|---|
| H1–H3, razões de custo | [primary.md](../docs/results/final/primary.md) / `.json` | `final_primary.py` |
| S1–S4 | [secondary.md](../docs/results/final/secondary.md) / `.json` | `final_primary.py` |
| A–K (estratégias, custo, calibração, latência, categorias, repetições, Jev, cascatas, e2e, v1, RQ5) | [estimation.md](../docs/results/final/estimation.md) / `.json` | `final_estimation.py` |
| Matriz enterprise | [enterprise_matrix.md](../docs/results/final/enterprise_matrix.md) | `final_enterprise.py` |
| D-002, análise de erros do e2e, pares confundidos | [exploratory_e2e.md](../docs/results/final/exploratory_e2e.md) / `.json` | `final_exploratory.py` |
| Relatório de registro (`study report`) | [study_report_test_v2.md](../docs/results/final/study_report_test_v2.md) | CLI |
| `estudos/figuras/final-*.png` | — | `final_figures.py`, `final_exploratory.py` |

Comandos de CLI equivalentes para partes isoladas:

```bash
uv run study report --manifest config/study_manifest.yaml --split test_v2   # tabela por run + contrastes
uv run study rq5 config/study_manifest.yaml --split test_v2                 # tabela RQ5
uv run study simulate results/rescored/v2-shadow-tuned-routing-r3.jsonl \
    -c config/experiments/e9_regex_jev_llm.yaml                             # replay de cascata
uv run study rescore results/<run>.jsonl                                    # rescore offline
uv run study budget                                                         # ledger de gastos
```

Busca e seleção de prompts (dev): ver [prompt-apex.md](../docs/prompt-apex.md). Ajuste dos
roteadores livres: [tuning-effort.md](../docs/tuning-effort.md). Limiares das cascatas:
[cascade-thresholds-dev.md](../docs/results/cascade-thresholds-dev.md).

## 4. Gastos

| Escopo | Bedrock (AWS) | OpenRouter |
|---|---|---|
| Estudo final (do congelamento ao fim dos runs; delta do ledger) | **US$ 34,48** (17,63 → 52,11) | **US$ 1,43** (4,40 → 5,83) |
| Projeto inteiro, no ledger (`uv run study budget`) | **US$ 52,11** | **US$ 5,83** |
| OpenRouter antes do ledger existir | — | US$ 10,19 (informado pelo responsável; não verificável a partir do repositório) |

Detalhe do ledger por modelo (`results/spend_ledger.jsonl`, 33.972 chamadas): Sonnet 5
US$ 41,05; Haiku 4.5 US$ 11,06; `typesafe/jev-router` US$ 3,32; geração do test-v2
(`google/gemini-2.5-flash`) US$ 1,65; auditores `deepseek/deepseek-v4-pro` US$ 0,65 e
`openai/gpt-5.6-luna` US$ 0,21. Modelos locais (Ollama) custam US$ 0.

## 5. Observabilidade

Cada turno é um trace no Langfuse local (v4), com spans por nó do grafo, por estratégia de
roteamento e pela chamada MCP. Cada run é um experimento ligado ao dataset do Langfuse.

![Experimentos no Langfuse](figuras/langfuse-experiments.png)

*Figura 1. Cada run é um experimento ligado ao dataset (aqui, os mais recentes: replicação v1,
exploratórios D-002, RQ5). A coluna "Error Count" do Langfuse conta spans de nível ERROR,
incluindo erros de negócio das tools (por exemplo, `NOT_ELIGIBLE`): nos runs `x-e*-fullskill`,
60 e 65 são esses erros, e não falhas de infraestrutura (0 erros de infraestrutura no
manifesto).*

![Dataset test-v2 no Langfuse](figuras/langfuse-experiments-test-v2.png)

*Figura 2. Os 349 itens do test-v2, com entrada, saída esperada (tool e argumentos) e metadados.*

![Datasets](figuras/langfuse-datasets.png)

*Figura 3. Datasets do projeto: test-v2 com 99 experimentos; o test-v1 usa o dataset original
`routing-study-test` (desvio D-003).*

![Painel do Langfuse](figuras/langfuse-dashboard-cost.png)

*Figura 4. Painel principal no dia do run final: custo por modelo (US$ 36,05, que bate com o
ledger) e notas. Os traces raiz `POST /{path}` e `GET /healthz` são o ruído anterior à correção
`a6c4330`; depois dela, esses spans ficam aninhados ou não são exportados.*

### Painel personalizado no Langfuse

O painel **"Agent Router Study: operação"** (Langfuse local → Dashboards) tem 9 widgets montados
para operar e auditar o agente. Os números oficiais, com IC, continuam sendo os de
`docs/results/final/`; o painel é a visão operacional sobre os mesmos traces.

| Widget | Pergunta que responde |
|---|---|
| Sucesso e2e por run (test-v2) | Qual configuração resolve mais turnos de ponta a ponta? (E0 0,556; E9 0,458) |
| Acurácia conjunta por roteador (test-v2) | Qual roteador acerta skill e tool, por run e repetição? |
| Latência p95 por nó do grafo (e2e) | Onde o tempo do turno é gasto? (executor ~7 s; nos runs e2e o roteador veio do cache) |
| Latência p95 do span de cada estratégia | Quanto custa em tempo cada estratégia no estágio skill (benchmark `lat-*`)? |
| Custo por experimento | Quanto custou cada run (roteador + executor)? |
| Custo por modelo | Para onde foi o dinheiro (Sonnet, Haiku, modelos atendidos pelo Jev)? |
| Tokens de entrada do executor (e2e) | Quanto contexto o roteador economiza (≈ 4,4 mil vs 5,3 mil tokens do nativo)? |
| Erros de negócio das tools | Quais tools o executor chama na hora errada (ex.: `NOT_ELIGIBLE`)? |
| Turnos ao longo do tempo | Volume de turnos por dia |

![Painel personalizado: resultado e latência](figuras/langfuse-dashboard-custom.png)

*Figura 5. Painel personalizado, parte 1: sucesso e2e por run e acurácia conjunta por roteador
(test-v2), latência por nó e por estratégia.*

![Painel personalizado: custo e contexto](figuras/langfuse-dashboard-custom-2.png)

*Figura 6. Parte 2: custo por experimento e por modelo, tokens de entrada do executor e erros de
negócio das tools.*

![Painel personalizado: tokens, erros e volume](figuras/langfuse-dashboard-custom-3.png)

*Figura 7. Parte 3: tokens do executor por run e2e, erros de negócio por tool e volume de turnos.*

Ressalvas de leitura, também escritas na descrição de cada widget: o widget de latência por
estratégia mede só o span da estratégia no estágio skill, não a latência total do roteador
(capítulo [08](08-economia.md)); "Custo por modelo" inclui o gasto de desenvolvimento (geração e
auditoria do dataset).

Os traces de exemplo já capturados estão no capítulo [07](07-ponta-a-ponta.md).

## 6. Ambiente

- Máquina local: Apple Silicon (Apple M5 Pro, 48 GB), Ollama, concorrência 1 para modelos locais.
- Bedrock em `sa-east-1` com perfis de inferência `global.*`; OpenRouter para Jev, geração e
  auditoria.
- Python 3.12, dependências travadas em `uv.lock`.

## 7. Fase 2

A fase 2 tem dois pré-registros, cada um congelado numa tag antes da primeira linha do seu split
de teste. Os artefatos da fase 1 acima não mudaram: `tests/test_phase1_hashes.py` confere que
toda entrada dos manifestos da fase 1 reproduz o `config_hash`/`prompt_hash` congelado.

### 7.1 Artefatos congelados

| Artefato | Parte A (`prereg-v2a`) | Parte B (`prereg-v2`) |
|---|---|---|
| Tag → commit | `prereg-v2a` → `d4b1463` | `prereg-v2` → `76c0f92` |
| Pré-registro | [prereg-v2a.md](../docs/prereg/prereg-v2a.md) | [prereg-v2.md](../docs/prereg/prereg-v2.md) |
| Split de teste | `data/dataset_test_v2.jsonl` (349, o mesmo da fase 1), sha256 `6637c4795b23…` | `data/dataset_test_l.jsonl` (300), sha256 `ae21a5dbce16eb90278612f7dbcf875cb6610b7b12a49cb6f7f57e503d680ff2` |
| Split de ajuste | `data/dataset_dev.jsonl` (151) | `data/dataset_dev_l.jsonl` (150), sha256 `b02b3722f5c4e434dd97a4c6a4811ac18a1fd1945784a6375639acd0b376e238` |
| Catálogo | `128584617807` (18 tools) | `bc7cd75fce87` (62 tools; `tools_list_large.json` sha256 `a0583726a351…`); X2 no `128584617807` |
| Manifesto | `config/addendum_manifest.yaml`, sha256 `177e374a8ee0f07303fc0244110c0ac5fa95f6b276d9006d30f2cdd54ac1149e` | `config/study_manifest_l.yaml`, sha256 `788fac3665ba82e06703a644f42e753f1413441dcc8d3395071d6d8ce8bc2e6b` (73 entradas) |
| Scorers | roteamento `e0eef1fb0073` | roteamento `e0eef1fb0073`; e2e primário `e2e_success_sym` `5ad0f65296e4` (`scorers_sym.py`) |
| Prompt | `c61ad0a7b7f8` (P0) | `c61ad0a7b7f8` (P0) |
| Script de análise | `scripts/analysis/addendum_a.py` | `scripts/analysis/phase2_b.py` (escrito no commit `27cacee`, antes do test-L; só o bloco de constantes do congelamento mudou até a tag) |
| Desvios | DV2-001 (nome do script) | D-L01 (Redis sem memória, só infraestrutura) |

`config_hash` por run: [prereg-v2a.md §1](../docs/prereg/prereg-v2a.md) e
[prereg-v2.md §1](../docs/prereg/prereg-v2.md). Desvios: [deviations-v2.md](../docs/prereg/deviations-v2.md).

### 7.2 Comandos

```bash
make up && make up-app      # Langfuse, Redis, mcp-server (:8765, 18 tools) e mcp-server-large (:8766, 62 tools)

# Parte A (test-v2, só roteamento)
uv run study run-manifest config/addendum_manifest.yaml
uv run python scripts/analysis/addendum_a.py                           # -> docs/results/addendum-a/, estudos/figuras/final-a-*.png

# Parte B (test-L)
uv run study run-manifest config/study_manifest_l.yaml --dry-run       # 73 PLAN, 0 ABORT na tag
BUDGET__AWS_USD_CAP=92.11 BUDGET__OPENROUTER_USD_CAP=9.43 \
    uv run study run-manifest config/study_manifest_l.yaml             # log: results/manifest-study_manifest_l.log
uv run study rescore results/l-e0-native-e2e-r1.jsonl results/l-e0-native-e2e-rep2-60.jsonl \
    results/l-e9-tuned-e2e-r1.jsonl results/l-e9-tuned-e2e-rep2-60.jsonl \
    results/l-e9-fullskill-e2e-r1.jsonl --scorer sym                   # -> results/rescored-sym/
uv run python scripts/analysis/phase2_b.py --manifest config/study_manifest_l.yaml
```

O `run-manifest` reescora com o scorer legacy ao completar cada run; o scorer simétrico é um
passo offline, aplicado aos mesmos arquivos brutos (o `phase2_b.py` confere o sha256 da fonte dos
dois arquivos).

| Tabela / figura | Arquivo |
|---|---|
| H1-L, H2-L, H3-L, co-primárias, sensibilidades, inventário de runs e proveniência | [phase2-b/primary.md](../docs/results/phase2-b/primary.md) / `.json` |
| S1–S4, S7 | [phase2-b/secondary.md](../docs/results/phase2-b/secondary.md) / `.json` |
| Acurácia, custo em três regimes, calibração, risco × cobertura, latência, cobertura das cascatas, e2e, repetições, erros, recortes | [phase2-b/estimation.md](../docs/results/phase2-b/estimation.md) / `.json` |
| X1, X2, X3 (cache do Haiku), X4 | [phase2-b/catalog_size.md](../docs/results/phase2-b/catalog_size.md) / `.json` |
| `estudos/figuras/final-b-*.png` | `docs/results/phase2-b/figure_data.json` |

### 7.3 Idempotência da análise da Parte B

O `phase2_b.py` foi rodado duas vezes seguidas sobre os mesmos insumos; os quatro `.md` e os cinco
`.json` saíram idênticos byte a byte. sha256 dos `.md`:

| Arquivo | sha256 |
|---|---|
| `primary.md` | `fcd067593d7fa3080b72dbab81e5fc0081760fd75bb62320256a5230b56f6c8d` |
| `secondary.md` | `2e00fc7499b8d217820e49a8ecab39f88bb87a759f9f8185bc5bb15b6175fc6c` |
| `estimation.md` | `b491712f31b499a5d86a36d8683732b5ae565e615d588faf9a77001afdea435c` |
| `catalog_size.md` | `ba3cdf8da2b163f43d821941343a5f94d5904dc446671552126078c7e6f742a3` |

### 7.4 Gastos da fase 2

Medidos contra a marca do ledger ([phase2-budget.md](../docs/prereg/phase2-budget.md)): AWS 52,11
e OpenRouter 5,83, em 2026-10-01T23:42:38Z.

| Escopo | Bedrock (AWS) | OpenRouter |
|---|---|---|
| Fase 2 inteira (Partes A e B: ajuste, geração e auditoria do dev-L/test-L, runs de teste) | **US$ 27,65** (52,11 → 79,76) | **US$ 1,69** (5,83 → 7,52) |
| Teto da Parte B (prereg-v2 §6) | ≤ US$ 40 (ledger ≤ 92,11) | ledger ≤ 9,43 |

O teto não foi atingido e nenhum run foi recusado pelo guarda de orçamento. Na Parte B, o
OpenRouter foi usado só para o `typesafe/jev-router`.

### 7.5 Observabilidade da fase 2

Os runs do test-L estão no Langfuse local, no dataset `routing-study-test_l`; a API
`/api/public/v2/observations` devolve 10.333 observações `turn` na janela do manifesto
(2026-10-02, 13:05–15:36 UTC). Esta instalação do Langfuse v4 roda em modo `events_only`, em que
os endpoints de `dataset runs` e `traces` da API pública v1 não respondem; os traces aparecem
normalmente na interface e no painel "Agent Router Study: operação" (seção 5), filtrando pelo
dataset do test-L.
