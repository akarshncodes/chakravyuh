"""
CHAKRAVYUH - Stage 5: case builder.

Turns the detector findings into a small number of cases, one per crime.
Without this step the officer would receive four separate alerts about one
crime (a circle finding, a speed finding, ...) and would have to work out by
hand that they are the same money.

Four steps, fully deterministic, no AI, no randomness:

    SEED    every structural finding (CIRCLE, SPRAY, SPEED, THRESHOLD)
    MERGE   findings that share a transaction or a person become one case
    EXPAND  add background transactions between the people involved
    PRUNE   keep exactly one ring of context around the case, drop the rest

WATCHLIST_SIGNAL findings are not seeds: they are weak hints, never claims.
They are attached to a case as a side note or become a low-priority review
item on their own (step 5).

Answer-key rule: ground_truth.csv, true_entity_id and owner_entity never
influence case building. ONLY score_cases() at the bottom of this file reads
ground_truth.csv. Score weights and thresholds come from the design and are
never tuned against the score.
"""

import json
import os
import time
from collections import defaultdict

import networkx as nx
import pandas as pd

from detectors import HOUR, prepare
from graph_builder import load_data

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DETECTIONS_PATH = os.path.join(DATA_DIR, "detections.json")
LAYOUT_PATH = os.path.join(DATA_DIR, "graphs", "ALL_layout.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "cases.json")

SEED_DETECTORS = ("CIRCLE", "SPRAY", "SPEED", "THRESHOLD")

# EXPAND: supporting transactions between core people, +/- 24h around the
# evidence. A day either side catches the settlement of a transfer or the
# repayment that explains it without dragging in the whole month.
SUPPORT_PAD = 24 * HOUR
# PRUNE: one ring of context, 48h out from the evidence, top 3 per direction.
CONTEXT_PAD = 48 * HOUR
CONTEXT_TOP_N = 3
CONTEXT_NOTE = "shown for where the money came from / went to; not accused"

# PRIORITY: fixed formula, no tuning.
PTS_PER_DETECTOR = 2
AMOUNT_TIERS = [(10_000_000, 3, "Rs 1 crore"), (1_000_000, 2, "Rs 10 lakh"), (100_000, 1, "Rs 1 lakh")]
HIGH_MIN, MEDIUM_MIN = 6, 4


# ---------------------------------------------------------------------------
# STEP 1 + 2: SEED and MERGE
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def merge_seeds(seeds):
    """Two findings join the same case if they share ANY transaction or ANY
    person. Why: a single crime routinely trips several detectors. The hero
    circle also moves fast enough to be a SPEED chain; a mule network's
    2-hop relay fragments are pieces of its SPRAY. Those are one crime seen
    from different angles, and the officer should get one case, not four."""
    uf = UnionFind(len(seeds))
    first_by_txn, first_by_person = {}, {}
    for i, f in enumerate(seeds):
        for t in f["txn_ids"]:
            uf.union(i, first_by_txn.setdefault(t, i))
        for p in f["people"]:
            uf.union(i, first_by_person.setdefault(p, i))
    groups = defaultdict(list)
    for i in range(len(seeds)):
        groups[uf.find(i)].append(seeds[i])
    return [groups[k] for k in sorted(groups)]


# ---------------------------------------------------------------------------
# STEP 3 + 4: EXPAND and PRUNE
# ---------------------------------------------------------------------------

def expand_and_prune(findings, recs, rec_by_id, entity_attrs, account_to_bank):
    core = sorted({p for f in findings for p in f["people"]})
    core_set = set(core)
    evidence_ids = sorted({t for f in findings for t in f["txn_ids"]},
                          key=lambda t: (rec_by_id[t].ts, t))
    evidence_set = set(evidence_ids)
    ev = [rec_by_id[t] for t in evidence_ids]
    first_ts, last_ts = ev[0].ts, ev[-1].ts

    # EXPAND. Evidence txns are CLAIMS: each one is cited by a detector that
    # proved a structural property from it. Supporting txns are only
    # BACKGROUND (other dealings between the same people around the same
    # time). They make the story readable for the investigator but nothing in
    # them was proven, so they are kept in a separate list and never counted
    # as evidence, in the amount, or in the priority score.
    supporting = [r for r in recs
                  if r.txn_id not in evidence_set
                  and r.from_ent in core_set and r.to_ent in core_set
                  and first_ts - SUPPORT_PAD <= r.ts <= last_ts + SUPPORT_PAD]

    # PRUNE, keeping one ring of context. A launderer's money has a source and
    # a destination outside the ring; showing the top few tells the officer
    # where to look next. Those people are marked CONTEXT and "not accused":
    # they merely sit next to the crime. Everything further out is dropped.
    into = defaultdict(list)
    out = defaultdict(list)
    for r in recs:
        if r.from_ent not in core_set and r.to_ent in core_set \
                and first_ts - CONTEXT_PAD <= r.ts <= first_ts:
            into[r.from_ent].append(r)
        elif r.from_ent in core_set and r.to_ent not in core_set \
                and last_ts <= r.ts <= last_ts + CONTEXT_PAD:
            out[r.to_ent].append(r)

    def top(groups, direction):
        ranked = sorted(groups.items(), key=lambda kv: (-sum(r.amount for r in kv[1]), kv[0]))
        return [{
            "entity_key": p,
            "name": entity_attrs[p]["canonical_name"],
            "role": "CONTEXT",
            "direction": direction,
            "amount": round(sum(r.amount for r in rs), 2),
            "note": CONTEXT_NOTE,
        } for p, rs in ranked[:CONTEXT_TOP_N]], [r for _, rs in ranked[:CONTEXT_TOP_N] for r in rs]

    ctx_in, ctx_in_txns = top(into, "IN")
    ctx_out, ctx_out_txns = top(out, "OUT")

    banks = sorted({account_to_bank[a] for r in ev for a in (r.from_acc, r.to_acc)})
    return {
        "core": core,
        "evidence": ev,
        "supporting": sorted(supporting, key=lambda r: (r.ts, r.txn_id)),
        "context_people": ctx_in + ctx_out,
        "context_txns": sorted(ctx_in_txns + ctx_out_txns, key=lambda r: (r.ts, r.txn_id)),
        "banks": banks,
        "crosses_banks": any(r.from_acc != r.to_acc and account_to_bank[r.from_acc] != account_to_bank[r.to_acc]
                             for r in ev),
    }


# ---------------------------------------------------------------------------
# PRIORITY
# ---------------------------------------------------------------------------

def priority(detectors, amount, any_watchlisted, crosses_banks):
    reasons, score = [], 0
    pts = PTS_PER_DETECTOR * len(detectors)
    score += pts
    reasons.append(f"+{pts} {len(detectors)} distinct detector(s) fired ({', '.join(detectors)})")
    for floor, p, label in AMOUNT_TIERS:
        if amount >= floor:
            score += p
            reasons.append(f"+{p} evidence amount Rs {amount:,.0f} is at least {label}")
            break
    if any_watchlisted:
        score += 1
        reasons.append("+1 a core person is watchlisted")
    if crosses_banks:
        score += 1
        reasons.append("+1 evidence transactions cross both banks")
    level = "HIGH" if score >= HIGH_MIN else "MEDIUM" if score >= MEDIUM_MIN else "LOW"
    return score, level, reasons


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def case_layout(core, ctx_people, txns):
    """Spring layout of the case's own small subgraph, computed here once so
    the dashboard never computes anything live."""
    nodes = sorted(set(core) | {c["entity_key"] for c in ctx_people})
    G = nx.Graph()
    G.add_nodes_from(nodes)
    for r in txns:
        if r.from_ent in G and r.to_ent in G and r.from_ent != r.to_ent:
            G.add_edge(r.from_ent, r.to_ent)
    pos = nx.spring_layout(G, seed=42)
    return {n: [float(x), float(y)] for n, (x, y) in sorted(pos.items())}


def build_cases(findings, recs, entity_attrs, account_to_bank):
    rec_by_id = {r.txn_id: r for r in recs}
    seeds = [f for f in findings if f["detector"] in SEED_DETECTORS]
    signals = [f for f in findings if f["detector"] == "WATCHLIST_SIGNAL"]

    cases = []
    for group in merge_seeds(seeds):
        x = expand_and_prune(group, recs, rec_by_id, entity_attrs, account_to_bank)
        ev = x["evidence"]
        amount = round(sum(r.amount for r in ev), 2)
        detectors = sorted({f["detector"] for f in group})
        watched = any(entity_attrs[p]["is_watchlisted"] for p in x["core"])
        score, level, reasons = priority(detectors, amount, watched, x["crosses_banks"])
        core_people = [{
            "entity_key": p,
            "name": entity_attrs[p]["canonical_name"],
            "role": "CORE",
            "is_watchlisted": entity_attrs[p]["is_watchlisted"],
            "accounts": entity_attrs[p]["account_ids"],
        } for p in x["core"]]
        layout_txns = ev + x["supporting"] + x["context_txns"]
        cases.append({
            "case_id": None,
            "lane": "WATCHLIST" if watched else "DISCOVERY",
            "detectors_fired": detectors,
            "finding_ids": sorted(f["finding_id"] for f in group),
            "core_people": core_people,
            "context_people": x["context_people"],
            "evidence_txn_ids": [r.txn_id for r in ev],
            "supporting_txn_ids": [r.txn_id for r in x["supporting"]],
            "context_txn_ids": [r.txn_id for r in x["context_txns"]],
            "total_evidence_amount": amount,
            "first_timestamp": ev[0].ts_str,
            "last_timestamp": ev[-1].ts_str,
            "hours_spanned": round((ev[-1].ts - ev[0].ts) / HOUR, 2),
            "banks_involved": x["banks"],
            "crosses_banks": x["crosses_banks"],
            "priority_score": score,
            "priority_level": level,
            "priority_reason": reasons,
            "watchlist_signals": [],
            "layout": case_layout(x["core"], x["context_people"], layout_txns),
            "highlight_nodes": sorted(set(x["core"]) | {c["entity_key"] for c in x["context_people"]}),
        })

    cases.sort(key=lambda c: (-c["priority_score"], -c["total_evidence_amount"], c["evidence_txn_ids"][0]))
    for n, c in enumerate(cases, 1):
        c["case_id"] = f"C{n:03d}"

    # STEP 5. A watchlist signal is a weak hint about a known person. If that
    # person is in a case, it is attached as a side note (never as evidence,
    # so it can never raise an accusation or the evidence amount). If nobody
    # in a case is involved it becomes a low-priority review item, not a case.
    review = []
    for s in signals:
        attached = False
        for c in cases:
            core_keys = {p["entity_key"] for p in c["core_people"]}
            if core_keys & set(s["people"]):
                c["watchlist_signals"].append({
                    "finding_id": s["finding_id"], "people": s["people"],
                    "reason": s["reason"], "evidence": s["evidence"],
                })
                attached = True
        if not attached:
            review.append({
                "finding_id": s["finding_id"], "type": "WATCHLIST_REVIEW", "priority": "LOW",
                "people": s["people"], "txn_ids": s["txn_ids"],
                "reason": s["reason"], "evidence": s["evidence"],
                "note": "low priority review item; not a case, no accusation",
            })
    return cases, review


# ---------------------------------------------------------------------------
# SCORING - the ONLY code allowed to read ground_truth.csv
# ---------------------------------------------------------------------------

def score_cases(cases, findings, recs, account_to_entity):
    gt = pd.read_csv(os.path.join(DATA_DIR, "ground_truth.csv"))
    rings = {rid: set(g["txn_id"]) for rid, g in gt.groupby("ring_id", sort=False)}
    ring_of_txn = {t: rid for rid, ts in rings.items() for t in ts}
    rec_by_id = {r.txn_id: r for r in recs}
    ring_members = {rid: {account_to_entity[a] for t in ts
                          for a in (rec_by_id[t].from_acc, rec_by_id[t].to_acc)}
                    for rid, ts in rings.items()}
    all_members = set().union(*ring_members.values())

    per_case = {}
    ring_cases = defaultdict(set)
    for c in cases:
        counts = defaultdict(int)
        for t in c["evidence_txn_ids"]:
            if t in ring_of_txn:
                counts[ring_of_txn[t]] += 1
        for rid in counts:
            ring_cases[rid].add(c["case_id"])
        main = max(sorted(counts), key=lambda r: counts[r]) if counts else None
        purity = counts[main] / len(c["evidence_txn_ids"]) if main else 0.0
        per_case[c["case_id"]] = {"main_ring": main, "purity": purity, "rings": sorted(counts)}

    split = {rid: sorted(cs) for rid, cs in ring_cases.items() if len(cs) > 1}
    mixed = {cid: v["rings"] for cid, v in per_case.items() if len(v["rings"]) > 1}

    core_total = core_members = 0
    innocent = []
    for c in cases:
        for p in c["core_people"]:
            core_total += 1
            if p["entity_key"] in all_members:
                core_members += 1
            else:
                innocent.append((p["entity_key"], p["name"], c["case_id"]))

    # Rings the detectors caught (Stage 4 rule: one structural finding covers
    # >=50% of the ring), and how many of those are covered by a single case.
    caught = [rid for rid, ts in rings.items()
              if any(f["detector"] in SEED_DETECTORS and len(set(f["txn_ids"]) & ts) >= 0.5 * len(ts)
                     for f in findings)]
    covered = [rid for rid in caught
               if any(len(set(c["evidence_txn_ids"]) & rings[rid]) >= 0.5 * len(rings[rid]) for c in cases)]

    hero = rings["CIRC_6_HERO"]
    hero_cases = [c for c in cases if hero <= set(c["evidence_txn_ids"])]
    return {
        "per_case": per_case, "split": split, "mixed": mixed,
        "precision": (core_members, core_total), "innocent": innocent,
        "caught": caught, "covered": covered,
        "hero_cases": hero_cases, "hero_people": ring_members["CIRC_6_HERO"],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(findings, cases, review, sc, elapsed):
    n_seed = sum(1 for f in findings if f["detector"] in SEED_DETECTORS)
    print("=" * 78)
    print("CHAKRAVYUH - Stage 5: case builder")
    print("=" * 78)
    print(f"{len(findings)} findings became {len(cases)} cases (+{len(review)} watchlist review items)"
          f"   [{n_seed} structural findings were seeds]\n")

    print(f"{'case':<5} {'prio':<12} {'detectors':<26} {'core':>4} {'ctx':>4} {'amount (Rs)':>16} "
          f"{'hours':>7}  {'main ring':<16} {'purity':>6}")
    for c in cases:
        s = sc["per_case"][c["case_id"]]
        print(f"{c['case_id']:<5} {c['priority_level'] + ' ' + str(c['priority_score']):<12} "
              f"{'+'.join(d[:4] for d in c['detectors_fired']):<26} {len(c['core_people']):>4} "
              f"{len(c['context_people']):>4} {c['total_evidence_amount']:>16,.0f} "
              f"{c['hours_spanned']:>7.1f}  {s['main_ring'] or '-':<16} {s['purity'] * 100:>5.0f}%")

    m, t = sc["precision"]
    print(f"\nSplit rings:   {len(sc['split'])}" + (f"  {sc['split']}" if sc["split"] else ""))
    print(f"Mixed cases:   {len(sc['mixed'])}" + (f"  {sc['mixed']}" if sc["mixed"] else ""))
    print(f"Rings covered: {len(sc['covered'])} of {len(sc['caught'])} caught rings map to a case")
    print(f"Accused precision: {m}/{t} core people are ring members ({m / t * 100:.1f}%)")
    for key, name, cid in sc["innocent"]:
        print(f"  NOT a ring member: {key} {name} (in {cid})")

    print("\nHero check")
    hc = sc["hero_cases"]
    if len(hc) != 1:
        print(f"  {len(hc)} cases contain all 6 hero txns (expected exactly 1)")
    for c in hc:
        core = {p["entity_key"] for p in c["core_people"]}
        print(f"  {c['case_id']}: {c['priority_level']} ({c['priority_score']}), 6/6 hero txns as evidence, "
              f"{len(core)} core people (exactly the hero people: {core == sc['hero_people']}), "
              f"crosses both banks: {c['crosses_banks']}")
        for line in c["priority_reason"]:
            print(f"    {line}")
        print("    context people (not accused):")
        for p in c["context_people"]:
            print(f"      {p['direction']:<3} {p['entity_key']} {p['name']}  Rs {p['amount']:,.0f}")
        print(f"    watchlist signals attached: {len(c['watchlist_signals'])}")
    print(f"\nRuntime: {elapsed:.1f}s")


def main():
    t0 = time.time()
    with open(DETECTIONS_PATH) as fh:
        findings = json.load(fh)
    tx, account_to_entity, entity_attrs, account_to_bank = load_data()
    _, recs = prepare(tx, account_to_entity)

    cases, review = build_cases(findings, recs, entity_attrs, account_to_bank)

    # The dashboard highlights case nodes on the full map, so every highlight
    # node must exist in the ALL layout.
    with open(LAYOUT_PATH) as fh:
        all_layout = json.load(fh)
    missing = {n for c in cases for n in c["highlight_nodes"]} - set(all_layout)
    assert not missing, f"highlight nodes missing from graphs/ALL_layout.json: {sorted(missing)[:5]}"

    with open(OUTPUT_PATH, "w") as fh:
        json.dump({"cases": cases, "watchlist_review": review}, fh, indent=2, ensure_ascii=False)

    sc = score_cases(cases, findings, recs, account_to_entity)
    print_report(findings, cases, review, sc, time.time() - t0)


if __name__ == "__main__":
    main()
