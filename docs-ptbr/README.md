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
| [dataset-card.md](dataset-card.md) | dataset card do benchmark (test-v1, test-v2) |
| [prompt-apex.md](prompt-apex.md) | estudo de prompt dos roteadores (trilhas canônica e ajustada) |
| [tuning-effort.md](tuning-effort.md) | esforço de tuning por estratégia |
| [rq5-design.md](rq5-design.md) | desenho leave-tools-out da RQ5 |
| [study-results.md](study-results.md) | relatório preliminar do split dev (substituído) |
| [decisions/2026-10-01-calibration-and-prompts.md](decisions/2026-10-01-calibration-and-prompts.md) | decisão: variantes de prompt e mapas de calibração |
| [prereg/prereg-v1.md](prereg/prereg-v1.md) | pré-registração prereg-v1 |
| [prereg/estimates.md](prereg/estimates.md) | estimativas de custo do prereg-v1 |
| [prereg/hashes.md](prereg/hashes.md) | hashes de config e prompt por run |
| [prereg/deviations.md](prereg/deviations.md) | desvios em relação ao prereg-v1 |
| [prereg/decisions-log.txt](prereg/decisions-log.txt) | log de decisões |
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

## Arquivos de dados (somente em `docs/`)

- [`docs/results/`](../docs/results/): `cascade-pareto-dev.csv`, `cascade-thresholds-dev.yaml`, `prompt-apex-metrics.json` e os `.jsonl` das rodadas no dev.
- [`docs/results/final/`](../docs/results/final/): `primary.json`, `secondary.json`, `estimation.json`, `exploratory_e2e.json`, `enterprise_matrix.json`.
