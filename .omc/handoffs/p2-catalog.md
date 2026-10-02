# Handoff: phase 2, large catalog (T3.1, T3.2, T3.3)

Branch `feat/phase2-cloud-and-large-catalog`. Commits:
- d92591a (catalog + profile switch + tests);
- 3f12594 (compose service on :8766);
- 12e518e (host wiring + experiments_l + smoke).

## What exists

- **Profile switch.** `CATALOG_PROFILE=small|large` (default small) is read by
  `mcp_server.server.profile_from_env()`. `build_server(profile)` builds either profile, and
  `profile_tools(profile)` returns its tools.
  - The small path is unchanged: `tools_list.json` is byte-identical and the catalog hash is
    `128584617807`. The other worker's `tests/test_phase1_hashes.py` covers this, and
    `tests/test_catalog_large.py` does too (in process, via `build_server("small")`).
  - core.py has one additive change: `catalog_tool(..., registry=None)`.
- **Large catalog: 62 tools, 10 skills, 5 globals.**
  - The new tools are in `mcp_server/src/mcp_server/tools_large/*.py` and register into
    `large.data.REGISTRY_LARGE` (44 tools).
  - The overlay of the 18 originals is `large/overrides.py`. It copies each tool, appends DON'T
    USE FOR pointers, fixes escalate_to_human's out-of-scope list and invoice example, and
    rebinds search_help_center to `policies_large.json`.
  - Other files: `large/models.py` (output models) and `large/probes.py` (canonical calls per
    entity).
  - Content: `skills_large/<7 new>/SKILL.md` (the 3 originals are served verbatim from
    `skills/`), `instructions_large.md` and `policies_large.json` (20 help articles).
  - Lint: `lint_tools_list.py --strict mcp_server/tools_list_large.json` reports 62 tools, 0
    errors, 0 warnings.
- **Mock DB.** `scripts/generate_mock_db_large.py` writes `mock_db_large.json` and
  `MOCK_DB_NOTES_LARGE.md`.
  - The DB is the small DB embedded unchanged (asserted at import) plus sellers, marketplace
    orders, service orders, extended warranties, subscriptions, invoices, billing profiles,
    coupons, promotions, prices, gift cards, loyalty, cashback, store cards and protocols.
  - The generator is deterministic; byte-identical re-runs were checked.
  - The notes list **measured** `compatible_tools` per entity: every tool is called in process.
    Every new tool completes on at least 2 entities.
- **Docs.** `docs/catalog-large.md` has the §1 tables, G1–G12 with the location of each rule,
  the design rules and the review checklist.
- **Service.** `infra/docker-compose.yml` has `mcp-server-large`: the same image with
  CATALOG_PROFILE=large, on :8766, healthcheck `/readyz` (62 tools). It is up and healthy.
  - `make health` checks both services.
  - `scripts/run_mcp_server.sh [small|large]` runs either profile locally.
  - Bring it up alone with: `docker compose -f infra/docker-compose.yml --env-file .env
    --profile app up -d --build --wait --no-deps mcp-server-large`. I did not restart the small
    container.
- **Host.**
  - `config/experiments_l/*_l.yaml` (15 configs: e0, e1, e2, e3, e4, e5 for the shadow only,
    e6, e6m, e6n, e7, e8, e9, e10, e11, e12) set `mcp_url :8766` and
    `config/regex_rules_l.yaml`.
  - There is **no local model** in them. Embedding and classifier run on Bedrock, with Cohere
    v4 as the default. `strategies.embedding.model` is the single switch to Titan.
  - Thresholds and calibration are **provisional** (phase-1 / Part-A values) until T5.
  - `config/regex_rules_l.yaml` is a STUB: a copy of the phase-1 rules, so the new skills have
    no rules and regex abstains on them.
- **Settings fix (important).** Before it, YAML had the lowest precedence, so `.env`
  `MCP_URL=...8765` silently overrode a config's `mcp_url`. `load_settings` now pins a config's
  `mcp_url` when the YAML sets it. An explicit kwarg still wins. Phase-1 configs set none, so
  their behaviour and hashes are unchanged.
- **Manifest guard.** `ManifestRun.catalog_hash` is optional. When set,
  `version_problems` fetches the catalog at the config's `mcp_url` and asserts the hash
  (`current_catalog_hash`, which tests can monkeypatch).
  - The large catalog hash today is **`bc7cd75fce87`**. It is not frozen: it changes if any
    large content changes before T6.1.

## Verification (fresh)

- `uv run ruff check .`: all checks passed. `ruff format --check .`: 250 files formatted.
- `uv run pytest -q -m "not integration"`: **927 passed**, 8 deselected.
- The MCP tests run on both profiles: the `client` fixture is parametrized over `PROFILES`.
  `test_mcp_tools_large.py` adds 90 tests, including:
  - 63 business-error cases;
  - every new tool completing on at least one entity;
  - G1–G12 rules (12/12);
  - the overlay only appending pointers;
  - leakage against the dev, test and test_v2 user turns.
- The consistency test (no dead-end `suggested_tool`; reads never suggest an irreversible
  action) also covers the 44 new tools in the large profile.
- The redis keys are `mcp:catalog:http://localhost:8766/mcp:2026-07-28` (62 tools, 10 skills)
  and `...8765...` (18 tools, 3 skills): one per URL, with no cross-profile hit.

## E2E smoke (scripts/smoke_large.py → results/smoke_l/)

- E0-L, 5/5 cases: `load_skill` picked the correct new skill each time (the enum has the 10
  skills; checked on the live :8766 catalog), then the target tool completed.
- E9-L, 2/2 cases with Jev: regex abstained (stub), then Jev routed skill and tool correctly,
  and the tool completed.
- Cost: US$ 0.1827 billed, of which Bedrock 0.1795 and OpenRouter (Jev) 0.0032. That is **above
  the US$ 0.15 smoke cap**. E0-L cost ~US$ 0.029 per turn, about 3× the phase-1 per-turn
  estimate, because of prompt-cache writes (~12.7k tokens) on a 62-tool / 10-skill prompt. This
  is relevant to risk R8 and to the B3/B8 estimates.
- **Trace ids: none.** The first version of the script did not export `.env` into the process
  (the Langfuse client reads os.environ), so no traces were exported. The script is fixed
  (`load_dotenv` + tracing init, as the CLI does), but I did not re-run it, to stay near the
  cap. A one-case traced re-run of E0-L costs about US$ 0.04.

## Notes for the next tasks

- T4.1: the out-of-scope topics of phase 1 that are now IN scope in the large profile are
  prices/coupons, invoices and registration changes. Large out-of-scope topics are jobs,
  launches/stock, password/login and wholesale (`policies_large.json`).
- T4.1: build slots from `MOCK_DB_NOTES_LARGE.md` (`report_coupon_not_applied(code=...)` names
  the code to use). `mcp_server.large.probes.entity_probes(db)` gives canonical arguments.
- T5.1: regex rules for the 7 new skills and 44 tools go into `config/regex_rules_l.yaml`.
- T6.1: freeze the large `catalog_hash` in `config/study_manifest_l.yaml` entries.
