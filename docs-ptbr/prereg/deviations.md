# Desvios em relação ao prereg-v1

Anexe uma entrada por desvio: timestamp ISO, run, o que mudou, por quê e seu efeito na
análise pré-registrada. Vazio na tag.

## D-001 — 2026-10-01T15:18:56-03:00
- **Run:** v2-e3-embedding-bgem3-routing-r1 (manifesto abortado antes do seu primeiro caso; 7 runs já COMPLETE com 0 erros e não afetadas).
- **O que mudou:** correção apenas de infra em `src/routing_study/llm.py` (`_check_ollama`): a comparação de nomes de modelo agora normaliza a tag implícita `:latest` do Ollama (`bge-m3` == `bge-m3:latest`). Nenhuma mudança de config, prompt, rótulo, catálogo ou scorer; config_hash/prompt_hash de todas as runs inalterados.
- **Por quê:** a checagem de modelo do pre-flight rejeitou um modelo já baixado e abortou o manifesto inteiro.
- **Efeito na análise:** nenhum (nenhuma linha de test_v2 foi produzida ou alterada pela checagem que falhou). Manifesto retomado; runs concluídas são puladas pela chave.

## D-002 — 2026-10-01T19:45:50-03:00
- **Runs:** x-e9-fullskill-e2e-r1, x-e7-fullskill-e2e-r1 (config/study_manifest_explore.yaml), lançadas após a conclusão do manifesto pré-registrado.
- **O quê:** EXPLORATÓRIO, post-hoc. Mesmas configs de E9/E7 com `routing.tool.expose_top_k: 5` (rotear a skill, expor ao executor todas as 5 tools da skill + as globais).
- **Por quê:** o resultado pré-registrado de H3 (e2e_success de E9 45.8% vs E0 nativo 55.6%), com E5 igualando E0 em tool na primeira chamada (75.1%), sugere que esconder tools auxiliares do executor, e não apenas o erro de routing, explica o gap e2e. Hipótese gerada após ver os resultados de test-v2.
- **Efeito na análise:** nenhum sobre H1–H3/S1–S4 (resultados pré-registrados inalterados). Reportado apenas como comparação exploratória, geradora de hipóteses, no mesmo split de teste (não confirmatória; qualquer afirmação exige um split novo).

## D-003 — 2026-10-01T20:21:04-03:00
- **Runs:** v1-* (replicação EXPLORATÓRIA do free-router no test-v1); o manifesto principal parou em v1-e1-regex-routing-r1 antes do seu primeiro caso. Todas as runs confirmatórias e de estimação já estavam COMPLETE.
- **O que mudou:** apenas infra (`eval/runner.py`): o split `test_v1` (um symlink para o `dataset_test.jsonl` original) faz upload para o dataset Langfuse já existente `routing-study-test`, porque ids de item de dataset no Langfuse são únicos por projeto e esses ids já pertencem àquele dataset. Nenhuma mudança de config/prompt/rótulo/scorer.
- **Efeito na análise:** nenhum; as runs v1 recomeçam do zero.

## Fase 2

Os desvios em relação ao prereg-v2a e ao prereg-v2 ficam em [deviations-v2.md](deviations-v2.md)
(prereg-v2 §7): DV2-001 (nome da análise da Parte A) e **D-L01** (test-L, 2026-10-02: app-redis
morto por falta de memória por checkpoints antigos do LangGraph; chaves apagadas com aprovação do
usuário, run retomada; só infra, sem efeito na análise).
