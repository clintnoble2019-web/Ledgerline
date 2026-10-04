"""
Ledgerline — parsers.

Two adapters, one output shape. Unknown headers fail the upload.

IMPORTANT, verify against real fixtures before trusting these maps:
a vendor's *transaction history* export and its *capital gains* export are
different files. The history has wallets, hashes and transfers but often
NO gain column. The gains report has gain but only disposals, no transfers.

This parser reads the history and takes money columns if they are present.
When no money column exists, findings are still produced — with counts and
no dollars — and `has_money` is False so the caller can say so plainly
instead of printing $0 and looking broken.
"""
from __future__ import annotations
import csv, io, re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from .models import Leg, ParseResult, ParseError, IN, OUT, TRADE, FEE, OTHER

# --- column maps -------------------------------------------------------
# Keys are our names; values are candidate vendor headers, lowercased.
KOINLY = {
    "date":      ["date", "date (utc)"],
    "sent_qty":  ["sent amount"],
    "sent_cur":  ["sent currency"],
    "recv_qty":  ["received amount"],
    "recv_cur":  ["received currency"],
    "fee_qty":   ["fee amount"],
    "fee_cur":   ["fee currency"],
    "from":      ["sending wallet", "from wallet", "from"],
    "to":        ["receiving wallet", "to wallet", "to"],
    "label":     ["label", "type"],
    "hash":      ["txhash", "tx hash", "transaction hash"],
    "id":        ["id", "koinly id"],
    "gain":      ["gain", "gain (usd)", "pnl"],
    "proceeds":  ["proceeds", "net worth amount", "net worth value (usd)"],
    "cost":      ["cost basis", "cost", "cost basis (usd)"],
}
COINTRACKER = {
    "date":      ["date"],
    "sent_qty":  ["sent quantity"],
    "sent_cur":  ["sent asset", "sent currency"],
    "recv_qty":  ["received quantity"],
    "recv_cur":  ["received asset", "received currency"],
    "fee_qty":   ["fee amount"],
    "fee_cur":   ["fee currency"],
    "from":      ["sent wallet", "from"],
    "to":        ["received wallet", "to"],
    "label":     ["tag", "type"],
    "hash":      ["transaction hash", "txhash"],
    "id":        ["id"],
    "gain":      ["gain", "gain/loss", "capital gain"],
    "proceeds":  ["proceeds"],
    "cost":      ["cost basis"],
}
VENDORS = {"koinly": KOINLY, "cointracker": COINTRACKER}

# vendor label -> our row type
TYPE_MAP = {
    "": OTHER, "trade": TRADE, "exchange": TRADE, "swap": TRADE,
    "deposit": IN, "withdrawal": OUT, "transfer": "transfer",
    "send": OUT, "receive": IN, "buy": TRADE, "sell": TRADE,
    "fee": FEE, "cost": FEE,
    "reward": "reward", "rewards": "reward", "staking": "staking",
    "staking reward": "staking", "interest": "interest", "airdrop": "airdrop",
    "mining": "mining", "income": "income", "gift received": "gift_received",
    "fork": "fork", "cashback": "cashback",
}


def _dec(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "n/a", "na", "null", "none"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _ts(s: str) -> float:
    s = (s or "").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
              "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc).timestamp()
    raise ParseError(f"unparseable date: {s!r}")


def detect_vendor(headers) -> str:
    h = {x.strip().lower() for x in headers}
    if {"sent amount", "received amount"} & h:
        return "koinly"
    if {"sent quantity", "received quantity"} & h:
        return "cointracker"
    raise ParseError(
        "Unrecognised export format. Expected a Koinly or CoinTracker "
        "transaction history CSV. Columns found: " + ", ".join(sorted(h))
    )


def _resolve(headers, vmap) -> dict:
    """our name -> actual header. Missing optional columns are simply absent."""
    low = {x.strip().lower(): x for x in headers}
    out = {}
    for key, cands in vmap.items():
        for c in cands:
            if c in low:
                out[key] = low[c]
                break
    for required in ("date",):
        if required not in out:
            raise ParseError(f"missing required column: {required}")
    if not ({"sent_qty", "recv_qty"} & set(out)):
        raise ParseError("no sent/received quantity columns found")
    return out


def parse(text: str) -> ParseResult:
    rdr = csv.DictReader(io.StringIO(text))
    if not rdr.fieldnames:
        raise ParseError("empty file")
    vendor = detect_vendor(rdr.fieldnames)
    cols = _resolve(rdr.fieldnames, VENDORS[vendor])
    res = ParseResult(vendor=vendor)
    res.has_hash = "hash" in cols
    res.has_vendor_id = "id" in cols
    res.has_wallets = "from" in cols or "to" in cols
    res.has_money = bool({"gain", "proceeds"} & set(cols))
    total_gain = Decimal("0")
    saw_gain = False

    g = lambda r, k: (r.get(cols[k]) if k in cols else None)

    for i, row in enumerate(rdr, start=2):          # line 1 is the header
        try:
            ts = _ts(g(row, "date"))
        except ParseError as e:
            res.failed_rows.append((i, str(e)))
            continue

        label = (g(row, "label") or "").strip().lower()
        rtype = TYPE_MAP.get(label, OTHER if label == "" else label)
        hsh = (g(row, "hash") or "").strip()
        vid = (g(row, "id") or "").strip()
        wfrom = (g(row, "from") or "").strip()
        wto = (g(row, "to") or "").strip()
        sq, sc = _dec(g(row, "sent_qty")), (g(row, "sent_cur") or "").strip()
        rq, rc = _dec(g(row, "recv_qty")), (g(row, "recv_cur") or "").strip()
        gain, proceeds, cost = _dec(g(row, "gain")), _dec(g(row, "proceeds")), _dec(g(row, "cost"))
        if gain is not None:
            total_gain += gain
            saw_gain = True

        has_out = sq is not None and sq > 0 and sc
        has_in = rq is not None and rq > 0 and rc

        # a trade claims two assets; one missing side is a broken row, not
        # an excuse to invent the other leg
        # only a crypto-to-crypto trade must have two assets. A sell to
        # fiat has one side and its proceeds live in the money columns.
        if (sq or rq) and label in ("trade", "exchange", "swap"):
            if not (has_out and has_in):
                res.failed_rows.append((i, "trade row missing one asset"))
                continue

        mk = lambda d, a, q, w, money: Leg(
            source_row=i, datetime_raw=(g(row, "date") or ""), ts=ts, direction=d,
            asset=a.upper(), qty=q, wallet=w, row_type=rtype, tx_hash=hsh,
            vendor_id=vid, label_raw=label,
            proceeds=proceeds if money else None,
            cost=cost if money else None,
            gain=gain if money else None,
        )
        # money stays on the OUT leg. An in-leg carrying gain would let one
        # disposal inflate two findings.
        if has_out:
            res.legs.append(mk(OUT, sc, sq, wfrom, True))
        if has_in:
            res.legs.append(mk(IN, rc, rq, wto, False))
        if not has_out and not has_in:
            res.failed_rows.append((i, "no quantity on either side"))

    res.total_gain = total_gain if saw_gain else None
    if not res.has_money:
        res.notes.append(
            "This export has no gain or proceeds column, so findings are "
            "counts only. Upload the capital gains report for dollars.")
    if not res.has_wallets:
        res.notes.append(
            "This export has no wallet labels. Per-wallet balance checks are "
            "skipped; hash-proven pairs still work.")
    return res
