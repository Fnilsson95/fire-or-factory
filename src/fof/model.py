"""Model with rule baseline, gradient-boosted classifier and comparison with FIRMs own labels

There is no ground truth so FIRMs static label (type 2/3) is used as noisy training labels
from VIIRS only (MODIS labels are much weaker). The model is then applied to both sensors
MODIS detections in cells that VIIRS sees all year inherit that cells history

Evaluation uses cross-validation grouped by grid cell, so the model is alwaysa scored on
cells it has never seen, never on a cell it can memorize
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from fof.features import CELL_FEATURES
from fof.features import OUT_PATH as FEATURES_PATH

OUT_PATH = Path("data/clean/classified.parquet")

MODEL_FEATURES = CELL_FEATURES + ["frp", "is_night"]
RULE_MIN_MONTHS = 6
THRESHOLD = 0.5
N_FOLDS = 5


def rule_static(df: pd.DataFrame, min_months: int = RULE_MIN_MONTHS) -> pd.Series:
    """A cell active in at least "min_months" different months is static"""
    return df["cell_months"] >= min_months

def make_model() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=20,
        random_state=42, verbose=-1,
    )


def cross_validated_scores(df: pd.DataFrame) -> np.ndarray:
    """Out-of-fold P(static) for every row in df, scored on unseed grid cells only"""

    X, y = df[MODEL_FEATURES], df["firms_static"].astype(int)
    groups = df["cell_x"].astype(str) + "_" + df["cell_y"].astype(str)
    scores = np.zeros(len(df))
    for train, test in GroupKFold(n_splits=N_FOLDS).split(X, y, groups):
        model = make_model().fit(X.iloc[train], y.iloc[train])
        scores[test] = model.predict_proba(X.iloc[test])[:, 1]
    return scores


def agreement(pred: pd.Series, firms: pd.Series) -> pd.DataFrame:
    """2x2 table: our label (rows) against FIRMs label (columns)"""
    return pd.crosstab(
        pred.map({True: "ours: static", False: "ours: fire"}),
        firms.map({True: "FIRMS: static", False: "FIRMS: fire"}),
    )


def classify(in_path: Path = FEATURES_PATH, out_path: Path = OUT_PATH) -> pd.DataFrame:
    df = pd.read_parquet(in_path)
    df["rule_static"] = rule_static(df)

    viirs = df["family"] == "VIIRS"
    v = df[viirs]

    # 1. How well do rule and model reproduce FIRMS on VIIRS cells they have not seen?
    oof = cross_validated_scores(v)
    rule_acc = (v["rule_static"] == v["firms_static"]).mean()
    model_acc = ((oof >= THRESHOLD) == v["firms_static"]).mean()
    print(f"VIIRS, unseen cells: rule accuracy {rule_acc:.3f} | "
          f"model accuracy {model_acc:.3f}, ROC AUC {roc_auc_score(v['firms_static'], oof):.3f}")

    # 2. Final model on all VIIRS labels, applied to every detection (MODIS included).
    model = make_model().fit(v[MODEL_FEATURES], v["firms_static"].astype(int))
    df["p_static"] = model.predict_proba(df[MODEL_FEATURES])[:, 1]
    df.loc[viirs, "p_static"] = oof  # VIIRS rows: keep the honest out-of-fold score
    df["is_static"] = df["p_static"] >= THRESHOLD

    for family in ["VIIRS", "MODIS"]:
        part = df[df["family"] == family]
        print(f"\n{family}: our label vs FIRMS")
        print(agreement(part["is_static"], part["firms_static"]).to_string())

    importance = pd.Series(model.feature_importances_, index=MODEL_FEATURES)
    print("\nFeature importance (splits):")
    print(importance.sort_values(ascending=False).to_string())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"\nwrote {out_path}")
    return df


def disagreements(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Cells with the most detections where we and FIRMS disagree: candidates to check on a map.

    we_static: we say static, FIRMS says fire (possible factory FIRMS missed).
    we_fire:   we say fire, FIRMS says static (possible FIRMS false alarm, or our mistake).
    """
    d = df.assign(
        we_static=df["is_static"] & ~df["firms_static"],
        we_fire=~df["is_static"] & df["firms_static"],
    )
    cells = d.groupby(["cell_x", "cell_y"]).agg(
        lat=("latitude", "mean"), lon=("longitude", "mean"),
        we_static=("we_static", "sum"), we_fire=("we_fire", "sum"),
        cell_days=("cell_days", "first"), cell_months=("cell_months", "first"),
        families=("family", lambda s: ",".join(sorted(set(s)))),
    )
    cells["disagree"] = cells["we_static"] + cells["we_fire"]
    return cells[cells["disagree"] > 0].sort_values("disagree", ascending=False).head(n).round(3)