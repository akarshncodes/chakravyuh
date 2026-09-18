#!/usr/bin/env python3
"""
CHAKRAVYUH AI - Stage 2: entity resolution.

Banks store the same real person multiple times across separate KYC systems,
each copy spelled differently and each missing different fields. Until those
scattered records are merged back into one person, the account/transaction
graph downstream is wrong - a ring "run by 3 people through 6 accounts" looks
like 6 unrelated strangers if nothing recognises they are the same names,
misspelled.

Standard library only - no third-party packages required.
Does not modify generate_data.py; reads its CSV outputs only.
"""

import csv
import os
from collections import Counter, defaultdict
from difflib import SequenceMatcher

# =====================================================================
# SETTINGS
# =====================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOMER_RECORDS_PATH = os.path.join(BASE_DIR, "customer_records.csv")
ACCOUNTS_PATH = os.path.join(BASE_DIR, "accounts.csv")
RESOLVED_ENTITIES_PATH = os.path.join(BASE_DIR, "resolved_entities.csv")
ACCOUNT_OWNERS_PATH = os.path.join(BASE_DIR, "account_owners.csv")

# When True, resolution is skipped entirely and every account is treated as
# its own separate person. Both output files are still written in the same
# shape, so any downstream stage keeps working against a "do nothing" answer.
BYPASS_RESOLUTION = False

# GREEN name-similarity threshold (R2/R3), YELLOW soundex threshold (R8).
GREEN_NAME_SIM_THRESHOLD = 0.85
YELLOW_SOUNDEX_SIM_THRESHOLD = 0.75

# Business suffixes to strip before comparing names, longest phrase first so
# "and sons" is removed as a unit before the bare word "sons" would be.
_RAW_SUFFIX_PHRASES = ["and sons", "sons", "traders", "enterprises", "co", "pvt ltd", "pvt", "ltd"]
SUFFIX_PHRASES = sorted(_RAW_SUFFIX_PHRASES, key=lambda p: -len(p.split()))


# =====================================================================
# LOADING
#
# CRITICAL: true_entity_id (customer_records.csv) and owner_entity
# (accounts.csv) are the answer key. load_records()/load_accounts() below
# physically never read those columns into the structures the matching
# logic operates on, so the matcher cannot "cheat" even by accident.
# load_answer_key() re-opens the file independently and is called from
# nowhere except score_resolution(), at the very end of the run.
# =====================================================================

def normalize_name(name):
    """lowercase, strip punctuation, collapse whitespace."""
    if not name:
        return ""
    chars = []
    for ch in name.lower():
        chars.append(ch if (ch.isalnum() or ch.isspace()) else " ")
    return " ".join("".join(chars).split())


def strip_business_suffix(normalized_name):
    """Remove trailing business words so 'mary bose & sons' -> 'mary bose'."""
    tokens = normalized_name.split()
    changed = True
    while changed and tokens:
        changed = False
        for phrase in SUFFIX_PHRASES:
            phrase_tokens = phrase.split()
            n = len(phrase_tokens)
            # len(tokens) > n (strict) guarantees we never strip a name down
            # to nothing - a business word alone is not a person's name.
            if len(tokens) > n and tokens[-n:] == phrase_tokens:
                tokens = tokens[:-n]
                changed = True
                break
    return " ".join(tokens)


def soundex(word):
    """
    Classic American Soundex: first letter kept, remaining consonants mapped
    to digit groups, vowels/H/W drop out (but do not block a repeated digit
    from re-triggering later), result padded/truncated to 4 characters.
    Lets "Desai" and "Deasi" (an adjacent-letter transposition typo) collide
    on the same code even though the strings differ.
    """
    word = "".join(ch for ch in word.upper() if ch.isalpha())
    if not word:
        return ""
    codes = {}
    for group, letters in enumerate(["BFPV", "CGJKQSXZ", "DT", "L", "MN", "R"], start=1):
        for ch in letters:
            codes[ch] = str(group)
    out = [word[0]]
    prev_code = codes.get(word[0], "")
    for ch in word[1:]:
        code = codes.get(ch, "")
        if code and code != prev_code:
            out.append(code)
        prev_code = code  # resets to "" on a vowel/H/W, allowing the next
                           # occurrence of the same digit group to count again
    return ("".join(out) + "000")[:4]


def generate_name_variants_key(tokens):
    return tuple(tokens)


def prepare_record(raw):
    norm = normalize_name(raw["name_as_written"])
    stripped = strip_business_suffix(norm)
    tokens = stripped.split()
    surname = tokens[-1] if tokens else ""
    rec = dict(raw)
    rec["stripped_name"] = stripped
    rec["tokens"] = tokens
    rec["surname_soundex"] = soundex(surname) if surname else ""
    return rec


def load_records(path):
    """Returns a list of record dicts WITHOUT true_entity_id anywhere in them."""
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = {
                "record_id": row["record_id"],
                "source_system": row["source_system"],
                "name_as_written": row["name_as_written"].strip(),
                "phone": row["phone"].strip(),
                "pan": row["pan"].strip(),
                "address": row["address"].strip(),
                "linked_account": row["linked_account"].strip(),
            }
            records.append(prepare_record(raw))
    return records


def load_accounts(path):
    """Returns account_id -> account dict WITHOUT owner_entity anywhere in it."""
    accounts = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            accounts[row["account_id"]] = {
                "account_id": row["account_id"],
                "name": row["name"],
                "account_type": row["account_type"],
                "bank": row["bank"],
            }
    return accounts


def load_answer_key(path):
    """record_id -> true_entity_id. Only ever called from score_resolution()."""
    key = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key[row["record_id"]] = row["true_entity_id"]
    return key


# =====================================================================
# NAME-STRUCTURE COMPARISONS
# =====================================================================

def name_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def initials_match(tokens_a, tokens_b):
    """
    'k pillai' vs 'karthik pillai': same token count, and every token either
    matches exactly or one side is a single-letter initial that is a prefix
    of the other side's full token, in the same position.
    """
    if len(tokens_a) != len(tokens_b) or not tokens_a:
        return False
    saw_initial = False
    for ta, tb in zip(tokens_a, tokens_b):
        if ta == tb:
            continue
        if len(ta) == 1 and tb.startswith(ta):
            saw_initial = True
            continue
        if len(tb) == 1 and ta.startswith(tb):
            saw_initial = True
            continue
        return False
    return saw_initial  # require at least one real initial, not just equality


def reversed_match(tokens_a, tokens_b):
    """'pillai karthik' vs 'karthik pillai' - same tokens, opposite order."""
    if len(tokens_a) < 2 or tokens_a == tokens_b:
        return False
    return tokens_a == list(reversed(tokens_b))


# =====================================================================
# FIELD-AGREEMENT / CONFLICT HELPERS
# =====================================================================

def _agree(r1, r2, field):
    return bool(r1[field]) and bool(r2[field]) and r1[field] == r2[field]


def _conflict(r1, r2, field):
    return bool(r1[field]) and bool(r2[field]) and r1[field] != r2[field]


def phone_agrees(r1, r2):
    return _agree(r1, r2, "phone")


def address_agrees(r1, r2):
    return _agree(r1, r2, "address")


def pan_agrees(r1, r2):
    return _agree(r1, r2, "pan")


def account_agrees(r1, r2):
    return _agree(r1, r2, "linked_account")


def phone_conflict(r1, r2):
    return _conflict(r1, r2, "phone")


def address_conflict(r1, r2):
    return _conflict(r1, r2, "address")


def other_field_agrees(r1, r2):
    """The 'at least one other field agreeing' precondition every YELLOW rule needs."""
    return phone_agrees(r1, r2) or address_agrees(r1, r2) or pan_agrees(r1, r2)


# =====================================================================
# BLOCKERS
#
# Checked FIRST. A blocker firing means: do not merge, no matter which
# matching rule would otherwise have fired.
# =====================================================================

def pan_hard_block(r1, r2):
    """
    B1: two different non-blank PANs can never be the same person.
    PAN is a unique government tax ID in India - one person, one PAN.
    A genuine mismatch is the single strongest "these are NOT the same
    person" signal available, so it overrides every other rule, including
    a shared account or a shared phone (which real families and joint
    accounts legitimately share between DIFFERENT people).
    """
    return bool(r1["pan"]) and bool(r2["pan"]) and r1["pan"] != r2["pan"]


def is_b3_family_case(r1, r2):
    """
    B3: same address but conflicting PAN - almost certainly family members
    living together (or successive occupants), not the same individual.
    Already blocked by B1 above; logged separately purely so the report can
    surface how often that specific real-world situation occurs.
    """
    return pan_hard_block(r1, r2) and address_agrees(r1, r2)


def name_only_conflict(r1, r2):
    """
    B2: guards every rule whose evidence leans on name *similarity* rather
    than an exact independent field. If phone AND address both actively
    disagree (both sides non-blank, both different), a similar-looking name
    is most likely coincidence - e.g. two unrelated "R. Sharma"s in
    different cities with different numbers - not evidence of one person.
    Rules with their own independent hard evidence (R0 same account, R1
    same PAN, R4 phone+address both agree) do not need this guard: by
    construction they cannot have a live phone/address conflict anyway.
    """
    return phone_conflict(r1, r2) and address_conflict(r1, r2)


# =====================================================================
# MATCHING RULES
# =====================================================================

def rule_R0(r1, r2):
    """Same non-blank linked_account: the bank's own ledger says one account, one owner."""
    return account_agrees(r1, r2)


def rule_R1(r1, r2):
    """Same non-blank PAN: the single most authoritative identity field available."""
    return pan_agrees(r1, r2)


def rule_R2(r1, r2, sim):
    """Same phone number, and the names are close enough to plausibly be one person."""
    return phone_agrees(r1, r2) and sim >= GREEN_NAME_SIM_THRESHOLD


def rule_R3(r1, r2, sim):
    """Same address and similar name - but only if phone doesn't actively contradict it."""
    return address_agrees(r1, r2) and sim >= GREEN_NAME_SIM_THRESHOLD and not phone_conflict(r1, r2)


def rule_R4(r1, r2):
    """Same phone AND same address: two independent fields agreeing, name aside."""
    return phone_agrees(r1, r2) and address_agrees(r1, r2)


def rule_R5(r1, r2):
    """Initial expansion ('K. Pillai' / 'Karthik Pillai'), corroborated by another field."""
    return other_field_agrees(r1, r2) and initials_match(r1["tokens"], r2["tokens"])


def rule_R6(r1, r2):
    """Reversed name order ('Pillai Karthik' / 'Karthik Pillai'), corroborated."""
    return other_field_agrees(r1, r2) and reversed_match(r1["tokens"], r2["tokens"])


def rule_R7(r1, r2):
    """Identical after stripping a business suffix ('Mary Bose & Sons' / 'Mary Bose')."""
    if not other_field_agrees(r1, r2):
        return False
    return bool(r1["stripped_name"]) and r1["stripped_name"] == r2["stripped_name"]


def rule_R8(r1, r2, sim):
    """Sound-alike surname (soundex) plus a reasonably similar full name, corroborated."""
    if not other_field_agrees(r1, r2):
        return False
    if not r1["surname_soundex"] or r1["surname_soundex"] != r2["surname_soundex"]:
        return False
    return sim >= YELLOW_SOUNDEX_SIM_THRESHOLD


def evaluate_pair(r1, r2):
    """
    Returns (tier, blocker_type, rules_fired).
    tier is one of "BLOCKED", "GREEN", "YELLOW", "NONE".
    """
    if pan_hard_block(r1, r2):
        return "BLOCKED", "B1_PAN_CONFLICT", []

    sim = name_similarity(r1["stripped_name"], r2["stripped_name"])
    conflict = name_only_conflict(r1, r2)

    green = []
    if rule_R0(r1, r2):
        green.append("R0_same_account")
    if rule_R1(r1, r2):
        green.append("R1_same_pan")
    if not conflict and rule_R2(r1, r2, sim):
        green.append("R2_phone_and_name_sim")
    if not conflict and rule_R3(r1, r2, sim):
        green.append("R3_address_and_name_sim")
    if rule_R4(r1, r2):
        green.append("R4_phone_and_address")
    if green:
        return "GREEN", None, green

    if conflict:
        return "BLOCKED", "B2_NAME_ONLY_CONFLICT", []

    yellow = []
    if rule_R5(r1, r2):
        yellow.append("R5_initials")
    if rule_R6(r1, r2):
        yellow.append("R6_reversed")
    if rule_R7(r1, r2):
        yellow.append("R7_suffix_stripped")
    if rule_R8(r1, r2, sim):
        yellow.append("R8_soundex")
    if yellow:
        return "YELLOW", None, yellow

    return "NONE", None, []


# =====================================================================
# CANDIDATE PAIR GENERATION (blocking indices, avoids full O(n^2) scan)
# =====================================================================

def _bucket_pairs(index):
    pairs = set()
    for record_ids in index.values():
        if len(record_ids) < 2:
            continue
        record_ids = sorted(record_ids)
        for i in range(len(record_ids)):
            for j in range(i + 1, len(record_ids)):
                pairs.add((record_ids[i], record_ids[j]))
    return pairs


def build_candidate_pairs(records):
    idx_account = defaultdict(list)
    idx_pan = defaultdict(list)
    idx_phone = defaultdict(list)
    idx_address = defaultdict(list)
    idx_initial_bucket = defaultdict(list)   # (first-char-of-first-token, surname)
    idx_sorted_tokens = defaultdict(list)    # tuple(sorted(tokens))
    idx_stripped_name = defaultdict(list)
    idx_soundex = defaultdict(list)

    for r in records:
        rid = r["record_id"]
        if r["linked_account"]:
            idx_account[r["linked_account"]].append(rid)
        if r["pan"]:
            idx_pan[r["pan"]].append(rid)
        if r["phone"]:
            idx_phone[r["phone"]].append(rid)
        if r["address"]:
            idx_address[r["address"]].append(rid)
        if r["stripped_name"]:
            idx_stripped_name[r["stripped_name"]].append(rid)
        if r["surname_soundex"]:
            idx_soundex[r["surname_soundex"]].append(rid)
        tokens = r["tokens"]
        if tokens:
            idx_initial_bucket[(tokens[0][0], tokens[-1])].append(rid)
            idx_sorted_tokens[tuple(sorted(tokens))].append(rid)

    pairs = set()
    for idx in (idx_account, idx_pan, idx_phone, idx_address,
                idx_initial_bucket, idx_sorted_tokens, idx_stripped_name, idx_soundex):
        pairs |= _bucket_pairs(idx)
    return sorted(pairs)


# =====================================================================
# UNION-FIND
# =====================================================================

class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def make(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x):
        self.make(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return ra


# =====================================================================
# CLUSTERING
# =====================================================================

def resolve_entities(records):
    records_by_id = {r["record_id"]: r for r in records}
    all_record_ids = list(records_by_id.keys())

    candidate_pairs = build_candidate_pairs(records)

    stats = {
        "candidate_pairs": len(candidate_pairs),
        "blockers": Counter(),
        "b3_family_cases": 0,
        "green_rule_counts": Counter(),
        "yellow_rule_counts": Counter(),
        "pan_invariant_guard_blocks": 0,
    }

    green_links = []   # (r1, r2, [rules])
    yellow_links = []  # (r1, r2, [rules])

    for r1_id, r2_id in candidate_pairs:
        r1, r2 = records_by_id[r1_id], records_by_id[r2_id]
        tier, blocker_type, rules = evaluate_pair(r1, r2)
        if tier == "BLOCKED":
            stats["blockers"][blocker_type] += 1
            if blocker_type == "B1_PAN_CONFLICT" and is_b3_family_case(r1, r2):
                stats["b3_family_cases"] += 1
            continue
        if tier == "GREEN":
            green_links.append((r1_id, r2_id, rules))
            for rule in rules:
                stats["green_rule_counts"][rule] += 1
        elif tier == "YELLOW":
            yellow_links.append((r1_id, r2_id, rules))
            for rule in rules:
                stats["yellow_rule_counts"][rule] += 1

    # ---- Pass 1: union-find over GREEN links only. Chaining is allowed
    # (A-B and B-C green means A, B, C are one person) - but every union is
    # guarded so a resolved entity can never end up holding two different
    # non-blank PANs, even transitively through a chain of individually
    # harmless-looking links. ----
    uf = UnionFind()
    for rid in all_record_ids:
        uf.make(rid)

    cluster_pans = {
        rid: ({records_by_id[rid]["pan"]} if records_by_id[rid]["pan"] else set())
        for rid in all_record_ids
    }

    for r1_id, r2_id, _rules in sorted(green_links):
        root1, root2 = uf.find(r1_id), uf.find(r2_id)
        if root1 == root2:
            continue
        pans1 = cluster_pans.get(root1, set())
        pans2 = cluster_pans.get(root2, set())
        merged_pans = pans1 | pans2
        if len(merged_pans) > 1:
            stats["pan_invariant_guard_blocks"] += 1
            continue
        new_root = uf.union(root1, root2)
        cluster_pans[new_root] = merged_pans

    # Freeze pass-1 cluster membership before doing any pass-2 merging.
    origin_root = {rid: uf.find(rid) for rid in all_record_ids}
    origin_clusters = defaultdict(list)
    for rid, root in origin_root.items():
        origin_clusters[root].append(rid)

    # ---- Pass 2: YELLOW links may merge two DIFFERENT pass-1 clusters, run
    # exactly once. Every pass-1 cluster may take part in at most one
    # yellow merge, which makes bridging structurally impossible: a yellow
    # link can never chain through a cluster that another yellow link has
    # already pulled in, so two weak guesses can never stack into a
    # confident-looking wrong answer. ----
    consumed_origins = set()
    unverified_record_ids = set()

    for r1_id, r2_id, _rules in sorted(yellow_links):
        oc1, oc2 = origin_root[r1_id], origin_root[r2_id]
        if oc1 == oc2:
            continue
        if oc1 in consumed_origins or oc2 in consumed_origins:
            continue
        cluster1 = origin_clusters[oc1]
        cluster2 = origin_clusters[oc2]
        blocked_pair = False
        for a_id in cluster1:
            a = records_by_id[a_id]
            for b_id in cluster2:
                b = records_by_id[b_id]
                tier, _bt, _r = evaluate_pair(a, b)
                if tier == "BLOCKED":
                    blocked_pair = True
                    break
            if blocked_pair:
                break
        if blocked_pair:
            continue

        uf.union(r1_id, r2_id)
        consumed_origins.add(oc1)
        consumed_origins.add(oc2)
        for rid in cluster1:
            unverified_record_ids.add(rid)
        for rid in cluster2:
            unverified_record_ids.add(rid)

    final_root = {rid: uf.find(rid) for rid in all_record_ids}
    final_groups = defaultdict(list)
    for rid, root in final_root.items():
        final_groups[root].append(rid)

    entity_rules = defaultdict(set)
    for r1_id, r2_id, rules in green_links + yellow_links:
        if final_root[r1_id] == final_root[r2_id]:
            entity_rules[final_root[r1_id]].update(rules)

    return {
        "records_by_id": records_by_id,
        "final_groups": final_groups,           # root -> [record_id, ...]
        "entity_rules": entity_rules,            # root -> {rule names}
        "unverified_record_ids": unverified_record_ids,
        "origin_root": origin_root,              # pass-1-only assignment (for scoring)
        "final_root": final_root,                # pass-1+pass-2 assignment (for scoring)
        "green_links": green_links,
        "yellow_links": yellow_links,
        "stats": stats,
    }


# =====================================================================
# ENTITY / OUTPUT ASSEMBLY
# =====================================================================

def choose_canonical_name(recs):
    """Most frequent spelling in the cluster; ties broken by longest (most complete)."""
    if not recs:
        return ""
    counts = Counter(r["name_as_written"] for r in recs)
    top = max(counts.values())
    candidates = [n for n, c in counts.items() if c == top]
    candidates.sort(key=lambda n: (-len(n), n))
    return candidates[0]


def choose_common_value(recs, field):
    vals = [r[field] for r in recs if r[field]]
    if not vals:
        return ""
    return Counter(vals).most_common(1)[0][0]


def build_entities(records, accounts, resolution):
    records_by_id = resolution["records_by_id"]
    final_groups = resolution["final_groups"]
    entity_rules = resolution["entity_rules"]
    unverified_record_ids = resolution["unverified_record_ids"]

    entities = []
    claimed_accounts = {}  # account_id -> entity index, for orphan detection

    ordered_roots = sorted(final_groups.keys(), key=lambda root: min(final_groups[root]))
    for root in ordered_roots:
        record_ids = sorted(final_groups[root])
        recs = [records_by_id[rid] for rid in record_ids]
        account_ids = sorted({r["linked_account"] for r in recs if r["linked_account"]})
        entity = {
            "canonical_name": choose_canonical_name(recs),
            "phone": choose_common_value(recs, "phone"),
            "pan": choose_common_value(recs, "pan"),
            "address": choose_common_value(recs, "address"),
            "account_ids": account_ids,
            "record_ids": record_ids,
            "has_unverified_link": any(rid in unverified_record_ids for rid in record_ids),
            "is_watchlisted": any(r["source_system"] == "WATCHLIST" for r in recs),
            "rules_used": sorted(entity_rules.get(root, set())),
        }
        entities.append(entity)
        for aid in account_ids:
            if aid not in claimed_accounts:
                claimed_accounts[aid] = len(entities) - 1

    # Accounts with zero linked customer_records carry no evidence at all,
    # so they cannot honestly be folded into anyone else's cluster - each
    # becomes its own single-account, zero-record entity. This (plus any
    # genuine recall misses above) is why the final headcount lands near,
    # not exactly at, the true number of people.
    orphan_accounts = sorted(aid for aid in accounts if aid not in claimed_accounts)
    for aid in orphan_accounts:
        entities.append({
            "canonical_name": accounts[aid]["name"],
            "phone": "",
            "pan": "",
            "address": "",
            "account_ids": [aid],
            "record_ids": [],
            "has_unverified_link": False,
            "is_watchlisted": False,
            "rules_used": [],
        })

    for idx, e in enumerate(entities):
        e["entity_key"] = f"PERSON{idx + 1:05d}"

    account_to_entity = {}
    for e in entities:
        for aid in e["account_ids"]:
            account_to_entity[aid] = e["entity_key"]

    return entities, account_to_entity


def build_bypass_entities(records, accounts):
    """BYPASS_RESOLUTION=True: every account is its own separate person."""
    records_by_account = defaultdict(list)
    for r in records:
        if r["linked_account"]:
            records_by_account[r["linked_account"]].append(r)

    entities = []
    for idx, aid in enumerate(sorted(accounts.keys())):
        recs = records_by_account.get(aid, [])
        entities.append({
            "entity_key": f"PERSON{idx + 1:05d}",
            "canonical_name": choose_canonical_name(recs) or accounts[aid]["name"],
            "phone": choose_common_value(recs, "phone"),
            "pan": choose_common_value(recs, "pan"),
            "address": choose_common_value(recs, "address"),
            "account_ids": [aid],
            "record_ids": sorted(r["record_id"] for r in recs),
            "has_unverified_link": False,
            "is_watchlisted": any(r["source_system"] == "WATCHLIST" for r in recs),
            "rules_used": [],
        })

    account_to_entity = {e["account_ids"][0]: e["entity_key"] for e in entities}
    return entities, account_to_entity


# =====================================================================
# OUTPUT
# =====================================================================

def write_outputs(entities, accounts, account_to_entity):
    with open(RESOLVED_ENTITIES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "entity_key", "canonical_name", "phone", "pan", "address",
            "num_records", "num_accounts", "account_ids", "record_ids",
            "has_unverified_link", "is_watchlisted", "rules_used",
        ])
        writer.writeheader()
        for e in sorted(entities, key=lambda x: x["entity_key"]):
            writer.writerow({
                "entity_key": e["entity_key"],
                "canonical_name": e["canonical_name"],
                "phone": e["phone"],
                "pan": e["pan"],
                "address": e["address"],
                "num_records": len(e["record_ids"]),
                "num_accounts": len(e["account_ids"]),
                "account_ids": ";".join(e["account_ids"]),
                "record_ids": ";".join(e["record_ids"]),
                "has_unverified_link": e["has_unverified_link"],
                "is_watchlisted": e["is_watchlisted"],
                "rules_used": ";".join(e["rules_used"]),
            })

    watchlisted_by_entity = {e["entity_key"]: e["is_watchlisted"] for e in entities}
    unverified_by_entity = {e["entity_key"]: e["has_unverified_link"] for e in entities}

    with open(ACCOUNT_OWNERS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "account_id", "entity_key", "is_watchlisted", "has_unverified_link",
        ])
        writer.writeheader()
        for aid in sorted(accounts.keys()):
            entity_key = account_to_entity[aid]
            writer.writerow({
                "account_id": aid,
                "entity_key": entity_key,
                "is_watchlisted": watchlisted_by_entity[entity_key],
                "has_unverified_link": unverified_by_entity[entity_key],
            })


# =====================================================================
# SCORING - the only place the answer key is read
# =====================================================================

def _pairwise_precision_recall(assignment, answer_key, record_ids):
    """
    Standard pairwise clustering precision/recall, computed via a
    contingency table instead of enumerating every record pair directly
    (O(n) instead of O(n^2)):
      predicted_pairs = sum over predicted clusters of C(size, 2)
      true_pairs      = sum over true entities of C(size, 2)
      true_positives  = sum over (predicted, true) cells of C(size, 2)
    """
    def c2(n):
        return n * (n - 1) // 2

    pred_sizes = Counter()
    true_sizes = Counter()
    cell_sizes = Counter()
    for rid in record_ids:
        pred = assignment[rid]
        true = answer_key[rid]
        pred_sizes[pred] += 1
        true_sizes[true] += 1
        cell_sizes[(pred, true)] += 1

    predicted_pairs = sum(c2(n) for n in pred_sizes.values())
    true_pairs = sum(c2(n) for n in true_sizes.values())
    true_positive_pairs = sum(c2(n) for n in cell_sizes.values())

    precision = (true_positive_pairs / predicted_pairs) if predicted_pairs else 1.0
    recall = (true_positive_pairs / true_pairs) if true_pairs else 1.0
    return precision, recall, predicted_pairs, true_pairs, true_positive_pairs


def find_offending_green_clusters(origin_clusters, answer_key, green_links):
    """For green-only clustering: clusters that mix more than one real person."""
    offending = []
    for root, rids in origin_clusters.items():
        if len(rids) < 2:
            continue
        true_ids = {answer_key[rid] for rid in rids}
        if len(true_ids) > 1:
            offending.append((root, sorted(rids), true_ids))
    return offending


def score_resolution(resolution, records_by_id):
    answer_key = load_answer_key(CUSTOMER_RECORDS_PATH)
    record_ids = list(records_by_id.keys())

    green_precision, green_recall, gp_pairs, gt_pairs, gtp_pairs = _pairwise_precision_recall(
        resolution["origin_root"], answer_key, record_ids)
    final_precision, final_recall, fp_pairs, ft_pairs, ftp_pairs = _pairwise_precision_recall(
        resolution["final_root"], answer_key, record_ids)

    origin_clusters = defaultdict(list)
    for rid, root in resolution["origin_root"].items():
        origin_clusters[root].append(rid)
    offending = find_offending_green_clusters(origin_clusters, answer_key, resolution["green_links"])

    return {
        "green_precision": green_precision, "green_recall": green_recall,
        "green_pairs": (gp_pairs, gt_pairs, gtp_pairs),
        "final_precision": final_precision, "final_recall": final_recall,
        "final_pairs": (fp_pairs, ft_pairs, ftp_pairs),
        "offending_green_clusters": offending,
    }


# =====================================================================
# REPORTING
# =====================================================================

def print_worked_examples_full(entities, records_by_id, count=3):
    candidates = [e for e in entities if len(e["record_ids"]) >= 2]
    candidates.sort(key=lambda e: (-len(e["record_ids"]), -len(e["rules_used"])))
    chosen = candidates[:count]
    for i, e in enumerate(chosen, start=1):
        print(f"\nExample {i}: {e['entity_key']}  ->  '{e['canonical_name']}'")
        print("  Scattered records before merge:")
        for rid in e["record_ids"]:
            r = records_by_id[rid]
            print(f"    [{r['source_system']:<17}] name='{r['name_as_written']:<22}' "
                  f"phone={r['phone'] or '-':<10} pan={r['pan'] or '-':<10} "
                  f"address={r['address'] or '-'}")
        print(f"  Merged result: canonical_name='{e['canonical_name']}', "
              f"phone={e['phone'] or '-'}, pan={e['pan'] or '-'}, "
              f"accounts={e['account_ids']}")
        print(f"  Rules that linked them: {e['rules_used'] or ['(single record only)']}")
        if e["has_unverified_link"]:
            print("  NOTE: includes an unverified (yellow-tier) link.")


def print_report(records, accounts, entities, resolution, score):
    stats = resolution["stats"]
    total_records = len(records)
    total_accounts = len(accounts)
    total_entities = len(entities)

    print("=" * 72)
    print("CHAKRAVYUH AI - Stage 2: entity resolution report")
    print("=" * 72)
    print(f"Customer records in:  {total_records:,}")
    print(f"Accounts in:          {total_accounts:,}")
    print(f"Resolved entities out: {total_entities:,}")
    print(f"Account -> person reduction: {total_accounts:,} accounts -> {total_entities:,} "
          f"people (target ~1,800)")

    print("-" * 72)
    print("GREEN links found, by rule:")
    for rule, n in sorted(stats["green_rule_counts"].items()):
        print(f"  {rule:<28} {n:,}")
    print(f"  {'TOTAL green links':<28} {len(resolution['green_links']):,}")

    print("YELLOW links found, by rule:")
    for rule, n in sorted(stats["yellow_rule_counts"].items()):
        print(f"  {rule:<28} {n:,}")
    print(f"  {'TOTAL yellow links':<28} {len(resolution['yellow_links']):,}")

    num_unverified_entities = sum(1 for e in entities if e["has_unverified_link"])
    print("-" * 72)
    print(f"Entities carrying an unverified (yellow) link: {num_unverified_entities:,}")

    print("-" * 72)
    print("Blockers fired, by type:")
    for blocker, n in sorted(stats["blockers"].items()):
        print(f"  {blocker:<28} {n:,}")
    print(f"  {'B3 (family, same addr/diff PAN)':<28} {stats['b3_family_cases']:,}  (subset of B1)")
    print(f"  {'Pass-1 PAN-invariant guard':<28} {stats['pan_invariant_guard_blocks']:,}  "
          f"(chain-safety: green union rejected)")

    print("-" * 72)
    print("Pairwise precision / recall (over customer_records pairs):")
    gp, gt, gtp = score["green_pairs"]
    fp, ft, ftp = score["final_pairs"]
    print(f"  GREEN-only:     precision={score['green_precision']:.4f}  recall={score['green_recall']:.4f}  "
          f"(true positive pairs {gtp:,} / predicted {gp:,} / true {gt:,})")
    print(f"  GREEN+YELLOW:   precision={score['final_precision']:.4f}  recall={score['final_recall']:.4f}  "
          f"(true positive pairs {ftp:,} / predicted {fp:,} / true {ft:,})")
    print(f"  Yellow tier cost: precision {score['green_precision'] - score['final_precision']:+.4f}, "
          f"recall {score['final_recall'] - score['green_recall']:+.4f}")

    if score["green_precision"] < 1.0:
        offending = score["offending_green_clusters"]
        print("-" * 72)
        print(f"WARNING: GREEN-only precision is below 1.0 - {len(offending)} cluster(s) "
              f"mix records from different real people:")
        records_by_id = resolution["records_by_id"]
        green_links = resolution["green_links"]
        for root, rids, true_ids in offending:
            print(f"  Cluster rooted at {root} mixes true entities {sorted(true_ids)}:")
            for rid in rids:
                r = records_by_id[rid]
                print(f"    {rid}  name='{r['name_as_written']}'  source={r['source_system']}")
            rid_set = set(rids)
            for r1_id, r2_id, rules in green_links:
                if r1_id in rid_set and r2_id in rid_set:
                    print(f"    linked by {rules}: {r1_id} <-> {r2_id}")

    print_worked_examples_full(entities, resolution["records_by_id"], count=3)
    print("=" * 72)


# =====================================================================
# MAIN
# =====================================================================

def main():
    records = load_records(CUSTOMER_RECORDS_PATH)
    accounts = load_accounts(ACCOUNTS_PATH)

    if BYPASS_RESOLUTION:
        entities, account_to_entity = build_bypass_entities(records, accounts)
        write_outputs(entities, accounts, account_to_entity)
        print("=" * 72)
        print("CHAKRAVYUH AI - Stage 2: entity resolution BYPASSED")
        print("=" * 72)
        print(f"Customer records in:  {len(records):,}")
        print(f"Accounts in:          {len(accounts):,}")
        print(f"Entities out:         {len(entities):,}  (one per account, no matching performed)")
        print("=" * 72)
        return

    resolution = resolve_entities(records)
    entities, account_to_entity = build_entities(records, accounts, resolution)
    write_outputs(entities, accounts, account_to_entity)

    score = score_resolution(resolution, resolution["records_by_id"])
    print_report(records, accounts, entities, resolution, score)


if __name__ == "__main__":
    main()
