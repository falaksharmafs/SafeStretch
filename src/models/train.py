"""Train the segment-risk model.

Setup: one row per (road segment, quarter t). Features use information up to and
including quarter t.

Label: does the segment have a SERIOUS/FATAL accident (severity <= 2)
in quarter t+1?

Validation:
  * Spatial CV - GroupKFold on ~2 km grid blocks.
  * Temporal  - train on earlier quarters, test on the most recent labelled quarter.
  * Baseline   - rank by historical accident count only.

Metrics are ranking metrics because positives are rare.
"""

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from ..config import GRID_DEG, REPORTS_DIR
from ..db import get_engine


# ---------------------------------------------------------------------
# FEATURES
# ---------------------------------------------------------------------

STATIC_NUM = [
    "speed_limit",
    "lanes",
    "oneway",
    "length_m",
    "curvature",
    "alcohol_nearby",
    "junctions_nearby",
    "schools_nearby",
    "hospitals_nearby",
    "bus_stops_nearby",
    "crossings_nearby",
]

HIST = [
    "acc_cum",
    "serious_cum",
    "acc_last",
    "serious_last",
    "night_cum",
    "rain_cum",
]

FEATURES = ["road_type"] + STATIC_NUM + HIST


LABELS = {
    "road_type": "road type",
    "speed_limit": "speed limit",
    "lanes": "lanes",
    "oneway": "one-way",
    "length_m": "segment length (m)",
    "curvature": "curvature",
    "alcohol_nearby": "alcohol outlets nearby",
    "junctions_nearby": "junctions nearby",
    "schools_nearby": "schools nearby",
    "hospitals_nearby": "hospitals nearby",
    "bus_stops_nearby": "bus stops nearby",
    "crossings_nearby": "crossings nearby",
    "acc_cum": "past accidents",
    "serious_cum": "past serious accidents",
    "acc_last": "accidents last quarter",
    "serious_last": "serious accidents last quarter",
    "night_cum": "past night accidents",
    "rain_cum": "past rain accidents",
}


PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
)


# ---------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------

def recall_at(y, score, frac):
    """Recall among the highest-risk fraction of segments."""

    rng = np.random.default_rng(0)

    # Random tie-breaker.
    # Useful because the history-only baseline contains many ties.
    s = score + rng.random(len(score)) * 1e-9

    k = max(1, int(len(y) * frac))

    top = np.argsort(-s)[:k]

    return float(
        y[top].sum() / max(y.sum(), 1)
    )


def metrics(y, score):
    """Calculate ranking metrics."""

    y = np.asarray(y)

    both = y.min() != y.max()

    return {
        "n": int(len(y)),
        "positives": int(y.sum()),

        "pr_auc": (
            float(average_precision_score(y, score))
            if both
            else None
        ),

        "roc_auc": (
            float(roc_auc_score(y, score))
            if both
            else None
        ),

        "recall_top1pct": recall_at(
            y,
            score,
            0.01,
        ),

        "recall_top5pct": recall_at(
            y,
            score,
            0.05,
        ),
    }


# ---------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------

def load():
    """Load static road features and quarterly accident counts."""

    eng = get_engine()

    static = pd.read_sql(
        "SELECT * FROM segment_static_features",
        eng,
    )

    counts = pd.read_sql(
        "SELECT * FROM segment_period_counts",
        eng,
    )

    counts["period_start"] = pd.to_datetime(
        counts["period_start"]
    )

    # Ensure boolean one-way becomes numeric.
    static["oneway"] = (
        static["oneway"]
        .fillna(False)
        .astype(int)
    )

    # Missing road types.
    static["road_type"] = (
        static["road_type"]
        .fillna("unknown")
        .astype(str)
    )

    # Create spatial grid IDs for GroupKFold.
    static["grid_id"] = (
        np.floor(static["lat"] / GRID_DEG).astype("int64") * 100000
        + np.floor(static["lon"] / GRID_DEG).astype("int64")
    )

    periods = pd.date_range(
        counts.period_start.min(),
        counts.period_start.max(),
        freq="QS",
    )

    return static, counts, periods


# ---------------------------------------------------------------------
# MATRIX BUILDING
# ---------------------------------------------------------------------

def matrices(static, counts, periods):
    """Convert quarterly counts into segment x quarter matrices."""

    sidx = pd.Series(
        np.arange(len(static)),
        index=static.segment_id.values,
    )

    pmap = {
        p: i
        for i, p in enumerate(periods)
    }

    r = sidx.loc[
        counts.segment_id.values
    ].values

    c = counts.period_start.map(
        pmap
    ).values

    def mat(col):
        m = np.zeros(
            (len(static), len(periods)),
            dtype=np.float32,
        )

        np.add.at(
            m,
            (r, c),
            counts[col].values.astype(np.float32),
        )

        return m

    return {
        k: mat(v)
        for k, v in {
            "A": "n_acc",
            "S": "n_serious",
            "N": "n_night",
            "R": "n_rain",
        }.items()
    }


# ---------------------------------------------------------------------
# FRAME BUILDING
# ---------------------------------------------------------------------

def build_frame(static, M, cum, j, cats):
    """Build one quarter of segment-level features."""

    df = pd.DataFrame({
        "segment_id": static.segment_id.values,

        "grid_id": static.grid_id.values,

        "acc_cum": cum["A"][:, j],

        "serious_cum": cum["S"][:, j],

        "night_cum": cum["N"][:, j],

        "rain_cum": cum["R"][:, j],

        "acc_last": M["A"][:, j],

        "serious_last": M["S"][:, j],
    })

    for col in ["road_type"] + STATIC_NUM:
        df[col] = static[col].values

    # Explicit categorical dtype.
    df["road_type"] = pd.Categorical(
        df["road_type"],
        categories=cats,
    )

    return df


# ---------------------------------------------------------------------
# FEATURE PREPARATION
# ---------------------------------------------------------------------

def prepare_features(X):
    """Prepare features so LightGBM receives valid numeric/categorical dtypes."""

    X = X.copy()

    # Convert all numeric features explicitly.
    #
    # This fixes columns such as speed_limit and lanes that may have
    # been loaded from PostGIS as pandas object/string columns.
    for col in STATIC_NUM + HIST:
        if col in X.columns:
            X[col] = pd.to_numeric(
                X[col],
                errors="coerce",
            )

    # LightGBM supports pandas categorical columns.
    if "road_type" in X.columns:
        X["road_type"] = X["road_type"].astype("category")

    # Replace any remaining missing numeric values.
    X = X.fillna(0)

    return X


# ---------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------

def fit(X, y):
    """Fit the LightGBM classifier."""

    X = prepare_features(X)

    model = lgb.LGBMClassifier(
        **PARAMS
    )

    categorical_features = []

    if "road_type" in X.columns:
        categorical_features.append("road_type")

    model.fit(
        X,
        y,
        categorical_feature=categorical_features,
    )

    return model


# ---------------------------------------------------------------------
# SHAP EXPLANATIONS
# ---------------------------------------------------------------------

def explain(model, X, scores, top_n=2000):
    """Get top-3 positive SHAP drivers for highest-risk rows."""

    top = np.argsort(-scores)[:top_n]

    sv = shap.TreeExplainer(
        model
    ).shap_values(
        X.iloc[top]
    )

    # Some SHAP versions return a list.
    if isinstance(sv, list):
        sv = sv[1]

    sv = np.asarray(sv)

    # Handle possible 3D SHAP output.
    if sv.ndim == 3:
        sv = sv[..., 1]

    reasons = {}

    for row, pos in enumerate(top):

        out = []

        # Features with highest positive SHAP contribution.
        for f in np.argsort(-sv[row])[:3]:

            if sv[row][f] <= 0:
                break

            name = X.columns[f]

            val = X.iloc[pos][name]

            if isinstance(val, str):
                display_value = val
            else:
                try:
                    display_value = format(
                        float(val),
                        "g",
                    )
                except (TypeError, ValueError):
                    display_value = str(val)

            out.append(
                f"{LABELS[name]}: {display_value}"
            )

        # Always keep exactly 3 reason slots.
        reasons[pos] = out + [""] * (
            3 - len(out)
        )

    return reasons


# ---------------------------------------------------------------------
# MAIN TRAINING PIPELINE
# ---------------------------------------------------------------------

def main():

    # -------------------------------------------------------------
    # Load data
    # -------------------------------------------------------------

    static, counts, periods = load()

    T = len(periods)

    if T < 4:
        raise SystemExit(
            f"Need at least 4 quarters of data, found {T}"
        )

    print(
        f"{len(static):,} segments, "
        f"{T} quarters "
        f"({periods[0].date()} -> {periods[-1].date()})"
    )

    # -------------------------------------------------------------
    # Build matrices
    # -------------------------------------------------------------

    M = matrices(
        static,
        counts,
        periods,
    )

    # Cumulative historical counts.
    cum = {
        k: v.cumsum(axis=1)
        for k, v in M.items()
    }

    cats = sorted(
        static.road_type.unique()
    )

    # -------------------------------------------------------------
    # Build quarter panel
    # -------------------------------------------------------------

    frames = []

    for j in range(T - 1):

        f = build_frame(
            static,
            M,
            cum,
            j,
            cats,
        )

        # Label:
        # Did a serious/fatal accident happen
        # in the NEXT quarter?
        f["y"] = (
            M["S"][:, j + 1] > 0
        ).astype(int)

        f["j"] = j

        frames.append(f)

    panel = pd.concat(
        frames,
        ignore_index=True,
    )

    # -------------------------------------------------------------
    # Train/test split
    # -------------------------------------------------------------

    train = panel[
        panel.j <= T - 3
    ]

    test = panel[
        panel.j == T - 2
    ]

    if train.y.sum() < 50:
        print(
            "WARNING: fewer than 50 positive "
            "training rows - results will be unreliable."
        )

    # -------------------------------------------------------------
    # Spatial cross-validation
    # -------------------------------------------------------------

    print("\nRunning spatial cross-validation...")

    oof = np.zeros(
        len(train),
        dtype=float,
    )

    for k, (tr, va) in enumerate(
        GroupKFold(5).split(
            train,
            train.y,
            groups=train.grid_id,
        ),
        1,
    ):

        X_tr = prepare_features(
            train.iloc[tr][FEATURES]
        )

        X_va = prepare_features(
            train.iloc[va][FEATURES]
        )

        m = fit(
            X_tr,
            train.y.iloc[tr],
        )

        oof[va] = m.predict_proba(
            X_va
        )[:, 1]

        print(
            f"  spatial fold {k}/5 done"
        )

    res = {
        "spatial_cv": {
            "model": metrics(
                train.y.values,
                oof,
            ),

            "baseline_history_only": metrics(
                train.y.values,
                train.acc_cum.values.astype(float),
            ),
        },
    }

    # -------------------------------------------------------------
    # Temporal hold-out
    # -------------------------------------------------------------

    print("\nRunning temporal hold-out...")

    X_train = prepare_features(
        train[FEATURES]
    )

    X_test = prepare_features(
        test[FEATURES]
    )

    m = fit(
        X_train,
        train.y,
    )

    p_test = m.predict_proba(
        X_test
    )[:, 1]

    res["temporal_test"] = {
        "test_quarter_label": str(
            periods[T - 1].date()
        ),

        "model": metrics(
            test.y.values,
            p_test,
        ),

        "baseline_history_only": metrics(
            test.y.values,
            test.acc_cum.values.astype(float),
        ),
    }

    # -------------------------------------------------------------
    # Final model
    # -------------------------------------------------------------

    print("\nTraining final model...")

    X_panel = prepare_features(
        panel[FEATURES]
    )

    final = fit(
        X_panel,
        panel.y,
    )

    # -------------------------------------------------------------
    # Score latest quarter
    # -------------------------------------------------------------

    cur = build_frame(
        static,
        M,
        cum,
        T - 1,
        cats,
    )

    X = prepare_features(
        cur[FEATURES]
    )

    score = final.predict_proba(
        X
    )[:, 1]

    # -------------------------------------------------------------
    # SHAP explanations
    # -------------------------------------------------------------

    print("Generating SHAP explanations...")

    reasons = explain(
        final,
        X,
        score,
    )

    # -------------------------------------------------------------
    # Output risk table
    # -------------------------------------------------------------

    out = pd.DataFrame({
        "segment_id": cur.segment_id.values,
        "risk_score": score,
    })

    out["risk_rank"] = (
        out.risk_score
        .rank(
            ascending=False,
            method="first",
        )
        .astype(int)
    )

    for i in range(3):

        out[f"reason_{i + 1}"] = [
            reasons.get(
                p,
                [""] * 3,
            )[i]

            for p in range(
                len(out)
            )
        ]

    out["as_of_period"] = str(
        periods[T - 1].date()
    )

    # -------------------------------------------------------------
    # Save to PostgreSQL
    # -------------------------------------------------------------

    print("\nSaving segment_risk table...")

    eng = get_engine()

    out.to_sql(
        "segment_risk",
        eng,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=5000,
    )

    with eng.begin() as con:

        con.exec_driver_sql(
            "CREATE UNIQUE INDEX "
            "segment_risk_segment_id_idx "
            "ON segment_risk (segment_id)"
        )

        con.exec_driver_sql(
            "CREATE INDEX "
            "segment_risk_risk_rank_idx "
            "ON segment_risk (risk_rank)"
        )

    # -------------------------------------------------------------
    # Save metrics
    # -------------------------------------------------------------

    REPORTS_DIR.mkdir(
        exist_ok=True
    )

    (
        REPORTS_DIR / "metrics.json"
    ).write_text(
        json.dumps(
            res,
            indent=2,
        )
    )

    # -------------------------------------------------------------
    # Print final results
    # -------------------------------------------------------------

    print("\nTraining complete.\n")

    print(
        json.dumps(
            res,
            indent=2,
        )
    )

    print(
        f"\nSaved {len(out):,} segment risk scores."
    )

    print(
        "Created PostgreSQL table: segment_risk"
    )


if __name__ == "__main__":
    main()