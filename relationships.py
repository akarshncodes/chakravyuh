#!/usr/bin/env python3
"""
CHAKRAVYUH - Relationship Lens (runs after Stage 5, before Stage 6).

FC-02 asks us to catch "unusual account relationships". The detectors already
find the *shape* of the money (circles, sprays, speed, thresholds). This file
looks at the *people and accounts* inside each case and asks: is there
something odd about how these accounts relate to each other?

Five checks, each one compared against what is normal for the whole bank:

  R1 FRESH_ACCOUNTS    accounts opened very recently (mules are new accounts)
  R2 HIDDEN_CONTROL    one real person quietly running several accounts
  R3 FIRST_CONTACT     people who had never transacted before, suddenly moving money
  R4 SHARED_PHONE      different people registered on the same phone number
  R5 BANK_BLIND_SPOT   hops that one bank alone can never see

Important design choices:
  * This file never creates a case. It only adds evidence to the 11 cases the
    detectors already found - so it cannot add a false positive.
  * Thresholds are fixed multiples of the bank-wide baseline. They were not
    tuned on the answer key.
  * A control group of ordinary groups of customers goes through the same
    five checks, so we can show the checks mean something.
  * Answer-key rule: ground_truth.csv, true_entity_id and owner_entity are
    never read here. accounts.csv has an owner_entity column - we only read
    account_id, bank and opened_days_ago from it.

Standard library only. Output: relationships.json
"""

import csv
import json
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda name: os.path.join(HERE, name)

FRESH_DAYS = 30          # an account younger than this is "fresh"
SEED = 26192             # same seed as the generator, so the control group is reproducible
CONTROL_PER_CASE = 20    # innocent comparison groups drawn per case

# A check fires only when the case is clearly above normal for the bank.
R1_MULTIPLE = 10         # fresh-account share at least 10x the bank rate
R2_MULTIPLE = 2          # multi-account-owner share at least 2x the bank rate
R3_MULTIPLE = 1.5        # first-contact share at least 1.5x the bank rate
MIN_COUNT = 2            # and never on a single account/person/transfer


# ---------------------------------------------------------------- loading
def load():
    accounts = {}
    with open(P("accounts.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # deliberately NOT reading r["owner_entity"] - that is answer key
            accounts[r["account_id"]] = {"bank": r["bank"], "age": int(r["opened_days_ago"])}

    owner = {}
    with open(P("account_owners.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            owner[r["account_id"]] = r["entity_key"]   # resolved by our Stage 2

    people = {}
    with open(P("resolved_entities.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            people[r["entity_key"]] = {
                "name": r["canonical_name"],
                "phone": r["phone"].strip(),
                "accounts": [a for a in r["account_ids"].split(";") if a],
            }

    txns = []
    with open(P("transactions.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            txns.append((r["timestamp"], r["txn_id"], r["from_account"], r["to_account"],
                         r["from_bank"], r["to_bank"]))
    txns.sort()

    with open(P("cases.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    return accounts, owner, people, txns, cases


# ---------------------------------------------------------------- baselines
def build_index(accounts, owner, people, txns):
    # R3: a transfer is "first contact" if this sender-person had never
    # sent money to this receiver-person at any earlier moment.
    seen_pairs = set()
    first_contact = set()
    txn_by_id = {}
    neighbours = defaultdict(set)
    for ts, tid, fa, ta, fb, tb in txns:
        fp, tp = owner.get(fa), owner.get(ta)
        txn_by_id[tid] = (ts, fa, ta, fb, tb)
        if fp and tp and fp != tp:
            neighbours[fp].add(tp)
            neighbours[tp].add(fp)
        if (fp, tp) not in seen_pairs:
            first_contact.add(tid)
            seen_pairs.add((fp, tp))

    phone_count = defaultdict(int)
    for p in people.values():
        if p["phone"]:
            phone_count[p["phone"]] += 1

    n_acc = len(accounts)
    baseline = {
        "fresh_account_rate": sum(a["age"] < FRESH_DAYS for a in accounts.values()) / n_acc,
        "multi_account_owner_rate": sum(len(p["accounts"]) > 1 for p in people.values()) / len(people),
        "first_contact_rate": len(first_contact) / len(txns),
        "shared_phone_person_rate": sum(1 for p in people.values()
                                        if p["phone"] and phone_count[p["phone"]] > 1) / len(people),
        "accounts": n_acc, "people": len(people), "transactions": len(txns),
    }
    return txn_by_id, first_contact, phone_count, neighbours, baseline


def pct(x):
    return f"{x * 100:.1f}%"


# ---------------------------------------------------------------- the five checks
def examine(txn_ids, accounts, owner, people, idx, baseline):
    """Run the five checks on one group of transactions. Returns a list of signals."""
    txn_by_id, first_contact, phone_count, _, _ = idx
    rows = [(t, txn_by_id[t]) for t in txn_ids if t in txn_by_id]
    accs = sorted({r[1] for _, r in rows} | {r[2] for _, r in rows})
    persons = defaultdict(set)
    for a in accs:
        if a in owner:
            persons[owner[a]].add(a)
    signals = []

    # R1 fresh accounts
    fresh = [a for a in accs if a in accounts and accounts[a]["age"] < FRESH_DAYS]
    share = len(fresh) / len(accs) if accs else 0
    if len(fresh) >= MIN_COUNT and share >= R1_MULTIPLE * baseline["fresh_account_rate"]:
        signals.append({
            "code": "R1", "name": "FRESH_ACCOUNTS",
            "headline": f"{len(fresh)} of {len(accs)} accounts are under {FRESH_DAYS} days old",
            "sentence": (f"In this network, {len(fresh)} of the {len(accs)} accounts in this network were opened less than "
                         f"{FRESH_DAYS} days ago ({pct(share)}), against {pct(baseline['fresh_account_rate'])} "
                         f"across the whole bank."),
            "case_value": pct(share), "bank_baseline": pct(baseline["fresh_account_rate"]),
            "accounts": fresh, "txn_ids": [],
        })

    # R2 hidden control - one resolved person, several accounts
    multi = {p: sorted(a) for p, a in persons.items() if len(a) > 1}
    share = len(multi) / len(persons) if persons else 0
    if len(multi) >= MIN_COUNT and share >= R2_MULTIPLE * baseline["multi_account_owner_rate"]:
        n_acc_multi = sum(len(a) for a in multi.values())
        signals.append({
            "code": "R2", "name": "HIDDEN_CONTROL",
            "headline": f"{len(accs)} accounts, only {len(persons)} real people behind them",
            "sentence": (f"The {len(accs)} accounts belong to only {len(persons)} people once identity records "
                         f"are resolved; {len(multi)} of them control {n_acc_multi} accounts between them "
                         f"({pct(share)} of the people here, against {pct(baseline['multi_account_owner_rate'])} "
                         f"bank-wide). To a bank looking account by account, these look like strangers."),
            "case_value": pct(share), "bank_baseline": pct(baseline["multi_account_owner_rate"]),
            "accounts": sorted(a for v in multi.values() for a in v), "people": sorted(multi),
            "txn_ids": [],
        })

    # R3 first contact
    fc = [t for t, _ in rows if t in first_contact]
    share = len(fc) / len(rows) if rows else 0
    if len(fc) >= MIN_COUNT and share >= R3_MULTIPLE * baseline["first_contact_rate"]:
        signals.append({
            "code": "R3", "name": "FIRST_CONTACT",
            "headline": f"{len(fc)} of {len(rows)} transfers were first-ever contact",
            "sentence": (f"Of the {len(rows)} transfers, {len(fc)} ({pct(share)}) were the first time that sender "
                         f"had ever paid that receiver, against {pct(baseline['first_contact_rate'])} of all "
                         f"transfers in the bank. The money moved between people with no history together."),
            "case_value": pct(share), "bank_baseline": pct(baseline["first_contact_rate"]),
            "accounts": [], "txn_ids": fc,
        })

    # R4 shared phone between different people
    shared = defaultdict(list)
    for p in persons:
        ph = people.get(p, {}).get("phone", "")
        if ph and phone_count[ph] > 1:
            shared[ph].append(p)
    shared = {ph: ps for ps_ph in [shared] for ph, ps in ps_ph.items()}
    if shared:
        n_people = len({p for ps in shared.values() for p in ps})
        signals.append({
            "code": "R4", "name": "SHARED_PHONE",
            "headline": f"{len(shared)} phone number(s) shared by different people",
            "sentence": (f"In this network, {n_people} people are registered on {len(shared)} phone number(s) "
                         f"that also belong to another, different customer. Only "
                         f"{pct(baseline['shared_phone_person_rate'])} of customers bank-wide share a phone. "
                         f"A shared number across unrelated accounts is a common sign of one handler "
                         f"operating several mule accounts."),
            "case_value": str(len(shared)), "bank_baseline": pct(baseline["shared_phone_person_rate"]),
            "accounts": [], "people": sorted({p for ps in shared.values() for p in ps}), "txn_ids": [],
        })

    # R5 bank blind spot - hops that each bank alone cannot see
    missing = {"BANK_A": [], "BANK_B": []}
    for t, (_, _, _, fb, tb) in rows:
        for bank in missing:
            if fb != bank and tb != bank:
                missing[bank].append(t)
    if rows and missing["BANK_A"] and missing["BANK_B"]:
        signals.append({
            "code": "R5", "name": "BANK_BLIND_SPOT",
            "headline": (f"Bank A cannot see {len(missing['BANK_A'])} hop(s), "
                         f"Bank B cannot see {len(missing['BANK_B'])}"),
            "sentence": (f"Bank A alone sees {len(rows) - len(missing['BANK_A'])} of the {len(rows)} transfers "
                         f"and Bank B alone sees {len(rows) - len(missing['BANK_B'])}. Neither bank on its own "
                         f"can see the whole network; it only becomes visible in the consortium view, which "
                         f"shares salted hashes, never customer data."),
            "case_value": f"A:{len(missing['BANK_A'])} B:{len(missing['BANK_B'])}", "bank_baseline": "n/a",
            "accounts": [], "txn_ids": missing["BANK_A"] + missing["BANK_B"],
        })
    return signals, len(accs), len(persons)


# ---------------------------------------------------------------- control group
def control_group(cases, accounts, owner, people, idx, baseline):
    """Ordinary customers, grouped the same way a case is (a connected
    neighbourhood of the same size), put through the same five checks."""
    txn_by_id, _, _, neighbours, _ = idx
    rng = random.Random(SEED)
    case_people = {p["entity_key"] for c in cases for p in c["core_people"] + c["context_people"]}
    pool = sorted(p for p in neighbours if p not in case_people)

    person_txns = defaultdict(list)
    for tid, (_, fa, ta, _, _) in txn_by_id.items():
        fp, tp = owner.get(fa), owner.get(ta)
        if fp:
            person_txns[fp].append(tid)
        if tp and tp != fp:
            person_txns[tp].append(tid)

    fired_counts, per_code, groups = [], defaultdict(int), 0
    for c in cases:
        size = max(3, len(c["core_people"]))
        n_txn = len(c["evidence_txn_ids"])
        for _ in range(CONTROL_PER_CASE):
            start = rng.choice(pool)
            group, frontier = {start}, [start]
            while frontier and len(group) < size:
                nxt = sorted(n for n in neighbours[frontier.pop(0)] if n not in case_people and n not in group)
                rng.shuffle(nxt)
                for n in nxt[: size - len(group)]:
                    group.add(n)
                    frontier.append(n)
            inside = sorted({t for p in group for t in person_txns[p]
                             if owner.get(txn_by_id[t][1]) in group and owner.get(txn_by_id[t][2]) in group})
            if not inside:
                continue
            inside = inside[:max(n_txn, 3)]
            sig, _, _ = examine(inside, accounts, owner, people, idx, baseline)
            groups += 1
            fired_counts.append(len(sig))
            for s in sig:
                per_code[s["code"]] += 1
    return {
        "groups": groups,
        "avg_signals_per_group": round(sum(fired_counts) / groups, 2) if groups else 0,
        "groups_with_2plus_signals": sum(1 for x in fired_counts if x >= 2),
        "share_with_2plus_signals": pct(sum(1 for x in fired_counts if x >= 2) / groups) if groups else "0%",
        "fire_rate_by_check": {k: pct(v / groups) for k, v in sorted(per_code.items())},
    }


# ---------------------------------------------------------------- main
def main():
    accounts, owner, people, txns, cases = load()
    idx = build_index(accounts, owner, people, txns)
    baseline = idx[4]

    out_cases = {}
    for c in cases:
        ids = c["evidence_txn_ids"]
        sig, n_acc, n_people = examine(ids, accounts, owner, people, idx, baseline)
        out_cases[c["case_id"]] = {
            "accounts_examined": n_acc, "people_examined": n_people,
            "signals_fired": [s["code"] for s in sig], "signals": sig,
        }

    control = control_group(cases, accounts, owner, people, idx, baseline)
    fired = [len(v["signals"]) for v in out_cases.values()]
    summary = {
        "cases": len(out_cases),
        "avg_signals_per_case": round(sum(fired) / len(fired), 2),
        "cases_with_2plus_signals": sum(1 for x in fired if x >= 2),
        "fire_rate_by_check": {code: pct(sum(code in v["signals_fired"] for v in out_cases.values()) / len(out_cases))
                               for code in ("R1", "R2", "R3", "R4", "R5")},
    }
    result = {
        "about": "Relationship Lens - unusual account relationships inside each case, measured against the bank baseline",
        "baseline": {k: (pct(v) if isinstance(v, float) else v) for k, v in baseline.items()},
        "thresholds": {"fresh_days": FRESH_DAYS, "R1_multiple": R1_MULTIPLE, "R2_multiple": R2_MULTIPLE,
                       "R3_multiple": R3_MULTIPLE, "min_count": MIN_COUNT},
        "case_summary": summary, "control_group": control, "cases": out_cases,
    }
    with open(P("relationships.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("Relationship Lens")
    print("  bank baseline:", {k: v for k, v in result["baseline"].items()})
    for cid, v in out_cases.items():
        print(f"  {cid}: {','.join(v['signals_fired']) or '-':<16} " +
              " | ".join(s["headline"] for s in v["signals"]))
    print(f"  cases:   {summary['avg_signals_per_case']} signals/case, "
          f"{summary['cases_with_2plus_signals']}/{summary['cases']} with 2+ signals")
    print(f"  control: {control['avg_signals_per_group']} signals/group, "
          f"{control['groups_with_2plus_signals']}/{control['groups']} with 2+ signals "
          f"({control['share_with_2plus_signals']}) by check {control['fire_rate_by_check']}")
    print("-> relationships.json")


if __name__ == "__main__":
    main()
