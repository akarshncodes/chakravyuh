"""
CHAKRAVYUH - Stage 4: detection swarm.

Four deterministic detectors, each hunting one laundering shape. No AI, no
machine learning, no randomness: the same input always gives the same
findings, and every finding names the exact transactions that prove it, so a
regulator can re-check it by hand with a calculator and the CSV.

    CIRCLE     money that leaves a person and comes back to them
    SPRAY      mule fan-out / fan-in
    SPEED      money that never rests (hop after hop within the hour)
    THRESHOLD  structuring just under the Indian reporting limits

Plus one aggregated WATCHLIST_SIGNAL finding per watchlisted person, listing
weak signals that are too soft to be a laundering claim on their own.

Two lanes
---------
DISCOVERY  the full thresholds, applied to everyone. Finds rings that contain
           nobody previously known.
WATCHLIST  if ANY person in a would-be finding is on the watchlist, a lower
           bar applies (enhanced due diligence: a known high-risk person needs
           less circumstantial evidence before we look closer).

Answer-key rule: ground_truth.csv, true_entity_id and owner_entity must never
influence detection. accounts.csv is loaded with usecols so owner_entity and
name never enter memory. ONLY the scoring section at the bottom of this file
reads ground_truth.csv. Thresholds come from the design and from real rules;
they are never tuned against the score.
"""

import bisect
import json
import os
import sys
import time
from collections import defaultdict, namedtuple

import pandas as pd

from graph_builder import (
    AMOUNT_BAND_EDGES,
    amount_band,
    filter_transactions,
    hour_bucket,
    load_data,
    resolve_node,
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(DATA_DIR, "detections.json")

sys.setrecursionlimit(10_000)

HOUR = 3600
DAY = 24 * HOUR
EPS = 1e-6  # float slack when comparing amounts that were rounded to paise

# ---------------------------------------------------------------------------
# Thresholds. Every number below has a real-world reason; none of them is
# adjusted after seeing a score.
# ---------------------------------------------------------------------------

# CIRCLE ---------------------------------------------------------------
# Layering is done quickly: the launderer wants the money back before an
# account freeze or a reconciliation. 72 hours covers a weekend of slow
# NEFT/IMPS settlement but not the months-long loops of genuine business
# credit cycles.
CIRCLE_WINDOW_HOURS = 72
# Each hop skims a little (fees, or a cut for the mule) but nobody gives away
# more than ~15% per hop: below 85% the money is being consumed, not moved.
# Above 100% the amount grew, which a pure pass-through cannot do.
CIRCLE_MIN_RETENTION = 0.85
CIRCLE_MAX_RETENTION = 1.00
# 2 hops is just a refund or a reversal (A pays B, B pays back). 3 is the
# smallest loop that can't be explained as a return. Beyond 8 the chance of
# coincidental matches in a busy graph overwhelms the signal.
CIRCLE_MIN_HOPS = 3
CIRCLE_MAX_HOPS = 8

# SPRAY ----------------------------------------------------------------
# A mule herder spreads one large sum across many accounts so that no single
# transfer looks unusual. Eight distinct receivers inside six hours is far
# beyond normal payroll-style behaviour for a retail account.
SPRAY_MIN_RECEIVERS = 8
SPRAY_MIN_RECEIVERS_WATCHLIST = 4
SPRAY_WINDOW_HOURS = 6
# Fan-in: mules exist only to forward the money on. 60% of receivers doing so
# (not 100%) tolerates a few mules who pocket the money or get frozen.
SPRAY_MIN_FORWARD_SHARE = 0.60
# A mule keeps a small cut at most (90-100% forwarded), and forwards fast
# (within the hour) because it holds the money on the launderer's behalf.
SPRAY_FORWARD_MIN_RETENTION = 0.90
SPRAY_FORWARD_MINUTES = 60

# SPEED ----------------------------------------------------------------
# Legitimate money rests: salaries sit, invoices are paid on terms. A chain
# where each receiver re-sends 90-100% within the hour is a relay, not a
# customer. 3 hops means two different intermediaries touched it.
SPEED_LINK_MINUTES = 60
SPEED_LINK_MIN_RETENTION = 0.90
SPEED_MIN_HOPS = 3
SPEED_MIN_HOPS_WATCHLIST = 2

# THRESHOLD ------------------------------------------------------------
# Real Indian limits. Rs 10,00,000 is the Cash Transaction Report level for
# cash deposits/withdrawals; Rs 50,000 is where PAN must be quoted for a cash
# deposit. Structuring is repeatedly staying just under a limit (90-100% of
# it) to avoid triggering the paperwork. Five in a rolling week is a pattern;
# one or two is somebody's shop takings.
THRESHOLD_LIMITS = (1_000_000.0, 50_000.0)
THRESHOLD_BAND_LOW = 0.90
THRESHOLD_MIN_DEPOSITS = 5
THRESHOLD_MIN_DEPOSITS_WATCHLIST = 3
THRESHOLD_WINDOW_DAYS = 7

# WATCHLIST_SIGNAL -------------------------------------------------------
# Rs 1 lakh is the customary "large value" bar for a first-time payee.
SIGNAL_FIRST_TRANSFER_MIN = 100_000.0
# An account opened in the last month that receives money from a high-risk
# person is a classic fresh mule account.
SIGNAL_NEW_ACCOUNT_DAYS = 30
# A person's habits are set in their first fortnight of history; a channel
# they never used before suddenly appearing is a change in behaviour.
SIGNAL_BASELINE_DAYS = 15

BAND_ORDER = [label for _, label in AMOUNT_BAND_EDGES] + ["50L_PLUS"]
BAND_INDEX = {label: i for i, label in enumerate(BAND_ORDER)}

Rec = namedtuple("Rec", "i txn_id ts ts_str from_acc to_acc amount channel from_ent to_ent")
Row = namedtuple("Row", "txn_id ts from_key to_key amount from_node to_node band hour_ts")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def prepare(tx, account_to_entity):
    tx = tx.sort_values(["timestamp", "txn_id"], kind="stable").reset_index(drop=True)
    epoch = ((tx["timestamp"] - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).tolist()
    ts_str = tx["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
    recs = []
    for i, row in enumerate(tx.itertuples(index=False)):
        recs.append(Rec(
            i, row.txn_id, int(epoch[i]), ts_str[i], row.from_account, row.to_account,
            float(row.amount), row.channel,
            account_to_entity[row.from_account], account_to_entity[row.to_account],
        ))
    return tx, recs


def load_account_ages():
    # usecols keeps owner_entity and name (the answer key) out of memory.
    accounts = pd.read_csv(os.path.join(DATA_DIR, "accounts.csv"),
                           usecols=["account_id", "bank", "opened_days_ago"])
    return dict(zip(accounts.account_id, accounts.opened_days_ago))


def index_outgoing(recs, key=lambda r: r.from_acc):
    by_key = defaultdict(list)
    for r in recs:
        by_key[key(r)].append(r.i)
    ts_by_key = {k: [recs[i].ts for i in v] for k, v in by_key.items()}
    return by_key, ts_by_key


# ---------------------------------------------------------------------------
# Finding helpers
# ---------------------------------------------------------------------------

def money(x):
    return f"Rs {x:,.0f}"


def make_finding(detector, used, watch, evidence, names, lane=None):
    used = sorted(used, key=lambda r: (r.ts, r.txn_id))
    people = sorted({r.from_ent for r in used} | {r.to_ent for r in used})
    accounts = sorted({r.from_acc for r in used} | {r.to_acc for r in used})
    if lane is None:
        lane = "WATCHLIST" if any(p in watch for p in people) else "DISCOVERY"
    return {
        "finding_id": None,
        "detector": detector,
        "lane": lane,
        "people": people,
        "accounts": accounts,
        "txn_ids": [r.txn_id for r in used],
        "total_amount": round(sum(r.amount for r in used), 2),
        "first_timestamp": used[0].ts_str,
        "last_timestamp": used[-1].ts_str,
        "evidence": evidence,
        "reason": None,
    }


def person_label(entity, names):
    return f"{names.get(entity, entity)} ({entity})"


# ---------------------------------------------------------------------------
# DETECTOR 1 - CIRCLE
# ---------------------------------------------------------------------------

def find_circle_cycles(rows, bucketed=False):
    """Temporal walk at transaction level. From every transaction t0 sent by
    person P0, follow outgoing transactions from the receiving account. The
    path closes when money reaches P0 again after 3-8 hops; the walk keeps
    going (to 8 hops) in case it returns again. Returns maximal cycles only,
    as lists of Row indices, each with rotations already collapsed.

    bucketed=False: exact amounts and timestamps, continuity per account.
    bucketed=True:  the consortium's coarser knowledge. Only amount bands and
                    hour buckets are shared, and there are no account numbers,
                    so amounts must sit in the same or an adjacent band, the
                    hour bucket must not go backwards, and continuity is per
                    pseudonym."""
    by_key = defaultdict(list)
    for i, r in enumerate(rows):
        by_key[r.from_key].append(i)
    ts_by_key = {k: [rows[i].ts for i in v] for k, v in by_key.items()}
    window = CIRCLE_WINDOW_HOURS * HOUR

    found = {}  # frozenset(txn_ids) -> ordered path of row indices

    for s, r0 in enumerate(rows):
        origin = r0.from_node
        t_start = r0.hour_ts if bucketed else r0.ts
        t_limit = t_start + window
        path = [s]
        seen_states = set() if bucketed else None

        def walk(last):
            hops = len(path)
            lr = rows[last]
            if lr.to_node == origin and hops >= CIRCLE_MIN_HOPS:
                found.setdefault(frozenset(rows[p].txn_id for p in path), list(path))
            if hops >= CIRCLE_MAX_HOPS:
                return
            idxs = by_key.get(lr.to_key)
            if not idxs:
                return
            ts_list = ts_by_key[lr.to_key]
            if bucketed:
                lo = bisect.bisect_left(ts_list, lr.hour_ts)
                hi = bisect.bisect_left(ts_list, t_limit + HOUR)
            else:
                lo = bisect.bisect_right(ts_list, lr.ts)
                hi = bisect.bisect_right(ts_list, t_limit)
            for c in idxs[lo:hi]:
                cr = rows[c]
                if bucketed:
                    if cr.hour_ts < lr.hour_ts or cr.hour_ts > t_limit:
                        continue
                    if abs(cr.band - lr.band) > 1:
                        continue
                    if c in path:
                        continue
                    state = (c, hops + 1)
                    if state in seen_states:
                        continue
                    seen_states.add(state)
                else:
                    if not (CIRCLE_MIN_RETENTION * lr.amount - EPS
                            <= cr.amount <= CIRCLE_MAX_RETENTION * lr.amount + EPS):
                        continue
                path.append(c)
                walk(c)
                path.pop()

        walk(s)

    # Keep only maximal cycles: drop any whose txn set is a subset of another.
    ordered = sorted(found.items(), key=lambda kv: (-len(kv[0]), sorted(kv[0])))
    kept = []
    by_txn = defaultdict(list)
    for txn_set, path in ordered:
        first = next(iter(txn_set))
        if any(txn_set <= k for k in by_txn[first]):
            continue
        kept.append((txn_set, path))
        for t in txn_set:
            by_txn[t].append(txn_set)
    return kept


def detect_circle(recs, watch, names):
    rows = [Row(r.txn_id, r.ts, r.from_acc, r.to_acc, r.amount, r.from_ent, r.to_ent, 0, r.ts)
            for r in recs]
    findings = []
    for txn_set, path in find_circle_cycles(rows, bucketed=False):
        used = [recs[p] for p in path]
        retentions = [used[k].amount / used[k - 1].amount * 100 for k in range(1, len(used))]
        origin = used[0].from_ent
        hours = (used[-1].ts - used[0].ts) / HOUR
        evidence = {
            "hops": len(used),
            "hours_elapsed": round(hours, 2),
            "min_retention_pct": round(min(retentions), 2),
            "first_hop_amount": used[0].amount,
            "last_hop_amount": used[-1].amount,
            "origin_person": origin,
            "distinct_people": len({r.from_ent for r in used}),
        }
        f = make_finding("CIRCLE", used, watch, evidence, names)
        f["reason"] = (f"{evidence['hops']}-hop circle: {money(evidence['first_hop_amount'])} left "
                       f"{person_label(origin, names)} and came back to them after "
                       f"{evidence['hours_elapsed']} hours via {evidence['distinct_people']} people, "
                       f"every hop keeping at least {evidence['min_retention_pct']}% of the previous amount.")
        findings.append(f)
    return findings


# ---------------------------------------------------------------------------
# DETECTOR 2 - SPRAY
# ---------------------------------------------------------------------------

def detect_spray(recs, watch, names):
    """One source account sends to many DISTINCT receiving accounts (accounts,
    not people: a herder often controls several mule accounts) inside six
    hours, and most receivers then forward nearly all of it, fast, to the SAME
    collector account. Two halves, both required: fan-out alone is payroll,
    fan-in alone is a merchant."""
    by_acc, ts_by_acc = index_outgoing(recs)
    window = SPRAY_WINDOW_HOURS * HOUR
    best = {}  # (source, collector) -> candidate

    def find_forward(r):
        idxs = by_acc.get(r.to_acc)
        if not idxs:
            return None
        ts_list = ts_by_acc[r.to_acc]
        lo = bisect.bisect_right(ts_list, r.ts)
        hi = bisect.bisect_right(ts_list, r.ts + SPRAY_FORWARD_MINUTES * 60)
        for j in idxs[lo:hi]:
            amt = recs[j].amount
            if SPRAY_FORWARD_MIN_RETENTION * r.amount - EPS <= amt <= r.amount + EPS:
                return j
        return None

    for src in sorted(by_acc):
        idxs = by_acc[src]
        if len(idxs) < SPRAY_MIN_RECEIVERS_WATCHLIST:
            continue
        ts_list = ts_by_acc[src]
        for a, i in enumerate(idxs):
            hi = bisect.bisect_right(ts_list, recs[i].ts + window)
            win = idxs[a:hi]
            receivers = {recs[j].to_acc for j in win}
            if len(receivers) < SPRAY_MIN_RECEIVERS_WATCHLIST:
                continue

            forwarded = {}  # receiving account -> (spray idx, forward idx)
            for j in win:
                acc = recs[j].to_acc
                if acc not in forwarded:
                    f = find_forward(recs[j])
                    if f is not None:
                        forwarded[acc] = (j, f)
            by_collector = defaultdict(list)
            for acc, (j, f) in forwarded.items():
                by_collector[recs[f].to_acc].append(acc)

            for collector, mules in sorted(by_collector.items()):
                if len(mules) < SPRAY_MIN_FORWARD_SHARE * len(receivers) - EPS:
                    continue
                used = []
                for acc in mules:
                    j, f = forwarded[acc]
                    used += [recs[j], recs[f]]
                people = {r.from_ent for r in used} | {r.to_ent for r in used}
                required = (SPRAY_MIN_RECEIVERS_WATCHLIST if any(p in watch for p in people)
                            else SPRAY_MIN_RECEIVERS)
                if len(receivers) < required:
                    continue
                key = (src, collector)
                cand = (len(mules), -recs[i].ts)
                if key not in best or cand > best[key][0]:
                    best[key] = (cand, used, len(receivers), mules, required, src, collector)

    findings = []
    for key in sorted(best):
        _, used, n_recv, mules, required, src, collector = best[key]
        spray = [r for r in used if r.from_acc == src]
        fwd = [r for r in used if r.from_acc != src]
        recv_by_mule = {r.to_acc: r for r in spray}
        delays, rets = [], []
        for r in fwd:
            s_r = recv_by_mule[r.from_acc]
            delays.append((r.ts - s_r.ts) / 60)
            rets.append(r.amount / s_r.amount * 100)
        evidence = {
            "source_account": src,
            "collector_account": collector,
            "receivers": n_recv,
            "forwarding_mules": len(mules),
            "forward_pct": round(len(mules) / n_recv * 100, 1),
            "spray_window_hours": round((max(r.ts for r in spray) - min(r.ts for r in spray)) / HOUR, 2),
            "min_forward_retention_pct": round(min(rets), 2),
            "max_forward_delay_minutes": round(max(delays), 1),
            "min_receivers_required": required,
        }
        f = make_finding("SPRAY", used, watch, evidence, names)
        f["reason"] = (f"Account {src} sent to {n_recv} distinct accounts within "
                       f"{evidence['spray_window_hours']} hours; {len(mules)} of them "
                       f"({evidence['forward_pct']}%) forwarded at least "
                       f"{evidence['min_forward_retention_pct']}% within "
                       f"{evidence['max_forward_delay_minutes']} minutes to the same collector {collector}.")
        findings.append(f)
    return findings


# ---------------------------------------------------------------------------
# DETECTOR 3 - SPEED
# ---------------------------------------------------------------------------

def detect_speed(recs, watch, names):
    """Link a->b to b->c when b->c follows within 60 minutes and carries 90-100%
    of the amount. Report maximal chains of 3+ consecutive linked hops (2+ when
    a watchlisted person is on the chain). Money that never rests is being
    relayed, not used."""
    by_acc, ts_by_acc = index_outgoing(recs)
    n = len(recs)
    succ = [[] for _ in range(n)]
    has_pred = [False] * n
    for r in recs:
        idxs = by_acc.get(r.to_acc)
        if not idxs:
            continue
        ts_list = ts_by_acc[r.to_acc]
        lo = bisect.bisect_right(ts_list, r.ts)
        hi = bisect.bisect_right(ts_list, r.ts + SPEED_LINK_MINUTES * 60)
        for j in idxs[lo:hi]:
            if SPEED_LINK_MIN_RETENTION * r.amount - EPS <= recs[j].amount <= r.amount + EPS:
                succ[r.i].append(j)
                has_pred[j] = True

    findings = []
    path = []

    def emit():
        used = [recs[p] for p in path]
        people = {r.from_ent for r in used} | {r.to_ent for r in used}
        required = SPEED_MIN_HOPS_WATCHLIST if any(p in watch for p in people) else SPEED_MIN_HOPS
        if len(used) < required:
            return
        gaps = [(used[k].ts - used[k - 1].ts) / 60 for k in range(1, len(used))]
        rets = [used[k].amount / used[k - 1].amount * 100 for k in range(1, len(used))]
        evidence = {
            "hops": len(used),
            "minutes_elapsed": round((used[-1].ts - used[0].ts) / 60, 1),
            "min_retention_pct": round(min(rets), 2),
            "max_gap_minutes": round(max(gaps), 1),
            "start_amount": used[0].amount,
            "end_amount": used[-1].amount,
            "min_hops_required": required,
        }
        f = make_finding("SPEED", used, watch, evidence, names)
        f["reason"] = (f"{evidence['hops']}-hop chain moved {money(evidence['start_amount'])} onward in "
                       f"{evidence['minutes_elapsed']} minutes, no hop waiting more than "
                       f"{evidence['max_gap_minutes']} minutes and each keeping at least "
                       f"{evidence['min_retention_pct']}% of the previous amount.")
        findings.append(f)

    def dfs(i):
        path.append(i)
        if not succ[i]:
            emit()
        else:
            for j in succ[i]:
                dfs(j)
        path.pop()

    for i in range(n):
        if not has_pred[i] and succ[i]:
            dfs(i)
    return findings


# ---------------------------------------------------------------------------
# DETECTOR 4 - THRESHOLD
# ---------------------------------------------------------------------------

def detect_threshold(recs, watch, names):
    """A receiving person gets 5+ CASH transactions inside a rolling 7 days,
    each between 90% and 100% of the same limit (3+ if a watchlisted person is
    involved). All transactions that sit in at least one qualifying window are
    reported together as one finding per person and limit."""
    cash_in = defaultdict(list)
    for r in recs:
        if r.channel == "CASH":
            cash_in[r.to_ent].append(r)

    window = THRESHOLD_WINDOW_DAYS * DAY
    findings = []
    for ent in sorted(cash_in):
        for limit in THRESHOLD_LIMITS:
            cand = [r for r in cash_in[ent] if THRESHOLD_BAND_LOW * limit - EPS <= r.amount <= limit + EPS]
            if len(cand) < THRESHOLD_MIN_DEPOSITS_WATCHLIST:
                continue
            ts_list = [r.ts for r in cand]
            flagged = set()
            max_in_window = 0
            required_used = THRESHOLD_MIN_DEPOSITS
            for a in range(len(cand)):
                hi = bisect.bisect_right(ts_list, cand[a].ts + window)
                win = cand[a:hi]
                people = {ent} | {r.from_ent for r in win}
                required = (THRESHOLD_MIN_DEPOSITS_WATCHLIST if any(p in watch for p in people)
                            else THRESHOLD_MIN_DEPOSITS)
                if len(win) >= required:
                    flagged.update(r.i for r in win)
                    if len(win) > max_in_window:
                        max_in_window = len(win)
                        required_used = required
            if not flagged:
                continue
            used = [recs[i] for i in sorted(flagged)]
            pcts = [r.amount / limit * 100 for r in used]
            evidence = {
                "limit": limit,
                "deposits_in_window": max_in_window,
                "flagged_deposits": len(used),
                "window_days": THRESHOLD_WINDOW_DAYS,
                "min_pct_of_limit": round(min(pcts), 2),
                "max_pct_of_limit": round(max(pcts), 2),
                "min_deposits_required": required_used,
                "receiving_person": ent,
            }
            f = make_finding("THRESHOLD", used, watch, evidence, names)
            f["reason"] = (f"{person_label(ent, names)} received {max_in_window} cash deposits within "
                           f"{THRESHOLD_WINDOW_DAYS} days, each {evidence['min_pct_of_limit']}-"
                           f"{evidence['max_pct_of_limit']}% of the {money(limit)} limit "
                           f"({evidence['flagged_deposits']} such deposits in total).")
            findings.append(f)
    return findings


# ---------------------------------------------------------------------------
# WATCHLIST_SIGNAL
# ---------------------------------------------------------------------------

def detect_watchlist_signals(recs, watch, names, account_age):
    """One aggregated finding per watchlisted person, only if at least one weak
    signal is present. These are deliberately soft: they say "look closer at
    this known high-risk person", not "this is laundering"."""
    first_pair_idx = {}
    for r in recs:
        if r.from_ent == r.to_ent:
            continue
        pair = (min(r.from_ent, r.to_ent), max(r.from_ent, r.to_ent))
        first_pair_idx.setdefault(pair, r.i)

    sent = defaultdict(list)
    for r in recs:
        if r.from_ent in watch:
            sent[r.from_ent].append(r)

    findings = []
    for ent in sorted(sent):
        out = sent[ent]

        # Signal 1: first-ever transfer >= Rs 1 lakh to someone never dealt with.
        first_big = []
        for r in out:
            if r.to_ent == ent or r.amount < SIGNAL_FIRST_TRANSFER_MIN:
                continue
            if first_pair_idx[(min(r.from_ent, r.to_ent), max(r.from_ent, r.to_ent))] == r.i:
                first_big.append(r)

        # Signal 2: money sent into an account opened <= 30 days ago.
        new_acct = [r for r in out if account_age.get(r.to_acc, 10**9) <= SIGNAL_NEW_ACCOUNT_DAYS]

        # Signal 3: a channel not used in the person's first 15 days of history.
        start = out[0].ts
        baseline = {r.channel for r in out if r.ts <= start + SIGNAL_BASELINE_DAYS * DAY}
        new_channel = [r for r in out if r.ts > start + SIGNAL_BASELINE_DAYS * DAY
                       and r.channel not in baseline]

        signals = {
            "first_large_transfer_to_new_counterparty": first_big,
            "money_into_new_account": new_acct,
            "new_channel_after_baseline": new_channel,
        }
        present = {k: v for k, v in signals.items() if v}
        if not present:
            continue
        used = {r.i: r for v in present.values() for r in v}.values()
        evidence = {
            "signals": sorted(present),
            "signal_txn_counts": {k: len(v) for k, v in sorted(present.items())},
            "signal_txn_ids": {k: [r.txn_id for r in v] for k, v in sorted(present.items())},
            "new_channels": sorted({r.channel for r in new_channel}),
        }
        f = make_finding("WATCHLIST_SIGNAL", used, watch, evidence, names, lane="WATCHLIST")
        f["reason"] = (f"Watchlisted {person_label(ent, names)} shows {len(present)} weak signal(s): "
                       + "; ".join(f"{k.replace('_', ' ')} x{len(v)}" for k, v in sorted(present.items())) + ".")
        findings.append(f)
    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_detectors(recs, entity_attrs, account_age):
    watch = {e for e, a in entity_attrs.items() if a["is_watchlisted"]}
    names = {e: a["canonical_name"] for e, a in entity_attrs.items()}

    findings = []
    findings += detect_circle(recs, watch, names)
    findings += detect_spray(recs, watch, names)
    findings += detect_speed(recs, watch, names)
    findings += detect_threshold(recs, watch, names)
    findings += detect_watchlist_signals(recs, watch, names, account_age)

    findings.sort(key=lambda f: (-f["total_amount"], f["detector"], f["txn_ids"][0]))
    for n, f in enumerate(findings, 1):
        f["finding_id"] = f"F{n:04d}"
    return findings


def write_detections(findings):
    with open(OUTPUT_PATH, "w") as fh:
        json.dump(findings, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Hero check helpers (detection logic only; the ground-truth lookup is in the
# scoring section below)
# ---------------------------------------------------------------------------

def build_view_rows(tx_sorted, view, account_to_entity, account_to_bank, entity_attrs):
    node_of = {acc: resolve_node(acc, view, account_to_entity, account_to_bank, entity_attrs)
               for acc in account_to_entity}
    ftx = filter_transactions(tx_sorted, view)
    epoch = ((ftx["timestamp"] - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).tolist()

    hour_cache = {}

    def hour_epoch(ts_s):
        h = ts_s - ts_s % HOUR
        if h not in hour_cache:
            label = hour_bucket(pd.Timestamp(h, unit="s"))  # graph_builder's own bucketing
            hour_cache[h] = int((pd.Timestamp(label) - pd.Timestamp("1970-01-01")).total_seconds())
        return hour_cache[h]

    bucketed = view == "CONSORTIUM"
    rows = []
    for k, r in enumerate(ftx.itertuples(index=False)):
        fn, tn = node_of[r.from_account], node_of[r.to_account]
        band = BAND_INDEX[amount_band(float(r.amount))]
        rows.append(Row(
            r.txn_id, int(epoch[k]),
            fn if bucketed else r.from_account,
            tn if bucketed else r.to_account,
            float(r.amount), fn, tn, band, hour_epoch(int(epoch[k])),
        ))
    return rows, bucketed


def bank_confirms(path, exact_by_id):
    """Bank-side confirmation of a consortium circle candidate.

    The consortium only knows amount bands and hour buckets, so a candidate is
    a hypothesis. Each pair of consecutive hops meets at ONE pass-through
    account, held by ONE bank, and that bank sees both legs with exact data.
    Each bank checks only its own junctions and answers yes/no: the outgoing
    leg must leave the same account the incoming leg arrived at, strictly
    later, keeping 85-100% of the incoming amount. No amounts, names or
    account numbers cross the bank boundary - only the yes/no. The salted
    evidence refs on consortium edges are what let each bank find its own
    transactions locally. (Here `exact_by_id` stands in for each bank's own
    ledger.) The whole loop must also fit inside 72 hours. A candidate is
    CONFIRMED only if every junction is confirmed."""
    legs = [exact_by_id[t] for t in path]
    if legs[-1].ts - legs[0].ts > CIRCLE_WINDOW_HOURS * HOUR:
        return False
    for incoming, outgoing in zip(legs, legs[1:]):
        if outgoing.from_acc != incoming.to_acc:
            return False
        if outgoing.ts <= incoming.ts:
            return False
        if not (CIRCLE_MIN_RETENTION * incoming.amount - EPS
                <= outgoing.amount <= CIRCLE_MAX_RETENTION * incoming.amount + EPS):
            return False
    return True


def circle_txn_sets(tx_sorted, view, account_to_entity, account_to_bank, entity_attrs, exact_by_id):
    """Returns (candidate count, list of txn-id sets that stand as findings).
    Single-bank views and ALL use exact data already. CONSORTIUM candidates
    must additionally be confirmed by the banks."""
    rows, bucketed = build_view_rows(tx_sorted, view, account_to_entity, account_to_bank, entity_attrs)
    cycles = find_circle_cycles(rows, bucketed=bucketed)
    if not bucketed:
        return len(cycles), [ts for ts, _ in cycles]
    confirmed = [ts for ts, path in cycles
                 if bank_confirms([rows[p].txn_id for p in path], exact_by_id)]
    return len(cycles), confirmed


# ---------------------------------------------------------------------------
# SCORING - the ONLY code allowed to read ground_truth.csv
# ---------------------------------------------------------------------------

DETECTORS = ["CIRCLE", "SPRAY", "SPEED", "THRESHOLD", "WATCHLIST_SIGNAL"]
STRUCTURAL = DETECTORS[:4]


def load_ground_truth():
    gt = pd.read_csv(os.path.join(DATA_DIR, "ground_truth.csv"))
    rings = {rid: set(g["txn_id"]) for rid, g in gt.groupby("ring_id", sort=False)}
    return rings


def score(findings):
    rings = load_ground_truth()
    all_ring = set().union(*rings.values())

    per_detector = {}
    for d in DETECTORS:
        fs = [f for f in findings if f["detector"] == d]
        tp = sum(1 for f in fs if len(set(f["txn_ids"]) & all_ring) >= 0.5 * len(f["txn_ids"]))
        per_detector[d] = (len(fs), tp, len(fs) - tp)

    # A ring counts as caught by a detector if one of ITS findings covers >=50%
    # of the ring's transactions. WATCHLIST_SIGNAL makes no structural claim,
    # so it never counts toward catching a ring.
    per_ring = {}
    for rid, txns in rings.items():
        by_det = {}
        for f in findings:
            if f["detector"] not in STRUCTURAL:
                continue
            cover = len(set(f["txn_ids"]) & txns) / len(txns)
            by_det[f["detector"]] = max(by_det.get(f["detector"], 0.0), cover)
        caught_by = [d for d in STRUCTURAL if by_det.get(d, 0) >= 0.5]
        per_ring[rid] = (len(txns), max(by_det.values(), default=0.0), caught_by)

    return per_detector, per_ring


def hero_check(tx_sorted, account_to_entity, account_to_bank, entity_attrs, exact_by_id):
    """The demo claim: ALL six hero txns inside ONE single confirmed circle."""
    hero = load_ground_truth()["CIRC_6_HERO"]
    out = {}
    for view in ["ALL", "BANK_A", "BANK_B", "CONSORTIUM"]:
        n_cand, sets = circle_txn_sets(tx_sorted, view, account_to_entity, account_to_bank,
                                       entity_attrs, exact_by_id)
        best = max((len(s & hero) for s in sets), default=0)
        out[view] = (best, len(hero), best == len(hero), len(sets), n_cand)
    return out


def discovery_only_score(recs, entity_attrs, account_age):
    """Re-run every detector with nobody on the watchlist: the full thresholds
    only, applied to everyone. Answers "you only caught them because you knew
    who they were"."""
    blind = {e: dict(a, is_watchlisted=False) for e, a in entity_attrs.items()}
    findings = run_detectors(recs, blind, account_age)
    _, per_ring = score(findings)
    per_detector, _ = score(findings)
    caught = sum(1 for _, _, by in per_ring.values() if by)
    false_alarms = sum(per_detector[d][2] for d in STRUCTURAL)
    return caught, len(per_ring), false_alarms


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(findings, per_detector, per_ring, hero, discovery, t_detect, t_total):
    counts = {d: sum(1 for f in findings if f["detector"] == d) for d in DETECTORS}
    print("=" * 78)
    print("CHAKRAVYUH - Stage 4: detection swarm")
    print("=" * 78)
    print(f"Circle {counts['CIRCLE']}, Spray {counts['SPRAY']}, Speed {counts['SPEED']}, "
          f"Threshold {counts['THRESHOLD']}, Watchlist {counts['WATCHLIST_SIGNAL']}")
    lanes = {l: sum(1 for f in findings if f["lane"] == l) for l in ("DISCOVERY", "WATCHLIST")}
    print(f"Lanes: DISCOVERY {lanes['DISCOVERY']}, WATCHLIST {lanes['WATCHLIST']}  "
          f"(total {len(findings)} findings -> detections.json)")

    print("\nPer detector (true positive = >=50% of the finding's txns are ring txns)")
    print(f"  {'detector':<18}{'findings':>9}{'true pos':>10}{'false alarms':>14}")
    for d in DETECTORS:
        n, tp, fa = per_detector[d]
        print(f"  {d:<18}{n:>9}{tp:>10}{fa:>14}")

    print("\nPer ring (caught = one finding covers >=50% of the ring's txns)")
    print(f"  {'ring':<18}{'txns':>5}  {'best cover':>10}  {'result':<8} by")
    caught = 0
    for rid, (n, cover, by) in per_ring.items():
        ok = bool(by)
        caught += ok
        print(f"  {rid:<18}{n:>5}  {cover * 100:>9.0f}%  {'CAUGHT' if ok else 'MISSED':<8} {', '.join(by) or '-'}")
    structural_fa = sum(per_detector[d][2] for d in STRUCTURAL)
    print(f"\nTotals: {caught} of {len(per_ring)} rings caught; "
          f"{structural_fa} false alarms across the four structural detectors "
          f"(+ {per_detector['WATCHLIST_SIGNAL'][2]} watchlist-signal findings that are not ring claims)")

    dc, dn, dfa = discovery
    print(f"\nDiscovery only (nobody known): {dc} of {dn} rings caught, {dfa} false alarms")

    print("\nHero check - CIRCLE on CIRC_6_HERO, per view (caught = all 6 hero txns in ONE confirmed circle)")
    for view in ["ALL", "BANK_A", "BANK_B", "CONSORTIUM"]:
        best, total, ok, n_final, n_cand = hero[view]
        line = (f"  {view:<11} {'hero caught' if ok else 'NOT caught':<12} "
                f"(best single circle finding covers {best}/{total} hero txns")
        if view == "CONSORTIUM":
            line += f"; CONSORTIUM candidates {n_cand} -> bank-confirmed {n_final}"
        else:
            line += f"; {n_final} circle findings in view"
        print(line + ")")

    print(f"\nRuntime: detection {t_detect:.1f}s, whole run incl. hero check and scoring {t_total:.1f}s")


def main():
    t0 = time.time()
    tx, account_to_entity, entity_attrs, account_to_bank = load_data()
    account_age = load_account_ages()
    tx_sorted, recs = prepare(tx, account_to_entity)

    findings = run_detectors(recs, entity_attrs, account_age)
    write_detections(findings)
    t_detect = time.time() - t0

    per_detector, per_ring = score(findings)
    exact_by_id = {r.txn_id: r for r in recs}
    hero = hero_check(tx_sorted, account_to_entity, account_to_bank, entity_attrs, exact_by_id)
    discovery = discovery_only_score(recs, entity_attrs, account_age)
    print_report(findings, per_detector, per_ring, hero, discovery, t_detect, time.time() - t0)


if __name__ == "__main__":
    main()
