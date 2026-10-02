# Pré-registro prereg-v2 (RASCUNHO): adendo de nuvem (Parte A) e catálogo grande (Parte B)

> Tradução pt-BR de [`docs/prereg/prereg-v2-draft.md`](../../docs/prereg/prereg-v2-draft.md). Rascunho substituído pelas versões congeladas [prereg-v2a.md](prereg-v2a.md) e [prereg-v2.md](prereg-v2.md); em caso de divergência, vale o original em inglês.

Status: **RASCUNHO**. Não congelado. A versão congelada será `docs/prereg/prereg-v2.md`:
- a Parte A é congelada na tag git `prereg-v2a` antes da primeira linha nova do test-v2;
- a Parte B é congelada na tag `prereg-v2` antes da primeira linha do test-L.

Os campos marcados `TBD@freeze` são preenchidos no congelamento (hashes, limiares, mapas de calibração). Nenhum outro
campo pode mudar depois da tag. Plano: `.omc/plans/autopilot-impl.md`. Especificação: `.omc/autopilot/spec.md`.

## 0. O que é herdado do prereg-v1 sem mudança

- Unidade de análise = caso. As repetições são tiradas a média por caso.
- ITT: uma falha de infra ou de parse conta como erro.
- Multirrótulo: qualquer rótulo aceitável conta, com o primeiro rótulo como sensibilidade.
- Fora de escopo: escalonamento conta como abstenção.
- Bootstrap: bootstrap pareado por cluster (caso), 10,000 reamostragens, seed 20260930.
- Testes:
  - não inferioridade (NI) usa o limite inferior do IC 95% bilateral mais um p-valor sign-flip com deslocamento;
  - equivalência usa TOST, aceita quando o IC 90% fica dentro dos limites;
  - testes bilaterais usam o IC mais um p-valor sign-flip;
  - correção de Holm dentro de cada família.
- Cache de respostas por (caso, rep, prompt renderizado).
- A latência vem **só** do benchmark dedicado.
- O custo é reportado em três regimes.
- Regras de operação, retentativa e aborto como no §7 do prereg-v1.

## 1. Artefatos congelados (TBD@freeze)

| Artefato | Parte A | Parte B |
|---|---|---|
| Código | commit em `prereg-v2a` | commit em `prereg-v2` |
| Catalog hash | pequeno `128584617807` (sem mudança) | grande `TBD` (`CATALOG_PROFILE=large`) |
| Dados | `dataset_test_v2.jsonl` (sha `6637c479…`, sem mudança), dev `112fc7f0…` | `dataset_dev_l.jsonl` `TBD`, `dataset_test_l.jsonl` `TBD` (auditado, adjudicação automática) |
| Scorers | legacy `e0eef1fb0073` (roteamento; sensibilidade do e2e); sym `TBD` (`scorers_sym.py`) | igual |
| Prompt hash | `c61ad0a7b7f8` (P0; sem mudança de template) | igual |
| Manifesto | `config/addendum_manifest.yaml` sha `TBD` | `config/study_manifest_l.yaml` sha `TBD` |
| Limiares e calibração | escritos nas configs da Parte A | escritos em `config/experiments_l/*` (E7-L, E9-L pela regra (a)) |
| Trava de hashes da fase 1 | `tests/test_phase1_hashes.py` verde na tag | verde na tag |

## 2. Braços

- **Parte A (catálogo pequeno, test-v2, 349 casos).**
  - Roteadores novos: E3c (roteador por embedding Cohere embed-v4), E3t (roteador por embedding Titan v2), E10c e E10t
    (sondas lineares sobre esses vetores), E6m (Ministral 3 8B), E6n (Nemotron Nano 9B v2, raciocínio desligado).
  - Os braços de comparação reaproveitam as linhas congeladas da fase 1 nos mesmos casos: E6b Qwen3-8B local, E3
    qwen3-embedding 8B local, E10 sonda local. Haiku e Jev da fase 1 são só contexto.
- **Parte B (catálogo grande, test-L, ~300 casos).**
  - Roteamento: E1 regex, E2 BM25, E3 embedding local, E3c, E3t, E10 (local e Cohere), E11 híbrido, E4 Jev,
    E6 Haiku 4.5, E6b Qwen3-8B, E6m, E6n, E7-L (regex → Jev), E9-L (regex → Jev → Sonnet).
  - e2e: E0-L (Sonnet 5 nativo), E9-L, E9-L-fullskill (E9-L com `expose_top_k` = todas as tools da skill).
  - Todos os roteadores LLM usam **P0**. O Sonnet 5 aparece só como último passo do E9-L e como executor.

## 3. Hipóteses

### Parte A: família A (secundária, confirmatória para o adendo; Holm entre A1–A4; α = 0.05)

- **A1 (NI).** Conjunta(E6m Ministral) − Conjunta(E6b Qwen3-8B local) > −3 pp.
- **A2 (NI).** Conjunta(E6n Nemotron) − Conjunta(E6b) > −3 pp.
- **A3 (bilateral).** Conjunta(E3c Cohere) − Conjunta(E3 qwen3-embedding local).
- **A4 (bilateral).** Conjunta(E3t Titan) − Conjunta(E3 local).

Só estimação (sem teste): latência p50/p95 de cada estratégia nova contra as âncoras **gerenciadas** rodadas de novo na
mesma janela (Jev, Haiku 4.5) e contra os blocos de latência locais da fase 1 (lat-qwen, lat-embedding, lat-classifier:
outra janela, mesmo Mac; ressalva de janela e de hardware, deriva = o Δ das âncoras gerenciadas contra os seus blocos
lat-* da fase 1); custo por 1k; E10c/E10t; taxa de mudança (rep2 em 50 casos); taxa de falha de parse. Nenhum modelo
local roda na fase 2 (restrição de 2026-10-01): os braços locais são as linhas congeladas do test-v2 da fase 1. **A Parte A
está congelada em `docs/prereg/prereg-v2a.md`.**

Regra de decisão da matriz enterprise (descritiva): uma opção gerenciada "qualifica" num orçamento de latência quando
o limite superior do IC do seu p95 fica abaixo do orçamento **e** a sua conjunta não é inferior à do par local.

### Parte B: primárias (confirmatórias; Holm entre H1–H3; α = 0.05)

- **H1-L ("vale ter roteador?", e2e, scorer simétrico).** e2e_success_sym(E9-L) − e2e_success_sym(E0-L),
  bilateral, pareado, com IC 95%. Afirmação direcional só se o IC excluir 0.
  - O MDE esperado com n ≈ 300 é de cerca de 5.5–7.5 pp.
  - O reescore sym da fase 1 (exploratório, `docs/results/phase1-sym/`) é o prior de tamanho de efeito. Ele é anotado
    no congelamento e não muda o teste.
  - Estimativa co-primária: razão de custo por turno E9-L / E0-L, regime observado, com IC.
- **H2-L (8B gerenciado × local).** Conjunta(E6m Ministral) − Conjunta(E6b Qwen3-8B) > −3 pp (NI).
  - Estimativa co-primária: a razão de p95 de latência E6m / E6b, do benchmark.
- **H3-L (meta-roteador barato × LLM pequeno premium).** Conjunta(E4 Jev) − Conjunta(E6 Haiku 4.5) > −3 pp (NI).

### Parte B: secundárias

- **Família S-e2e** (Holm dentro):
  - **S1.** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, unilateral. Confirma o achado
    exploratório D-002 da fase 1 num split novo.
  - **S2.** e2e_success_sym(E9-L) − e2e_success_sym(E0-L) restrito aos casos em que os dois braços fizeram as mesmas
    chamadas de negócio. Se a assimetria de atribuição sumiu, isso deve dar ≈ 0, então o teste é de equivalência
    ±3 pp (TOST).
- **Família S-routing** (Holm dentro):
  - **S3.** Regex conjunta test-L − CV dev-L < 0 (magnitude com IC; dev fixo).
  - **S4.** Conjunta(E3 local) − Conjunta(E1 regex), bilateral.
  - **S5.** Conjunta(E3c Cohere) − Conjunta(E3 local), bilateral.
  - **S6.** Conjunta(E6n Nemotron) − Conjunta(E6b) > −3 pp (NI).
  - **S7.** Conjunta(E10 melhor sonda pré-declarada) − Conjunta(E4 Jev), bilateral. A "melhor sonda pré-declarada" é a
    sonda com a maior conjunta de CV aninhada no dev-L, fixada no congelamento.

**Sensibilidade, não testada.**
- H1-L com o **scorer legacy assimétrico** (`e2e_success` do prereg-v1). Os dois números são reportados lado a lado,
  junto com a contagem de casos em que o veredito difere.
- Também: conjunta só com o primeiro rótulo; a interseção sem erros; ambiguo reportado à parte; os casos sinalizados por humano excluídos.

### Só estimação (ICs, sem testes)

Por estratégia:
- skill %, tool % condicional, recall@1/2/3;
- taxas de erro e de parse; taxas de mudança entre repetições (Haiku 60, Qwen/8B 50);
- ECE e Brier (bruto e calibrado no dev-L);
- custo por 1k (três regimes);
- latência p50/p95 (primeiro caso frio à parte);
- cobertura das cascatas por passo, incluindo **a cobertura do regex no seu limiar**;
- precisão e recall da abstenção;
- a decomposição do e2e, mais `args_invented`, `entity_grounded` e a variância do executor (E0-L e E9-L em 60 casos);
- por categoria, por skill (original × nova), por grupo confundível G1–G12.

### Exploratório: tamanho do catálogo, 18 × 62 tools

- **X1 (entre datasets, não pareado).** Para cada estratégia presente nas duas fases, Conjunta(test-L) − Conjunta(test-v2), com
  bootstraps **independentes** por split, e a mesma comparação para o e2e de E0/E9 (scorer sym nos dois).
  - **Ressalva (obrigatória onde aparecer):** os datasets diferem. Eles têm casos diferentes, conjuntos de rótulos
    diferentes e texto de catálogo diferente. Eles compartilham o gerador, as proporções de categoria e o procedimento de
    deduplicação, mas a dificuldade dos casos não é controlada. Os roteadores são reajustados por catálogo, então Δ mede
    "sistema com 18 × sistema com 62", não um efeito puro de tamanho. As acurácias absolutas não são estimativas de produção.
- **X2 (subconjunto pareado de tamanho de catálogo, estimação secundária).** O subconjunto orig do test-L é todo caso cujas
  tools aceitáveis estão todas entre as 18 originais, ou que é fora de escopo; n ≥ 60 é garantido pela cota.
  - Ele é roteado pelos roteadores do perfil pequeno (configs da fase 1, congeladas) e pelos roteadores do perfil grande
    nos **mesmos casos**, dando um Δ conjunta pareado com IC por estratégia: roteadores livres, Jev, Ministral, Haiku.
  - Isso isola o efeito de acrescentar 44 tools confundíveis em casos que o catálogo pequeno consegue responder.
  - Ressalva que resta: cada perfil tem o seu próprio ajuste (dev × dev-L).
- **X3.** Comportamento do cache do Haiku com o prompt maior (ele passa do mínimo de cache de 4,096 tokens?) e o seu
  efeito no custo.
- **X4.** Reescore sym da fase 1 (já rodado antes do congelamento; reportado como exploratório e nunca reclassificado).

## 4. Métricas e scorers

- **Primária de roteamento:** acurácia conjunta top-1 (scorer legacy de roteamento, sem mudança).
- **Primária do e2e:** `e2e_success_sym` (`src/routing_study/eval/scorers_sym.py`). A skill é atribuída pelo
  comportamento, de forma idêntica nos dois braços:
  1. a skill da primeira tool de negócio que o servidor executou;
  2. senão, a skill da tool creditada por uma clarificação, inferida da pergunta feita, nunca da
     tool do roteador;
  3. senão, um turno só de escalonamento ou uma abstenção do host → `__abstain__`;
  4. só chamadas globais → `__global__`;
  5. nenhuma ação → `__abstain__`.

  Sucesso = a skill atribuída é aceitável **e** (a primeira chamada está OK com args válidos e terminou, **ou**
  uma clarificação é creditada, **ou** uma chamada posterior recupera). A decomposição e o `args_invented` são como no
  prereg-v1. O scorer nunca lê `native`, a skill ou a tool do roteador, nem `resolved_by`. Um teste de unidade garante isso.
- **Sensibilidade do e2e:** `e2e_success` legacy.

## 5. Ajuste e limiares (tudo no dev / dev-L; congelados na tag)

- **Prompt.** P0 para todo roteador LLM, sem busca de prompt nova. Uma correção só de formato é permitida por modelo se a
  taxa de falha de parse no dev for > 2%; ela é registrada.
- **Roteadores livres.** Grades da fase 1, CV aninhada de 5 folds. O regex é escrito por um agente com timebox de 4 h, com uma
  rodada opcional e registrada de 2 h.
- **Calibração.** Mapas isotônicos ou Platt pelo Brier da CV, aplicados só se `ece_cal < ece_raw`.
- **Limiares das cascatas E7-L e E9-L.** Regra (a) do prereg-v1 §4: conjunta máxima sujeita a custo de roteamento ≤ 0.5 ×
  o custo por caso do Sonnet 5 P0 no dev-L. Grade 0.50..0.99, passo 0.01. Ajuste cruzado no shadow do dev-L (Sonnet
  1 rep, só no dev; OQ-1).
  - Fallback se OQ-1 = não: o Sonnet sai do shadow, o último passo do E9-L é reproduzido como "decisão do Jev"
    no ajuste dos limiares, e isso é registrado como limitação de desenho.
- **Registro de esforço:** `docs/tuning-effort-l.md`.

## 6. Esboço do manifesto de runs (`config/study_manifest_l.yaml`; Parte A em `config/addendum_manifest.yaml`)

Parte A (test-v2), em ordem de prioridade:

| Prioridade | Runs |
|---|---|
| 10 | E3c, E3t, E10c, E10t (1 rep) |
| 20 | E6m, E6n (1 rep) |
| 21 | E6m, E6n rep2 em 50 casos |
| 70 | blocos `lat-a-*` 1–4 × {E3c, E3t, E10c, E10t, E6m, E6n} + âncoras gerenciadas {jev, haiku}, intercalados por bloco, `config/manifest/latency_test_v2_b*.ids` (sem âncora local: latência local = blocos lat-* da fase 1) |

Parte B (test-L), em ordem de prioridade:

| Prioridade | Runs |
|---|---|
| 10 | Roteadores livres 1 rep: E1, E2, E3, E3c, E3t, E10, E10c, E11; E1 repeat20 |
| 20 | Shadow ajustado, 3 reps, **sem Sonnet**: regex, bm25, embedding, classifier, hybrid, jev |
| 25 | E4 Jev 3 reps (H3-L); E6 Haiku 1 rep (H3-L); E6m 1 rep (H2-L); E6b Qwen 1 rep (H2-L, concorrência 1); E6n 1 rep |
| 30 | E9-L roteamento 3 reps; E7-L roteamento 3 reps |
| 40 | **E0-L e2e r1, E9-L e2e r1 (H1-L)** |
| 45 | E9-L-fullskill e2e r1 (S1) |
| 50 | Verificações de repetição: Haiku rep2 60, Qwen/8B rep2 50 |
| 70 | Blocos de latência 1–4 × {regex, bm25, embedding, E3c, E3t, classifier, hybrid, jev, haiku, qwen, E6m, E6n, E7-L, E9-L}, `latency_test_l_b*.ids` |
| 80 | Subconjunto pareado X2, perfil pequeno (`mcp_url` :8765): E1, E2, E3, E10, E11, E4, E6m, E6 Haiku |
| 90 | Variância do executor: E0-L, E9-L rep2 em 60 |

Cada entrada carrega `config_hash`, `prompt_hash` e `catalog_hash`. A guarda de versão verifica os três.

## 7. Orçamento

- **Marca do ledger da fase 2:** AWS 52.11, OpenRouter 5.83.
- **Teto da fase 2:** US$ 40 no total, dos quais os tetos das runs são AWS ≤ 29.0 e OR ≤ 9.0.
- **Gasto esperado:** US$ 28.0, ou 35.1 com 25% de contingência. Por item: `.omc/plans/autopilot-impl.md` §5.
  No congelamento: `docs/prereg/estimates-l.md`, com o limite superior a priori e o valor esperado a partir do custo
  por caso e por turno medido no dev-L.
- **Guarda:** roda antes de toda run. Uma run recusada é um desvio e é reportada como não rodada. As runs nunca são
  reordenadas.

## 8. Regras de parada e de desvio

- Nenhuma mudança de configs, prompts, rótulos, limiares, mapas de calibração, catálogo ou scorers depois da primeira linha
  do split que eles governam: linhas do test-v2 para a Parte A, linhas do test-L para a Parte B.
- Erros de infra: até 2 retentativas das linhas de erro. Uma run com > 2% de erros é FLAGGED e refeita do zero,
  nunca remendada.
- **Parada por orçamento:** se o delta do ledger da fase 2 chegar a US$ 38 antes de toda run com prioridade ≤ 40 estar COMPLETE,
  parar e registrar um desvio. As primárias são reportadas com o que estiver COMPLETE. Uma primária incompleta é reportada
  como não rodada, nunca imputada.
- **Parada por dados:** se a auditoria do test-L sinalizar mais de 40% dos casos, parar antes da tag e decidir (com registro) se
  regenera as vagas afetadas. Isso acontece antes do congelamento, então não é desvio.
- Correções de rótulo depois da run vão para um reescore separado e nunca substituem a análise.
- Os desvios são acrescentados a `docs/prereg/deviations-v2.md` com timestamp.

## 9. Plano de análise

1. **Parte A.** `scripts/analysis/addendum_all.py` → `docs/results/addendum/`: família A (Holm), tabelas de estimação
   e latência com âncoras. A deriva em relação à fase 1 é reportada como Δ p50/p95 das âncoras contra os valores lat-* da fase 1.
2. **Parte B.** `scripts/analysis/final_l_all.py` → `docs/results/phase2/` (`primary.md`, `secondary.md`,
   `estimation.md`, `exploratory.md`, `enterprise_matrix_l.md`, figuras). Todo número é marcado [C], [E] ou [X].
   H1-L aparece com os dois scorers.
3. **18 × 62** (X1, X2) em `docs/results/phase2/catalog_size.md`, com a ressalva repetida na legenda de toda tabela.
4. **Relatório:** capítulos novos em pt-BR em `estudos/` (resultados de tamanho de catálogo, o adendo de nuvem, a matriz
   enterprise atualizada e as ameaças à validade) mais o espelho em `docs/`. Os capítulos da fase 1 não são editados, a não ser por links.

## 10. Pendências a resolver antes do congelamento

- OQ-1: se o shadow do dev-L pode incluir o Sonnet 5 com 1 rep (~US$ 1.35) para ajustar os limiares do E9-L.
- OQ-2: se o S2 (a equivalência no subconjunto com as mesmas chamadas) continua um teste, ou vira estimação se o subconjunto
  tiver menos de 60 casos.
- OQ-3: a cota final por skill do subconjunto orig (≥ 30% dos casos de rótulo único) contra a cobertura por tool das
  tools novas.

## Atualização de restrição (2026-10-02, decisão do usuário, vinculante)

- **Nenhum modelo local.** Nada de Ollama na fase 2 (sem Qwen3-8B, sem qwen3-embedding local): a inferência local
  perturbaria desempenho/latência. Regex e BM25 (CPU, sem modelo) ficam. Os braços locais nas comparações
  são as linhas EXISTENTES da fase 1 (acurácia no test-v2, latência lat-* da fase 1), nunca rodadas de novo.
- **OpenRouter = só Jev** (`typesafe/jev-router`); saldo de US$ 3.91 reservado para ele.
- **Todo o resto no Bedrock, teto de US$ 40** (AWS). A geração e a auditoria do dataset passam para o Bedrock
  (`scripts/dataset/bedrock_chat.py`, mesmo contrato de `openrouter.chat_json`):
  - gerador **`moonshotai.kimi-k2.5`** (família Moonshot: nem roteador, nem auditor);
  - auditores **`openai.gpt-oss-120b-1:0`** (família OpenAI, reasoning_effort low) e
    **`deepseek.v3.2`** (família DeepSeek): as mesmas duas famílias que auditaram o test-v2.
  - Escolhidos por um smoke em pt-BR em 2026-10-02 (o Kimi produziu o pt-BR coloquial mais natural e um
    caso ambíguo rotulado corretamente; o GLM-5 rotulou um errado).
- A deduplicação semântica usa o Bedrock Titan v2 (não o embedder local).
- Os roteadores de embedding/classificador/híbrido do perfil grande usam embeddings do Bedrock (Cohere v4 ou Titan v2,
  o que vencer a CV no dev da Parte A). H2-L (8B gerenciado × local) é reespecificada: Ministral × Haiku 4.5
  (NI, 3 pp), já que nenhum braço local roda no test-L.
