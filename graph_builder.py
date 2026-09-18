"""
CHAKRAVYUH — Stage 3: graph builder.

Turns 80,000 account-level transactions into a network of PEOPLE. A
laundering circle that moves through six accounts owned by three real people
is invisible while those accounts look like six strangers; it only becomes a
circle once accounts are grouped by resolved owner (Stage 2).

Builds four views of the same underlying data:

  ALL         everything, fully resolved. God's-eye view, used for scoring only.
  BANK_A      only what Bank A's own transaction log can show, from Bank A's
              own vantage point.
  BANK_B      same, for Bank B.
  CONSORTIUM  both banks contribute, but only hashed pseudonyms and bucketed
              (never exact) transaction attributes cross the bank boundary.

Why single-bank views use opaque external nodes
-------------------------------------------------
A bank only runs entity resolution over ITS OWN customer records — it has no
legal or technical access to the other bank's KYC files. So when Bank A sees
a transaction touching an account at Bank B, it cannot tell who owns that
account, or whether two such accounts belong to the same person. Bank A can
only record that money moved to/from "some account at the other bank" — an
opaque placeholder node (EXT_<account_id>) that can never be merged with
another opaque node, even if in reality they belong to the same person. This
is deliberately how the code is written: resolve_node() only ever looks up
an entity for accounts that belong to the view's own bank.

What the consortium does and does not share
---------------------------------------------
The consortium layer is not a merged database. Each bank publishes, per
transaction, a keyed pseudonym for each party — sha256(PAN + shared salt)
when a PAN is known, otherwise a bank-local sha256(bank + entity_key + shared
salt) that can never match anything at the other bank — plus a
bucketed amount band and an hour-granularity timestamp bucket. This is
sufficient to say "the same real person shows up in both banks' logs" and to
join a ring that spans both banks, without either bank ever learning the
other's customer names, PANs in the clear, addresses, balances or KYC
levels. build_consortium_graph() asserts this after construction: it fails
loudly if a forbidden field or a non-hashed node id ever leaks in.
"""

import hashlib
import json
import os
import pickle

import networkx as nx
import pandas as pd

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.join(DATA_DIR, "graphs")

VIEWS = ["ALL", "BANK_A", "BANK_B", "CONSORTIUM"]

# Shared secret used to derive consortium pseudonyms. In production this
# would be a securely rotated secret held by the consortium operator, never
# by either bank alone; for the hackathon demo a fixed constant is enough to
# make pseudonyms reproducible run to run.
SHARED_SALT = "CHAKRAVYUH_CONSORTIUM_SALT_2026"

# Fields that must never appear anywhere in the consortium graph.
FORBIDDEN_CONSORTIUM_KEYS = {
    "canonical_name", "name", "pan", "phone", "address",
    "kyc_level", "balance", "account_ids", "account_id",
    "account_type", "is_watchlisted", "has_unverified_link",
}

AMOUNT_BAND_EDGES = [
    (10_000, "UNDER_10K"),
    (100_000, "10K_1L"),
    (500_000, "1L_5L"),
    (1_000_000, "5L_10L"),
    (5_000_000, "10L_50L"),
]


def amount_band(amount):
    for ceiling, label in AMOUNT_BAND_EDGES:
        if amount <= ceiling:
            return label
    return "50L_PLUS"


def hour_bucket(timestamp):
    return pd.Timestamp(timestamp).floor("h").strftime("%Y-%m-%d %H:00")


def pseudonym(entity_key, pan, bank):
    """Cross-bank linking happens through salted PAN hashes ONLY. When a
    person has no known PAN, the pseudonym is scoped to the publishing bank,
    so it can never be joined to anything the other bank publishes - a bank
    cannot vouch that its PAN-less customer is the same human as someone at
    another bank, and the consortium must not pretend it can."""
    if isinstance(pan, str) and pan.strip():
        basis = pan
    else:
        basis = f"{bank}:{entity_key}"
    digest = hashlib.sha256(f"{basis}{SHARED_SALT}".encode()).hexdigest()[:16]
    return f"PSU_{digest}"


def evidence_ref(txn_id):
    """A salted hash of a txn_id. Reveals nothing on its own - the raw
    transaction only exists in the bank that originated it - but lets each
    bank resolve its own references locally, and lets a verifier confirm two
    parties are citing the same underlying transaction without either side
    disclosing account numbers or customer identities."""
    return hashlib.sha256(f"{txn_id}{SHARED_SALT}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data():
    tx = pd.read_csv(os.path.join(DATA_DIR, "transactions.csv"), parse_dates=["timestamp"])
    owners = pd.read_csv(os.path.join(DATA_DIR, "account_owners.csv"))
    entities = pd.read_csv(os.path.join(DATA_DIR, "resolved_entities.csv"))

    account_to_entity = dict(zip(owners.account_id, owners.entity_key))

    entity_attrs = {}
    for row in entities.itertuples(index=False):
        pan = row.pan if isinstance(row.pan, str) and row.pan.strip() else None
        account_ids = row.account_ids.split(";") if isinstance(row.account_ids, str) else []
        entity_attrs[row.entity_key] = {
            "canonical_name": row.canonical_name,
            "pan": pan,
            "is_watchlisted": bool(row.is_watchlisted),
            "has_unverified_link": bool(row.has_unverified_link),
            "account_ids": account_ids,
        }

    account_to_bank = build_account_to_bank(tx)

    return tx, account_to_entity, entity_attrs, account_to_bank


def build_account_to_bank(tx):
    """Every account transacts through exactly one bank. Derive that mapping
    from the transaction log itself (never from accounts.csv's owner_entity
    column, which is ground truth and off-limits outside scoring)."""
    pairs = pd.concat([
        tx[["from_account", "from_bank"]].rename(columns={"from_account": "account_id", "from_bank": "bank"}),
        tx[["to_account", "to_bank"]].rename(columns={"to_account": "account_id", "to_bank": "bank"}),
    ]).drop_duplicates()

    conflicts = pairs.groupby("account_id")["bank"].nunique()
    conflicts = conflicts[conflicts > 1]
    if len(conflicts):
        print(f"WARNING: {len(conflicts)} accounts appear under more than one bank in the "
              f"transaction log; using the first bank seen for each.")

    return dict(zip(pairs.account_id, pairs.bank))


# ---------------------------------------------------------------------------
# Node resolution — the core of the cross-bank blindness/visibility story
# ---------------------------------------------------------------------------

def resolve_node(account_id, view, account_to_entity, account_to_bank, entity_attrs):
    """Map a raw account id to the node id it becomes in a given view."""
    entity = account_to_entity[account_id]
    if view == "ALL":
        return entity
    if view in ("BANK_A", "BANK_B"):
        bank = account_to_bank.get(account_id)
        if bank == view:
            return entity
        return f"EXT_{account_id}"
    if view == "CONSORTIUM":
        pan = entity_attrs.get(entity, {}).get("pan")
        return pseudonym(entity, pan, account_to_bank.get(account_id))
    raise ValueError(f"unknown view: {view}")


def filter_transactions(tx, view):
    if view == "ALL":
        return tx
    if view in ("BANK_A", "BANK_B"):
        return tx[(tx["from_bank"] == view) | (tx["to_bank"] == view)]
    if view == "CONSORTIUM":
        return tx
    raise ValueError(f"unknown view: {view}")


def _ensure_node(G, node_id, account_id, view, account_to_entity, entity_attrs, account_to_bank):
    if node_id in G:
        return
    if node_id.startswith("EXT_"):
        # An opaque counterparty: the viewing bank knows this specific
        # account moved money, and nothing else about who holds it.
        G.add_node(
            node_id,
            is_external=True,
            canonical_name=None,
            is_watchlisted=False,
            has_unverified_link=False,
            account_ids=[account_id],
            banks_used=[account_to_bank.get(account_id)],
        )
        return

    entity = account_to_entity[account_id]
    attrs = entity_attrs.get(entity, {})
    all_account_ids = attrs.get("account_ids", [account_id])
    if view in ("BANK_A", "BANK_B"):
        # The bank only knows the accounts this customer holds WITH IT.
        known_accounts = [a for a in all_account_ids if account_to_bank.get(a) == view]
    else:
        known_accounts = all_account_ids
    banks_used = sorted({account_to_bank.get(a) for a in known_accounts if account_to_bank.get(a)})

    G.add_node(
        node_id,
        is_external=False,
        canonical_name=attrs.get("canonical_name"),
        is_watchlisted=attrs.get("is_watchlisted", False),
        has_unverified_link=attrs.get("has_unverified_link", False),
        account_ids=known_accounts,
        banks_used=banks_used,
    )


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_resolved_view_graph(view, tx, account_to_entity, account_to_bank, entity_attrs):
    """Builds ALL, BANK_A or BANK_B. Edges are aggregated per ordered node
    pair; self-transfers between a person's own accounts are kept as
    self-loops, since moving money between your own accounts is itself a
    laundering behaviour we do not want to discard."""
    ftx = filter_transactions(tx, view)
    G = nx.MultiDiGraph()
    edge_acc = {}

    for row in ftx.itertuples(index=False):
        u = resolve_node(row.from_account, view, account_to_entity, account_to_bank, entity_attrs)
        v = resolve_node(row.to_account, view, account_to_entity, account_to_bank, entity_attrs)
        _ensure_node(G, u, row.from_account, view, account_to_entity, entity_attrs, account_to_bank)
        _ensure_node(G, v, row.to_account, view, account_to_entity, entity_attrs, account_to_bank)

        acc = edge_acc.setdefault((u, v), {
            "txn_count": 0, "total_amount": 0.0,
            "min_amount": float("inf"), "max_amount": float("-inf"),
            "first_timestamp": None, "last_timestamp": None,
            "channels": set(), "txn_ids": [], "crosses_banks": False,
        })
        acc["txn_count"] += 1
        acc["total_amount"] += float(row.amount)
        acc["min_amount"] = min(acc["min_amount"], float(row.amount))
        acc["max_amount"] = max(acc["max_amount"], float(row.amount))
        ts = row.timestamp
        if acc["first_timestamp"] is None or ts < acc["first_timestamp"]:
            acc["first_timestamp"] = ts
        if acc["last_timestamp"] is None or ts > acc["last_timestamp"]:
            acc["last_timestamp"] = ts
        acc["channels"].add(row.channel)
        acc["txn_ids"].append(row.txn_id)
        if row.from_bank != row.to_bank:
            acc["crosses_banks"] = True

    for (u, v), acc in edge_acc.items():
        G.add_edge(
            u, v,
            txn_count=acc["txn_count"],
            total_amount=round(acc["total_amount"], 2),
            min_amount=round(acc["min_amount"], 2),
            max_amount=round(acc["max_amount"], 2),
            first_timestamp=str(acc["first_timestamp"]),
            last_timestamp=str(acc["last_timestamp"]),
            channels=sorted(acc["channels"]),
            txn_ids=acc["txn_ids"],
            crosses_banks=acc["crosses_banks"],
            is_self_transfer=(u == v),
        )

    _annotate_node_flow(G)
    return G


def build_consortium_graph(tx, account_to_entity, account_to_bank, entity_attrs):
    """Builds CONSORTIUM. Every transaction is published by both the sending
    and receiving bank as a pseudonymous edge stub — direction, amount band,
    hour bucket, hashed counterparty. No raw PII crosses the boundary; only
    pseudonym-to-pseudonym linkage does. This is what lets two banks jointly
    discover a ring neither could see alone, without pooling customer data
    (the approach that got Transaction Monitoring Netherlands shut down on
    GDPR grounds in Jan 2025)."""
    G = nx.MultiDiGraph()
    edge_acc = {}

    for row in tx.itertuples(index=False):
        u_entity = account_to_entity[row.from_account]
        v_entity = account_to_entity[row.to_account]
        u = pseudonym(u_entity, entity_attrs.get(u_entity, {}).get("pan"), row.from_bank)
        v = pseudonym(v_entity, entity_attrs.get(v_entity, {}).get("pan"), row.to_bank)
        G.add_node(u)
        G.add_node(v)

        acc = edge_acc.setdefault((u, v), {
            "txn_count": 0, "amount_bands": set(), "hour_buckets": set(),
            "crosses_banks": False, "evidence_refs": [],
        })
        acc["txn_count"] += 1
        acc["amount_bands"].add(amount_band(float(row.amount)))
        acc["hour_buckets"].add(hour_bucket(row.timestamp))
        acc["evidence_refs"].append(evidence_ref(row.txn_id))
        if row.from_bank != row.to_bank:
            acc["crosses_banks"] = True

    for (u, v), acc in edge_acc.items():
        G.add_edge(
            u, v,
            txn_count=acc["txn_count"],
            amount_bands=sorted(acc["amount_bands"]),
            hour_buckets=sorted(acc["hour_buckets"]),
            crosses_banks=acc["crosses_banks"],
            is_self_transfer=(u == v),
            evidence_refs=acc["evidence_refs"],
        )

    for n in G.nodes():
        out_ct = sum(d["txn_count"] for _, _, d in G.out_edges(n, data=True))
        in_ct = sum(d["txn_count"] for _, _, d in G.in_edges(n, data=True))
        G.nodes[n]["txn_count"] = out_ct + in_ct

    _assert_no_pii_leak(G)
    return G


def _annotate_node_flow(G):
    for n in G.nodes():
        sent = sum(d["total_amount"] for _, _, d in G.out_edges(n, data=True))
        recv = sum(d["total_amount"] for _, _, d in G.in_edges(n, data=True))
        txn_ct = (sum(d["txn_count"] for _, _, d in G.out_edges(n, data=True)) +
                  sum(d["txn_count"] for _, _, d in G.in_edges(n, data=True)))
        G.nodes[n]["total_sent"] = round(sent, 2)
        G.nodes[n]["total_received"] = round(recv, 2)
        G.nodes[n]["txn_count"] = txn_ct


def _assert_no_pii_leak(G):
    for n, data in G.nodes(data=True):
        assert n.startswith("PSU_"), f"consortium node id is not a pseudonym: {n}"
        leaked = FORBIDDEN_CONSORTIUM_KEYS & set(data.keys())
        assert not leaked, f"forbidden field(s) {leaked} present on consortium node {n}"
    for u, v, data in G.edges(data=True):
        leaked = FORBIDDEN_CONSORTIUM_KEYS & set(data.keys())
        assert not leaked, f"forbidden field(s) {leaked} present on consortium edge {u}->{v}"


def build_graph(view, tx, account_to_entity, account_to_bank, entity_attrs):
    if view == "CONSORTIUM":
        return build_consortium_graph(tx, account_to_entity, account_to_bank, entity_attrs)
    return build_resolved_view_graph(view, tx, account_to_entity, account_to_bank, entity_attrs)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_view(view, G, stats):
    os.makedirs(GRAPH_DIR, exist_ok=True)

    with open(os.path.join(GRAPH_DIR, f"{view}.gpickle"), "wb") as f:
        pickle.dump(G, f)

    # Laying out ~1,800 nodes is slow — compute it once here, never at demo time.
    pos = nx.spring_layout(G, seed=42)
    pos_json = {str(n): [float(x), float(y)] for n, (x, y) in pos.items()}
    with open(os.path.join(GRAPH_DIR, f"{view}_layout.json"), "w") as f:
        json.dump(pos_json, f)

    with open(os.path.join(GRAPH_DIR, f"{view}_stats.json"), "w") as f:
        json.dump(stats, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Stats / reporting
# ---------------------------------------------------------------------------

def compute_stats(G, view):
    self_transfer_edges = sum(1 for _, _, d in G.edges(data=True) if d.get("is_self_transfer"))
    cross_bank_edges = sum(1 for _, _, d in G.edges(data=True) if d.get("crosses_banks"))

    top5 = []
    for node, degree in sorted(G.degree(), key=lambda x: x[1], reverse=True)[:5]:
        data = G.nodes[node]
        if view == "CONSORTIUM":
            label = f"{node}  [anonymized pseudonym — no bank can see this person's name]"
        elif data.get("is_external"):
            label = f"{node}  [external account at the other bank — identity unknown to this bank]"
        else:
            label = data.get("canonical_name") or node
        top5.append({"node": node, "connections": degree, "label": label})

    return {
        "view": view,
        "num_people": G.number_of_nodes(),
        "num_connections": G.number_of_edges(),
        "self_transfer_edges": self_transfer_edges,
        "cross_bank_edges": cross_bank_edges,
        "top5_busiest": top5,
    }


def print_report(all_stats, graphs):
    print("=" * 78)
    print("CHAKRAVYUH — Stage 3: graph builder report")
    print("=" * 78)

    for view in VIEWS:
        s = all_stats[view]
        print(f"\n--- {view} ---")
        print(f"  people (nodes):        {s['num_people']}")
        print(f"  connections (edges):   {s['num_connections']}")
        print(f"  self-transfer edges:   {s['self_transfer_edges']}")
        print(f"  cross-bank edges:      {s['cross_bank_edges']}")
        print(f"  5 busiest people:")
        for entry in s["top5_busiest"]:
            print(f"    {entry['connections']:>3} connections — {entry['label']}")

    all_edges = all_stats["ALL"]["num_connections"]
    bank_a_pct = 100 * all_stats["BANK_A"]["num_connections"] / all_edges
    bank_b_pct = 100 * all_stats["BANK_B"]["num_connections"] / all_edges
    consortium_pct = 100 * all_stats["CONSORTIUM"]["num_connections"] / all_edges

    print("\n" + "=" * 78)
    print(f"Bank A alone sees {bank_a_pct:.0f}% of the network. "
          f"Bank B alone sees {bank_b_pct:.0f}%.")
    print(f"The consortium sees {consortium_pct:.0f}%.")
    print("=" * 78)


# ---------------------------------------------------------------------------
# Hero ring verification — CIRC_6_HERO must be invisible per-bank, visible
# in CONSORTIUM and ALL. Verify this now, not at 4am during the demo.
# ---------------------------------------------------------------------------

def load_hero_ring_txns(tx):
    """Scoring only: ground_truth.csv is the answer key and is read here and
    nowhere else in this file."""
    gt = pd.read_csv(os.path.join(DATA_DIR, "ground_truth.csv"))
    hero_txn_ids = set(gt[gt["ring_id"] == "CIRC_6_HERO"]["txn_id"])
    return tx[tx["txn_id"].isin(hero_txn_ids)].sort_values("timestamp")


def check_hero_ring(hero_tx, view, account_to_entity, account_to_bank, entity_attrs):
    """Edge-based test. Take the ring's transactions that this view can
    actually see, map each endpoint to the node it becomes in this view, and
    ask whether those edges close a loop. No shortcuts: an opaque external
    node is allowed to take part in a cycle - if a bank could close the loop
    through one, this test would say so."""
    visible = filter_transactions(hero_tx, view)
    H = nx.DiGraph()
    for row in visible.itertuples(index=False):
        H.add_edge(
            resolve_node(row.from_account, view, account_to_entity, account_to_bank, entity_attrs),
            resolve_node(row.to_account, view, account_to_entity, account_to_bank, entity_attrs),
        )
    cycles = [c for c in nx.simple_cycles(H) if len(c) > 1]
    seen = f"sees {len(visible)} of {len(hero_tx)} hops"
    if cycles:
        # Report the largest strongly connected group: every participant in
        # it can send money round and get it back.
        loop = max(nx.strongly_connected_components(H), key=len)
        return True, f"{seen}; money returns to origin, loop links {len(loop)} participants"
    return False, f"{seen}; the loop never closes"


def print_hero_ring_report(results, hero_tx, account_to_entity):
    people = len({account_to_entity[a] for a in set(hero_tx.from_account) | set(hero_tx.to_account)})
    accounts = len(set(hero_tx.from_account) | set(hero_tx.to_account))
    entry = hero_tx.iloc[0]["amount"] / 1e7
    print("\n" + "=" * 78)
    print(f"CIRC_6_HERO check — Rs {entry:.1f} crore looping through {accounts} accounts / {people} people")
    print("=" * 78)
    for view in VIEWS:
        found, reason = results[view]
        tag = "FOUND" if found else "not found"
        print(f"  {view:<11} {tag:<10} — {reason}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    tx, account_to_entity, entity_attrs, account_to_bank = load_data()

    graphs = {}
    all_stats = {}
    for view in VIEWS:
        G = build_graph(view, tx, account_to_entity, account_to_bank, entity_attrs)
        stats = compute_stats(G, view)
        save_view(view, G, stats)
        graphs[view] = G
        all_stats[view] = stats

    print_report(all_stats, graphs)

    hero_tx = load_hero_ring_txns(tx)
    hero_results = {
        view: check_hero_ring(hero_tx, view, account_to_entity, account_to_bank, entity_attrs)
        for view in VIEWS
    }
    print_hero_ring_report(hero_results, hero_tx, account_to_entity)


if __name__ == "__main__":
    main()
