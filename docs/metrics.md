# Metrics and statistics

Every published number is computed offline by `study rescore` (the shared scorer
`src/routing_study/eval/scorers.py`) and rendered by `study report` /
`scripts/analysis/study_report.py`. This page defines each metric and each test. The unit of
analysis is the case. Repetitions are averaged per case before any test or difference
interval.

## Error handling: intention to treat (ITT)

A row is an error row when one of these holds:
- a routing stage failed: no consulted step accepted, and a step raised (`usage.error`) or
  returned an unparseable reply (`usage.parse_fail`);
- the case crashed and left no turn record.

Error rows count as WRONG for every correctness score, and they stay in the denominator. This
holds everywhere: `tune_router.py` (evaluation and selection), `simulate`, cascade calibration,
`study report` and `study_report.py`. A failure is never scored as an abstention. Each run
reports its error rate as a separate column.

The intersection of the case ids that are error-free in every listed run is shown only as a
labelled SENSITIVITY table. Rates of a bad outcome (`args_invented`) and `entity_grounded`
are not applicable to an error row.

## Routing scores (routing-only and e2e)

| score | definition |
|---|---|
| `skill_correct` | the chosen skill is in `acceptable_skills`. |
| `tool_correct` | routing-only: the router's top-1 tool. e2e: the executor's first business call, or the tool of a credited clarification. |
| `joint_correct` | skill and tool are both correct. This is the primary routing metric. |
| `joint_first_label` | joint against the FIRST listed skill and tool only. Strict multi-label sensitivity analysis (methodology M4). |
| `abstain_correct` | escalation or abstention accuracy. Abstaining is correct iff the gold allows it; acting is correct iff the gold does not expect abstention. |

Out-of-scope rule: if the gold is `__abstain__`, escalating as the only action counts as
abstaining. `__global__` + `escalate_to_human` is scored the same way in every consumer.

## e2e scores

`e2e_success`: the skill is correct, and one of these holds:
- the first business call used an acceptable tool, had valid args, and finished;
- a later acceptable call completed with valid args (and no earlier call completed an action).

A call "finished" when it completed, when it was a NOT_ELIGIBLE refusal on the order the user
meant, or when it led to a correct "which order?" clarification.

The success is split into three disjoint parts that sum to `e2e_success` (F6):

| part | meaning |
|---|---|
| `first_call_success` | the first business call did it. |
| `clarification_credited` | a clarifying question was credited. Either no call was made and the reply asked for what the next step needed, or the tool answered "which order?" and the reply offered the options. |
| `recovered_credited` | a later acceptable call reached the goal after a wrong or failed first attempt. |

Other e2e scores:

| score | definition |
|---|---|
| `e2e_strict` | `e2e_success`, and the call that decided the outcome invented no required fact. |
| `args_valid` | the args are schema-valid, the gold args match, and any `order_id` the call passed is one the user wrote (when the user wrote any). The last check applies even when the gold omits `order_id` (F5). |
| `args_invented` | a required free-text argument is supported by neither the gold args nor the user's words (at least 50% token overlap; an ISO date needs a date hint). |
| `entity_grounded` | every id, amount and date in the final answer appears in the evidence: the profile, the tool results or the user turns. It checks entities only. Rows scored before F6 carry the old name `grounded`, which the report reads as an alias. |

### Clarification heuristics (F5)

A "which order?" clarification is credited only when all of these hold:
- the user named no order and the customer has at least two;
- the reply contains a question sentence (a segment ending in `?`);
- the reply offers at least two order ids;
- the reply does not claim that an action was already done, such as "pronto", "sucesso",
  "já cancelei" or "foi cancelado".

A missing-field clarification is credited only when both hold:
- the field is missing: the gold args do not cover it, an enum value is not in the user
  words, and the field's lexical cue is absent from the user turns (the cues are listed below);
- a question sentence of the reply names the field. The keyword must start a word inside a
  segment ending in `?`, so a stray keyword elsewhere does not count.

Cues that mark a free-text field as already given (accent-free, casefolded user turns):

| field | cue |
|---|---|
| `defect_description` | defeito, quebr-, parou, não liga/funciona/carrega, rasg-, manch-, trinc-, … |
| `reason` | porque, pois, motivo, por causa, desisti, arrepend-, não quero/gostei/serviu, errad-, … |
| `new_variant` | tamanho, número, cor, modelo, voltagem, PP/P/M/G/GG, a 2-digit size, a colour name |
| address fields | rua/R., avenida/av, alameda, travessa, rodovia, CEP or a `00000-000` postal code |
| `new_date` | a date hint: `dd/mm`, ISO, "dia N", weekday, month, amanhã, hoje, … |

Native (E0) skill: this is the first skill the agent loads, or the skill of the first
skill-bound tool it calls. A global tool called before that does not decide the skill; the
skill is `__global__` only when no skill was ever loaded.

These heuristics are lexical and deliberately conservative. The planned human audit of 60 e2e
transcripts (methodology M5) reports scorer-vs-human agreement.

## Secondary metrics (`eval/metrics.py`)

| metric | definition |
|---|---|
| recall@1/2/3 | an acceptable tool is in the router's top-k tool ranking (its choice first, then the recorded candidates), with a correct skill. Out-of-scope golds accept `escalate_to_human`. Error rows count 0. |
| abstention precision / recall | abstained = a routed abstention, a host abstention or escalation as the only action. Precision is the share of abstentions whose gold allows abstaining. Recall is the share of abstaining among golds that expect it (only abstention or escalation acceptable). The LLM routers run with `allow_abstain: false`; regex and BM25 can abstain. |
| risk-coverage, AURC, coverage@5% risk | rows ranked by confidence = min(skill, tool) of the recorded decision. Error rows have confidence 0 and count wrong. Ties enter together. AURC is the mean risk over coverages 1/n..1. Coverage@5% is the largest coverage whose risk is ≤ 5%. |
| Brier, ECE | per level, over the decisions made (abstentions and error rows out): skill confidence vs `skill_correct`, and tool confidence vs `tool_correct` on rows with a correct skill. ECE uses 10 adaptive (equal-mass) bins, and the report prints the bin counts. |
| trivial baselines | scored by the shared scorer on the cases of the listed runs. `always_escalate` = `__global__` + `escalate_to_human`. `majority` = the most common first-label skill on dev, then the most common tool within it. `uniform` = the expected score of a uniformly random choice over each stage's options, with globals offered at every tool stage as in the host. |

## Statistics (`eval/stats.py`)

- **Marginal CI**: a cluster bootstrap over case ids. All reps of a case move together. It
  uses 10,000 resamples, seed 20260930, and percentile intervals.
- **Paired Δ CI** (`paired_delta`): per-case means over reps, then Δ = mean(run − reference)
  over the shared cases. Case ids are resampled 10k times with seed 20260930.
- **Case-level tests**:
  - exact McNemar on per-case majorities (mean > 0.5 is correct; a tie counts as not
    correct);
  - a sign-flip permutation test of the mean per-case difference, exact up to 20 non-zero
    cases, else Monte Carlo (10k, seeded).
- **Contrast kinds**:

  | kind | hypothesis | test |
  |---|---|---|
  | `two_sided` | Δ ≠ 0 | sign-flip, two-sided |
  | `greater` | Δ > 0 | sign-flip, one-sided |
  | `non_inferiority` (margin m) | Δ > −m | sign-flip on Δ + m, one-sided. Verdict: lower bound of the two-sided 95% paired CI (= one-sided 97.5%) > −m |
  | `equivalence` (TOST, margin m) | \|Δ\| < m | p = max of the two one-sided shifted sign-flip tests. Verdict by CI inclusion of the 90% paired CI: inside ±m → equivalent; entirely outside → not equivalent; else inconclusive |

- **Holm**: Holm step-down within each named family (e.g. H1–H3, S1, S2). Adjusted p < 0.05
  means reject.
- The rep-level McNemar (`stats.mcnemar` on (case, rep) pairs) is anti-conservative. It is kept
  only for audit.

The contrasts and families are explicit, never a hard-coded reference:
- `study report --contrast run:reference[:family[:kind[:margin]]]`, or the `contrasts:` block of
  the run manifest;
- `--reference X` = every run vs X, two-sided, in one family.

## Cost columns

| column | definition |
|---|---|
| `$study/case` | the ORIGINAL cost of every consulted decision (cache-independent). |
| `$paid total` | what the run was billed: consulted and shadow routing (`shadow_billed_usd`; it equals the consulted billing outside shadow mode), plus the executor. Cache hits are free. |
| `$list/case` | list price without prompt-cache discount. It needs `rescore --prices`. It uses each step's recorded tokens, and the executor's tokens in e2e. A model without a list price (OpenRouter pricing −1, e.g. the Jev meta-router) shows `n/a`. |
