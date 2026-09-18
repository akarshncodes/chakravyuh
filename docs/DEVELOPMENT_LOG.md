# Development log

How CHAKRAVYUH was built during IGNITRRON'26, 18–19 September 2026. We committed after every stage that worked, and we tested each stage ourselves instead of trusting that it "looked right". Most of what's interesting below is what those tests caught.

![Development progress](development_progress.png)

## The build, stage by stage

| When | Stage | What we built | What we checked |
| --- | --- | --- | --- |
| 18 Sep, 13:27 | **1 · Data** | Synthetic bank data: 80,000 transfers, 2,500 accounts, 3 identity systems, 12 hidden laundering rings (seed 26192) | Rings are only 0.32% of transfers, so finding them means something |
| 18 Sep, 19:39 | **2 · Identity** | Entity resolution: 3 confidence tiers, contradiction blockers, weak links never chain | Zero false merges across ~3,700 records |
| 18 Sep, 15:32 | **3 · Graph** | People as nodes, money as edges; Bank A, Bank B and consortium views | The hero ring must be invisible to each bank alone |
| 18 Sep, 21:23 | **4 · Detection** | CIRCLE, SPRAY, SPEED, THRESHOLD (+3 extra detectors that stay silent unless certain) | 42 findings |
| 18 Sep, 21:35 | **5 · Cases** | Seed → trace → expand → prune; overlapping findings merged | 11 cases, 11 of 12 rings, **0 false positives** |
| 18 Sep, 21:41 | **8 · Dashboard** | Streamlit portal, deployed on Streamlit Cloud | Loads only precomputed files, so the demo can't lag |
| 18 Sep, 23:31 | **6–7 · AI writer + verifier** | Case narratives + code fact-check + sceptical AI reviewer | Every ID, amount and date checked against raw data |
| 19 Sep, 02:13 | **5b · Relationship Lens** | Five "unusual relationship" checks vs the bank baseline | 2.73 signals per case vs 0.4 for random customer groups |
| 19 Sep, 02:13 | **DRONA + STR draft** | AI lead investigator with read-only tools; printable STR on approval | Every decision checked by code before it's saved |
| 19 Sep, 02:39 | **War Room** | Replay DRONA's investigation step by step, graph lights up | Runs from the cached log, with no live API call |

*(Stage 3's timestamp is earlier than stage 2's because the graph builder was drafted first and committed before the identity fixes landed.)*

## Bugs we found and fixed

| # | What went wrong | How we caught it | Fix |
| --- | --- | --- | --- |
| 1 | 274 accounts had no identity record at all, so rings split into strangers | Counted people after resolution: 2,113 instead of ~1,800 | Data bug, not a resolver bug — generator now writes a record for every account |
| 2 | Some records had no phone, PAN or address, only a name | Hero ring still split | Every account now has at least one strong identifier (like real KYC) |
| 3 | **The cross-bank demo was inverted**: both banks could see the whole ring | Ran a cycle test on every view | Changed the ring's bank pattern so each bank misses one hop |
| 4 | `.gitignore` excluded every CSV, so the deployed app had no data | Checked what was actually pushed | Only scratch files ignored now |
| 5 | No README | Checkpoint audit | Written, then rewritten for judges |
| 6 | Stages 6–7 (the AI part) didn't exist yet | Audit against the problem statement | Built the writer and the verifier |
| 7 | The AI never actually ran — every report came from the offline template | Read the output file: `model: template` | Added the missing API key file |
| 8 | **The AI wrote ₹140 crore for ₹14 crore** (lakh/crore formatting) | Our code fact-checker rejected the report | Python formats every number; the AI only copies them |
| 9 | The verifier rejected all 11 cases | Read its reasons: it demanded proof of intent | Rewrote it around *reasonable suspicion*, the actual STR standard → 11/11 PASS |
| 10 | Mule-network reports quoted a meaningless "amount cycled" | Read the reports | Only circular cases get that figure |
| 11 | "Amount cycled" and "total volume" were the same number | Read the reports | Principal = largest single transfer; assert added |

## Times our guardrails caught the AI

These happened in real runs, not in tests we staged:

- **"Rs 24,000,000"**: DRONA copied a western-format figure from detector text. We now re-express all detector amounts in Indian format, and code rejects any figure that no tool showed him.
- **"Rs 6.19 lakh"** for a ₹6,19,926 transfer (the correct short form is ₹6.2 lakh): blocked by code, and DRONA rewrote his reason.
- **A mule network described as a "closed loop"** and as "structuring": the numbers were right, so the fact-checker passed it. We added a typology check: a report may say *loop* only if CIRCLE fired and *structuring* only if THRESHOLD fired. On the re-run it fired again, blocking DRONA's "structured transactions" on case C006.

## Decisions we made on purpose

- **We report 11 of 12 rings, not 12.** `CIRC_5_SUBTLE` moves money slowly over days. We could tune a threshold to catch it, but that's tuning to the answer key.
- **The AI never detects.** Detection has to be reproducible and auditable. AI only runs the investigation and writes it up, and code checks what it writes.
- **Nothing is filed automatically.** Every case ends with a human officer.
