#!/usr/bin/env python3
"""
CHAKRAVYUH - DRONA, the lead investigator (runs after Stage 5b, drives 6 & 7).

In the Mahabharata, Drona is the one who designed the chakravyuh. Here DRONA
is the AI that runs the investigation. Three AI agents, one chain of command:

  DRONA    (this file, gpt-4o)       plans and runs the investigation
  SANJAYA  (agents.py investigator)  writes the case - the narrator
  VIDURA   (agents.py verifier)      argues the innocent side - the truth-teller

What DRONA actually decides - these are real decisions, not a fixed script:
  1. Triage     which item to work first, and why
  2. Evidence   which tools to call for each item (it chooses, per item)
  3. Readiness  whether a case is ready to be written up by SANJAYA
  4. Rewrites   if VIDURA says REVISE, whether and how to send it back
  5. Leads      what to do with weak signals that are NOT cases
                (a watchlist hint, a person feeding two different rings)
  6. Final      a recommendation per item for the human officer

What DRONA can never do (enforced in code below, not just asked in a prompt):
  * detect anything - every tool is read-only over files the deterministic
    stages already wrote; there is no tool that creates a finding or a case
  * cite something that isn't there - every ID in a decision is checked
    against that item's own evidence; invented IDs are rejected and counted
  * decide without looking - at least two evidence tools before a decision
  * file anything - the final call is always the human officer's

Everything is cached to investigation_log.json, so the demo needs no network.

Answer-key rule: ground_truth.csv, true_entity_id and owner_entity are never
read here (accounts.csv is read for account age and bank only).
"""

import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import agents
import relationships as rl

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda name: os.path.join(HERE, name)
LOG_PATH = P("investigation_log.json")

COMMANDER_MODEL = "gpt-4o"      # DRONA - SANJAYA and VIDURA keep agents.MODEL
MAX_STEPS = 10                  # tool calls per item before we hand it to a human
MIN_EVIDENCE_TOOLS = 2          # tools DRONA must use before it may decide
MAX_WRITER_RUNS = 2             # first draft + one rewrite
WORKERS = int(os.environ.get("DRONA_WORKERS", "2"))   # items in parallel (lower if rate-limited)
PARTIAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "investigation_log.partial.json")

EVIDENCE_TOOLS = {"open_item", "check_relationships", "compare_bank_views",
                  "account_history", "expand_neighbourhood", "lookup_transaction"}
DECISIONS = {
    "CASE": ["FILE_STR", "ESCALATE", "MONITOR"],
    "WATCHLIST_REVIEW": ["ESCALATE", "MONITOR", "CLOSE_RECOMMENDED"],
    "LEAD": ["ESCALATE_AS_LEAD", "MONITOR", "CLOSE_RECOMMENDED"],
}


# =====================================================================
# THE WORLD DRONA CAN LOOK AT (read-only)
# =====================================================================

class World:
    def __init__(self):
        accounts, owner, people, txns, cases = rl.load()
        self.accounts, self.owner, self.people, self.cases_list = accounts, owner, people, cases
        self.idx = rl.build_index(accounts, owner, people, txns)
        self.baseline = self.idx[4]
        self.txn = {t[1]: {"txn_id": t[1], "timestamp": t[0], "from_account": t[2], "to_account": t[3],
                           "from_bank": t[4], "to_bank": t[5]} for t in txns}
        with open(P("transactions.csv"), newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.txn[r["txn_id"]]["amount"] = float(r["amount"])
                self.txn[r["txn_id"]]["channel"] = r["channel"]
        self.by_account = defaultdict(list)
        for t in self.txn.values():
            self.by_account[t["from_account"]].append(t)
            self.by_account[t["to_account"]].append(t)
        for v in self.by_account.values():
            v.sort(key=lambda t: t["timestamp"])
        self.flags = {}
        with open(P("resolved_entities.csv"), newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.flags[r["entity_key"]] = {
                    "watchlisted": r["is_watchlisted"].strip().lower() == "true",
                    "unverified_link": r["has_unverified_link"].strip().lower() == "true"}
        with open(P("cases.json"), encoding="utf-8") as f:
            cj = json.load(f)
        with open(P("detections.json"), encoding="utf-8") as f:
            self.findings = {x["finding_id"]: x for x in json.load(f)}
        with open(P("relationships.json"), encoding="utf-8") as f:
            self.rel = json.load(f)["cases"]
        self.cases = {c["case_id"]: c for c in cj["cases"]}
        self.core_in = defaultdict(list)
        for c in cj["cases"]:
            for p in c["core_people"]:
                self.core_in[p["entity_key"]].append(c["case_id"])
        self.items = self._build_items(cj)

    def principal(self, case):
        """For a CIRCLE case the hop-sum counts one principal once per hop, so we
        also give the largest single evidence transfer - the money that moved."""
        if "CIRCLE" not in case["detectors_fired"]:
            return None
        amts = [self.txn[t]["amount"] for t in case["evidence_txn_ids"] if t in self.txn]
        return agents.format_inr(max(amts))["words"] if amts else None

    def name(self, pid):
        return self.people.get(pid, {}).get("name", pid).title()

    def _build_items(self, cj):
        items = {}
        for c in cj["cases"]:
            items[c["case_id"]] = {"id": c["case_id"], "kind": "CASE", "txn_ids": list(c["evidence_txn_ids"]),
                                   "people": [p["entity_key"] for p in c["core_people"]]}
        for w in cj["watchlist_review"]:
            items[w["finding_id"]] = {"id": w["finding_id"], "kind": "WATCHLIST_REVIEW",
                                      "txn_ids": list(w["txn_ids"]), "people": list(w["people"]), "raw": w}
        # LEADS: a person accused in no case, but whose money touches two or
        # more different cases. Deterministic - DRONA only judges them.
        seen = defaultdict(list)
        for c in cj["cases"]:
            for p in c["context_people"]:
                if p["entity_key"] not in self.core_in:
                    seen[p["entity_key"]].append((c["case_id"], p["direction"], p["amount"]))
        n = 0
        for pid, touches in sorted(seen.items()):
            if len({t[0] for t in touches}) >= 2:
                n += 1
                lid = f"L{n:02d}"
                txn_ids = []
                for cid, _, _ in touches:
                    c = self.cases[cid]
                    for t in c["context_txn_ids"]:
                        tx = self.txn.get(t)
                        if tx and pid in (self.owner.get(tx["from_account"]), self.owner.get(tx["to_account"])):
                            txn_ids.append(t)
                items[lid] = {"id": lid, "kind": "LEAD", "txn_ids": txn_ids, "people": [pid], "touches": touches}
        return items

    # ---- the set of IDs an item is allowed to cite ------------------------
    def allowed_ids(self, item, extra):
        ids = set(item["txn_ids"]) | set(item["people"]) | {item["id"]}
        for t in item["txn_ids"]:
            tx = self.txn.get(t)
            if tx:
                ids |= {tx["from_account"], tx["to_account"]}
        if item["kind"] == "CASE":
            c = self.cases[item["id"]]
            ids |= set(c["supporting_txn_ids"]) | set(c["context_txn_ids"]) | set(c["finding_ids"])
            for p in c["core_people"] + c["context_people"]:
                ids.add(p["entity_key"])
                ids |= set(p.get("accounts", []))
            ids |= {l["case_id"] for l in c.get("linked_cases", [])}
            ids |= set(c["detectors_fired"])
            ids |= set(self.rel.get(item["id"], {}).get("signals_fired", []))
        if item["kind"] == "LEAD":
            ids |= {t[0] for t in item["touches"]}
        return ids | extra      # extra = IDs DRONA was shown by its own tool calls

    # =================================================================
    # TOOLS - each returns (data_for_model, one_line_for_the_log, ids_seen)
    # =================================================================
    def open_item(self, item):
        if item["kind"] == "CASE":
            c = self.cases[item["id"]]
            vol = agents.format_inr(c["total_evidence_amount"])["words"]
            data = {
                "case_id": c["case_id"], "detectors_fired": c["detectors_fired"],
                "why_flagged": [_inr_text(self.findings[f]["reason"]) for f in c["finding_ids"] if f in self.findings][:6],
                "core_people": [{"person": p["entity_key"], "name": p["name"], "accounts": p["accounts"],
                                 "watchlisted": self.flags.get(p["entity_key"], {}).get("watchlisted", False),
                                 "identity_link_unverified": self.flags.get(p["entity_key"], {}).get("unverified_link", False)}
                                for p in c["core_people"]][:15],
                "core_people_count": len(c["core_people"]), "evidence_txn_count": len(c["evidence_txn_ids"]),
                "evidence_txn_ids_sample": c["evidence_txn_ids"][:10], "total_volume": vol,
                "hours_spanned": round(c["hours_spanned"], 2), "banks": c["banks_involved"],
                "principal_cycled": self.principal(c),
                "note_on_amounts": ("CIRCLE case: principal_cycled is the money that actually moved; total_volume "
                                    "counts it once per hop." if self.principal(c) else None),
                "linked_cases": c.get("linked_cases", []), "found_without_watchlist": c.get("found_without_watchlist"),
            }
            pr = self.principal(c)
            moved = f"{pr} cycled ({vol} across all hops)" if pr else vol
            line = (f"{len(c['core_people'])} people · {len(c['evidence_txn_ids'])} evidence transfers · "
                    f"{moved} in {c['hours_spanned']:.1f} h · {' + '.join(c['detectors_fired'])}")
            seen = set(data["evidence_txn_ids_sample"])
            return data, line, seen
        if item["kind"] == "WATCHLIST_REVIEW":
            w = item["raw"]
            data = {"item": w["finding_id"], "reason": w["reason"], "people": w["people"],
                    "txn_ids": w["txn_ids"], "signals": w["evidence"]["signals"],
                    "note": "Weak hint only. Not a case, no structural pattern was detected."}
            return data, w["reason"], set()
        pid = item["people"][0]
        touches = [{"case_id": cid, "direction": d, "amount": agents.format_inr(a)["words"]}
                   for cid, d, a in item["touches"]]
        data = {"lead": item["id"], "person": pid, "name": self.name(pid),
                "accused_in_any_case": False, "touches_cases": touches, "txn_ids": item["txn_ids"],
                "note": "Not accused anywhere. Their money reaches more than one separate ring."}
        line = f"{self.name(pid)} is not accused, but their money reaches " + \
               ", ".join(f"{t['case_id']} ({t['direction']} {t['amount']})" for t in touches)
        return data, line, set()

    def check_relationships(self, item):
        if item["kind"] == "CASE":
            sig = self.rel.get(item["id"], {}).get("signals", [])
        else:
            sig, _, _ = rl.examine(item["txn_ids"], self.accounts, self.owner, self.people, self.idx, self.baseline)
        data = [{"code": s["code"], "finding": s["sentence"]} for s in sig] or \
               ["No relationship check is above the bank baseline for this item."]
        line = " · ".join(s["headline"] for s in sig) or "nothing unusual versus the bank baseline"
        return data, line, {s["code"] for s in sig}

    def compare_bank_views(self, item):
        rows = [self.txn[t] for t in item["txn_ids"] if t in self.txn]
        out = {}
        for bank in ("BANK_A", "BANK_B"):
            blind = [t["txn_id"] for t in rows if bank not in (t["from_bank"], t["to_bank"])]
            out[bank] = {"sees": len(rows) - len(blind), "of": len(rows), "cannot_see": blind[:10]}
        out["consortium_sees"] = len(rows)
        line = (f"Bank A sees {out['BANK_A']['sees']}/{len(rows)} · Bank B sees {out['BANK_B']['sees']}/{len(rows)}"
                f" · consortium sees all {len(rows)}")
        return out, line, set(out["BANK_A"]["cannot_see"] + out["BANK_B"]["cannot_see"])

    def account_history(self, item, account_id):
        if account_id not in self.accounts:
            return {"error": f"{account_id} does not exist"}, f"{account_id}: no such account", set()
        hist = self.by_account[account_id]
        inc = [t for t in hist if t["to_account"] == account_id]
        out = [t for t in hist if t["from_account"] == account_id]
        fastest = None
        for t in inc:   # fastest pass-through: money out within X minutes of arriving
            ts = datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S")
            for o in out:
                to = datetime.strptime(o["timestamp"], "%Y-%m-%d %H:%M:%S")
                if to >= ts and o["amount"] >= 0.5 * t["amount"]:
                    m = (to - ts).total_seconds() / 60
                    fastest = m if fastest is None else min(fastest, m)
                    break
        pid = self.owner.get(account_id)
        cps = {t["from_account"] if t["to_account"] == account_id else t["to_account"] for t in hist}
        data = {"account": account_id, "bank": self.accounts[account_id]["bank"],
                "opened_days_ago": self.accounts[account_id]["age"],
                "owner_person": pid, "owner_name": self.name(pid),
                "owner_watchlisted": self.flags.get(pid, {}).get("watchlisted", False),
                "owner_controls_accounts": self.people.get(pid, {}).get("accounts", []),
                "transfers_in": len(inc), "transfers_out": len(out),
                "money_in": agents.format_inr(sum(t["amount"] for t in inc))["words"],
                "money_out": agents.format_inr(sum(t["amount"] for t in out))["words"],
                "distinct_counterparties": len(cps),
                "fastest_pass_through_minutes": None if fastest is None else round(fastest, 1),
                "first_seen": hist[0]["timestamp"] if hist else None, "last_seen": hist[-1]["timestamp"] if hist else None,
                "bank_median_account_age_days": 1731}
        line = (f"{account_id}: opened {data['opened_days_ago']} days ago · {len(inc)} in / {len(out)} out · "
                + (f"fastest pass-through {_dur(fastest)}" if fastest is not None else "no pass-through") + f" · owner controls {len(data['owner_controls_accounts'])} account(s)")
        return data, line, {account_id, pid} | set(data["owner_controls_accounts"])

    def expand_neighbourhood(self, item, person_id):
        accs = self.people.get(person_id, {}).get("accounts", [])
        if not accs:
            return {"error": f"{person_id} does not exist"}, f"{person_id}: no such person", set()
        agg = defaultdict(lambda: [0, 0.0])
        for a in accs:
            for t in self.by_account[a]:
                other = t["to_account"] if t["from_account"] == a else t["from_account"]
                op = self.owner.get(other)
                if op and op != person_id:
                    agg[op][0] += 1
                    agg[op][1] += t["amount"]
        top = sorted(agg.items(), key=lambda kv: -kv[1][1])[:8]
        data = {"person": person_id, "name": self.name(person_id), "total_counterparties": len(agg),
                "top_counterparties": [{"person": p, "name": self.name(p), "transfers": n,
                                        "volume": agents.format_inr(v)["words"],
                                        "accused_in_cases": self.core_in.get(p, [])} for p, (n, v) in top]}
        hits = [c for p, _ in top for c in self.core_in.get(p, [])]
        line = (f"{self.name(person_id)} deals with {len(agg)} people; "
                + (f"top counterparties are accused in {', '.join(sorted(set(hits)))}" if hits
                   else "none of the top counterparties is accused anywhere"))
        return data, line, {p for p, _ in top}

    def lookup_transaction(self, item, txn_id):
        t = self.txn.get(txn_id)
        if not t:
            return {"error": f"{txn_id} does not exist"}, f"{txn_id}: no such transaction", set()
        data = dict(t, amount=agents.format_inr(t["amount"]),
                    from_person=self.owner.get(t["from_account"]), to_person=self.owner.get(t["to_account"]))
        line = f"{txn_id}: {data['amount']['words']} {t['from_account']} → {t['to_account']} at {t['timestamp']} via {t['channel']}"
        return data, line, {txn_id, t["from_account"], t["to_account"]}


def _inr_text(text):
    """Detector reasons were written with western digit grouping (Rs 24,000,000).
    Re-express every amount in Indian format before DRONA sees it, so the only
    rupee strings DRONA can ever copy are the ones format_inr produced."""
    import re
    return re.sub(r"Rs\.?\s*(\d[\d,]*(?:\.\d+)?)",
                  lambda m: agents.format_inr(float(m.group(1).replace(",", "")))["digits"], text)


def _dur(minutes):
    if minutes < 120:
        return f"{minutes:.0f} min"
    if minutes < 2880:
        return f"{minutes / 60:.1f} h"
    return f"{minutes / 1440:.0f} days"


# =====================================================================
# TOOL DEFINITIONS SHOWN TO THE MODEL
# =====================================================================

def _tool(name, desc, props=None, required=None):
    props = dict(props or {})
    props["why"] = {"type": "string", "description": "One short sentence, first person, plain English: why you are doing this now."}
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": (required or []) + ["why"]}}}


TOOLS = [
    _tool("open_item", "Open the item you are investigating: what was flagged, who is involved, the amounts."),
    _tool("check_relationships", "Run the Relationship Lens: fresh accounts, one person behind several accounts, "
          "first-ever contact, shared phone numbers, hops a single bank cannot see - each versus the bank baseline."),
    _tool("compare_bank_views", "Which transfers Bank A alone, Bank B alone, and the consortium can each see."),
    _tool("account_history", "Full history of one account: age, owner, volumes, fastest pass-through.",
          {"account_id": {"type": "string"}}, ["account_id"]),
    _tool("expand_neighbourhood", "Who else a person deals with, and whether those people are accused in other cases.",
          {"person_id": {"type": "string"}}, ["person_id"]),
    _tool("lookup_transaction", "Details of one transaction.", {"txn_id": {"type": "string"}}, ["txn_id"]),
    _tool("send_to_sanjaya", "CASES ONLY. Send the case to SANJAYA to write the report; VIDURA then checks it. "
          "Give SANJAYA a short brief on what to focus on. You may send once more with new instructions if VIDURA says REVISE.",
          {"commander_notes": {"type": "string", "description": "2-4 sentences: the points the report must make, based on what you found."}},
          ["commander_notes"]),
    _tool("record_decision", "Final step. Record your recommendation for the human officer. Cite the IDs "
          "(transactions, accounts, persons, cases, relationship codes R1-R5, detector names) that support it.",
          {"decision": {"type": "string", "description": "CASE: FILE_STR | ESCALATE | MONITOR. WATCHLIST_REVIEW: ESCALATE | MONITOR | CLOSE_RECOMMENDED. LEAD: ESCALATE_AS_LEAD | MONITOR | CLOSE_RECOMMENDED"},
           "reason": {"type": "string", "description": "2-3 sentences for the officer, in plain English."},
           "evidence_ids": {"type": "array", "items": {"type": "string"}},
           "link_with_cases": {"type": "array", "items": {"type": "string"},
                               "description": "Optional: other case IDs this should be investigated together with."}},
          ["decision", "reason", "evidence_ids"]),
]

SYSTEM = """You are DRONA, the lead investigator of CHAKRAVYUH, an anti-money-laundering unit at an Indian bank.

Your team:
- Deterministic detectors have ALREADY found every pattern. You never detect anything and you cannot create cases.
- SANJAYA writes the Suspicious Transaction Report. VIDURA, a sceptic, reviews it and argues the innocent side.
- A human officer makes every final decision. You recommend.

Your job on each item: decide what to look at, look at it with your tools, and make a recommendation.
- Start by opening the item. Then choose the tools that matter for THIS item - do not call every tool by habit.
  Mule or velocity patterns: check account ages and pass-through speed. Circles: check who controls the accounts
  and whether a single bank could see the loop. Leads and watchlist hints: look at the person's wider dealings.
- CASES: when you have enough, send the case to SANJAYA with a brief. If VIDURA returns REVISE, decide whether to send
  it back once with specific instructions. Then record a decision. A case can be FILE_STR, ESCALATE or MONITOR.
- WATCHLIST_REVIEW and LEAD items are weak signals, not cases. Be fair: a weak signal with nothing behind it should be
  closed or monitored, not escalated. Escalate only if your tools show something concrete.
- The standard is reasonable suspicion, not proof. Decision meanings for CASES:
  FILE_STR  = reasonable suspicion is established and VIDURA passed the report. Recommend the officer files it.
              Structuring just under a reporting threshold is itself reportable.
  ESCALATE  = suspicious, but a specific gap must be closed by a senior officer before filing - name the gap.
  MONITOR   = the evidence does not yet reach reasonable suspicion.
- Cite only IDs that appeared in your tool results. Invented IDs are rejected automatically.
- Copy numbers exactly as the tools give them. Never calculate, convert or re-format an amount.
  Prefer citing IDs over quoting rupee figures in your reason; any amount you do quote is checked by code.
- Keep every "why" to one short sentence. Be decisive: most items need 3-6 tool calls."""


# =====================================================================
# THE INVESTIGATION LOOP
# =====================================================================

def _chat(client, **kw):
    for attempt in range(8):
        try:
            return client.chat.completions.create(**kw)
        except Exception as exc:  # noqa: BLE001
            if attempt == 7:
                raise
            wait = min(2 + attempt * 5, 20)
            if "rate" in str(exc).lower() or "429" in str(exc):
                wait = max(wait, 15)
            print(f"    retry {attempt + 1} in {wait}s after: {str(exc)[:160]}")
            time.sleep(wait)


def triage(client, world):
    queue = []
    for it in world.items.values():
        if it["kind"] == "CASE":
            c = world.cases[it["id"]]
            queue.append({"item": it["id"], "kind": "CASE", "detectors": c["detectors_fired"],
                          "people": len(c["core_people"]), "volume": agents.format_inr(c["total_evidence_amount"])["words"],
                          "principal_cycled": world.principal(c),
                          "hours": round(c["hours_spanned"], 1), "crosses_banks": c["crosses_banks"],
                          "relationship_flags": world.rel.get(it["id"], {}).get("signals_fired", [])})
        else:
            d, line, _ = world.open_item(it)
            queue.append({"item": it["id"], "kind": it["kind"], "summary": line})
    resp = _chat(client, model=COMMANDER_MODEL, temperature=0.2, response_format={"type": "json_object"},
                 messages=[{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": json.dumps({
                               "task": "Triage this queue. Order every item from most to least urgent and give a one-sentence reason each. "
                                       "Respond as JSON: {\"order\": [{\"item\": \"...\", \"reason\": \"...\"}]}",
                               "queue": queue})}])
    order = json.loads(resp.choices[0].message.content).get("order", [])
    clean, seen = [], set()
    for o in order:
        if o.get("item") in world.items and o["item"] not in seen:
            seen.add(o["item"])
            clean.append({"item": o["item"], "reason": str(o.get("reason", ""))})
    for iid in world.items:           # anything the model forgot still gets worked
        if iid not in seen:
            clean.append({"item": iid, "reason": "Added by code: missing from triage order."})
    return clean


def investigate(client, world, item, triage_note, rank):
    kind = item["kind"]
    log = {"item": item["id"], "kind": kind, "triage_rank": rank, "triage_reason": triage_note,
           "steps": [], "writer_runs": [], "blocked": [], "decision": None}
    seen_ids, evidence_calls = set(), 0
    seen_amounts = set()          # every rupee string a tool has shown DRONA
    tx_lookup = None
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Investigate item {item['id']} (type {kind}). Your triage note: {triage_note}"}]

    for step in range(1, MAX_STEPS + 1):
        resp = _chat(client, model=COMMANDER_MODEL, temperature=0.2, messages=msgs, tools=TOOLS,
                     tool_choice="required", parallel_tool_calls=False)
        msg = resp.choices[0].message
        call = msg.tool_calls[0]
        msgs.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}]})
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        why = str(args.pop("why", "")).strip()
        t0 = time.time()
        entry = {"n": step, "tool": name, "why": why, "args": args}

        if name in EVIDENCE_TOOLS:
            fn = getattr(world, name)
            if name == "account_history":
                data, line, ids = fn(item, str(args.get("account_id", "")))
            elif name == "expand_neighbourhood":
                data, line, ids = fn(item, str(args.get("person_id", "")))
            elif name == "lookup_transaction":
                data, line, ids = fn(item, str(args.get("txn_id", "")))
            else:
                data, line, ids = fn(item)
            if not (isinstance(data, dict) and "error" in data):
                evidence_calls += 1
                seen_ids |= {i for i in ids if i}
            result = data

        elif name == "send_to_sanjaya":
            if kind != "CASE":
                result, line = {"error": "Only cases can be written up. Record a decision instead."}, "refused: not a case"
            elif len(log["writer_runs"]) >= MAX_WRITER_RUNS:
                result, line = {"error": "Writer limit reached. Record a decision."}, "refused: writer limit reached"
            else:
                if tx_lookup is None:
                    c = world.cases[item["id"]]
                    tx_lookup = agents.load_transactions(set(c["evidence_txn_ids"]) | set(c["supporting_txn_ids"]))
                packet = agents.build_evidence_packet(world.cases[item["id"]], tx_lookup, agents.load_entities())
                packet["commander_notes"] = str(args.get("commander_notes", ""))
                narrative, fc, verification, final_conf = agents.investigate_case(client, packet)
                run = {"commander_notes": packet["commander_notes"], "narrative": narrative, "fact_check": fc,
                       "verification": verification, "final_confidence": final_conf}
                log["writer_runs"].append(run)
                result = {"sanjaya_summary": narrative.get("summary"), "sanjaya_recommends": narrative.get("recommended_action"),
                          "fact_check": f"{fc['passed']} of {fc['checked']} facts confirmed", "fact_failures": fc["failures"][:5],
                          "vidura_verdict": verification.get("verdict"), "vidura_innocent_explanation": verification.get("innocent_explanation"),
                          "vidura_weaknesses": verification.get("weaknesses", [])[:4], "final_confidence": final_conf}
                line = (f"SANJAYA wrote the case · fact-check {fc['passed']}/{fc['checked']} · "
                        f"VIDURA: {verification.get('verdict')} · confidence {final_conf}")

        elif name == "record_decision":
            decision = str(args.get("decision", "")).upper()
            cited = [str(x) for x in args.get("evidence_ids", [])]
            links = [str(x) for x in args.get("link_with_cases", []) or []]
            allowed = world.allowed_ids(item, seen_ids)
            bad = [x for x in cited if x not in allowed] + [x for x in links if x not in world.cases]
            problem = None
            if decision not in DECISIONS[kind]:
                problem = f"Decision must be one of {DECISIONS[kind]}."
            elif evidence_calls < MIN_EVIDENCE_TOOLS:
                problem = f"Look before you decide: use at least {MIN_EVIDENCE_TOOLS} evidence tools first."
            elif kind == "CASE" and decision == "FILE_STR" and not log["writer_runs"]:
                problem = "A case must be written by SANJAYA and checked by VIDURA before FILE_STR."
            elif (kind == "CASE" and decision == "FILE_STR"
                  and log["writer_runs"][-1]["verification"].get("verdict") == "REJECT"):
                problem = "VIDURA rejected the latest report. You cannot recommend FILE_STR on a rejected report."
            elif not cited:
                problem = "Cite at least one ID from your tool results."
            elif [m for m in agents.MONEY_SPAN_RE.findall(str(args.get("reason", "")))
                  if agents._normalize_money_text(m) not in seen_amounts]:
                wrong = [m for m in agents.MONEY_SPAN_RE.findall(str(args.get("reason", "")))
                         if agents._normalize_money_text(m) not in seen_amounts]
                problem = (f"These amounts in your reason were not shown by any tool, exactly as written: {wrong}. "
                           f"Copy amounts verbatim or leave them out.")
                log["blocked"].append({"step": step, "invalid_amounts": wrong})
            elif agents.typology_violations(str(args.get("reason", "")),
                                            world.cases[item["id"]]["detectors_fired"] if kind == "CASE" else []):
                problem = ("Your reason names a laundering method the detectors did not prove: "
                           + "; ".join(agents.typology_violations(str(args.get("reason", "")),
                                       world.cases[item["id"]]["detectors_fired"] if kind == "CASE" else []))
                           + ". Describe only what the evidence shows.")
                log["blocked"].append({"step": step, "invalid_typology": [problem]})
            elif bad:
                problem = f"These IDs are not in this item's evidence and were rejected: {bad}. Cite only what your tools showed."
                log["blocked"].append({"step": step, "invalid_ids": bad})
            if problem:
                result, line = {"accepted": False, "error": problem}, f"rejected by code: {problem}"
            else:
                log["decision"] = {"decision": decision, "reason": str(args.get("reason", "")),
                                   "evidence_ids": cited, "link_with_cases": links}
                result, line = {"accepted": True}, f"{decision}: {args.get('reason', '')}"
        else:
            result, line = {"error": f"unknown tool {name}"}, f"unknown tool {name}"

        if name != "record_decision":
            blob = json.dumps(result, default=str, ensure_ascii=False) + " " + line
            seen_amounts |= {agents._normalize_money_text(m) for m in agents.MONEY_SPAN_RE.findall(blob)}
        entry["result"] = line
        entry["ms"] = int((time.time() - t0) * 1000)
        log["steps"].append(entry)
        msgs.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)[:3500]})
        if log["decision"]:
            break

    if not log["decision"]:
        log["decision"] = {"decision": "ESCALATE" if kind == "CASE" else "MONITOR",
                           "reason": "DRONA ran out of its step budget, so the item goes to a human as-is.",
                           "evidence_ids": [], "link_with_cases": [], "fallback": True}
    print(f"  {item['id']:<6} {len(log['steps'])} steps -> {log['decision']['decision']}")
    return log


def main():
    client = agents.get_client()
    if client is None:
        print("No OPENAI_API_KEY in .env - DRONA needs the API. Existing investigation_log.json left untouched.")
        sys.exit(1)
    world = World()
    print(f"DRONA: {len(world.items)} items in the queue "
          f"({sum(i['kind'] == 'CASE' for i in world.items.values())} cases, "
          f"{sum(i['kind'] != 'CASE' for i in world.items.values())} weak signals)")
    t0 = time.time()
    # Resume: if an earlier run crashed part-way (e.g. rate limits), keep the
    # triage and every item already finished, and only work what is left.
    partial = {}
    if "--only" in sys.argv:
        # re-investigate just these items, keep everything else from the last full run
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
        with open(LOG_PATH, encoding="utf-8") as f:
            prev = json.load(f)
        partial = {"triage": prev["triage"], "items": {k: v for k, v in prev["items"].items() if k not in only}}
        print(f"  re-investigating only: {sorted(only)}")
    elif os.path.exists(PARTIAL_PATH) and "--fresh" not in sys.argv:
        with open(PARTIAL_PATH, encoding="utf-8") as f:
            partial = json.load(f)
        print(f"  resuming: {len(partial.get('items', {}))} item(s) already done")
    order = partial.get("triage") or triage(client, world)
    print("  triage:", " > ".join(o["item"] for o in order))
    done = dict(partial.get("items", {}))
    import threading
    lock = threading.Lock()

    def work(r, o):
        if o["item"] in done:
            return done[o["item"]]
        lg = investigate(client, world, world.items[o["item"]], o["reason"], r)
        with lock:
            done[o["item"]] = lg
            with open(PARTIAL_PATH, "w", encoding="utf-8") as f:
                json.dump({"triage": order, "items": done}, f, default=str)
        return lg

    print(f"  working with {WORKERS} parallel worker(s)")
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(work, r, o) for r, o in enumerate(order, 1)]
        logs = [f.result() for f in futs]

    # the cases SANJAYA wrote under DRONA's command become the case files
    written = {}
    if os.path.exists(agents.OUTPUT_PATH):
        with open(agents.OUTPUT_PATH, encoding="utf-8") as f:
            written = json.load(f)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for lg in logs:
        if lg["writer_runs"]:
            run = lg["writer_runs"][-1]
            written[lg["item"]] = {"case_id": lg["item"], "narrative": run["narrative"], "fact_check": run["fact_check"],
                                   "verification": run["verification"], "final_confidence": run["final_confidence"],
                                   "model": agents.MODEL, "commander": "DRONA (" + COMMANDER_MODEL + ")",
                                   "commander_notes": run["commander_notes"], "generated_at": now}
    with open(agents.OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(written, f, indent=2)

    decisions = defaultdict(int)
    for lg in logs:
        decisions[lg["decision"]["decision"]] += 1
    runs = [r for lg in logs for r in lg["writer_runs"]]
    meta = {
        "commander_model": COMMANDER_MODEL, "writer_model": agents.MODEL, "generated_at": now,
        "seconds": round(time.time() - t0, 1), "items": len(logs),
        "cases": sum(lg["kind"] == "CASE" for lg in logs), "weak_signals": sum(lg["kind"] != "CASE" for lg in logs),
        "tool_calls": sum(len(lg["steps"]) for lg in logs),
        "evidence_tool_calls": sum(1 for lg in logs for s in lg["steps"] if s["tool"] in EVIDENCE_TOOLS),
        "writer_runs": len(runs), "rewrites": sum(max(0, len(lg["writer_runs"]) - 1) for lg in logs),
        "vidura_pass": sum(1 for lg in logs if lg["writer_runs"] and lg["writer_runs"][-1]["verification"].get("verdict") == "PASS"),
        "facts_checked": sum(r["fact_check"]["checked"] for lg in logs for r in lg["writer_runs"][-1:]),
        "facts_confirmed": sum(r["fact_check"]["passed"] for lg in logs for r in lg["writer_runs"][-1:]),
        "blocked_citations": sum(len(b.get("invalid_ids", [])) + len(b.get("invalid_amounts", []))
                                 + len(b.get("invalid_typology", [])) for lg in logs for b in lg["blocked"]),
        "decisions": dict(decisions),
        "fallbacks": sum(1 for lg in logs if lg["decision"].get("fallback")),
    }
    out = {"meta": meta, "triage": order, "items": {lg["item"]: lg for lg in logs}}
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    if os.path.exists(PARTIAL_PATH):
        os.remove(PARTIAL_PATH)
    print(json.dumps(meta, indent=2))
    print(f"-> {LOG_PATH}\n-> {agents.OUTPUT_PATH}")


if __name__ == "__main__":
    main()
