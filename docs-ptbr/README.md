# Documentação (pt-BR)

Tradução em português brasileiro da pasta [`docs/`](../docs/). A estrutura de diretórios espelha a original.

- Apenas os documentos em prosa (`.md`, `.txt`) foram traduzidos.
- Arquivos de dados (`.json`, `.jsonl`, `.csv`, `.yaml`) não foram duplicados e permanecem em `docs/`: os links apontam para os originais em `docs/`.
- Números, ICs, p-valores, hashes, nomes de run, ids de config, identificadores de código, caminhos, comandos e slugs de modelo são idênticos aos da versão em inglês (separador decimal com ponto).
- Em caso de divergência, a versão em inglês em `docs/` é a fonte canônica (em especial a pré-registração em `docs/prereg/`).

## Arquivos traduzidos

| arquivo | conteúdo |
|---|---|
| [projeto.md](projeto.md) | visão geral do estudo de roteamento agent-skill |
| [graph.md](graph.md) | grafo do host |
| [metrics.md](metrics.md) | definição de métricas e estatística |
| [calibration.md](calibration.md) | calibração dos limiares da cascata |
| [dataset-card.md](dataset-card.md) | dataset card do benchmark (test-v1, test-v2; fase 2: dev-L, test-L) |
| [catalog-large.md](catalog-large.md) | catálogo grande da fase 2 (62 tools, grupos confundíveis G1–G12) |
| [prompt-apex.md](prompt-apex.md) | estudo de prompt dos roteadores (trilhas canônica e ajustada) |
| [tuning-effort.md](tuning-effort.md) | esforço de tuning por estratégia |
| [tuning-effort-l.md](tuning-effort-l.md) | esforço de tuning da fase 2 (Parte A no dev, Parte B no dev-L) |
| [rq5-design.md](rq5-design.md) | desenho leave-tools-out da RQ5 |
| [study-results.md](study-results.md) | relatório preliminar do split dev (substituído) |
| [decisions/2026-10-01-calibration-and-prompts.md](decisions/2026-10-01-calibration-and-prompts.md) | decisão: variantes de prompt e mapas de calibração |
| [prereg/prereg-v1.md](prereg/prereg-v1.md) | pré-registração prereg-v1 |
| [prereg/estimates.md](prereg/estimates.md) | estimativas de custo do prereg-v1 |
| [prereg/hashes.md](prereg/hashes.md) | hashes de config e prompt por run |
| [prereg/deviations.md](prereg/deviations.md) | desvios em relação ao prereg-v1 |
| [prereg/decisions-log.txt](prereg/decisions-log.txt) | log de decisões |
| [prereg/prereg-v2a.md](prereg/prereg-v2a.md) | pré-registro prereg-v2a (fase 2, Parte A) |
| [prereg/prereg-v2.md](prereg/prereg-v2.md) | pré-registro prereg-v2 (fase 2, Parte B, test-L) |
| [prereg/prereg-v2-draft.md](prereg/prereg-v2-draft.md) | rascunho do prereg-v2 (substituído) |
| [prereg/phase2-budget.md](prereg/phase2-budget.md) | marca de orçamento e tetos da fase 2 |
| [prereg/deviations-v2.md](prereg/deviations-v2.md) | desvios em relação ao prereg-v2a / prereg-v2 (DV2-001, D-L01) |
| [results/study_report.md](results/study_report.md) | saída do `study_report.py` no shadow run do dev |
| [results/prompt-selection.md](results/prompt-selection.md) | seleção de prompts |
| [results/cascade-thresholds-dev.md](results/cascade-thresholds-dev.md) | calibração de thresholds de cascade no dev |
| [results/final/primary.md](results/final/primary.md) | análise primária (H1-H3) no test-v2 |
| [results/final/secondary.md](results/final/secondary.md) | análises secundárias (S1-S4) |
| [results/final/estimation.md](results/final/estimation.md) | tabelas de estimação |
| [results/final/exploratory_e2e.md](results/final/exploratory_e2e.md) | análises e2e exploratórias (D-002) |
| [results/final/enterprise_matrix.md](results/final/enterprise_matrix.md) | matriz de decisão enterprise |
| [results/final/runs_status.md](results/final/runs_status.md) | status das runs do manifest |
| [results/final/study_report_test_v2.md](results/final/study_report_test_v2.md) | saída do `study report` no test-v2 |
| [results/phase1-sym/exploratory_e2e_sym.md](results/phase1-sym/exploratory_e2e_sym.md) | e2e da fase 1 com o scorer simétrico (exploratório) |
| [results/addendum-a/primary.md](results/addendum-a/primary.md) | fase 2, Parte A: família A (A1–A4) |
| [results/addendum-a/estimation.md](results/addendum-a/estimation.md) | fase 2, Parte A: tabelas de estimação |
| [results/addendum-a/enterprise_matrix.md](results/addendum-a/enterprise_matrix.md) | fase 2, Parte A: matriz enterprise com as opções gerenciadas |
| [results/phase2-dev-l/cascade-thresholds-dev-l.md](results/phase2-dev-l/cascade-thresholds-dev-l.md) | limiares das cascatas no dev-L |
| [results/phase2-dev-l/cascade-thresholds-dev-l-e8-unconstrained.md](results/phase2-dev-l/cascade-thresholds-dev-l-e8-unconstrained.md) | limiares do E8-L no dev-L, sem orçamento |
| [results/phase2-b/primary.md](results/phase2-b/primary.md) | fase 2, Parte B: H1-L, H2-L, H3-L no test-L |
| [results/phase2-b/secondary.md](results/phase2-b/secondary.md) | fase 2, Parte B: S1–S4, S7 |
| [results/phase2-b/estimation.md](results/phase2-b/estimation.md) | fase 2, Parte B: tabelas de estimação |
| [results/phase2-b/catalog_size.md](results/phase2-b/catalog_size.md) | fase 2, Parte B: 18 × 62 tools (X1–X4) |

## Arquivos de dados (somente em `docs/`)

- [`docs/results/`](../docs/results/): `cascade-pareto-dev.csv`, `cascade-thresholds-dev.yaml`, `prompt-apex-metrics.json` e os `.jsonl` das rodadas no dev.
- [`docs/results/final/`](../docs/results/final/): `primary.json`, `secondary.json`, `estimation.json`, `exploratory_e2e.json`, `enterprise_matrix.json`.
- [`docs/results/addendum-a/`](../docs/results/addendum-a/), [`docs/results/phase1-sym/`](../docs/results/phase1-sym/), [`docs/results/phase2-b/`](../docs/results/phase2-b/): os `.json` da fase 2 (`figure_data.json` inclusive).
- [`docs/results/phase2-dev-l/`](../docs/results/phase2-dev-l/): `cascade-thresholds-dev-l.yaml`, `tuned_blocks.yaml`, `summaries/` e `scripts/`.
