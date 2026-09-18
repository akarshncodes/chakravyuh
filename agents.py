#!/usr/bin/env python3
"""
CHAKRAVYUH AI - Stages 6 & 7: the Investigator and the Verifier.

Stage 6 (Investigator, LLM): turns a verified graph-detected case into a
plain-English STR narrative. It is given ONLY the evidence packet for that
case - it does not decide whether a pattern exists, it explains one that
deterministic detectors already proved.

Stage 7 (Verifier, two layers):
  Layer 1 - deterministic fact check (plain code): every account, txn,
            person, amount and date the narrative mentions must trace back
            to the evidence packet. No AI judgement involved.
  Layer 2 - adversarial AI review: a second model, with a skeptical system
            prompt, argues for the innocent explanation before conceding.

Detection happened in earlier stages and is not re-derived here. This file
only writes language about evidence that already exists, and then checks
that language against the evidence it is describing.

ABSOLUTE RULE: ground_truth.csv, true_entity_id and owner_entity are the
answer key and are never opened, read or referenced anywhere in this file.
The AI must not see which ring a case belongs to - only what the evidence
shows.

Standard library + openai + python-dotenv. Does not modify generate_data.py,
entity_resolution.py, graph_builder.py, detectors.py or case_builder.py.
"""

import csv
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# =====================================================================
# SETTINGS
# =====================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_PATH = os.path.join(HERE, "cases.json")
TRANSACTIONS_PATH = os.path.join(HERE, "transactions.csv")
RESOLVED_ENTITIES_PATH = os.path.join(HERE, "resolved_entities.csv")
OUTPUT_PATH = os.path.join(HERE, "cases_written.json")

MODEL = "gpt-4o-mini"       # change here, nowhere else
TEMPERATURE = 0.2           # low, for consistent report language

load_dotenv(os.path.join(HERE, ".env"))


# =====================================================================
# SYSTEM PROMPTS
# =====================================================================

INVESTIGATOR_SYSTEM_PROMPT = """You are a financial crime analyst writing a Suspicious Transaction Report (STR) for India's Financial Intelligence Unit (FIU-IND).

Rules you must follow exactly:
- You may ONLY reference transactions, accounts, people and amounts that appear in the evidence packet you are given. Inventing any detail not present in the packet is a critical failure.
- Write in plain, professional English. State amounts in Indian format (for example "Rs 2.4 crore", "Rs 9,85,000").
- The evidence packet has already been detected and structurally proven by deterministic graph analysis. You are not deciding whether a suspicious pattern exists - it does. Your job is only to explain it clearly and accurately.
- If any person in the "people" list has has_unverified_link = true, say so explicitly in why_suspicious or what_happened, and lower your confidence rating accordingly.
- Respond with a single JSON object and nothing else, in exactly this shape:
{
  "summary": "two sentences a busy compliance officer can read in 10 seconds",
  "what_happened": "the money's journey step by step, in chronological order, with real amounts, times and account numbers taken from the packet",
  "typology": "which laundering method this matches (circular transfer / round-tripping, mule network / fan-out fan-in, rapid layering, structuring) and why",
  "why_suspicious": "concrete reasoning - closed loop, value returned, time compressed, threshold proximity, no economic purpose - never vague language like 'this looks unusual'",
  "recommended_action": "one of FILE_STR, ESCALATE, MONITOR, CLOSE",
  "confidence": {"level": "HIGH, MEDIUM or LOW", "reason": "one line"}
}"""

VERIFIER_SYSTEM_PROMPT = """You are a skeptical senior compliance reviewer. Your job is to find reasons this case should NOT be filed. Assume the analyst is wrong until the evidence convinces you.

Specifically:
- Propose the most plausible INNOCENT explanation for this pattern (treasury sweeps between related companies, payroll distribution, a legitimate supplier settlement cycle, coincidence).
- Then state whether the evidence rules that explanation out, and why.
- Check whether the analyst's stated reasoning actually follows from the evidence given, not just from confident-sounding language.
- Note any weakness a regulator or a court would attack.

You are given the same evidence packet the analyst had, plus the analyst's narrative. Respond with a single JSON object and nothing else, in exactly this shape:
{
  "verdict": "PASS, REVISE or REJECT",
  "confidence": "HIGH, MEDIUM or LOW",
  "innocent_explanation": "the best innocent reading of this pattern, and whether it survives scrutiny",
  "weaknesses": ["specific weak points a regulator or court would attack - may be empty"],
  "notes": "one short paragraph for the human officer"
}"""


# =====================================================================
# LOADING
#
# resolved_entities.csv carries only entity_key / canonical_name /
# is_watchlisted / has_unverified_link for our purposes here - it has no
# true_entity_id column (that lives solely in customer_records.csv, which
# this file never opens). ground_truth.csv is never opened anywhere below.
# =====================================================================

def load_cases():
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)["cases"]


def load_transactions(needed_ids):
    lookup = {}
    with open(TRANSACTIONS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["txn_id"] in needed_ids:
                lookup[row["txn_id"]] = {
                    "timestamp": row["timestamp"],
                    "from_account": row["from_account"],
                    "to_account": row["to_account"],
                    "amount": float(row["amount"]),
                    "channel": row["channel"],
                    "from_bank": row["from_bank"],
                    "to_bank": row["to_bank"],
                }
    return lookup


def load_entities():
    entities = {}
    with open(RESOLVED_ENTITIES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entities[row["entity_key"]] = {
                "canonical_name": row["canonical_name"],
                "is_watchlisted": row["is_watchlisted"].strip().lower() == "true",
                "has_unverified_link": row["has_unverified_link"].strip().lower() == "true",
            }
    return entities


# =====================================================================
# EVIDENCE PACKET - the only thing the model ever sees
# =====================================================================

def build_evidence_packet(case, txn_lookup, entities):
    txn_ids = case["evidence_txn_ids"] + case["supporting_txn_ids"]
    transactions = []
    for tid in txn_ids:
        row = txn_lookup.get(tid)
        if row is None:
            continue
        transactions.append({"txn_id": tid, **row})

    people = []
    seen = set()
    for role, plist in (("CORE", case["core_people"]), ("CONTEXT", case["context_people"])):
        for p in plist:
            ek = p["entity_key"]
            if ek in seen:
                continue
            seen.add(ek)
            ent = entities.get(ek, {})
            people.append({
                "entity_key": ek,
                "name": ent.get("canonical_name", p.get("name", "")),
                "role": role,
                "is_watchlisted": ent.get("is_watchlisted", bool(p.get("is_watchlisted", False))),
                "has_unverified_link": ent.get("has_unverified_link", False),
            })

    return {
        "case_id": case["case_id"],
        "lane": case["lane"],
        "detectors_fired": case["detectors_fired"],
        "core_people": case["core_people"],
        "context_people": case["context_people"],
        "evidence_txn_ids": case["evidence_txn_ids"],
        "supporting_txn_ids": case["supporting_txn_ids"],
        "total_evidence_amount": case["total_evidence_amount"],
        "first_timestamp": case["first_timestamp"],
        "last_timestamp": case["last_timestamp"],
        "hours_spanned": case["hours_spanned"],
        "banks_involved": case["banks_involved"],
        "transactions": transactions,
        "people": people,
    }


# =====================================================================
# LAYER 1 - DETERMINISTIC FACT CHECK (no AI)
# =====================================================================

ACC_RE = re.compile(r"\bACC\d+\b")
TXN_RE = re.compile(r"\bTXN\d+\b")
PERSON_RE = re.compile(r"\bPERSON\d+\b")

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
_MONTH_NAMES = "|".join(_MONTHS.keys())

AMOUNT_CUR_RE = re.compile(r"\b(?:Rs\.?|₹|INR)\s*(\d[\d,]*(?:\.\d+)?)\s*(crore|lakh)?", re.I)
AMOUNT_BARE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(crore|lakh)\b", re.I)
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_DMY_RE = re.compile(r"\b(\d{1,2})\s+(" + _MONTH_NAMES + r")\s+(\d{4})\b", re.I)
DATE_MDY_RE = re.compile(r"\b(" + _MONTH_NAMES + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.I)


def _parse_amount(num_str, suffix):
    val = float(num_str.replace(",", ""))
    if suffix:
        suffix = suffix.lower()
        if suffix == "crore":
            val *= 1e7
        elif suffix == "lakh":
            val *= 1e5
    return val


def extract_amounts(text):
    spans, amounts = [], []
    for m in AMOUNT_CUR_RE.finditer(text):
        spans.append(m.span())
        amounts.append(_parse_amount(m.group(1), m.group(2)))
    for m in AMOUNT_BARE_RE.finditer(text):
        s, e = m.span()
        if any(s >= a and e <= b for a, b in spans):
            continue  # already captured as part of a currency-prefixed match
        spans.append((s, e))
        amounts.append(_parse_amount(m.group(1), m.group(2)))
    return amounts


def extract_dates(text):
    dates = []
    for y, mo, d in DATE_ISO_RE.findall(text):
        try:
            dates.append(datetime(int(y), int(mo), int(d)).date())
        except ValueError:
            pass
    for d, mon, y in DATE_DMY_RE.findall(text):
        try:
            dates.append(datetime(int(y), _MONTHS[mon.lower()], int(d)).date())
        except ValueError:
            pass
    for mon, d, y in DATE_MDY_RE.findall(text):
        try:
            dates.append(datetime(int(y), _MONTHS[mon.lower()], int(d)).date())
        except ValueError:
            pass
    return dates


def _narrative_text(narrative):
    parts = [str(narrative.get(f, "")) for f in
             ("summary", "what_happened", "typology", "why_suspicious")]
    conf = narrative.get("confidence")
    if isinstance(conf, dict):
        parts.append(str(conf.get("reason", "")))
    elif conf:
        parts.append(str(conf))
    return " ".join(parts)


def run_fact_check(narrative, packet):
    """
    Every ACC/TXN/PERSON id, rupee amount and date the narrative mentions
    must trace back to this case's own evidence packet. This is plain code,
    not a model call - the investigator does not get to grade its own work.
    """
    allowed_accounts = set()
    for p in packet["core_people"] + packet["context_people"]:
        allowed_accounts.update(p.get("accounts", []))
    for t in packet["transactions"]:
        allowed_accounts.add(t["from_account"])
        allowed_accounts.add(t["to_account"])

    allowed_txn_ids = set(packet["evidence_txn_ids"]) | set(packet["supporting_txn_ids"])
    allowed_persons = {p["entity_key"] for p in packet["core_people"] + packet["context_people"]}
    packet_amounts = [t["amount"] for t in packet["transactions"]]
    case_total = packet["total_evidence_amount"]
    start_date = datetime.strptime(packet["first_timestamp"], "%Y-%m-%d %H:%M:%S").date()
    end_date = datetime.strptime(packet["last_timestamp"], "%Y-%m-%d %H:%M:%S").date()

    text = _narrative_text(narrative)
    checked, passed = 0, 0
    failures = []

    for acc in sorted(set(ACC_RE.findall(text))):
        checked += 1
        if acc in allowed_accounts:
            passed += 1
        else:
            failures.append(f"Account {acc} is not part of this case's evidence")

    for txn in sorted(set(TXN_RE.findall(text))):
        checked += 1
        if txn in allowed_txn_ids:
            passed += 1
        else:
            failures.append(f"Transaction {txn} is not part of this case's evidence")

    for person in sorted(set(PERSON_RE.findall(text))):
        checked += 1
        if person in allowed_persons:
            passed += 1
        else:
            failures.append(f"Person {person} is not part of this case")

    for amt in sorted(set(round(a) for a in extract_amounts(text))):
        checked += 1
        ok = math.isclose(amt, case_total, rel_tol=0.01) or any(
            math.isclose(amt, a, rel_tol=0.01) for a in packet_amounts)
        if ok:
            passed += 1
        else:
            failures.append(
                f"Amount Rs {amt:,.0f} matches neither the case total nor any case "
                f"transaction amount (within 1%)")

    for d in sorted(set(extract_dates(text))):
        checked += 1
        if start_date <= d <= end_date:
            passed += 1
        else:
            failures.append(
                f"Date {d.isoformat()} falls outside the case window "
                f"({start_date} to {end_date})")

    return {"checked": checked, "passed": passed, "failures": failures}


# =====================================================================
# OPENAI CALLS
# =====================================================================

def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def call_investigator(client, packet, corrections=None):
    user_content = {"evidence_packet": packet}
    if corrections:
        user_content["corrections_required"] = corrections
        user_content["instruction"] = (
            "Your previous narrative failed an automated fact-check against the raw "
            "evidence packet. Fix every item in corrections_required. Do not introduce "
            "any new claim that is not directly present in evidence_packet."
        )
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": INVESTIGATOR_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_content, default=str)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def call_verifier(client, packet, narrative):
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(
                {"evidence_packet": packet, "investigator_narrative": narrative}, default=str)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def downgrade_confidence(level):
    order = ["LOW", "MEDIUM", "HIGH"]
    level = (level or "MEDIUM").upper()
    if level not in order:
        level = "MEDIUM"
    return order[max(0, order.index(level) - 1)]


def investigate_case(client, packet):
    narrative = call_investigator(client, packet)
    fc = run_fact_check(narrative, packet)

    if fc["failures"]:
        narrative = call_investigator(client, packet, corrections=fc["failures"])
        fc = run_fact_check(narrative, packet)

    if fc["failures"]:
        # Do not silently accept a narrative that failed fact-checking twice.
        # Skip the adversarial layer entirely - there is nothing to argue
        # about if the narrative already contradicts the raw evidence.
        verification = {
            "verdict": "REJECT",
            "confidence": "LOW",
            "innocent_explanation": (
                "Not evaluated - the narrative failed automated fact-checking against "
                "the raw evidence twice and was rejected before adversarial review."),
            "weaknesses": fc["failures"],
            "notes": ("Rejected automatically: the investigator narrative still referenced "
                      "facts absent from the evidence packet after one regeneration attempt."),
        }
        return narrative, fc, verification, "LOW"

    verification = call_verifier(client, packet, narrative)
    final_confidence = str(verification.get("confidence", "MEDIUM")).upper()
    if final_confidence not in ("HIGH", "MEDIUM", "LOW"):
        final_confidence = "MEDIUM"

    if any(p["has_unverified_link"] for p in packet["people"]):
        downgraded = downgrade_confidence(final_confidence)
        if downgraded != final_confidence:
            note = ("Confidence reduced: this case depends on an identity link that was "
                    "merged on probable rather than confirmed evidence.")
            verification["notes"] = (str(verification.get("notes", "")).strip() + " " + note).strip()
        final_confidence = downgraded
        verification["confidence"] = final_confidence

    return narrative, fc, verification, final_confidence


# =====================================================================
# FALLBACK - no API key, or a live call failed. Never crash; the
# dashboard must always have something to show.
# =====================================================================

def infer_typology(detectors_fired):
    d = set(detectors_fired)
    if "CIRCLE" in d:
        return ("Circular transfer / round-tripping - funds move through a closed loop of "
                "accounts and return to their point of origin, which has no legitimate "
                "economic purpose.")
    if "SPRAY" in d:
        return ("Mule network / fan-out fan-in - one source account disperses funds to many "
                "accounts that each immediately forward them on to a single collector.")
    if "THRESHOLD" in d:
        return "Structuring - many deposits kept just under a reporting threshold."
    if "SPEED" in d:
        return ("Rapid layering - funds move through a chain of accounts in a compressed "
                "time window, resting nowhere.")
    return "Unclassified pattern flagged by deterministic detectors: " + ", ".join(sorted(d))


def build_fallback_narrative(packet):
    # "What happened" is the evidence chain only - supporting/background
    # transactions can genuinely fall outside the evidence date window (that
    # is exactly why they are background, not evidence), so mixing their raw
    # timestamps into the main journey would make even a template narrative
    # fail its own fact-check for the wrong reason.
    evidence_ids = set(packet["evidence_txn_ids"])
    evidence_txns = sorted(
        (t for t in packet["transactions"] if t["txn_id"] in evidence_ids),
        key=lambda t: t["timestamp"])
    supporting_count = len(packet["transactions"]) - len(evidence_txns)

    lines = [
        f"{t['timestamp']}: Rs {t['amount']:,.2f} from {t['from_account']} to "
        f"{t['to_account']} via {t['channel']} ({t['from_bank']} -> {t['to_bank']})"
        for t in evidence_txns
    ]
    if supporting_count:
        lines.append(f"(plus {supporting_count} background/supporting transaction(s) "
                     f"in the same period, not counted as evidence)")

    core_names = ", ".join(p["name"] for p in packet["people"] if p["role"] == "CORE") or "unnamed parties"
    return {
        "summary": (
            f"Case {packet['case_id']}: {len(evidence_txns)} evidence transactions totalling "
            f"Rs {packet['total_evidence_amount']:,.0f} across {packet['hours_spanned']:.2f} hours, "
            f"flagged by {', '.join(packet['detectors_fired'])}. Involves {core_names}."),
        "what_happened": " | ".join(lines),
        "typology": infer_typology(packet["detectors_fired"]),
        "why_suspicious": (
            f"Deterministically detected by {', '.join(packet['detectors_fired'])} across "
            f"{packet['hours_spanned']:.2f} hours spanning {', '.join(packet['banks_involved'])}. "
            f"No AI narrative analysis was performed for this case - see typology above for "
            f"the structural reason it was flagged."),
        "recommended_action": "ESCALATE",
        "confidence": {
            "level": "LOW",
            "reason": "Template-generated; no AI analysis was performed (no API key available).",
        },
    }


def fallback_case(packet, reason):
    narrative = build_fallback_narrative(packet)
    fc = run_fact_check(narrative, packet)
    verification = {
        "verdict": "NOT_VERIFIED",
        "confidence": "LOW",
        "innocent_explanation": "Not evaluated - the adversarial review step did not run.",
        "weaknesses": [],
        "notes": (f"{reason} This case was generated from a template and was never reviewed "
                  f"by the AI verifier. Treat as unverified pending manual review."),
    }
    return narrative, fc, verification, "LOW"


# =====================================================================
# MAIN
# =====================================================================

def main():
    force = "--force" in sys.argv

    cases = load_cases()
    needed_txn_ids = set()
    for c in cases:
        needed_txn_ids.update(c["evidence_txn_ids"])
        needed_txn_ids.update(c["supporting_txn_ids"])
    txn_lookup = load_transactions(needed_txn_ids)
    entities = load_entities()

    written = {}
    if os.path.exists(OUTPUT_PATH) and not force:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            written = json.load(f)

    client = get_client()
    if client is None:
        print("No OPENAI_API_KEY found (.env missing or empty) - every case will be "
              "generated from the offline template and marked NOT_VERIFIED.")

    n_cached, n_generated = 0, 0
    for case in cases:
        cid = case["case_id"]
        if cid in written and not force:
            n_cached += 1
            continue

        packet = build_evidence_packet(case, txn_lookup, entities)

        if client is None:
            narrative, fc, verification, final_conf = fallback_case(
                packet, "No OPENAI_API_KEY was available.")
            model_used = "template (no API key)"
        else:
            try:
                narrative, fc, verification, final_conf = investigate_case(client, packet)
                model_used = MODEL
            except Exception as exc:  # noqa: BLE001 - must never crash the pipeline
                print(f"  [WARN] {cid}: API call failed ({exc}); using offline template")
                narrative, fc, verification, final_conf = fallback_case(
                    packet, f"The OpenAI API call failed ({exc}).")
                model_used = "template (API call failed)"

        written[cid] = {
            "case_id": cid,
            "narrative": narrative,
            "fact_check": fc,
            "verification": verification,
            "final_confidence": final_conf,
            "model": model_used,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        n_generated += 1
        print(f"  {cid}: verdict={verification['verdict']:<12} "
              f"confidence={final_conf:<6} fact-check {fc['passed']}/{fc['checked']}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(written, f, indent=2)

    print(f"\nCached: {n_cached}  Generated: {n_generated}  Total written: {len(written)}")
    print(f"-> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
