# Handoff: phase 2, dev-L dataset (T4.1, T4.2)

Branch `feat/phase2-cloud-and-large-catalog`. The code, data and docs are in one commit (see
`git log`).

## What exists

- **`scripts/dataset/common_l.py`.** The large-catalog case schema:
  - `CaseL` / `ExpectedL`, validated against the 62 tools of `tools_list_large.json`;
  - `source: synthetic_l`;
  - `ORIG_TOOLS` (the 18 phase-1 tools) and `NEW_TOOLS` (44).

  `common.py` is untouched.
- **`scripts/dataset/generate_l.py`.** A parametrized copy of `generate_v2.py` (whose bytes are
  unchanged). It takes `--split dev_l|test_l`. The seed is pre-declared per split, and any other
  seed is refused.
  - Quotas follow plan §2. The per-tool remainders go to the originals first (≥ 30% orig share).
    ambiguo is 3/4 over G1–G12 and 1/4 over the 8 phase-1 groups.
  - Entity slots come from the measured `compatible_tools` in `MOCK_DB_NOTES_LARGE.md`, plus
    the phase-1 order archetypes. Coupons, promotions and unredeemed gift cards are shared.
  - An item is rejected when it cites an id it was not offered, or a customer code `C0xx`.
  - Dedupe/leakage uses lexical checks plus Titan (`PHASE2_SEMANTIC_THRESHOLD = 0.71`). The
    references are the 849 phase-1 cases, plus dev-L when generating test-L, and the large
    catalog units; the leak rule runs on both catalogs.
  - `--pilot N` writes to `data/audit/pilot_<split>.jsonl` only.
  - `--resume` replays `generation_<split>_raw.jsonl`.
  - `--overlap-report` writes `data/audit/overlap_report_<split>.json`.
- **`scripts/dataset/audit_l.py`.** A parametrized copy of `audit.py` (whose bytes are
  unchanged).
  - Bedrock auditors: A `openai.gpt-oss-120b-1:0`, B `deepseek.v3.2`.
  - The schema is stated in the prompt and each verdict is validated. The adjudication rule is
    the same.
  - Outputs: `verdicts_<split>_{A,B}.jsonl`, `adjudication_<split>.jsonl`, `summary_l.json`
    (keyed by split) and `review_<split>.html`.
- **`scripts/dataset/overlap.py`** (additive): `CATALOG_FILES_LARGE`, `leak_units_large()` and
  `leak_hit_units()`.
- **`tests/test_dataset_l.py`** checks:
  - quotas, ids and source;
  - every gold tool (and every pre-audit original) is in the large catalog;
  - coverage of all 62 tools and the ≥ 30% orig share;
  - `routing_study.eval.runner.load_cases("dev_l")`;
  - 0 lexical leakage against the large catalog;
  - the frozen sha in `docs/dataset-card.md`.

  `tests/test_leakage.py` also picks up `dataset_dev_l.jsonl` automatically, against the small
  catalog.
- **CLI.** The help text of `study run --split` now lists `test_v2 | dev_l | test_l`. The loader
  needed no change, since split = file name.

## dev-L numbers

- 150 cases: direto 45, parafrase 37, ambiguo 30 (22 G-groups + 8 phase-1), multiturno 15,
  fora_escopo 15, adversarial 8.
- Single-label: 97 over all 62 tools, 30 of them on the originals (30.9%). The orig subset has
  41 cases.
- Mock satisfiability: 98.0%. The 3 conflicts are all adversarial.
- Overlap report: 0 hits. Maximum cosines: 0.704 vs cases, 0.665 vs catalog, 0.696 per turn.
- Audit:
  - κ on gold acceptance 0.382 (raw 0.847); κ on the first tool 0.849 (raw 0.853);
  - out of scope κ 0.934; escalation κ 0.713;
  - decisions keep / fixed / flagged = 102 / 8 / 40. ambiguo has 15 of the 40 flags.
- sha256 of `data/dataset_dev_l.jsonl`:
  `b02b3722f5c4e434dd97a4c6a4811ac18a1fd1945784a6375639acd0b376e238` (frozen in the card).
- Spend (Bedrock): **US$ 0.99**. Pilot 0.033, generation 0.529, audit A 0.083, audit B 0.344.

## Caveats for later tasks

- Prompt changes made during the run (both documented in the card):
  - the rule against customer codes, added after the pilot;
  - one "must contain the attack" sentence for injection/abuse, plus "cite other customers by
    name, not C0xx", added after round 6. Rounds 1–6 were replayed from the raw file.

  `generation_meta_dev_l.json` `code_sha256` is the generator **as of the last resume**.
  `--overlap-report` was added afterwards and does not affect generation.
- **test-L (T4.3, after the T5 freeze).** Run:

  ```
  BUDGET__AWS_USD_CAP=<mark+cap> uv run python scripts/dataset/generate_l.py --split test_l --seed 20261009
  uv run python scripts/dataset/audit_l.py run --split test_l
  uv run python scripts/dataset/audit_l.py adjudicate --split test_l
  uv run python scripts/dataset/generate_l.py --split test_l --overlap-report
  ```

  Then add `test_l` to `SPLITS` in `tests/test_dataset_l.py` and a freeze row to the card.
  Expected numbers: 195 single-label cases, 59 on the originals by construction (30.3%). The
  orig subset needs ≥ 60; the phase-1 ambiguous groups add about 15.
- Multi-turn items sometimes contain two consecutive user turns. The schema allows it, as in
  phase 1. The auditors flagged the doubtful multiturno labels.
- `apply-decisions` (human review) is not ported to `audit_l.py`. Doing it would change the dev-L
  sha.
