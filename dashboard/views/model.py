import pandas as pd
import streamlit as st

from ..config import BAND_NOTE, MODEL_PATH
from ..core import model_info as M
from ..core import queries as Q
from ..core.risk import fmt_int, parse_reason, top_overlap
from ..ui import charts, theme as th
from ..ui.compat import stretch

CFG = {"displayModeBar": False}
METRICS = [("PR-AUC", "pr_auc"), ("ROC-AUC", "roc_auc"), ("Recall @ top 1%", "recall_top1pct"), ("Recall @ top 5%", "recall_top5pct")]


@st.cache_resource(show_spinner=False)
def _artifact(mtime):
    import joblib
    return joblib.load(MODEL_PATH)


def _importance():
    if not M.has_model_artifact():
        return None
    try:
        art = _artifact(MODEL_PATH.stat().st_mtime)
        return list(art["features"]), list(art["model"].booster_.feature_importance(importance_type="gain"))
    except Exception:
        return None


def _table(block):
    mm, bb = block["model"], block["baseline_history_only"]
    rows = []
    for label, k in METRICS:
        a, b = mm.get(k), bb.get(k)
        rows.append({"Metric": label, "Model": a, "Baseline": b, "Change": (a - b) if a is not None and b is not None else None})
    return pd.DataFrame(rows)


def _validation(title, block):
    th.section(title)
    df = _table(block)
    a, b = st.columns([1.1, 1], gap="medium")
    with a:
        stretch(st.plotly_chart, charts.metric_compare(df), config=CFG)
    with b:
        stretch(st.dataframe, df.rename(columns={"Baseline": "History-only baseline", "Change": "Δ vs baseline"}), hide_index=True,
                column_config={c: st.column_config.NumberColumn(format="%.3f") for c in ("Model", "Baseline", "Change")} |
                {"History-only baseline": st.column_config.NumberColumn(format="%.3f"), "Δ vs baseline": st.column_config.NumberColumn(format="%+.3f")})
        n, pos = block["model"].get("n"), block["model"].get("positives")
        if n:
            st.caption(f"{fmt_int(n)} rows · {fmt_int(pos)} positives · prevalence {pos / n:.3%} (a random ranking scores a PR-AUC of about this).")


def render():
    seg, m, acc = Q.segments(), M.metrics(), Q.accident_facts()
    if acc.get("synthetic"):
        th.callout("Synthetic accident data", "These metrics validate that the pipeline works on generated data. They are NOT evidence of "
                   "real-world predictive performance.", "warn")
    th.section("Model", "Transparent validation - ranking metrics, not an 'accuracy' percentage.")
    t_perf, t_cal, t_eb, t_exp = st.tabs(["Performance", "Calibration", "Black-spot comparison (EB)", "Explainability"])

    with t_perf:
        if not m:
            th.callout("No metrics yet", "reports/metrics.json was not found. Run `python -m src.models.train`.", "warn")
        else:
            qc = Q.quarterly_counts()
            span = f"{pd.Timestamp(qc.quarter.min()):%b %Y} → {pd.Timestamp(qc.quarter.max()):%b %Y}" if not qc.empty else "N/A"
            test_q = (m.get("temporal_test") or {}).get("test_quarter_label")
            as_of = seg.as_of_period.dropna().iloc[0] if not seg.empty and seg.as_of_period.notna().any() else None
            th.render(th.stat_grid([("Algorithm", "LightGBM (gradient-boosted trees)"), ("Model version", M.version(m)),
                                    ("Data span", span), ("Temporal hold-out quarter", f"{pd.Timestamp(test_q):%b %Y}" if test_q else "N/A"),
                                    ("Scores predict the quarter after", f"{pd.Timestamp(as_of):%b %Y}" if as_of is not None else "N/A"),
                                    ("Segments scored", fmt_int(len(seg)))], cols=3))
            if "spatial_cv" in m:
                _validation("Spatial cross-validation", m["spatial_cv"])
                st.caption("Folds are ~2 km geographic blocks, so neighbouring roads never sit in both training and validation.")
            if "temporal_test" in m:
                _validation("Temporal hold-out", m["temporal_test"])
                st.caption("Trained on earlier quarters, tested on the most recent labelled quarter.")
            th.callout("Why PR-AUC and recall@k?", "Serious accidents on any one segment are rare, so plain accuracy would look excellent for a model "
                       "that predicts 'no accident' everywhere. PR-AUC and recall in the top 1% / 5% of ranked segments measure what matters: "
                       "does the ranking put future accident segments near the top? The history-only baseline ranks by past accident counts.")

    with t_cal:
        cal = (m or {}).get("calibration")
        if not cal:
            th.callout("Calibration not available", "The current trainer outputs an uncalibrated score. The upgraded trainer adds isotonic "
                       "calibration and writes reliability bins to metrics.json; this tab fills in automatically.", "muted")
        else:
            a, b = st.columns([1.2, 1], gap="medium")
            with a:
                stretch(st.plotly_chart, charts.reliability(cal["reliability_calibrated_test"]), config=CFG)
            with b:
                th.render(th.stat_grid([("Brier score · raw", f"{cal['brier_raw']:.5f}"), ("Brier score · calibrated", f"{cal['brier_calibrated']:.5f}")]))
                st.caption("Lower Brier is better. Points near the diagonal mean predicted probabilities match observed frequencies.")
            bins = pd.DataFrame(cal["reliability_calibrated_test"]).rename(columns={"mean_pred": "Predicted", "observed": "Observed", "n": "Segments"})
            stretch(st.dataframe, bins, hide_index=True, column_config={"Predicted": st.column_config.NumberColumn(format="%.4f"),
                                                                        "Observed": st.column_config.NumberColumn(format="%.4f")})
        th.callout("Probability vs index", "A calibrated probability answers 'how often do segments scored like this have a serious accident next "
                   "quarter?'. The Live Risk Index (added later) is a relative index = base risk × hour multiplier × rain multiplier. "
                   "The two are never mixed or shown as the same thing.", "accent")

    with t_eb:
        if seg.empty or seg.eb_rank.isna().all():
            th.callout("Empirical-Bayes ranking not available", "segment_eb is empty or missing. Run `python -m src.models.empirical_bayes` "
                       "(part of the upgraded project) and refresh.", "muted")
        else:
            k = st.segmented_control("Compare top", [25, 50, 100], default=50, key="eb_k", label_visibility="collapsed") or 50
            top_m, top_e = seg.nsmallest(k, "risk_rank"), seg.nsmallest(k, "eb_rank")
            o = top_overlap(top_m.segment_id, top_e.segment_id)
            cols = st.columns(4)
            for c, (lab, val, sub) in zip(cols, [("Shared", o["shared"], f"in both top {k}"), ("Model only", o["only_a"], "ranked high by the model"),
                                                  ("EB only", o["only_b"], "historical black spots"), ("Jaccard overlap", f"{o['jaccard']:.2f}", "0 = disjoint, 1 = identical")]):
                c.markdown(th.h(th.kpi_card(lab, str(val), sub, "map", "accent")), unsafe_allow_html=True)
            a, b = st.columns(2, gap="medium")
            with a:
                th.section("Rank agreement", "Union of both top lists")
                u = pd.concat([top_m, top_e]).drop_duplicates("segment_id")
                stretch(st.plotly_chart, charts.rank_scatter(u), config=CFG)
            with b:
                th.section("Raw count vs EB-smoothed", "EB top segments")
                t = top_e.head(15)
                stretch(st.dataframe, pd.DataFrame({"EB rank": t.eb_rank.astype(int), "Road": t.label, "Observed": t.eb_observed,
                                                    "Exposure proxy": t.eb_exposure, "Expected": t.eb_expected, "EB estimate": t.eb_estimate,
                                                    "Model rank": t.risk_rank.astype(int)}), hide_index=True,
                        column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ("Exposure proxy", "Expected", "EB estimate")})
            th.callout("Neither is 'better'", "The model ranks segments by predicted future serious-accident risk using road context and history. "
                       "Empirical-Bayes ranks historical black spots after adjusting for exposure and regression to the mean. They capture "
                       "different information; disagreement is a prompt to look closer, not an error. Exposure here is a proxy "
                       "(road class, length, lanes) until traffic counts are supplied.", "accent")

    with t_exp:
        a, b = st.columns(2, gap="medium")
        with a:
            th.section("Most frequent top-3 drivers", "Among the 500 highest-ranked segments (from stored SHAP reasons)")
            labels = [p[0] for r in seg.head(500).itertuples() for p in (parse_reason(r.reason_1), parse_reason(r.reason_2), parse_reason(r.reason_3)) if p]
            if labels:
                stretch(st.plotly_chart, charts.driver_bars(pd.Series(labels).value_counts()), config=CFG)
            else:
                st.caption("No stored SHAP reasons.")
        with b:
            th.section("Feature importance", "LightGBM gain, from the saved model artifact")
            imp = _importance()
            if imp:
                stretch(st.plotly_chart, charts.importance_bars(*imp), config=CFG)
            else:
                st.caption("Not available - the current trainer does not save a model artifact (models/latest.joblib). The upgraded trainer does.")
        th.section("Predicted score distribution", "All scored segments")
        if not seg.empty:
            stretch(st.plotly_chart, charts.risk_histogram(seg), config=CFG)
            st.caption(BAND_NOTE)
        st.caption("SHAP explains what drove a score relative to a typical segment. It reveals associations in the data, not causes.")
