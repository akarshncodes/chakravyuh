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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
.stMarkdown, .stMarkdown p, h1, h2, h3, h4, label p, button p, [data-testid="stMetricLabel"] p, [data-testid="stMetricValue"] {font-family: 'Inter', system-ui, sans-serif;}
.stApp {background: linear-gradient(180deg, #eef3fb 0%, #f7f9fd 45%, #f7f9fd 100%);}
.block-container {padding-top: 1rem; max-width: 1280px;}
h1, h2, h3, h4 {letter-spacing: -0.01em; color:#14213d;}
.hero {background: linear-gradient(120deg, #14213d 0%, #1f4e8c 60%, #2e86c1 100%); color:#fff;
       border-radius:18px; padding:22px 28px; margin-bottom:14px; box-shadow:0 8px 24px rgba(20,33,61,.18);}
.hero h1 {color:#fff; margin:0; font-size:2rem;}
.hero p {margin:4px 0 0 0; color:#dbe7f7; font-size:0.98rem;}
.hero .tag {display:inline-block; background:rgba(255,255,255,.16); border-radius:999px; padding:2px 12px;
            font-size:0.78rem; margin-top:10px; margin-right:6px;}
.card {background:#fff; border:1px solid #e1e8f3; border-radius:14px; padding:14px 16px; height:100%;
       box-shadow:0 2px 8px rgba(20,33,61,.06);}
.card h4 {margin:0 0 4px 0; font-size:0.95rem; color:#1f4e8c;}
.card p {margin:0; font-size:0.85rem; color:#3d4b5c;}
.pill {display:inline-block; padding:3px 12px; border-radius:999px; font-size:0.8rem; font-weight:600; color:#fff;}
.HIGH {background:#c0392b;} .MEDIUM {background:#d68910;} .LOW {background:#5d6d7e;}
.verdict-yes {background:#e8f6ef; border:1px solid #a9dfbf; border-radius:12px; padding:12px 16px; font-size:1rem;}
.verdict-no {background:#fdecea; border:1px solid #f5b7b1; border-radius:12px; padding:12px 16px; font-size:1rem;}
.note {background:#fff8e6; border:1px solid #f3dc9c; border-radius:10px; padding:8px 12px; font-size:0.88rem;}
.help {background:#eaf2fc; border-left:4px solid #1f4e8c; border-radius:8px; padding:10px 14px;
       font-size:0.92rem; color:#23364f; margin-bottom:12px;}
[data-testid="stMetric"] {background:#fff; border:1px solid #e1e8f3; border-radius:14px; padding:12px 16px;
       box-shadow:0 2px 8px rgba(20,33,61,.06);}
[data-testid="stMetricValue"] {font-size:1.6rem; color:#1f4e8c;}
.stTabs [data-baseweb="tab-list"] {gap:6px; flex-wrap:wrap;}
.stTabs [data-baseweb="tab"] {background:#fff; border:1px solid #dbe3ef; border-radius:999px; padding:6px 16px; height:auto;}
.stTabs [aria-selected="true"] {background:#1f4e8c !important; color:#fff !important; border-color:#1f4e8c;}
.stTabs [aria-selected="true"] p {color:#fff !important;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display:none;}
[data-testid="stSidebar"] {background:#e9eff8;}
[data-testid="stDataFrame"] {border:1px solid #e1e8f3; border-radius:10px;}
@media (max-width: 800px) {.hero h1 {font-size:1.4rem;} .block-container {padding-left:.8rem; padding-right:.8rem;}}
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


D = get_data()
per_detector, per_ring, hero, disc, precision = get_scoring()
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
<div class="hero">
  <h1>🌀 CHAKRAVYUH</h1>
  <p>Catching money laundering by scoring networks, not single transactions.</p>
  <span class="tag">Team Tech Coders (7-300)</span><span class="tag">IGNITRRON'26 · FC-02</span>
  <span class="tag">Fintech &amp; Cyber</span>
</div>
""", unsafe_allow_html=True)

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

tabs = st.tabs(["Overview", "1 · Identity", "2 · Network & cross-bank", "3 · Detectors",
                "4 · Cases", "Scorecard"])

# ------------------------------------------------------------- overview ---
with tabs[0]:
    st.subheader("We score networks, not transactions")
    helpbox("New here? Click the tabs in order: Identity, Network, Detectors, Cases, Scorecard.")
    st.write("Banks check one transaction at a time, so they cannot see money that is passed through "
             "many accounts to hide it. Chakravyuh joins the dots and hands the officer a finished, "
             "evidence-backed case instead of a pile of alerts.")
    c = st.columns(5)
    c[0].metric("Transactions", f"{len(D['tx']):,}")
    c[1].metric("Accounts → people", f"{len(D['a2e']):,} → {len(D['attrs']):,}")
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
with tabs[1]:
    st.subheader("Step 1 · Who is really behind these accounts?")
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
with tabs[2]:
    st.subheader("Step 2 · One ring, four points of view")
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
with tabs[3]:
    st.subheader("Step 3 · Four deterministic detectors")
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
with tabs[4]:
    st.subheader("Step 4 · One case per crime")
    helpbox("Start with C001, the hero ring. Scroll down for the graph, evidence, the map and the officer decision.")
    st.write(f"**{len(D['findings'])} findings became {len(cases)} cases** "
             f"(+{len(D['review'])} watchlist review item). Overlapping findings are merged; each case keeps "
             f"its evidence, background and one ring of context.")
    st.dataframe(pd.DataFrame([{
        "Case": c["case_id"], "Priority": f"{c['priority_level']} ({c['priority_score']})",
        "Lane": c["lane"], "Detectors": " + ".join(c["detectors_fired"]),
        "Core people": len(c["core_people"]), "Context": len(c["context_people"]),
        "Evidence amount": inr(c["total_evidence_amount"]), "Hours": c["hours_spanned"],
        "Both banks": "yes" if c["crosses_banks"] else "no"} for c in cases]),
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
                                          hover=f"{p['name']} · CONTEXT ({p['direction']}) · not accused",
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
                   "Red dots are watchlisted, blue are core, grey are context and NOT accused.")
    with pcol:
        st.markdown("**Why this priority**")
        for line in c["priority_reason"]:
            st.write("• " + line)
        st.markdown("**Findings merged into this case**")
        for fid in c["finding_ids"]:
            f = next(x for x in D["findings"] if x["finding_id"] == fid)
            st.write(f"• `{fid}` {f['detector']}: {f['reason']}")
        if c["watchlist_signals"]:
            st.markdown("**Watchlist signals (hints, not evidence)**")
            for w in c["watchlist_signals"]:
                st.write("• " + w["reason"])

    t1, t2, t3, t4 = st.tabs(["Core people (accused)", "Context (not accused)", "Evidence transactions",
                              "Background (supporting)"])
    with t1:
        st.dataframe(pd.DataFrame([{"Person": p["name"], "Key": p["entity_key"],
                                    "Watchlisted": "yes" if p["is_watchlisted"] else "",
                                    "Accounts": ", ".join(p["accounts"])} for p in c["core_people"]]),
                     hide_index=True, width="stretch")
    with t2:
        st.caption("Shown for where the money came from / went to; not accused.")
        st.dataframe(pd.DataFrame([{"Person": p["name"], "Direction": p["direction"],
                                    "Amount": inr(p["amount"])} for p in c["context_people"]]),
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
        hovertext=[D["names"][n] + (" · accused" if n in core_keys else " · context, not accused") for n in order],
        hoverinfo="text"))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, plot_bgcolor="white",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(fig, width="stretch")

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
    b[3].download_button("⬇ Case file (JSON)", json.dumps({k: v for k, v in c.items() if k != "layout"}, indent=2),
                         f"{c['case_id']}.json", width="stretch")

    if D["review"]:
        with st.expander(f"Watchlist review queue ({len(D['review'])}): low priority, not a case, no accusation"):
            for w in D["review"]:
                st.write(f"• `{w['finding_id']}` {w['reason']}")

# ------------------------------------------------------------ scorecard ---
with tabs[5]:
    st.subheader("Scorecard: checked against the hidden answer key")
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

st.divider()
st.caption("Chakravyuh · Team Tech Coders (7-300) · Detection is deterministic; humans make every decision.")
