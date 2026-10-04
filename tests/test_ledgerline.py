import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from decimal import Decimal
from ledgerline import analyze, free, paid, process, scrub, short_hash, RETENTION_DAYS, purge_sql
from ledgerline.parse import parse, ParseError

H = ("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
     "Sending Wallet,Receiving Wallet,Label,TxHash,Gain,Proceeds,Cost Basis,Koinly ID")
def csv(*rows): return "\n".join([H, *rows])
def kinds(r): return [(f.kind, f.confidence) for f in r["findings"]]
def of(r, kind): return [f for f in r["findings"] if f.kind == kind]

# ---------- the Done Means list ----------

def test_sale_then_buy_elsewhere_is_not_a_transfer():
    """The dangerous false positive: two real disposals must not be
    collapsed into one self-transfer."""
    _, r = analyze(csv(
        "2026-02-01 09:00:00,1.0,ETH,,,Coinbase,,sell,,3200,3200,0,a1",
        "2026-02-01 20:00:00,,,1.004,ETH,,Kraken,buy,,,,,a2"))
    assert not of(r, "pair"), "a larger deposit must never pair"

def test_hash_pair_is_high_confidence():
    _, r = analyze(csv(
        "2026-02-01 09:00:00,1.0,ETH,,,Coinbase,Ledger,withdrawal,0xaaa,3200,3200,0,b1",
        "2026-02-01 09:30:00,,,0.998,ETH,Coinbase,Ledger,deposit,0xaaa,,,,b2"))
    p = of(r, "pair")
    assert len(p) == 1 and p[0].confidence == "high"
    assert p[0].impact == Decimal("3200")
    assert "share a transaction hash" in p[0].fix

def test_timing_guess_never_says_reclassify():
    _, r = analyze(csv(
        "2026-04-02 08:00:00,3.0,SOL,,,Phantom,Kraken,withdrawal,,2100,2100,0,c1",
        "2026-04-02 15:00:00,,,2.99,SOL,Phantom,Kraken,deposit,,,,,c2"))
    p = of(r, "pair")
    assert len(p) == 1 and p[0].confidence == "low"
    assert p[0].impact == 0, "a guess contributes no dollars"
    assert "Confirm" in p[0].fix and "self-transfer" not in p[0].fix.lower()

def test_opening_gap_is_not_the_headline():
    _, r = analyze(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,d1"))
    g = of(r, "opening_gap")
    assert g and g[0].impact == 0
    assert "no earlier history" in g[0].fix

def test_mid_stream_break_is_the_finding():
    _, r = analyze(csv(
        "2026-01-05 10:00:00,,,2.0,ETH,,Coinbase,deposit,,,,,e1",
        "2026-06-15 10:00:00,3.0,ETH,,,Coinbase,,sell,0xfff,7400,7400,0,e2"))
    b = of(r, "mid_break")
    assert b and b[0].impact == Decimal("7400")
    assert "missing from an otherwise complete record" in b[0].fix
    assert not of(r, "opening_gap")

def test_airdrop_is_not_a_zero_cost_error():
    _, r = analyze(csv(
        "2026-05-01 11:00:00,,,500,ARB,,Ledger,airdrop,,,,,f1"))
    assert not of(r, "zero_cost")

def test_selling_an_income_asset_is_downgraded():
    _, r = analyze(csv(
        "2026-05-01 11:00:00,,,500,ARB,,Ledger,airdrop,,,,,g1",
        "2026-05-20 11:00:00,500,ARB,,,Ledger,,sell,0xccc,640,640,0,g2"))
    z = of(r, "zero_cost")
    assert z and z[0].confidence == "low" and z[0].impact == 0

def test_duplicate_keys_on_hash_not_vendor_id():
    """Duplicated imports carry DIFFERENT ids, so the id can never find them."""
    _, r = analyze(csv(
        "2026-07-01 10:00:00,0.2,ETH,,,Ledger,,sell,0xeee,800,800,120,h1",
        "2026-07-01 10:00:30,0.2,ETH,,,Ledger,,sell,0xeee,800,800,120,h2"))
    d = of(r, "duplicate")
    assert len(d) == 1 and d[0].impact == Decimal("800")

def test_no_row_is_counted_twice():
    p, r = analyze(open(os.path.join(os.path.dirname(__file__),
                   "fixtures/koinly_sample.csv")).read())
    seen = set()
    for f in r["findings"]:
        if not f.counted or f.impact == 0: continue
        rows = {l.source_row for l in f.legs if l.direction == "out"}
        assert not (rows & seen), f"{f.kind} re-counted {rows & seen}"
        seen |= rows

def test_headline_cannot_exceed_the_file_total():
    p, r = analyze(open(os.path.join(os.path.dirname(__file__),
                   "fixtures/koinly_sample.csv")).read())
    assert r["headline"] <= p.total_gain

def test_free_page_shows_one_checkable_finding():
    p, r = analyze(open(os.path.join(os.path.dirname(__file__),
                   "fixtures/koinly_sample.csv")).read())
    f = free(r, p)
    assert f["showcase"] and f["showcase_kind"] == "pair"
    assert len(f["showcase"]["legs"]) == 2
    assert f["locked"] == len(r["findings"]) - 1
    assert "owe" not in f["footer"].lower()

def test_free_falls_back_to_a_break_and_says_so():
    p, r = analyze(csv(
        "2026-01-05 10:00:00,,,2.0,ETH,,Coinbase,deposit,,,,,i1",
        "2026-06-15 10:00:00,3.0,ETH,,,Coinbase,,sell,,7400,7400,0,i2"))
    f = free(r, p)
    assert f["showcase_kind"] == "mid_break"
    assert "not a proven transfer" in f["showcase_copy"]

def test_never_claims_tax_saved():
    p, r = analyze(open(os.path.join(os.path.dirname(__file__),
                   "fixtures/koinly_sample.csv")).read())
    blob = (str(free(r, p)) + str(paid(r, p))).lower()
    for phrase in ("owe less", "saves you", "tax saved", "refund"):
        assert phrase not in blob

# ---------- parser ----------

def test_unknown_headers_fail_loud():
    try:
        parse("Foo,Bar\n1,2"); assert False
    except ParseError as e:
        assert "Unrecognised export format" in str(e)

def test_trade_splits_into_two_legs_with_gain_on_the_out_leg():
    p, _ = analyze(csv(
        "2026-03-10 12:00:00,0.5,ETH,1800,USDC,Ledger,Ledger,trade,0xbbb,900,1800,900,j1"))
    assert len(p.legs) == 2
    out = [l for l in p.legs if l.direction == "out"][0]
    inn = [l for l in p.legs if l.direction == "in"][0]
    assert out.gain == Decimal("900") and inn.gain is None
    assert out.source_row == inn.source_row

def test_half_a_trade_fails_the_row_rather_than_inventing_a_leg():
    p, _ = analyze(csv(
        "2026-03-10 12:00:00,0.5,ETH,,,Ledger,Ledger,trade,0xbbb,900,1800,900,k1"))
    assert p.legs == [] and p.failed_rows and "missing one asset" in p.failed_rows[0][1]

def test_sell_to_fiat_is_one_leg_not_a_broken_trade():
    p, _ = analyze(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,l1"))
    assert len(p.legs) == 1 and not p.failed_rows

def test_blank_cost_stays_none_not_zero():
    p, _ = analyze(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,,m1"))
    assert p.legs[0].cost is None

def test_no_wallet_labels_skips_the_walk_and_says_so():
    txt = ("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
           "Label,TxHash,Gain,Proceeds,Cost Basis\n"
           "2026-06-01 10:00:00,1.0,BTC,,,sell,0xddd,41000,41000,0")
    p, r = analyze(txt)
    assert not p.has_wallets and not of(r, "mid_break")
    assert any("wallet labels" in n for n in r["notes"])

def test_no_money_column_reports_counts_only():
    txt = ("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
           "Sending Wallet,Receiving Wallet,Label,TxHash\n"
           "2026-02-01 09:00:00,1.0,ETH,,,Coinbase,Ledger,withdrawal,0xaaa\n"
           "2026-02-01 09:30:00,,,0.998,ETH,Coinbase,Ledger,deposit,0xaaa")
    p, r = analyze(txt)
    assert not p.has_money and of(r, "pair")
    assert r["headline"] == 0
    assert any("no gain or proceeds column" in n for n in r["notes"])

def test_cointracker_format_parses():
    txt = ("Date,Sent Quantity,Sent Asset,Received Quantity,Received Asset,"
           "Sent Wallet,Received Wallet,Tag,Transaction Hash\n"
           "2026-02-01 09:00:00,1.0,ETH,,,Coinbase,Ledger,withdrawal,0xaaa\n"
           "2026-02-01 09:30:00,,,0.998,ETH,Coinbase,Ledger,deposit,0xaaa")
    p, r = analyze(txt)
    assert p.vendor == "cointracker" and of(r, "pair")

def test_decimals_never_become_floats():
    p, _ = analyze(csv(
        "2026-06-01 10:00:00,0.000000000000000001,ETH,,,V,,sell,0x1,1,1,0,n1"))
    assert str(p.legs[0].qty) == "1E-18"

# ---------- privacy and compliance ----------

def test_process_returns_no_raw_hash_anywhere():
    """A full tx hash resolves to a public address. It must not survive."""
    f, pd = process(csv(
        "2026-02-01 09:00:00,1.0,ETH,,,Coinbase,Ledger,withdrawal,"
        "0xabcdef0123456789abcdef0123456789abcdef01,3200,3200,0,p1",
        "2026-02-01 09:30:00,,,0.998,ETH,Coinbase,Ledger,deposit,"
        "0xabcdef0123456789abcdef0123456789abcdef01,,,,p2"))
    blob = str(f) + str(pd)
    assert "0xabcdef0123456789abcdef0123456789abcdef01" not in blob
    assert "0xabcdef" in blob, "a short prefix must survive so a row is findable"

def test_process_hands_back_no_legs():
    f, pd = process(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,q1"))
    assert "legs" not in f and all("qty" not in str(k) for k in f)
    for x in pd["findings"]:
        assert x["legs"] == [] or all("tx_hash" not in leg for leg in x["legs"])

def test_process_states_retention():
    f, _ = process(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,r1"))
    assert str(RETENTION_DAYS) in f["retention"]
    assert "never written to disk" in f["retention"]

def test_scrub_removes_addresses_from_free_text():
    t = scrub("sent from 0x1234567890abcdef1234567890abcdef12345678 today")
    assert "0x1234" not in t and "[address]" in t

def test_short_hash_is_not_lookupable():
    h = "0x" + "a" * 64
    assert len(short_hash(h)) < 12 and short_hash(h).startswith("0xaaaaaa")

def test_fix_text_never_instructs_on_tax_treatment():
    """Describing what two rows are is fine. Telling someone how to treat a
    transaction for tax is not ours to say."""
    p, r = analyze(open(os.path.join(os.path.dirname(__file__),
                   "fixtures/koinly_sample.csv")).read())
    for f in r["findings"]:
        low = f.fix.lower()
        for banned in ("mark both as", "mark them as a transfer",
                       "you should report", "claim this as", "deduct"):
            assert banned not in low, f"{f.kind}: {f.fix}"

def test_footer_disclaims_preparer_status():
    p, r = analyze(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,s1"))
    assert "not a tax preparer" in free(r, p)["footer"]

def test_purge_is_a_real_statement():
    assert "DELETE FROM jobs" in purge_sql() and "expires_at" in purge_sql()

def test_a_zero_dollar_guess_never_silences_a_real_finding():
    """A low-confidence pair contributes $0. If it claimed its rows it would
    zero out a real zero-cost disposal sitting on the same row."""
    p, r = analyze(csv(
        "2026-04-02 08:00:00,40,SOL,,,Phantom,Kraken,withdrawal,,5280,5280,0,t1",
        "2026-04-02 19:36:00,,,39.94,SOL,Phantom,Kraken,deposit,,,,,t2"))
    guess = [f for f in r["findings"] if f.kind == "pair" and f.confidence == "low"]
    zero  = [f for f in r["findings"] if f.kind == "zero_cost" and f.confidence == "high"]
    assert guess, "the timing guess should still be reported"
    assert zero and zero[0].counted and zero[0].impact == Decimal("5280")
    assert r["headline"] == Decimal("5280")

def test_an_opening_gap_never_claims_a_row():
    p, r = analyze(csv(
        "2026-06-01 10:00:00,1.0,BTC,,,Vault,,sell,0xddd,41000,41000,0,u1"))
    assert any(f.kind == "opening_gap" for f in r["findings"])
    z = [f for f in r["findings"] if f.kind == "zero_cost"][0]
    assert z.counted and z.impact == Decimal("41000")

if __name__ == "__main__":
    n = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v(); n += 1; print("  ok ", k)
    print(f"\n{n} passed")
