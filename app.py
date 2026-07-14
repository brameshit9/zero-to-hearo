"""
Zero to Hero - Premium Explosion Scanner (NIFTY 50) - Streamlit App
Strategy: Price Compression -> OI Build -> Volume/ATR Explosion.
"""

import time

import pandas as pd
import streamlit as st

from scanner_core import DEFAULT_CONFIG, build_universe, score_ticker
from render import plot_detail_chart, render_cards_html

st.set_page_config(page_title="Zero to Hero - Explosion Scanner", page_icon="⚡", layout="wide")

st.title("⚡ Zero to Hero — Premium Explosion Scanner")
st.caption("NIFTY 50 · 18 conditions · Compression → OI Build → Volume/ATR Explosion")

st.warning(
    "This is a pattern-matching screener, **not financial advice**. "
    "C3 (OI Build) is a volume/price proxy, not real F&O Open Interest — "
    "yfinance does not carry option-chain data. Confirm price action and "
    "size risk yourself before acting on anything shown here.",
    icon="⚠️",
)

# ─────────────────────────────────────────────────────────────
#  SIDEBAR CONFIG
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Scan settings")

    config = dict(DEFAULT_CONFIG)  # copy so we never mutate the default

    config["data_period"] = st.selectbox(
        "History window", ["3mo", "6mo", "1y"], index=1,
        help="How much daily price history to pull per ticker.",
    )
    config["min_score_show"] = st.slider("Minimum score to display", 0, 18, 5)

    st.subheader("Compression thresholds")
    config["atr_pct_compress_threshold"] = st.slider("ATR% compress threshold", 0.5, 5.0, 1.8, 0.1)
    config["vol_compress_ratio"] = st.slider("Volume compression ratio", 0.2, 1.0, 0.65, 0.05)
    config["candle_size_threshold"] = st.slider("Small-candle body % threshold", 0.2, 3.0, 0.8, 0.1)

    st.subheader("Explosion thresholds")
    config["volume_explosion_x"] = st.slider("Volume explosion multiple", 1.5, 6.0, 2.5, 0.1)
    config["atr_expansion_pct"] = st.slider("ATR expansion % from low", 5, 50, 15, 1)

    st.subheader("RSI reset zone")
    rsi_low, rsi_high = st.slider("RSI band", 10, 90, (38, 60))
    config["rsi_low"], config["rsi_high"] = rsi_low, rsi_high

    st.divider()
    run_clicked = st.button("🚀 Run scan", type="primary", use_container_width=True)


# ─────────────────────────────────────────────────────────────
#  RUN SCAN
# ─────────────────────────────────────────────────────────────
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
    st.session_state.scan_errors = []

if run_clicked:
    tickers, universe_msg = build_universe()
    st.info(f"Universe: NIFTY 50 — {universe_msg}", icon="📋")

    progress = st.progress(0.0, text="Starting scan...")
    results, errors = [], []

    for i, ticker in enumerate(tickers):
        progress.progress((i + 1) / len(tickers), text=f"Scanning {ticker} ({i+1}/{len(tickers)})")
        try:
            res = score_ticker(ticker, config)
            if res and res["total_score"] >= config["min_score_show"]:
                results.append(res)
        except Exception as e:
            errors.append(f"{ticker}: {e}")

    progress.empty()
    results.sort(key=lambda x: (x["is_trigger"], x["core5_score"], x["total_score"]), reverse=True)

    st.session_state.scan_results = results
    st.session_state.scan_errors = errors
    st.session_state.scan_config = config

# ─────────────────────────────────────────────────────────────
#  DISPLAY RESULTS
# ─────────────────────────────────────────────────────────────
results = st.session_state.scan_results

if results is None:
    st.info("Set your thresholds in the sidebar and click **Run scan** to begin.")
else:
    errors = st.session_state.scan_errors
    used_config = st.session_state.scan_config

    st.success(f"Scan complete — {len(results)} stocks at or above the minimum score.")
    if errors:
        with st.expander(f"⚠️ {len(errors)} tickers skipped due to errors"):
            st.write(errors)

    triggers = [r for r in results if r["is_trigger"]]

    # ── BUY TRIGGER ALERTS ──────────────────────────────────
    st.subheader("🎯 Buy Trigger Alerts")
    if triggers:
        st.write(
            f"**{len(triggers)}** stock(s) confirmed — score ≥12 with Volume Explosion (C6) "
            "and Breakout (C8) both fired."
        )
        trig_df = pd.DataFrame([{
            "Ticker": r["ticker"],
            "Price": f"{r['currency']}{r['price']:.2f}",
            "Score": f"{r['total_score']}/18",
            "Core5": f"{r['core5_score']}/5",
            "5d Move": r["details"].get("5d Move", "—"),
            "Vol Explode": r["details"].get("Vol Explode", "—"),
        } for r in triggers])
        st.dataframe(trig_df, use_container_width=True, hide_index=True)
        st.caption(
            "These are pattern matches, not advice — confirm price action and your own "
            "risk/strike selection before acting. Confirmed ≠ guaranteed."
        )
    else:
        st.write(
            "No NIFTY 50 stock currently has both Volume Explosion (C6) and Breakout (C8) "
            "confirmed alongside score ≥12. Anything below is still Compression (setup "
            "forming) or Watch — not a confirmed entry by this script's logic."
        )

    # ── SUMMARY TABLE ────────────────────────────────────────
    st.subheader("Summary table")
    summary_df = pd.DataFrame([{
        "Trigger": "🎯" if r["is_trigger"] else "",
        "Ticker": r["ticker"],
        "Mkt": r["market"],
        "Price": f"{r['currency']}{r['price']:.2f}",
        "Core5": f"{r['core5_score']}/5",
        "Score": f"{r['total_score']}/18",
        "Compress": f"{r['compression_score']}/8",
        "Explode": f"{r['explosion_score']}/6",
        "Phase": r["phase"],
    } for r in results[:30]])
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # ── CARD GRID ─────────────────────────────────────────────
    st.subheader("Card grid")
    html, n_cards = render_cards_html(results, config["min_score_show"])
    rows = max(1, -(-n_cards // 4))  # ceil division, ~4 cards per row at typical width
    import streamlit.components.v1 as components
    components.html(html, height=rows * 430 + 40, scrolling=True)

    # ── DETAIL CHARTS ─────────────────────────────────────────
    st.subheader("📊 Detail charts")
    top_names = [r["ticker"] for r in results[:15]]
    chosen = st.multiselect(
        "Pick tickers to chart (defaults to top 5 by score)",
        options=top_names,
        default=top_names[:5],
    )
    for ticker in chosen:
        r = next(x for x in results if x["ticker"] == ticker)
        fig = plot_detail_chart(r, used_config)
        st.pyplot(fig)
        import matplotlib.pyplot as plt
        plt.close(fig)
