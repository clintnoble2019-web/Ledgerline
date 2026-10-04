# Ledgerline — site

Single-page site. The CSV is parsed **in the browser** — nothing is uploaded,
so there is no server, no storage and nothing to breach.

```
index.html          the whole site: landing, parser, detectors, results
assets/             logo, mark, favicon
```

## Run it

Open `index.html`. That's it. No build step, no dependencies.

## Deploy

Any static host. Cloudflare Pages, Netlify, Vercel, GitHub Pages — point it at
this repo and it serves. No backend to configure.

## Taking money — Stripe Payment Link

No backend, no webhook, no code to deploy.

**1. Create the link.** Stripe dashboard → Payment Links → new link, $79,
one-time.

**2. Set the confirmation page to redirect**, not to Stripe's own receipt
page. Point it at your site with the flag appended:

```
https://yoursite.com/?paid=1
```

**3. Under Advanced options, turn on client reference ID.** The site
generates a `LL-XXXXXX` reference per analysis and attaches it to the
checkout, so a payment in your dashboard maps to a specific report.

**4. Paste the link** into `STRIPE.LINK` at the top of the script block in
`index.html`. That is the entire integration.

### What happens on the round trip

The redirect to Stripe would normally destroy the analysis, because the file
only ever existed in that tab's memory. So before leaving, the findings are
stashed in `sessionStorage` — **never the CSV**, only the findings — and
restored when the customer returns with `?paid=1`. Payment is remembered for
the session, so re-uploading the same file opens unlocked.

If the tab was closed mid-checkout, the return page says so plainly and asks
them to re-upload. Nothing was stored on your side to recover, which is the
point.

### Manual unlock

Set `STRIPE.MANUAL` to a code and `?unlock=THATCODE` unlocks the view. Useful
while delivery is by hand: customer pays, you email the code or the findings.

### Fees

Stripe is 2.9% + $0.30. Lemon Squeezy and Paddle charge roughly 5% + $0.50 but
act as merchant of record, taking on global sales tax and VAT liability. For a
product aimed at US filers that is not worth the extra 2% yet — revisit if it
starts selling abroad.

You need a business entity and a bank account before Stripe will pay out.

## Logo

| File | Use |
| --- | --- |
| `assets/logo-lockup.svg` | Mark + wordmark, on white |
| `assets/logo-lockup-reverse.svg` | Mark + wordmark, on green |
| `assets/logo-mark.svg` | Mark alone |
| `assets/favicon.svg` | 16px-safe mark, thicker bars |

Green `#0E7A4D` · Deep `#0A4F33` · Ink `#10211A` · Wash `#E8F4EE`
Archivo 700 for the wordmark at −3.5% tracking. Public Sans for body.

## Note on the paywall

Everything runs client-side, so the locked findings are technically in the
page. That is fine for v1 — honest people pay, and the point is to learn
whether anyone does.

When it needs to be real: the browser still parses the file, then posts only
the **redacted findings** to a server, which gates the paid view behind a
Stripe webhook. The file still never moves.
