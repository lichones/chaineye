"""
ChainEye (체인아이) - inference module.

Backend-facing API. Import and call load() once at startup, then use
score_tx() and trace_tx().

    from app.ml import inference
    inference.load()
    inference.score_tx("230425980")
    inference.trace_tx("230425980", hops=2)
"""
import json
import os
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

# helper works both as a package import (app.ml.inference) and as a script
try:
    from . import _feature_store as _fs
except ImportError:  # run directly as `python app/ml/inference.py`
    import _feature_store as _fs

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "chaineye_model.pkl")
FEATURE_TABLE_PATH = os.path.join(HERE, "feature_table.parquet")
EDGES_PATH = os.path.join(HERE, "edges.parquet")

N_FEATURES = 165
FEATURE_COLS = [f"feat_{i}" for i in range(N_FEATURES)]
MAX_TRACE_NODES = 60

# module globals populated by load()
_MODEL = None
_FEAT_MATRIX = None     # read-only float32 memmap, shape (n_rows, 165)
_ROW_IDX = None         # dict: txId(int) -> row position(int)
_EDGES = None           # DataFrame with columns txId1, txId2 (int64)
_ADJ = None             # dict: node -> set(neighbors) (undirected, for tracing)
_EXPLAINER = None       # shap.TreeExplainer (built lazily on first explanation)
_EXPECTED_VALUE = 0.0   # SHAP base value for the illicit class
_DECISION_THRESHOLD = 0.5


def load() -> None:
    """Load model + feature table + graph into module globals. Idempotent."""
    global _MODEL, _FEAT_MATRIX, _ROW_IDX, _EDGES, _ADJ, _DECISION_THRESHOLD
    if _MODEL is not None:
        return

    _MODEL = joblib.load(MODEL_PATH)
    metrics_path = os.path.join(HERE, "metrics.json")
    try:
        with open(metrics_path, encoding="utf-8") as fh:
            _DECISION_THRESHOLD = float(json.load(fh).get("threshold", 0.5))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        _DECISION_THRESHOLD = 0.5

    # memory-mapped float32 feature matrix + txId->row index (near-zero RSS;
    # avoids the large transient allocation of pd.read_parquet on this file)
    _FEAT_MATRIX, _ROW_IDX = _fs.load_feature_matrix(FEATURE_TABLE_PATH)

    _EDGES = pd.read_parquet(EDGES_PATH)

    # build undirected adjacency for neighborhood tracing
    adj = {}
    src = _EDGES["txId1"].to_numpy()
    dst = _EDGES["txId2"].to_numpy()
    for a, b in zip(src, dst):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    _ADJ = adj

    # NOTE: the SHAP explainer is built lazily on first explanation
    # (see _ensure_explainer) so that trace-only workloads never pay for it.


def _ensure_explainer() -> None:
    """Build the SHAP TreeExplainer on first use. Cheap for LightGBM:
    feature_perturbation='tree_path_dependent' needs no background dataset."""
    global _EXPLAINER, _EXPECTED_VALUE
    if _EXPLAINER is not None:
        return
    import shap
    _EXPLAINER = shap.TreeExplainer(
        _MODEL, feature_perturbation="tree_path_dependent"
    )
    ev = _EXPLAINER.expected_value
    if isinstance(ev, (list, np.ndarray)):
        ev = np.ravel(ev)
        _EXPECTED_VALUE = float(ev[-1])  # illicit-class base value
    else:
        _EXPECTED_VALUE = float(ev)


def _to_int(tx_id):
    try:
        return int(tx_id)
    except (ValueError, TypeError):
        return None


def _feature_row(tx_int):
    """Return feature vector (1, N) for a txId, or None if not present."""
    if tx_int is None:
        return None
    i = _ROW_IDX.get(tx_int)
    if i is None:
        return None
    # copy the single row out of the memmap (float32, values identical to source)
    return np.array(_FEAT_MATRIX[i], dtype=np.float32).reshape(1, -1)


@lru_cache(maxsize=100000)
def _proba(tx_int):
    """Illicit probability for a node with features, else None. Cached."""
    x = _feature_row(tx_int)
    if x is None:
        return None
    return float(_MODEL.predict_proba(x)[:, 1][0])


def _risk_int(tx_int):
    p = _proba(tx_int)
    return int(round(p * 100)) if p is not None else None


def _decision_threshold_int() -> int:
    return int(round(_DECISION_THRESHOLD * 100))


def _is_model_positive(proba) -> bool:
    """Apply the decision rule to the unrounded model output.

    Integer risk scores and the integer threshold are display values only.
    Comparing those rounded values can disagree with ``score_tx`` near the
    threshold.
    """
    return proba is not None and proba >= _DECISION_THRESHOLD


def score_tx(tx_id: str) -> dict:
    """Score a single transaction and explain it with SHAP.

    Returns:
        {"txId": str, "riskScore": int(0-100)|None,
         "decisionThreshold": int(0-100),
         "label": "illicit"|"licit"|"unknown",
         "topFactors": [{"feature": str, "impact": float}, ...] up to 6}
    """
    if _MODEL is None:
        load()

    tx_int = _to_int(tx_id)
    x = _feature_row(tx_int)
    if x is None:
        # Absence from the closed benchmark is not evidence of licit behavior.
        # Explicitly abstain instead of returning a misleading zero-risk score.
        return {
            "txId": str(tx_id),
            "riskScore": None,
            "decisionThreshold": _decision_threshold_int(),
            "label": "unknown",
            "topFactors": [],
        }

    proba = float(_MODEL.predict_proba(x)[:, 1][0])
    risk = int(round(proba * 100))
    label = "illicit" if proba >= _DECISION_THRESHOLD else "licit"

    # per-prediction SHAP (explainer built lazily on first call)
    _ensure_explainer()
    sv = _EXPLAINER.shap_values(x)
    if isinstance(sv, list):        # binary -> list per class; take illicit
        sv = sv[-1]
    sv = np.asarray(sv)
    if sv.ndim == 3:                # (n, features, classes)
        sv = sv[:, :, -1]
    sv = sv.reshape(-1)             # (n_features,)

    order = np.argsort(np.abs(sv))[::-1][:6]
    top_factors = [
        {"feature": FEATURE_COLS[i], "impact": round(float(sv[i]), 4)}
        for i in order
    ]

    return {
        "txId": str(tx_id),
        "riskScore": risk,
        "decisionThreshold": _decision_threshold_int(),
        "label": label,
        "topFactors": top_factors,
    }


MAX_TRACE_PATHS = 8        # cap on model-positive candidate paths returned


def trace_tx(tx_id: str, hops: int = 2) -> dict:
    """Build the transaction neighborhood up to `hops` (both directions).

    Returns:
        {"nodes": [{"id": str, "risk": int(0-100), "focus": bool,
                    "modelPositive": bool}, ...],
         "edges": [{"source": str, "target": str}, ...],
         "candidatePaths": [[txId, txId, ...], ...],
         "decisionThreshold": int(0-100)}
    Total nodes capped at ~MAX_TRACE_NODES, keeping highest-risk neighbors.

    "modelPositive" is True when the raw model output meets the
    validation-selected threshold. ``risk`` is rounded for display only.
    "candidatePaths" holds up to MAX_TRACE_PATHS model-positive review candidates:
    directed walks (following edge direction) that start at the focus node and
    END at a model-positive node, with length between 2 and hops+1 nodes.
    A returned path is triage evidence, not proof of money laundering.
    """
    if _MODEL is None:
        load()

    focus = _to_int(tx_id)
    if focus is None or focus not in _ADJ:
        # unknown node in graph: return just the focus node if it has features
        proba = _proba(focus) if focus is not None else None
        risk = int(round(proba * 100)) if proba is not None else None
        return {
            "nodes": [{
                "id": str(tx_id),
                "risk": risk,
                "focus": True,
                "modelPositive": _is_model_positive(proba),
                "scored": risk is not None,
            }],
            "edges": [],
            "candidatePaths": [],
            "decisionThreshold": _decision_threshold_int(),
        }

    # BFS up to `hops` on the undirected adjacency
    visited = {focus}
    frontier = {focus}
    for _ in range(max(hops, 0)):
        nxt = set()
        for node in frontier:
            nxt |= _ADJ.get(node, set())
        nxt -= visited
        visited |= nxt
        frontier = nxt
        if not frontier:
            break

    # cap nodes: always keep focus, then highest-risk neighbors
    neighbors = [n for n in visited if n != focus]
    if len(neighbors) + 1 > MAX_TRACE_NODES:
        neighbors.sort(
            key=lambda n: (_risk_int(n) if _risk_int(n) is not None else -1),
            reverse=True,
        )
        neighbors = neighbors[: MAX_TRACE_NODES - 1]
    kept = set(neighbors) | {focus}

    # Raw probabilities drive decisions; rounded integers are display-only.
    proba_map = {focus: _proba(focus)}
    for n in neighbors:
        proba_map[n] = _proba(n)
    risk_map = {
        n: int(round(p * 100)) if p is not None else None
        for n, p in proba_map.items()
    }

    nodes = [{
        "id": str(focus),
        "risk": risk_map[focus],
        "focus": True,
        "modelPositive": _is_model_positive(proba_map[focus]),
        "scored": risk_map[focus] is not None,
    }]
    for n in neighbors:
        nodes.append({
            "id": str(n),
            "risk": risk_map[n],
            "focus": False,
            "modelPositive": _is_model_positive(proba_map[n]),
            "scored": risk_map[n] is not None,
        })

    # edges among kept nodes only (directed as in original edge list)
    mask = _EDGES["txId1"].isin(kept) & _EDGES["txId2"].isin(kept)
    sub = _EDGES[mask]
    edges = [{"source": str(a), "target": str(b)}
             for a, b in zip(sub["txId1"].to_numpy(), sub["txId2"].to_numpy())]

    # ------------------------------------------------------------------ #
    # Candidate paths: directed walks from the focus node that end at a
    # model-positive node, length 2..hops+1 nodes (1..hops edges).
    # ------------------------------------------------------------------ #
    dadj = {}  # directed adjacency among kept nodes
    for a, b in zip(sub["txId1"].to_numpy(), sub["txId2"].to_numpy()):
        dadj.setdefault(a, []).append(b)

    max_len_nodes = max(int(hops), 1) + 1
    paths = []
    seen_paths = set()

    def _walk(node, path):
        if len(paths) >= MAX_TRACE_PATHS:
            return
        if len(path) >= max_len_nodes:
            return
        for nxt in dadj.get(node, []):
            if nxt in path:          # avoid cycles within a single path
                continue
            new_path = path + [nxt]
            if _is_model_positive(proba_map.get(nxt)):
                key = tuple(new_path)
                if key not in seen_paths:
                    seen_paths.add(key)
                    paths.append([str(x) for x in new_path])
                    if len(paths) >= MAX_TRACE_PATHS:
                        return
            _walk(nxt, new_path)     # keep extending toward deeper high-risk nodes
            if len(paths) >= MAX_TRACE_PATHS:
                return

    _walk(focus, [focus])

    return {
        "nodes": nodes,
        "edges": edges,
        "candidatePaths": paths,
        "decisionThreshold": _decision_threshold_int(),
    }


if __name__ == "__main__":
    load()
    import json
    for t in ["230425980", "232022460"]:
        print(json.dumps(score_tx(t), ensure_ascii=False))
        tr = trace_tx(t, hops=2)
        print(f"trace {t}: {len(tr['nodes'])} nodes, {len(tr['edges'])} edges, "
              f"{len(tr['candidatePaths'])} candidate paths")
