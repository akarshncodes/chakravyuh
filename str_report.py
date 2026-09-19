"""
CHAKRAVYUH - STR draft generator (Stage 8, officer hand-off).

Turns one approved case into a printable Suspicious Transaction Report draft:
a self-contained HTML page the officer opens in a browser and prints / saves
as PDF. Everything in it already exists on disk - the case evidence, the
relationship findings, SANJAYA's narrative, VIDURA's review and DRONA's
investigation trail. Nothing is generated here; this file only lays it out.

The layout follows the sections an STR to FIU-IND is built around (reporting
entity, persons and accounts, transactions, grounds of suspicion, action
taken). It is a prototype draft on synthetic data, not the official form.
"""

import html
from datetime import datetime

from agents import format_inr

E = lambda x: html.escape(str(x if x is not None else ""))

CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1c2333; font-size: 11.5px; line-height: 1.45; margin: 0; background: #eef1f7; }
.sheet { max-width: 900px; margin: 18px auto; background: #fff; padding: 26px 30px; box-shadow: 0 2px 14px rgba(0,0,0,.08); }
.tri { height: 5px; background: linear-gradient(90deg,#ff9933 0 33.3%,#fff 33.3% 66.6%,#138808 66.6% 100%); border: 1px solid #d9e0f0; }
.head { display: flex; justify-content: space-between; align-items: flex-start; padding: 14px 0 10px; border-bottom: 2px solid #172a74; }
.head h1 { font-size: 19px; margin: 0; color: #172a74; letter-spacing: .3px; }
.head .sub { color: #3b4763; font-size: 11px; margin-top: 3px; }
.head .ref { text-align: right; font-size: 11px; color: #3b4763; }
.head .ref b { color: #172a74; font-size: 13px; }
.stamp { display: inline-block; border: 2px solid; border-radius: 6px; padding: 3px 10px; font-weight: 700; margin-top: 6px; letter-spacing: .5px; }
h2 { font-size: 12.5px; color: #fff; background: #172a74; padding: 5px 9px; margin: 18px 0 8px; letter-spacing: .4px; }
table { width: 100%; border-collapse: collapse; margin: 4px 0; }
th, td { border: 1px solid #d9e0f0; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f2f5fc; color: #172a74; font-weight: 600; }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.kv td:first-child { width: 28%; background: #f7f9fe; font-weight: 600; color: #2a3552; }
.box { border: 1px solid #d9e0f0; border-left: 4px solid #172a74; background: #f7f9fe; padding: 8px 10px; margin: 6px 0; }
.box.red { border-left-color: #c0392b; } .box.green { border-left-color: #138808; }
.muted { color: #6b7589; } .small { font-size: 10.5px; }
.sig { display: flex; gap: 30px; margin-top: 26px; }
.sig div { flex: 1; border-top: 1px solid #1c2333; padding-top: 4px; font-size: 10.5px; color: #3b4763; }
.foot { margin-top: 18px; padding-top: 8px; border-top: 1px solid #d9e0f0; font-size: 9.5px; color: #6b7589; }
.printbar { max-width: 900px; margin: 12px auto 0; text-align: right; }
.printbar button { background: #172a74; color: #fff; border: 0; padding: 8px 16px; border-radius: 6px; font-size: 13px; cursor: pointer; }
@media print { body { background: #fff; } .sheet { box-shadow: none; margin: 0; padding: 0; max-width: none; } .printbar { display: none; }
               h2 { -webkit-print-color-adjust: exact; print-color-adjust: exact; } tr, .box { page-break-inside: avoid; } }
"""


def build_str_html(case, written, rel, drona, txns, entities, officer=None):
    """case: cases.json entry. written: cases_written.json entry (or None).
    rel: relationships.json case entry (or None). drona: investigation_log item (or None).
    txns: list of evidence transaction dicts. entities: entity_key -> dict (name, flags).
    officer: {"decision", "note", "time"} from the dashboard, or None."""
    cid = case["case_id"]
    n = (written or {}).get("narrative", {}) or {}
    v = (written or {}).get("verification", {}) or {}
    fc = (written or {}).get("fact_check", {"checked": 0, "passed": 0}) or {}
    conf = (written or {}).get("final_confidence", "")
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    approved = bool(officer and officer.get("decision") == "Approved")
    stamp_col = "#138808" if approved else "#d68910"
    stamp = "APPROVED BY OFFICER" if approved else "DRAFT · AWAITING OFFICER"
    total = format_inr(case["total_evidence_amount"])
    value = f"{total['digits']} ({total['words']}) across {len(case['evidence_txn_ids'])} transfers"
    if "CIRCLE" in case["detectors_fired"] and txns:
        # a loop moves one principal round every hop; the hop-sum overstates it
        pr = format_inr(max(t["amount"] for t in txns))
        value = (f"{pr['digits']} ({pr['words']}) principal cycled round the loop · "
                 f"{total['words']} across all {len(case['evidence_txn_ids'])} hops")

    rows = []
    for t in sorted(txns, key=lambda t: t["timestamp"]):
        a = format_inr(t["amount"])
        rows.append(f"<tr><td>{E(t['txn_id'])}</td><td>{E(t['timestamp'])}</td><td>{E(t['from_account'])}"
                    f"<br><span class='muted small'>{E(t.get('from_person', ''))}</span></td><td>{E(t['to_account'])}"
                    f"<br><span class='muted small'>{E(t.get('to_person', ''))}</span></td>"
                    f"<td class='num'>{E(a['digits'])}</td><td>{E(t['channel'])}</td>"
                    f"<td>{E(t['from_bank'].replace('BANK_', ''))} → {E(t['to_bank'].replace('BANK_', ''))}</td></tr>")

    people = []
    for p in case["core_people"]:
        ent = entities.get(p["entity_key"], {})
        ident = "Probable link (flagged)" if ent.get("has_unverified_link") else "Confirmed"
        people.append(f"<tr><td>{E(p['name'])}</td><td>{E(p['entity_key'])}</td><td>{E(', '.join(p.get('accounts', [])))}</td>"
                      f"<td>{'Yes' if p.get('is_watchlisted') else 'No'}</td><td>{ident}</td></tr>")

    rel_html = "".join(f"<div class='box'><b>{E(s['code'])} · {E(s['name'].replace('_', ' ').title())}.</b> {E(s['sentence'])}</div>"
                       for s in (rel or {}).get("signals", [])) or "<p class='muted'>No relationship check above the bank baseline.</p>"

    weak = "".join(f"<li>{E(w)}</li>" for w in v.get("weaknesses", []) or [])
    conf_n = n.get("confidence", {})
    conf_reason = conf_n.get("reason", "") if isinstance(conf_n, dict) else ""

    trail = ""
    if drona:
        steps = "".join(f"<tr><td>{s['n']}</td><td>{E(s['tool'].replace('_', ' '))}</td><td>{E(s['why'])}</td>"
                        f"<td>{E(s['result'])}</td></tr>" for s in drona.get("steps", []))
        d = drona.get("decision", {})
        trail = (f"<h2>PART F · INVESTIGATION TRAIL (DRONA, AI LEAD INVESTIGATOR)</h2>"
                 f"<table><tr><th>#</th><th>Action</th><th>Why</th><th>What it found</th></tr>{steps}</table>"
                 f"<div class='box'><b>DRONA recommends: {E(d.get('decision', '').replace('_', ' '))}.</b> {E(d.get('reason', ''))}"
                 f"<br><span class='small muted'>Cites: {E(', '.join(d.get('evidence_ids', [])))}</span></div>")

    officer_rows = ""
    if officer:
        officer_rows = (f"<tr><td>Officer decision</td><td><b>{E(officer.get('decision'))}</b> at {E(officer.get('time'))}"
                        f"{(' · note: ' + E(officer.get('note'))) if officer.get('note') else ''}</td></tr>")

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>STR draft {E(cid)}</title><style>{CSS}</style></head>
<body><div class="printbar"><button onclick="window.print()">Print / Save as PDF</button></div><div class="sheet">
<div class="tri"></div>
<div class="head"><div><h1>SUSPICIOUS TRANSACTION REPORT</h1>
<div class="sub">Draft prepared for the Principal Officer · for filing with the Financial Intelligence Unit – India (FIU-IND)</div>
<div class="sub">Generated by CHAKRAVYUH · prototype on synthetic data</div></div>
<div class="ref">Report reference<br><b>CHK/STR/2026/{E(cid)}</b><br>Prepared {E(now)}<br>
<span class="stamp" style="color:{stamp_col};border-color:{stamp_col}">{stamp}</span></div></div>

<h2>PART A · REPORT SUMMARY</h2>
<table class="kv">
<tr><td>Case</td><td>{E(cid)} · detected by {E(' + '.join(case['detectors_fired']))} (deterministic graph detection)</td></tr>
<tr><td>Suspected typology</td><td>{E(str(n.get('typology', ''))[:1].upper() + str(n.get('typology', ''))[1:])}</td></tr>
<tr><td>Period of activity</td><td>{E(case['first_timestamp'])} to {E(case['last_timestamp'])} ({case['hours_spanned']:.1f} hours)</td></tr>
<tr><td>Value of evidence transfers</td><td>{E(value)}</td></tr>
<tr><td>Banks involved</td><td>{E(', '.join(b.replace('_', ' ').title() for b in case['banks_involved']))}{' · crosses both banks' if case.get('crosses_banks') else ''}</td></tr>
<tr><td>Recommended action</td><td><b>{E(n.get('recommended_action', ''))}</b> · confidence {E(conf)}{(' · ' + E(conf_reason)) if conf_reason else ''}</td></tr>
{officer_rows}
</table>
<div class="box">{E(n.get('summary', ''))}</div>

<h2>PART B · PERSONS AND ACCOUNTS</h2>
<table><tr><th>Name</th><th>Resolved ID</th><th>Accounts</th><th>Watchlisted</th><th>Identity</th></tr>{''.join(people)}</table>
<p class="small muted">Identity: records from three source systems were merged into one person only on confirmed evidence
(unique ID, or two independent fields). A probable link is flagged and lowers the report's confidence.</p>

<h2>PART C · TRANSACTION DETAILS (EVIDENCE)</h2>
<table><tr><th>Txn ID</th><th>Date &amp; time</th><th>From</th><th>To</th><th>Amount</th><th>Channel</th><th>Bank</th></tr>{''.join(rows)}</table>

<h2>PART D · GROUNDS OF SUSPICION</h2>
<div class="box"><b>What happened.</b> {E(n.get('what_happened', ''))}</div>
<div class="box red"><b>Why it is suspicious.</b> {E(n.get('why_suspicious', ''))}</div>
<p><b>Unusual account relationships</b> <span class="muted small">(measured against the whole bank)</span></p>
{rel_html}

<h2>PART E · VERIFICATION BEFORE FILING</h2>
<table class="kv">
<tr><td>Automated fact-check</td><td>{fc.get('passed', 0)} of {fc.get('checked', 0)} accounts, transactions, amounts and dates in this report were matched against raw bank data by code</td></tr>
<tr><td>Independent review (VIDURA)</td><td><b>{E(v.get('verdict', 'NOT_VERIFIED'))}</b> · {E(v.get('confidence', ''))}</td></tr>
<tr><td>Innocent explanation tested</td><td>{E(v.get('innocent_explanation', ''))}</td></tr>
</table>
{('<p><b>Points a reviewer may challenge</b></p><ul>' + weak + '</ul>') if weak else ''}
{trail}

<div class="sig"><div>Prepared by: CHAKRAVYUH (DRONA · SANJAYA · VIDURA)</div>
<div>Reviewed and approved by: ____________________<br>Principal Officer, name &amp; signature</div>
<div>Date of filing: ______________</div></div>
<div class="foot">This draft was assembled from deterministic detection results and AI-written text that passed an automated
fact-check and an independent AI review. Nothing is filed automatically; filing is the Principal Officer's decision.
Prototype built for IGNITRRON'26 (Team Tech Coders, T-300) on synthetic data. Not an official FIU-IND form.</div>
</div></body></html>"""
