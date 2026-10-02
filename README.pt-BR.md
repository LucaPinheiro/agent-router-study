<div align="center">

# agent-router-study

**Como um agente deve decidir qual skill e qual tool usar, e ele precisa mesmo de um roteador?**
Uma comparação pré-registrada e reproduzível de regex, BM25, embeddings densos, um classificador
treinado, um híbrido, LLMs de uso geral (Bedrock e locais) e o modelo de decisão Jev, isolados e em
cascata, num agente LangGraph, num servidor MCP e num dataset rotulado em pt-BR.

[Resultados](#resultados-principais) · [Arquitetura](#arquitetura) · [Início rápido](#início-rápido) ·
[Reproduzir o estudo](#reproduzir-o-estudo) · [Estudo completo](estudos/README.md) ·
[English](README.md)

</div>

---

## O que é

O padrão *agent-skill* mantém o contexto do agente pequeno: algumas **tools globais** ficam sempre
visíveis e cada **skill** (um conjunto de tools de domínio mais um playbook) é carregada sob
demanda. O roteamento pode então acontecer em dois estágios, fora do LLM executor:

1. **Skill:** a que skill a mensagem pertence (ou nenhuma: abster ou escalar)?
2. **Tool:** dentro dessa skill (mais as globais), quais tools o executor deve ver?

Este repositório mede, no mesmo agente e nos mesmos dados, **acurácia × custo × latência × esforço
de manutenção** de cada estratégia e de cascatas ("o primeiro roteador confiante decide"), e
compara o agente roteado com um agente **nativo**, que chama `load_skill` sozinho.

O run confirmatório foi pré-registrado (tag `prereg-v1`) e executado uma única vez num split novo
(`test_v2`, 349 casos) que nenhum roteador, prompt ou limiar tinha visto. O relatório completo está
em [`estudos/`](estudos/README.md).

## Resultados principais

test-v2, 349 casos, intenção de tratar, IC 95% por bootstrap pareado por caso (10 mil reamostragens).
Acurácia conjunta de roteamento = skill e tool certas no top-1.

| Config | Roteador | Conjunta % [IC 95%] | US$ de roteamento / 1k casos | p95 quente |
|---|---|---|---|---|
| E1 | regex | 52,7 [47,3; 57,9] | 0 | 0,4 ms |
| E2 | BM25 | 49,0 [43,8; 54,2] | 0 | 7 ms |
| E3 | embeddings (qwen3-embedding 8B, local) | 73,6 [68,8; 78,2] | 0 | 0,7 s |
| E10 | classificador (sonda linear, local) | 74,8 [70,2; 79,4] | 0 | 1,0 s |
| E11 | híbrido regex + classificador (local) | 72,8 [67,9; 77,4] | 0 | 1,0 s |
| E6b | Qwen3-8B (local, Ollama) | 79,9 [75,6; 84,0] | 0 | 12,0 s |
| E4 | Jev (`typesafe/jev-router` via OpenRouter) | **84,7** [81,0; 88,2] | **0,82** | 6,9 s |
| E5 | Claude Sonnet 5 (Bedrock) | 84,1 [80,3; 87,8] | 4,98 | 11,0 s |
| E6 | Claude Haiku 4.5 (Bedrock) | 84,5 [80,5; 88,3] | 5,23 | 5,9 s |
| E7 | regex → Jev | 79,9 [75,8; 84,0] | 0,73 | 7,1 s |
| E9 | regex → Jev → Sonnet | 81,8 [77,8; 85,6] | 0,99 | 9,9 s |

Hipóteses pré-registradas ([primary.md](docs/results/final/primary.md),
[secondary.md](docs/results/final/secondary.md)):

- **H1** cascata E9 × Sonnet 5: −2,4 pp [−5,4; 0,7]; não inferioridade (margem 3 pp) **não
  demonstrada**. Razão de custo de roteamento 0,199 [0,174; 0,224].
- **H2** cascata E7 × Sonnet 5: −4,2 pp [−7,8; −0,6]; não inferioridade **não demonstrada**.
- **H3** ponta a ponta, E9 roteado × E0 nativo (executor Sonnet 5): `e2e_success` 45,8% × 55,6%,
  **−9,7 pp [−13,5; −6,0]**, Holm p 0,0003. **O agente nativo vence o roteado**, e o roteador
  economiza só ~9% por turno (razão de custo 0,909 [0,859; 0,960]).
- Engenharia de prompt: a regra de um erro-padrão manteve o prompt base P0 para os quatro LLMs;
  nenhum ganho de ajuste foi encontrado. A equivalência entre modelos (±3 pp contra o Sonnet) não
  se estabeleceu depois de Holm.
- As regras de regex escritas no dev caíram de 84,8% (dev) para 52,7% (teste): **−32,1 pp**.

Exploratório (post hoc, mesmo split): expor todas as tools da skill roteada em vez das top-2 levou
o E9 a 48,1% (ainda −7,4 pp contra o nativo). Em 22 dos 40 casos que só o nativo resolveu, o
executor roteado fez exatamente as mesmas chamadas de tool e falhou só pela pontuação do rótulo de
skill do roteador; ver [estudos/07](estudos/07-ponta-a-ponta.md).

![Acurácia × custo de roteamento](estudos/figuras/final-pareto-accuracy-cost.png)

**Leitura prática para este catálogo (18 tools):** não coloque um roteador na frente do agente;
se precisar de um (governança, auditoria, catálogo crescendo), o Jev sozinho tem a acurácia do
Sonnet 5 por cerca de um sexto do custo; nenhum roteador testado chega a 75% de conjunta com p95
abaixo de 2 s. Matriz de decisão por caso de uso: [estudos/11](estudos/11-matriz-enterprise.md).

## Arquitetura

```mermaid
flowchart LR
    U["Mensagem do usuário<br/>+ histórico curto"] --> I[ingest]
    I --> RS["route_skill<br/>pipeline, ex.: regex → Jev → Sonnet"]
    RS -- abstém --> ESC["escalate_to_human"]
    RS -- skill --> RT["route_tool<br/>pipeline, expõe top-k"]
    RT --> A["agent (executor Sonnet 5)<br/>vê top-k + globais"]
    A <--> T["tools<br/>servidor MCP (dados fictícios)"]
    A --> R[resposta]

    classDef router fill:#e3eefc,stroke:#2f6fd6,stroke-width:2px;
    class RS,RT router;
```

| Componente | O que é | Onde |
|---|---|---|
| **Servidor MCP** | FastMCP: 3 skills × 5 tools + 3 tools globais, recursos de skill e política, banco fictício determinístico; a única fonte do catálogo que todos os roteadores leem | [`mcp_server/`](mcp_server) |
| **Agente** | `StateGraph` do LangGraph (`ingest → route_skill → route_tool → agent ⇄ tools`) com checkpointer no Redis; no modo nativo (E0) o executor chama `load_skill` sozinho | [`src/routing_study/graph`](src/routing_study/graph) |
| **Roteadores** | Um contrato (escolha, confiança, candidatos, custo, latência) para os dois estágios: regex, BM25, embedding, classificador, híbrido, LLM (Bedrock / Ollama), Jev; pipelines `single`, `cascade`, `shadow` | [`src/routing_study/routers`](src/routing_study/routers) |
| **Provedores** | AWS Bedrock (Claude Sonnet 5, Haiku 4.5), OpenRouter (Jev, geração do dataset, auditoria de rótulos), Ollama (Qwen3-8B, qwen3-embedding) | [`src/routing_study/llm.py`](src/routing_study/llm.py) |
| **Observabilidade** | Langfuse v4: um trace por turno, spans por nó do grafo e por passo de roteamento, chamadas MCP como spans filhos; cada run é um experimento de dataset | [`src/routing_study/tracing`](src/routing_study/tracing) |
| **Avaliação** | Runner, rescore offline (a única fonte de números), executor de manifesto pré-registrado com trava de versão e ledger de gastos, estatística (bootstrap pareado por caso, McNemar, permutação de sinais, Holm, TOST) | [`src/routing_study/eval`](src/routing_study/eval) |
| **Dataset** | Pós-venda de e-commerce em pt-BR: dev 151, test-v1 349 (exposto), test-v2 349 (confirmatório, gerado por um modelo fora da família Claude, auditado às cegas por duas outras famílias) | [`data/`](data), [dataset card](docs/dataset-card.md) |

## Início rápido

Requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, chave do OpenRouter, credenciais
AWS com acesso ao Bedrock (cadeia padrão do boto3, região `sa-east-1`) e, para os roteadores locais,
[Ollama](https://ollama.com) com `qwen3:8b-q8_0` e `qwen3-embedding:8b-q8_0`.

```bash
git clone https://github.com/LucaPinheiro/agent-router-study.git
cd agent-router-study
uv sync
cp .env.example .env            # OPENROUTER_API_KEY, chaves do Langfuse, MCP_TOKEN, REDIS_URL

make up                         # Langfuse v4 (http://localhost:3300) + Redis
make up-app                     # + servidor MCP em :8765
make health

uv run study estimate -c config/experiments/e9_regex_jev_llm.yaml --split dev --mode routing-only
uv run study run -c config/experiments/e9_regex_jev_llm.yaml --split dev --mode routing-only --limit 10
uv run study run -c config/experiments/e0_native.yaml --split dev --mode e2e --limit 10
uv run study budget             # ledger de gastos por provedor e modelo
make test && make lint
```

## Reproduzir o estudo

```bash
BUDGET__AWS_USD_CAP=85 uv run study run-manifest config/study_manifest.yaml   # 102 runs pré-registrados
uv run study run-manifest config/study_manifest_explore.yaml                  # 2 runs exploratórios (D-002)
uv run python scripts/analysis/final_all.py                                   # todas as tabelas e figuras
```

O manifesto fixa o `config_hash` e o `prompt_hash` de cada run, confere o orçamento antes de cada
um, retoma por (caso, repetição) e marca runs com mais de 2% de erros. Hashes congelados, desvios
(D-001 a D-003) e comandos por tabela estão em [`docs/prereg/`](docs/prereg/prereg-v1.md) e em
[estudos/13](estudos/13-reprodutibilidade.md). Saídas da análise:
[`docs/results/final/`](docs/results/final/). Gasto do estudo final: US$ 34,48 no Bedrock +
US$ 1,43 no OpenRouter (ledger do projeto inteiro: US$ 52,11 Bedrock, US$ 5,83 OpenRouter).

## Limitações

Um domínio, um idioma, 18 tools: nesse tamanho o agente nativo é forte, e as conclusões não se
estendem automaticamente a catálogos com centenas de tools. Os dados são sintéticos e os rótulos
foram auditados por modelos, não por humanos. "Jev" aqui é o `typesafe/jev-router` via OpenRouter,
um meta-roteador cujo modelo atendido varia por chamada, e não a API tipada nativa do Jev. Lista
completa: [estudos/12](estudos/12-limitacoes.md).

Documentação técnica em português: [`docs-ptbr/`](docs-ptbr/README.md) espelha [`docs/`](docs/)
(pré-registro, métricas, dataset card, resultados finais). No Langfuse local há um painel
personalizado, "Agent Router Study: operação", com 9 widgets ([estudos/13](estudos/13-reprodutibilidade.md)).

O relatório anterior, só com o dev ([docs/study-results.md](docs/study-results.md)), foi
**substituído** por este estudo.
