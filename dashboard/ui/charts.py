"""Plotly figure factories with one consistent, theme-aware look."""
import numpy as np
import plotly.graph_objects as go

from ..config import ACCENT, BAND_COLORS, MIN_EVENTS, SEVERITY
from .compat import is_dark

FONT = "Inter, system-ui, sans-serif"


def _base(fig, height=320, legend=False):
    dark = is_dark()
    txt, grid = ("#C9D1DC", "rgba(148,163,184,.16)") if dark else ("#344054", "rgba(100,116,139,.18)")
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=26, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, color=txt, size=12), showlegend=legend,
                      hoverlabel=dict(font_family=FONT), legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(gridcolor=grid, zeroline=False, linecolor=grid)
    fig.update_yaxes(gridcolor=grid, zeroline=False, linecolor=grid)
    return fig


def risk_histogram(seg):
    fig = go.Figure(go.Histogram(x=seg.risk_score, nbinsx=60, marker_color=ACCENT, opacity=.85,
                                 hovertemplate="score %{x:.3f}<br>%{y:,} segments<extra></extra>"))
    for name, q in (("Moderate", .80), ("High", .95), ("Critical", .99)):
        x = float(seg.risk_score.quantile(q))
        fig.add_vline(x=x, line_color=BAND_COLORS[name], line_dash="dot", line_width=1.5,
                      annotation_text=name, annotation_font_color=BAND_COLORS[name], annotation_position="top")
    fig.update_yaxes(title="Segments", type="log")
    fig.update_xaxes(title="Model score (uncalibrated)")
    return _base(fig, 330)


def band_bars(seg):
    order = ["Critical", "High", "Moderate", "Low"]
    c = seg.band.value_counts().reindex(order).fillna(0)
    fig = go.Figure(go.Bar(x=c.values, y=c.index, orientation="h", marker_color=[BAND_COLORS[b] for b in c.index],
                           hovertemplate="%{y}: %{x:,} segments<extra></extra>", text=[f"{int(v):,}" for v in c.values],
                           textposition="auto"))
    fig.update_yaxes(autorange="reversed")
    return _base(fig, 220)


def road_type_bars(seg, top=10):
    g = (seg.groupby("road_type").agg(n=("segment_id", "size"), pct=("risk_pct", "mean"), acc=("n_acc", "sum"))
         .sort_values("n", ascending=False).head(top).sort_values("pct"))
    fig = go.Figure(go.Bar(x=g.pct * 100, y=g.index, orientation="h", marker_color=ACCENT,
                           customdata=np.c_[g.n, g.acc.fillna(0)],
                           hovertemplate="%{y}<br>mean risk percentile %{x:.1f}<br>%{customdata[0]:,} segments"
                                         "<br>%{customdata[1]:,} accidents<extra></extra>"))
    fig.update_xaxes(title="Mean risk percentile (50 = average)", range=[0, 100])
    return _base(fig, 330)


def hour_profile(counts, mult, lo, hi):
    h = list(range(24))
    fig = go.Figure()
    fig.add_bar(x=h, y=counts, name="Accidents", marker_color="rgba(127,140,160,.35)", yaxis="y2",
                hovertemplate="%{x}:00 - %{y:,.0f} accidents<extra></extra>")
    fig.add_scatter(x=h + h[::-1], y=list(hi) + list(lo[::-1]), fill="toself", line=dict(width=0),
                    fillcolor="rgba(59,158,255,.18)", name="95% interval", hoverinfo="skip")
    fig.add_scatter(x=h, y=mult, mode="lines+markers", name="Hour multiplier", line=dict(color=ACCENT, width=3),
                    hovertemplate="%{x}:00 - x%{y:.2f}<extra></extra>")
    fig.add_hline(y=1, line_dash="dot", line_color="rgba(127,140,160,.6)")
    fig.update_layout(yaxis=dict(title="Relative accident rate (1 = average hour)"),
                      yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Accidents"),
                      xaxis=dict(title="Hour of day (local)", dtick=2))
    return _base(fig, 360, legend=True)


def rain_compare(stats):
    """stats: DataFrame cond, value, lo, hi, accidents, hours  (value NaN when not computable)."""
    colors, labels = [], []
    for r in stats.itertuples():
        ok = r.accidents >= MIN_EVENTS and r.value == r.value
        colors.append(ACCENT if ok else "rgba(127,140,160,.35)")
        labels.append(f"x{r.value:.2f}" if ok else "insufficient data")
    fig = go.Figure(go.Bar(x=stats.cond, y=stats.value, marker_color=colors, text=labels, textposition="outside",
                           error_y=dict(type="data", symmetric=False, array=(stats.hi - stats.value).clip(lower=0),
                                        arrayminus=(stats.value - stats.lo).clip(lower=0), color="rgba(127,140,160,.9)"),
                           customdata=np.c_[stats.accidents, stats.hours],
                           hovertemplate="%{x}<br>rate ratio %{y:.2f}<br>%{customdata[0]:,.0f} accidents in "
                                         "%{customdata[1]:,.0f} weather-hours<extra></extra>"))
    fig.add_hline(y=1, line_dash="dot", line_color="rgba(127,140,160,.6)")
    fig.update_yaxes(title="Accident rate per weather-hour vs overall", rangemode="tozero")
    return _base(fig, 340)


def severity_donut(df):
    names = [SEVERITY.get(int(s), (str(s), "#888"))[0] for s in df.severity]
    cols = [SEVERITY.get(int(s), (str(s), "#888"))[1] for s in df.severity]
    fig = go.Figure(go.Pie(labels=names, values=df.n, hole=.66, marker=dict(colors=cols), sort=False,
                           hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>", textinfo="none"))
    fig.update_layout(annotations=[dict(text=f"{int(df.n.sum()):,}<br><span style='font-size:11px'>accidents</span>",
                                        showarrow=False, font_size=20)])
    return _base(fig, 280, legend=True)


def quarterly(df):
    fig = go.Figure()
    fig.add_scatter(x=df.quarter, y=df.accidents, name="All accidents", mode="lines+markers", line=dict(color=ACCENT, width=3))
    fig.add_scatter(x=df.quarter, y=df.serious, name="Serious + fatal", mode="lines+markers",
                    line=dict(color=BAND_COLORS["High"], width=3))
    fig.update_yaxes(rangemode="tozero")
    return _base(fig, 280, legend=True)


def reliability(bins):
    x = [b["mean_pred"] for b in bins]
    y = [b["observed"] for b in bins]
    top = max(max(x), max(y), 1e-6) * 1.15
    fig = go.Figure()
    fig.add_scatter(x=[0, top], y=[0, top], mode="lines", name="Perfect calibration",
                    line=dict(color="rgba(127,140,160,.7)", dash="dot"))
    fig.add_scatter(x=x, y=y, mode="lines+markers", name="Model (held-out quarter)", line=dict(color=ACCENT, width=3),
                    marker=dict(size=[8 + min(20, b["n"] ** .5 / 8) for b in bins]),
                    customdata=[b["n"] for b in bins],
                    hovertemplate="predicted %{x:.3f}<br>observed %{y:.3f}<br>%{customdata:,} segments<extra></extra>")
    fig.update_xaxes(title="Mean predicted probability", range=[0, top])
    fig.update_yaxes(title="Observed frequency", range=[0, top])
    return _base(fig, 380, legend=True)


def rank_scatter(df):
    fig = go.Figure(go.Scattergl(x=df.risk_rank, y=df.eb_rank, mode="markers", marker=dict(color=ACCENT, size=6, opacity=.6),
                                 text=df.label, hovertemplate="%{text}<br>model rank %{x:,}<br>EB rank %{y:,}<extra></extra>"))
    fig.update_xaxes(title="Model risk rank", type="log")
    fig.update_yaxes(title="Empirical-Bayes rank", type="log")
    return _base(fig, 380)


def driver_bars(counts):
    c = counts.sort_values()
    fig = go.Figure(go.Bar(x=c.values, y=c.index, orientation="h", marker_color=ACCENT,
                           hovertemplate="%{y}: in %{x:,} segments' top-3 drivers<extra></extra>"))
    return _base(fig, max(240, 28 * len(c) + 60))


def importance_bars(names, values):
    order = np.argsort(values)
    fig = go.Figure(go.Bar(x=np.asarray(values)[order], y=np.asarray(names)[order], orientation="h", marker_color=ACCENT))
    fig.update_xaxes(title="Gain (LightGBM)")
    return _base(fig, max(260, 26 * len(names) + 60))


def metric_compare(df):
    """df: Metric, Model, Baseline (None allowed)."""
    fig = go.Figure()
    fig.add_bar(x=df.Metric, y=df.Model, name="Model", marker_color=ACCENT,
                hovertemplate="%{x}<br>model %{y:.3f}<extra></extra>")
    fig.add_bar(x=df.Metric, y=df.Baseline, name="History-only baseline", marker_color="rgba(127,140,160,.55)",
                hovertemplate="%{x}<br>baseline %{y:.3f}<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_yaxes(rangemode="tozero")
    return _base(fig, 300, legend=True)
