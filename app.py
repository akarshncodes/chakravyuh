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

st.set_page_config(page_title="Chakravyuh", page_icon="🌀", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@600;700&display=swap');
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
@media (max-width: 800px) {.masthead .badge {display:none;} .masthead .hi {font-size:1.3rem;} .band:after,.band:before {display:none;}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data ----

def inr(x):
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} crore"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} lakh"
    return f"₹{x:,.0f}"


@st.cache_resource(show_spinner="Loading data…")
def get_data():
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
def get_scoring():
    D = get_data()
    per_detector, per_ring = det.score(D["findings"])
    exact = {r.txn_id: r for r in D["recs"]}
    hero = det.hero_check(D["tx_sorted"], D["a2e"], D["a2b"], D["attrs"], exact)
    disc = det.discovery_only_score(D["recs"], D["attrs"], det.load_account_ages())
    case_score = score_cases(D["cases"], D["findings"], D["recs"], D["a2e"])  # scoring only
    return per_detector, per_ring, hero, disc, case_score["precision"]


@st.cache_data(show_spinner=False)
def get_relationships():
    """Relationship Lens output (relationships.py). Absent file = panel hidden."""
    path = os.path.join(HERE, "relationships.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def get_investigation_log():
    """DRONA's cached investigation (orchestrator.py). Absent file = setup hint."""
    path = os.path.join(HERE, "investigation_log.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def get_written_cases():
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
    t["amount"] = t["amount"].map(lambda a: f"{a:,.2f}")
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
            f"{'+'.join(d[:4] for d in c['detectors_fired'])} · {inr(c['total_evidence_amount'])}")


# --------------------------------------------------------------- header ---

st.markdown("""
<div class="util"><span>Prototype demonstration · Not an official government or bank website</span>
<span>IGNITRRON'26 · Project J.A.R.V.I.S. · Problem FC-02</span></div>
<div class="tricolor"></div>
<div class="masthead">
  <div class="logo">🌀</div>
  <div><div class="hi">चक्रव्यूह</div>
       <div class="en"><b>CHAKRAVYUH</b> · Anti-Money-Laundering Investigation Portal</div></div>
  <div class="badge"><span>Team Tech Coders (7-300)</span><span>Fintech &amp; Cyber</span></div>
</div>
""", unsafe_allow_html=True)

def pagetitle(text):
    st.markdown(f'<div class="ptitle">{text}</div>', unsafe_allow_html=True)


def helpbox(text):
    st.markdown(f'<div class="help">💡 {text}</div>', unsafe_allow_html=True)

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

tabs = st.tabs(["⚔️ War Room", "Overview", "1 · Identity", "2 · Network & cross-bank", "3 · Detectors",
                "4 · Cases", "Scorecard"])

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


with tabs[0]:
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
        col.markdown(f'<div class="card"><h4>{nm}</h4><p><b>{role}</b></p><p>{line}</p></div>', unsafe_allow_html=True)

    if not ilog:
        st.info("DRONA has not run yet. Run `python orchestrator.py` (needs OPENAI_API_KEY in .env).")
    else:
        m = ilog["meta"]
        k = st.columns(6)
        k[0].metric("Items investigated", m["items"], f"{m['cases']} cases + {m['weak_signals']} weak signals", delta_color="off")
        k[1].metric("Tool calls DRONA chose", m["tool_calls"], f"{m['evidence_tool_calls']} evidence lookups", delta_color="off")
        k[2].metric("Reports passed by VIDURA", f"{m['vidura_pass']} / {m['cases']}", f"{m['rewrites']} sent back for rewrite", delta_color="off")
        k[3].metric("Facts confirmed by code", f"{m['facts_confirmed']} / {m['facts_checked']}")
        k[4].metric("Invented citations blocked", m["blocked_citations"], "rejected before any officer saw them", delta_color="off")
        k[5].metric("Filed automatically", 0, "every decision goes to a human", delta_color="off")

        st.markdown("#### DRONA's triage")
        st.caption("DRONA ordered the queue himself and wrote down why. The final column is his recommendation, not a filing.")
        st.dataframe(pd.DataFrame([{
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
        st.markdown('<div class="note">Guardrails are code, not promises: DRONA has no tool that can create a finding '
                    'or a case, cannot cite an ID his tools did not show him, must look at evidence before deciding, '
                    'and cannot recommend filing a report VIDURA rejected.</div>', unsafe_allow_html=True)
        st.caption(f"Recorded {m['generated_at']} · DRONA {m['commander_model']} · SANJAYA/VIDURA {m['writer_model']} · "
                   f"replayed from investigation_log.json, no live API call.")

# ------------------------------------------------------------- overview ---
with tabs[1]:
    st.markdown('<div class="band"><h2>Detect. Connect. Confirm.</h2><p>Banks see one transaction at a time. '
                'Chakravyuh joins accounts into real people, people into networks, and networks into '
                'evidence-backed cases for the investigating officer.</p></div>', unsafe_allow_html=True)
    pagetitle("We score networks, not transactions")
    helpbox("New here? Start in the War Room, then Identity, Network, Detectors, Cases, Scorecard.")
    st.write("Banks check one transaction at a time, so they cannot see money that is passed through "
             "many accounts to hide it. Chakravyuh joins the dots and hands the officer a finished, "
             "evidence-backed case instead of a pile of alerts.")
    c = st.columns(5)
    c[0].metric("Transactions", f"{len(D['tx']):,}")
    c[1].metric("Real people (from 2,500 accounts)", f"{len(D['attrs']):,}")
    c[2].metric("Detector findings", len(D["findings"]))
    c[3].metric("Cases", len(cases))
    c[4].metric("Rings caught", f"{sum(1 for v in per_ring.values() if v[2])} / {len(per_ring)}")

    st.markdown("#### The pipeline")
    steps = [("1 · Data", "80,000 bank transactions with 12 hidden laundering rings"),
             ("2 · Identity", "Scattered customer records merged into real people"),
             ("3 · Graph", "People are nodes, money is edges. Four views incl. cross-bank"),
             ("4 · Detectors", "Circle, Spray, Speed, Threshold. Deterministic, no AI"),
             ("5 · Cases", "Findings merged into one case per crime, with context")]
    cols = st.columns(5)
    for col, (h, p) in zip(cols, steps):
        col.markdown(f'<div class="card"><h4>{h}</h4><p>{p}</p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown("**Design principle:** detection is deterministic and re-checkable by hand. "
                "Every finding names the exact transactions that prove it.")
    st.markdown("**Suggested tour:** Identity → Network & cross-bank (the hero ring) → Detectors → "
                "Cases (C001) → Scorecard.")

# ------------------------------------------------------------- identity ---
with tabs[2]:
    pagetitle("Step 1 · Who is really behind these accounts?")
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
with tabs[3]:
    pagetitle("Step 2 · One ring, four points of view")
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
with tabs[4]:
    pagetitle("Step 3 · Four deterministic detectors")
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
        "Finding": f["finding_id"], "Detector": f["detector"], "Lane": f["lane"],
        "People": len(f["people"]), "Txns": len(f["txn_ids"]), "Amount": inr(f["total_amount"]),
        "First seen": f["first_timestamp"], "Why": f["reason"]} for f in shown]),
        hide_index=True, width="stretch", height=300)
    if shown:
        sel = st.selectbox("Inspect a finding", [f["finding_id"] for f in shown],
                           format_func=lambda i: next(f"{f['finding_id']} · {f['detector']} · {inr(f['total_amount'])}"
                                                      for f in shown if f["finding_id"] == i))
        f = next(f for f in shown if f["finding_id"] == sel)
        st.info(f["reason"])
        a, b = st.columns([2, 3])
        a.markdown("**Numbers that triggered it**")
        a.json(f["evidence"], expanded=False)
        b.markdown("**Exact transactions (re-checkable by hand)**")
        b.dataframe(txn_table(f["txn_ids"]), hide_index=True, width="stretch", height=250)

# ---------------------------------------------------------------- cases ---
with tabs[5]:
    pagetitle("Step 4 · One case per crime")
    helpbox("Start with C001, the hero ring. Scroll down for the graph, evidence, the map and the officer decision.")
    st.write(f"**{len(D['findings'])} findings became {len(cases)} cases** "
             f"(+{len(D['review'])} watchlist review item). Overlapping findings are merged; each case keeps "
             f"its evidence, background and one ring of context.")
    st.dataframe(pd.DataFrame([{
        "Case": c["case_id"], "Queue priority": f"{c['priority_level']} ({c['priority_score']})",
        "Detectors": " + ".join(c["detectors_fired"]),
        "Relationship flags": " ".join(relationships.get("cases", {}).get(c["case_id"], {}).get("signals_fired", [])),
        "Core people": len(c["core_people"]), "Context": len(c["context_people"]),
        "Evidence amount": inr(c["total_evidence_amount"]), "Hours": c["hours_spanned"],
        "Both banks": "yes" if c["crosses_banks"] else "no",
        "Found without watchlist": "yes" if c.get("found_without_watchlist") else "no"} for c in cases]),
        hide_index=True, width="stretch")

    case_ids = [x["case_id"] for x in cases]
    picked = st.selectbox("Open a case", case_ids, key="case_pick",
                          format_func=lambda i: case_label(
                              next(x for x in cases if x["case_id"] == i)))
    c = next(x for x in cases if x["case_id"] == picked)
    st.markdown(f"## {c['case_id']} &nbsp;<span class='pill {c['priority_level']}'>{c['priority_level']} · "
                f"{c['priority_score']}</span>", unsafe_allow_html=True)
    k = st.columns(5)
    k[0].metric("Evidence amount", inr(c["total_evidence_amount"]))
    k[1].metric("Time span", f"{c['hours_spanned']:.1f} h")
    k[2].metric("Core people", len(c["core_people"]))
    k[3].metric("Evidence txns", len(c["evidence_txn_ids"]))
    k[4].metric("Banks", " + ".join(b.replace("BANK_", "") for b in c["banks_involved"]))

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
        st.caption("Red arrows = evidence (proven claims) · pale = background · blue = context money in/out. "
                   "Red dots are watchlisted, blue are core, grey are context (not accused, unless the hover says "
                   "they are accused in another case).")
    with pcol:
        st.markdown("**Why this queue position** (order of work only; the evidence is below)")
        for line in c["priority_reason"]:
            st.write("• " + line)
        st.markdown("**Linked cases**")
        if c.get("linked_cases"):
            for l in c["linked_cases"]:
                st.write(f"• {l['case_id']} via {l['via_person']} (money {l['direction']}, "
                         f"Rs {l['amount']:,.0f})")
            st.caption("Different rings; money connects them. They are not merged.")
        else:
            st.caption("None. No context person here is accused in another case.")
        st.markdown("**Findings merged into this case**")
        for fid in c["finding_ids"]:
            f = next(x for x in D["findings"] if x["finding_id"] == fid)
            st.write(f"• `{fid}` {f['detector']}: {f['reason']}")
        if c["watchlist_signals"]:
            st.markdown("**Watchlist signals (hints, not evidence)**")
            for w in c["watchlist_signals"]:
                st.write("• " + w["reason"])

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

    st.markdown("**Where this case sits on the full network**")
    st.caption(f"Every dot is one of the {len(D['all_layout']):,} real people. Grey = uninvolved. "
               "Red = accused (core), amber = context, lines = money in this case.")
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
        st.caption("Relationship Lens: how the accounts in this case relate to each other, compared with "
                   "what is normal across the whole bank. Adds evidence only; it never creates a case.")
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
        cg = relationships.get("control_group", {})
        cs = relationships.get("case_summary", {})
        if cg:
            st.caption(f"Sanity check: the same five checks fire {cs.get('avg_signals_per_case')} times per case, "
                       f"but only {cg.get('avg_signals_per_group')} times per group across {cg.get('groups')} "
                       f"random groups of ordinary customers.")

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
        ac1.markdown(f'<div class="narrative-box"><h5>Recommended action</h5>'
                     f'<p>{n.get("recommended_action", "")}</p></div>', unsafe_allow_html=True)
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
    st.markdown('<div class="note">The system recommends; the officer decides. Nothing is filed automatically.</div>',
                unsafe_allow_html=True)
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
        st.caption("📄 The STR report downloads as a draft. Approve the case to stamp it as approved by the officer.")
    st.download_button("⬇ Raw case data (JSON)", json.dumps({k: v for k, v in c.items() if k != "layout"}, indent=2),
                       f"{c['case_id']}.json", key=f"json_{c['case_id']}")

    if D["review"]:
        with st.expander(f"Watchlist review queue ({len(D['review'])}): low priority, not a case, no accusation"):
            for w in D["review"]:
                st.write(f"• `{w['finding_id']}` {w['reason']}")

# ------------------------------------------------------------ scorecard ---
with tabs[6]:
    pagetitle("Scorecard: checked against the hidden answer key")
    st.caption("The answer key is used only here, never by any detection or case logic.")
    caught = sum(1 for v in per_ring.values() if v[2])
    fa = sum(per_detector[d][2] for d in det.STRUCTURAL)
    m = st.columns(4)
    m[0].metric("Rings caught", f"{caught} of {len(per_ring)}")
    m[1].metric("False alarms (4 detectors)", fa)
    m[2].metric("Discovery only, nobody known", f"{disc[0]} of {disc[1]}", f"{disc[2]} false alarms")
    m[3].metric("Accused precision", f"{precision[0]} / {precision[1]}", f"{precision[0] / precision[1] * 100:.0f}% of core people are ring members")
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
    st.dataframe(pd.DataFrame([{"Detector": d, "Findings": v[0], "True positives": v[1], "False alarms": v[2]}
                               for d, v in per_detector.items()]), hide_index=True, width="stretch")

st.markdown("""
<div class="footer"><span><b>CHAKRAVYUH</b> · Anti-Money-Laundering Investigation Portal (prototype)</span>
<span>Detection is deterministic · Every decision is made by a human officer · Nothing is filed automatically</span>
<span>© Team Tech Coders (7-300) · IGNITRRON'26</span></div>
""", unsafe_allow_html=True)
