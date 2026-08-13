"""
ChainEye (체인아이) - inference module.

Backend-facing API. Import and call load() once at startup, then use
score_tx() and trace_tx().

    from app.ml import inference
    inference.load()
    inference.score_tx("230425980")
    inference.trace_tx("230425980", hops=2)
"""
import os
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "chaineye_model.pkl")
FEATURE_TABLE_PATH = os.path.join(HERE, "feature_table.parquet")
EDGES_PATH = os.path.join(HERE, "edges.parquet")

N_FEATURES = 165
FEATURE_COLS = [f"feat_{i}" for i in range(N_FEATURES)]
MAX_TRACE_NODES = 60

# module globals populated by load()
_MODEL = None
_FEATURES = None        # DataFrame indexed by txId (int64), columns = FEATURE_COLS
_EDGES = None           # DataFrame with columns txId1, txId2 (int64)
_ADJ = None             # dict: node -> set(neighbors) (undirected, for tracing)
_EXPLAINER = None       # shap.TreeExplainer
_EXPECTED_VALUE = 0.0   # SHAP base value for the illicit class


def load() -> None:
    """Load model + feature table + graph into module globals. Idempotent."""
    global _MODEL, _FEATURES, _EDGES, _ADJ, _EXPLAINER, _EXPECTED_VALUE
    if _MODEL is not None:
        return

    _MODEL = joblib.load(MODEL_PATH)

    ft = pd.read_parquet(FEATURE_TABLE_PATH)
    # ensure only the feature columns, indexed by txId, drop time_step if present
    keep = [c for c in FEATURE_COLS if c in ft.columns]
    _FEATURES = ft[keep]

    _EDGES = pd.read_parquet(EDGES_PATH)

    # build undirected adjacency for neighborhood tracing
    adj = {}
    src = _EDGES["txId1"].to_numpy()
    dst = _EDGES["txId2"].to_numpy()
    for a, b in zip(src, dst):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    _ADJ = adj

    # SHAP explainer for per-prediction explanations
    import shap
    _EXPLAINER = shap.TreeExplainer(_MODEL)
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
    if tx_int is None or tx_int not in _FEATURES.index:
        return None
    row = _FEATURES.loc[tx_int]
    if isinstance(row, pd.DataFrame):  # duplicate index guard
        row = row.iloc[0]
    return row.to_numpy(dtype=np.float32).reshape(1, -1)


@lru_cache(maxsize=100000)
def _proba(tx_int):
    """Illicit probability for a node with features, else None. Cached."""
    x = _feature_row(tx_int)
    if x is None:
        return None
    return float(_MODEL.predict_proba(x)[:, 1][0])


def _risk_int(tx_int):
    p = _proba(tx_int)
    return int(round(p * 100)) if p is not None else 0


def score_tx(tx_id: str) -> dict:
    """Score a single transaction and explain it with SHAP.

    Returns:
        {"txId": str, "riskScore": int(0-100), "label": "illicit"|"licit",
         "topFactors": [{"feature": str, "impact": float}, ...] up to 6}
    """
    if _MODEL is None:
        load()

    tx_int = _to_int(tx_id)
    x = _feature_row(tx_int)
    if x is None:
        # not found (or no features): safe default, do not raise
        return {"txId": str(tx_id), "riskScore": 0, "label": "licit", "topFactors": []}

    proba = float(_MODEL.predict_proba(x)[:, 1][0])
    risk = int(round(proba * 100))
    label = "illicit" if proba >= 0.5 else "licit"

    # per-prediction SHAP
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
        "label": label,
        "topFactors": top_factors,
    }


HIGH_RISK_THRESHOLD = 70   # risk >= this is considered high-risk / illicit
MAX_TRACE_PATHS = 8        # cap on suspicious laundering paths returned


def trace_tx(tx_id: str, hops: int = 2) -> dict:
    """Build the transaction neighborhood up to `hops` (both directions).

    Returns:
        {"nodes": [{"id": str, "risk": int(0-100), "focus": bool,
                    "illicit": bool}, ...],
         "edges": [{"source": str, "target": str}, ...],
         "paths": [[txId, txId, ...], ...]}
    Total nodes capped at ~MAX_TRACE_NODES, keeping highest-risk neighbors.

    "illicit" is True when risk >= HIGH_RISK_THRESHOLD (70).
    "paths" holds up to MAX_TRACE_PATHS suspicious money-laundering chains:
    directed walks (following edge direction) that start at the focus node and
    END at a high-risk (illicit) node, with length between 2 and hops+1 nodes.
    """
    if _MODEL is None:
        load()

    focus = _to_int(tx_id)
    if focus is None or focus not in _ADJ:
        # unknown node in graph: return just the focus node if it has features
        risk = _risk_int(focus) if focus is not None else 0
        return {
            "nodes": [{
                "id": str(tx_id),
                "risk": risk,
                "focus": True,
                "illicit": risk >= HIGH_RISK_THRESHOLD,
            }],
            "edges": [],
            "paths": [],
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
        neighbors.sort(key=lambda n: _risk_int(n), reverse=True)
        neighbors = neighbors[: MAX_TRACE_NODES - 1]
    kept = set(neighbors) | {focus}

    # risk lookup for every kept node (computed once, reused below)
    risk_map = {focus: _risk_int(focus)}
    for n in neighbors:
        risk_map[n] = _risk_int(n)

    nodes = [{
        "id": str(focus),
        "risk": risk_map[focus],
        "focus": True,
        "illicit": risk_map[focus] >= HIGH_RISK_THRESHOLD,
    }]
    for n in neighbors:
        nodes.append({
            "id": str(n),
            "risk": risk_map[n],
            "focus": False,
            "illicit": risk_map[n] >= HIGH_RISK_THRESHOLD,
        })

    # edges among kept nodes only (directed as in original edge list)
    mask = _EDGES["txId1"].isin(kept) & _EDGES["txId2"].isin(kept)
    sub = _EDGES[mask]
    edges = [{"source": str(a), "target": str(b)}
             for a, b in zip(sub["txId1"].to_numpy(), sub["txId2"].to_numpy())]

    # ------------------------------------------------------------------ #
    # Suspicious laundering paths: directed walks from the focus node that
    # end at a high-risk node, length 2..hops+1 nodes (1..hops edges).
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
            if risk_map.get(nxt, 0) >= HIGH_RISK_THRESHOLD:
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

    return {"nodes": nodes, "edges": edges, "paths": paths}


if __name__ == "__main__":
    load()
    import json
    for t in ["230425980", "232022460"]:
        print(json.dumps(score_tx(t), ensure_ascii=False))
        tr = trace_tx(t, hops=2)
        print(f"trace {t}: {len(tr['nodes'])} nodes, {len(tr['edges'])} edges, "
              f"{len(tr['paths'])} paths")
