"""Phase-1 hash lock (plan T0.1): phase 1 is read-only.

Every entry of the frozen phase-1 manifests must still reproduce its `config_hash` /
`prompt_hash`, the scorer of record must keep its hash, and the small-profile catalog (built
offline from `mcp_server/tools_list.json` + the SKILL.md resources, in server order) must keep
the `catalog_hash` the phase-1 rows carry. The manifest bytes are pinned too, so the frozen
values cannot be "fixed" by editing the manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from routing_study.catalog import Catalog, parse_skill
from routing_study.eval.manifest import load_manifest, load_run_settings
from routing_study.eval.runner import config_hash, run_prompt_hash
from routing_study.eval.scorers import scorer_hash

ROOT = Path(__file__).resolve().parents[1]
MCP_PKG = ROOT / "mcp_server" / "src" / "mcp_server"
# server order of the skill:// resources (mcp_server.server.SKILL_IDS): order shapes the hash
SKILL_IDS = ("pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes")

PHASE1_MANIFESTS = {
    "config/study_manifest.yaml": "9e4cdb262621",
    "config/study_manifest_explore.yaml": "93694326db6d",
}
SCORER_HASH = "e0eef1fb0073"
PROMPT_HASH = "c61ad0a7b7f8"
CATALOG_HASH = "128584617807"


def _runs() -> list[tuple[str, object]]:
    out = []
    for rel in PHASE1_MANIFESTS:
        for run in load_manifest(ROOT / rel).runs:
            out.append((f"{Path(rel).stem}:{run.name}", run))
    return out


@pytest.mark.parametrize("rel", sorted(PHASE1_MANIFESTS))
def test_phase1_manifest_bytes_are_frozen(rel: str) -> None:
    digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:12]
    assert digest == PHASE1_MANIFESTS[rel], f"{rel} was edited"


def test_every_phase1_entry_freezes_its_hashes() -> None:
    runs = _runs()
    assert len(runs) > 100
    missing = [k for k, r in runs if not (r.config_hash and r.prompt_hash)]  # type: ignore[attr-defined]
    assert not missing


@pytest.mark.parametrize(("key", "run"), _runs(), ids=[k for k, _ in _runs()])
def test_phase1_config_hash_reproduces(key: str, run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)  # regex rule paths are relative to the repo root
    assert config_hash(load_run_settings(run)) == run.config_hash, key


def test_phase1_prompt_hash_reproduces() -> None:
    assert run_prompt_hash() == PROMPT_HASH
    assert {r.prompt_hash for _, r in _runs()} == {PROMPT_HASH}  # type: ignore[attr-defined]


def test_phase1_scorer_hash_is_unchanged() -> None:
    assert scorer_hash() == SCORER_HASH


def test_phase1_small_catalog_hash_is_unchanged() -> None:
    tools = json.loads((ROOT / "mcp_server" / "tools_list.json").read_text(encoding="utf-8"))
    skills = {
        sid: parse_skill(sid, (MCP_PKG / "skills" / sid / "SKILL.md").read_text(encoding="utf-8"))[
            0
        ]
        for sid in SKILL_IDS
    }
    catalog = Catalog(
        url="offline",
        protocol_version="offline",
        instructions=(MCP_PKG / "instructions.md").read_text(encoding="utf-8"),
        tools=tools["tools"],
        skills=skills,
    )
    assert catalog.hash == CATALOG_HASH
