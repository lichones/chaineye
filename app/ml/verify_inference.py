"""Smoke test for inference.py: verifies load/score_tx/trace_tx shapes."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inference

inference.load()
print("load() OK")

# Decisions use raw probabilities, never independently rounded display values.
assert inference._is_model_positive(inference._DECISION_THRESHOLD)
assert not inference._is_model_positive(inference._DECISION_THRESHOLD - 1e-12)

SAMPLES = {
    "illicit": "68995268",
    "licit": "155699346",
    "unknown": "230425980",   # unlabeled but has features -> still scored
    "missing": "999999999999",  # not in features -> safe default
}

for kind, tx in SAMPLES.items():
    r = inference.score_tx(tx)
    assert set(r.keys()) == {
        "txId", "riskScore", "decisionThreshold", "label", "topFactors"
    }, r.keys()
    assert isinstance(r["txId"], str)
    assert isinstance(r["decisionThreshold"], int)
    assert 0 <= r["decisionThreshold"] <= 100
    if kind == "missing":
        assert r["riskScore"] is None
        assert r["label"] == "unknown"
    else:
        assert isinstance(r["riskScore"], int) and 0 <= r["riskScore"] <= 100
        assert r["label"] in ("illicit", "licit")
    assert isinstance(r["topFactors"], list) and len(r["topFactors"]) <= 6
    for f in r["topFactors"]:
        assert set(f.keys()) == {"feature", "impact"}
        assert isinstance(f["feature"], str) and isinstance(f["impact"], float)
    print(f"\nscore_tx[{kind}] {tx}: risk={r['riskScore']} label={r['label']} "
          f"nFactors={len(r['topFactors'])}")
    print("  ", json.dumps(r["topFactors"][:3], ensure_ascii=False))

for kind, tx in [("illicit", "68995268"), ("licit", "155699346")]:
    tr = inference.trace_tx(tx, hops=2)
    assert set(tr.keys()) == {
        "nodes", "edges", "candidatePaths", "decisionThreshold"
    }
    assert isinstance(tr["decisionThreshold"], int)
    assert len(tr["nodes"]) <= 60
    foci = [n for n in tr["nodes"] if n["focus"]]
    assert len(foci) == 1 and foci[0]["id"] == tx
    for n in tr["nodes"]:
        assert set(n.keys()) == {
            "id", "risk", "focus", "modelPositive", "scored"
        }
        assert isinstance(n["scored"], bool)
        if n["scored"]:
            assert isinstance(n["risk"], int) and 0 <= n["risk"] <= 100
        else:
            assert n["risk"] is None
        assert isinstance(n["modelPositive"], bool)
    ids = {n["id"] for n in tr["nodes"]}
    for e in tr["edges"]:
        assert set(e.keys()) == {"source", "target"}
        assert e["source"] in ids and e["target"] in ids
    for path in tr["candidatePaths"]:
        assert 2 <= len(path) <= 3
        assert path[0] == tx
        assert all(node_id in ids for node_id in path)
    print(f"\ntrace_tx[{kind}] {tx}: {len(tr['nodes'])} nodes, {len(tr['edges'])} edges, "
          f"focus_risk={foci[0]['risk']} threshold={tr['decisionThreshold']}")

print("\nALL ASSERTIONS PASSED")
