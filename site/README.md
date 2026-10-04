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

## Taking money

Set `PAYMENT_LINK` at the top of the script block in `index.html` to a Stripe
Payment Link. Until it is set, the Unlock button explains itself and the demo
button still shows the paid view.

For v1 delivery is manual: the customer pays, you email the full findings.
That is deliberate — it validates whether anyone pays before you build a
paywall that has to be real.

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
