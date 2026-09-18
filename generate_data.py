#!/usr/bin/env python3
"""
CHAKRAVYUH AI - synthetic Indian retail banking dataset generator.

Generates a realistic-looking transaction/account/identity dataset with
twelve hidden money-laundering rings stitched into ordinary traffic, plus
an answer key (ground_truth.csv) for measuring detection accuracy later.

Standard library only - no third-party packages required.
"""

import csv
import datetime
import os
import random
from collections import Counter, defaultdict

# =====================================================================
# SETTINGS (constants)
# =====================================================================

SEED = 26192

NUM_ACCOUNTS = 2500
TARGET_TOTAL_TRANSACTIONS = 80000
NUM_DAYS = 30
START_DATE = datetime.date(2026, 8, 18)

BANKS = ["BANK_A", "BANK_B"]
CHANNELS = ["UPI", "IMPS", "NEFT", "RTGS", "CASH"]

NUM_ENTITIES = 1800  # real people the 2,500 accounts should resolve to

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW_START = datetime.datetime.combine(START_DATE, datetime.time(0, 0))
RTGS_MIN_AMOUNT = 200000  # real-world RTGS floor in India - keeps channel choice plausible

random.seed(SEED)

# =====================================================================
# NAME / ADDRESS POOLS
# =====================================================================

FIRST_NAMES_M = [
    "Arjun", "Rahul", "Amit", "Vijay", "Karthik", "Suresh", "Ramesh", "Anil",
    "Sanjay", "Rajesh", "Vikram", "Manoj", "Deepak", "Ashok", "Ravi", "Sunil",
    "Arun", "Prakash", "Naveen", "Kiran", "Gopal", "Mahesh", "Sandeep", "Rohit",
    "Ajay", "Pankaj", "Vinod", "Harish", "Nitin", "Gaurav", "Imran", "Faisal",
    "Zubair", "Irfan", "Harpreet", "Gurpreet", "Jaspreet", "Manpreet", "Thomas",
    "George", "Joseph", "Dinesh", "Srinivas", "Venkatesh", "Balaji", "Muthu",
]
FIRST_NAMES_F = [
    "Priya", "Anita", "Sunita", "Kavita", "Neha", "Pooja", "Deepa", "Rekha",
    "Meena", "Geeta", "Lakshmi", "Divya", "Swati", "Anjali", "Shobha", "Nisha",
    "Vandana", "Sarita", "Ritu", "Manisha", "Aarti", "Sneha", "Kritika", "Shreya",
    "Fatima", "Ayesha", "Zeenat", "Sabiha", "Harleen", "Simran", "Amandeep",
    "Rajwinder", "Mary", "Susan", "Anna", "Radha", "Padma", "Vasantha", "Kalpana",
    "Nithya", "Sowmya", "Bhavana", "Preethi", "Sangeeta", "Usha", "Jyoti",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Shah", "Mehta",
    "Reddy", "Rao", "Nair", "Pillai", "Iyer", "Iyengar", "Menon", "Naidu",
    "Chatterjee", "Banerjee", "Mukherjee", "Das", "Ghosh", "Bose", "Sengupta",
    "Khan", "Ahmed", "Sheikh", "Ansari", "Qureshi", "Malik", "Chauhan", "Yadav",
    "Mishra", "Tiwari", "Dubey", "Pandey", "Joshi", "Desai", "Trivedi", "Bhatt",
    "Kaur", "Gill", "Sandhu", "Brar", "Sidhu", "Dhillon", "Thomas", "Varghese",
    "Pillai & Sons", "Agarwal", "Bansal", "Jain", "Saxena", "Kapoor", "Malhotra",
]
BUSINESS_WORDS = [
    "Traders", "Enterprises", "Exports", "Textiles", "Foods", "Logistics",
    "Electronics", "Constructions", "Agro Industries", "Retail", "Pharma",
    "Motors", "Hardware", "Fashions", "Infotech", "Distributors", "Overseas",
]
CITIES = [
    ("Chennai", "Tamil Nadu"), ("Coimbatore", "Tamil Nadu"), ("Madurai", "Tamil Nadu"),
    ("Bengaluru", "Karnataka"), ("Mysuru", "Karnataka"), ("Mumbai", "Maharashtra"),
    ("Pune", "Maharashtra"), ("Nagpur", "Maharashtra"), ("Hyderabad", "Telangana"),
    ("Delhi", "Delhi"), ("Kolkata", "West Bengal"), ("Ahmedabad", "Gujarat"),
    ("Surat", "Gujarat"), ("Jaipur", "Rajasthan"), ("Lucknow", "Uttar Pradesh"),
    ("Kochi", "Kerala"), ("Thiruvananthapuram", "Kerala"), ("Bhopal", "Madhya Pradesh"),
    ("Patna", "Bihar"), ("Chandigarh", "Punjab"),
]
STREET_WORDS = ["Main Road", "Cross Street", "Nagar", "Colony", "Layout", "Extension", "Avenue"]

# =====================================================================
# GLOBAL STATE
# =====================================================================

accounts = []
accounts_by_id = {}
entities = []
entity_by_id = {}
transactions = []
ground_truth = []
customer_records = []
ring_account_ids = set()
ring_principals = []  # list of (ring_id, entity_id)
ring_txn_counts = defaultdict(int)
ring_meta = []  # (ring_id, ring_type, size, list_of_account_ids)

_acct_counter = 0
_txn_counter = 0
_record_counter = 0


def next_account_id():
    global _acct_counter
    _acct_counter += 1
    return f"ACC{_acct_counter:05d}"


def next_txn_id():
    global _txn_counter
    _txn_counter += 1
    return f"TXN{_txn_counter:06d}"


def next_record_id():
    global _record_counter
    _record_counter += 1
    return f"REC{_record_counter:06d}"


# =====================================================================
# HELPERS
# =====================================================================

def rand_phone():
    return random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))


def rand_pan():
    letters1 = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
    digits = "".join(random.choice("0123456789") for _ in range(4))
    letter2 = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters1}{digits}{letter2}"


def rand_address():
    house = random.randint(1, 999)
    street = random.choice(STREET_WORDS)
    city, state = random.choice(CITIES)
    pin = random.randint(100000, 699999)
    return f"{house}, {street}, {city}, {state} - {pin}"


def random_dt(day_range=None, business_hours_bias=0.75):
    """Timestamp inside the 30-day window, weighted toward business hours."""
    if day_range is None:
        day = random.randint(0, NUM_DAYS - 1)
    else:
        lo, hi = day_range
        day = random.randint(lo, hi)
    if random.random() < business_hours_bias:
        hour = random.randint(9, 18)
    else:
        hour = random.choice([6, 7, 8, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5])
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return WINDOW_START + datetime.timedelta(days=day, hours=hour, minutes=minute, seconds=second)


def pick_channel(amount, options):
    valid = [c for c in options if not (c == "RTGS" and amount < RTGS_MIN_AMOUNT)]
    if not valid:
        valid = ["IMPS"]
    return random.choice(valid)


def generate_name_variants(first, last, n):
    """
    Real banks store the same person multiple times, spelled differently.
    Produce up to n distinct spellings of one identity.
    """
    full = f"{first} {last}"
    candidates = [
        full,
        f"{first[0]}. {last}",
        full.upper(),
        f"{last} {first}",
        f"{full} & Sons",
    ]
    if len(last) > 3:
        idx = random.randint(1, len(last) - 2)
        misspelled = last[:idx] + last[idx + 1] + last[idx] + last[idx + 2:]
        candidates.append(f"{first} {misspelled}")
    if len(last) > 4:
        drop = random.randint(1, len(last) - 2)
        candidates.append(f"{first} {last[:drop] + last[drop + 1:]}")
    random.shuffle(candidates)
    uniq = []
    for c in candidates:
        if c not in uniq:
            uniq.append(c)
    while len(uniq) < n:
        uniq.append(full)
    return uniq[:max(n, 1)]


def make_entity():
    gender = random.choice(["M", "F"])
    first = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
    last = random.choice(LAST_NAMES)
    entity_id = f"ENT{len(entities) + 1:05d}"
    e = {
        "entity_id": entity_id,
        "first": first,
        "last": last,
        "phone": rand_phone(),
        "pan": rand_pan(),
        "address": rand_address(),
    }
    entities.append(e)
    entity_by_id[entity_id] = e
    return e


def create_account(owner_entity_id, account_type, bank, opened_days_ago=None, kyc_level=None):
    aid = next_account_id()
    if opened_days_ago is None:
        opened_days_ago = random.randint(60, 3650)
    if kyc_level is None:
        kyc_level = random.choices(["LOW", "MEDIUM", "HIGH"], weights=[15, 65, 20])[0]
    owner = entity_by_id[owner_entity_id]
    if account_type == "BUSINESS":
        name = f"{owner['last']} {random.choice(BUSINESS_WORDS)}"
    else:
        name = f"{owner['first']} {owner['last']}"
    acct = {
        "account_id": aid,
        "name": name,
        "account_type": account_type,
        "bank": bank,
        "opened_days_ago": opened_days_ago,
        "kyc_level": kyc_level,
        "owner_entity": owner_entity_id,
    }
    accounts.append(acct)
    accounts_by_id[aid] = acct
    return acct


def record_ring_txn(frm, to, amount, channel, ts, ring_id, ring_type):
    tid = next_txn_id()
    transactions.append({
        "txn_id": tid,
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "from_account": frm["account_id"],
        "to_account": to["account_id"],
        "amount": round(amount, 2),
        "channel": channel,
        "from_bank": frm["bank"],
        "to_bank": to["bank"],
    })
    ground_truth.append({"txn_id": tid, "ring_id": ring_id, "ring_type": ring_type})
    ring_account_ids.add(frm["account_id"])
    ring_account_ids.add(to["account_id"])
    ring_txn_counts[ring_id] += 1


def add_normal_txn(frm, to, amount, channel, ts):
    tid = next_txn_id()
    transactions.append({
        "txn_id": tid,
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "from_account": frm["account_id"],
        "to_account": to["account_id"],
        "amount": round(amount, 2),
        "channel": channel,
        "from_bank": frm["bank"],
        "to_bank": to["bank"],
    })


# =====================================================================
# RING OWNER BOOKKEEPING
#
# Each ring's accounts are deliberately owned by roughly HALF as many real
# people as there are accounts - the same launderer/mule-herder controls
# several accounts, which is exactly the pattern entity resolution should
# surface once name-spelling noise is stripped away.
# =====================================================================

_ring_owner_ptr = 0
ring_owner_entities = []  # populated in main()


def consume_owners(n):
    global _ring_owner_ptr
    ids = [e["entity_id"] for e in ring_owner_entities[_ring_owner_ptr:_ring_owner_ptr + n]]
    _ring_owner_ptr += n
    return ids


def cyclic_assign(owner_ids, n_accounts):
    """Spread n_accounts across owner_ids so every owner is used at least once."""
    assignments = [owner_ids[i % len(owner_ids)] for i in range(n_accounts)]
    random.shuffle(assignments)
    return assignments


# =====================================================================
# RING BUILDERS
# =====================================================================

def ring_bank_seq(size):
    """
    Bank assignment for a circular ring's accounts, in loop order.

    Every ring must have at least one hop that stays entirely inside BANK_A
    and at least one that stays entirely inside BANK_B - those two hops are
    each invisible to the other bank, which is exactly what makes cross-bank
    detection necessary. A naive strict A,B,A,B,... alternation fails this:
    every single hop crosses banks, so both banks individually see every
    transaction in the loop and neither is actually blind to anything.

    Positions 0,1 sit inside BANK_A (hop 0->1 is intra-A), positions 2,3 sit
    inside BANK_B (hop 2->3 is intra-B), and any remaining positions
    alternate. For size=6 this produces exactly
    A, A, B, B, A, B - the CIRC_6_HERO assignment.
    """
    seq = []
    for i in range(size):
        if i < 2:
            seq.append("BANK_A")
        elif i < 4:
            seq.append("BANK_B")
        else:
            seq.append("BANK_A" if i % 2 == 0 else "BANK_B")
    return seq


def build_circular_ring(ring_id, size, owners_count, subtle=False, hero=False):
    """
    A circular ring is suspicious because money that starts and ends at the
    same account, after hopping through a closed loop of other accounts, has
    no legitimate economic reason to travel in a circle - real commerce and
    payroll flow in straight lines (employer->employee, buyer->seller), not
    loops. Looping money is the classic layering signature.
    """
    owner_ids = consume_owners(owners_count)
    assignments = cyclic_assign(owner_ids, size)

    bank_seq = ring_bank_seq(size)

    accts = []
    for i in range(size):
        atype = "BUSINESS" if (hero and i % 3 == 0) else "PERSONAL"
        opened = random.randint(15, 120) if (hero or subtle) else random.randint(60, 2000)
        acc = create_account(assignments[i], atype, bank_seq[i], opened_days_ago=opened)
        accts.append(acc)

    if hero:
        # The hero ring: Rs 2.4 crore laundered through a 6-account loop in
        # ~4 hours, alternating banks - fast, large, and cross-bank, which
        # defeats single-bank transaction monitoring entirely.
        t = random_dt(day_range=(0, NUM_DAYS - 1), business_hours_bias=0.5)
        if t.hour > 19:
            t = t.replace(hour=random.randint(9, 15))
        amt = 24_000_000.0
        for i in range(size):
            frm, to = accts[i], accts[(i + 1) % size]
            ch = pick_channel(amt, ["RTGS"])
            record_ring_txn(frm, to, amt, ch, t, ring_id, "CIRCULAR")
            amt *= random.uniform(0.985, 0.998)
            t += datetime.timedelta(minutes=random.randint(25, 50))
    elif subtle:
        # The subtle ring deliberately uses small amounts and slow hops
        # spread over several days - it is built to hide beneath simple
        # "large amount" or "same-day loop" detection rules.
        t = random_dt(day_range=(0, NUM_DAYS - 6), business_hours_bias=0.8)
        amt = random.uniform(60000, 150000)
        for i in range(size):
            frm, to = accts[i], accts[(i + 1) % size]
            ch = pick_channel(amt, ["NEFT", "IMPS", "UPI"])
            record_ring_txn(frm, to, amt, ch, t, ring_id, "CIRCULAR")
            amt *= random.uniform(0.9, 0.98)
            t += datetime.timedelta(hours=random.randint(14, 48))
    else:
        t = random_dt(day_range=(0, NUM_DAYS - 2), business_hours_bias=0.65)
        amt = random.uniform(200000, 800000)
        for i in range(size):
            frm, to = accts[i], accts[(i + 1) % size]
            ch = pick_channel(amt, ["NEFT", "IMPS", "RTGS"])
            record_ring_txn(frm, to, amt, ch, t, ring_id, "CIRCULAR")
            amt *= random.uniform(0.97, 0.995)
            t += datetime.timedelta(hours=random.randint(1, 6))

    ring_meta.append((ring_id, "CIRCULAR", size, [a["account_id"] for a in accts]))
    ring_principals.append((ring_id, owner_ids[0]))
    return accts


def build_mule_network(ring_id, num_mules, owners_count):
    """
    One source account sprays money out to many "mule" accounts, and each
    mule immediately forwards it on to a single collector. This fan-out /
    fan-in shape is suspicious because the mules have no ongoing economic
    relationship with the source or the collector - they exist only to
    fragment one large transfer into many small, less-conspicuous ones
    before it re-consolidates.
    """
    owner_ids = consume_owners(owners_count)
    total_accounts = num_mules + 2
    assignments = cyclic_assign(owner_ids, total_accounts)
    idx = 0

    source = create_account(assignments[idx], "PERSONAL", random.choice(BANKS),
                             opened_days_ago=random.randint(10, 90))
    idx += 1
    mules = []
    for _ in range(num_mules):
        m = create_account(assignments[idx], "PERSONAL", random.choice(BANKS),
                            opened_days_ago=random.randint(5, 60))
        idx += 1
        mules.append(m)
    collector = create_account(assignments[idx], "BUSINESS", random.choice(BANKS),
                                opened_days_ago=random.randint(10, 90))

    spray_start = random_dt(day_range=(0, NUM_DAYS - 1), business_hours_bias=0.6)
    for m in mules:
        amt = random.uniform(15000, 90000)
        t1 = spray_start + datetime.timedelta(minutes=random.randint(0, 180))
        record_ring_txn(source, m, amt, pick_channel(amt, ["UPI", "IMPS"]), t1, ring_id, "MULE_NETWORK")
        t2 = t1 + datetime.timedelta(minutes=random.randint(2, 45))
        amt2 = amt * random.uniform(0.97, 0.995)
        record_ring_txn(m, collector, amt2, pick_channel(amt2, ["UPI", "IMPS"]), t2, ring_id, "MULE_NETWORK")

    accts = [source] + mules + [collector]
    ring_meta.append((ring_id, "MULE_NETWORK", len(accts), [a["account_id"] for a in accts]))
    ring_principals.append((ring_id, owner_ids[0]))
    return accts


def build_velocity_chain(ring_id, hops, owners_count):
    """
    Money passes through a straight line of accounts in under 90 minutes and
    rests nowhere - each account receives and immediately forwards nearly
    the full amount. Legitimate funds usually sit somewhere (a payroll
    account, a savings buffer); money that never rests is being deliberately
    kept moving to outrun same-day account monitoring.
    """
    owner_ids = consume_owners(owners_count)
    n_accounts = hops + 1
    assignments = cyclic_assign(owner_ids, n_accounts)
    accts = [
        create_account(assignments[i], "PERSONAL", random.choice(BANKS), opened_days_ago=random.randint(5, 90))
        for i in range(n_accounts)
    ]

    start = random_dt(day_range=(0, NUM_DAYS - 1), business_hours_bias=0.6)
    if start.hour > 21:
        start = start.replace(hour=random.randint(9, 18))
    amt = random.uniform(500000, 3000000)
    t = start
    per_hop_minutes = max(6, 80 // hops)
    for i in range(hops):
        frm, to = accts[i], accts[i + 1]
        ch = pick_channel(amt, ["IMPS", "RTGS"])
        record_ring_txn(frm, to, amt, ch, t, ring_id, "VELOCITY_CHAIN")
        amt *= random.uniform(0.98, 0.999)
        t += datetime.timedelta(minutes=random.randint(4, per_hop_minutes))

    ring_meta.append((ring_id, "VELOCITY_CHAIN", n_accounts, [a["account_id"] for a in accts]))
    ring_principals.append((ring_id, owner_ids[0]))
    return accts


def build_structuring_ring(ring_id, threshold, num_deposits, num_depositors, owners_count):
    """
    Many deposits land in one account, each sized just under a reporting
    threshold. Real transaction-reporting rules trigger scrutiny above a
    fixed cutoff, so structuring - splitting one large sum into many
    deposits that each stay just under the line - is a direct, deliberate
    attempt to stay invisible to that specific control.
    """
    owner_ids = consume_owners(owners_count)
    n_accounts = num_depositors + 1
    assignments = cyclic_assign(owner_ids, n_accounts)

    dest_bank = random.choice(BANKS)
    depositors = [
        create_account(assignments[i], "PERSONAL", dest_bank, opened_days_ago=random.randint(30, 500))
        for i in range(num_depositors)
    ]
    dest = create_account(assignments[-1], "BUSINESS", dest_bank, opened_days_ago=random.randint(60, 800))

    for _ in range(num_deposits):
        dep = random.choice(depositors)
        amt = random.uniform(threshold * 0.90, threshold * 0.995)
        t = random_dt(day_range=(0, NUM_DAYS - 1), business_hours_bias=0.7)
        record_ring_txn(dep, dest, amt, "CASH", t, ring_id, "STRUCTURING")

    accts = depositors + [dest]
    ring_meta.append((ring_id, "STRUCTURING", len(accts), [a["account_id"] for a in accts]))
    ring_principals.append((ring_id, owner_ids[0]))
    return accts


# =====================================================================
# CAMOUFLAGE
# =====================================================================

def add_camouflage_transactions():
    """
    Every ring account also makes a few small, ordinary transactions, so a
    detector cannot simply flag "accounts that only ever move ring money" -
    it has to separate the suspicious pattern from genuine background noise
    on the same account.
    """
    all_ids = [a["account_id"] for a in accounts]
    count = 0
    for aid in sorted(ring_account_ids):
        acct = accounts_by_id[aid]
        n = random.randint(2, 4)
        for _ in range(n):
            other_id = random.choice(all_ids)
            while other_id == aid:
                other_id = random.choice(all_ids)
            other = accounts_by_id[other_id]
            amt = round(random.uniform(200, 6000), 2)
            ch = random.choice(["UPI", "IMPS", "CASH"])
            ts = random_dt()
            if random.random() < 0.5:
                add_normal_txn(acct, other, amt, ch, ts)
            else:
                add_normal_txn(other, acct, amt, ch, ts)
            count += 1
    return count


# =====================================================================
# MAIN
# =====================================================================

def main():
    # ---- 1. Real people (entities) ----
    for _ in range(NUM_ENTITIES):
        make_entity()

    global ring_owner_entities
    ring_owner_entities = entities[:76]  # sum of owners_count across all 12 rings below
    normal_entities = entities[76:]

    # ---- 2. Build the 12 hidden rings (also creates their accounts) ----
    # Owner budget per ring (roughly half as many owners as accounts):
    #  circular 4/5/6/8 -> 2/3/3/4   mule 12/25/40 -> 7/14/21
    #  velocity 4/5/7   -> 3/3/4     structuring 10L/50k -> 6/6   (sum = 76)
    build_circular_ring("CIRC_4", size=4, owners_count=2)
    build_circular_ring("CIRC_5_SUBTLE", size=5, owners_count=3, subtle=True)
    build_circular_ring("CIRC_6_HERO", size=6, owners_count=3, hero=True)
    build_circular_ring("CIRC_8", size=8, owners_count=4)

    build_mule_network("MULE_12", num_mules=12, owners_count=7)
    build_mule_network("MULE_25", num_mules=25, owners_count=14)
    build_mule_network("MULE_40", num_mules=40, owners_count=21)

    build_velocity_chain("VELOCITY_4", hops=4, owners_count=3)
    build_velocity_chain("VELOCITY_5", hops=5, owners_count=3)
    build_velocity_chain("VELOCITY_7", hops=7, owners_count=4)

    build_structuring_ring("STRUCTURING_10L", threshold=1000000, num_deposits=30,
                            num_depositors=10, owners_count=6)
    build_structuring_ring("STRUCTURING_50K", threshold=50000, num_deposits=35,
                            num_depositors=10, owners_count=6)

    assert _ring_owner_ptr == len(ring_owner_entities), "ring owner budget mismatch"

    ring_txn_total = len(transactions)

    # ---- 3. Remaining ordinary accounts, owned by the remaining entities ----
    remaining_accounts_needed = NUM_ACCOUNTS - len(accounts)
    counts = {e["entity_id"]: 1 for e in normal_entities}
    extra_needed = remaining_accounts_needed - len(normal_entities)
    pool_ids = list(counts.keys())
    for _ in range(extra_needed):
        counts[random.choice(pool_ids)] += 1

    for oid, cnt in counts.items():
        for k in range(cnt):
            if cnt == 1:
                atype = "PERSONAL" if random.random() < 0.85 else "BUSINESS"
            else:
                atype = "PERSONAL" if k == 0 else "BUSINESS"
            create_account(oid, atype, random.choice(BANKS))

    assert len(accounts) == NUM_ACCOUNTS

    # ---- 4. Roles for normal traffic (employers / landlords / merchants / utilities) ----
    business_accounts = [a for a in accounts if a["account_type"] == "BUSINESS"
                          and a["account_id"] not in ring_account_ids]
    random.shuffle(business_accounts)
    n_biz = len(business_accounts)
    n_emp = max(20, n_biz // 6)
    n_land = max(15, n_biz // 8)
    n_merch = max(50, n_biz // 3)
    n_util = max(10, n_biz // 10)

    employers = business_accounts[:n_emp]
    landlords = business_accounts[n_emp:n_emp + n_land]
    merchants = business_accounts[n_emp + n_land:n_emp + n_land + n_merch]
    utilities = business_accounts[n_emp + n_land + n_merch:n_emp + n_land + n_merch + n_util]
    leftover = business_accounts[n_emp + n_land + n_merch + n_util:]
    merchants = merchants + leftover
    if not merchants:
        merchants = business_accounts[:1]
    if not utilities:
        utilities = business_accounts[:1]
    if not employers:
        employers = business_accounts[:1]
    if not landlords:
        landlords = business_accounts[:1]

    personal_accounts = [a for a in accounts if a["account_type"] == "PERSONAL"]
    personal_ids = [a["account_id"] for a in personal_accounts]

    # Each account gets a limited, repeating set of counterparties - real
    # people transact with the same handful of contacts, not everyone.
    partners = {}
    for a in personal_accounts:
        aid = a["account_id"]
        p = {}
        if random.random() < 0.7:
            p["employer"] = random.choice(employers)
        if random.random() < 0.4:
            p["landlord"] = random.choice(landlords)
        p["utilities"] = random.sample(utilities, k=min(len(utilities), random.randint(1, 3)))
        p["merchants"] = random.sample(merchants, k=min(len(merchants), random.randint(3, 8)))
        k = min(len(personal_ids) - 1, random.randint(3, 12))
        sample = random.sample(personal_ids, k + 1)
        if aid in sample:
            sample.remove(aid)
        p["peers"] = sample[:k]
        partners[aid] = p

    # ---- 5. Camouflage transactions for ring accounts ----
    camouflage_count = add_camouflage_transactions()

    # ---- 6. Fill the rest with ordinary traffic ----
    normal_budget = TARGET_TOTAL_TRANSACTIONS - ring_txn_total
    remaining = normal_budget - camouflage_count
    category_weights = {"salary": 6, "rent": 6, "bills": 16, "shopping": 40, "peer": 32}

    for _ in range(remaining):
        actor = random.choice(personal_accounts)
        aid = actor["account_id"]
        p = partners[aid]
        cats, weights = [], []
        if p.get("employer"):
            cats.append("salary"); weights.append(category_weights["salary"])
        if p.get("landlord"):
            cats.append("rent"); weights.append(category_weights["rent"])
        if p.get("utilities"):
            cats.append("bills"); weights.append(category_weights["bills"])
        if p.get("merchants"):
            cats.append("shopping"); weights.append(category_weights["shopping"])
        if p.get("peers"):
            cats.append("peer"); weights.append(category_weights["peer"])

        cat = random.choices(cats, weights=weights)[0]
        ts = random_dt()

        if cat == "salary":
            emp = p["employer"]
            amt = round(random.uniform(20000, 150000), 2)
            add_normal_txn(emp, actor, amt, random.choice(["NEFT", "IMPS"]), ts)
        elif cat == "rent":
            ll = p["landlord"]
            amt = round(random.uniform(8000, 45000), 2)
            add_normal_txn(actor, ll, amt, random.choice(["NEFT", "UPI"]), ts)
        elif cat == "bills":
            u = random.choice(p["utilities"])
            amt = round(random.uniform(300, 5000), 2)
            add_normal_txn(actor, u, amt, random.choice(["UPI", "NEFT"]), ts)
        elif cat == "shopping":
            m = random.choice(p["merchants"])
            amt = round(random.uniform(100, 15000), 2)
            add_normal_txn(actor, m, amt, random.choice(["UPI", "CASH", "IMPS"]), ts)
        else:  # peer
            peer_id = random.choice(p["peers"])
            peer_acc = accounts_by_id[peer_id]
            amt = round(random.uniform(100, 50000), 2)
            if random.random() < 0.5:
                add_normal_txn(actor, peer_acc, amt, random.choice(["UPI", "IMPS"]), ts)
            else:
                add_normal_txn(peer_acc, actor, amt, random.choice(["UPI", "IMPS"]), ts)

    # ---- 7. Customer identity records across three source systems ----
    #
    # One pass per ACCOUNT, not per owner. A bank issues its own KYC
    # paperwork whenever an account is opened, so a second or third account
    # held by the same person leaves its own separate trail too - looping
    # per owner let all of an owner's records pile onto just one of their
    # accounts, leaving the others with zero identity evidence: unrealistic
    # (no bank opens an account with no KYC on file) and unresolvable
    # downstream (nothing to match on). Looping per account guarantees every
    # account_id gets at least one linked customer_records row.
    owned_accounts_by_entity = defaultdict(list)
    for a in accounts:
        owned_accounts_by_entity[a["owner_entity"]].append(a["account_id"])

    ring_principal_ids = {eid for (_, eid) in ring_principals}
    # Each ring principal's bonus WATCHLIST row lands on their first (lowest)
    # ring account - deterministic, and unchanged from the original design.
    principal_watchlist_account = {
        eid: owned_accounts_by_entity[eid][0] for eid in ring_principal_ids
    }

    # Only two non-watchlist systems exist, so "1-3 records, each in a
    # different source system" tops out at 2 ordinary records per account;
    # a ring principal's designated account gets a 3rd, on WATCHLIST.
    ORDINARY_SOURCE_SYSTEMS = ["RETAIL_CBS", "CORPORATE_BANKING"]

    def draw_field(value, blank_rate):
        return value if random.random() > blank_rate else ""

    for acct in accounts:
        aid = acct["account_id"]
        eid = acct["owner_entity"]
        e = entity_by_id[eid]

        # Criminals give poor KYC: ring accounts run with a higher blank
        # rate than ordinary ones, but every account still gets >=1 record.
        blank_rate = 0.40 if aid in ring_account_ids else 0.25

        is_watchlist_account = principal_watchlist_account.get(eid) == aid
        num_records = random.randint(1, 2)
        variants = generate_name_variants(e["first"], e["last"],
                                           num_records + (1 if is_watchlist_account else 0))
        systems = ORDINARY_SOURCE_SYSTEMS[:] if num_records == 2 else [random.choice(ORDINARY_SOURCE_SYSTEMS)]

        account_records = []
        for i in range(num_records):
            account_records.append({
                "record_id": next_record_id(),
                "source_system": systems[i],
                "name_as_written": variants[i],
                "phone": draw_field(e["phone"], blank_rate),
                "pan": draw_field(e["pan"], blank_rate),
                "address": draw_field(e["address"], blank_rate),
                "linked_account": aid,
                "true_entity_id": eid,
            })

        if is_watchlist_account:
            account_records.append({
                "record_id": next_record_id(),
                "source_system": "WATCHLIST",
                "name_as_written": variants[-1],
                "phone": draw_field(e["phone"], blank_rate),
                "pan": draw_field(e["pan"], blank_rate),
                "address": draw_field(e["address"], blank_rate),
                "linked_account": aid,
                "true_entity_id": eid,
            })

        # Guarantee 1: no record may have phone, pan AND address all blank -
        # a KYC record with zero identifying fields does not exist in real
        # banking. If the random draw above produced one, restore a single
        # field (chosen at random) rather than re-drawing the whole record,
        # so the ~25%/40% blank rate elsewhere is barely disturbed.
        for rec in account_records:
            if not rec["phone"] and not rec["pan"] and not rec["address"]:
                field = random.choice(["phone", "pan", "address"])
                rec[field] = e[field]

        # Guarantee 2: every account needs at least one record with a STRONG
        # identifier (non-blank phone or PAN) - address alone is too weak to
        # anchor a match. If none of this account's records qualify, promote
        # one field (phone or pan) on one record rather than touching all of
        # them, again keeping the disturbance to the blank rate minimal.
        if not any(rec["phone"] or rec["pan"] for rec in account_records):
            rec = random.choice(account_records)
            field = random.choice(["phone", "pan"])
            rec[field] = e[field]

        customer_records.extend(account_records)

    # ---- Self-check: identity coverage guarantees ----
    records_per_account = Counter(r["linked_account"] for r in customer_records)
    missing = [a["account_id"] for a in accounts if records_per_account[a["account_id"]] == 0]
    assert not missing, f"{len(missing)} accounts have zero customer_records rows: {missing[:10]}"
    per_account_counts = [records_per_account[a["account_id"]] for a in accounts]
    print(f"Self-check: every account has >= 1 customer record "
          f"(min={min(per_account_counts)}, max={max(per_account_counts)}, "
          f"avg={sum(per_account_counts) / len(per_account_counts):.2f})")

    all_blank_records = [r for r in customer_records
                          if not r["phone"] and not r["pan"] and not r["address"]]
    assert not all_blank_records, (
        f"{len(all_blank_records)} customer_records rows have phone, pan AND "
        f"address all blank: {[r['record_id'] for r in all_blank_records[:10]]}"
    )
    print(f"Self-check: no customer record has phone/pan/address all blank "
          f"(0 of {len(customer_records)} violate this)")

    strong_records_per_account = Counter(
        r["linked_account"] for r in customer_records if r["phone"] or r["pan"]
    )
    accounts_without_strong_id = [
        a["account_id"] for a in accounts if strong_records_per_account[a["account_id"]] == 0
    ]
    assert not accounts_without_strong_id, (
        f"{len(accounts_without_strong_id)} accounts have no record with a "
        f"non-blank phone or pan: {accounts_without_strong_id[:10]}"
    )
    print(f"Self-check: every account has >= 1 record with a strong identifier "
          f"(non-blank phone or pan) - {len(accounts) - len(accounts_without_strong_id)} "
          f"of {len(accounts)} accounts confirmed")

    # ---- 8. Write CSVs ----
    def write_csv(filename, fieldnames, rows):
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    write_csv("transactions.csv",
              ["txn_id", "timestamp", "from_account", "to_account", "amount",
               "channel", "from_bank", "to_bank"],
              transactions)

    write_csv("accounts.csv",
              ["account_id", "name", "account_type", "bank", "opened_days_ago",
               "kyc_level", "owner_entity"],
              accounts)

    write_csv("customer_records.csv",
              ["record_id", "source_system", "name_as_written", "phone", "pan",
               "address", "linked_account", "true_entity_id"],
              customer_records)

    write_csv("ground_truth.csv", ["txn_id", "ring_id", "ring_type"], ground_truth)

    # ---- 9. Summary ----
    resolved_entities = len({a["owner_entity"] for a in accounts})
    total_txns = len(transactions)
    total_ring_txns = len(ground_truth)

    print("=" * 60)
    print("CHAKRAVYUH AI - synthetic dataset generated")
    print("=" * 60)
    print(f"Accounts:          {len(accounts):,}")
    print(f"Transactions:      {total_txns:,}")
    print(f"Customer records:  {len(customer_records):,}")
    print(f"Real entities:     {resolved_entities:,} (target ~1,800)")
    print(f"Ring transactions: {total_ring_txns:,} ({total_ring_txns / total_txns * 100:.3f}% of all transactions)")
    print("-" * 60)
    print(f"{'ring_id':<18}{'type':<16}{'size':<6}{'txns':<7}{'% of all txns'}")
    for ring_id, ring_type, size, acct_ids in ring_meta:
        n = ring_txn_counts[ring_id]
        pct = n / total_txns * 100
        print(f"{ring_id:<18}{ring_type:<16}{size:<6}{n:<7}{pct:.3f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
