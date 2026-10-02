# Desvios em relação ao prereg-v2a / prereg-v2

> Tradução pt-BR de [`docs/prereg/deviations-v2.md`](../../docs/prereg/deviations-v2.md). Em caso de divergência, vale o original em inglês.

Acrescente uma entrada por desvio: timestamp ISO, run, o que mudou, por quê, e o efeito na
análise pré-registrada (prereg-v2a §7).

## DV2-001 — 2026-10-02T00:43:34-03:00
- **Runs:** nenhuma (só o nome da análise).
- **O que mudou:** o prereg-v2a §8 nomeia o script de análise `scripts/analysis/addendum_all.py`, escrevendo em `docs/results/addendum/`; a tarefa T2.6 o implementou como `scripts/analysis/addendum_a.py`, escrevendo em `docs/results/addendum-a/` (e as figuras `estudos/figuras/final-a-*.png`).
- **Por quê:** especificação da tarefa pelo coordenador (T2.6), para manter as saídas da Parte A separadas de uma análise posterior da Parte B.
- **Efeito na análise:** nenhum. As mesmas hipóteses (A1-A4, Holm), a mesma maquinaria (bootstrap pareado por cluster 10k, seed 20260930, p sign-flip), a mesma lista de estimação; o catalog/config/prompt hash de toda linha verificado como no §8.

## DV2-002 — 2026-10-02T00:43:34-03:00
- **Runs:** nenhuma (só o momento da análise).
- **O que mudou:** o script de análise da Parte A, `scripts/analysis/addendum_a.py`, teve o primeiro commit em 2026-10-02 00:43:34 (commit `2a9bda4`), depois da tag `prereg-v2a` (commit `d4b1463`, 00:02:22) e depois das runs da Parte A (00:03:42–00:30:38, `results/phase2a/run-manifest.log`). O script não está na tag `prereg-v2a`.
- **Por quê:** as runs da Parte A foram lançadas logo após o congelamento, e o código de análise foi escrito durante e depois delas.
- **Efeito na análise:** limitado a escolhas de implementação da análise. As hipóteses (A1-A4, Holm) e a estatística (bootstrap pareado por cluster 10k, seed 20260930, p sign-flip, lista de estimação) estavam congeladas no prereg-v2a §3/§8 antes de existir qualquer linha da Parte A.

## D-L01 — 2026-10-02T10:11:44-03:00
- **Runs:** `config/study_manifest_l.yaml` (prereg-v2, test-L), interrompido durante `l-shadow-tuned-routing-r3` (o passe shadow que preenche o cache; não é um braço analisado) e retomado por (caso, rep). Todas as outras runs começaram depois da retomada.
- **O que mudou:** apenas infra. Às 10:08:19 o processo filho do app-redis foi morto por falta de memória durante um fork de reescrita do AOF; auto-aof-rewrite e o save RDB foram desligados durante a run (`results/phase2b/redis-restore.sh`). Às 10:11:44 o próprio app-redis foi morto por falta de memória (VM do Docker com 8.3 GB) por ~811k chaves antigas de checkpoint do LangGraph (~2 GB), deixadas por runs anteriores. O manifesto foi parado; as chaves `checkpoint*` / `write_keys_zset` foram apagadas com a aprovação do usuário (todo resultado já está em `results/*.jsonl`), o Redis foi de 2.05 GB para 141 MB, e o manifesto foi retomado. As 66 linhas de erro da run shadow na janela da queda (7.3%) foram retentadas uma vez pela regra de retentativa pré-registrada do runner (prereg-v2 §7: até 2 retentativas das linhas de erro) e terminaram COMPLETE com 0 erros. A config do Redis foi restaurada depois do fim do manifesto (12:36:52). Log: `results/phase2b/launch.log`, `results/phase2b/run-manifest.log`.
- **Por quê:** o checkpointer do LangGraph no host guarda o estado por thread no Redis; nada expirava os checkpoints da fase 1 / Parte A / dev-L.
- **Efeito na análise:** nenhum. Nenhuma mudança de config, prompt, rótulo, catálogo, limiar, scorer, manifesto, arquivo de ids ou `phase2_b.py`; todo `config_hash` / `prompt_hash` / `catalog_hash` é o congelado (verificado em toda linha pelo `phase2_b.py`). Estado final: 73/73 runs COMPLETE, 0 linhas de erro no log do manifesto. Os checkpoints do LangGraph são estado de conversa por turno, não resultados; nenhuma linha analisada depende de uma chave apagada.
