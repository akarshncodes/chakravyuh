# CHAKRAVYUH — Evidence Pack for the Shortlisting Round

Researched material to harden each of the five scoring criteria. Everything here is sourced and verifiable — judges can check it, which is the point.

**The single biggest find:** the FATF's September 2024 Mutual Evaluation of India officially states that suspicious transaction reporting by **rural banks and non-banking companies is low**, and rates India's supervision and preventive measures only **Moderate**. That is an international regulator confirming, in writing, the exact gap this project targets. Nothing else in this pack is as valuable.

---

# 1 · PROBLEM RELEVANCE & UNDERSTANDING (10)

## 1.1 The global picture

| Figure | Value |
| --- | --- |
| Laundered per year | 2–5% of global GDP — $800bn to $2tn (UNODC) |
| Illicit funds through the financial system, 2025 | $4.4 trillion |
| Of that, drug trafficking | $1.1 trillion |
| Of that, human trafficking | $528.5 billion |
| Intercepted by authorities | **under 1%** |
| Spent on financial-crime compliance each year | **$206 billion** |
| AML alerts that are false positives | 85–95% (legacy systems: **95–98%**) |
| Alerts becoming a filed report | 1–5% |
| Analyst time on alerts leading nowhere | up to 90% |
| **Cost to investigate a single alert** | **$25–$50** |

That last figure is new and useful. It converts the false-positive problem into money: a mid-size bank clearing 10,000 alerts a month at $25–50 each, of which 95% are wrong, is burning roughly **$237,500–$475,000 a month on nothing.**

## 1.2 India's official position — the FATF Mutual Evaluation, September 2024

India was assessed across 11 Immediate Outcomes:

| Immediate Outcome | Rating |
| --- | --- |
| IO.1 Risk, policy, coordination | Substantial |
| IO.2 International cooperation | Substantial |
| **IO.3 Supervision** | **Moderate** |
| **IO.4 Preventive measures** | **Moderate** |
| IO.5 Legal persons | Substantial |
| IO.6 Financial intelligence | Substantial |
| IO.7 ML investigation & prosecution | Moderate |
| IO.8 Confiscation | Substantial |
| IO.9 TF investigation | Moderate |
| IO.10 TF preventive measures | Moderate |
| IO.11 PF sanctions | Substantial |

**The findings that matter for this project, quoted:**

> *"Suspicious transaction reporting by some FI sub-sectors appears low"* — naming **non-banking companies, postal services and rural banks**.

> *"Supervision is less developed... with limited or no capacity to supervise"* certain sectors.

And a striking enforcement gap: **€9.3 billion in asset attachments but only €4.4 million in conviction-based confiscation.**

**Why this is the most valuable paragraph in the pack:** you are no longer *claiming* small and rural institutions under-report. The FATF says so, in an official evaluation of India, published thirteen months ago. Your product targets precisely those institutions.

## 1.3 The legal definition you are matching

Under the PMLA, a suspicious transaction is one that, to a person acting in good faith, gives rise to reasonable suspicion of proceeds of crime, or which:

> *"demonstrates unusual or unjustified complexity"*
> *"appears to have no economic rationale or bona fide purpose"*

**Read your own system's output again.** Chakravyuh's `why_suspicious` field says things like *"a closed loop returning 95.4% of the principal within three hours, with no legitimate economic purpose."* That is not a paraphrase of the statute — it is the statutory test, applied.

**Say this in the video or Q&A:** *"Our narrative field is written against the PMLA's own definition of a suspicious transaction: unusual or unjustified complexity, and no economic rationale or bona fide purpose. That's not our phrasing — it's the statute's."*

## 1.4 India's reporting regime — the numbers to quote

| Report | Trigger | Deadline |
| --- | --- | --- |
| **CTR** | Cash transactions over **₹10 lakh** (single, or connected within a month) | By the 15th of the following month |
| **STR** | Reasonable suspicion of proceeds of crime | **Within 7 working days** of forming suspicion |
| **CWTR** | Cross-border transfers over ₹5 lakh equivalent | By the 15th of the following month |

Penalty for failure: **₹10,000 to ₹1,00,000 per failure**, imposed on the Principal Officer's institution.

**The seven-day clock is your strongest operational argument.** An analyst has seven working days from forming suspicion to file. Investigation at 20–60 minutes per alert, with 95% of alerts worthless, is what makes that clock impossible to meet at volume. Chakravyuh delivers a drafted case in seconds.

**Line to use:** *"An Indian bank has seven working days to file an STR once suspicion is formed. We hand the officer a drafted, evidence-linked case in under a minute."*

## 1.5 The India-specific typologies you are detecting

RBI and FIU-IND guidance names these patterns explicitly:
- **Structuring just below the ₹10 lakh CTR threshold** across multiple deposits
- **Rapid in-and-out pass-through activity** within hours or days
- **Mule-account fan-out over UPI** — sudden inflows split instantly across many small transfers to unrelated recipients
- Trade-based mis-invoicing
- Hawala-style offsetting transfers
- Crypto layering

**Your STRUCTURING_10L ring is calibrated to the real ₹10 lakh CTR threshold, not an invented number.** Say that out loud — it shows the data was designed against Indian regulation rather than generically.

---

# 2 · INNOVATION / NOVELTY (10)

Three claims, each now with external grounding.

## 2.1 Entity resolution before the graph

**The claim:** the ring is invisible until fragmented identities are merged.

**The grounding:** this is the capability Quantexa built a company on, and the reason enterprise graph AML costs crores. Doing it with deterministic, explainable rules — and proving precision 1.0 — at a scale a small bank could run is the novel part, not entity resolution itself.

**Be precise in how you claim it:** *"Entity resolution isn't new. Doing it with rules a regulator can audit, with zero false merges, cheaply enough for a co-operative bank, is."*

## 2.2 Cross-bank detection without data pooling

**The claim:** two banks discover a shared ring without either seeing the other's customers.

**The grounding — and this is the strongest evidence in the project:**
- TMNL (five Dutch banks, launched 2020, 70+ staff) pooled transaction data centrally.
- It **worked** — surfaced criminal networks invisible to any single bank, praised by FATF.
- It was **shut down in January 2025**: a human-rights group petitioned on behalf of 15,000 customers on GDPR grounds, the Dutch DPA and Council of State questioned its legal basis, and the EU's new AMLR restricted pooling to already-identified high-risk customers.

**The framing:** the only approach that demonstrably solved cross-bank layering was made illegal because it required centralising innocent people's data. Chakravyuh exchanges salted PAN hashes and structural signatures only — never names, addresses, balances, KYC or account numbers, enforced by an assertion in the code.

**This is a live, unsolved regulatory problem, and you have a working demonstration of an answer.** That is real novelty, not a feature claim.

## 2.3 Two-layer verification — code checks facts, AI checks reasoning

**The claim:** hallucination in a legal filing is prevented by arithmetic, not by a second opinion.

**The grounding:** the entire GenAI-compliance category (Lucinity, Silent Eight, ComplyAdvantage) generates narratives, and hallucination risk in a regulatory filing is the accepted blocker to adoption. The standard mitigation is "a human reviews it" — which restores the workload the tool was meant to remove.

**Your differentiator, stated precisely:** *"We don't have an AI checking an AI. Every number, account and date is verified by code against the raw transactions before any model reviews anything. Only the reasoning goes to the second model, and it's given an opposing instruction."*

**And you have live proof it works.** During the build, the model wrote ₹140 crore for a ₹14 crore figure. The fact checker caught it, forced a regeneration, and rejected the case when it failed again. Current run: **236 of 236 facts verified.**

## 2.4 The deterministic-detection position

**The grounding:** almost all published AML machine-learning research is trained on the Elliptic (2% illicit of 234,355 edges) or IBM AML (0.1% illicit of 5.08m edges) datasets, and the field's acknowledged blockers are label scarcity, extreme class imbalance, concept drift and catastrophic forgetting — one review reports forgetting scores reaching 0.98. The 2025–2026 literature is still overwhelmingly crypto-based and largely undeployed.

**Your position:** by making detection deterministic, Chakravyuh sidesteps the field's central unsolved problem entirely. No labels, no training, no drift, no forgetting — and every finding reproducible.

**Line for a technical judge:** *"The hardest problem in ML-based AML is that illicit transactions are 0.1 to 2 percent of any dataset and labels are analyst opinions rather than convictions. We don't have that problem, because we don't train anything. The graph either contains a cycle or it doesn't."*

---

# 3 · TECHNICAL APPROACH (10)

## 3.1 Map your detectors onto the official indicators

This is the highest-value addition available to you tonight. RBI's Master Direction on KYC (para 36) names the red flags banks must monitor, and FIU-IND guidance names India-specific typologies. **Your four detectors map onto them directly.**

| Chakravyuh detector | Official indicator it implements |
| --- | --- |
| **CIRCLE** | RBI: *"large and complex transactions with no apparent economic rationale or legitimate purpose"* · PMLA: *"unusual or unjustified complexity"* |
| **SPRAY** | FIU-IND / RBI: mule-account fan-out over UPI — sudden inflows split across many unrelated recipients |
| **SPEED** | RBI: *"high account turnover inconsistent with the balance maintained"* · rapid in-and-out pass-through within hours |
| **THRESHOLD** | Structuring just below the **₹10 lakh CTR threshold** set in the PMLA Rules |

**Add this table to your README.** It converts "we invented four detectors" into "we implemented the regulator's own indicators", which is a completely different claim and is worth marks on both Technical Approach and Practical Applicability.

RBI also directs banks (paras 35, 37, 50) to *"deploy robust software that throws up alerts"* and to apply risk-based segmentation with enhanced monitoring for higher-risk customers. **Your two-lane design — full thresholds for everyone, lower thresholds for known high-risk entities — is that instruction, implemented.**

## 3.2 Name your techniques precisely

Judges score specificity. Use these exact terms:

| Stage | Technique |
| --- | --- |
| 2 | Union-find clustering over typed match rules, with contradiction blockers as hard constraints; Soundex phonetic matching; difflib sequence similarity; tiered confidence with non-transitive weak links |
| 3 | Directed multigraph, edge aggregation with full transaction provenance; per-view construction with opaque external nodes; precomputed spring layout |
| 4 | Cycle detection; in-degree/out-degree fan analysis; inter-arrival dwell-time computation; threshold-proximity distribution analysis |
| 5 | Seed-and-expand subgraph extraction with innocence pruning and one-hop context retention; cross-lane case merging on shared membership |
| 6–7 | Evidence-constrained generation; deterministic claim verification by token extraction and set membership; adversarial secondary review with hypothesis falsification |
| Cross-bank | Salted pseudonymisation (SHA-256 over PAN + shared salt); bucketed edge stubs; hashed evidence references |

## 3.3 The design principle, stated for a technical judge

> "LLMs are used only where judgement is required, never for detection. Detection must be deterministic, reproducible and auditable — a regulator cannot accept 'the model felt it was suspicious.' The graph engine finds the structure and proves it; the language model only translates a verified finding into prose. The evidence exists before the model speaks."

---

# 4 · PROTOTYPE FUNCTIONALITY (10)

## 4.1 The numbers that prove it works

| Metric | Value | Why it scores |
| --- | --- | --- |
| Transactions processed | 80,000 | Realistic scale |
| Accounts → resolved people | 2,500 → 1,828 | Entity resolution measurably works |
| Resolution precision | **1.0** | Zero false merges |
| Detector findings | 42 | Detection runs |
| Cases produced | 11 | Findings become cases |
| Rings caught | **11 of 12** | Honest, verifiable |
| **False positives** | **ZERO** | The strongest single number |
| Facts verified | **236 of 236** | The safety net works |
| Verifier verdicts | 11/11 PASS | End to end complete |

## 4.2 Frame the numbers as a funnel

Don't list them — show the collapse:

> **80,000 transactions → 42 findings → 11 cases → 11 filed reports, zero false alarms.**

One line, and it demonstrates the entire pipeline.

## 4.3 The honest-miss framing

You missed `CIRC_5_SUBTLE` — deliberately the hardest ring, using small amounts over several days.

**State it proactively.** An unprompted admission of a limitation is one of the highest-trust signals available, and it makes "zero false positives" land as measured rather than boastful.

> *"We caught 11 of 12. The one we missed is the one we deliberately made hard. We could have tuned until we hit 12 on our own test set, but a system that claims perfection on data it generated isn't one you should trust. Zero false positives matters more than twelve out of twelve."*

## 4.4 Convert accuracy into money

Using the researched cost-per-alert of **$25–$50**:

> "A legacy system generating 42 findings at a 95% false-positive rate produces roughly 40 wasted investigations — about $1,000 to $2,000 of analyst time, for nothing. We produced 11 cases and zero false alarms, each arriving pre-written."

---

# 5 · PRACTICAL APPLICABILITY / FEASIBILITY (10)

## 5.1 The market, with real numbers

**India's co-operative banking sector, as of 31 March 2025 (RBI/NABARD supervised):**

| Type | Count |
| --- | --- |
| Urban Co-operative Banks | **1,457** |
| State Co-operative Banks | 34 |
| District Central Co-operative Banks | 351 |
| Industrial Co-operative Banks | 1 |
| **Total** | **1,843** |

Maharashtra alone has 458 UCBs, Karnataka 250, Tamil Nadu 128.

Every one of these is a PMLA reporting entity with the same STR obligation as HDFC or SBI — and the same seven-working-day clock.

## 5.2 What AML actually costs them today

| Item | Cost |
| --- | --- |
| Total AML program, mid-size bank ($1–10bn assets) | **$500,000 – $3,000,000+ per year** |
| As a share of non-interest expenses | ~2.9% |
| Transaction monitoring platform alone | $100,000 – $500,000+ per year |
| One-time implementation and integration | $50,000 – $200,000 |
| Personnel share of the AML budget | 50–60% |
| Cost per alert investigated | $25 – $50 |
| Legacy false-positive rate | **95–98%** |

**Now put the two facts together — this is your closing argument:**

> "India has 1,843 co-operative banks. A transaction monitoring platform costs a hundred thousand to half a million dollars a year before anyone is hired to operate it. These banks will never buy one. And the FATF's 2024 evaluation of India found exactly that — suspicious transaction reporting by rural banks and non-banking companies is low, and India's supervision and preventive measures were rated only Moderate.
>
> That gap is not a market opportunity we invented. It's an international regulator's finding. Chakravyuh runs on a laptop, needs no training data, and costs a few rupees per run."

## 5.3 Regulatory fit — the checklist

| Requirement | How Chakravyuh meets it |
| --- | --- |
| RBI Master Direction: *"deploy robust software that throws up alerts"* | Four detectors plus watchlist-lane monitoring |
| RBI: risk-based segmentation, enhanced monitoring for high-risk | The two-lane design — lower thresholds for known high-risk entities |
| PMLA: STR within 7 working days of suspicion | Drafted, evidence-linked case in under a minute |
| PMLA: *"unusual or unjustified complexity"*, *"no economic rationale"* | The exact language of the `why_suspicious` field |
| FIU-IND: STR must be evidence-backed and traceable | Every edge retains its transaction IDs; every claim verified against raw data |
| Human accountability of the Principal Officer | Nothing is filed without human approval |
| Auditability under supervision | Deterministic detection — every finding reproducible and explainable |
| GDPR / AMLR-style data-sharing limits | Consortium exchanges salted hashes only; no customer data crosses |

## 5.4 What deployment would actually require

Judges score realism. Name the gap rather than glossing it:

> "What's missing for production is data integration and scale testing, not a change of approach. A bank would point it at its core banking export and KYC records — the same CSVs we already consume. The detection, the case builder and the verifier are unchanged. The honest engineering work left is connectors, throughput and a supervised tuning period against that bank's own history."

---

# 6 · WHAT TO ACTUALLY DO BEFORE 05:00

Ranked by marks gained per minute spent. Do them in order and stop when you run out of time.

### 🥇 1. Add the regulatory-mapping table to the README (10 minutes)
Paste the detector → official indicator table from §3.1, plus the reporting-obligation table from §1.4. This single addition strengthens Technical Approach, Problem Understanding *and* Practical Applicability simultaneously. **Highest return available.**

### 🥈 2. Add the FATF finding to the README's problem section (5 minutes)
Two sentences with the source link. Turns your market claim from an assertion into a citation.

### 🥉 3. Add a "Regulatory Alignment" section to the README (10 minutes)
The table from §5.3. Nothing else you can write in ten minutes scores on feasibility as hard.

### 4. Add a Sources section to the README (5 minutes)
FATF MER India 2024, FIU-IND FAQs, RBI Master Direction, UNODC, the TD Bank DOJ release. **Cited claims are checkable claims, and judges notice.**

### 5. If the dashboard is easy to edit (15 minutes)
Add one line under each detector on the Detectors tab naming the official indicator it implements. Seeing "implements RBI Master Direction para 36" inside a working product is worth more than the same words in a document.

### ⛔ Do not
Touch the detection code, the resolver or the case builder. You have zero false positives and 11/11 PASS. Nothing in this pack is worth risking that.

---

# 7 · SOURCES

- [FATF Mutual Evaluation Report — India, September 2024 (Executive Summary)](https://www.fatf-gafi.org/content/dam/fatf-gafi/mer/Executive-Summary-MER%20India%202024.pdf.coredownload.inline.pdf)
- [FATF — India's measures to combat money laundering and terrorist financing](https://www.fatf-gafi.org/en/publications/Mutualevaluations/India-MER-2024.html)
- [FIU-IND Frequently Asked Questions — STR and CTR obligations](https://fiuindia.gov.in/files/FAQs/faqs.html)
- [RBI Master Circular on KYC norms / AML standards](https://rbidocs.rbi.org.in/rdocs/content/pdfs/45ML010712F_A.pdf)
- [AML Transaction Monitoring in India: RBI, PMLA, FIU-IND — KYC Hub](https://www.kychub.com/blog/transaction-monitoring-aml-india)
- [Cooperative Banks in India — Press Information Bureau, August 2025](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2157875&reg=3&lang=2)
- [AML Compliance System Costs for Mid-Size Banks, 2026 — Fraxtional](https://fraxtional.co/feeds/blog/aml-compliance-systems-cost-mid-size-banks)
- [TD Bank pleads guilty to BSA and money laundering conspiracy violations — US Department of Justice](https://www.justice.gov/archives/opa/pr/td-bank-pleads-guilty-bank-secrecy-act-and-money-laundering-conspiracy-violations-18b)
- [Transaction Monitoring Netherlands: what went wrong — ZQUAS](https://zquas.ai/tmnl.html)
- [Advances in Continual Graph Learning for Anti-Money Laundering Systems — arXiv](https://arxiv.org/html/2503.24259v1)
- [Money Laundering Statistics 2026 — KYC Hub](https://www.kychub.com/blog/money-laundering-statistics)
