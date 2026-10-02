"""Build docs/results/phase2-dev-l/tuned_blocks.yaml from the dev-L tune_router summaries.
A map is written only when its cross-fitted ECE < raw ECE (prereg-v2 §5)."""
import json, sys, yaml
from pathlib import Path
R = Path("results/phase2l")

def maps(summary, round_to=6):
    d = json.loads((R / summary).read_text())
    out, why = {}, {}
    for lv, st in d["calibration_stats"].items():
        name = d["calibrator"][lv]
        cal_ece = st[f"ece_{name}"]
        keep = cal_ece < st["ece_raw"]
        why[lv] = f"{name} ECE {st['ece_raw']:.3f}->{cal_ece:.3f} {'written' if keep else 'NOT written'}"
        if keep and lv in (d["calibration"] or {}):
            c = d["calibration"][lv]
            out[lv] = {"x": [round(v, round_to) for v in c["x"]], "y": [round(v, round_to) for v in c["y"]]}
    return out or None, why

log = {}
regex_cal, log["regex"] = maps("regex_r1.json")
emb_cal, log["embedding"] = maps("emb_titan_T0.02.json")
clf_cal, log["classifier"] = maps("probe_titan_refine.json")
HAVE_BM25 = (R / "bm25_grid2.json").exists()
bm = json.loads((R / "bm25_grid2.json").read_text()) if HAVE_BM25 else {"best_point": {}}
bm_cal, log["bm25"] = maps("bm25_grid2.json") if HAVE_BM25 else (None, "pending")
bm25 = {"index": "utterance", "aggregate": "topk_sum", "analyzer": "char", "shots": True, "quotes": False, "variant": "okapi"}
bm25.update({k.split(".")[-1]: v for k, v in bm["best_point"].items()})
blocks = {
  "regex": {"rules_path": "config/regex_rules_l.yaml", "history_turns": 2, "history_weight": 0.3, "calibration": regex_cal},
  "bm25": bm25 | {"calibration": bm_cal},
  "embedding": {"provider": "bedrock", "model": "amazon.titan-embed-text-v2:0", "region": "sa-east-1",
                "similarity": "centroid", "top_k": 3, "confidence": "softmax", "softmax_temperature": 0.02,
                "history_turns": 1, "shots": True, "query_instruction": None, "calibration": emb_cal},
  "classifier": {"model": "probe", "c": 1000, "shots": True, "quotes": False, "description": True,
                 "probe_instruction": False, "history_turns": 2, "history_weight": 0.3, "calibration": clf_cal},
}
if not HAVE_BM25:
    blocks.pop("bm25")
for k in list(blocks):
    if blocks[k].get("calibration") is None:
        blocks[k].pop("calibration")
per = {}
for stem, f in [("e6_llm_haiku_l", "e6_llm_haiku_l_summary.json"), ("e6m_llm_ministral_l", "e6m_llm_ministral_l_summary.json"),
                ("e6n_llm_nemotron_l", "e6n_llm_nemotron_l_summary.json")]:
    cal, log[stem] = maps(f)
    per[stem] = {"strategies": {"llm": {"calibration": cal}}}
jev_cal, log["jev"] = maps("e4_jev_l_summary.json")
son_cal, log["sonnet"] = maps("e5_llm_sonnet_l_summary.json")
for stem in ["e1_regex_l", "e2_bm25_l", "e3_embedding_l", "e4_jev_l", "e5_llm_sonnet_l", "e7_regex_jev_l",
             "e8_regex_llm_l", "e9_regex_jev_llm_l", "e10_classifier_l", "e11_hybrid_l", "e12_hybrid_jev_llm_l"]:
    per[stem] = {"strategies": {"llm": {"calibration": son_cal}}}
spec = {"strategies": blocks, "per_config": per, "jev_calibration": jev_cal, "decisions": log}
if len(sys.argv) > 1:  # extra blocks (hybrid) and per-config merges (cascade thresholds)
    extra = yaml.safe_load(Path(sys.argv[1]).read_text())
    spec["strategies"].update(extra.get("strategies") or {})
    for stem, patch in (extra.get("per_config") or {}).items():
        spec["per_config"].setdefault(stem, {}).setdefault("strategies", {})
        for k, v in patch.items():
            if k == "strategies":
                spec["per_config"][stem]["strategies"].update(v)
            else:
                spec["per_config"][stem][k] = v
Path("docs/results/phase2-dev-l/tuned_blocks.yaml").write_text(
    "# dev-L tuned strategy blocks (T5.1-T5.3); built by results/phase2l/make_blocks.py from the\n"
    "# tune_router summaries; applied with scripts/analysis/apply_tuned_l.py.\n"
    + yaml.safe_dump(spec, sort_keys=False, default_flow_style=None, width=110))
print(json.dumps(log, indent=1))
