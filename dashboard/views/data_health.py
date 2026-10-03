import pandas as pd
import streamlit as st

from ..core import queries as Q
from ..core.health import build_checks, overall
from ..core.risk import fmt_int, human_age
from ..core.status import system_status
from ..ui import theme as th
from ..ui.compat import stretch

TONE = {"ok": "ok", "warn": "warn", "error": "critical"}
WORD = {"ok": "Healthy", "warn": "Warning", "error": "Error"}


def _ts_age(ts):
    return (human_age(pd.Timestamp(ts).to_pydatetime()), f"{pd.Timestamp(ts):%d %b %Y %H:%M}") if ts is not None else ("N/A", "")


def render():
    f = Q.health_facts()
    checks = build_checks(f)
    state = overall(checks)
    acc = Q.accident_facts()
    th.section("Data health", "Green = healthy · Amber = warning · Red = error. Each check says why.")
    th.callout({"ok": "All checks passed", "warn": "Some checks need attention", "error": "Errors found - fix before retraining"}[state],
               f"{sum(c.status == 'ok' for c in checks)} healthy · {sum(c.status == 'warn' for c in checks)} warnings · "
               f"{sum(c.status == 'error' for c in checks)} errors.", TONE[state])
    if acc.get("synthetic"):
        th.callout("Synthetic accident data", "Accident records are generated for testing; quality checks here validate structure, not truth.", "warn")

    la, lw = _ts_age(f["last_accident"]), _ts_age(f["last_weather"])
    cols = st.columns(4)
    for c, card in zip(cols, [
        th.kpi_card("Road segments", fmt_int(f["roads"]), "OpenStreetMap (local PBF)", "route", "accent"),
        th.kpi_card("Accident records", fmt_int(f["accidents"]), f"Latest {la[1]} · {la[0]}" if f["accidents"] else "None loaded", "siren", "accent"),
        th.kpi_card("Points of interest", fmt_int(f["poi"]), ", ".join(f"{k} {v}" for k, v in sorted(f["poi_counts"].items())) or "None", "map", "accent"),
        th.kpi_card("Weather records", fmt_int(f["weather"]), f"Latest {lw[1]} · {lw[0]}" if f["weather"] else "None loaded", "cloud",
                    "ok" if f["weather"] else "warn")]):
        c.markdown(th.h(card), unsafe_allow_html=True)

    th.section("Checks")
    body = ""
    for c in checks:
        body += (f'<div class="ss-row"><span style="display:flex;gap:10px;align-items:center"><span class="ss-dot {c.status}"></span>'
                 f'<b>{th.esc(c.name)}</b></span><span style="text-align:right"><b>{th.esc(c.value)}</b>'
                 f'<div class="m" style="font-size:.76rem">{th.esc(c.why)}</div></span></div>')
    th.render(f'<div class="ss-card">{body}</div>')
    if f.get("snap_p95") is not None and pd.notna(f["snap_p95"]):
        st.caption(f"Snap distance: 95% of accidents are within {f['snap_p95']:.1f} m of their matched road.")

    a, b = st.columns(2, gap="medium")
    with a:
        th.section("Services")
        th.render('<div class="ss-card">' + "".join(
            f'<div class="ss-row"><span style="display:flex;gap:10px;align-items:center"><span class="ss-dot {s}"></span>{th.esc(n)}</span>'
            f'<span class="m">{th.esc(d)}</span></div>' for n, s, d in system_status()) + "</div>")
    with b:
        th.section("Pipeline validation log", "From src.validation (if it has been run)")
        log = Q.dq_log()
        if log.empty:
            st.caption("No validation runs recorded yet. Run `python -m src.validation` (part of the upgraded project).")
        else:
            stretch(st.dataframe, log, hide_index=True)
