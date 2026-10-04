#!/usr/bin/env python3
"""Ledgerline CLI — run the diagnostic on a real export before building any UI.

    python3 cli.py export.csv            free summary
    python3 cli.py export.csv --paid     every finding
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledgerline import analyze, free, paid
from ledgerline.parse import ParseError

def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    try:
        p, r = analyze(open(sys.argv[1], encoding="utf-8-sig").read())
    except ParseError as e:
        print(f"Could not read this file:\n  {e}"); return 2

    full = "--paid" in sys.argv
    print(f"\n{p.vendor} export · {len(p.legs)} legs · "
          f"{len(p.failed_rows)} unreadable rows")
    for n in r["notes"]:
        print(f"  note: {n}")

    f = free(r, p)
    print(f"\nHeadline impact on the gain column: ${f['headline_impact']}"
          + ("  (capped at the file total)" if f["headline_capped"] else ""))
    print("Counts:", ", ".join(f"{k}={v}" for k, v in sorted(f["counts"].items())) or "none")

    if f["showcase"]:
        s = f["showcase"]
        print(f"\nFREE FINDING ({f['showcase_kind']}) — {f['showcase_copy']}")
        for leg in s["legs"]:
            print(f"   row {leg['source_row']:>4}  {leg['date']}  "
                  f"{leg['direction']:<3} {leg['qty']:>14} {leg['asset']:<6} "
                  f"{leg['wallet']}")
        print(f"   impact ${s['impact']} ({s['impact_basis']})")
        print(f"   fix: {s['fix']}")
        print(f"\n   {f['locked']} more findings behind the paywall.")

    if full:
        print("\n--- all findings ---")
        for x in paid(r, p)["findings"]:
            flag = "" if x["counted"] else "  (context only, $0)"
            print(f"\n{x['kind']} [{x['confidence']}] rows {x['source_rows']} "
                  f"${x['impact']}{flag}")
            print(f"   {x['fix']}")
            if x["note"]: print(f"   note: {x['note']}")
        if p.failed_rows:
            print("\nunreadable rows:", p.failed_rows[:10])

    print(f"\n{f['footer']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
