"""
Zero to Hero - Premium Explosion Scanner (NIFTY 50)
Core logic module: universe resolution, data fetch, indicator computation,
and the 18-condition scoring engine.

Strategy: Price Compression -> OI Build -> Volume/ATR Explosion.

CORE 5 (highest-priority conditions, checked in this order):
    C1 Price Compression -> C2 Volume Compression -> C3 OI Build ->
    C6 Volume Explosion -> C7 ATR Expansion

NOTE on C3: yfinance only provides price/volume bars for cash-market
stocks - it does NOT carry actual F&O Open Interest. C3 is therefore a
*proxy* for OI build (price flat + volume rising = quiet accumulation),
not real OI data. For true OI, you'd need NSE's option-chain API
(e.g. https://www.nseindia.com/api/option-chain-equities?symbol=...).

SCORING (max 18 points):
    Score >= 12  -> PREMIUM EXPLOSION READY
    Score  8-11  -> COMPRESSION PHASE
    Score  5-7   -> EARLY WATCH
    Score  < 5   -> NEUTRAL

BUY TRIGGER: score >= 12 AND Volume Explosion (C6) AND Breakout (C8) both
fired. Compression-phase names are setups, not confirmed entries.
"""

import io
import urllib.request
import warnings

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
#  DEFAULT CONFIG  (the Streamlit sidebar can override a copy of this)
# ─────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    # Compression thresholds
    "atr_pct_compress_threshold": 1.8,   # ATR% below this = compressed
    "vol_compress_ratio":         0.65,  # vol < ratio x 20d avg = compressed
    "bb_squeeze_percentile":      20,    # BB width bottom X-th pct of 52w
    "candle_size_threshold":      0.8,   # avg body pct below this = small
    "price_range_days":           10,    # days for tight-range check

    # OI-proxy divergence
    "oi_vol_divergence_days": 5,

    # Explosion thresholds
    "volume_explosion_x":    2.5,   # vol >= X x 20d avg = explosion
    "atr_expansion_pct":     15,    # ATR% rose by X% from recent low

    # S/R detection
    "sr_lookback":       60,
    "sr_proximity_pct":  1.5,

    # RSI compression zone
    "rsi_low":  38,
    "rsi_high": 60,

    # EMA periods
    "ema_fast": 9, "ema_mid": 21, "ema_slow": 50,

    # Minimum score to appear on output cards
    "min_score_show": 5,

    # yfinance download period
    "data_period": "6mo",
}

# ─────────────────────────────────────────────────────────────
#  UNIVERSE - NIFTY 50  (live fetch, with static fallback)
# ─────────────────────────────────────────────────────────────
NIFTY50_FALLBACK = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "LT", "SBIN",
    "BHARTIARTL", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "M&M",
    "MARUTI", "SUNPHARMA", "NTPC", "TATAMOTORS", "TITAN", "ASIANPAINT",
    "ULTRACEMCO", "BAJAJFINSV", "WIPRO", "ADANIENT", "POWERGRID", "HCLTECH",
    "JSWSTEEL", "TATASTEEL", "COALINDIA", "GRASIM", "NESTLEIND", "TECHM",
    "INDUSINDBK", "HINDALCO", "CIPLA", "DRREDDY", "EICHERMOT", "BPCL", "ONGC",
    "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "BRITANNIA", "APOLLOHOSP", "DIVISLAB",
    "TATACONSUM", "LTIM", "ADANIPORTS", "SHRIRAMFIN", "TRENT",
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_nifty50_tickers():
    """Fetch the live NIFTY 50 constituent list from the NSE archive CSV.
    Falls back to NIFTY50_FALLBACK on any failure, and appends '.NS' for
    yfinance (Yahoo Finance's suffix for NSE-listed symbols)."""
    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        csv_bytes = urllib.request.urlopen(req, timeout=10).read()
        df = pd.read_csv(io.BytesIO(csv_bytes))
        col = "Symbol" if "Symbol" in df.columns else df.columns[2]
        symbols = df[col].astype(str).str.strip().tolist()
        symbols = sorted(set(symbols))
        if len(symbols) >= 45:
            return [s + ".NS" for s in symbols], f"Live list fetched ({len(symbols)} tickers)"
        raise ValueError("Parsed list looked too short")
    except Exception as e:
        return (
            [s + ".NS" for s in NIFTY50_FALLBACK],
            f"Could not fetch live list ({e}). Using fallback of {len(NIFTY50_FALLBACK)} names.",
        )


def build_universe():
    tickers, msg = get_nifty50_tickers()
    return tickers, msg


# ─────────────────────────────────────────────────────────────
#  CORE 5 - the highest-priority conditions, in priority order
# ─────────────────────────────────────────────────────────────
CORE5_KEYS = ["C1_PriceCompress", "C2_VolCompress", "C3_OIBuild",
              "C6_VolExplosion", "C7_ATRExpand"]
CORE5_LABELS = {
    "C1_PriceCompress": "Price Compression",
    "C2_VolCompress":   "Volume Compression",
    "C3_OIBuild":       "OI Build",
    "C6_VolExplosion":  "Volume Explosion",
    "C7_ATRExpand":     "ATR Expansion",
}

COND_LABELS = {
    "C1_PriceCompress": "PC", "C2_VolCompress": "VC", "C3_OIBuild": "OI",
    "C4_SRLevel": "SR", "C5_SmartMoney": "SM", "C6_VolExplosion": "VE",
    "C7_ATRExpand": "AE", "C8_Breakout": "BO", "C9_DeltaRising": "D+",
    "C10_GammaAccel": "G+", "C11_VegaExpand": "V+", "C12_ThetaIgnore": "T0",
    "C13_UpperCircuit": "UC", "C14_RSIReset": "RR", "C15_MACDCompress": "MC",
    "C16_BBSqueeze": "BB", "C17_EMAStack": "EM", "C18_RelStrength": "RS",
}

KEY_DETAIL_ORDER = [
    "ATR%", "10d Rng", "Avg Body", "Vol Ratio", "RSI",
    "5d Move", "EMA Stack", "S/R", "BB Width", "BB Sq%",
    "RS vs Bmk", "Circuit ~",
]


# ─────────────────────────────────────────────────────────────
#  MARKET / CURRENCY HELPERS
# ─────────────────────────────────────────────────────────────
def market_of(ticker):
    """'IN' for NSE (.NS) tickers, else 'US'."""
    return "IN" if ticker.upper().endswith(".NS") else "US"


def currency_symbol(ticker):
    return "₹" if market_of(ticker) == "IN" else "$"


# ─────────────────────────────────────────────────────────────
#  INDICATOR MATH  (plain pandas/numpy - no pandas_ta dependency)
#  pandas_ta is unmaintained and frequently fails to build on fresh
#  installs (e.g. Streamlit Community Cloud), so every indicator below is
#  implemented directly against pandas Series.
# ─────────────────────────────────────────────────────────────
def _ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def _atr(high, low, close, length=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder's smoothing (equivalent to an EMA with alpha = 1/length)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def _rsi(close, length=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _macd_hist(close, fast=12, slow=26, signal=9):
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    return macd_line - signal_line


def _bbands_width(close, length=20, std=2):
    mid = close.rolling(length).mean()
    dev = close.rolling(length).std()
    upper = mid + std * dev
    lower = mid - std * dev
    return (upper - lower) / mid.replace(0, np.nan) * 100


# ─────────────────────────────────────────────────────────────
#  DATA FETCH  (cached per ticker+period for the Streamlit session)
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def fetch_data(ticker, period="6mo"):
    try:
        df = yf.download(ticker, period=period, interval="1d",
                          progress=False, auto_adjust=True)
        if df is None or len(df) < 40:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  INDICATOR COMPUTATION
# ─────────────────────────────────────────────────────────────
def compute_indicators(df, config):
    df = df.copy()
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    df["atr"] = _atr(h, l, c, length=14)
    df["atr_pct"] = (df["atr"] / c) * 100
    df["atr_20min"] = df["atr_pct"].rolling(20).min()

    df["bb_width"] = _bbands_width(c, length=20, std=2)
    df["bb_squeeze"] = df["bb_width"].rolling(252, min_periods=60).rank(pct=True) * 100

    df["vol_20avg"] = v.rolling(20).mean()
    df["vol_ratio"] = v / df["vol_20avg"]

    df["rsi"] = _rsi(c, length=14)

    df["macd_hist"] = _macd_hist(c, fast=12, slow=26, signal=9)
    df["macd_hist_abs"] = df["macd_hist"].abs()

    df["ema9"] = _ema(c, config["ema_fast"])
    df["ema21"] = _ema(c, config["ema_mid"])
    df["ema50"] = _ema(c, config["ema_slow"])

    df["body_pct"] = ((df["Close"] - df["Open"]).abs() / df["Open"].replace(0, np.nan)) * 100

    n = config["price_range_days"]
    df["range_n"] = (h.rolling(n).max() - l.rolling(n).min()) / c * 100

    days = config["oi_vol_divergence_days"]
    df["price_chg"] = c.pct_change(days) * 100
    df["vol_chg"] = v.pct_change(days) * 100

    return df


# ─────────────────────────────────────────────────────────────
#  S/R PIVOT DETECTION
# ─────────────────────────────────────────────────────────────
def find_sr_levels(df, lookback=60):
    recent = df.tail(lookback)
    h_arr = recent["High"].values
    l_arr = recent["Low"].values
    levels = []
    for i in range(2, len(h_arr) - 2):
        if h_arr[i] > h_arr[i - 1] and h_arr[i] > h_arr[i - 2] \
                and h_arr[i] > h_arr[i + 1] and h_arr[i] > h_arr[i + 2]:
            levels.append(float(h_arr[i]))
        if l_arr[i] < l_arr[i - 1] and l_arr[i] < l_arr[i - 2] \
                and l_arr[i] < l_arr[i + 1] and l_arr[i] < l_arr[i + 2]:
            levels.append(float(l_arr[i]))
    return levels


def near_sr(price, levels, pct=1.5):
    for lvl in levels:
        if abs(price - lvl) / price * 100 < pct:
            return True, lvl
    return False, None


# ─────────────────────────────────────────────────────────────
#  BENCHMARK RETURN (SPY for US tickers, ^NSEI for .NS tickers) - cached
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_benchmark_return(market, period="6mo"):
    """20-day % return of the appropriate index for relative-strength (C18)."""
    symbol = "^NSEI" if market == "IN" else "SPY"
    try:
        idx = yf.download(symbol, period=period, interval="1d",
                           progress=False, auto_adjust=True)
        closes = idx["Close"].squeeze()
        ret = float((closes.iloc[-1] - closes.iloc[-20]) / closes.iloc[-20] * 100)
    except Exception:
        ret = 0.0
    return ret


# ─────────────────────────────────────────────────────────────
#  CORE SCORER
# ─────────────────────────────────────────────────────────────
def score_ticker(ticker, config):
    df_raw = fetch_data(ticker, period=config["data_period"])
    if df_raw is None:
        return None

    df = compute_indicators(df_raw, config)
    if len(df) < 50:
        return None

    market = market_of(ticker)
    cur = currency_symbol(ticker)
    bmk_ret = get_benchmark_return(market, period=config["data_period"])

    row = df.iloc[-1]
    prev5 = df.iloc[-6:-1]
    price = float(row["Close"])

    scores = {}
    details = {}

    # ── CORE 5 ──────────────────────────────────────────────
    atr_low = float(row["atr_pct"]) < config["atr_pct_compress_threshold"]
    candle_small = float(prev5["body_pct"].mean()) < config["candle_size_threshold"]
    range_tight = float(row["range_n"]) < 4.0
    scores["C1_PriceCompress"] = int(sum([atr_low, candle_small, range_tight]) >= 2)
    details["ATR%"] = f"{row['atr_pct']:.2f}%"
    details["10d Rng"] = f"{row['range_n']:.1f}%"
    details["Avg Body"] = f"{prev5['body_pct'].mean():.2f}%"

    vol_compressed = float(row["vol_ratio"]) < config["vol_compress_ratio"]
    vol_declining = float(df["vol_ratio"].tail(5).mean()) < 0.80
    scores["C2_VolCompress"] = int(vol_compressed or vol_declining)
    details["Vol Ratio"] = f"{row['vol_ratio']:.2f}x"

    price_flat = abs(float(row["price_chg"])) < 2.0
    vol_building = float(row["vol_chg"]) > 10.0
    scores["C3_OIBuild"] = int(price_flat and vol_building)
    details["5d ΔPrice"] = f"{row['price_chg']:.1f}%"
    details["5d ΔVol"] = f"{row['vol_chg']:.1f}%"

    scores["C6_VolExplosion"] = int(float(row["vol_ratio"]) >= config["volume_explosion_x"])
    details["Vol Explode"] = f"{row['vol_ratio']:.1f}x"

    atr_low_20 = float(df["atr_pct"].tail(20).min())
    atr_expanded_pct = (float(row["atr_pct"]) - atr_low_20) / (atr_low_20 + 1e-6) * 100
    scores["C7_ATRExpand"] = int(atr_expanded_pct >= config["atr_expansion_pct"])
    details["ATR Expand"] = f"+{atr_expanded_pct:.0f}%"

    # ── REMAINING CONDITIONS ────────────────────────────────
    sr_levels = find_sr_levels(df, lookback=config["sr_lookback"])
    is_near, sr_val = near_sr(price, sr_levels, pct=config["sr_proximity_pct"])
    scores["C4_SRLevel"] = int(is_near)
    details["S/R"] = f"{cur}{sr_val:.2f}" if sr_val else "None"

    oi_divergence = (float(row["vol_chg"]) > 20.0) and (abs(float(row["price_chg"])) < 1.5)
    scores["C5_SmartMoney"] = int(oi_divergence)

    ema9_ok = not pd.isna(row["ema9"]) and price > float(row["ema9"])
    ema21_ok = not pd.isna(row["ema21"]) and price > float(row["ema21"])
    big_body = float(row["body_pct"]) > 1.0
    scores["C8_Breakout"] = int(ema9_ok and ema21_ok and big_body
                                 and float(row["vol_ratio"]) > 1.5)

    price_5d = float((price - df["Close"].iloc[-6]) / df["Close"].iloc[-6] * 100)
    scores["C9_DeltaRising"] = int(price_5d > 1.5)
    details["5d Move"] = f"{price_5d:.1f}%"

    atr_accel = float(df["atr_pct"].diff().tail(3).mean()) > 0.05
    scores["C10_GammaAccel"] = int(atr_accel and scores["C7_ATRExpand"])

    bb_now = float(row["bb_width"]) if not pd.isna(row["bb_width"]) else np.nan
    bb_5ago = float(df["bb_width"].iloc[-5]) if not pd.isna(df["bb_width"].iloc[-5]) else np.nan
    bb_exp = (not np.isnan(bb_now)) and (not np.isnan(bb_5ago)) and (bb_now > bb_5ago * 1.10)
    scores["C11_VegaExpand"] = int(bb_exp)
    details["BB Width"] = f"{bb_now:.2f}%" if not np.isnan(bb_now) else "N/A"

    scores["C12_ThetaIgnore"] = int(abs(price_5d) > 3.0)

    scores["C13_UpperCircuit"] = int(float(row["atr_pct"]) > 1.5 and price_5d > 0)
    circuit_target = price * (1 + float(row["atr_pct"]) * 3 / 100)
    details["Circuit ~"] = f"{cur}{circuit_target:.2f} (+{row['atr_pct']*3:.1f}%)"

    rsi_val = float(row["rsi"]) if not pd.isna(row["rsi"]) else 50.0
    scores["C14_RSIReset"] = int(config["rsi_low"] <= rsi_val <= config["rsi_high"])
    details["RSI"] = f"{rsi_val:.1f}"

    macd_shrink = False
    if not pd.isna(row["macd_hist_abs"]):
        m5 = float(df["macd_hist_abs"].tail(5).mean())
        m20 = float(df["macd_hist_abs"].tail(20).mean())
        macd_shrink = (m5 < m20 * 0.60)
    scores["C15_MACDCompress"] = int(macd_shrink)

    bb_sq = float(row["bb_squeeze"]) if not pd.isna(row["bb_squeeze"]) else 50.0
    scores["C16_BBSqueeze"] = int(bb_sq < config["bb_squeeze_percentile"])
    details["BB Sq%"] = f"{bb_sq:.0f}th pct"

    ema_stack = (not pd.isna(row["ema9"]) and not pd.isna(row["ema21"]) and
                 not pd.isna(row["ema50"]) and
                 float(row["ema9"]) > float(row["ema21"]) > float(row["ema50"]))
    scores["C17_EMAStack"] = int(ema_stack)
    details["EMA Stack"] = "Yes" if ema_stack else "No"

    stock_20d = float((price - df["Close"].iloc[-21]) / df["Close"].iloc[-21] * 100)
    scores["C18_RelStrength"] = int(stock_20d > bmk_ret)
    bmk_label = "NIFTY" if market == "IN" else "SPY"
    details["RS vs Bmk"] = f"{stock_20d:.1f}% vs {bmk_ret:.1f}% ({bmk_label})"

    # ── TOTALS ────────────────────────────────────────────────
    total = sum(scores.values())
    comp_keys = ["C1_PriceCompress", "C2_VolCompress", "C3_OIBuild", "C4_SRLevel",
                 "C5_SmartMoney", "C14_RSIReset", "C15_MACDCompress", "C16_BBSqueeze"]
    expl_keys = ["C6_VolExplosion", "C7_ATRExpand", "C8_Breakout",
                 "C9_DeltaRising", "C10_GammaAccel", "C11_VegaExpand"]
    extra_keys = ["C12_ThetaIgnore", "C13_UpperCircuit", "C17_EMAStack", "C18_RelStrength"]

    comp_score = sum(scores[k] for k in comp_keys)
    expl_score = sum(scores[k] for k in expl_keys)
    extra_score = sum(scores[k] for k in extra_keys)
    core5_score = sum(scores[k] for k in CORE5_KEYS)

    if total >= 12:
        phase, pc = "EXPLOSION READY", "#ff4444"
    elif total >= 8:
        phase, pc = "COMPRESSION", "#ffaa00"
    elif total >= 5:
        phase, pc = "EARLY WATCH", "#44aaff"
    else:
        phase, pc = "NEUTRAL", "#888888"

    is_trigger = bool(total >= 12 and scores["C6_VolExplosion"] and scores["C8_Breakout"])

    return dict(
        ticker=ticker, price=price, market=market, currency=cur,
        total_score=total, compression_score=comp_score,
        explosion_score=expl_score, extras_score=extra_score,
        core5_score=core5_score,
        phase=phase, phase_color=pc, is_trigger=is_trigger,
        scores=scores, details=details, df=df,
    )
