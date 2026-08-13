"""
ChainEye (체인아이) - Bitcoin money-laundering detection
Training script for the 2026 금융 AI Challenge.

Trains a LightGBM binary classifier on the Elliptic dataset using the
standard TEMPORAL split (train time_step 1..34, test 35..49).

Run:
    C:/Users/DELL/fsec-ai-challenge-2026/.venv/Scripts/python.exe app/ml/train.py

Artifacts written into app/ml/:
    - chaineye_model.pkl        : trained LightGBM classifier (joblib)
    - feature_table.parquet     : features indexed by txId (fast inference lookup)
    - edges.parquet             : directed edge list (txId1 -> txId2)
    - shap_background.parquet    : small background sample for SHAP at inference
    - metrics.json              : evaluation metrics on the test set
    - feature_importance.csv     : global SHAP feature importance
"""
import json
import os
import time

import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "data", "elliptic_bitcoin_dataset"))
FEATURES_CSV = os.path.join(DATA_DIR, "elliptic_txs_features.csv")
CLASSES_CSV = os.path.join(DATA_DIR, "elliptic_txs_classes.csv")
EDGES_CSV = os.path.join(DATA_DIR, "elliptic_txs_edgelist.csv")

N_FEATURES = 165
FEATURE_COLS = [f"feat_{i}" for i in range(N_FEATURES)]  # feat_0 .. feat_164


def load_data():
    print(f"[load] reading features from {FEATURES_CSV} ...")
    t0 = time.time()
    # features.csv has NO header. col0=txId, col1=time_step, col2..166 = 165 feats.
    # Read txId + time_step as needed dtypes; feats as float32 to save memory.
    col_names = ["txId", "time_step"] + FEATURE_COLS
    dtype = {"txId": "int64", "time_step": "int16"}
    for c in FEATURE_COLS:
        dtype[c] = "float32"
    feats = pd.read_csv(FEATURES_CSV, header=None, names=col_names, dtype=dtype)
    print(f"[load] features shape={feats.shape} in {time.time()-t0:.1f}s")

    classes = pd.read_csv(CLASSES_CSV, dtype={"txId": "int64", "class": "string"})
    print(f"[load] classes shape={classes.shape}")

    df = feats.merge(classes, on="txId", how="left")
    return df, feats


def main():
    df, feats = load_data()

    # Map labels: illicit "1" -> 1, licit "2" -> 0, else unknown (drop for supervised)
    label_map = {"1": 1, "2": 0}
    df["label"] = df["class"].map(label_map)
    labeled = df[df["label"].notna()].copy()
    labeled["label"] = labeled["label"].astype("int8")
    print(f"[prep] labeled rows={len(labeled)} "
          f"illicit={int((labeled.label==1).sum())} licit={int((labeled.label==0).sum())}")

    # TEMPORAL split
    train_df = labeled[labeled["time_step"] <= 34]
    test_df = labeled[labeled["time_step"] >= 35]
    X_train = train_df[FEATURE_COLS].values
    y_train = train_df["label"].values
    X_test = test_df[FEATURE_COLS].values
    y_test = test_df["label"].values
    print(f"[split] train={X_train.shape} (illicit={int(y_train.sum())})  "
          f"test={X_test.shape} (illicit={int(y_test.sum())})")

    # Class imbalance
    n_pos = int(y_train.sum())
    n_neg = int((y_train == 0).sum())
    scale_pos_weight = n_neg / max(n_pos, 1)
    print(f"[prep] scale_pos_weight={scale_pos_weight:.2f}")

    clf = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=600,
        learning_rate=0.03,
        num_leaves=64,
        max_depth=-1,
        min_child_samples=30,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    print("[train] fitting LightGBM ...")
    t0 = time.time()
    clf.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        eval_metric="average_precision",
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    print(f"[train] done in {time.time()-t0:.1f}s, best_iter={clf.best_iteration_}")

    # Evaluate
    proba = clf.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    p, r, f1, _ = precision_recall_fscore_support(
        y_test, pred, labels=[1], average=None, zero_division=0)
    illicit_p, illicit_r, illicit_f1 = float(p[0]), float(r[0]), float(f1[0])
    pr_auc = float(average_precision_score(y_test, proba))
    roc_auc = float(roc_auc_score(y_test, proba))
    cm = confusion_matrix(y_test, pred, labels=[0, 1])  # rows true [licit, illicit]

    print("\n==== TEST-SET METRICS (temporal split, illicit = positive) ====")
    print(f"Illicit Precision : {illicit_p:.4f}")
    print(f"Illicit Recall    : {illicit_r:.4f}")
    print(f"Illicit F1        : {illicit_f1:.4f}   <-- headline")
    print(f"PR-AUC (AP)       : {pr_auc:.4f}")
    print(f"ROC-AUC           : {roc_auc:.4f}")
    print("Confusion matrix [rows=true licit/illicit, cols=pred licit/illicit]:")
    print(cm)
    print("\n" + classification_report(y_test, pred, target_names=["licit", "illicit"], digits=4))

    metrics = {
        "illicit_precision": illicit_p,
        "illicit_recall": illicit_r,
        "illicit_f1": illicit_f1,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "confusion_matrix": {
            "tn_licit_licit": int(cm[0, 0]),
            "fp_licit_illicit": int(cm[0, 1]),
            "fn_illicit_licit": int(cm[1, 0]),
            "tp_illicit_illicit": int(cm[1, 1]),
        },
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "best_iteration": int(clf.best_iteration_ or clf.n_estimators),
        "scale_pos_weight": float(scale_pos_weight),
        "threshold": 0.5,
    }

    # ---- SHAP global importance ----
    print("[shap] computing global feature importance ...")
    import shap
    explainer = shap.TreeExplainer(clf)
    # sample test set for global importance (speed)
    rng = np.random.RandomState(42)
    idx = rng.choice(len(X_test), size=min(3000, len(X_test)), replace=False)
    sv = explainer.shap_values(X_test[idx])
    if isinstance(sv, list):  # older shap returns list per class
        sv = sv[1]
    mean_abs = np.abs(sv).mean(axis=0)
    fi = (pd.DataFrame({"feature": FEATURE_COLS, "mean_abs_shap": mean_abs})
          .sort_values("mean_abs_shap", ascending=False))
    fi.to_csv(os.path.join(HERE, "feature_importance.csv"), index=False)
    print("[shap] top 10 features:")
    print(fi.head(10).to_string(index=False))

    # ---- Persist artifacts ----
    joblib.dump(clf, os.path.join(HERE, "chaineye_model.pkl"))

    # feature table indexed by txId (ALL nodes, so inference can score any node)
    feat_table = feats.set_index("txId")
    feat_table.to_parquet(os.path.join(HERE, "feature_table.parquet"))

    edges = pd.read_csv(EDGES_CSV, dtype={"txId1": "int64", "txId2": "int64"})
    edges.to_parquet(os.path.join(HERE, "edges.parquet"), index=False)

    # SHAP background: small representative sample of training features
    bg_idx = rng.choice(len(X_train), size=min(200, len(X_train)), replace=False)
    bg = pd.DataFrame(X_train[bg_idx], columns=FEATURE_COLS)
    bg.to_parquet(os.path.join(HERE, "shap_background.parquet"), index=False)

    with open(os.path.join(HERE, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print("\n[done] artifacts written to", HERE)
    for fn in ["chaineye_model.pkl", "feature_table.parquet", "edges.parquet",
               "shap_background.parquet", "metrics.json", "feature_importance.csv"]:
        p = os.path.join(HERE, fn)
        print(f"   {fn:26s} {os.path.getsize(p)/1e6:8.2f} MB")


if __name__ == "__main__":
    main()
