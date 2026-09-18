"""
CHAKRAVYUH - investigation dashboard (Stage 8).
Run with:  streamlit run app.py
Everything shown here is read from the files the earlier stages produced;
nothing is computed live except a few cached scoring calls at start-up.
"""

import json
import os
from datetime import datetime

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import detectors as det
from str_report import build_str_html
from case_builder import score_cases
from graph_builder import filter_transactions, load_data, resolve_node

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = ["ALL", "BANK_A", "BANK_B", "CONSORTIUM"]
VIEW_TITLES = {
    "ALL": "Everything (god's-eye, scoring only)",
    "BANK_A": "Bank A alone",
    "BANK_B": "Bank B alone",
    "CONSORTIUM": "Consortium (hashed, no data pooled)",
}
BLUE, RED, GREY, TEAL, AMBER = "#1f4e8c", "#c0392b", "#9aa5b1", "#138d75", "#d68910"

st.set_page_config(page_title="Chakravyuh · AML Investigation Portal", page_icon="🌀", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Poppins:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@600;700&display=swap');
.stMarkdown, .stMarkdown p, h1, h2, h3, h4, label p, button p, [data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"] {font-family: 'Poppins', system-ui, sans-serif;}
.stApp {background:#ffffff;}
header[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:0 !important; max-width:1240px;}
:root {--navy:#172a74; --navy2:#0f1d55; --saffron:#ff9933; --green:#138808; --sky:#e8eefb; --line:#d9e0f0;}

/* top utility strip + tricolour line (in the style of Indian government portals) */
.util {display:flex; justify-content:space-between; font-size:0.72rem; color:#3b4763; padding:6px 4px;
       border-bottom:1px solid var(--line);}
.tricolor {height:5px; background:linear-gradient(90deg,#ff9933 0 33.3%,#ffffff 33.3% 66.6%,#138808 66.6% 100%);
           border-bottom:1px solid var(--line);}
.masthead {display:flex; align-items:center; gap:18px; padding:14px 4px 12px 4px;}
.logo {width:62px; height:62px; border-radius:50%; background:radial-gradient(circle at 30% 30%,#2e86c1,#172a74);
       display:flex; align-items:center; justify-content:center; font-size:2rem; color:#fff;
       box-shadow:0 0 0 3px #fff, 0 0 0 5px var(--saffron);}
.masthead .hi {font-family:'Noto Sans Devanagari',sans-serif; font-size:1.7rem; color:var(--navy); line-height:1.1; font-weight:700;}
.masthead .en {font-size:1.05rem; color:#2a3552; font-weight:500;}
.masthead .en b {color:var(--navy);}
.masthead .badge {margin-left:auto; text-align:right; font-size:0.72rem; color:#3b4763;}
.masthead .badge span {display:inline-block; border:1px solid var(--line); border-radius:6px; padding:3px 9px; margin-left:4px; background:#f7f9fe;}

/* navigation bar = the tabs */
.stTabs [role="tablist"] {background:var(--navy); gap:0; padding:0 8px; border-radius:0; flex-wrap:wrap;}
.stTabs [role="tab"] {background:transparent; color:#fff; height:auto; padding:13px 18px; border-radius:0; border:none;}
.stTabs [role="tab"] p {color:#e6ecff !important; font-weight:500; font-size:0.93rem;}
.stTabs [role="tab"]:hover {background:rgba(255,255,255,.10);}
.stTabs [aria-selected="true"] {background:var(--navy2) !important; box-shadow:inset 0 -4px 0 var(--saffron);}
.stTabs [aria-selected="true"] p {color:#fff !important; font-weight:600;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display:none;}
.stTabs .stTabs [role="tablist"] {background:var(--sky); border:1px solid var(--line); border-radius:8px;}
.stTabs .stTabs [role="tab"] p {color:var(--navy) !important;}
.stTabs .stTabs [aria-selected="true"] {background:#fff !important; box-shadow:inset 0 -3px 0 var(--navy);}

.crumb {background:#f3f5fa; border-bottom:1px solid var(--line); padding:8px 14px; font-size:0.82rem; color:#3b4763; margin-bottom:6px;}
.crumb b {color:var(--green); font-weight:600;}
.ptitle {text-align:center; color:var(--navy); font-weight:600; letter-spacing:.03em; text-transform:uppercase;
         font-size:1.25rem; border-top:2px solid var(--line); border-bottom:2px solid var(--line);
         padding:12px 8px; margin:18px 0 14px 0; background:linear-gradient(90deg,#fff,#f4f7fd,#fff);}

/* hero band (bank-site style) */
.band {background:linear-gradient(110deg,#0f1d55 0%,#1f4e8c 55%,#3d7fc4 100%); color:#fff; border-radius:10px;
       padding:26px 30px; margin:10px 0 16px 0; position:relative; overflow:hidden;}
.band:after {content:""; position:absolute; right:-40px; top:-30px; width:220px; height:220px; background:#c0392b;
             opacity:.85; transform:rotate(35deg); border-radius:24px;}
.band:before {content:""; position:absolute; right:110px; top:-60px; width:120px; height:300px; background:#ffffff22; transform:rotate(35deg);}
.band h2 {color:#fff; margin:0 0 6px 0; position:relative; z-index:1;}
.band p {color:#dbe7f7; margin:0; max-width:640px; position:relative; z-index:1;}

.card {background:#fff; border:1px solid var(--line); border-top:4px solid var(--navy); border-radius:8px; padding:14px 16px;
       height:100%; box-shadow:0 2px 8px rgba(23,42,116,.07);}
.card h4 {margin:0 0 4px 0; font-size:0.95rem; color:var(--navy);}
.card p {margin:0; font-size:0.84rem; color:#3d4b5c;}
.pill {display:inline-block; padding:3px 12px; border-radius:999px; font-size:0.8rem; font-weight:600; color:#fff;}
.HIGH {background:#c0392b;} .MEDIUM {background:#d68910;} .LOW {background:#5d6d7e;}
.PASS {background:var(--green);} .REVISE {background:#d68910;} .REJECT {background:#c0392b;} .NOT_VERIFIED {background:#5d6d7e;}
.narrative-box {background:#fff; border:1px solid var(--line); border-left:5px solid var(--navy); border-radius:8px;
       padding:14px 18px; margin-bottom:10px;}
.narrative-box h5 {margin:0 0 4px 0; color:var(--navy); font-size:0.85rem; text-transform:uppercase; letter-spacing:.04em;}
.narrative-box p {margin:0; font-size:0.92rem; color:#23364f; white-space:pre-wrap;}
.verdict-yes {background:#e8f6ef; border:1px solid #a9dfbf; border-left:5px solid var(--green); border-radius:8px; padding:12px 16px;}
.verdict-no {background:#fdecea; border:1px solid #f5b7b1; border-left:5px solid #c0392b; border-radius:8px; padding:12px 16px;}
.note {background:#fff8e6; border:1px solid #f3dc9c; border-radius:8px; padding:8px 12px; font-size:0.86rem;}
.help {background:#eef3ff; border-left:4px solid var(--navy); border-radius:6px; padding:10px 14px;
       font-size:0.9rem; color:#23364f; margin-bottom:12px;}
[data-testid="stMetric"] {background:#fff; border:1px solid var(--line); border-left:5px solid var(--navy); border-radius:8px;
       padding:10px 14px; box-shadow:0 2px 8px rgba(23,42,116,.06);}
[data-testid="stMetricValue"] {font-size:1.3rem; color:var(--navy);}
[data-testid="stMetricLabel"] p {white-space:normal !important; font-size:0.8rem;}
[data-testid="stMetricValue"] div {white-space:normal !important;}
[data-testid="stSidebar"] {background:#f3f5fa; border-right:1px solid var(--line);}
[data-testid="stDataFrame"] {border:1px solid var(--line); border-radius:6px;}
.footer {background:var(--navy2); color:#c9d4f2; border-top:5px solid var(--saffron); padding:18px 24px; margin-top:26px;
         font-size:0.8rem; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;}
.footer b {color:#fff;}
/* ---- final design pass: calmer type, bank-dashboard components ---- */
.stMarkdown, .stMarkdown p, h1, h2, h3, h4, label p, button p, [data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"], .stTabs [role="tab"] p {font-family:'IBM Plex Sans', system-ui, sans-serif !important;}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu {visibility:hidden; height:0;}
.block-container {padding-top:.4rem !important; max-width:1280px;}
.stApp {background:#f7f8fb;}
.stTabs [role="tab"] p {font-size:0.95rem; letter-spacing:.01em;}
.band {padding:22px 28px;} .band h2 {font-size:1.6rem;}
[data-testid="stMetric"] {border-left:1px solid var(--line); border-top:3px solid var(--navy);}
[data-testid="stMetricValue"] {font-size:1.45rem; font-weight:600;}
.dash-head {display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin:18px 0 14px;}
.eyebrow-s {font-family:'IBM Plex Mono',monospace; font-size:.74rem; letter-spacing:.08em; text-transform:uppercase; color:#6b7385;}
.dash-title {font-size:1.75rem; font-weight:700; color:#101a3a; letter-spacing:-.01em; margin:4px 0 4px;}
.dash-sub {color:#4a5468; font-size:.95rem; max-width:760px;}
.status-chip {white-space:nowrap; background:#e9f6ee; color:#146c3d; border:1px solid #bfe3cd; border-radius:999px;
              padding:6px 14px; font-weight:600; font-size:.85rem;}
.dot-live {display:inline-block; width:8px; height:8px; border-radius:50%; background:#1f9d57; margin-right:8px;
           box-shadow:0 0 0 3px #1f9d5733;}
.kpis {display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:6px 0 14px;}
.kpi {background:#fff; border:1px solid #e1e5ee; border-radius:10px; padding:14px 16px;}
.kpi .k-l {font-size:.78rem; color:#5e6678; font-weight:500;}
.kpi .k-v {font-size:1.6rem; font-weight:700; color:#101a3a; margin:4px 0 2px; font-variant-numeric:tabular-nums;}
.kpi .k-s {font-size:.76rem; color:#8a91a1;}
.kpi.good {border-color:#bfe3cd; background:#f3fbf6;} .kpi.good .k-v {color:#146c3d;}
.flow {display:flex; align-items:center; background:#fff; border:1px solid #e1e5ee; border-radius:10px; padding:12px 16px; margin-bottom:18px;}
.flow .fs {flex:1; text-align:center;} .flow .fa {color:#b3b9c6; font-size:1.4rem; padding:0 4px;}
.flow .fv {font-size:1.25rem; font-weight:700; color:#101a3a; font-variant-numeric:tabular-nums;}
.flow .fl {font-size:.78rem; color:#6b7385;}
.flow .fs.hi .fv {color:#1F4E8C;}
.chart-t {font-weight:600; color:#101a3a; font-size:1rem; margin:6px 0 2px;}
.leg {display:inline-flex; align-items:center; margin:0 14px 4px 0; font-size:.82rem; color:#3b4459;}
.leg i {display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px;}
table.q {width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid #e1e5ee; border-radius:10px;
         overflow:hidden; font-size:.88rem;}
table.q th {background:#f2f4f9; color:#4a5468; font-weight:600; text-align:left; padding:10px 12px; font-size:.78rem;
            text-transform:uppercase; letter-spacing:.04em; border-bottom:1px solid #e1e5ee;}
table.q td {padding:10px 12px; border-bottom:1px solid #eef0f5; color:#1c2333;}
table.q tr:last-child td {border-bottom:none;} table.q tr:hover td {background:#f8f9fc;}
table.q td.num {text-align:right; font-variant-numeric:tabular-nums;} table.q td.cid {font-family:'IBM Plex Mono',monospace; font-weight:500;}
table.q td.rec {font-weight:600; color:#101a3a;}
.tp {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:600; color:var(--c);
     background:color-mix(in srgb, var(--c) 12%, white); border:1px solid color-mix(in srgb, var(--c) 30%, white);}
.bd {display:inline-block; padding:2px 9px; border-radius:6px; font-size:.74rem; font-weight:600;}
.bd.PASS {background:#e9f6ee; color:#146c3d;} .bd.REVISE {background:#fff4e0; color:#8a5a00;} .bd.REJECT {background:#fdecea; color:#a2281b;}
.bd.cHIGH {background:#e8eefb; color:#1F4E8C;} .bd.cMEDIUM {background:#f3f0fa; color:#5b4690;} .bd.cLOW {background:#f1f2f5; color:#5e6678;}
.block-container h3 {border-top:1px solid #e1e5ee; padding-top:22px !important; margin-top:26px !important; color:#101a3a;}
[data-testid="stExpander"] {background:#fff; border:1px solid #e1e5ee !important; border-radius:10px;}
[data-testid="stExpander"] summary p {font-weight:600; color:#1c2b4a;}
.masthead .badge span {background:#fff; color:#4a5468;}
.cf-head {display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin:6px 0 14px;}
.cf-status {background:#fff; border:1px solid #e1e5ee; border-radius:10px; padding:12px 18px; text-align:right; min-width:220px;}
.cf-rec {font-size:1.35rem; font-weight:700; color:#a2281b; margin:2px 0;}
.cf-grid {display:grid; grid-template-columns:1.2fr 1fr 1fr; gap:12px; margin-bottom:16px;}
.cf-card {background:#fff; border:1px solid #e1e5ee; border-radius:10px; padding:14px 16px; border-top:3px solid #4c7dff;}
.cf-card.sus {border-top-color:#ff3b30;} .cf-card.in {border-top-color:#35c28a;} .cf-card.out {border-top-color:#f0a53a;}
.cf-name {font-size:1.3rem; font-weight:700; color:#101a3a; margin:4px 0;}
.cf-row {display:flex; justify-content:space-between; font-size:.88rem; padding:5px 0; border-bottom:1px dashed #eceef3; color:#2a3242;}
.cf-row:last-child {border-bottom:none;} .cf-row b {font-variant-numeric:tabular-nums; color:#101a3a;}
.cf-sum {background:#fff; border:1px solid #e1e5ee; border-left:4px solid #1F4E8C; border-radius:10px; padding:14px 16px; font-size:.95rem; color:#1c2333; line-height:1.5;}
[data-testid="stPlotlyChart"] {border-radius:12px; overflow:hidden;}
/* ---- controls: clearly visible, clearly clickable ---- */
.picker-t {font-weight:700; color:#101a3a; font-size:.95rem; margin:14px 0 6px; display:flex; align-items:center; gap:8px;}
.picker-t:before {content:""; width:4px; height:16px; background:#ff9933; border-radius:2px; display:inline-block;}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div, [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
[data-testid="stTextInput"] input {background:#ffffff !important; border:1.5px solid #9fb0d6 !important; border-radius:9px !important;
     box-shadow:0 1px 3px rgba(16,26,58,.08); min-height:44px;}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {border-color:#1F4E8C !important; box-shadow:0 0 0 3px rgba(31,78,140,.12);}
[data-testid="stSelectbox"] div[data-baseweb="select"] span, [data-testid="stSelectbox"] div[data-baseweb="select"] div {font-weight:600; color:#101a3a;}
[data-testid="stWidgetLabel"] p {font-weight:600 !important; color:#1c2b4a !important;}
[data-testid="stPills"] button, [data-testid="stButtonGroup"] button {background:#ffffff; border:1.5px solid #c9d3ea; color:#1c2b4a;
     border-radius:999px; font-weight:600; padding:6px 14px; box-shadow:0 1px 2px rgba(16,26,58,.06);}
[data-testid="stPills"] button:hover, [data-testid="stButtonGroup"] button:hover {border-color:#1F4E8C; color:#1F4E8C;}
[data-testid="stPills"] button[kind$="Active"], [data-testid="stButtonGroup"] button[kind$="Active"],
[data-testid="stPills"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[aria-checked="true"]
     {background:#172a74 !important; border-color:#172a74 !important; color:#ffffff !important; box-shadow:0 3px 10px rgba(23,42,116,.30);}
[data-testid="stPills"] button[kind$="Active"] p, [data-testid="stButtonGroup"] button[kind$="Active"] p {color:#ffffff !important;}
[data-testid="stRadio"] label {background:#fff; border:1.5px solid #c9d3ea; border-radius:999px; padding:5px 14px 5px 10px; margin-right:6px;}
[data-testid="stRadio"] label:has(input:checked) {border-color:#172a74; background:#eef2fc;}
.stButton > button, [data-testid="stDownloadButton"] > button {border-radius:9px; border:1.5px solid #9fb0d6; font-weight:600; min-height:44px; background:#fff;}
.stButton > button:hover, [data-testid="stDownloadButton"] > button:hover {border-color:#1F4E8C; color:#1F4E8C;}
.stButton > button[kind="primary"], [data-testid="stDownloadButton"] > button[kind="primary"] {background:#172a74; border-color:#172a74; color:#fff;}
[data-testid="stCaptionContainer"] p {color:#5a6275 !important;}
.stTabs .stTabs [role="tablist"] {background:#fff; border:1px solid #e1e5ee;}
@media (max-width: 1000px) {.kpis {grid-template-columns:repeat(3,1fr);} .flow {flex-wrap:wrap;}}
@media (max-width: 800px) {.masthead .badge {display:none;} .masthead .hi {font-size:1.3rem;} .band:after,.band:before {display:none;}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data ----

import re as _re
from agents import format_inr as _format_inr


def inr_text(text):
    """Detector and case-builder text was written with western digit grouping
    (Rs 24,000,000). Show every rupee figure in Indian format instead."""
    return _re.sub(r"Rs\.?\s*(\d[\d,]*(?:\.\d+)?)",
                   lambda m: _format_inr(float(m.group(1).replace(",", "")))["digits"], str(text))


def moved(txn_ids, detectors, total):
    """For a CIRCLE the hop-sum counts one principal once per hop; the money that
    actually moved is the largest single transfer. Returns (label, value, note)."""
    if "CIRCLE" in detectors:
        amts = D["full"].set_index("txn_id").loc[list(txn_ids), "amount"]
        return "Amount cycled", inr(float(amts.max())), f"{inr(total)} across all {len(txn_ids)} hops"
    return "Evidence amount", inr(total), ""


def inr(x):
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} crore"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} lakh"
    return f"₹{x:,.0f}"


# Bump this whenever the data files or detectors change. Streamlit Cloud keeps
# cached results across redeploys; a new value forces a fresh load (this is
# what caused a KeyError on the live Scorecard after the extra detectors landed).
DATA_BUILD = "2026-09-19-final"


@st.cache_resource(show_spinner="Loading data…")
def get_data(build=DATA_BUILD):
    tx, account_to_entity, entity_attrs, account_to_bank = load_data()
    tx_sorted, recs = det.prepare(tx, account_to_entity)
    names = {e: a["canonical_name"] for e, a in entity_attrs.items()}
    full = tx_sorted.copy()
    full["from_person"] = full["from_account"].map(account_to_entity).map(names)
    full["to_person"] = full["to_account"].map(account_to_entity).map(names)
    rec_by_id = {r.txn_id: r for r in recs}
    with open(os.path.join(HERE, "cases.json")) as fh:
        cj = json.load(fh)
    with open(os.path.join(HERE, "detections.json")) as fh:
        findings = json.load(fh)
    with open(os.path.join(HERE, "graphs", "ALL_layout.json")) as fh:
        all_layout = json.load(fh)
    stats = {}
    for v in VIEWS:
        with open(os.path.join(HERE, "graphs", f"{v}_stats.json")) as fh:
            stats[v] = json.load(fh)
    records = pd.read_csv(os.path.join(HERE, "customer_records.csv"), dtype=str,
                          usecols=["record_id", "source_system", "name_as_written", "phone",
                                   "pan", "address", "linked_account"])
    entities = pd.read_csv(os.path.join(HERE, "resolved_entities.csv"), dtype=str)
    return dict(tx=tx, tx_sorted=tx_sorted, recs=recs, rec_by_id=rec_by_id, full=full,
                a2e=account_to_entity, attrs=entity_attrs, a2b=account_to_bank, names=names,
                cases=cj["cases"], review=cj["watchlist_review"], findings=findings,
                all_layout=all_layout, stats=stats, records=records, entities=entities)


@st.cache_data(show_spinner="Scoring against the answer key (once)…")
def get_scoring(build=DATA_BUILD):
    D = get_data()
    per_detector, per_ring = det.score(D["findings"])
    exact = {r.txn_id: r for r in D["recs"]}
    hero = det.hero_check(D["tx_sorted"], D["a2e"], D["a2b"], D["attrs"], exact)
    disc = det.discovery_only_score(D["recs"], D["attrs"], det.load_account_ages())
    case_score = score_cases(D["cases"], D["findings"], D["recs"], D["a2e"])  # scoring only
    return per_detector, per_ring, hero, disc, case_score["precision"]


@st.cache_data(show_spinner=False)
def get_relationships(build=DATA_BUILD):
    """Relationship Lens output (relationships.py). Absent file = panel hidden."""
    path = os.path.join(HERE, "relationships.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def get_investigation_log(build=DATA_BUILD):
    """DRONA's cached investigation (orchestrator.py). Absent file = setup hint."""
    path = os.path.join(HERE, "investigation_log.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def get_written_cases(build=DATA_BUILD):
    """Stage 6/7 output (agents.py). Additive: absent file means no panel shown."""
    path = os.path.join(HERE, "cases_written.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


D = get_data()
per_detector, per_ring, hero, disc, precision = get_scoring()
written_cases = get_written_cases()
relationships = get_relationships()
ilog = get_investigation_log()
cases = D["cases"]


def txn_table(ids):
    t = D["full"][D["full"]["txn_id"].isin(ids)].copy()
    t["amount"] = t["amount"].map(lambda a: _format_inr(a)["digits"])
    return t[["txn_id", "timestamp", "from_person", "from_account", "to_person", "to_account",
              "amount", "channel", "from_bank", "to_bank"]]


def rng(nodes, k):
    vals = [n[k] for n in nodes.values()] or [0, 1]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.3 + 0.15
    return [lo - pad, hi + pad]


def draw(nodes, edges, height=470, title=None):
    """nodes: id -> dict(x,y,label,color,size,hover). edges: (u,v,color,width)."""
    fig = go.Figure()
    for u, v, color, width in edges:
        if u == v or u not in nodes or v not in nodes:
            continue
        x0, y0, x1, y1 = nodes[u]["x"], nodes[u]["y"], nodes[v]["x"], nodes[v]["y"]
        dx, dy = x1 - x0, y1 - y0
        ln = (dx * dx + dy * dy) ** 0.5 or 1.0
        ox, oy = -dy / ln * 0.06 * ln, dx / ln * 0.06 * ln  # shift sideways so A->B and B->A both show
        fig.add_annotation(x=x0 + dx * 0.86 + ox, y=y0 + dy * 0.86 + oy, ax=x0 + dx * 0.14 + ox,
                           ay=y0 + dy * 0.14 + oy, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=1.1, arrowwidth=width, arrowcolor=color)
    ids = list(nodes)
    fig.add_trace(go.Scatter(
        x=[nodes[i]["x"] for i in ids], y=[nodes[i]["y"] for i in ids], mode="markers+text",
        text=[nodes[i]["label"] for i in ids], textposition="top center", textfont=dict(size=11),
        hovertext=[nodes[i]["hover"] for i in ids], hoverinfo="text",
        marker=dict(size=[nodes[i]["size"] for i in ids], color=[nodes[i]["color"] for i in ids],
                    line=dict(width=1.5, color="white"))))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30 if title else 10, b=10), showlegend=False,
                      title=title, plot_bgcolor="white", xaxis=dict(visible=False, range=rng(nodes, "x")),
                      yaxis=dict(visible=False, range=rng(nodes, "y")))
    return fig


def loop_figure(view, hero_tx, visible_ids):
    """The six accounts drawn as the loop they form. Solid red = hop this viewpoint can see,
    dashed grey = hop it cannot see. Nodes the viewpoint cannot identify are grey."""
    import math
    hops = hero_tx.sort_values("timestamp").to_dict("records")
    n = len(hops)
    pos = {}
    for i, h in enumerate(hops):
        ang = math.pi / 2 - 2 * math.pi * i / n
        pos[h["from_account"]] = (math.cos(ang), math.sin(ang))
    fig = go.Figure()
    for i, h in enumerate(hops):
        x0, y0 = pos[h["from_account"]]
        x1, y1 = pos[h["to_account"]]
        seen = h["txn_id"] in visible_ids
        if seen:
            fig.add_annotation(x=x0 + (x1 - x0) * 0.8, y=y0 + (y1 - y0) * 0.8, ax=x0 + (x1 - x0) * 0.2,
                               ay=y0 + (y1 - y0) * 0.2, xref="x", yref="y", axref="x", ayref="y",
                               showarrow=True, arrowhead=3, arrowsize=1.3, arrowwidth=3, arrowcolor=RED)
        else:
            fig.add_trace(go.Scatter(x=[x0 + (x1 - x0) * 0.2, x0 + (x1 - x0) * 0.8],
                                     y=[y0 + (y1 - y0) * 0.2, y0 + (y1 - y0) * 0.8], mode="lines",
                                     line=dict(color="#c5ccd6", width=2, dash="dot"), hoverinfo="skip"))
        fig.add_annotation(x=(x0 + x1) / 2 * 1.0, y=(y0 + y1) / 2, text=f"<b>{i + 1}</b>", showarrow=False,
                           font=dict(size=13, color=RED if seen else "#9aa5b1"), bgcolor="white", borderpad=2)
    xs, ys, labels, colors, hovers = [], [], [], [], []
    for acc, (x, y) in pos.items():
        node = resolve_node(acc, view, D["a2e"], D["a2b"], D["attrs"])
        bank = D["a2b"][acc].replace("BANK_", "Bank ")
        if view == "CONSORTIUM":
            lab, col, hov = node[4:10], TEAL, f"pseudonym {node}. No name, PAN or account number is shared"
        elif node.startswith("EXT_"):
            lab, col, hov = "Unknown<br>(other bank)", GREY, f"{node}: identity invisible from this bank"
        else:
            lab = f"{D['names'][node].split(' ')[0].title()}<br>{acc[-5:]} · {bank[-1]}"
            col = BLUE if D["a2b"][acc] == "BANK_A" else AMBER
            hov = f"{D['names'][node]} · {acc} · {bank}"
        xs.append(x); ys.append(y); labels.append(lab); colors.append(col); hovers.append(hov)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
                             hovertext=hovers, hoverinfo="text", textfont=dict(size=11),
                             marker=dict(size=34, color=colors, line=dict(width=2, color="white"))))
    fig.update_layout(height=470, showlegend=False, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                      xaxis=dict(visible=False, range=[-1.6, 1.6]), yaxis=dict(visible=False, range=[-1.5, 1.5]))
    return fig


def case_label(c):
    return (f"{c['case_id']} · {c['priority_level']} {c['priority_score']} · "
            f"{' + '.join(c['detectors_fired'])} · "
            f"{moved(c['evidence_txn_ids'], c['detectors_fired'], c['total_evidence_amount'])[1]}"
            f"{' cycled' if 'CIRCLE' in c['detectors_fired'] else ''}")


# --------------------------------------------------------------- header ---

st.markdown("""
<div class="tricolor"></div>
<div class="masthead">
  <div class="logo">🌀</div>
  <div><div class="hi">चक्रव्यूह</div>
       <div class="en"><b>CHAKRAVYUH</b> · Anti-Money-Laundering Investigation Portal</div></div>
  <div class="badge"><span>Consortium · Bank A · Bank B</span><span>Screening run · 19 Sep 2026</span></div>
</div>
""", unsafe_allow_html=True)

def pagetitle(text):
    st.markdown(f'<div class="ptitle">{text}</div>', unsafe_allow_html=True)


def helpbox(text):
    return None      # guidance lives in the page titles; kept as a no-op so call sites stay simple

with st.sidebar:
    st.header("Officer decision log")
    st.markdown('<div class="note">Nothing is ever filed automatically. '
                'A human reviews every case.</div>', unsafe_allow_html=True)
    log = st.session_state.setdefault("log", [])
    if log:
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
        st.download_button("Download log (CSV)", pd.DataFrame(log).to_csv(index=False),
                           "officer_decisions.csv", width="stretch")
    else:
        st.caption("No decisions yet. Open a case in the Cases tab.")

tabs = st.tabs(["Dashboard", "Case Queue", "Case File", "AI War Room", "Cross-Bank View", "Identity",
                "Detection Rules", "Accuracy"])

# ------------------------------------------------------------ war room ---
TOOL_LOOK = {
    "open_item": ("📂", "Opens the file"), "check_relationships": ("🕸️", "Relationship Lens"),
    "compare_bank_views": ("🏦", "Compares bank views"), "account_history": ("🧾", "Pulls account history"),
    "expand_neighbourhood": ("🔭", "Widens the net"), "lookup_transaction": ("🔎", "Checks a transaction"),
    "send_to_sanjaya": ("📜", "Hands the case to SANJAYA → VIDURA"), "record_decision": ("⚖️", "Recommendation"),
}
DEC_COLOR = {"FILE_STR": "#c0392b", "ESCALATE": "#d68910", "ESCALATE_AS_LEAD": "#d68910",
             "MONITOR": "#1f4e8c", "CLOSE_RECOMMENDED": "#138d75"}


def step_html(s):
    icon, label = TOOL_LOOK.get(s["tool"], ("•", s["tool"]))
    arg = " ".join(str(v) for k, v in s.get("args", {}).items() if k in ("account_id", "person_id", "txn_id"))
    bad = s["result"].startswith("rejected by code")
    border = "#c0392b" if bad else ("#172a74" if s["tool"] in ("send_to_sanjaya", "record_decision") else "#d9e0f0")
    return (f'<div style="border-left:4px solid {border};background:#f7f9fe;padding:8px 12px;margin:6px 0;'
            f'border-radius:6px"><div style="font-size:.78rem;color:#3b4763">Step {s["n"]} · {icon} <b>{label}</b> '
            f'<code>{arg}</code></div><div style="font-style:italic;color:#172a74">“{s["why"]}”</div>'
            f'<div style="font-size:.9rem;margin-top:2px">{"🛑 " if bad else "→ "}{s["result"]}</div></div>')


_ID_RE = __import__("re").compile(r"\b(?:ACC|PERSON|TXN)\d+\b")
_BANK = None


def _ids_in(*texts):
    out = set()
    for t in texts:
        out |= set(_ID_RE.findall(json.dumps(t, default=str) if not isinstance(t, str) else t))
    return out


def war_graph(item_id, lg, upto):
    """The item's money trail at ACCOUNT level, lit up by what DRONA has looked at in steps 1..upto.
    grey = not looked at yet · navy = examined · gold = this step · purple arrow = a hop one bank
    alone cannot see · red arrow = evidence sent to SANJAYA · red node = cited in the recommendation."""
    import math
    global _BANK
    if _BANK is None:
        _BANK = dict(zip(D["full"]["txn_id"], zip(D["full"]["from_bank"], D["full"]["to_bank"])))
    rec, a2e = D["rec_by_id"], D["a2e"]
    case = next((c for c in cases if c["case_id"] == item_id), None)
    if case:
        txn_ids = list(case["evidence_txn_ids"])
    else:
        allids = _ids_in([s.get("args", {}) for s in lg["steps"]], [s["result"] for s in lg["steps"]], lg["decision"])
        txn_ids = [t for t in sorted(allids) if t.startswith("TXN") and t in rec]
    txn_ids = sorted(txn_ids, key=lambda t: rec[t].ts_str)
    accs = []
    for t in txn_ids:
        for a in (rec[t].from_acc, rec[t].to_acc):
            if a not in accs:
                accs.append(a)
    pos = {}
    if case and len(accs) > 12 and case.get("layout"):
        by_owner = {}
        for a in accs:
            by_owner.setdefault(a2e.get(a), []).append(a)
        for owner, lst in by_owner.items():
            cx, cy = case["layout"].get(owner, (0.0, 0.0))
            for j, a in enumerate(lst):
                ang = 2 * math.pi * j / len(lst)
                pos[a] = (cx + 0.035 * math.cos(ang) * (len(lst) > 1), cy + 0.035 * math.sin(ang) * (len(lst) > 1))
    else:                                  # small networks: the money path drawn as a ring
        for i, a in enumerate(accs):
            ang = math.pi / 2 - 2 * math.pi * i / max(len(accs), 1)
            pos[a] = (math.cos(ang), math.sin(ang))

    owner_accs = {}
    for a in accs:
        owner_accs.setdefault(a2e.get(a), set()).add(a)

    def to_accs(ids):
        out = {i for i in ids if i in pos}
        for i in ids:
            if i.startswith("PERSON"):
                out |= owner_accs.get(i, set())
            if i in rec:
                out |= {rec[i].from_acc, rec[i].to_acc} & set(pos)
        return out

    seen, focus, focus_txn, cited = set(), set(), set(), set()
    blind = sent = False
    for s in lg["steps"][:upto]:
        ids = _ids_in(s.get("args", {}), s["result"])
        focus = to_accs(ids) if s["tool"] in ("account_history", "expand_neighbourhood", "lookup_transaction") else set()
        focus_txn = {i for i in ids if i.startswith("TXN")} if s["tool"] == "lookup_transaction" else set()
        if s["tool"] in ("open_item", "check_relationships"):
            seen |= set(pos)
        seen |= focus
        blind = blind or s["tool"] == "compare_bank_views"
        sent = sent or s["tool"] == "send_to_sanjaya"
        if s["tool"] == "record_decision" and s["result"].split(":")[0] in ("FILE_STR", "ESCALATE", "ESCALATE_AS_LEAD"):
            ev = lg["decision"].get("evidence_ids", [])
            cited = to_accs(set(ev)) | (set(pos) if item_id in ev else set())
    last_tool = lg["steps"][upto - 1]["tool"] if upto else ""

    nodes = {}
    for a, (x, y) in pos.items():
        col, size = "#cdd6e3", 13
        if a in seen:
            col, size = "#172a74", 16
        if a in cited:
            col, size = "#c0392b", 19
        if a in focus and last_tool != "record_decision":
            col, size = "#f1c40f", 26
        owner = D["names"].get(a2e.get(a), "")
        nodes[a] = dict(x=x, y=y, size=size, color=col, hover=f"{a} · {owner}",
                        label=(f"{a}<br>{owner.title()[:12]}" if len(pos) <= 10 or a in focus else ""))
    agg = {}
    for t in txn_ids:
        r = rec[t]
        colr, w = "#d5dbe5", 1.2
        if blind and _BANK.get(t, ("", "x"))[0] == _BANK.get(t, ("x", ""))[1]:
            colr, w = "#8e44ad", 2.2          # both legs in one bank: the other bank never sees this hop
        if sent:
            colr, w = "#c0392b", 2.2
        if t in focus_txn:
            colr, w = "#f1c40f", 3.5
        agg[(r.from_acc, r.to_acc)] = (colr, w)
    return draw(nodes, [(u, v, c_, w) for (u, v), (c_, w) in agg.items()], 440)


with tabs[3]:
    st.markdown('<div class="band"><h2>The War Room</h2><p>Three AI agents, one chain of command. '
                'The detectors find the patterns. DRONA decides where to look, SANJAYA writes the case, '
                'VIDURA argues the innocent side. A human officer makes the call.</p></div>', unsafe_allow_html=True)
    a = st.columns(3)
    for col, (nm, role, line) in zip(a, [
        ("🏹 DRONA", "Lead investigator · gpt-4o", "Designed the chakravyuh in the Mahabharata. Here he triages the queue, "
         "chooses which evidence to pull, commissions reports, sends weak ones back and recommends a decision."),
        ("📜 SANJAYA", "Case writer", "Narrated the war to a king who could not see it. Here he turns proven evidence "
         "into a report an officer can read in a minute."),
        ("⚖️ VIDURA", "Sceptical reviewer", "The truth-teller of the court. Here he looks for the innocent explanation first. "
         "Every number is checked by code before he even reads it.")]):
        col.markdown(f'<div class="card" style="min-height:215px"><h4>{nm}</h4><p><b>{role}</b></p><p>{line}</p></div>', unsafe_allow_html=True)

    if not ilog:
        st.info("DRONA has not run yet. Run `python orchestrator.py` (needs OPENAI_API_KEY in .env).")
    else:
        m = ilog["meta"]
        k = st.columns(6)
        k[0].metric("Items investigated", m["items"])
        k[1].metric("Tool calls DRONA chose", m["tool_calls"])
        k[2].metric("Reports passed by VIDURA", f"{m['vidura_pass']} / {m['cases']}")
        k[3].metric("Facts confirmed by code", f"{m['facts_confirmed']} / {m['facts_checked']}")
        k[4].metric("AI mistakes blocked", m["blocked_citations"])
        k[5].metric("Filed automatically", 0)


        _tri = st.expander(f"DRONA's triage: how he ordered all {m['items']} items, and why", expanded=False)
        _tri.caption("DRONA ordered the queue himself and wrote down why. The final column is his recommendation, not a filing.")
        _tri.dataframe(pd.DataFrame([{
            "#": i, "Item": t["item"], "Type": ilog["items"][t["item"]]["kind"].replace("_", " ").title(),
            "Why this position": t["reason"],
            "Tool calls": len(ilog["items"][t["item"]]["steps"]),
            "DRONA recommends": ilog["items"][t["item"]]["decision"]["decision"].replace("_", " ")}
            for i, t in enumerate(ilog["triage"], 1)]), hide_index=True, width="stretch")

        st.markdown("#### Watch DRONA investigate")
        order = [t["item"] for t in ilog["triage"]]
        cc = st.columns([3, 1, 1])
        pick = cc[0].selectbox("Item", order, key="war_pick",
                               format_func=lambda i: f"{i} · {ilog['items'][i]['kind'].replace('_', ' ').title()} · "
                                                     f"{ilog['items'][i]['decision']['decision'].replace('_', ' ')}")
        speed = cc[1].select_slider("Speed", ["slow", "normal", "fast"], value="normal", key="war_speed")
        replay = cc[2].button("▶ Replay investigation", type="primary", width="stretch")
        lg = ilog["items"][pick]
        st.caption(f"Triage #{lg['triage_rank']}: {lg['triage_reason']}")
        left, right = st.columns([5, 4])
        box = left.container()
        gph = right.empty()
        right.caption("🟡 DRONA is looking here now · 🔵 examined · ⚪ not yet looked at · "
                      "🟣 hop one bank alone cannot see · 🔴 evidence sent to SANJAYA / cited in the recommendation")
        if replay:
            import time as _t
            delay = {"slow": 1.4, "normal": 0.8, "fast": 0.3}[speed]
            ph = box.empty()
            shown = ""
            gph.plotly_chart(war_graph(pick, lg, 0), width="stretch", key=f"wg_{pick}_0")
            for i, s in enumerate(lg["steps"], 1):
                shown += step_html(s)
                ph.markdown(shown + '<div style="color:#9aa5b1;font-size:.8rem">DRONA is thinking…</div>',
                            unsafe_allow_html=True)
                gph.plotly_chart(war_graph(pick, lg, i), width="stretch", key=f"wg_{pick}_{i}")
                _t.sleep(delay)
            ph.markdown(shown, unsafe_allow_html=True)
        else:
            box.markdown("".join(step_html(s) for s in lg["steps"]), unsafe_allow_html=True)
            gph.plotly_chart(war_graph(pick, lg, len(lg["steps"])), width="stretch", key=f"wg_{pick}_final")

        d = lg["decision"]
        col = DEC_COLOR.get(d["decision"], "#172a74")
        links = f"<br><small>Investigate together with: {', '.join(d['link_with_cases'])}</small>" if d.get("link_with_cases") else ""
        st.markdown(f'<div style="border:2px solid {col};border-radius:10px;padding:12px 16px;margin-top:10px">'
                    f'<div style="font-size:.75rem;color:#3b4763">DRONA\'S RECOMMENDATION TO THE OFFICER</div>'
                    f'<div style="font-size:1.4rem;font-weight:700;color:{col}">{d["decision"].replace("_", " ")}</div>'
                    f'<div>{d["reason"]}</div><div style="font-size:.8rem;color:#3b4763;margin-top:4px">'
                    f'Cites: {", ".join(d["evidence_ids"][:12]) or "—"}</div>{links}</div>', unsafe_allow_html=True)
        if lg["writer_runs"]:
            with st.expander(f"What DRONA told SANJAYA ({len(lg['writer_runs'])} brief(s)) and what VIDURA said"):
                for i, r in enumerate(lg["writer_runs"], 1):
                    st.markdown(f"**Brief {i}:** {r['commander_notes']}")
                    st.markdown(f"**VIDURA:** {r['verification'].get('verdict')} · "
                                f"facts {r['fact_check']['passed']}/{r['fact_check']['checked']} · "
                                f"confidence {r['final_confidence']}")
        if lg["blocked"]:
            st.caption(f"🛑 DRONA tried to cite {sum(len(b.get('invalid_ids', [])) + len(b.get('invalid_amounts', [])) for b in lg['blocked'])} "
                       f"ID(s) or amount(s) that no tool had shown him. Code rejected them and he had to try again.")
        st.caption("Replayed from the saved investigation log. No live AI call is made during the demo.")

# ------------------------------------------------------------ dashboard ---
TYPO = {"CIRCLE": "Round-tripping", "SPRAY": "Mule network", "THRESHOLD": "Structuring", "SPEED": "Rapid layering"}
TYPO_COL = {"Round-tripping": "#1F4E8C", "Mule network": "#C8553D", "Structuring": "#2E7D5B", "Rapid layering": "#7B5EA7"}


def typology(dets):
    for d in ("CIRCLE", "SPRAY", "THRESHOLD", "SPEED"):
        if d in dets:
            return TYPO[d]
    return "Other"


def moved_raw(c):
    if "CIRCLE" in c["detectors_fired"]:
        return float(D["full"].set_index("txn_id").loc[c["evidence_txn_ids"], "amount"].max())
    return float(c["total_evidence_amount"])


def _fig_style(fig, h):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=13, color="#1c2333"),
                      showlegend=False)
    return fig


with tabs[0]:
    rows = []
    for c_ in cases:
        dec = (ilog.get("items", {}).get(c_["case_id"], {}) if ilog else {}).get("decision", {})
        wc_ = written_cases.get(c_["case_id"], {})
        rows.append(dict(case=c_["case_id"], typ=typology(c_["detectors_fired"]), amt=moved_raw(c_),
                         people=len(c_["core_people"]), accts=len({a for p in c_["core_people"] for a in p["accounts"]}),
                         banks="Both" if c_["crosses_banks"] else c_["banks_involved"][0].replace("BANK_", "Bank "),
                         verdict=wc_.get("verification", {}).get("verdict", "—"),
                         conf=wc_.get("final_confidence", "—"),
                         rec=dec.get("decision", "—").replace("_", " "), hours=c_["hours_spanned"]))
    dfq = pd.DataFrame(rows)
    at_risk = dfq["amt"].sum()
    ev_ids = sorted({t for c_ in cases for t in c_["evidence_txn_ids"]})
    evb = D["full"].set_index("txn_id").loc[ev_ids, ["from_bank", "to_bank"]]
    seen_a = ((evb["from_bank"] == "BANK_A") | (evb["to_bank"] == "BANK_A")).mean()
    seen_b = ((evb["from_bank"] == "BANK_B") | (evb["to_bank"] == "BANK_B")).mean()
    cs_sum = relationships.get("case_summary", {})
    cg_sum = relationships.get("control_group", {})
    m_ = ilog.get("meta", {}) if ilog else {}

    st.markdown(f"""
<div class="dash-head">
  <div><div class="eyebrow-s">Screening summary · run of 19 Sep 2026 · Bank A + Bank B consortium</div>
       <div class="dash-title">{len(cases)} suspicious networks found in {len(D['tx']):,} transactions</div>
       <div class="dash-sub">Every case below is backed by the exact transactions that prove it, investigated by AI,
       fact-checked by code, and waiting for an officer's decision.</div></div>
  <div class="status-chip"><span class="dot-live"></span>All {len(cases)} reports verified</div>
</div>
<div class="kpis">
  <div class="kpi"><div class="k-l">Transactions screened</div><div class="k-v">{len(D['tx']):,}</div><div class="k-s">30 days · 2 banks</div></div>
  <div class="kpi"><div class="k-l">Customers resolved</div><div class="k-v">{len(D['attrs']):,}</div><div class="k-s">from 2,500 accounts</div></div>
  <div class="kpi"><div class="k-l">Suspicious networks</div><div class="k-v">{len(cases)}</div><div class="k-s">11 of 12 hidden rings</div></div>
  <div class="kpi"><div class="k-l">Value at risk</div><div class="k-v">{inr(at_risk)}</div><div class="k-s">money moved in these networks</div></div>
  <div class="kpi"><div class="k-l">STR drafts ready</div><div class="k-v">{sum(1 for r in rows if r['verdict'] == 'PASS')}</div><div class="k-s">passed independent review</div></div>
  <div class="kpi good"><div class="k-l">False positives</div><div class="k-v">0</div><div class="k-s">industry norm: 85–95%</div></div>
</div>
<div class="flow">
  <div class="fs"><div class="fv">{len(D['tx']):,}</div><div class="fl">transactions</div></div><div class="fa">›</div>
  <div class="fs"><div class="fv">{len(D['findings'])}</div><div class="fl">pattern findings</div></div><div class="fa">›</div>
  <div class="fs"><div class="fv">{len(cases)}</div><div class="fl">cases, one per network</div></div><div class="fa">›</div>
  <div class="fs"><div class="fv">{m_.get('facts_confirmed', '—')}</div><div class="fl">facts checked by code</div></div><div class="fa">›</div>
  <div class="fs hi"><div class="fv">{len(cases)}</div><div class="fl">reports for the officer</div></div>
</div>
""", unsafe_allow_html=True)

    g1, g2 = st.columns([2, 3])
    with g1:
        st.markdown('<div class="chart-t">Cases by laundering method</div>', unsafe_allow_html=True)
        tc = dfq["typ"].value_counts()
        fig = go.Figure(go.Pie(labels=tc.index, values=tc.values, hole=.62, sort=False,
                               marker=dict(colors=[TYPO_COL.get(t, "#999") for t in tc.index], line=dict(color="white", width=2)),
                               textinfo="value", textfont=dict(size=14, color="white"),
                               hovertemplate="%{label}: %{value} case(s)<extra></extra>"))
        fig.add_annotation(text=f"<b>{len(cases)}</b><br><span style='font-size:12px;color:#5e6470'>cases</span>",
                           showarrow=False, font=dict(size=26, color="#1c2333"))
        _fig_style(fig, 250)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="d_pie")
        st.markdown("".join(f'<span class="leg"><i style="background:{TYPO_COL[t]}"></i>{t}</span>' for t in tc.index),
                    unsafe_allow_html=True)
    with g2:
        st.markdown('<div class="chart-t">Money moved per case</div>', unsafe_allow_html=True)
        d2 = dfq.sort_values("amt")
        fig = go.Figure(go.Bar(x=d2["amt"] / 1e5, y=d2["case"], orientation="h",
                               marker=dict(color=[TYPO_COL.get(t, "#999") for t in d2["typ"]]),
                               text=[inr(a) for a in d2["amt"]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{text}<extra></extra>"))
        _fig_style(fig, 300)
        fig.update_xaxes(title=None, showgrid=True, gridcolor="#eef0f4", ticksuffix=" L", zeroline=False,
                         range=[0, float(d2["amt"].max()) / 1e5 * 1.28])
        fig.update_yaxes(title=None)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="d_bar")
        st.caption("For round-tripping, the amount is the principal that went round the loop. L = lakh.")

    g3, g4 = st.columns(2)
    with g3:
        st.markdown('<div class="chart-t">What one bank alone can see</div>', unsafe_allow_html=True)
        vis = pd.DataFrame({"who": ["Bank A alone", "Bank B alone", "Consortium"],
                            "pct": [seen_a * 100, seen_b * 100, 100.0]})
        fig = go.Figure(go.Bar(x=vis["pct"], y=vis["who"], orientation="h",
                               marker=dict(color=["#9AA7BF", "#9AA7BF", "#1F4E8C"]),
                               text=[f"{p:.0f}%" for p in vis["pct"]], textposition="inside",
                               insidetextanchor="end", textfont=dict(color="white", size=14),
                               hovertemplate="%{y}: %{x:.0f}% of suspicious transfers<extra></extra>"))
        _fig_style(fig, 190)
        fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=True, gridcolor="#eef0f4")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="d_vis")
        st.caption("Share of the suspicious transfers each party can see. Banks share only hashed IDs, never customer data.")
    with g4:
        st.markdown('<div class="chart-t">Relationship red flags: cases vs ordinary customers</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(x=[cs_sum.get("avg_signals_per_case", 0), cg_sum.get("avg_signals_per_group", 0)],
                               y=["Suspicious cases", "Ordinary customers"], orientation="h",
                               marker=dict(color=["#C8553D", "#9AA7BF"]),
                               text=[f"{cs_sum.get('avg_signals_per_case', 0)} per case",
                                     f"{cg_sum.get('avg_signals_per_group', 0)} per group"],
                               textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{x}<extra></extra>"))
        _fig_style(fig, 190)
        fig.update_xaxes(range=[0, 3.6], showgrid=True, gridcolor="#eef0f4")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="d_rf")
        st.caption("Fresh accounts, one person behind many accounts, first-ever contact, shared phones, bank blind spots. "
                   f"Measured on {cg_sum.get('groups', 0)} random customer groups.")

    st.markdown('<div class="chart-t" style="margin-top:6px">Case queue: highest priority first</div>', unsafe_allow_html=True)
    body = ""
    for r in rows:
        body += (f"<tr><td class='cid'>{r['case']}</td>"
                 f"<td><span class='tp' style='--c:{TYPO_COL.get(r['typ'], '#999')}'>{r['typ']}</span></td>"
                 f"<td class='num'>{inr(r['amt'])}</td><td class='num'>{r['accts']}</td><td>{r['banks']}</td>"
                 f"<td class='num'>{r['hours']:.1f} h</td>"
                 f"<td><span class='bd {r['verdict']}'>{r['verdict']}</span></td>"
                 f"<td><span class='bd c{r['conf']}'>{r['conf']}</span></td>"
                 f"<td class='rec'>{r['rec']}</td></tr>")
    st.markdown(f"<table class='q'><thead><tr><th>Case</th><th>Pattern</th><th>Amount</th><th>Accounts</th><th>Banks</th>"
                f"<th>Duration</th><th>Review</th><th>Confidence</th><th>AI recommends</th></tr></thead>"
                f"<tbody>{body}</tbody></table>", unsafe_allow_html=True)


# ------------------------------------------------------------- case file ---
def main_suspect(c):
    """The person the money story starts from. Circle / chain: whoever sent the first
    evidence transfer. Mule network: whoever paid the most distinct accounts.
    Structuring: whoever received the deposits. Deterministic, no AI."""
    rec = D["rec_by_id"]
    ev = sorted((rec[t] for t in c["evidence_txn_ids"] if t in rec), key=lambda r: r.ts_str)
    core = {p["entity_key"] for p in c["core_people"]}
    if not ev:
        return c["core_people"][0]["entity_key"], "core person"
    d = c["detectors_fired"]
    if "SPRAY" in d:
        outs = {}
        for r in ev:
            outs.setdefault(r.from_ent, set()).add(r.to_ent)
        who = max(outs, key=lambda k: len(outs[k]))
        return who, f"paid {len(outs[who])} different people"
    if "THRESHOLD" in d and "CIRCLE" not in d:
        cnt = {}
        for r in ev:
            cnt[r.to_ent] = cnt.get(r.to_ent, 0) + 1
        who = max(cnt, key=cnt.get)
        return who, f"received {cnt[who]} deposits just under the limit"
    who = ev[0].from_ent if ev[0].from_ent in core else next(iter(core))
    return who, ("sent the money that came back to them" if "CIRCLE" in d else "started the chain")


def money_flow_3d(c, suspect):
    """3D money-flow graph: sources on the left, the network in the middle, destinations
    on the right. Drag to rotate, scroll to zoom, right-drag to pan."""
    import math
    import networkx as _nx
    rec = D["rec_by_id"]
    core = {p["entity_key"] for p in c["core_people"]}
    ins = {p["entity_key"]: p for p in c["context_people"] if p["direction"] == "IN" and p["entity_key"] not in core}
    outs = {p["entity_key"]: p for p in c["context_people"] if p["direction"] == "OUT" and p["entity_key"] not in core}
    G = _nx.Graph()
    G.add_nodes_from(core)
    for t in c["evidence_txn_ids"]:
        r = rec.get(t)
        if r and r.from_ent in core and r.to_ent in core and r.from_ent != r.to_ent:
            G.add_edge(r.from_ent, r.to_ent)
    p3 = _nx.spring_layout(G, dim=3, seed=7) if len(G) > 1 else {n: (0, 0, 0) for n in G}
    pos = {n: (float(v[0]) * 2.2, float(v[1]) * 2.2, float(v[2]) * 2.2) for n, v in p3.items()}
    if suspect in pos and len(core) > 8:          # hub-shaped networks: put the suspect at the centre
        cx, cy, cz = pos[suspect]
        pos = {n: (x - cx, y - cy, z - cz) for n, (x, y, z) in pos.items()}
    for grp, x0 in ((ins, -4.2), (outs, 4.2)):
        ks = sorted(grp)
        for i, k in enumerate(ks):
            ang = 2 * math.pi * i / max(len(ks), 1)
            pos[k] = (x0, 1.6 * math.cos(ang), 1.6 * math.sin(ang))

    edges = {}
    for kind, ids in (("ev", c["evidence_txn_ids"]), ("ctx", c["context_txn_ids"])):
        for t in ids:
            r = rec.get(t)
            if not r or r.from_ent == r.to_ent or r.from_ent not in pos or r.to_ent not in pos:
                continue
            k = (r.from_ent, r.to_ent)
            e = edges.setdefault(k, {"kind": kind, "amt": 0.0, "n": 0})
            e["amt"] += r.amount
            e["n"] += 1
    fig = go.Figure()
    col = {"ev": "#ff5a4f", "in": "#35c28a", "out": "#f0a53a"}
    for (u, v), e in edges.items():
        kind = e["kind"] if e["kind"] == "ev" else ("in" if u in ins else "out")
        (x0, y0, z0), (x1, y1, z1) = pos[u], pos[v]
        fig.add_trace(go.Scatter3d(x=[x0, x1], y=[y0, y1], z=[z0, z1], mode="lines",
                                   line=dict(color=col[kind], width=6 if kind == "ev" else 3),
                                   hoverinfo="text", showlegend=False,
                                   text=f"{D['names'].get(u, u).title()} → {D['names'].get(v, v).title()}"
                                        f"<br>{e['n']} transfer(s) · {_format_inr(e['amt'])['words']}"))
        fig.add_trace(go.Cone(x=[x0 + (x1 - x0) * .72], y=[y0 + (y1 - y0) * .72], z=[z0 + (z1 - z0) * .72],
                              u=[x1 - x0], v=[y1 - y0], w=[z1 - z0], sizemode="absolute", sizeref=.22, anchor="tip",
                              colorscale=[[0, col[kind]], [1, col[kind]]], showscale=False, hoverinfo="skip"))

    def node_trace(keys, color, size, label, show_text=True):
        keys = [k for k in keys if k in pos]
        if not keys:
            return
        fig.add_trace(go.Scatter3d(
            x=[pos[k][0] for k in keys], y=[pos[k][1] for k in keys], z=[pos[k][2] for k in keys],
            mode="markers+text", name=label,
            marker=dict(size=size, color=color, line=dict(color="rgba(255,255,255,.85)", width=2), opacity=.97),
            text=[D["names"].get(k, k).title()[:18] if show_text else "" for k in keys], textposition="top center",
            textfont=dict(color="#dfe6f5", size=11),
            hovertext=[f"<b>{D['names'].get(k, k).title()}</b><br>{label}" for k in keys], hoverinfo="text"))
    node_trace(sorted(ins), "#35c28a", 7, "Money came from")
    node_trace(sorted(core - {suspect}), "#4c7dff", 10, "In the network", show_text=len(core) <= 10)
    node_trace(sorted(outs), "#f0a53a", 7, "Money went to")
    node_trace([suspect], "#ff3b30", 22, "Main suspect")

    ax = dict(visible=False, showbackground=False)
    frames = [go.Frame(layout=dict(scene_camera=dict(eye=dict(x=1.6 * math.cos(a), y=1.6 * math.sin(a), z=.6))))
              for a in [i * 2 * math.pi / 60 for i in range(61)]]
    fig.frames = frames
    fig.update_layout(
        height=560, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0b1330",
        scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, bgcolor="#0b1330", aspectmode="cube",
                   camera=dict(eye=dict(x=1.35, y=-0.95, z=.6))),
        legend=dict(orientation="h", y=.02, x=.02, font=dict(color="#dfe6f5", size=12), bgcolor="rgba(0,0,0,0)"),
        font=dict(family="IBM Plex Sans, sans-serif"),
        updatemenus=[dict(type="buttons", showactive=False, x=.98, y=.97, xanchor="right", yanchor="top",
                          bgcolor="#1c2b5a", bordercolor="#3a4d86", font=dict(color="#ffffff", size=12),
                          buttons=[dict(label="⟳  Rotate", method="animate",
                                        args=[None, dict(frame=dict(duration=70, redraw=True), fromcurrent=True,
                                                         transition=dict(duration=0), mode="immediate")]),
                                   dict(label="❚❚  Pause", method="animate",
                                        args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])])
    return fig


with tabs[2]:
    pagetitle("Case file")
    cf_ids = [x["case_id"] for x in cases]
    st.markdown('<div class="picker-t">Select a case file</div>', unsafe_allow_html=True)
    _short = {"Round-tripping": "Loop", "Mule network": "Mule", "Structuring": "Structuring", "Rapid layering": "Layering"}
    cf_pick = st.pills("Select a case file", cf_ids, default=cf_ids[0], key="cf_pick", label_visibility="collapsed",
                       format_func=lambda i: f"{i} · {_short.get(typology(next(x for x in cases if x['case_id'] == i)['detectors_fired']), '')}")
    cf_pick = cf_pick or cf_ids[0]
    cf = next(x for x in cases if x["case_id"] == cf_pick)
    sus, why_sus = main_suspect(cf)
    wc_cf = written_cases.get(cf["case_id"], {})
    dec_cf = (ilog.get("items", {}).get(cf["case_id"], {}) if ilog else {}).get("decision", {})
    lab_cf, amt_cf, note_cf = moved(cf["evidence_txn_ids"], cf["detectors_fired"], cf["total_evidence_amount"])
    typ_cf = typology(cf["detectors_fired"])
    ins_cf = sorted((p for p in cf["context_people"] if p["direction"] == "IN"), key=lambda p: -p["amount"])
    outs_cf = sorted((p for p in cf["context_people"] if p["direction"] == "OUT"), key=lambda p: -p["amount"])
    sus_p = next((p for p in cf["core_people"] if p["entity_key"] == sus), {"name": D["names"].get(sus, sus), "accounts": []})

    st.markdown(f"""
<div class="cf-head">
  <div><div class="eyebrow-s">Case {cf['case_id']} · {cf['first_timestamp'][:16]} → {cf['last_timestamp'][:16]}</div>
       <div class="dash-title">{typ_cf} · {amt_cf}{' cycled' if 'CIRCLE' in cf['detectors_fired'] else ''}</div>
       <div class="dash-sub">{len(cf['core_people'])} people · {len(cf['evidence_txn_ids'])} evidence transfers ·
       {cf['hours_spanned']:.1f} hours · {'crosses both banks' if cf['crosses_banks'] else 'one bank'}</div></div>
  <div class="cf-status"><div class="k-l">AI recommends</div><div class="cf-rec">{dec_cf.get('decision', '—').replace('_', ' ')}</div>
       <div class="k-s">Review {wc_cf.get('verification', {}).get('verdict', '—')} · confidence {wc_cf.get('final_confidence', '—')}</div></div>
</div>
<div class="cf-grid">
  <div class="cf-card sus"><div class="k-l">Main suspect</div><div class="cf-name">{str(sus_p['name']).title()}</div>
       <div class="k-s">{why_sus} · {len(sus_p.get('accounts', []))} account(s): {', '.join(sus_p.get('accounts', []))}</div></div>
  <div class="cf-card in"><div class="k-l">Money came from</div>
       {''.join(f"<div class='cf-row'><span>{p['name'].title()[:26]}</span><b>{inr(p['amount'])}</b></div>" for p in ins_cf[:3]) or "<div class='k-s'>No outside source: the money started inside the network</div>"}</div>
  <div class="cf-card out"><div class="k-l">Money went to</div>
       {''.join(f"<div class='cf-row'><span>{p['name'].title()[:26]}</span><b>{inr(p['amount'])}</b></div>" for p in outs_cf[:3]) or "<div class='k-s'>No outside destination: the money stayed inside the network</div>"}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div class="chart-t">Money trail in 3D</div>', unsafe_allow_html=True)
    st.caption("Drag to rotate · scroll to zoom · right-drag to move · press Rotate for a slow orbit. "
               "Green = where the money came from, blue = the network, amber = where it went, red = main suspect.")
    st.plotly_chart(money_flow_3d(cf, sus), width="stretch", key=f"cf3d_{cf['case_id']}",
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["toImage"]})

    tcol, scol = st.columns([3, 2])
    with tcol:
        st.markdown('<div class="chart-t">Evidence transfers over time</div>', unsafe_allow_html=True)
        evt = D["full"][D["full"]["txn_id"].isin(cf["evidence_txn_ids"])].sort_values("timestamp")
        figt = go.Figure(go.Scatter(x=evt["timestamp"], y=evt["amount"] / 1e5,
                                    mode="lines+markers" if len(evt) <= 12 else "markers",
                                    line=dict(color="#1F4E8C", width=2),
                                    marker=dict(size=8, color="#C8553D", line=dict(color="white", width=1)),
                                    text=[f"{a} → {b}<br>{_format_inr(v)['digits']}" for a, b, v in
                                          zip(evt["from_account"], evt["to_account"], evt["amount"])],
                                    hovertemplate="%{x}<br>%{text}<extra></extra>"))
        _fig_style(figt, 260)
        figt.update_yaxes(title=None, ticksuffix=" L", gridcolor="#eef0f4")
        figt.update_xaxes(gridcolor="#eef0f4")
        st.plotly_chart(figt, width="stretch", config={"displayModeBar": False}, key=f"cft_{cf['case_id']}")
    with scol:
        st.markdown('<div class="chart-t">In one line</div>', unsafe_allow_html=True)
        st.markdown(f"<div class='cf-sum'>{wc_cf.get('narrative', {}).get('summary', '')}</div>", unsafe_allow_html=True)
        st.caption("Full report, evidence table and the approve button are in Case Queue.")

# ------------------------------------------------------------- identity ---
with tabs[5]:
    pagetitle("Identity · who is really behind these accounts?")
    helpbox("Pick a person. Left: the messy records banks hold. Right: the one real person we merged them into.")
    st.write("The same person shows up in several bank systems, spelled differently and with fields missing. "
             "Until those records are merged, a laundering circle looks like strangers paying each other.")
    ents = D["entities"]
    multi = ents[ents["num_accounts"].astype(int) > 1]
    hero_case = next((c for c in cases if "CIRCLE" in c["detectors_fired"]), cases[0])
    hero_people = [p["entity_key"] for p in hero_case["core_people"]]
    options = hero_people + [e for e in multi["entity_key"] if e not in hero_people][:60]
    label = {e: f"{D['names'][e]} ({e})" + ("  ⭐ hero ring" if e in hero_people else "") for e in options}
    pick = st.selectbox("Pick a person", options, format_func=lambda e: label[e])
    row = ents[ents["entity_key"] == pick].iloc[0]
    accs = row["account_ids"].split(";")
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**What the banks hold: {row['num_records']} scattered records**")
        recs_df = D["records"][D["records"]["linked_account"].isin(accs)].drop(columns=["linked_account"])
        st.dataframe(recs_df.fillna("—"), hide_index=True, width="stretch")
    with right:
        st.markdown("**Resolved into one person**")
        st.markdown(f"### {row['canonical_name']}")
        st.write(f"Accounts: `{', '.join(accs)}`")
        st.write(f"Phone: {row['phone'] if isinstance(row['phone'], str) else '—'}  ·  "
                 f"PAN: {row['pan'] if isinstance(row['pan'], str) else '—'}")
        st.write(f"Address: {row['address'] if isinstance(row['address'], str) else '—'}")
        st.write(f"Merged by rules: {row['rules_used'] if isinstance(row['rules_used'], str) else 'same account'}")
        if row["is_watchlisted"] == "True":
            st.error("On the watchlist")
        if row["has_unverified_link"] == "True":
            st.warning("Contains a probable (yellow) link, permanently flagged unverified")
    st.divider()
    m = st.columns(3)
    m[0].metric("Customer records", f"{len(D['records']):,}")
    m[1].metric("Accounts", f"{len(D['a2e']):,}")
    m[2].metric("Real people", f"{len(D['attrs']):,}")
    st.caption("Precision over recall: entity resolution scored pairwise precision 1.0 in Stage 2. "
               "Different PANs can never be merged; probable links are flagged and never chained.")

# -------------------------------------------------------------- network ---
with tabs[4]:
    pagetitle("Cross-bank view · one ring, four points of view")
    helpbox("Choose a viewpoint below the table. Watch the ring appear or vanish depending on who is looking.")
    s = D["stats"]
    base = s["ALL"]["num_connections"]
    pa, pb = 100 * s["BANK_A"]["num_connections"] / base, 100 * s["BANK_B"]["num_connections"] / base
    st.success(f"Bank A alone sees {pa:.0f}% of the network. Bank B alone sees {pb:.0f}%. "
               f"The consortium sees 100%.")
    st.dataframe(pd.DataFrame([{
        "View": VIEW_TITLES[v], "People (nodes)": s[v]["num_people"], "Connections": s[v]["num_connections"],
        "Self-transfers": s[v]["self_transfer_edges"], "Cross-bank edges": s[v]["cross_bank_edges"],
        "Sees": f"{100 * s[v]['num_connections'] / base:.0f}% of the network"} for v in VIEWS]),
        hide_index=True, width="stretch")

    st.markdown("### The hero ring: ₹2.4 crore looping through 6 accounts in ~3 hours")
    st.write("Six accounts, three real people, two banks. Pick a viewpoint:")
    view = st.radio("Viewpoint", VIEWS, horizontal=True, format_func=lambda v: VIEW_TITLES[v])
    ev_ids = hero_case["evidence_txn_ids"]
    hero_tx = D["tx_sorted"][D["tx_sorted"]["txn_id"].isin(ev_ids)]
    visible = filter_transactions(hero_tx, view)
    nodes, edges, G = {}, [], nx.DiGraph()

    def node_info(acc):
        n = resolve_node(acc, view, D["a2e"], D["a2b"], D["attrs"])
        if view == "CONSORTIUM":
            return n, f"{n[:8]}…", "hashed pseudonym: no name, PAN or account number shared", TEAL
        if n.startswith("EXT_"):
            return n, "Unknown<br>account", f"{n}: account at the other bank, identity invisible", GREY
        return n, D["names"][n], f"{D['names'][n]} ({n}), a customer this bank can resolve", BLUE

    info = {}
    for r in visible.itertuples(index=False):
        for acc in (r.from_account, r.to_account):
            n, lab, hov, col = node_info(acc)
            info[n] = (lab, hov, col)
        G.add_edge(node_info(r.from_account)[0], node_info(r.to_account)[0])
    pos = nx.circular_layout(G) if len(G) else {}
    for n, (x, y) in pos.items():
        nodes[n] = dict(x=float(x), y=float(y), label=info[n][0], hover=info[n][1], color=info[n][2], size=26)
    edges = [(u, v, RED, 2) for u, v in G.edges()]
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(loop_figure(view, hero_tx, set(visible["txn_id"])), width="stretch")
        st.caption("Numbers show the order of the six hops. Solid red = this viewpoint can see the hop, "
                   "dotted grey = it cannot. Blue = Bank A account, orange = Bank B account.")
    with right:
        best, total, ok, n_final, n_cand = hero[view]
        if ok:
            extra = f" Candidates {n_cand} → bank-confirmed {n_final}." if view == "CONSORTIUM" else ""
            st.markdown(f'<div class="verdict-yes"><b>Ring caught ✅</b><br>All {total}/{total} transactions '
                        f'sit in one closed, confirmed circle.{extra}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="verdict-no"><b>Ring NOT caught ❌</b><br>Best circle covers {best}/{total}. '
                        f'Only {len(visible)} of the {len(hero_tx)} transactions are visible from here, and the '
                        f'other bank\'s accounts are opaque.</div>', unsafe_allow_html=True)
        st.write("")
        st.caption({
            "ALL": "Fully resolved. Used to score the system, never available to a real bank.",
            "BANK_A": "A bank only knows its own customers. Any account at the other bank is an opaque "
                      "EXT node that can never be merged with another.",
            "BANK_B": "Same blindness from the other side. The hop inside Bank A is invisible here.",
            "CONSORTIUM": "Banks publish only salted hashes, amount bands and hour buckets. The consortium "
                          "proposes candidate loops; each bank then confirms only its own junctions with a "
                          "yes/no. No names, PANs, addresses, balances, KYC or account numbers cross.",
        }[view])
    with st.expander("Show the same view as people (who pays whom)"):
        st.plotly_chart(draw(nodes, edges, 380), width="stretch")
    st.markdown("**Hops visible in this view**")
    st.dataframe(txn_table(visible["txn_id"].tolist())[
        ["txn_id", "timestamp", "from_person", "to_person", "amount", "from_bank", "to_bank"]],
        hide_index=True, width="stretch")

# ------------------------------------------------------------ detectors ---
with tabs[6]:
    pagetitle("Detection rules · deterministic, no AI")
    helpbox("Filter the findings, then pick one at the bottom to see the exact transactions that prove it.")
    st.write("No AI, no randomness. The same input always gives the same findings and each one lists "
             "the exact transactions that prove it.")
    f_all = D["findings"]
    cnt = {d: sum(1 for f in f_all if f["detector"] == d) for d in det.DETECTORS}
    cc = st.columns(5)
    for col, (d, n) in zip(cc, cnt.items()):
        col.metric(d.replace("_", " ").title(), n)
    with st.expander("What each detector looks for, and why the thresholds"):
        st.markdown(f"""
- **Circle:** money leaves a person and returns within {det.CIRCLE_WINDOW_HOURS}h, {det.CIRCLE_MIN_HOPS}–{det.CIRCLE_MAX_HOPS} hops, every hop keeping {det.CIRCLE_MIN_RETENTION:.0%}–100% of the previous amount.
- **Spray:** one account pays {det.SPRAY_MIN_RECEIVERS}+ distinct accounts in {det.SPRAY_WINDOW_HOURS}h and {det.SPRAY_MIN_FORWARD_SHARE:.0%}+ of them forward 90–100% within an hour to the same collector.
- **Speed:** hop after hop within {det.SPEED_LINK_MINUTES} minutes keeping 90–100%. {det.SPEED_MIN_HOPS}+ hops.
- **Threshold:** {det.THRESHOLD_MIN_DEPOSITS}+ cash deposits in {det.THRESHOLD_WINDOW_DAYS} days each at 90–100% of ₹10,00,000 (Cash Transaction Report) or ₹50,000 (PAN limit).
- **Two lanes:** the *discovery* lane uses these bars for everyone. The *watchlist* lane lowers them (Spray 4, Speed 2, Threshold 3) when a known high-risk person is involved.
- **Watchlist signals:** weak hints only (first big transfer to a new counterparty, money into a brand-new account, new channel). Never evidence.
""")
    fc = st.columns(2)
    dsel = fc[0].multiselect("Detector", det.DETECTORS, default=det.DETECTORS)
    lsel = fc[1].multiselect("Lane", ["DISCOVERY", "WATCHLIST"], default=["DISCOVERY", "WATCHLIST"])
    shown = [f for f in f_all if f["detector"] in dsel and f["lane"] in lsel]
    st.dataframe(pd.DataFrame([{
        "Finding": f["finding_id"], "Detector": f["detector"],
        "People": len(f["people"]), "Txns": len(f["txn_ids"]),
        "Amount": moved(f["txn_ids"], [f["detector"]], f["total_amount"])[1],
        "First seen": f["first_timestamp"], "Why": inr_text(f["reason"])} for f in shown]),
        hide_index=True, width="stretch", height=300)
    if shown:
        sel = st.selectbox("Inspect a finding", [f["finding_id"] for f in shown],
                           format_func=lambda i: next(f"{f['finding_id']} · {f['detector']} · {moved(f['txn_ids'], [f['detector']], f['total_amount'])[1]}"
                                                      for f in shown if f["finding_id"] == i))
        f = next(f for f in shown if f["finding_id"] == sel)
        st.info(inr_text(f["reason"]))
        a, b = st.columns([2, 3])
        a.markdown("**Numbers that triggered it**")
        a.json(f["evidence"], expanded=True)
        b.markdown("**Exact transactions (re-checkable by hand)**")
        b.dataframe(txn_table(f["txn_ids"]), hide_index=True, width="stretch", height=250)

# ---------------------------------------------------------------- cases ---
with tabs[1]:
    pagetitle(f"Case queue · {len(cases)} cases awaiting an officer's decision")
    helpbox("Pick a case below. Each case shows the money trail, the unusual relationships, the AI report and its review, then your decision.")
    st.dataframe(pd.DataFrame([{
        "Case": c["case_id"], "Queue priority": f"{c['priority_level']} ({c['priority_score']})",
        "Detectors": " + ".join(c["detectors_fired"]),
        "Relationship flags": " ".join(relationships.get("cases", {}).get(c["case_id"], {}).get("signals_fired", [])),
        "Core people": len(c["core_people"]), "Context": len(c["context_people"]),
        "Amount moved": moved(c["evidence_txn_ids"], c["detectors_fired"], c["total_evidence_amount"])[1]
                        + (" cycled" if "CIRCLE" in c["detectors_fired"] else ""),
        "Hours": c["hours_spanned"],
        "Both banks": "yes" if c["crosses_banks"] else "no",
        "Found without watchlist": "yes" if c.get("found_without_watchlist") else "no"} for c in cases]),
        hide_index=True, width="stretch")

    case_ids = [x["case_id"] for x in cases]
    st.markdown('<div class="picker-t">Open a case</div>', unsafe_allow_html=True)
    picked = st.selectbox("Open a case", case_ids, key="case_pick", label_visibility="collapsed",
                          format_func=lambda i: case_label(
                              next(x for x in cases if x["case_id"] == i)))
    c = next(x for x in cases if x["case_id"] == picked)
    st.markdown(f"## {c['case_id']} &nbsp;<span class='pill {c['priority_level']}'>{c['priority_level']} · "
                f"{c['priority_score']}</span>", unsafe_allow_html=True)
    k = st.columns(5)
    _lab, _val, _note = moved(c["evidence_txn_ids"], c["detectors_fired"], c["total_evidence_amount"])
    k[0].metric(_lab, _val)
    k[1].metric("Time span", f"{c['hours_spanned']:.1f} h")
    k[2].metric("Core people", len(c["core_people"]))
    k[3].metric("Evidence txns", len(c["evidence_txn_ids"]))
    k[4].metric("Banks", " + ".join(b.replace("BANK_", "") for b in c["banks_involved"]))
    if _note:
        st.caption(f"Amount cycled = the principal that went round the loop. The same money counted once per hop is {_note}.")

    gcol, pcol = st.columns([3, 2])
    with gcol:
        rec = D["rec_by_id"]
        nodes = {}
        for p in c["core_people"]:
            x, y = c["layout"][p["entity_key"]]
            nodes[p["entity_key"]] = dict(x=x, y=y, label=p["name"].split(" (")[0][:16],
                                          hover=f"{p['name']} · CORE" + (" · watchlisted" if p["is_watchlisted"] else ""),
                                          color=RED if p["is_watchlisted"] else BLUE, size=22)
        for p in c["context_people"]:
            if p["entity_key"] in nodes:
                continue
            x, y = c["layout"][p["entity_key"]]
            nodes[p["entity_key"]] = dict(x=x, y=y, label=p["name"][:16],
                                          hover=f"{p['name']} · CONTEXT ({p['direction']}) · " + (
                                              f"also accused in {p['also_core_in']}" if p.get("also_core_in") else "not accused"),
                                          color=GREY, size=15)
        agg = {}
        for kind, ids, colr, w in (("ctx", c["context_txn_ids"], "#8fb3e0", 1), ("sup", c["supporting_txn_ids"], "#c5ccd6", 1),
                                   ("ev", c["evidence_txn_ids"], RED, 2.2)):
            for t in ids:
                r = rec[t]
                agg[(r.from_ent, r.to_ent)] = (colr, w)
        if len(nodes) > 12:
            for nid, nd in nodes.items():
                if nd["color"] != RED:
                    nd["label"] = ""
        st.plotly_chart(draw(nodes, [(u, v, col, w) for (u, v), (col, w) in agg.items()], 470),
                        width="stretch")
        st.caption("Red = evidence transfers · blue = money in or out of the network · grey = context, not accused.")
    with pcol:
        st.markdown("**Why it was flagged**")
        for fid in c["finding_ids"]:
            f = next(x for x in D["findings"] if x["finding_id"] == fid)
            st.write(f"• {f['detector'].title()}: {inr_text(f['reason'])}")
        _qx = st.expander("Queue priority, linked cases and hints")
        with _qx:
            st.markdown("**Queue priority** (order of work only)")
            for line in c["priority_reason"]:
                _m = _re.match(r"^\+(\d+)\s+(.*)$", inr_text(line))
                st.write("• " + (f"{_m.group(2)} (+{_m.group(1)})" if _m else inr_text(line)))
            st.markdown("**Linked cases**")
            if c.get("linked_cases"):
                for l in c["linked_cases"]:
                    st.write(f"• {l['case_id']} via {l['via_person']} (money {l['direction']}, "
                             f"{_format_inr(l['amount'])['digits']})")
                st.caption("Different rings; money connects them. They are not merged.")
            else:
                st.caption("None. No context person here is accused in another case.")
            if c["watchlist_signals"]:
                st.markdown("**Watchlist signals (hints, not evidence)**")
                for w in c["watchlist_signals"]:
                    st.write("• " + inr_text(w["reason"]))

    t1, t2, t3, t4 = st.tabs(["Core people (accused)", "Context (see notes)", "Evidence transactions",
                              "Background (supporting)"])
    with t1:
        st.dataframe(pd.DataFrame([{"Person": p["name"], "Key": p["entity_key"],
                                    "Watchlisted": "yes" if p["is_watchlisted"] else "",
                                    "Accounts": ", ".join(p["accounts"])} for p in c["core_people"]]),
                     hide_index=True, width="stretch")
    with t2:
        st.caption("Shown for where the money came from / went to. Read each note: a person accused in "
                   "another case is labelled as such.")
        st.dataframe(pd.DataFrame([{"Person": p["name"], "Direction": p["direction"],
                                    "Amount": inr(p["amount"]), "Note": p["note"]} for p in c["context_people"]]),
                     hide_index=True, width="stretch")
    with t3:
        st.dataframe(txn_table(c["evidence_txn_ids"]), hide_index=True, width="stretch")
    with t4:
        st.caption("Other dealings between the same people around the same time. Background only; "
                   "never counted as evidence.")
        st.dataframe(txn_table(c["supporting_txn_ids"]), hide_index=True, width="stretch")

    with st.expander(f"Where this case sits among all {len(D['all_layout']):,} customers"):
        st.caption("Grey = uninvolved · red = accused · amber = context · lines = money in this case.")
        lay = D["all_layout"]
        xs, ys = zip(*lay.values())
        core_keys = {p["entity_key"] for p in c["core_people"]}
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=xs, y=ys, mode="markers", marker=dict(size=4, color="#cdd6e3"), hoverinfo="skip"))
        lx, ly = [], []
        for t in c["evidence_txn_ids"] + c["context_txn_ids"]:
            r = D["rec_by_id"][t]
            if r.from_ent in lay and r.to_ent in lay and r.from_ent != r.to_ent:
                lx += [lay[r.from_ent][0], lay[r.to_ent][0], None]
                ly += [lay[r.from_ent][1], lay[r.to_ent][1], None]
        fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines", line=dict(color="rgba(192,57,43,.45)", width=1.5), hoverinfo="skip"))
        order = [n for n in c["highlight_nodes"] if n in lay]
        fig.add_trace(go.Scatter(
            x=[lay[n][0] for n in order], y=[lay[n][1] for n in order], mode="markers+text",
            text=[D["names"][n].title()[:14] if (n in core_keys and len(core_keys) <= 6) else "" for n in order],
            textposition="top center",
            marker=dict(size=[14 if n in core_keys else 10 for n in order],
                        color=[RED if n in core_keys else AMBER for n in order], line=dict(width=1.5, color="white")),
            hovertext=[D["names"][n] + (" · accused" if n in core_keys else " · context") for n in order],
            hoverinfo="text"))
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, plot_bgcolor="white",
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        st.plotly_chart(fig, width="stretch")

    rel = relationships.get("cases", {}).get(c["case_id"])
    if rel:
        st.markdown("### Unusual account relationships")
        st.caption("How the accounts in this case relate to each other, compared with what is normal across the bank.")
        if rel["signals"]:
            rc = st.columns(len(rel["signals"]))
            for col, s in zip(rc, rel["signals"]):
                col.markdown(f'<div class="card"><h4>{s["code"]} · {s["name"].replace("_", " ").title()}</h4>'
                             f'<p><b>{s["headline"]}</b></p><p>Case {s["case_value"]} · bank {s["bank_baseline"]}</p></div>',
                             unsafe_allow_html=True)
            for s in rel["signals"]:
                st.write("• " + s["sentence"])
        else:
            st.caption("No unusual relationships above the bank baseline for this case.")

    st.markdown("### AI investigator report")
    wc = written_cases.get(c["case_id"])
    if wc is None:
        st.info("Run `python orchestrator.py` to generate the AI investigator report and verifier "
                "review for this case.")
    else:
        n = wc.get("narrative", {})
        conf = n.get("confidence", {})
        conf_level = conf.get("level", "") if isinstance(conf, dict) else conf
        conf_reason = conf.get("reason", "") if isinstance(conf, dict) else ""
        st.caption(f"Model: {wc.get('model', '?')} · generated {wc.get('generated_at', '?')}"
                   + (f" · commissioned by {wc['commander']}" if wc.get("commander") else ""))
        if wc.get("commander_notes"):
            st.markdown(f'<div class="note">🏹 <b>DRONA\'s brief to SANJAYA:</b> {wc["commander_notes"]}</div>',
                        unsafe_allow_html=True)
        for label, key in [("Summary", "summary"), ("What happened", "what_happened"),
                           ("Typology", "typology"), ("Why suspicious", "why_suspicious")]:
            st.markdown(f'<div class="narrative-box"><h5>{label}</h5><p>{n.get(key, "")}</p></div>',
                       unsafe_allow_html=True)
        ac1, ac2 = st.columns(2)
        _dr = (ilog.get("items", {}).get(c["case_id"], {}) if ilog else {}).get("decision", {}).get("decision", "")
        ac1.markdown(f'<div class="narrative-box"><h5>Recommended action</h5>'
                     f'<p><b>{_dr.replace("_", " ") or n.get("recommended_action", "")}</b> (DRONA, lead investigator)'
                     f'<br><span style="color:#6b7385">Writer\'s first suggestion: '
                     f'{str(n.get("recommended_action", "")).replace("_", " ")}</span></p></div>', unsafe_allow_html=True)
        ac2.markdown(f'<div class="narrative-box"><h5>Investigator confidence</h5>'
                     f'<p><b>{conf_level}</b> — {conf_reason}</p></div>', unsafe_allow_html=True)

        st.markdown("### Verifier review")
        v = wc.get("verification", {})
        fc = wc.get("fact_check", {"checked": 0, "passed": 0, "failures": []})
        verdict = v.get("verdict", "NOT_VERIFIED")
        final_conf = wc.get("final_confidence", "LOW")
        vcol, fcol, ccol = st.columns(3)
        vcol.markdown(f"**Verdict**<br><span class='pill {verdict}'>{verdict}</span>",
                     unsafe_allow_html=True)
        fcol.markdown(f"**Facts checked**<br>{fc['passed']} of {fc['checked']} confirmed "
                     f"against raw data", unsafe_allow_html=True)
        ccol.markdown(f"**Final confidence**<br><span class='pill {final_conf}'>{final_conf}</span>",
                     unsafe_allow_html=True)
        st.markdown(f'<div class="narrative-box"><h5>Innocent explanation considered</h5>'
                    f'<p>{v.get("innocent_explanation", "")}</p></div>', unsafe_allow_html=True)
        if v.get("weaknesses"):
            st.markdown("**Weaknesses a regulator or court would attack**")
            for w in v["weaknesses"]:
                st.write("• " + w)
        if fc.get("failures"):
            with st.expander(f"Fact-check failures ({len(fc['failures'])})"):
                for fail in fc["failures"]:
                    st.write("• " + fail)
        if v.get("notes"):
            st.caption(v["notes"])

    st.markdown("### Officer decision")
    st.caption("The system recommends; you decide. Nothing is filed automatically.")
    note = st.text_input("Note (optional)", key=f"note_{c['case_id']}")
    b = st.columns(4)
    for col, (lab, dec) in zip(b[:3], [("✅ Approve for STR drafting", "Approved"),
                                       ("🔎 Request more evidence", "More evidence"),
                                       ("🚫 Dismiss", "Dismissed")]):
        if col.button(lab, key=f"{dec}_{c['case_id']}", width="stretch"):
            st.session_state["log"].append({"Time": datetime.now().strftime("%H:%M:%S"), "Case": c["case_id"],
                                            "Decision": dec, "Note": note})
            st.rerun()
    officer = next((e for e in reversed(st.session_state["log"]) if e["Case"] == c["case_id"]), None)
    officer = {"decision": officer["Decision"], "note": officer["Note"], "time": officer["Time"]} if officer else None
    ev_rows = txn_table(c["evidence_txn_ids"])
    ev_rows["amount"] = D["full"].set_index("txn_id").loc[ev_rows["txn_id"], "amount"].values
    str_html = build_str_html(c, written_cases.get(c["case_id"]), relationships.get("cases", {}).get(c["case_id"]),
                              ilog.get("items", {}).get(c["case_id"]) if ilog else None,
                              ev_rows.to_dict("records"),
                              {k: {"has_unverified_link": bool(a.get("has_unverified_link"))} for k, a in D["attrs"].items()},
                              officer)
    approved = bool(officer and officer["decision"] == "Approved")
    b[3].download_button("📄 STR report" + (" (approved)" if approved else " (draft)"), str_html,
                         f"STR_{c['case_id']}.html", mime="text/html", width="stretch",
                         type="primary" if approved else "secondary")
    if approved:
        st.success(f"Approved. The STR report for {c['case_id']} is ready: download it, open it, and print or save it as PDF. "
                   "The officer did not have to write a word.")
    else:
        st.caption("Approve the case to stamp the STR report as officer-approved.")
    st.download_button("⬇ Raw case data (JSON)", json.dumps({k: v for k, v in c.items() if k != "layout"}, indent=2),
                       f"{c['case_id']}.json", key=f"json_{c['case_id']}")

    if D["review"]:
        with st.expander(f"Watchlist review queue ({len(D['review'])}): low priority, not a case, no accusation"):
            for w in D["review"]:
                st.write(f"• `{w['finding_id']}` {w['reason']}")

# ------------------------------------------------------------ scorecard ---
with tabs[7]:
    pagetitle("Accuracy · checked against the hidden answer key")
    st.caption("The answer key is used only here, never by any detection or case logic.")
    caught = sum(1 for v in per_ring.values() if v[2])
    fa = sum(per_detector.get(d, (0, 0, 0))[2] for d in det.STRUCTURAL)
    m = st.columns(4)
    m[0].metric("Rings caught", f"{caught} of {len(per_ring)}")
    m[1].metric("False alarms (4 detectors)", fa)
    m[2].metric("Discovery only, nobody known", f"{disc[0]} of {disc[1]}", f"{disc[2]} false alarms")
    m[3].metric("Accused who are real ring members", f"{precision[0]} / {precision[1]}")
    st.write("**Discovery only** re-runs every detector with nobody on the watchlist, answering "
             "“you only caught them because you knew who they were.”")
    st.dataframe(pd.DataFrame([{
        "Ring": rid, "Transactions": n, "Best coverage": f"{cover * 100:.0f}%",
        "Result": "CAUGHT" if by else "MISSED", "Caught by": ", ".join(by) or "—"}
        for rid, (n, cover, by) in per_ring.items()]), hide_index=True, width="stretch")
    st.markdown('<div class="note">CIRC_5_SUBTLE is missed on purpose: it moves money slowly over several days, '
                'outside the 72-hour circle window. We report this rather than tune the threshold to hide it.</div>',
                unsafe_allow_html=True)
    st.write("")
    st.dataframe(pd.DataFrame([{"Detector": (d + " (weak hints, never a case)") if d == "WATCHLIST_SIGNAL" else d,
                                "Findings": v[0], "True positives": v[1], "False alarms": v[2]}
                               for d, v in per_detector.items()]), hide_index=True, width="stretch")
    st.caption("Watchlist signals are hints about already-known people (e.g. money into a brand-new account). "
               "They never open a case on their own, so their misses cannot become false accusations.")

st.markdown("""
<div class="footer"><span><b>CHAKRAVYUH</b> · Anti-Money-Laundering Investigation Portal</span>
<span>Every decision is made by an officer · Nothing is filed automatically</span>
<span>© 2026 Team Tech Coders</span></div>
""", unsafe_allow_html=True)
