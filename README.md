# CHAKRAVYUH

**AI-Powered Anti-Money-Laundering Investigation System**

IGNITRRON'26 · Project J.A.R.V.I.S. · Team Tech Coders (7-300) · Problem Statement **FC-02** · Domain: Fintech & Cyber

---

## The problem

Money laundering hides in the *layering* stage — moving funds through many accounts so no single transfer looks wrong. Bank monitoring systems evaluate **one transaction at a time**, so they are architecturally blind to the thing they hunt.

The result:

| | |
| --- | --- |
| Laundered globally each year | 2–5% of global GDP ($800bn–$2tn) |
| Intercepted by authorities | under 1% |
| Spent on compliance annually | $206 billion |
| AML alerts that are false positives | 85–95% |
| Alerts that become a filed report | 1–5% |

TD Bank failed to monitor 92% of its transaction volume — $18.3 trillion — while three networks moved $670 million through it. They did not lack alerts. They could not connect them.

## What Chakravyuh does

It scores **networks**, not transactions, and returns a **finished investigation case** instead of an alert.

1. **Detects the structure** — circular transfers, mule fan-out/fan-in, rapid movement, threshold structuring.
2. **Assembles the case** — merges overlapping detections into one network with a full evidence chain.
3. **Writes the report** — an AI investigator produces a filed-ready STR narrative.
4. **Verifies before filing** — a second, adversarial AI re-checks every claim against raw data.
5. **Waits for a human** — nothing is ever filed automatically.

### Cross-bank detection without data pooling

Transaction Monitoring Netherlands pooled five banks' data, worked, and was shut down in January 2025 on GDPR grounds. Chakravyuh exchanges only hashed account identifiers and structural signatures — never names, balances or KYC — so two banks can discover a shared ring without either seeing the other's customers.

## Architecture

```
Fragmented records                transactions + 3 identity source systems
    ↓
Entity resolution        scattered records → real people
    ↓
Graph builder            entities = nodes, transfers = edges
    ↓
Detection swarm          4 deterministic agents, graph algorithms only
    ↓
Context agent            merges hits into one network + evidence
    ↓
Investigator agent       LLM — writes the case from verified evidence
    ↓
Verifier agent           LLM — adversarial check, pass / revise / reject
    ↓
Human analyst            approves → STR
```

**Two entry points into the same graph:**

- **Targeted** — a watchlist hit resolves to a real person, the graph expands around them, the detectors analyse what they find.
- **Discovery** — the detectors sweep the whole graph for rings containing nobody previously known.

Targeted alone would only ever catch criminals already on a list. Discovery is how a new network gets found.

### Why entity resolution comes first

Banks hold the same person's details across retail, corporate and watchlist systems, written differently each time and often incomplete. Until those records are merged, the graph is wrong: six accounts that look like six strangers may be three people, and a laundering circle is invisible because its nodes are fragmented.

In our dataset, **47 ring accounts are controlled by only 19 real people.** The ring is only a ring after resolution.

**Design principle:** LLMs are used only where judgement is required, never for detection. Detection must be deterministic, reproducible and auditable — a regulator cannot accept "the model felt it was suspicious."

## Data

No bank releases real transaction data, so `generate_data.py` produces a realistic Indian retail banking log with four laundering rings injected at known positions. This gives us **ground truth**, which real AML systems lack — they train on filed reports, which are analyst opinions rather than convictions.

```bash
python3 generate_data.py
```

Produces:

| File | Contents |
| --- | --- |
| `transactions.csv` | ~12,300 transactions over 30 days, two banks |
| `accounts.csv` | 347 accounts with type, bank, KYC level, age |
| `customer_records.csv` | 448 identity records across 3 source systems, with name variations and missing fields |
| `ground_truth.csv` | The 100 transactions that belong to a ring (0.81%) |

`customer_records.csv` is deliberately messy — the same person appears as "Karthik Pillai", "KARTHIK PILLAI" and "Pillai Karthik", sometimes with a phone number, sometimes with a PAN, sometimes with neither. `true_entity_id` is ground truth for scoring only and is never fed to the resolver.

Hidden rings:

| Ring | Pattern | Shape |
| --- | --- | --- |
| RING-01 | Circular transfer | ₹2.4 crore looping through 6 accounts in ~4 hours, split across both banks |
| RING-02 | Mule network | 1 source → 25 mules → 1 collector |
| RING-03 | Rapid movement | ₹85 lakh through 5 accounts in under 90 minutes |
| RING-04 | Structuring | 40 cash deposits just under the ₹10,00,000 threshold |

The generator uses a fixed random seed, so every run is identical and the demo is reproducible.

## Status

- [x] Stage 1 — synthetic data with fragmented identity records
- [ ] Stage 2 — entity resolution
- [ ] Stage 3 — graph builder
- [ ] Stage 4 — detection swarm
- [ ] Stage 5 — context agent
- [ ] Stage 6 — investigator agent
- [ ] Stage 7 — verifier agent
- [ ] Dashboard and case view

## Stack

Python · NetworkX · Streamlit · Claude API

Deliberately out of scope: authentication, user accounts, admin panels, live bank integrations, cryptocurrency.
