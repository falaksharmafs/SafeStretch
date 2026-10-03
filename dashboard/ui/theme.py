"""SafeStretch design system: CSS + small HTML components.

Surfaces are translucent greys and text inherits the active Streamlit theme, so the same CSS works in light and
dark mode. Red/orange are reserved for risk semantics, green for healthy, amber for warnings."""
import html as _html
import re

import streamlit as st

from ..config import ACCENT, BAND_COLORS

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
.stApp { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding: 0.9rem 2rem 3rem; max-width: 1640px; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, h4 { letter-spacing: -0.015em; }

:root {
  --ss-surface: rgba(127,140,160,.09); --ss-surface-2: rgba(127,140,160,.15);
  --ss-border: rgba(127,140,160,.26); --ss-muted: rgba(127,140,160,.95);
  --ss-accent: __ACCENT__; --ss-radius: 14px;
}
.ss-brand { display:flex; align-items:center; gap:12px; }
.ss-brand .name { font-weight:700; font-size:1.25rem; letter-spacing:-0.02em; line-height:1.1; }
.ss-brand .tag { font-size:.72rem; color:var(--ss-muted); letter-spacing:.08em; text-transform:uppercase; }
.ss-meta { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.ss-pill { display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; font-size:.74rem;
  border:1px solid var(--ss-border); background:var(--ss-surface); white-space:nowrap; }
.ss-pill b { font-weight:600; }
.ss-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.ss-dot.ok{background:#30A46C;box-shadow:0 0 0 3px rgba(48,164,108,.2)} .ss-dot.warn{background:#F5B83D;box-shadow:0 0 0 3px rgba(245,184,61,.2)}
.ss-dot.error{background:#E5484D;box-shadow:0 0 0 3px rgba(229,72,77,.2)} .ss-dot.off{background:#8B98A9}

.ss-section { margin: 1.1rem 0 .55rem; }
.ss-section .t { font-size:1.02rem; font-weight:650; letter-spacing:-.01em; }
.ss-section .s { font-size:.8rem; color:var(--ss-muted); margin-top:2px; }

.ss-card { border:1px solid var(--ss-border); background:var(--ss-surface); border-radius:var(--ss-radius); padding:16px 18px; }
.ss-kpi { position:relative; overflow:hidden; border:1px solid var(--ss-border); background:var(--ss-surface);
  border-radius:var(--ss-radius); padding:15px 17px 14px; min-height:118px; }
.ss-kpi::before { content:''; position:absolute; left:0; top:14px; bottom:14px; width:3px; border-radius:0 3px 3px 0; background:var(--bar,#8B98A9); }
.ss-kpi .top { display:flex; justify-content:space-between; align-items:center; color:var(--ss-muted); font-size:.74rem;
  font-weight:600; text-transform:uppercase; letter-spacing:.06em; }
.ss-kpi .val { font-size:1.9rem; font-weight:700; letter-spacing:-.025em; line-height:1.15; margin-top:6px; }
.ss-kpi .val small { font-size:.95rem; font-weight:500; color:var(--ss-muted); margin-left:4px; }
.ss-kpi .sub { font-size:.78rem; color:var(--ss-muted); margin-top:3px; }
.ss-kpi .delta { font-size:.76rem; font-weight:600; margin-top:5px; }
.ss-kpi .delta.good{color:#30A46C} .ss-kpi .delta.bad{color:#E5484D} .ss-kpi .delta.flat{color:var(--ss-muted)}
.ss-kpi svg, .ss-ico { stroke:currentColor; fill:none; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }

.ss-badge { display:inline-block; padding:2px 9px; border-radius:6px; font-size:.7rem; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase; color:#fff; }
.ss-chip { display:inline-flex; align-items:center; gap:7px; padding:5px 10px; margin:0 6px 6px 0; border-radius:9px;
  background:var(--ss-surface-2); font-size:.78rem; }
.ss-chip b { font-weight:650; }
.ss-callout { border-radius:12px; padding:11px 14px; font-size:.84rem; border:1px solid var(--ss-border);
  border-left:4px solid var(--c,#8B98A9); background:var(--ss-surface); margin:.4rem 0 .8rem; }
.ss-callout .h { font-weight:650; margin-bottom:2px; }

.ss-legend { display:flex; flex-wrap:wrap; gap:14px; font-size:.76rem; color:var(--ss-muted); align-items:center; margin:2px 0 8px; }
.ss-legend i { display:inline-block; width:22px; height:5px; border-radius:3px; margin-right:6px; vertical-align:middle; }

.ss-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; margin:6px 0 4px; }
.ss-stat { border:1px solid var(--ss-border); border-radius:11px; padding:8px 11px; background:var(--ss-surface); }
.ss-stat .k { font-size:.68rem; text-transform:uppercase; letter-spacing:.06em; color:var(--ss-muted); font-weight:600; }
.ss-stat .v { font-size:1.02rem; font-weight:650; margin-top:1px; }

.ss-driver { display:flex; gap:12px; align-items:flex-start; border:1px solid var(--ss-border); border-radius:12px;
  padding:10px 12px; margin-bottom:8px; background:var(--ss-surface); }
.ss-driver .n { flex:0 0 26px; height:26px; border-radius:8px; display:flex; align-items:center; justify-content:center;
  font-weight:700; font-size:.82rem; color:#fff; background:var(--ss-accent); }
.ss-driver .l { font-size:.74rem; text-transform:uppercase; letter-spacing:.05em; color:var(--ss-muted); font-weight:600; }
.ss-driver .v { font-size:1.05rem; font-weight:650; }
.ss-driver .c { font-size:.76rem; color:var(--ss-muted); margin-top:1px; }
.ss-bar { height:6px; border-radius:4px; background:var(--ss-surface-2); overflow:hidden; margin-top:6px; }
.ss-bar > span { display:block; height:100%; border-radius:4px; background:var(--ss-accent); }

.ss-row { display:flex; justify-content:space-between; gap:10px; padding:9px 0; border-bottom:1px solid var(--ss-border); font-size:.84rem; }
.ss-row:last-child { border-bottom:none; } .ss-row .m { color:var(--ss-muted); }

.stButton > button { border-radius:10px; border:1px solid var(--ss-border); font-weight:550; }
.stButton > button:hover { border-color: var(--ss-accent); }
button[data-baseweb="tab"] { font-weight:600; }
[data-testid="stDataFrame"] { border:1px solid var(--ss-border); border-radius:12px; overflow:hidden; }
[data-testid="stDeckGlJsonChart"], [data-testid="stPydeckChart"] { border-radius:16px; overflow:hidden; border:1px solid var(--ss-border); }
[data-testid="stPopoverBody"] { border-radius:14px; }
@media (max-width: 900px) { .block-container { padding: .6rem .8rem 2rem; } .ss-kpi .val { font-size:1.55rem; } }
</style>
""".replace("__ACCENT__", ACCENT)

ICONS = {
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "siren": '<path d="M7 18v-6a5 5 0 1 1 10 0v6"/><path d="M5 21a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2z"/><path d="M12 2v1"/><path d="M21 12h1"/><path d="M2 12h1"/><path d="M12 12v6"/>',
    "route": '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    "cloud": '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M16 14v6"/><path d="M8 14v6"/><path d="M12 16v6"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "map": '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
}
LOGO = ('<svg width="38" height="38" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="ssg" '
        'x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3B9EFF"/><stop offset="1" stop-color="#6E56CF"/>'
        '</linearGradient></defs><rect width="40" height="40" rx="11" fill="url(#ssg)"/>'
        '<path d="M8 31C16 29 14 19 21 17.5S29 13 32 9" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<circle cx="32" cy="9" r="3.2" fill="#fff"/><path d="M8 31h6" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".55"/></svg>')

TONE = {"neutral": "#8B98A9", "risk": "#F76B15", "critical": "#E5484D", "ok": "#30A46C", "warn": "#F5B83D",
        "accent": ACCENT, "muted": "#8B98A9"}


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def h(markup: str) -> str:
    """Collapse whitespace - indented HTML would otherwise be rendered as a markdown code block."""
    return re.sub(r">\s+<", "><", " ".join(markup.split()))


def render(markup: str):
    st.markdown(h(markup), unsafe_allow_html=True)


def esc(x) -> str:
    return _html.escape("" if x is None else str(x))


def icon(name: str, size: int = 18) -> str:
    return f'<svg class="ss-ico" width="{size}" height="{size}" viewBox="0 0 24 24">{ICONS.get(name, ICONS["info"])}</svg>'


def section(title: str, sub: str = ""):
    render(f'<div class="ss-section"><div class="t">{esc(title)}</div>'
           + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>")


def kpi_card(label, value, sub="", icon_name="gauge", tone="neutral", delta=None, delta_tone="flat", tip="", unit=""):
    d = f'<div class="delta {delta_tone}">{esc(delta)}</div>' if delta else ""
    u = f"<small>{esc(unit)}</small>" if unit else ""
    return (f'<div class="ss-kpi" style="--bar:{TONE.get(tone, tone)}" title="{esc(tip)}">'
            f'<div class="top"><span>{esc(label)}</span>{icon(icon_name, 16)}</div>'
            f'<div class="val">{esc(value)}{u}</div><div class="sub">{esc(sub)}</div>{d}</div>')


def band_badge(band: str) -> str:
    return f'<span class="ss-badge" style="background:{BAND_COLORS.get(band, "#8B98A9")}">{esc(band)}</span>'


def pill(text, state=None, strong=None):
    dot = f'<span class="ss-dot {state}"></span>' if state else ""
    b = f"<b>{esc(strong)}</b> " if strong else ""
    return f'<span class="ss-pill">{dot}{b}{esc(text)}</span>'


def callout(title, body, tone="accent"):
    render(f'<div class="ss-callout" style="--c:{TONE.get(tone, tone)}"><div class="h">{esc(title)}</div>{esc(body)}</div>')


def stat_grid(pairs, cols=2):
    cells = "".join(f'<div class="ss-stat"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div></div>' for k, v in pairs)
    return f'<div class="ss-grid" style="grid-template-columns:repeat({cols},1fr)">{cells}</div>'


def chips(items):
    """items: [(label, value, color_or_None)]"""
    return "".join(f'<span class="ss-chip">' + (f'<span class="ss-dot" style="background:{c}"></span>' if c else "")
                   + f'{esc(k)} <b>{esc(v)}</b></span>' for k, v, c in items)


def driver_card(rank, label, value, context=None, fill=None):
    ctx = f'<div class="c">{esc(context)}</div>' if context else ""
    bar = f'<div class="ss-bar"><span style="width:{max(2, min(100, fill * 100)):.0f}%"></span></div>' if fill is not None else ""
    return (f'<div class="ss-driver"><div class="n">{rank}</div><div style="flex:1"><div class="l">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div>{ctx}{bar}</div></div>')


def rows(pairs):
    return "".join(f'<div class="ss-row"><span class="m">{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in pairs)


def legend(items):
    """items: [(label, color)]"""
    return '<div class="ss-legend">' + "".join(f'<span><i style="background:{c}"></i>{esc(l)}</span>' for l, c in items) + "</div>"
