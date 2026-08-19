# ChainEye (체인아이) — ML module

Bitcoin money-laundering (illicit-transaction) detection for the 2026 금융 AI Challenge.
LightGBM binary classifier trained on the **Elliptic** dataset using a strict
**temporal split**: train 1..30, validation 31..34, final test 35..49. The final
test window is not used for early stopping, threshold selection, or model choice.

## Test-set metrics (temporal split, illicit = positive class)

| Metric | Value |
|---|---|
| Illicit Precision | 0.6985 |
| Illicit Recall | 0.7230 |
| **Illicit F1 (headline)** | **0.7105** |
| PR-AUC (Average Precision) | 0.6739 |
| ROC-AUC | 0.8990 |
| Brier score | 0.0510 |

Confusion matrix (rows = true, cols = predicted), validation-selected threshold 0.2257:

|            | pred licit | pred illicit |
|------------|-----------:|-------------:|
| **true licit**   | 15249 | 338 |
| **true illicit** |   300 | 783 |

Train: 26,905 labeled tx; validation: 2,989; train+validation refit: 29,894;
final test: 16,670 (1,083 illicit). The selected threshold sends about 67 of every
1,000 test transactions to analyst review. The earlier F1 0.7757 / ROC-AUC 0.9363
run used the final test window for early stopping and is retained only as a lesson
about optimistic evaluation, not as the current performance claim.

Top global SHAP features: feat_52, feat_21, feat_17, feat_39, feat_158, feat_45
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
inference.score_tx("68995268")
#   {"txId": "68995268", "riskScore": 29, "decisionThreshold": 23,
#    "label": "illicit", "topFactors": [...]}  # up to 6, signed SHAP
inference.trace_tx("68995268", hops=2)
#   {"nodes": [{"id": str, "risk": int|None, "focus": bool,
#                "modelPositive": bool, "scored": bool}, ...],
#    "edges": [...], "candidatePaths": [...], "decisionThreshold": 23}
```

- Unlabeled/unknown txId **with features** is still scored.
- txId **not in the feature table** returns `riskScore None`, `label "unknown"`,
  and empty `topFactors`. Absence from this closed benchmark is never treated as
  evidence of licit behavior.
- `trace_tx` follows edges both directions up to `hops`; caps at ~60 nodes keeping highest-risk neighbors.

## Retrain

```
C:/Users/DELL/fsec-ai-challenge-2026/.venv/Scripts/python.exe app/ml/train.py
```

Re-reads the Elliptic CSVs from `data/elliptic_bitcoin_dataset/`, rebuilds all artifacts
above (~30s total; features.csv is 665MB, read once with float32 downcasting).

Verify inference: `... python app/ml/verify_inference.py`
