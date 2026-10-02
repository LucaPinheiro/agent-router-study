# Handoff: phase 2, regex rules for the large catalog (T5.1, catalog-only part)

Branch `feat/phase2-cloud-and-large-catalog`. One commit (see `git log -1 -- config/regex_rules_l.yaml`).

## What exists

- `config/regex_rules_l.yaml` (478 lines): 73 option ids (10 skills + `__global__` + 62 tools),
  235 rules (91 at the skill stage, 144 at the tool stage), 64 of them suppressors, and 46 defs.
  It replaces the T3.3 stub and keeps the same format and loader (`RegexRules.load`).
  - The 79 phase-1 rules are byte-identical. The original ids get 43 new rules: 39 G1–G12
    suppressors, 3 `__global__` rules for the new globals, and 1 escalate_to_human rule (senha /
    login).
  - The OFF_SCOPE def drops "nota fiscal|precos", which are in scope in the large catalog, and
    gains "senha|login|atacado|estoque".
  - It was written from the catalog only. **No dataset file was read** (no `data/*`, no
    dev-L).
- `tests/routers/test_regex_rules_l.py` (129 cases):
  - every rule key is a catalog id;
  - each of the 62 tools gets ≥ 2 of its 4 `_meta` examples end to end (skill stage over 11
    options, then tool stage over the skill's tools + 5 globals);
  - the phase-1 phrase tests pass on the large option sets, both with and without globals;
  - one probe per tool in each G1–G12 group (34 cases).
- `docs/tuning-effort-l.md` §B "regex": the effort row, rule counts, decisions and in-sample
  hit rates.

## Numbers (in-sample: the rules were written against these phrases)

- `_meta` examples: 231/248 (93.1%).
  - The 44 new tools hit 176/176.
  - The 18 originals hit 55/72. That is the same set the phase-1 rules hit on the small
    catalog: 0 regressions, 0 gains.
- WHEN TO USE quotes: 118/121.
- SKILL.md examples at the skill stage: 50/50.
- G1–G12 probes: 34/34.
- Per skill:

  | Skill | Hits |
  |---|---|
  | 7 new skills | 24/24 each |
  | `__global__` | 19/20 |
  | trocas_devolucoes | 16/20 |
  | pagamentos_reembolsos | 15/20 |
  | pedidos_logistica | 13/20 |

## Effort

- About 0.4 h of agent wall-clock, 0 human hours, 0 dev passes, US$ 0.
- That leaves about 3.6 h of the 4 h timebox for the dev-L error round. R1 then allows at most
  one more logged 2 h round after the dev-L CV.

## Next (T5.1, part 2, after dev-L is frozen)

- Run the 5-fold CV / history grid on dev-L as in phase 1 (`scripts/analysis/tune_router.py`),
  then read the dev-L errors and edit the rules inside the remaining timebox. Log it as a second
  row in §B.
- The calibration in `config/experiments_l/e1_regex_l.yaml` is still the phase-1 map. Refit it
  on dev-L, with the `ece_cal < ece_raw` rule.
- Expect a large drop on dev-L: these rules never saw user phrasing.
- The known weak spots are the phase-1 misses on original tools: request_refund "extraviado"
  loses to pedidos TRACK, "Qual o prazo do meu reembolso?" goes to the help center, and there
  are ties in trocas (garantia, troca + "dá para").
- The `test_regex_rules_stub_loads` test name in `tests/test_experiments_l.py` is now a
  misnomer. The test still passes, and I left it untouched.
