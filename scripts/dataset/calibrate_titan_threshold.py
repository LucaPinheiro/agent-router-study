"""Phase 2: map the phase-1 semantic-dedupe threshold (qwen3-embedding cosine 0.9) onto Bedrock
Titan v2, which phase 2 uses because it runs no local model. Pairs: every test-v2 case against
its nearest dev/test-v1 case and the within-test-v2 nearest pairs. qwen vectors come from the
phase-1 disk cache (no model call); Titan vectors are embedded on Bedrock (cents). The Titan
threshold is the cosine that flags the same SHARE of top pairs as qwen >= 0.9 (rank matching),
reported with the isotonic/linear fits for comparison. Writes data/audit/titan_threshold.json."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from common import Case  # noqa: E402
from overlap import PHASE2_EMBED_MODEL, Embedder, semantic_text  # noqa: E402

QWEN_CACHE = Path.home() / ".cache" / "routing_study" / "embed_qwen3-embedding_8b-q8_0.npz"
QWEN_THRESHOLD = 0.9


def main() -> None:
    def load(name: str) -> list[Case]:
        path = ROOT / "data" / f"dataset_{name}.jsonl"
        return [Case.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]

    splits = {s: load(s) for s in ("dev", "test", "test_v2")}
    texts = {s: [semantic_text(c) for c in cs] for s, cs in splits.items()}
    with np.load(QWEN_CACHE) as z:
        qcache = {k: z[k] for k in z.files}

    def qvec(t: str) -> np.ndarray | None:
        return qcache.get(hashlib.sha256(t.encode()).hexdigest())

    pool = [t for s in ("dev", "test") for t in texts[s]] + texts["test_v2"]
    pool = list(dict.fromkeys(pool))
    have = [t for t in pool if qvec(t) is not None]
    print(f"{len(have)}/{len(pool)} texts have a cached qwen vector")
    Q = np.stack([qvec(t) for t in have]).astype(np.float32)
    Q /= np.linalg.norm(Q, axis=1, keepdims=True)
    T = Embedder(PHASE2_EMBED_MODEL, backend="bedrock")(have)
    sq, st = Q @ Q.T, T @ T.T
    np.fill_diagonal(sq, -1)
    np.fill_diagonal(st, -1)
    iu = np.triu_indices(len(have), 1)
    q, t = sq[iu], st[iu]
    # rank matching on the upper tail: same number of pairs flagged
    k = int((q >= QWEN_THRESHOLD).sum())
    t_rank = float(np.sort(t)[::-1][k - 1]) if k else float("nan")
    # nearest-neighbour view (what the dedupe actually checks: max cosine per text)
    qn, tn = sq.max(1), st.max(1)
    kn = int((qn >= QWEN_THRESHOLD).sum())
    t_nn = float(np.sort(tn)[::-1][kn - 1]) if kn else float("nan")
    slope, icpt = (
        np.polyfit(q[q > 0.6], t[q > 0.6], 1) if (q > 0.6).sum() > 10 else (np.nan, np.nan)
    )
    out = {
        "qwen_threshold": QWEN_THRESHOLD,
        "n_texts": len(have),
        "pairs": int(len(q)),
        "pairs_qwen_ge_thr": k,
        "titan_threshold_pair_rank": round(t_rank, 4),
        "texts_qwen_nn_ge_thr": kn,
        "titan_threshold_nn_rank": round(t_nn, 4),
        "linear_fit_titan_at_qwen_thr": round(float(slope * QWEN_THRESHOLD + icpt), 4),
        "spearman_pairs_q_gt_0.6": round(
            float(
                np.corrcoef(np.argsort(np.argsort(q[q > 0.6])), np.argsort(np.argsort(t[q > 0.6])))[
                    0, 1
                ]
            ),
            3,
        ),
        "titan_model": PHASE2_EMBED_MODEL,
    }
    out["titan_threshold"] = round(min(v for v in (t_rank, t_nn) if v == v), 4)
    (ROOT / "data" / "audit").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "audit" / "titan_threshold.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
