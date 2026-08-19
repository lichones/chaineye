# ChainEye — GCN Graph Model (Elliptic Bitcoin AML)

A standalone **Graph Convolutional Network (GCN)** node classifier trained on the
Elliptic Bitcoin transaction graph. It is a **differentiator** for the 2026 금융 AI
Challenge writeup: unlike the LightGBM baseline, which treats each transaction as an
independent feature vector, the GCN **propagates features across the transaction graph**,
so its prediction for a node also depends on that node's neighbours — capturing the
"who transacts with whom" structural signal that gradient-boosted trees cannot see.

This model is **not wired into inference.py or the backend** — it is a research artifact
that produces a trained model, metrics, and this narrative.

## Setup

```
graph      : 203,769 nodes (all transactions), 468,710 undirected edges
features   : the 165 Elliptic node features (standardized on train-mask stats)
labels     : illicit=1, licit=0, unknown=masked out of the loss
split       : EXPLORATORY TEMPORAL — train = labeled nodes with time_step 1..34
                                      test  = labeled nodes with time_step 35..49
                                      no validation split
architecture: 3 × GCNConv (165 → 128 → 128 → 2), ReLU, dropout 0.3
loss        : class-weighted cross-entropy (illicit weight ≈ 7.63, inverse-frequency)
training    : 400 epochs, Adam (lr 0.01, wd 5e-4), full-batch on CPU (~10 min)
```

Reproduce:

```
C:/Users/DELL/fsec-ai-challenge-2026/.venv/Scripts/python.exe app/ml/gcn/gcn_train.py
```

## Test-set metrics (temporal split, illicit = positive class)

| Model                 | Illicit Precision | Illicit Recall | Illicit F1 | ROC-AUC |
|-----------------------|:-----------------:|:--------------:|:----------:|:-------:|
| **GCN (this model)**  |      0.561        |     0.563      | **0.562**  | **0.892** |

Test set: 16,670 labeled nodes (1,083 illicit / 15,587 licit).
Confusion matrix (rows = true [licit, illicit], cols = predicted):

```
[[15109   478]
 [  473   610]]
```

Full metrics in [`gcn_metrics.json`](gcn_metrics.json).

## Evaluation status

This GCN run is an exploratory artifact, not a baseline comparison. It has no validation
split, logs test metrics during training, and uses full-graph message passing. Its numbers
must therefore not be compared with the independently evaluated LightGBM service model or
presented as an ensemble improvement. A comparable run requires train/validation/final-test
separation, validation-only stopping, and a single final-test evaluation.

## Files

| File              | Description                                               |
|-------------------|-----------------------------------------------------------|
| `gcn_train.py`    | End-to-end training script (data → graph → train → eval). |
| `gcn_model.pt`    | Trained weights (state_dict) + config + feature scaler.   |
| `gcn_metrics.json`| Test-set metrics and run metadata.                        |
| `README.md`       | This file.                                                |

### Loading the saved model

```python
import torch
from gcn_train import GCN
ckpt = torch.load("app/ml/gcn/gcn_model.pt", weights_only=False)
cfg = ckpt["config"]
model = GCN(cfg["in_dim"], cfg["hidden"], cfg["n_classes"], cfg["dropout"])
model.load_state_dict(ckpt["state_dict"])
model.eval()
# standardize new features with ckpt["feat_mean"] / ckpt["feat_std"] before forward()
```

*Note:* per-epoch logging shows illicit-F1 peaking near **0.61 around epoch 100** before
settling; the saved checkpoint is the epoch-400 model (ROC-AUC 0.892). Early-stopping on a
validation slice would recover a slightly higher F1 and is a cheap future improvement.
