# CHAKRAVYUH · चक्रव्यूह

**AI-Powered Anti-Money-Laundering Investigation System**

IGNITRRON'26 · Project J.A.R.V.I.S. · Team Tech Coders (7-300) · Problem Statement **FC-02** · Domain: FinTech & Cyber

**Live demo:** https://chakravyuh-bnkiuzjcv44pm79vn7jaxr.streamlit.app/

> Existing systems score transactions. We score **networks** — and instead of an alert, we hand the analyst a finished, evidence-backed investigation case.

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

## 2. The solution

| Pillar | What it attacks |
| --- | --- |
| **Precision** | The 85–95% false-positive problem |
| **Case, not alert** | The blank page — the analyst receives a written, evidence-linked case |
| **Consortium without exposure** | Cross-bank rings are found without pooling customer data |

## 3. Features

- **Entity resolution** — merges fragmented identity records from 3 source systems into real people, with contradiction blockers so innocent people are never merged.
- **Four-view transaction graph** — `ALL`, `BANK_A`, `BANK_B`, `CONSORTIUM`; every edge keeps its transaction IDs as receipts.
- **Deterministic detection swarm** — CIRCLE, SPRAY, SPEED, THRESHOLD, plus dormant-reactivation, pass-through and round-amount detectors and a watchlist-signal lane. Graph algorithms only; no model decides what is suspicious.
- **Case builder** — seed → trace → expand → prune turns overlapping detections into one case per network, with one ring of context.
- **AI investigator** — writes a six-field case (summary, what happened, typology, why suspicious, recommended action, confidence) using only verified evidence.
- **Two-layer verifier** — a code-based fact check of every account, transaction, amount and date, then an adversarial AI review against the *reasonable suspicion* standard.
- **Privacy-preserving cross-bank detection** — banks exchange salted hashes only; a ring invisible to each bank alone closes in the consortium view.
- **Analyst dashboard** — Overview, Identity, Network & cross-bank, Detectors, Cases, Scorecard. A human approves before anything is filed.

## 4. Results (current committed run)

| Metric | Value |
| --- | --- |
| Transactions / accounts | 80,000 / 2,500 |
| Accounts resolved to people | 2,500 → 1,828 (true: 1,800) |
| Entity resolution | zero false merges |
| Detector findings → cases | 42 → **11** |
| Hidden rings caught | **11 of 12** (missed `CIRC_5_SUBTLE`, the deliberately hard one) |
| False-positive cases | **0** — every case contains a real ring |
| Cases found without using the watchlist | 11 of 11 |
| Verifier verdicts | 11 / 11 PASS |
| Fact checks (claims verified against raw data) | 215 / 215 passed |
| Final confidence | 6 HIGH, 5 MEDIUM |

## 5. Architecture

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
 6. Investigator agent   LLM writes the case from the evidence packet only
        │
 7. Verifier             Layer 1: code fact-check (accounts, txns, amounts, dates)
        │                Layer 2: adversarial LLM review (PASS / REVISE / REJECT)
        │
 8. Human analyst        reviews in the dashboard ► approves ► STR
```

**Core principle: LLMs are used only where judgement is required, never for detection.** The graph engine finds and proves the structure; the model only turns a verified finding into language. The evidence exists before the model speaks.

## 6. Tech stack

| Layer | Tools |
| --- | --- |
| Language | Python 3 |
| Graph & detection | NetworkX, SciPy |
| Data | pandas, CSV/JSON |
| AI agents | OpenAI API (`gpt-4o-mini`) via `openai`, `python-dotenv` |
| Dashboard | Streamlit, Plotly |
| Deployment | Streamlit Community Cloud |

## 7. Repository layout

| File | Stage |
| --- | --- |
| `generate_data.py` | 1 — synthetic data with 12 hidden rings (standard library only, seed 26192) |
| `entity_resolution.py` | 2 — records → real people |
| `graph_builder.py` | 3 — four graph views, precomputed layouts in `graphs/` |
| `detectors.py` | 4 — detection swarm |
| `case_builder.py` | 5 — case assembly |
| `agents.py` | 6 & 7 — investigator and verifier |
| `app.py` | 8 — Streamlit dashboard |
| `*.csv`, `*.json`, `graphs/` | generated data and outputs, committed so the deployed app needs no compute |
| `docs/` | build plan and mentor deck |

## 8. Setup

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
cp .env.example .env           #    add OPENAI_API_KEY (never commit .env)
python3 agents.py              # 6-7 cases_written.json  (--force to regenerate)
```

Without an API key, `agents.py` writes templated narratives marked `NOT_VERIFIED` instead of failing.

## 9. Usage

1. **Overview** — the scale of the data and the headline results.
2. **Identity** — see one person written three ways across three systems, and how they are resolved.
3. **Network & cross-bank** — switch Bank A → Bank B → Consortium and watch the ₹2.4 crore hero ring close only in the consortium view.
4. **Detectors** — which detector fired, on what, and why.
5. **Cases** — the written case, its evidence transactions, the fact-check and the verifier's reasoning. The analyst approves or rejects.
6. **Scorecard** — accuracy against the hidden ground truth.

## 10. APIs and dependencies

- **OpenAI Chat Completions** (`gpt-4o-mini`) — used only in `agents.py`, offline, before the demo. Output is cached to `cases_written.json`, so the **live app makes no API calls and needs no key**.
- Python packages: see `requirements.txt` (networkx, streamlit, pandas, openai, python-dotenv, scipy, plotly).
- No bank or external data APIs — all data is synthetic.

## 11. Key implementation details

**Synthetic data with ground truth.** No bank releases real transactions, so `generate_data.py` injects 12 rings (circular, mule, velocity, structuring) into 80,000 normal transactions — 0.32% of the total. `ground_truth.csv` is the answer key and is read **only** by scoring functions, never by resolution, detection or anything sent to the LLM.

**Entity resolution, precision first.** Three tiers: 🟢 confirmed (unique ID or two fields agree) is merged; 🟡 probable (name variant + one field) is merged but flagged `has_unverified_link`; ⚪ possible (name only) is never merged. Blockers override every rule — two different PANs are two people; a shared address with different PANs is a family, not one person. Yellow links never chain. A false merge accuses an innocent person, so missing a link is acceptable and inventing one is not.

**Cross-bank without pooling.** Each bank resolves only its own records. Banks share `SHA256(PAN + shared salt)`, bucketed amounts and times, and hashed transaction references — never names, PANs, addresses, balances or account numbers; an assertion fails if any leak. The hero ring's bank pattern (`A,A,B,B,A,B`) leaves one hop invisible to each bank, so neither bank alone can see the loop.

**Numbers never come from the model.** A Python `format_inr()` produces every amount as finished Indian-format strings (lakh/crore). The model copies them verbatim; the fact checker rejects any figure not in the allowed set. During the build this caught the model writing ₹140 crore for ₹14 crore.

**Verifier uses the right legal standard.** An STR reports *reasonable suspicion*, not proof. The verifier must propose the most plausible innocent explanation and test it against specific evidence; it may REJECT only for a factual error, an unsupported narrative, or an innocent explanation the evidence confirms. Confidence is automatically lowered if any person in the case rests on an unverified identity link.

**Demo-safe by design.** All heavy compute and all LLM output are precomputed and committed. The dashboard only reads files, so it runs without network, keys or delay.

**Nothing is filed automatically.** Every case ends with a human decision.

## 12. Limitations

- Data is synthetic by design, so accuracy can be measured against ground truth.
- `CIRC_5_SUBTLE` (small amounts over several days) is not detected; we report 11/12 rather than tune to the answer key.
- The hero ring's 3 real people resolve to 4, because two records share only a name — the resolver correctly refuses to merge on name alone. The loop is still detected.
- Out of scope: authentication, live bank integrations, cryptocurrency.
