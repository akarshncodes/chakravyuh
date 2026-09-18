# CHAKRAVYUH · चक्रव्यूह

**AI-Powered Anti-Money-Laundering Investigation System**

IGNITRRON'26 · Project J.A.R.V.I.S. · Team Tech Coders (7-300) · Problem Statement **FC-02** · Domain: FinTech & Cyber

**Live demo:** https://chakravyuh-bnkiuzjcv44pm79vn7jaxr.streamlit.app/

> Existing systems score transactions. We score **networks** — and instead of an alert, we hand the analyst a finished, evidence-backed investigation case.

**The key challenge in FC-02 is one sentence:** *"Discover meaningful relationships within transaction networks and convert them into an understandable investigation narrative."* We took that sentence as our architecture. Stages 2–5 **discover the relationships** (who is really behind each account, how money moves, how the accounts relate). Stages 6–7 **convert them into a narrative** that is fact-checked before a human reads it.

---

## 1. The problem

Money laundering hides in the *layering* stage: funds move through many accounts so that no single transfer looks wrong. Bank monitoring evaluates **one transaction at a time**, so it is blind to the thing it hunts — the crime is a *shape*.

| | |
| --- | --- |
| Laundered globally each year | 2–5% of global GDP ($800bn–$2tn) — UNODC |
| Intercepted by authorities | under 1% |
| Spent on financial-crime compliance annually | $206 billion — LexisNexis |
| AML alerts that are false positives | 85–95% |
| Alerts that become a filed report | 1–5% |

TD Bank failed to monitor 92% of its transaction volume (~$18.3 trillion) while three networks moved $670 million through it, and was fined $3.09 billion. It did not lack alerts. It could not connect them.

FC-02 asks for a graph-based system that finds **layering, circular transfers, rapid movement of funds and unusual account relationships**, and — rather than a risk score — produces **explainable evidence and an investigation narrative**.

## 2. How we map to FC-02

We went through the problem statement line by line and made sure every ask points to something you can open in the app.

| FC-02 asks for | What we built | Where to see it |
| --- | --- | --- |
| **Layering** | SPEED + SPRAY detectors find multi-hop chains and mule fan-out/fan-in | Detectors tab · cases C005–C007, C009 |
| **Circular transfers** | CIRCLE detector on the resolved graph (loops that return to the origin) | Network tab (hero ring) · C001–C004, C010 |
| **Rapid movement of funds** | SPEED: money leaving within minutes of arriving | Detectors tab · 21 findings |
| **Unusual account relationships** | Relationship Lens — fresh accounts, one person behind many accounts, first-ever contact, shared phone numbers, hops a single bank can't see. Each one measured against the whole bank | Cases tab → "Unusual account relationships" · `relationships.py` |
| **Explainable evidence, not just a risk score** | Every case lists the exact transactions that prove it; the narrative can only cite those; a code fact-checker verifies every ID, amount and date | Cases tab → evidence table, fact-check, verifier |
| **Investigation narrative** (key challenge) | AI investigator writes an STR-style case; an adversarial AI reviewer argues the innocent side first | Cases tab → AI investigator report |

A note on scores: each case does carry a *queue priority*, but that only decides which case an analyst opens first. It is never the output. The output is the evidence and the narrative.

**Relationship Lens, in numbers.** The five checks fire **2.73 times per case** on average (9 of 11 cases trip two or more). We ran the same checks on **220 random groups of ordinary customers**, built the same way a case is — they fire **0.4 times per group**, and only 3.6% trip two or more. So the checks aren't firing on everything; they're picking out something real. The lens only adds evidence to existing cases and never opens a new one, so it can't create a false positive.

## 3. The solution

| Pillar | What it attacks |
| --- | --- |
| **Precision** | The 85–95% false-positive problem |
| **Case, not alert** | The blank page — the analyst receives a written, evidence-linked case and a printable STR draft |
| **Consortium without exposure** | Cross-bank rings are found without pooling customer data |

### Three AI agents, one chain of command

We didn't want AI bolted on at the end, and we didn't want AI doing detection either (a regulator can't audit "the model felt it"). So the AI runs the *investigation*, and code supplies the facts. We named the agents after the Mahabharata, since the chakravyuh itself comes from there:

| Agent | Role | What it actually decides |
| --- | --- | --- |
| 🏹 **DRONA** (gpt-4o) — he designed the chakravyuh | Lead investigator | Triage order of the whole queue · which evidence to pull for each item (7 read-only tools) · when a case is ready to write · whether to send a report back · what to do with weak signals that are *not* cases · a recommendation for the officer |
| 📜 **SANJAYA** (gpt-4o-mini) — narrated the war to a king who couldn't see it | Case writer | Turns the proven evidence plus DRONA's brief into an STR narrative |
| ⚖️ **VIDURA** (gpt-4o-mini) — the truth-teller of the court | Sceptical reviewer | Argues the innocent explanation first, then PASS / REVISE / REJECT |

The guardrails are in code, not in the prompt. DRONA has no tool that can create a finding or a case. Every ID and every rupee amount in his decision is checked against what his tools actually showed him, and anything else is rejected. He has to look at evidence at least twice before deciding, and he can't recommend filing a report VIDURA rejected. The officer makes the final call.

In our run DRONA worked **13 items** (11 cases, 1 watchlist hint, and 1 lead he'd never have seen from the detectors alone — a person accused nowhere whose money reaches two separate rings) using **98 tool calls he chose himself**. VIDURA passed **11 of 11** reports and **293 of 293** facts matched the raw data. Every step is saved to `investigation_log.json` and can be replayed in the War Room tab.

## 4. Features

- **Entity resolution** — merges fragmented identity records from 3 source systems into real people, with contradiction blockers so innocent people are never merged.
- **Four-view transaction graph** — `ALL`, `BANK_A`, `BANK_B`, `CONSORTIUM`; every edge keeps its transaction IDs as receipts.
- **Deterministic detection swarm** — CIRCLE, SPRAY, SPEED, THRESHOLD, plus dormant-reactivation, pass-through and round-amount detectors and a watchlist-signal lane. Graph algorithms only; no model decides what is suspicious.
- **Relationship Lens** — five checks on how the accounts in a case relate to each other, each compared with the bank-wide normal (e.g. 15 of 27 accounts under 30 days old, against 1.7% bank-wide).
- **Case builder** — seed → trace → expand → prune turns overlapping detections into one case per network, with one ring of context.
- **DRONA, AI lead investigator** — triages the queue, chooses its own evidence lookups, briefs the writer, handles reviewer pushback and recommends a decision, with every step logged.
- **AI investigator (SANJAYA)** — writes a six-field case (summary, what happened, typology, why suspicious, recommended action, confidence) using only verified evidence.
- **Two-layer verifier (VIDURA)** — a code-based fact check of every account, transaction, amount and date, then an adversarial AI review against the *reasonable suspicion* standard.
- **Privacy-preserving cross-bank detection** — banks exchange salted hashes only; a ring invisible to each bank alone closes in the consortium view.
- **Analyst dashboard** — War Room (replay DRONA's investigation step by step), Overview, Identity, Network & cross-bank, Detectors, Cases, Scorecard. A human approves before anything is filed.
- **STR draft, ready to file** — when the officer approves a case, one click gives a printable Suspicious Transaction Report (persons, accounts, transactions, grounds of suspicion, unusual relationships, verification, DRONA's investigation trail) laid out around the sections an FIU-IND STR asks for.

## 5. Results (current committed run)

| Metric | Value |
| --- | --- |
| Transactions / accounts | 80,000 / 2,500 |
| Accounts resolved to people | 2,500 → 1,828 (true: 1,800) |
| Entity resolution | zero false merges |
| Detector findings → cases | 42 → **11** |
| Hidden rings caught | **11 of 12** (missed `CIRC_5_SUBTLE`, the deliberately hard one) |
| False-positive cases | **0** — every case contains a real ring |
| Cases found without using the watchlist | 11 of 11 |
| Relationship signals per case vs. random customer groups | 2.73 vs 0.4 |
| DRONA: items investigated / tool calls he chose | 13 / 98 |
| Verifier verdicts (VIDURA) | 11 / 11 PASS |
| Fact checks (claims verified against raw data) | 293 / 293 passed |
| Final confidence | 6 HIGH, 5 MEDIUM |

## 6. Architecture

```
 1. Bank data            transactions + identity records from 3 source systems
        │
 2. Entity resolution    scattered records ──► real people   (watchlist hits noted)
        │
 3. Graph builder        people = nodes, money flows = edges
        │                views: ALL · BANK_A · BANK_B · CONSORTIUM (salted hashes only)
        │
 4. Detection swarm      deterministic graph algorithms — no LLM
        │                CIRCLE · SPRAY · SPEED · THRESHOLD · + 3 more · watchlist lane
        │
 5. Case builder         seed ► trace ► expand ► prune  → one case per network
        │
 5b. Relationship Lens   fresh accounts · hidden control · first contact ·
        │                shared phone · bank blind spot  (vs. bank baseline)
        │
 ┌─ DRONA · AI lead investigator ───────────────────────────────────────┐
 │  triage ► picks evidence tools ► briefs SANJAYA ► reads VIDURA ►      │
 │  sends back or decides ► recommends          (read-only tools only)   │
 │                                                                       │
 │  6. SANJAYA            LLM writes the case from the evidence packet   │
 │         │                                                             │
 │  7. VIDURA             Layer 1: code fact-check (IDs, amounts, dates) │
 │                        Layer 2: adversarial LLM review                │
 └───────────────────────────────────────────────────────────────────────┘
        │
 8. Human officer        War Room + Cases tab ► approves ► printable STR draft
```

**Core principle: LLMs are used only where judgement is required, never for detection.** The graph engine finds and proves the structure; the model only turns a verified finding into language. The evidence exists before the model speaks.

## 7. Tech stack

| Layer | Tools |
| --- | --- |
| Language | Python 3 |
| Graph & detection | NetworkX, SciPy |
| Data | pandas, CSV/JSON |
| AI agents | OpenAI API (`gpt-4o-mini`) via `openai`, `python-dotenv` |
| Dashboard | Streamlit, Plotly |
| Deployment | Streamlit Community Cloud |

## 8. Repository layout

| File | Stage |
| --- | --- |
| `generate_data.py` | 1 — synthetic data with 12 hidden rings (standard library only, seed 26192) |
| `entity_resolution.py` | 2 — records → real people |
| `graph_builder.py` | 3 — four graph views, precomputed layouts in `graphs/` |
| `detectors.py` | 4 — detection swarm |
| `case_builder.py` | 5 — case assembly |
| `relationships.py` | 5b — Relationship Lens (unusual account relationships) |
| `agents.py` | 6 & 7 — SANJAYA (investigator) and VIDURA (verifier) |
| `orchestrator.py` | DRONA — AI lead investigator that runs 6 & 7 |
| `str_report.py` | 8 — printable STR draft for an approved case |
| `app.py` | 8 — Streamlit dashboard |
| `*.csv`, `*.json`, `graphs/` | generated data and outputs, committed so the deployed app needs no compute |
| `docs/` | build plan and mentor deck |

## 9. Setup

```bash
git clone https://github.com/akarshncodes/chakravyuh.git
cd chakravyuh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Run the dashboard** (uses the committed outputs — no API key needed):

```bash
streamlit run app.py
```

**Rebuild the whole pipeline from scratch** (optional):

```bash
python3 generate_data.py       # 1  data
python3 entity_resolution.py   # 2  identities
python3 graph_builder.py       # 3  graphs + layouts
python3 detectors.py           # 4  detections.json
python3 case_builder.py        # 5  cases.json
python3 relationships.py       # 5b relationships.json
cp .env.example .env           #    add OPENAI_API_KEY (never commit .env)
python3 orchestrator.py        # DRONA runs 6-7 → investigation_log.json + cases_written.json
                               # (python3 agents.py --force runs 6-7 without DRONA)
```

Without an API key, `agents.py` writes templated narratives marked `NOT_VERIFIED` instead of failing.

## 10. Usage

1. **War Room** — pick an item and press *Replay investigation* to watch DRONA work it, step by step, with his reasoning.
2. **Overview** — the scale of the data and the headline results.
3. **Identity** — see one person written three ways across three systems, and how they are resolved.
4. **Network & cross-bank** — switch Bank A → Bank B → Consortium and watch the ₹2.4 crore hero ring close only in the consortium view.
5. **Detectors** — which detector fired, on what, and why.
6. **Cases** — the unusual relationships, the written case, its evidence transactions, the fact-check and the verifier's reasoning. The officer approves, and downloads the STR draft.
7. **Scorecard** — accuracy against the hidden ground truth.

## 11. APIs and dependencies

- **OpenAI Chat Completions** — `gpt-4o` for DRONA (with function calling), `gpt-4o-mini` for SANJAYA and VIDURA. Used only in `orchestrator.py` / `agents.py`, offline, before the demo. Output is cached to `investigation_log.json` and `cases_written.json`, so the **live app makes no API calls and needs no key**.
- Python packages: see `requirements.txt` (networkx, streamlit, pandas, openai, python-dotenv, scipy, plotly).
- No bank or external data APIs — all data is synthetic.

## 12. Key implementation details

**Synthetic data with ground truth.** No bank releases real transactions, so `generate_data.py` injects 12 rings (circular, mule, velocity, structuring) into 80,000 normal transactions — 0.32% of the total. `ground_truth.csv` is the answer key and is read **only** by scoring functions, never by resolution, detection or anything sent to the LLM.

**Entity resolution, precision first.** Three tiers: 🟢 confirmed (unique ID or two fields agree) is merged; 🟡 probable (name variant + one field) is merged but flagged `has_unverified_link`; ⚪ possible (name only) is never merged. Blockers override every rule — two different PANs are two people; a shared address with different PANs is a family, not one person. Yellow links never chain. A false merge accuses an innocent person, so missing a link is acceptable and inventing one is not.

**Cross-bank without pooling.** Each bank resolves only its own records. Banks share `SHA256(PAN + shared salt)`, bucketed amounts and times, and hashed transaction references — never names, PANs, addresses, balances or account numbers; an assertion fails if any leak. The hero ring's bank pattern (`A,A,B,B,A,B`) leaves one hop invisible to each bank, so neither bank alone can see the loop.

**Numbers never come from the model.** A Python `format_inr()` produces every amount as finished Indian-format strings (lakh/crore). The model copies them verbatim; the fact checker rejects any figure not in the allowed set. During the build this caught the model writing ₹140 crore for ₹14 crore.

**Verifier uses the right legal standard.** An STR reports *reasonable suspicion*, not proof. The verifier must propose the most plausible innocent explanation and test it against specific evidence; it may REJECT only for a factual error, an unsupported narrative, or an innocent explanation the evidence confirms. Confidence is automatically lowered if any person in the case rests on an unverified identity link.

**The AI commands, the code decides what's true.** DRONA's tools are read-only views over files the deterministic stages already wrote. When he records a decision, code checks every cited ID against that item's evidence and every rupee figure against what his tools returned (detector text is re-expressed in Indian format first, so he can only copy `format_inr` strings). In our first real run DRONA wrote "Rs 24,000,000" — a figure copied from a detector's western-format text — which is exactly why that check exists now.

**Demo-safe by design.** All heavy compute and all LLM output are precomputed and committed. The dashboard only reads files, so it runs without network, keys or delay.

**Nothing is filed automatically.** Every case ends with a human decision.

## 13. Limitations

- Data is synthetic by design, so accuracy can be measured against ground truth.
- `CIRC_5_SUBTLE` (small amounts over several days) is not detected; we report 11/12 rather than tune to the answer key.
- The hero ring's 3 real people resolve to 4, because two records share only a name — the resolver correctly refuses to merge on name alone. The loop is still detected.
- Out of scope: authentication, live bank integrations, cryptocurrency.
