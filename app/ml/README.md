# ChainEye (체인아이) — ML module

Bitcoin money-laundering (illicit-transaction) detection for the 2026 금융 AI Challenge.
LightGBM binary classifier trained on the **Elliptic** dataset using the standard
**temporal split** (train time_step 1..34, test 35..49 — never a random split).

## Test-set metrics (temporal split, illicit = positive class)

| Metric | Value |
|---|---|
| Illicit Precision | 0.8259 |
| Illicit Recall | 0.7313 |
| **Illicit F1 (headline)** | **0.7757** |
| PR-AUC (Average Precision) | 0.7970 |
| ROC-AUC | 0.9363 |

Confusion matrix (rows = true, cols = predicted), threshold 0.5:

|            | pred licit | pred illicit |
|------------|-----------:|-------------:|
| **true licit**   | 15420 | 167 |
| **true illicit** |   291 | 792 |

Train: 29,894 labeled tx (3,462 illicit). Test: 16,670 labeled tx (1,083 illicit).
`scale_pos_weight = 7.63` for class imbalance. Headline illicit-F1 = 0.776 sits inside
the published LightGBM/GBT baseline range (~0.70–0.80).

Top global SHAP features: feat_58, feat_52, feat_75, feat_57, feat_4, feat_124
(Elliptic features are anonymized; `feat_i` = column i of the 165 features).

## Artifacts (all in `app/ml/`)

| File | Purpose |
|---|---|
| `chaineye_model.pkl` | trained LightGBM classifier (joblib) |
| `feature_table.parquet` | 165 features indexed by txId (all 203,769 nodes) for fast inference |
| `edges.parquet` | directed edge list (txId1 -> txId2) |
| `shap_background.parquet` | background sample for SHAP |
| `feature_importance.csv` | global SHAP mean-abs importance |
| `metrics.json` | evaluation metrics |

## Inference API (`inference.py`) — imported by the backend

```python
from app.ml import inference
inference.load()                      # once at startup; idempotent
inference.score_tx("232629023")
#   {"txId": "232629023", "riskScore": 98, "label": "illicit",
#    "topFactors": [{"feature": "feat_1", "impact": 1.18}, ...]}   # up to 6, signed SHAP
inference.trace_tx("232629023", hops=2)
#   {"nodes": [{"id": str, "risk": int, "focus": bool}, ...],      # <= 60 nodes
#    "edges": [{"source": str, "target": str}, ...]}
```

- Unlabeled/unknown txId **with features** is still scored.
- txId **not in the feature table** returns `riskScore 0`, `label "licit"`, empty `topFactors` (never raises).
- `trace_tx` follows edges both directions up to `hops`; caps at ~60 nodes keeping highest-risk neighbors.

## Retrain

```
C:/Users/DELL/fsec-ai-challenge-2026/.venv/Scripts/python.exe app/ml/train.py
```

Re-reads the Elliptic CSVs from `data/elliptic_bitcoin_dataset/`, rebuilds all artifacts
above (~30s total; features.csv is 665MB, read once with float32 downcasting).

Verify inference: `... python app/ml/verify_inference.py`
