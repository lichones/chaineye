"""
ChainEye (체인아이) - Bitcoin money-laundering detection
Training script for the 2026 금융 AI Challenge.

Trains a LightGBM binary classifier on the Elliptic dataset using a strict
TEMPORAL split (train 1..30, validation 31..34, final test 35..49).

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
    brier_score_loss,
    roc_auc_score,
    precision_recall_fscore_support,
    precision_recall_curve,
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
TRAIN_END = 30
VALIDATION_END = 34


def _best_f1_threshold(y_true, probabilities) -> float:
    """Select a classification threshold using validation data only."""
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    if thresholds.size == 0:
        return 0.5
    denom = precision[:-1] + recall[:-1]
    f1 = np.divide(
        2 * precision[:-1] * recall[:-1],
        denom,
        out=np.zeros_like(denom),
        where=denom > 0,
    )
    return float(thresholds[int(np.argmax(f1))])


def _model_params(n_estimators: int, scale_pos_weight: float) -> dict:
    return {
        "objective": "binary",
        "n_estimators": n_estimators,
        "learning_rate": 0.03,
        "num_leaves": 64,
        "max_depth": -1,
        "min_child_samples": 30,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,
        "scale_pos_weight": scale_pos_weight,
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    }


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

    # Strict TEMPORAL split. The final test window is never used for model
    # selection, early stopping, or threshold tuning.
    train_df = labeled[labeled["time_step"] <= TRAIN_END]
    validation_df = labeled[
        (labeled["time_step"] > TRAIN_END)
        & (labeled["time_step"] <= VALIDATION_END)
    ]
    test_df = labeled[labeled["time_step"] > VALIDATION_END]
    X_train = train_df[FEATURE_COLS].values
    y_train = train_df["label"].values
    X_validation = validation_df[FEATURE_COLS].values
    y_validation = validation_df["label"].values
    X_test = test_df[FEATURE_COLS].values
    y_test = test_df["label"].values
    print(f"[split] train={X_train.shape} (illicit={int(y_train.sum())})  "
          f"validation={X_validation.shape} (illicit={int(y_validation.sum())})  "
          f"test={X_test.shape} (illicit={int(y_test.sum())})")

    if min(len(y_train), len(y_validation), len(y_test)) == 0:
        raise ValueError("Temporal train/validation/test split produced an empty partition")

    # Class imbalance
    n_pos = int(y_train.sum())
    n_neg = int((y_train == 0).sum())
    scale_pos_weight = n_neg / max(n_pos, 1)
    print(f"[prep] scale_pos_weight={scale_pos_weight:.2f}")

    tuning_clf = lgb.LGBMClassifier(**_model_params(600, scale_pos_weight))
    print("[train] fitting selection model on train window ...")
    t0 = time.time()
    tuning_clf.fit(
        X_train, y_train,
        eval_set=[(X_validation, y_validation)],
        eval_metric="average_precision",
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    best_iteration = int(tuning_clf.best_iteration_ or tuning_clf.n_estimators)
    validation_proba = tuning_clf.predict_proba(X_validation)[:, 1]
    threshold = _best_f1_threshold(y_validation, validation_proba)
    print(f"[train] selection done in {time.time()-t0:.1f}s, "
          f"best_iter={best_iteration}, validation_threshold={threshold:.4f}")

    # Refit the deployable model on train + validation with the selected tree
    # count. The untouched test window remains available for one final estimate.
    train_validation_df = pd.concat([train_df, validation_df], ignore_index=True)
    X_train_validation = train_validation_df[FEATURE_COLS].values
    y_train_validation = train_validation_df["label"].values
    final_pos = int(y_train_validation.sum())
    final_neg = int((y_train_validation == 0).sum())
    final_scale_pos_weight = final_neg / max(final_pos, 1)
    clf = lgb.LGBMClassifier(
        **_model_params(best_iteration, final_scale_pos_weight)
    )
    print("[train] refitting final model on train + validation windows ...")
    clf.fit(X_train_validation, y_train_validation)

    # Evaluate once on the untouched final test window.
    proba = clf.predict_proba(X_test)[:, 1]
    pred = (proba >= threshold).astype(int)

    p, r, f1, _ = precision_recall_fscore_support(
        y_test, pred, labels=[1], average=None, zero_division=0)
    illicit_p, illicit_r, illicit_f1 = float(p[0]), float(r[0]), float(f1[0])
    pr_auc = float(average_precision_score(y_test, proba))
    roc_auc = float(roc_auc_score(y_test, proba))
    brier = float(brier_score_loss(y_test, proba))
    cm = confusion_matrix(y_test, pred, labels=[0, 1])  # rows true [licit, illicit]

    # Preserve a fixed 0.5 view for comparison with older runs. This is a
    # diagnostic only; the deployable decision threshold comes from validation.
    fixed_pred = (proba >= 0.5).astype(int)
    fixed_p, fixed_r, fixed_f1, _ = precision_recall_fscore_support(
        y_test, fixed_pred, labels=[1], average=None, zero_division=0
    )
    fixed_cm = confusion_matrix(y_test, fixed_pred, labels=[0, 1])

    print("\n==== TEST-SET METRICS (temporal split, illicit = positive) ====")
    print(f"Illicit Precision : {illicit_p:.4f}")
    print(f"Illicit Recall    : {illicit_r:.4f}")
    print(f"Illicit F1        : {illicit_f1:.4f}   <-- headline")
    print(f"PR-AUC (AP)       : {pr_auc:.4f}")
    print(f"ROC-AUC           : {roc_auc:.4f}")
    print(f"Brier score       : {brier:.4f}")
    print("Confusion matrix [rows=true licit/illicit, cols=pred licit/illicit]:")
    print(cm)
    print("\n" + classification_report(y_test, pred, target_names=["licit", "illicit"], digits=4))

    metrics = {
        "illicit_precision": illicit_p,
        "illicit_recall": illicit_r,
        "illicit_f1": illicit_f1,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "brier_score": brier,
        "confusion_matrix": {
            "tn_licit_licit": int(cm[0, 0]),
            "fp_licit_illicit": int(cm[0, 1]),
            "fn_illicit_licit": int(cm[1, 0]),
            "tp_illicit_illicit": int(cm[1, 1]),
        },
        "split": {
            "train": f"time_step 1..{TRAIN_END}",
            "validation": f"time_step {TRAIN_END + 1}..{VALIDATION_END}",
            "final_test": f"time_step {VALIDATION_END + 1}..49",
            "final_test_used_for_model_selection": False,
        },
        "n_train": int(len(y_train)),
        "n_validation": int(len(y_validation)),
        "n_train_validation": int(len(y_train_validation)),
        "n_test": int(len(y_test)),
        "best_iteration": best_iteration,
        "scale_pos_weight_selection": float(scale_pos_weight),
        "scale_pos_weight_final": float(final_scale_pos_weight),
        "threshold": threshold,
        "threshold_selected_on": "validation",
        "analyst_reviews_per_1000_at_selected_threshold": float(
            pred.sum() / len(pred) * 1000
        ),
        "fixed_threshold_0_5": {
            "illicit_precision": float(fixed_p[0]),
            "illicit_recall": float(fixed_r[0]),
            "illicit_f1": float(fixed_f1[0]),
            "confusion_matrix": {
                "tn_licit_licit": int(fixed_cm[0, 0]),
                "fp_licit_illicit": int(fixed_cm[0, 1]),
                "fn_illicit_licit": int(fixed_cm[1, 0]),
                "tp_illicit_illicit": int(fixed_cm[1, 1]),
            },
        },
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
