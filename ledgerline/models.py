"""
Ledgerline — data model.

One CSV row becomes one or two LEGS. Every detector consumes legs, never
raw rows, so a trade (one row, two assets) can never be half-counted.

Quantities and dollars are Decimal. Never float: a 1e-18 token rounding
error turns a matched transfer into an unmatched one.

Blank stays blank. A missing cost is None, not 0 — the whole product
turns on the difference between "no cost recorded" and "cost was zero".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

ZERO = Decimal("0")

# Row types after normalisation
IN, OUT, TRADE, TRANSFER, FEE, OTHER = "in", "out", "trade", "transfer", "fee", "other"

# Types whose zero cost basis is CORRECT, not an error. Flagging these is
# how the user's first spot-check fails and they stop trusting the tool.
INCOME_TYPES = {
    "income", "reward", "rewards", "airdrop", "interest", "staking",
    "staking_reward", "mining", "gift_received", "fork", "cashback",
}


@dataclass
class Leg:
    """One side of one movement."""
    source_row: int                 # CSV line the user sees in the export
    datetime_raw: str
    ts: float                       # epoch seconds, for ordering only
    direction: str                  # IN or OUT
    asset: str
    qty: Decimal                    # always positive; direction carries sign
    wallet: str = ""                # "" when the export has no label
    row_type: str = OTHER           # normalised vendor label
    tx_hash: str = ""
    vendor_id: str = ""
    # vendor money columns — only ever on an OUT leg of a disposal
    proceeds: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    gain: Optional[Decimal] = None
    label_raw: str = ""

    @property
    def signed(self) -> Decimal:
        return self.qty if self.direction == IN else -self.qty

    @property
    def is_income(self) -> bool:
        return self.row_type in INCOME_TYPES

    @property
    def impact(self) -> tuple[Decimal, str]:
        """Dollars this leg contributes, and which column it came from.
        Gain is preferred. Proceeds is the fallback and is labelled, because
        proceeds overstates impact wherever a real cost exists."""
        if self.gain is not None:
            return self.gain, "gain"
        if self.proceeds is not None:
            return self.proceeds, "proceeds-not-gain"
        return ZERO, "none"


@dataclass
class Finding:
    kind: str                       # pair | mid_break | opening_gap | zero_cost | duplicate
    confidence: str                 # high | low
    legs: list                      # Leg objects involved
    impact: Decimal = ZERO
    impact_basis: str = "none"      # gain | proceeds-not-gain | none
    fix: str = ""
    note: str = ""
    counted: bool = True            # False once another finding claimed the dollars

    @property
    def source_rows(self) -> list:
        return sorted({l.source_row for l in self.legs})


@dataclass
class ParseResult:
    legs: list = field(default_factory=list)
    vendor: str = ""
    total_gain: Optional[Decimal] = None   # file's own gain total, for the cap
    has_hash: bool = False
    has_vendor_id: bool = False
    has_wallets: bool = False
    has_money: bool = False                # any gain/proceeds column at all
    failed_rows: list = field(default_factory=list)
    notes: list = field(default_factory=list)


class ParseError(Exception):
    """Raised on unknown headers. A silent remap is worse than a hard fail —
    a mis-mapped gain column produces confident wrong dollars."""
