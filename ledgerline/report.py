"""
Ledgerline — free and paid output.

The free page gives away ONE finding in full so the user can check it in
Koinly before paying. Everything else is a count. Nothing here ever says
the user owes less tax.
"""
from __future__ import annotations
from decimal import Decimal
from .models import ZERO
from .privacy import short_hash, scrub

FOOTER = ("These are inconsistencies in the export, not a recomputed return. "
          "Ledgerline is not a tax preparer and this is not tax advice. "
          "Your preparer decides what is reportable.")


def _row(l):
    """Row number, date and amount are what a user needs to find the line in
    their own tool. A full transaction hash is not — it resolves to a public
    address, so only a prefix leaves this function."""
    return {"source_row": l.source_row, "date": l.datetime_raw,
            "direction": l.direction, "asset": l.asset, "qty": str(l.qty),
            "wallet": scrub(l.wallet) or "(no label)",
            "tx_hash_short": short_hash(l.tx_hash)}


def _finding(f):
    return {"kind": f.kind, "confidence": f.confidence,
            "impact": str(f.impact), "impact_basis": f.impact_basis,
            "counted": f.counted, "fix": f.fix, "note": f.note,
            "legs": [_row(l) for l in f.legs[:2]],
            "source_rows": f.source_rows}


def free(result, parsed):
    """One proven finding in full, plus counts. Prefer a hash pair; fall
    back to a mid-stream break and say which it is."""
    fs = result["findings"]
    counts = {}
    for f in fs:
        k = f.kind if f.confidence == "high" else f.kind + "_guess"
        counts[k] = counts.get(k, 0) + 1

    pairs = [f for f in fs if f.kind == "pair" and f.confidence == "high"]
    breaks = [f for f in fs if f.kind == "mid_break"]
    showcase, kind = None, None
    if pairs:
        showcase, kind = max(pairs, key=lambda f: abs(f.impact)), "pair"
    elif breaks:
        showcase, kind = max(breaks, key=lambda f: abs(f.impact)), "mid_break"

    out = {
        "vendor": parsed.vendor,
        "has_money": parsed.has_money,
        "headline_impact": str(result["headline"]),
        "headline_capped": result["capped"],
        "counts": counts,
        "locked": max(0, len(fs) - (1 if showcase else 0)),
        "notes": result["notes"],
        "footer": FOOTER,
        "showcase": None,
    }
    if showcase:
        out["showcase"] = _finding(showcase)
        out["showcase_kind"] = kind
        out["showcase_copy"] = (
            "This withdrawal and this deposit share a transaction hash."
            if kind == "pair" else
            "This wallet held the asset, then went negative here — a missing "
            "inbound, not a proven transfer.")
    return out


def paid(result, parsed):
    return {"vendor": parsed.vendor,
            "headline_impact": str(result["headline"]),
            "headline_capped": result["capped"],
            "findings": [_finding(f) for f in result["findings"]],
            "failed_rows": parsed.failed_rows,
            "notes": result["notes"],
            "footer": FOOTER}
