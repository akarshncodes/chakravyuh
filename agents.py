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
# INDIAN RUPEE FORMATTING
#
# The model cannot reliably do lakh/crore arithmetic (1 crore = 1,00,00,000,
# not 10,00,000 or 1,000,000 - a mistake gpt-4o-mini made repeatedly). So it
# never gets a raw number to work with: every amount in the evidence packet
# is pre-formatted here, in Python, and the model is instructed to copy the
# strings verbatim rather than compute anything.
# =====================================================================

def _indian_group(int_str):
    """Indian digit grouping: last 3 digits, then pairs. '24000000' -> '2,40,00,000'."""
    if len(int_str) <= 3:
        return int_str
    last3 = int_str[-3:]
    rest = int_str[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups + [last3])


def _trim(x):
    """2.40 -> '2.4', 14.09 -> '14.09', 3.00 -> '3' - no forced trailing zeros."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def format_inr(amount):
    """
    Rs amount -> {"digits": "Rs 2,40,00,000", "words": "Rs 2.4 crore"}.
    1 crore = 1,00,00,000; 1 lakh = 1,00,000. This is the ONLY place amounts
    are formatted - the model never sees a raw number, only these strings.
    """
    amount = round(float(amount), 2)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise >= 100:
        rupees += 1
        paise -= 100

    digits = f"{sign}Rs {_indian_group(str(rupees))}"
    if paise:
        digits += f".{paise:02d}"

    if amount >= 1_00_00_000:
        words = f"{sign}Rs {_trim(amount / 1_00_00_000)} crore"
    elif amount >= 1_00_000:
        words = f"{sign}Rs {_trim(amount / 1_00_000)} lakh"
    else:
        words = digits

    return {"digits": digits, "words": words}


assert format_inr(24000000)["digits"] == "Rs 2,40,00,000"
assert format_inr(24000000)["words"] == "Rs 2.4 crore"
assert format_inr(140947500)["digits"] == "Rs 14,09,47,500"
assert format_inr(140947500)["words"] == "Rs 14.09 crore"
assert format_inr(23837091.92)["digits"] == "Rs 2,38,37,091.92"


# =====================================================================
# SYSTEM PROMPTS
# =====================================================================

INVESTIGATOR_SYSTEM_PROMPT = """You are a financial crime analyst writing a Suspicious Transaction Report (STR) for India's Financial Intelligence Unit (FIU-IND).

Rules you must follow exactly:
- You may ONLY reference transactions, accounts, people and amounts that appear in the evidence packet you are given. Inventing any detail not present in the packet is a critical failure.
- Write in plain, professional English.
- NUMBERS ARE PRE-FORMATTED. NEVER CALCULATE, CONVERT, ROUND, RE-GROUP OR RE-EXPRESS ANY AMOUNT. Every monetary figure in the packet already comes as exact strings - a "digits" form (e.g. "Rs 2,40,00,000") and a "words" form (e.g. "Rs 2.4 crore") - under each transaction's "amount", and under total_volume (and amount_cycled, when present - see below). Whenever you mention an amount, copy one of these strings EXACTLY as given, character for character. Never write a rupee figure that does not appear verbatim in the evidence packet - not a total you added up, not a re-grouped version, not a rounded one. The same applies to return_percentage (e.g. "95.4%") when it is present: copy it, do not compute it yourself.
- AMOUNTS: total_volume is the sum of every transaction in the case - report it as the amount moved. amount_cycled and return_percentage appear in the packet ONLY when is_circular is true (a CIRCLE case, money looping back to its origin) - if you do not see an "amount_cycled" key at all, the case is not circular, so just report total_volume as the amount, as normal. amount_cycled is the largest SINGLE transaction in the case - the actual principal that moved - and it is always a SMALLER number than total_volume, which counts that same principal once per hop. These are two DIFFERENT figures - never write the same amount for both.
- CIRCULAR CASES - DO NOT COMPOSE THE AMOUNT SENTENCE YOURSELF. When "circular_amount_summary" is present in the packet, it is already the complete, correct sentence fragment - for example:
  "Rs 2.4 crore was cycled through six accounts, generating Rs 14.09 crore in total transaction volume, with 95.4% of the principal returning to the originating account."
  Copy circular_amount_summary VERBATIM into your summary and why_suspicious (you may add a leading/trailing clause of your own around it, but never alter, reorder, or recompute the two amounts or the percentage inside it). Do not independently combine amount_cycled and total_volume into a sentence of your own wording - that is exactly how the two figures get swapped.
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

VERIFIER_SYSTEM_PROMPT = """You are a senior compliance reviewer deciding whether a Suspicious Transaction Report should be filed with FIU-IND.

THE STANDARD IS REASONABLE SUSPICION, NOT PROOF. You are not deciding guilt. You are deciding whether a reasonable compliance officer, seeing this pattern, would consider it unusual enough to report. Proof of criminal intent is never available at this stage and is not required.

Your job is rigour, not obstruction.

For each innocent explanation you propose, you MUST test it against the specific evidence and state whether the evidence rules it out. Do not accept an explanation merely because intent is unproven. Example: a supplier settlement does not return funds to the payer; payroll does not flow back to the employer; treasury sweeps occur between accounts under common ownership.

VERDICTS - use these definitions exactly:
  PASS   - the pattern is genuinely anomalous, the narrative is supported by the evidence, and no innocent explanation is consistent with what the evidence shows. File it.
  REVISE - the pattern warrants reporting but the narrative overstates, understates or reasons poorly. Say what to change.
  REJECT - reserved for: a factual error, a narrative unsupported by its own evidence, or an innocent explanation that the evidence positively CONFIRMS. Never reject merely because intent is unproven.

Most genuinely anomalous patterns should PASS. If you find yourself rejecting everything, you are applying a criminal-court standard and that is wrong.

You are given the same evidence packet the analyst had, plus the analyst's narrative. Respond with a single JSON object and nothing else, in exactly this shape:
{
  "verdict": "PASS, REVISE or REJECT",
  "confidence": "HIGH, MEDIUM or LOW",
  "innocent_explanation": "the innocent explanation you tested, and whether the specific evidence rules it out (say how) or confirms it",
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
    evidence_id_set = set(case["evidence_txn_ids"])
    transactions = []
    evidence_amounts = []
    for tid in txn_ids:
        row = txn_lookup.get(tid)
        if row is None:
            continue
        # Amounts appear ONLY as pre-formatted strings from here on - the
        # model never receives a raw number for a transaction amount.
        transactions.append({
            "txn_id": tid,
            "timestamp": row["timestamp"],
            "from_account": row["from_account"],
            "to_account": row["to_account"],
            "amount": format_inr(row["amount"]),
            "channel": row["channel"],
            "from_bank": row["from_bank"],
            "to_bank": row["to_bank"],
        })
        if tid in evidence_id_set:
            evidence_amounts.append(row["amount"])

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

    # A circular ring returns to its origin, so total_evidence_amount (the
    # sum of every hop) counts the same principal once per hop - the hero
    # ring's Rs 2.4 crore reads as Rs 14.09 crore if that sum is quoted as
    # "the amount laundered". total_volume is reported for every case;
    # is_circular decides whether that hop-sum needs the extra context.
    is_circular = "CIRCLE" in case["detectors_fired"]
    total_volume_raw = case["total_evidence_amount"]

    packet = {
        "case_id": case["case_id"],
        "lane": case["lane"],
        "detectors_fired": case["detectors_fired"],
        "is_circular": is_circular,
        "core_people": case["core_people"],
        "context_people": case["context_people"],
        "evidence_txn_ids": case["evidence_txn_ids"],
        "supporting_txn_ids": case["supporting_txn_ids"],
        "total_volume": format_inr(total_volume_raw),
        "first_timestamp": case["first_timestamp"],
        "last_timestamp": case["last_timestamp"],
        "hours_spanned": case["hours_spanned"],
        "banks_involved": case["banks_involved"],
        "transactions": transactions,
        "people": people,
    }

    # amount_cycled (the single largest evidence transaction: the actual
    # principal that moved) and return_percentage are only meaningful for a
    # CIRCLE case, where that principal loops back to its origin. A mule
    # network, velocity chain or structuring case has no principal that
    # "returns" - money genuinely moves onward - so quoting a largest-hop
    # figure next to the total is meaningless (e.g. "Rs 88,691.70 cycled"
    # inside a mule-network report makes no sense). Omit both keys entirely
    # for non-circular cases rather than send a number that doesn't apply;
    # the investigator prompt is written to only look for them when
    # is_circular is true.
    if is_circular and evidence_amounts:
        amount_cycled_raw = max(evidence_amounts)
        # A circle has >=3 hops (CIRCLE_MIN_HOPS in detectors.py), so the
        # sum of every hop is always strictly greater than any single hop.
        # If this ever trips, amount_cycled and total_volume have been
        # computed from the same figure somewhere - the exact bug that
        # produced "Rs 14.09 crore was cycled ... generating Rs 14.09
        # crore" (the model was handed the same number twice).
        if len(evidence_amounts) > 1:
            assert amount_cycled_raw < total_volume_raw, (
                f"{case['case_id']}: amount_cycled (Rs {amount_cycled_raw:,.2f}) must be "
                f"strictly less than total_volume (Rs {total_volume_raw:,.2f}) for a "
                f"multi-transaction case")
        packet["amount_cycled"] = format_inr(amount_cycled_raw)
        last_evidence_amount = None
        for tid in case["evidence_txn_ids"]:
            row = txn_lookup.get(tid)
            if row is not None:
                last_evidence_amount = row["amount"]
        if last_evidence_amount is not None and amount_cycled_raw:
            packet["return_percentage"] = f"{last_evidence_amount / amount_cycled_raw * 100:.1f}%"

        # The model kept substituting total_volume for amount_cycled when
        # composing this sentence itself, even with both correct strings in
        # front of it - so stop asking it to compose the sentence at all.
        # It gets one ready-made, pre-assembled phrase and copies it.
        evidence_only = [t for t in transactions if t["txn_id"] in evidence_id_set]
        num_accounts = len({t["from_account"] for t in evidence_only} |
                           {t["to_account"] for t in evidence_only})
        packet["circular_amount_summary"] = _circular_amount_phrase(
            packet["amount_cycled"], packet["total_volume"],
            packet.get("return_percentage"), num_accounts)

    return packet


def _circular_amount_phrase(amount_cycled, total_volume, return_percentage, num_accounts):
    phrase = (f"{amount_cycled['words']} was cycled through {num_accounts} accounts, "
              f"generating {total_volume['words']} in total transaction volume")
    if return_percentage:
        phrase += f", with {return_percentage} of the principal returning to the originating account"
    return phrase


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

DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_DMY_RE = re.compile(r"\b(\d{1,2})\s+(" + _MONTH_NAMES + r")\s+(\d{4})\b", re.I)
DATE_MDY_RE = re.compile(r"\b(" + _MONTH_NAMES + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.I)

# Locates anything in the narrative that LOOKS like a monetary figure -
# Rs/₹/INR-prefixed, a bare "N crore"/"N lakh", or a bare comma-grouped
# number (commas are not used for anything else in our narratives: dates
# are ISO, account/txn ids have none). The matched TEXT is what matters,
# not its numeric value - see run_fact_check.
MONEY_SPAN_RE = re.compile(
    r"(?:Rs\.?|₹|INR)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crore|lakh))?"
    r"|\b\d+(?:\.\d+)?\s*(?:crore|lakh)\b"
    r"|\b\d{1,3}(?:,\d{2,3}){1,}(?:\.\d+)?\b",
    re.I,
)


def _normalize_money_text(s):
    """Collapse whitespace and fold Rs./₹/INR to a single canonical 'Rs '
    prefix, so trivial punctuation/spacing differences don't cause a false
    fact-check failure - the actual digits/words still have to match
    exactly."""
    s = re.sub(r"\s+", " ", s.strip())
    if re.match(r"^(₹|Rs\.?|INR)\b", s, re.I):
        s = re.sub(r"^(₹|Rs\.?|INR)\s*", "Rs ", s, flags=re.I)
    else:
        s = "Rs " + s
    return s


def collect_allowed_amount_strings(packet):
    """Every 'digits' and 'words' string in the packet, normalized - the
    ONLY monetary figures a narrative is allowed to contain."""
    allowed = set()
    for t in packet["transactions"]:
        allowed.add(_normalize_money_text(t["amount"]["digits"]))
        allowed.add(_normalize_money_text(t["amount"]["words"]))
    for key in ("amount_cycled", "total_volume"):
        if key not in packet:
            continue  # amount_cycled is absent for non-circular cases
        allowed.add(_normalize_money_text(packet[key]["digits"]))
        allowed.add(_normalize_money_text(packet[key]["words"]))
    return allowed


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
    # No numeric parsing, no tolerance: an amount is only valid if it is
    # one of the exact strings build_evidence_packet handed to the model.
    allowed_amounts = collect_allowed_amount_strings(packet)
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

    for span in sorted(set(m.strip() for m in MONEY_SPAN_RE.findall(text))):
        checked += 1
        if _normalize_money_text(span) in allowed_amounts:
            passed += 1
        else:
            failures.append(
                f"Amount \"{span}\" does not appear verbatim in the evidence packet "
                f"(it was calculated, re-grouped or invented rather than copied)")

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
        f"{t['timestamp']}: {t['amount']['digits']} from {t['from_account']} to "
        f"{t['to_account']} via {t['channel']} ({t['from_bank']} -> {t['to_bank']})"
        for t in evidence_txns
    ]
    if supporting_count:
        lines.append(f"(plus {supporting_count} background/supporting transaction(s) "
                     f"in the same period, not counted as evidence)")

    core_names = ", ".join(p["name"] for p in packet["people"] if p["role"] == "CORE") or "unnamed parties"

    # Circular cases must never quote total_volume (the hop-sum) as if it
    # were the amount laundered - it counts the same principal once per
    # hop. circular_amount_summary is the one pre-assembled sentence
    # build_evidence_packet already computed from amount_cycled and
    # total_volume - reused here verbatim, never rebuilt, so the template
    # and the AI investigator can never disagree on which figure is which.
    total_volume = packet["total_volume"]
    if packet["is_circular"] and evidence_txns and packet.get("circular_amount_summary"):
        amount_phrase = packet["circular_amount_summary"]
    else:
        amount_phrase = f"{total_volume['words']} moved across {len(evidence_txns)} evidence transactions"

    return {
        "summary": (
            f"Case {packet['case_id']}: {amount_phrase} over {packet['hours_spanned']:.2f} hours, "
            f"flagged by {', '.join(packet['detectors_fired'])}. Involves {core_names}."),
        "what_happened": " | ".join(lines),
        "typology": infer_typology(packet["detectors_fired"]),
        "why_suspicious": (
            f"Deterministically detected by {', '.join(packet['detectors_fired'])} across "
            f"{packet['hours_spanned']:.2f} hours spanning {', '.join(packet['banks_involved'])}. "
            f"{amount_phrase}. No AI narrative analysis was performed for this case - see "
            f"typology above for the structural reason it was flagged."),
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
