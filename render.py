"""
Rendering helpers for the Streamlit app: the HTML card grid and the
per-ticker matplotlib detail chart. Kept separate from scanner_core so the
scoring logic stays UI-agnostic.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from scanner_core import COND_LABELS, CORE5_KEYS, CORE5_LABELS, KEY_DETAIL_ORDER, find_sr_levels


def render_cards_html(results, min_score_show):
    """Build the dark-themed HTML card grid. Returns an HTML string to pass
    to st.components.v1.html()."""
    filtered = [r for r in results if r["total_score"] >= min_score_show]

    css = """
    <style>
      body{margin:0}
      .zh-grid{display:flex;flex-wrap:wrap;gap:12px;font-family:'Courier New',monospace;padding:6px}
      .zh-card{background:#111827;border:1px solid #1f2937;border-radius:10px;
               padding:14px;width:270px;color:#e5e7eb;font-size:12px;
               box-shadow:0 2px 8px rgba(0,0,0,.4)}
      .zh-card.fire {border-color:#ff4444;box-shadow:0 0 12px rgba(255,68,68,.3)}
      .zh-card.spark{border-color:#ffaa00;box-shadow:0 0 10px rgba(255,170,0,.25)}
      .zh-card.watch{border-color:#44aaff}
      .zh-card.triggered{border-color:#fbbf24;border-width:2px;
              box-shadow:0 0 18px rgba(251,191,36,.55)}
      .zh-trigger-badge{background:#fbbf24;color:#111827;font-size:10px;
              font-weight:bold;padding:3px 8px;border-radius:4px;
              display:inline-block;margin-bottom:6px;letter-spacing:0.5px}
      .zh-ticker{font-size:18px;font-weight:bold;color:#fff}
      .zh-mkt{font-size:9px;color:#6b7280;margin-left:6px}
      .zh-price {font-size:13px;color:#9ca3af}
      .zh-phase {font-size:10px;font-weight:bold;padding:3px 7px;border-radius:4px;
                 display:inline-block;margin:5px 0}
      .zh-scores{display:flex;justify-content:space-between;margin:6px 0}
      .zh-sb{text-align:center}
      .zh-sb-val{font-size:15px;font-weight:bold}
      .zh-sb-lbl{font-size:9px;color:#6b7280}
      .zh-bar-bg{background:#1f2937;border-radius:3px;height:5px;margin:5px 0}
      .zh-bar-fg{height:5px;border-radius:3px}
      .zh-dots{display:flex;flex-wrap:wrap;gap:3px;margin-top:7px}
      .zh-dot{width:22px;height:22px;border-radius:4px;font-size:8px;
              display:flex;align-items:center;justify-content:center;font-weight:bold}
      .zh-dot.on {background:#14532d;color:#4ade80}
      .zh-dot.off{background:#1f2937;color:#374151}
      .zh-detail{color:#6b7280;margin-top:7px;font-size:10px;line-height:1.75}
      .zh-detail span{color:#d1d5db}
      .zh-core5{margin:8px 0;padding:8px;background:#0b1220;border-radius:6px;
              border:1px solid #1f2937}
      .zh-core5-hdr{display:flex;justify-content:space-between;align-items:center;
              margin-bottom:5px}
      .zh-core5-title{font-size:9px;color:#9ca3af;letter-spacing:0.5px;font-weight:bold}
      .zh-core5-score{font-size:12px;font-weight:bold;color:#fbbf24}
      .zh-core5-row{display:flex;justify-content:space-between;font-size:9px;padding:1px 0}
      .zh-core5-row.on  span.lbl{color:#4ade80}
      .zh-core5-row.off span.lbl{color:#6b7280}
      .zh-core5-row span.mark{font-size:10px}
    </style>
    """

    cards = []
    for r in filtered:
        if r["is_trigger"]:
            cls = "triggered"
        elif r["phase"] == "EXPLOSION READY":
            cls = "fire"
        elif r["phase"] == "COMPRESSION":
            cls = "spark"
        else:
            cls = "watch"

        bar_pct = int(r["total_score"] / 18 * 100)
        bar_col = "#fbbf24" if r["is_trigger"] else \
            ("#ff4444" if bar_pct >= 67 else ("#ffaa00" if bar_pct >= 44 else "#44aaff"))

        dots = "".join(
            f'<div class="zh-dot {"on" if r["scores"].get(k, 0) else "off"}" title="{k}">{lbl}</div>'
            for k, lbl in COND_LABELS.items()
        )
        det_lines = "".join(
            f'{k}: <span>{r["details"][k]}</span><br>'
            for k in KEY_DETAIL_ORDER if k in r["details"]
        )
        trigger_badge = '<div class="zh-trigger-badge">BUY TRIGGER</div>' if r["is_trigger"] else ""
        core5_rows = "".join(
            f'<div class="zh-core5-row {"on" if r["scores"].get(k, 0) else "off"}">'
            f'<span class="lbl">{i}. {CORE5_LABELS[k]}</span>'
            f'<span class="mark">{"Y" if r["scores"].get(k, 0) else "N"}</span></div>'
            for i, k in enumerate(CORE5_KEYS, start=1)
        )

        cards.append(f"""
        <div class="zh-card {cls}">
          {trigger_badge}
          <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
              <div class="zh-ticker">{r['ticker']}<span class="zh-mkt">{r['market']}</span></div>
              <div class="zh-price">{r['currency']}{r['price']:.2f}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:24px;font-weight:bold;color:{bar_col}">
                {r['total_score']}<span style="font-size:11px;color:#6b7280">/18</span>
              </div>
            </div>
          </div>
          <div class="zh-phase" style="background:{r['phase_color']}22;color:{r['phase_color']}">{r['phase']}</div>
          <div class="zh-bar-bg"><div class="zh-bar-fg" style="width:{bar_pct}%;background:{bar_col}"></div></div>
          <div class="zh-core5">
            <div class="zh-core5-hdr">
              <div class="zh-core5-title">CORE 5</div>
              <div class="zh-core5-score">{r['core5_score']}/5</div>
            </div>
            {core5_rows}
          </div>
          <div class="zh-scores">
            <div class="zh-sb"><div class="zh-sb-val" style="color:#44aaff">{r['compression_score']}/8</div><div class="zh-sb-lbl">COMPRESS</div></div>
            <div class="zh-sb"><div class="zh-sb-val" style="color:#ff4444">{r['explosion_score']}/6</div><div class="zh-sb-lbl">EXPLODE</div></div>
            <div class="zh-sb"><div class="zh-sb-val" style="color:#a855f7">{r['extras_score']}/4</div><div class="zh-sb-lbl">EXTRAS</div></div>
          </div>
          <div class="zh-dots">{dots}</div>
          <div class="zh-detail">{det_lines}</div>
        </div>""")

    return css + '<div class="zh-grid">' + "".join(cards) + "</div>", len(filtered)


def plot_detail_chart(result, config, n=60):
    """Build and return a matplotlib Figure for one ticker (caller displays
    it via st.pyplot and should plt.close(fig) afterwards)."""
    r = result
    df = r["df"].tail(n).copy()
    cur = r["currency"]

    fig = plt.figure(figsize=(12, 9), facecolor="#0d0d0d")
    gs = GridSpec(4, 1, figure=fig, hspace=0.08, height_ratios=[3, 1, 1, 1])
    axes = [fig.add_subplot(gs[i]) for i in range(4)]

    for ax in axes:
        ax.set_facecolor("#111827")
        ax.tick_params(colors="#6b7280", labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor("#1f2937")

    x = list(range(len(df)))
    c, o, h, l = df["Close"].values, df["Open"].values, df["High"].values, df["Low"].values
    v, vma = df["Volume"].values, df["vol_20avg"].values

    ax = axes[0]
    for i in x:
        col = "#22c55e" if c[i] >= o[i] else "#ef4444"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.8, alpha=0.6)
        ax.add_patch(plt.Rectangle((i - 0.3, min(o[i], c[i])), 0.6,
                                    abs(c[i] - o[i]) or 0.01, color=col, alpha=0.9))
    for ema, col, lbl in [("ema9", "#facc15", "EMA9"), ("ema21", "#60a5fa", "EMA21"),
                           ("ema50", "#a78bfa", "EMA50")]:
        ax.plot(x, df[ema].values, color=col, lw=1.0, label=lbl, alpha=0.85)

    for lvl in find_sr_levels(df, lookback=config["sr_lookback"])[:4]:
        ax.axhline(lvl, color="#f97316", lw=0.7, ls="--", alpha=0.6)

    ax.set_title(
        f"{r['ticker']} ({r['market']})  |  Score {r['total_score']}/18  |  "
        f"{r['phase']}  |  {cur}{r['price']:.2f}",
        color="#e5e7eb", fontsize=11, pad=8, fontfamily="monospace",
    )
    ax.legend(loc="upper left", fontsize=7, facecolor="#1f2937",
              labelcolor="#e5e7eb", framealpha=0.7)
    ax.set_ylabel("Price", color="#6b7280", fontsize=8)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    for i in x:
        col = "#22c55e" if v[i] >= vma[i] * config["volume_explosion_x"] else \
            ("#facc15" if v[i] >= vma[i] else "#374151")
        ax.bar(i, v[i], color=col, width=0.8, alpha=0.8)
    ax.plot(x, vma, color="#60a5fa", lw=1.0, ls="--", alpha=0.7)
    ax.set_ylabel("Volume", color="#6b7280", fontsize=8)
    ax.tick_params(labelbottom=False)

    ax = axes[2]
    atrv = df["atr_pct"].values
    ax.plot(x, atrv, color="#f59e0b", lw=1.2, label="ATR%")
    ax.axhline(config["atr_pct_compress_threshold"], color="#44aaff", lw=0.8,
               ls="--", alpha=0.7, label=f"Compress <{config['atr_pct_compress_threshold']}%")
    ax.fill_between(x, 0, atrv,
                     where=np.array(atrv) < config["atr_pct_compress_threshold"],
                     color="#44aaff", alpha=0.08)
    ax.legend(loc="upper right", fontsize=7, facecolor="#1f2937",
              labelcolor="#e5e7eb", framealpha=0.7)
    ax.set_ylabel("ATR%", color="#6b7280", fontsize=8)
    ax.tick_params(labelbottom=False)

    ax = axes[3]
    rsiv = df["rsi"].values
    ax.plot(x, rsiv, color="#a78bfa", lw=1.2, label="RSI")
    ax.axhline(config["rsi_high"], color="#6b7280", lw=0.7, ls="--")
    ax.axhline(config["rsi_low"], color="#6b7280", lw=0.7, ls="--")
    ax.fill_between(x, config["rsi_low"], config["rsi_high"],
                     alpha=0.08, color="#44aaff", label="Reset Zone")
    ax.set_ylim(10, 90)
    ax.set_ylabel("RSI", color="#6b7280", fontsize=8)
    ax.legend(loc="upper right", fontsize=7, facecolor="#1f2937",
              labelcolor="#e5e7eb", framealpha=0.7)

    cond_str = "  ".join(f"{k.split('_')[0]}:{'Y' if val else 'N'}" for k, val in r["scores"].items())
    fig.text(0.01, 0.005, cond_str, fontsize=6, color="#4b5563", fontfamily="monospace")

    plt.tight_layout(rect=[0, 0.02, 1, 1])
    return fig
