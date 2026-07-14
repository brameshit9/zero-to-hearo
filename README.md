# Zero to Hero — Premium Explosion Scanner ⚡

A Streamlit screener for NIFTY 50 stocks that looks for the setup pattern:

**Price Compression → quiet OI/volume build → Volume & ATR Explosion**

It scores each stock against 18 conditions (grouped into Compression,
Explosion, and Extra signals) and flags a **Buy Trigger** only when score
≥12 *and* both the Volume Explosion and Breakout conditions have actually
fired — everything else is a setup, not a confirmed signal.

> ⚠️ **Not financial advice.** This is a rule-based pattern scanner for
> research purposes. Condition C3 ("OI Build") is a volume/price-divergence
> **proxy**, not real F&O Open Interest — `yfinance` only provides
> cash-market price/volume bars, not NSE option-chain data. For true OI
> you'd need NSE's option-chain API
> (`https://www.nseindia.com/api/option-chain-equities?symbol=...`).

## Features

- Live NIFTY 50 constituent list (fetched from NSE's archive CSV, with a
  built-in 50-name fallback if that fetch fails)
- Adjustable thresholds for every compression/explosion condition in the
  sidebar
- Buy Trigger alert table
- Full sortable summary table (Core-5 score, total score, sub-scores, phase)
- Dark-themed HTML card grid per ticker with an 18-condition dot matrix
- Matplotlib detail charts (price + EMA9/21/50, volume, ATR%, RSI) for any
  ticker you pick
- Data cached (15–60 min) so re-running with tweaked thresholds doesn't
  re-download everything

## Project structure

```
nifty-explosion-scanner/
├── app.py              # Streamlit UI: sidebar, scan runner, results display
├── scanner_core.py      # Universe, data fetch, indicators, 18-condition scorer
├── render.py             # HTML card grid + matplotlib detail chart builders
├── requirements.txt
├── .gitignore
└── README.md
```

## The scoring model

**Core 5** (checked first, backbone of the strategy):

1. C1 — Price Compression
2. C2 — Volume Compression
3. C3 — OI Build (proxy)
4. C6 — Volume Explosion
5. C7 — ATR Expansion

**Remaining 13 conditions** cover support/resistance proximity, smart-money
volume divergence, breakout confirmation, momentum ("Greeks" proxies —
Delta/Gamma/Vega/Theta), RSI reset zone, MACD compression, Bollinger
squeeze, EMA stack, and relative strength vs. benchmark (`^NSEI` for `.NS`
tickers, `SPY` otherwise).

Max score = 18.

| Score | Phase |
|---|---|
| ≥ 12 | 🔥 Premium Explosion Ready |
| 8–11 | ⚡ Compression Phase |
| 5–7 | 👀 Early Watch |
| < 5 | 😴 Neutral |

## Run locally

```bash
git clone https://github.com/<your-username>/nifty-explosion-scanner.git
cd nifty-explosion-scanner
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`. A full scan of NIFTY 50 takes
roughly 1–3 minutes depending on Yahoo Finance rate limits.

## Push to GitHub

```bash
cd nifty-explosion-scanner
git init
git add .
git commit -m "Initial commit: Zero to Hero explosion scanner"
git branch -M main
git remote add origin https://github.com/<your-username>/nifty-explosion-scanner.git
git push -u origin main
```

## Deploy on Streamlit Community Cloud

1. Push the repo to GitHub (steps above).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**, select this repo/branch, and set the main file path to `app.py`.
4. Click **Deploy** — Streamlit Cloud installs `requirements.txt` automatically.

No API keys or secrets are required; `yfinance` and the NSE archive CSV are
both public endpoints.

## Notes / known limitations

- Data comes from Yahoo Finance (`yfinance`) — subject to its own rate
  limits and occasional gaps.
- NIFTY 50 composition changes at semi-annual reviews; the live-fetch keeps
  this current, and the fallback list is just an offline safety net.
- Detail charts are capped to 15 selectable tickers in the UI to keep
  rendering fast; the underlying summary table always covers the full
  scanned universe.
