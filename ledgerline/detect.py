"""
Ledgerline — detectors.

Order matters. Pairs and mid-stream breaks are the findings a spreadsheet
cannot produce; zero-cost and duplicates are subordinate and mostly exist
so the paid list is complete.

Every rule here is written to avoid one specific failure: telling someone
to delete a real taxable event. A sale on one exchange followed by a buy
on another looks like a self-transfer and is not one.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from .models import Leg, Finding, IN, OUT, ZERO

PAIR_WINDOW_S = 36 * 3600
DUP_WINDOW_S = 120
# A self-transfer loses the network fee: an absolute dust amount, not a
# percentage. 1% of 10 ETH is 0.1 ETH, which is not a fee, it is a trade.
DUST = {"BTC": Decimal("0.01"), "ETH": Decimal("0.05")}
DUST_DEFAULT = Decimal("1")
STABLES = {"USDC", "USDT", "DAI", "BUSD", "TUSD"}


def _dust(asset: str) -> Decimal:
    if asset in STABLES:
        return Decimal("5")
    return DUST.get(asset, DUST_DEFAULT)


# ---------------------------------------------------------------- A pairs
def transfer_pairs(legs) -> list:
    """Hash-proven pairs are the headline. Timing guesses are counts only."""
    out, used = [], set()

    by_hash = defaultdict(list)
    for l in legs:
        if l.tx_hash:
            by_hash[l.tx_hash].append(l)

    for h, group in by_hash.items():
        outs = [l for l in group if l.direction == OUT]
        ins = [l for l in group if l.direction == IN]
        for o in outs:
            for i in ins:
                if i.asset != o.asset or id(i) in used or id(o) in used:
                    continue
                # a trade is one row split into two legs — same row, not a transfer
                if i.source_row == o.source_row:
                    continue
                # if both sides carry a wallet and they match, it is not a move
                if o.wallet and i.wallet and o.wallet == i.wallet:
                    continue
                used.add(id(o)); used.add(id(i))
                imp, basis = o.impact
                out.append(Finding(
                    kind="pair", confidence="high", legs=[o, i],
                    impact=imp, impact_basis=basis,
                    # Describe what the rows are. Do not instruct the user
                    # how to treat a transaction for tax purposes.
                    fix=("These two rows share a transaction hash, so the "
                         "export has recorded one movement as both a disposal "
                         "and an acquisition. In most tools a transfer label "
                         "is what carries cost basis across a move between "
                         "your own wallets. Confirm the wallets are yours."),
                ))
                break

    # heuristic, only where BOTH hashes are blank
    cand = [l for l in legs if not l.tx_hash and id(l) not in used]
    outs = sorted([l for l in cand if l.direction == OUT], key=lambda l: l.ts)
    ins = sorted([l for l in cand if l.direction == IN], key=lambda l: l.ts)
    for o in outs:
        if id(o) in used:
            continue
        for i in ins:
            if id(i) in used or i.asset != o.asset:
                continue
            if not (0 <= i.ts - o.ts <= PAIR_WINDOW_S):
                continue
            if o.wallet and i.wallet and o.wallet == i.wallet:
                continue
            if not (o.wallet or i.wallet):
                continue                       # no labels, no inference
            # a deposit LARGER than the withdrawal is not a transfer
            if i.qty > o.qty:
                continue
            if (o.qty - i.qty) > _dust(o.asset):
                continue
            used.add(id(o)); used.add(id(i))
            out.append(Finding(
                kind="pair", confidence="low", legs=[o, i],
                impact=ZERO, impact_basis="none",
                fix=("These two rows look related — same asset, within 36 "
                     "hours, and the deposit is smaller by about a fee. "
                     "Confirm they are the same movement before changing "
                     "anything. Do not reclassify on this alone."),
                note="timing guess, not proven",
            ))
            break
    return out


# ------------------------------------------------------- B negative balance
def balance_breaks(legs, has_wallets: bool) -> list:
    """Opening gap: never positive, first disposal goes negative. Everyone
    with a partial import has this; it is a count, not a diagnosis.
    Mid-stream break: was positive, then went below zero. That is a missing
    inbound and it is the finding."""
    if not has_wallets:
        return []
    out = []
    buckets = defaultdict(list)
    for l in legs:
        if l.wallet:
            buckets[(l.asset, l.wallet)].append(l)

    for (asset, wallet), group in buckets.items():
        group.sort(key=lambda l: (l.ts, l.source_row))
        bal, ever_positive, broke = ZERO, False, None
        for l in group:
            bal += l.signed
            if bal > 0:
                ever_positive = True
            if bal < 0 and broke is None:
                broke = l
                break
        if broke is None:
            continue

        after = [l for l in group
                 if l.ts >= broke.ts and l.direction == OUT and l.impact[0] != ZERO]
        imp = sum((l.impact[0] for l in after), ZERO)
        basis = after[0].impact[1] if after else "none"

        if ever_positive:
            out.append(Finding(
                kind="mid_break", confidence="high", legs=[broke] + after,
                impact=imp, impact_basis=basis,
                fix=(f"{wallet} held {asset}, then this row drives the balance "
                     "below zero. An incoming transfer is missing from an "
                     "otherwise complete record. Import the source wallet "
                     "before editing any cost downstream."),
            ))
        else:
            out.append(Finding(
                kind="opening_gap", confidence="high", legs=[broke],
                impact=ZERO, impact_basis="none",
                fix=(f"This is the first {asset} disposal in {wallet} and there "
                     "is no earlier history in this file. Import the prior "
                     "year if you have it."),
                note="opening gap — expected on a partial import",
            ))
    return out


# ------------------------------------------------------------ C zero cost
def zero_cost(legs) -> list:
    """A disposal with no cost. Income is excluded: an airdrop legitimately
    has zero basis, and flagging it is how the first spot-check fails.

    A SALE of a token the file shows arriving as income is the same trap one
    step removed — it is downgraded, not hidden."""
    income_assets = {l.asset for l in legs if l.is_income and l.direction == IN}
    out = []
    for l in legs:
        if l.direction != OUT or l.is_income:
            continue
        if l.proceeds is None or l.proceeds <= 0:
            continue
        if l.cost is not None and l.cost > 0:
            continue
        imp, basis = l.impact
        if l.asset in income_assets:
            out.append(Finding(
                kind="zero_cost", confidence="low", legs=[l], impact=ZERO,
                impact_basis="none",
                fix=(f"This sells {l.asset}, which arrives in this file as "
                     "income. A zero cost may be correct if it was received "
                     "at no value. Check the receipt row before changing it."),
                note="asset was received as income — may be correct"))
            continue
        out.append(Finding(
            kind="zero_cost", confidence="high", legs=[l],
            impact=imp, impact_basis=basis,
            fix=("This disposal has no purchase in the file, so the whole "
                 "proceeds became gain. Import the wallet or year that holds "
                 "the acquisition. Do not type in a cost you cannot support."),
        ))
    return out


# ------------------------------------------------------------ D duplicates
def duplicates(legs, has_vendor_id: bool, has_hash: bool) -> tuple:
    """A duplicated import has a DIFFERENT vendor id on each copy — the id is
    per row, not per movement. So the id can only prove two rows are the
    same row; it can never prove they are duplicates. The key is the hash."""
    if not has_hash:
        return [], ("Duplicate detection skipped: this export has no "
                    "transaction hash to key on.")
    out, seen = [], {}
    for l in sorted(legs, key=lambda l: (l.ts, l.source_row)):
        if l.direction != OUT or not l.tx_hash:
            continue
        key = (l.tx_hash, l.asset, str(l.qty))
        prev = seen.get(key)
        if prev is None:
            seen[key] = l
            continue
        if prev.source_row == l.source_row:
            continue
        if l.vendor_id and prev.vendor_id and l.vendor_id == prev.vendor_id:
            continue                       # same row seen twice, not a dup
        if abs(l.ts - prev.ts) > DUP_WINDOW_S:
            continue
        imp, basis = l.impact
        out.append(Finding(
            kind="duplicate", confidence="high", legs=[prev, l],
            impact=imp, impact_basis=basis,          # the extra row only
            fix=("Two rows describe the same movement. Delete one — keep "
                 "either the API sync or the CSV import, not both."),
        ))
    return out, None


# -------------------------------------------------------------- assignment
PRIORITY = ["pair", "mid_break", "zero_cost", "duplicate", "opening_gap"]


def assign(findings, total_gain=None) -> dict:
    """A source row's gain lands on exactly one finding. Lower-priority
    findings keep the row as context and contribute $0, so the headline can
    never sum the same disposal twice."""
    findings.sort(key=lambda f: (PRIORITY.index(f.kind), -abs(f.impact)))
    claimed, headline = set(), ZERO
    for f in findings:
        rows = {l.source_row for l in f.legs if l.direction == OUT}
        if rows & claimed:
            f.counted = False
            f.impact = ZERO
            f.impact_basis = "none"
        else:
            claimed |= rows
            if f.confidence == "high" and f.kind != "opening_gap":
                headline += f.impact
    # the headline can never exceed the report the user is looking at
    capped = False
    if total_gain is not None and total_gain > 0 and headline > total_gain:
        headline, capped = total_gain, True
    return {"findings": findings, "headline": headline, "capped": capped}


def run_all(parsed) -> dict:
    f = []
    f += transfer_pairs(parsed.legs)
    f += balance_breaks(parsed.legs, parsed.has_wallets)
    f += zero_cost(parsed.legs)
    d, note = duplicates(parsed.legs, parsed.has_vendor_id, parsed.has_hash)
    f += d
    res = assign(f, parsed.total_gain)
    res["notes"] = list(parsed.notes) + ([note] if note else [])
    return res
