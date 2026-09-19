# CHAKRAVYUH — project context for Claude Code

Read this before doing anything in this folder.

**What this is:** an AI anti-money-laundering investigation system, built for the
IGNITRRON'26 / Project J.A.R.V.I.S. 24-hour hackathon at KPR Institute,
18–19 September 2026. Team Tech Coders (T-300), problem statement FC-02,
domain FinTech & Cyber.

**The idea in one line:** existing systems score transactions; we score
*networks*, and return a finished evidence-backed case instead of an alert.

**Submission deadline: 06:00–07:00 AM, 19 September 2026.** A public GitHub
repo and a working live deployment are both mandatory.

---

## The eight stages

| # | Stage | File | Status |
| --- | --- | --- | --- |
| 1 | Synthetic data with 12 hidden laundering rings | `generate_data.py` | ✅ done |
| 2 | Entity resolution — records → real people | `entity_resolution.py` | ✅ done |
| 3 | Graph builder — people as nodes, money as edges | `graph_builder.py` | ✅ done |
| 4 | Detection swarm — 4 deterministic agents | `detectors.py` | ✅ done |
| 5 | Case builder — seed, trace, expand, prune | `case_builder.py` | ✅ done |
| 6 | Investigator agent (LLM) — writes the case | `agents.py` | ✅ done |
| 7 | Verifier agent (LLM) — adversarial check | `agents.py` | ✅ done |
| 5b | Relationship Lens — unusual account relationships vs bank baseline | `relationships.py` | ✅ done |
| — | DRONA — AI lead investigator that runs stages 6 & 7 | `orchestrator.py` | ✅ done |
| 8 | Streamlit dashboard + human approval (War Room, Cases, STR draft) | `app.py`, `str_report.py` | ✅ done |

## Rules that must not be broken

1. **Detection is deterministic. LLMs are used only where judgement is
   required, never for detection.** Graph algorithms find the structure and
   prove it; the LLM only turns a verified finding into language. This is the
   project's core claim — a regulator cannot accept "the model felt it was
   suspicious."

2. **Precision over recall, always.** Entity resolution scores pairwise
   precision **1.0** and it must stay there. A false merge accuses an innocent
   person. Missing a link is acceptable; inventing one is not.

3. **`ground_truth.csv`, `true_entity_id` and `owner_entity` are the answer
   key.** They may be read ONLY inside scoring functions, never by resolution,
   graph-building or detection logic.

4. **Never commit API keys.** The repo is public. Keys go in `.env` (which is
   gitignored) and in Streamlit Cloud secrets. Never in a source file.

5. **Do not modify completed stages.** `generate_data.py` and
   `entity_resolution.py` are finished and verified. If a later stage seems to
   need a change there, say so and stop — do not change them unilaterally.

6. **Cache all LLM output to disk.** The demo must run with no network. A live
   API call during the presentation is an unacceptable risk.

7. **Commit after every working stage**, with a message naming the stage.
   Meaningful commit history is inspected by judges at the 2:30 AM checkpoint.

## Run order

`generate_data.py` → `entity_resolution.py` → `graph_builder.py` → `detectors.py` →
`case_builder.py` → `relationships.py` → `orchestrator.py` (needs OPENAI_API_KEY) →
`streamlit run app.py`. The app only reads the files these write.

## The three AI agents

- **DRONA** (`orchestrator.py`, gpt-4o, function calling): triage, chooses read-only
  evidence tools, briefs SANJAYA, handles VIDURA's REVISE, records a recommendation.
  Guardrails are code: no tool creates findings or cases; every cited ID and every
  rupee string in a decision must have been returned by his tools; at least two
  evidence tools before deciding; no FILE_STR on a REJECTed report.
- **SANJAYA** = the investigator in `agents.py`. **VIDURA** = the verifier in `agents.py`.
- The Relationship Lens only annotates existing cases. It must never create a case —
  that is what keeps the zero-false-positive record safe.

## Key design decisions already made

- **Entity resolution runs before the graph.** 2,500 accounts resolve to ~1,828
  real people. A laundering circle is invisible while its nodes are fragmented.
- **Three-tier matching:** green (confirmed), yellow (probable, permanently
  flagged `has_unverified_link`), possible (not merged). Yellow links never
  chain — two weak guesses must not stack into a confident wrong answer.
- **Contradiction blockers** override every matching rule. Different PANs can
  never be the same person. Same address with different PANs means family
  members, not one person.
- **Cross-bank detection without data pooling** is the project's main novelty
  and is NOT optional. Single-bank views use opaque external counterparty nodes
  — a bank cannot tell that two external accounts are the same person. The
  consortium layer links them through salted PAN hashes only. Names, PANs in
  the clear, addresses, balances, KYC and account numbers must never appear in
  the consortium graph.
- **Two detection lanes:** discovery (rings found with nobody known in them) and
  watchlist (known high-risk entities on a lower threshold — enhanced due
  diligence). Overlapping cases merge into one.
- **Human in the loop.** Nothing is ever filed automatically.

## The dataset

Generated by `generate_data.py` with fixed seed 26192, so every run is
identical and the demo is reproducible.

| File | Rows | Contents |
| --- | --- | --- |
| `transactions.csv` | 80,000 | 30 days, two banks |
| `accounts.csv` | 2,500 | Type, bank, KYC level, owner |
| `customer_records.csv` | ~3,700 | Identity records across 3 systems, ~25% fields blank |
| `ground_truth.csv` | 258 | The ring transactions — answer key only |

Twelve hidden rings: four circular, three mule networks, three velocity chains,
two structuring. Ring transactions are 0.32% of the total.

**The hero ring is `CIRC_6_HERO`:** ₹2.4 crore looping through six accounts in
about three hours, alternating between both banks, returning to its origin.
Six accounts, three resolved people, one circle. It must be invisible in each
single-bank view and visible in the consortium view — that is the demo.

## Stack

Python 3 · NetworkX · Streamlit · OpenAI API · Streamlit Community Cloud

Deliberately out of scope: authentication, user accounts, admin panels,
settings, mobile app, live bank integrations, cryptocurrency.

## If you are unsure

Ask rather than guess. Do one thing per request, verify it works, and commit.
If a bug survives three fix attempts, stop and say so rather than continuing to
patch — removing the feature is preferable to breaking working code.
