# CHAKRAVYUH — Complete Project Context

**Purpose of this file:** full handover context for any AI assistant (Claude, Claude Code, ChatGPT) picking up this project. It covers what was built, why every decision was made, every bug found and how it was fixed, and the current state. Nothing is omitted.

---

## 1. The event and the constraints

**IGNITRRON'26 · Project J.A.R.V.I.S.** — 24-hour software hackathon at KPR Institute of Engineering and Technology, Coimbatore, 18–19 September 2026.

| | |
| --- | --- |
| Team | Tech Coders |
| Team ID | T-300 |
| Team Leader | Akarsh N (GitHub: akarshncodes) |
| Domain | FinTech & Cyber |
| Problem Statement | **FC-02** — AI-Powered Anti-Money-Laundering Investigation System |
| Repository | https://github.com/akarshncodes/chakravyuh (public) |
| Live deployment | https://chakravyuh-bnkiuzjcv44pm79vn7jaxr.streamlit.app/ |

**Hard rules from the official rulebook:**
- Submission window **06:00–07:00 AM, 19 September**. Everything must be done by then.
- Public GitHub repo with **meaningful commit history** — inspected at a checkpoint (02:30–03:00 AM) and at judging.
- **Live deployment is mandatory.** A broken link loses marks.
- README must cover: problem, solution, features, stack, architecture, setup, usage, APIs/dependencies, key implementation details.
- PPT: **6–8 slides**. Architecture diagram required in README or PPT.
- Final presentation: **5 minutes + 3 minutes Q&A**, and **all team members must be present and presenting**.
- AI tools fully allowed, no cap, no disclosure required. But the team must be able to defend the submission.
- Shortlisting takes ~40–45 teams; final judging after that.

**Important context about the builder:** Akarsh has no formal coding background and builds entirely through AI tools. All technical work is delivered as prompts to paste into Claude Code. This is why every stage is specified precisely and why verification is done independently rather than trusting build reports.

---

## 2. The problem statement (FC-02, verbatim intent)

Build a graph-based financial intelligence system that identifies suspicious transaction structures and generates an investigation case. It should identify patterns such as **layering, circular transfers, rapid movement of funds, and unusual account relationships**.

> **The stated key challenge:** "Discover meaningful relationships within transaction networks and convert them into an understandable investigation narrative."

And explicitly: *"Rather than producing only a risk score, the system should generate explainable evidence showing why a transaction network was considered suspicious."*

**This sentence drove the entire design.** The problem statement is rejecting two things every team would build: a risk score (a black box, useless to an analyst and indefensible to a regulator) and a classifier (pointless, because the transaction was never the unit of crime).

---

## 3. Why this problem statement was chosen

All 25 problem statements across five domains were scored on novelty, hardness, impact, and buildability-by-AI-in-24h. FC-02 was the only one scoring high on all four.

Rejected as traps:
- **FC-01** (privacy-preserving data exchange with zero-knowledge proofs) — highest novelty and hardness of all 25, but requires real cryptography. Unbuildable without deep expertise; a fake would collapse under one question.
- **SI-03** (vision-based defect detection) — needs a labelled defect-image dataset that does not exist.
- **SI-04, SI-01, HE-01** — genuine constraint-solver/optimization problems.
- **FC-05** (fraud detection) — lowest novelty on the sheet; everyone builds fraud detection.
- **AI-01 / FC-04** (incident and SOC correlation) — near-duplicates of each other and the most obvious "safe agentic" picks, so the most crowded.

---

## 4. The domain research that informs the pitch

### The scale of the problem

| Figure | Value | Source |
| --- | --- | --- |
| Laundered globally per year | 2–5% of global GDP ($800bn–$2tn) | UNODC |
| Illicit funds through the financial system, 2025 | $4.4 trillion | KYC Hub |
| Tied to drug trafficking | $1.1 trillion | |
| Tied to human trafficking | $528.5 billion | |
| Share authorities actually intercept | **under 1%** | |
| Annual financial-crime compliance cost | **$206 billion** | LexisNexis |
| Global AML/KYC fines, 2025 | $3.8 billion | |

### Why current systems fail

| Metric | Value |
| --- | --- |
| AML alerts that are false positives | **85–95%** |
| Alerts that become a filed report | **1–5%** |
| Analyst time on alerts leading nowhere | up to **90%** |
| Alerts per day at a large institution | 10,000+ |
| Investigation time per alert | 20–60 minutes |

Rule-based monitoring evaluates **one transaction at a time**. Criminals know the rules and engineer around them — structuring below thresholds, round-tripping, shell layering, rapid cross-border movement through "3–5 accounts in 3–5 countries in a matter of hours". The crime is a *shape*, and the tools are blind to shapes.

### The case studies that anchor the pitch

**TD Bank (exposed October 2024)** — the best evidence available:
- Failed to monitor **92% of transaction volume** from January 2018 to April 2024 — approximately **$18.3 trillion** unmonitored.
- Monitoring program **effectively static from 2014 to 2022**.
- Three networks moved over **$670 million** through the bank: $470m through nominee accounts, ~$120m through a "jewelry business" using shell accounts, ~$39m deposited in the US and withdrawn from Colombian ATMs with five TD employees issuing the cards.
- One network bribed staff with **$57,000 in gift cards**.
- Penalty: **$3.09 billion**, the largest Bank Secrecy Act fine ever, plus a cap on US assets.
- **The lesson: TD did not lack alerts. It could not connect them.**

**Danske Bank (Estonia)** — a small branch pushed a reported ~€200 billion of suspicious flows 2007–2015. Fined roughly €1.8bn.

**TMNL — Transaction Monitoring Netherlands (the most important case for our novelty):**
- Five Dutch banks (ABN AMRO, ING, Rabobank, Triodos, de Volksbank) pooled transaction data into a shared platform in 2020, 70+ staff.
- **It worked** — surfaced criminal networks invisible to any single bank, including cocaine trafficking. Praised by FATF.
- **Shut down January 2025.** A human-rights group petitioned on behalf of 15,000 customers on GDPR grounds; the Dutch DPA and Council of State questioned its legal basis; the EU's new AMLR restricted pooling to already-identified high-risk customers.
- **The lesson: the only approach that demonstrably solved cross-bank layering was made illegal because it required centralising innocent people's data.**

**India, ongoing:**
- Banks have frozen around **8.5 lakh mule accounts** across ~700 branches (up from ~4.5 lakh earlier).
- Fraud networks shifting from Jamtara (Jharkhand) and Nuh (Haryana) to Katni and Shajapur (MP), Kalaburagi (Karnataka), districts in Assam.
- RBI's own AI tool **MuleHunter.AI** (built by RBI Innovation Hub) is live across ~31 banks, flagging roughly **20,000 suspicious accounts a month**.
- **The human cost:** blunt freezing also locks students, gig workers and small traders out of their own money for weeks. False positives have real victims in India right now.

### The competitive landscape (the gap we occupy)

| Tier | Players | Strength | Fatal weakness |
| --- | --- | --- | --- |
| Rule engines | Oracle FCCM/Mantas, NICE Actimize, SAS, Verafin | Regulator-defensible, auditable, scales | One transaction at a time; 85–95% false positives; static |
| ML scoring | Feedzai, Featurespace, ThetaRay, Hawk AI, Unit21, Tookitaki | 30–60% FP reduction; adaptive | Label scarcity (IBM AML dataset is 0.1% illicit of 5.08m edges; Elliptic 2% of 234,355); black box; entity-level not network-level; catastrophic forgetting (reported up to 0.98) |
| Graph intelligence | Quantexa, Palantir, Linkurious, Sayari | Correct unit of analysis; entity resolution is the real moat | Multi-crore, multi-year deployments; exploration tools, not conclusion tools; still no narrative |
| GenAI copilots | Lucinity, Silent Eight, ComplyAdvantage | Target analyst time; produce narrative | Sit downstream of a broken detector — an eloquent false positive is worse than a silent one; hallucination risk in a legal filing |
| Crypto analytics | Chainalysis, Elliptic, TRM Labs | Complete public ledger | Irrelevant to fiat rupee flows |
| Collective | TMNL 💀, COSMIC (SG), RBI MuleHunter | Only approach that solved cross-bank | TMNL illegal; MuleHunter classifies accounts, not networks, and produces no case file |

**The gap, in one sentence:** *network-level detection that outputs a regulator-ready, evidence-linked investigation case, at a price and complexity a co-operative bank or fintech can actually deploy.*

**No tier produces a filed-ready case.** Every one stops at "here is something suspicious" and hands a human the hard part.

---

## 5. The solution: CHAKRAVYUH

Named after the circular formation from the Mahabharata — easy to enter, impossible to escape. Laundering rings are literally circles of transactions.

**One-line pitch:**
> Existing systems score transactions. We score networks — and instead of an alert, we hand the analyst a finished, evidence-backed investigation case.

**Three pillars:**

| Pillar | Attacks |
| --- | --- |
| Precision | The 95% false-positive problem |
| Case, not alert | The blank-page problem — analysts get a network, not homework |
| Consortium without exposure | The TMNL problem — cross-bank detection without pooling data |

---

## 6. Architecture — the eight stages

```
1. Bank data              transactions + records from 3 identity systems
        |
2. Entity resolution      scattered records -> real people
        |                 (watchlist matches noted here)
3. Graph builder          people = nodes, transfers = edges
        |                 built per VIEW: ALL / BANK_A / BANK_B / CONSORTIUM
4. Detection swarm        4 deterministic agents, graph algorithms only
        |
5. Case builder           seed -> trace -> expand -> prune
        |                 two lanes: discovery + watchlist, merged if overlapping
6. Investigator agent     LLM - writes the case from verified evidence
        |
7. Verifier agent         deterministic fact check + adversarial LLM review
        |
8. Human analyst          approves -> STR filed
```

### The single most important design principle

**LLMs are used only where judgement is required, never for detection.**

Detection must be deterministic, reproducible and auditable — a regulator cannot accept "the model felt it was suspicious." The graph engine finds the structure and proves it; the LLM only translates a verified finding into language.

**This is the answer to "isn't this just an LLM wrapper?"** — the LLM does no detection. The evidence exists before the model speaks.

Practical reasoning behind it: an LLM scanning 80,000 transactions for cycles would take minutes-to-hours, cost thousands of calls, be unreliable, non-reproducible and indefensible. A graph algorithm does it in milliseconds, exactly, every time.

### Stage-by-stage detail

**Stage 1 — Synthetic data (`generate_data.py`)**
Standard library only, no dependencies. Fixed random seed **26192** so every run is identical and the demo is reproducible.

No bank releases real transaction data and no public dataset exists, so rings are injected at known positions. This gives **ground truth**, which production AML systems lack — they train on filed reports, which are analyst opinions rather than convictions. *(This is a strength to state in the pitch, not a weakness to hide.)*

**Stage 2 — Entity resolution (`entity_resolution.py`)**
Merges fragmented identity records into real people. Runs before the graph because otherwise the graph is wrong: six accounts that look like six strangers may be three people, and a circle is invisible when its nodes are fragmented.

Three-tier matching:
- 🟢 **Confirmed (green)** — unique identifier match, or two independent fields agree. Treated as fact.
- 🟡 **Probable (yellow)** — good evidence, one field. Merged, but permanently marked `has_unverified_link`.
- ⚪ **Possible** — name similarity only. **Not merged**, surfaced as a suggestion.

Matching rules:
| # | Rule | Tier |
| --- | --- | --- |
| R0 | Same non-blank linked_account | 🟢 |
| R1 | Same non-blank PAN | 🟢 |
| R2 | Same phone + name similarity ≥ 0.85 | 🟢 |
| R3 | Same address + name similarity ≥ 0.85 + no phone conflict | 🟢 |
| R4 | Same phone + same address | 🟢 |
| R5 | Initial expansion ("K. Pillai" = "Karthik Pillai") | 🟡 |
| R6 | Reversed order ("Pillai Karthik") | 🟡 |
| R7 | Suffix stripping ("Mary Bose & Sons") | 🟡 |
| R8 | Soundex surname + similarity ≥ 0.75 ("Deasi"/"Desai") | 🟡 |

Rules 5–8 require at least one other field to agree.

**Contradiction blockers — override every matching rule:**
| Blocker | Reason |
| --- | --- |
| B1: different non-blank PANs | Conclusive — two PANs means two people. Enforced as an invariant: an entity may hold at most one distinct non-blank PAN |
| B2: name-similarity only, with different phone AND different address | Two strangers sharing a name |
| B3: same address, different PAN | **Family members, not one person.** This is exactly how innocent people get caught in real systems |

**Chain safety:** green links chain freely (A–B and B–C means A, B, C are one person). **Yellow links never chain** — pass 2 runs exactly once and a yellow link may never act as a bridge for a further merge. Two weak guesses must not stack into a confident wrong answer.

**Precision is the priority, absolutely.** A false merge accuses an innocent person. Missing a link is acceptable; inventing one is not.

**Stage 3 — Graph builder (`graph_builder.py`)**
NetworkX directed multigraph. Nodes are resolved people. Edges are aggregated money flows carrying txn_count, total/min/max amount, first/last timestamp, channels, `crosses_banks`, and **the full list of txn_ids — every edge keeps its receipts**, so the investigator can cite exact transactions.

Self-transfers (both accounts owned by the same person) are **kept and marked** `is_self_transfer=True` — shuffling money between your own accounts is a real laundering behaviour and dropping it loses signal.

**The four views:**
| View | Sees |
| --- | --- |
| `ALL` | Everything, fully resolved. God's-eye view, used for scoring only |
| `BANK_A` / `BANK_B` | Only transactions touching that bank. **Counterparties at the other bank become opaque `EXT_<account_id>` nodes** with no entity resolution and no ability to merge two external nodes — the bank has no idea two external accounts are the same person |
| `CONSORTIUM` | Both banks, linked through salted PAN hashes only |

**Layout is computed once and saved to JSON.** Laying out 1,800 nodes is slow and must never happen during a demo.

**Stage 4 — Detection swarm (`detectors.py`)**
Four deterministic detectors, plain graph maths and arithmetic. No model inference, no training, no labels — which removes the single biggest failure mode in published AML systems.

| Detector | Hunts | Why it matters |
| --- | --- | --- |
| CIRCLE | Money that leaves and returns | No honest business sends money in a loop |
| SPRAY | One-to-many or many-to-one | The classic mule pattern |
| SPEED | Money leaving within minutes of arriving | Real money rests for days; dirty money runs |
| THRESHOLD | Transfers sitting just under reporting limits | Nobody accidentally sends ₹9.8 lakh eleven times |

Four rather than one because a single signal is weak. A circle might be innocent; a circle *plus* speed *plus* threshold-hugging is not.

**Stage 5 — Case builder (`case_builder.py`)**
Four steps: **seed** on each flagged person → **trace** money in and out → **expand** to whoever they touch → **prune** every innocent account, so the case contains only the guilty network **plus one ring of context** (kept because an analyst will always ask where the money entered from and where it went).

Without this you get four separate alerts about one crime. This is the stage that turns noise into a case.

**Two lanes arrive here:**
| Lane | Holds | Starts from |
| --- | --- | --- |
| Discovery | Rings found with nobody known in them | A pattern in the data |
| Watchlist | Known high-risk entities on a **lower threshold** | A name already known |

**Why the watchlist lane is a lower threshold, not just a label:** a criminal we already know about may move money in a shape that looks completely innocent — one clean transfer to a new account, nothing for a detector to catch. Known people are therefore judged on weaker signals too: a counterparty never seen before, money into a freshly opened account, any break from normal pattern. The industry term is **risk-based monitoring**, and enhanced due diligence on high-risk customers is what FATF and the RBI's KYC directions actually require.

If a discovery case and a watchlist case share accounts, they are **merged into one case** rather than reported as two crimes.

**Stage 6 — Investigator agent (`agents.py`)**
The first use of AI. Receives one confirmed case and writes six fields: `summary`, `what_happened`, `typology`, `why_suspicious`, `recommended_action` (FILE_STR / ESCALATE / MONITOR / CLOSE), `confidence`.

It may only cite transactions present in the case. It is a **translator, not a detective** — detection already happened in Stage 4.

**Stage 7 — Verifier, in two layers**

*Layer 1 — deterministic fact check (plain code, no AI).* Extracts every `ACC\d+`, `TXN\d+`, `PERSON\d+`, rupee amount and date from the narrative and verifies each against the case data. On failure it regenerates once; a second failure is an automatic REJECT. **This catches invented facts with total certainty — no model opinion involved.**

*Layer 2 — adversarial AI review.* A second call with a sceptical system prompt: propose the most plausible innocent explanation, then state whether the evidence rules it out.

**Critical: the legal standard is REASONABLE SUSPICION, not proof.** An STR is a report of suspicion, not a conviction. No compliance officer has proof of intent when they file. Verdicts:
- **PASS** — genuinely anomalous, narrative supported, no innocent explanation consistent with the evidence.
- **REVISE** — warrants reporting but the narrative reasons poorly.
- **REJECT** — reserved for a factual error, a narrative unsupported by its own evidence, or an innocent explanation the evidence positively *confirms*. **Never reject merely because intent is unproven.**

Confidence is downgraded one level automatically if any person in the case carries `has_unverified_link`, with a note explaining why. This connects Stage 2's uncertainty all the way through to the human.

**Everything is cached to `cases_written.json`.** The dashboard reads the cache, so the demo makes **no API call at presentation time** — no network dependency, no lag, no failure on venue wifi. The deployed app therefore needs no API key at all.

**Fallback:** with no API key, a templated narrative is written from case data and `verdict = NOT_VERIFIED`. The system never crashes.

**Stage 8 — Dashboard (`app.py`)**
Streamlit. Government-portal styling (navy, Devanagari चक्रव्यूह wordmark). Tabs: Overview, Identity, Network & cross-bank, Detectors, Cases, Scorecard. Loads only precomputed JSON/CSV — no heavy compute at runtime, which is why it deploys and demos reliably.

**Nothing is ever filed automatically. A human approves.**

---

## 7. The cross-bank feature (the main novelty)

Built into Stage 3 rather than added at the end, because features built at 4am get cut at 5am.

**What crosses between banks:**
- A salted hash of the PAN — `SHA256(PAN + SHARED_SALT)`. The same person at two banks produces the same hash, which neither bank can reverse.
- Edge stubs: direction, bucketed amount band, bucketed timestamp, hashed counterparty.
- `evidence_refs` = `SHA256(txn_id + SHARED_SALT)` so each bank can resolve its own references locally and findings remain verifiable.

**What never leaves a bank:** names, cleartext PANs, addresses, balances, KYC, account numbers. An assertion in the code fails loudly if any of these leak into the consortium graph.

**The demo:**
1. Bank A's view — clean, no ring visible.
2. Bank B's view — clean, no ring visible.
3. Consortium layer on — the ring closes. ₹2.4 crore going round in a circle.
4. *"Neither bank could see this. Neither saw the other's customers. Pooling the data would be illegal — the Dutch banks tried it and were shut down in January. We pooled nothing."*

**Prepared answer:** *"Doesn't your entity resolution already merge across banks — isn't that the pooling you claim to avoid?"* → No. Each bank resolves only its own records. The cross-bank link is made through salted hashes after resolution, never by sharing records. That is why the hash is of the PAN rather than the name — it works without either side learning anything.

---

## 8. The dataset

Generated by `generate_data.py`, seed 26192.

| File | Rows | Contents |
| --- | --- | --- |
| `transactions.csv` | 80,000 | 30 days, two banks, UPI/IMPS/NEFT/RTGS/CASH |
| `accounts.csv` | 2,500 | type, bank, KYC level, account age, owner |
| `customer_records.csv` | ~3,737 | identity records across 3 source systems, ~25% of fields blank |
| `ground_truth.csv` | 258 | the ring transactions — **answer key, never read by resolution, graph or detection logic** |

**2,500 accounts resolve to ~1,828 real people** (true count 1,800). Ring transactions are **0.32%** of the total — realistically rare, so detection means something.

**Twelve hidden rings:**

| Ring | Type | Shape |
| --- | --- | --- |
| CIRC_6_HERO | Circular | **₹2.4 crore through 6 accounts in ~3 hours, crossing both banks, returning to origin.** The demo centrepiece |
| CIRC_4 / CIRC_5_SUBTLE / CIRC_8 | Circular | 4, 5, 8 accounts; the subtle one uses smaller amounts over several days |
| MULE_12 / MULE_25 / MULE_40 | Mule network | source → N mules → collector, within minutes |
| VELOCITY_4 / _5 / _7 | Velocity chain | 4, 5, 7 accounts in under 90 minutes |
| STRUCTURING_10L / _50K | Structuring | repeated deposits just under ₹10,00,000 and ₹50,000 |

Mixed difficulty is deliberate: if every ring were obvious, finding them all would prove nothing.

**Why identity resolution is genuinely hard here** — the same person across systems:
```
[CORPORATE_BANKING] ANNA DESAI    ph=7705029423  pan=FNZVH4843G  acct=ACC00003
[RETAIL_CBS       ] Anna Deasi    ph=7705029423  pan=FNZVH4843G  acct=ACC00004
[CORPORATE_BANKING] Anna Desai    ph=-           pan=FNZVH4843G  acct=ACC00003
[WATCHLIST        ] Anna Deasi    ph=7705029423  pan=FNZVH4843G  acct=ACC00003
```
Three spellings including a typo, a missing phone, two accounts — one person.

---

## 9. Build history — every bug found and fixed

This section matters most for a new assistant. Each of these was caught by independent verification, not by trusting the build report.

### Bug 1 — 274 accounts with no identity record
**Found:** after Stage 2, entity count was 2,113 against a true 1,800. All 12 rings had a split owner.
**Cause:** the generator gave accounts an owner but never wrote a customer record for some of them — 274 of 2,500 (11%), including 24 ring accounts. An account with no identity record cannot be resolved; there is nothing to match on.
**Key insight:** this was a **data bug, not a resolver bug.** The resolver was behaving correctly. The fix was in `generate_data.py`, looping per **account** rather than per owner.
**Result:** 2,113 → 1,841 entities; 5 rings became clean.

### Bug 2 — records with every identifying field blank
**Found:** hero ring still split 3 → 4.
**Cause:** some records had no phone, no PAN and no address — nothing but a name. The resolver correctly refused to merge (name alone could be a different person). No real bank holds a KYC record with zero identifying fields.
**Fix:** guarantee every record has at least one of phone/PAN/address, and every account has at least one record with a **strong** identifier (phone or PAN).
**Result:** 1,841 → 1,828 entities, 6 of 12 rings perfectly resolved.
**Accepted limitation:** the hero ring still resolves 3 true people → 4. This was deliberately accepted — the circle still exists as a 4-node loop, and the honest framing is stronger than a perfect number: *"our resolver refused to merge two records sharing only a name. Zero false merges across 3,700 records."*

### Bug 3 — the cross-bank demo was exactly inverted 🔴
**Found:** independent cycle test across the four views returned:
```
ALL -> cycle found | BANK_A -> cycle FOUND | BANK_B -> cycle FOUND | CONSORTIUM -> no cycle
```
The precise opposite of what the novelty requires.
**Cause:** the hero ring alternated banks perfectly (A→B→A→B→A→B), so **every hop had one leg at each bank** and both banks saw all six transfers. Nothing was hidden from either.
**Fix:** change the bank pattern to `A,A,B,B,A,B` so at least one hop stays inside each bank:

| Hop | Banks | Bank A | Bank B |
| --- | --- | :--: | :--: |
| 1→2 | A→A | ✅ | ❌ invisible |
| 3→4 | B→B | ❌ invisible | ✅ |

Bank A is missing hop 3→4; Bank B is missing hop 1→2. Neither can close the loop; the consortium can.
**Also fixed:** consortium edges carried no transaction references at all, so nothing downstream could cite evidence. Added hashed `evidence_refs`.
**Verified:** hero ring now has exactly 1 hop invisible to each bank.

### Bug 4 — `.gitignore` blocked the data
**Found:** `.gitignore` contained `*.csv`, so the deployed app would have loaded with no data.
**Fix:** ignore only `scratch_*.csv` and `export_*.csv`; commit the four data files and the graph pickles.

### Bug 5 — no README
Written to cover every item the rulebook requires. Inspected at the checkpoint.

### Bug 6 — Stages 6 and 7 were never built
**Found:** an audit showed `agents.py` did not exist and no OpenAI call appeared anywhere. The system was a very good detector that stopped one step short of the problem statement's stated key challenge.
**Fixed:** built `agents.py` with both agents.

### Bug 7 — the AI never actually ran
**Found:** `cases_written.json` showed `model: "template (no API key)"`, all verdicts `NOT_VERIFIED`, all confidence LOW. The fallback path had executed; the real AI path had never run even once.
**Cause:** no `.env` file.
**Fix:** create `.env` with the key.

### Bug 8 — the model cannot do Indian number formatting 🔴
**Found:** first real AI run produced `Rs 140.95 crore` for a ₹14.09 crore figure (10× too big), `Rs 24,00,000` for ₹2,40,00,000 (10× too small), and mis-grouped digits as `Rs 23,83,70,91.92`.
**The fact checker caught it and rejected the case.** *This is a genuine demonstration that the safety net works and is worth telling judges about.*
**Cause:** `gpt-4o-mini` is simply unreliable on the lakh/crore system. Prompting does not fix it.
**Fix — the correct engineering answer: take numbers away from the model entirely.** A Python `format_inr()` helper produces finished strings (`{"digits": "Rs 2,40,00,000", "words": "Rs 2.4 crore"}`); every amount appears in the evidence packet only as these strings; the model is instructed to copy them verbatim and never calculate, convert, round or re-group. The fact checker verifies every monetary figure appears in the allowed string set exactly. Percentages are pre-computed in Python too.
**Result:** fact checks went from failures to 236/236 passing.

### Bug 9 — the verifier used the wrong legal standard 🔴
**Found:** after the formatting fix, fact checks passed 178/178 but **all 11 cases were REJECT**.
**Cause:** the verifier was demanding **proof of criminal intent** — the standard for a criminal conviction, not for an STR. It also failed to test its own hypothesis, accepting "legitimate supplier settlement cycle" as surviving scrutiny when a supplier settlement does not return 95.4% of the funds to the payer three hours later.
**Fix:** rewrite the verifier prompt around **reasonable suspicion**, require each innocent explanation to be tested against specific evidence, and define the three verdicts explicitly with "never reject merely because intent is unproven."
**Result:** 11/11 PASS, 8 at HIGH confidence.

### Bug 10 — `amount_cycled` meaningless for non-circular cases
Reported "Rs 45.78 lakh total volume, with Rs 88,691.70 cycled" for a mule network. Fixed by including `amount_cycled` only for CIRCLE-detected cases.

### Bug 11 — `amount_cycled` equalled `total_volume`
Summaries read "Rs 14.09 crore was cycled ... generating Rs 14.09 crore in total volume" — the same figure twice. `amount_cycled` must be the **largest single transaction** (the principal that actually moved), with `total_volume` the sum. Fixed with an assert that `amount_cycled < total_volume` for multi-transaction cases.

### Security incident — API key exposure
The OpenAI key was pasted into a terminal command and screenshotted twice, exposing it in a chat transcript. The key must be rotated. **Correct procedure going forward:**
```bash
cd ~/Desktop/CHAKRAVYUH\ AI && read -s -p "Paste key: " K && echo "OPENAI_API_KEY=$K" > .env && unset K
```
`read -s` hides the input entirely. `.env` is gitignored and confirmed untracked.

---

## 10. Current state

**Files:**
```
generate_data.py        Stage 1 - synthetic data, stdlib only
entity_resolution.py    Stage 2 - resolution, precision 1.0
graph_builder.py        Stage 3 - four views, saved layouts
detectors.py            Stage 4 - four detectors, two lanes
case_builder.py         Stage 5 - seed/trace/expand/prune
agents.py               Stages 6 & 7 - investigator + verifier
app.py                  Stage 8 - Streamlit dashboard
README.md               full submission documentation
CLAUDE.md               project context for Claude Code
requirements.txt        networkx, streamlit, pandas, openai, python-dotenv, scipy, plotly
.env                    API key (gitignored, untracked - verified)
.env.example            placeholder
graphs/                 4 gpickles + layouts + stats
docs/BUILD_PLAN.pdf     planning documentation
transactions.csv, accounts.csv, customer_records.csv,
ground_truth.csv, resolved_entities.csv, account_owners.csv,
detections.json, cases.json, cases_written.json
```

**Numbers as of the last verified run:**

| Metric | Value |
| --- | --- |
| Transactions | 80,000 |
| Accounts → real people | 2,500 → 1,828 (true: 1,800) |
| Entity resolution precision (green-only) | **1.0 — zero false merges** |
| Detector findings | 42 |
| Cases | 11 |
| Rings caught | **11 of 12** (missed: `CIRC_5_SUBTLE`, the deliberately hard one) |
| **False positives** | **ZERO** — no case without a real ring in it |
| Verifier verdicts | **11/11 PASS** |
| Fact checks | **236 of 236 passed** |
| Confidence | 8 HIGH, 1 MEDIUM, 2 LOW |
| Model | gpt-4o-mini |

**Commit history** (stage-by-stage, as the checkpoint requires): initial setup → Stage 1 generator → Stage 1 dataset → build plan docs → Stage 2 → Stage 3 → Stage 4 → Stage 4 refinement → Stage 5 → Stage 8 dashboard → dashboard polish ×2 → Stage 5 cross-case links → Stages 6 & 7 → formatting and verifier fixes.

---

## 11. Known issues and what is NOT done

| Issue | Status |
| --- | --- |
| `CIRC_5_SUBTLE` not detected | **Accepted.** 11/12 is an honest number and beats a suspicious 12/12 |
| Hero ring resolves 3 people → 4 | **Accepted.** Circle still visible; framing is a strength |
| All cases tagged WATCHLIST lane, ~1 DISCOVERY | **Open.** A labelling artifact: `detectors.py` marks a finding WATCHLIST if *anyone in it* is watchlisted, and the generator puts a watchlisted principal in every ring. The detectors used full thresholds — it should be labelled by **which mechanism fired**, not who is inside. **Risk: the dashboard implies the system only catches people already known.** |
| Three extra detectors (dormant reactivation, pass-through, round-amount clustering) | **Not built.** Optional. Any new detector must preserve the zero-false-positive record |
| PPT | Owned by a teammate |
| API key rotation | Required — old key exposed |

---

## 12. Rules that must not be broken

1. **Detection is deterministic. LLMs only where judgement is required.**
2. **Precision over recall, always.** Entity resolution precision is 1.0 and must stay there. A false merge accuses an innocent person.
3. **Zero false positives across cases.** This is the strongest single number. Any change must preserve it.
4. `ground_truth.csv`, `true_entity_id` and `owner_entity` may be read **only** inside scoring functions — never by resolution, graph-building, detection, or anything sent to an LLM.
5. **Never commit API keys.** The repo is public.
6. **Do not modify completed stages** without saying so first.
7. **Cache all LLM output to disk.** The demo must run with no network.
8. **Commit after every working stage** with a message naming the stage.
9. **Never let the model format or calculate a number.** Python formats; the model copies.
10. **Three strikes and cut** — if a bug survives three fix attempts, remove the feature rather than breaking working code.

---

## 13. The demo, in order

1. **The mess** — 80,000 transactions, 2,500 accounts. Nothing looks wrong.
2. **The fragments** — the same man written three ways across three systems. *"The bank does not know these are one person."*
3. **Resolve** — accounts collapse into real people. **The circle appears.** It was always there; the bank could not see it was the same people.
4. **Run the detectors** — Circle, Spray, Speed, Threshold light up in about two seconds.
5. **The prune** — the map greys out until only the ring and its context remain.
6. **The reveal** — ₹2.4 crore round a closed loop in ~3 hours, crossing both banks.
7. **Bank A alone: no ring. Bank B alone: no ring. Consortium: the ring.**
8. **The case writes itself** — plain English, accounts, amounts, order, method.
9. **The verifier speaks** — innocent explanation considered and ruled out, facts checked against raw data, PASS.
10. **The human decides** — Approve → STR generated.

**Closing line:** *"Three hundred alerts became eleven cases. And the officer did not have to write a word."*

---

## 14. Prepared answers for Q&A

**"What if the criminal isn't on any watchlist?"**
The detectors sweep the whole graph regardless. The watchlist is a shortcut for extra scrutiny on known risk, not a requirement for detection.

**"Isn't this just an LLM wrapper?"**
The LLM does no detection. Graph analysis finds the structure and proves it; the LLM only turns a verified finding into language. The evidence exists before the model speaks.

**"How do you stop the AI making things up in a legal filing?"**
Two layers. Numbers and references are checked by **code**, not by a model — every account, transaction and amount in the narrative must appear in the case data. Only the *reasoning* is reviewed by a second AI with an opposing instruction. And it has already caught a real error: the model wrote ₹140 crore instead of ₹14 crore during our build, and the fact checker blocked the filing.

**"What if you merge the wrong people?"**
Precision is 1.0 on our test set. Contradiction rules block merges — different PANs can never be the same person, and a shared address with different PANs means family, not one person. Soft links are flagged and reduce case confidence. And nothing reaches a filing without a human. The protection is layered, not a single check.

**"Lower thresholds on known people means harassing anyone wrongly listed."**
The extra scrutiny produces a case for a human, never an automatic freeze. Every case carries a confidence score and its evidence, so a weak one is dismissed in seconds. Every decision is logged, so repeated flagging with nothing found is visible and reviewable — which is more than a rule engine offers today.

**"Your data is fake."**
Synthetic by design, with rings injected at known positions so we can measure accuracy. Real systems train on filed reports, which are analyst opinions rather than convictions. Our ground truth is cleaner than theirs.

**"Doesn't entity resolution across banks mean you're pooling data?"**
No. Each bank resolves only its own records. The cross-bank link is a salted PAN hash exchanged after resolution — never the records themselves.

---

## 15. Remaining schedule

| Time | Task |
| --- | --- |
| 02:30–03:00 | GitHub checkpoint — repo, README and commit history inspected |
| 03:00–05:00 | Walk the live site end to end; record backup demo video on a phone |
| 05:00 | **FREEZE — nothing new after this** |
| 05:00–06:00 | Final deploy, rehearse the 5-minute pitch three times, all four members |
| **06:00–07:00** | **SUBMIT — GitHub link + live link** |
| 09:00–10:00 | Shortlist announced |
| 11:00–12:00 | Final presentations, 5 min + 3 min Q&A, all members present |
