"""LULU DCF visualization - phase 5.

Renders three portfolio-ready charts to data/gold/charts/:
1. Sensitivity heatmap (WACC x terminal growth → $/share)
2. Revenue: 16 yrs of historical + 5-yr base-case projection
3. Reverse DCF comparison - what the market price implies vs history

Local run: python viz.py
"""

from datetime import datetime
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

import dcf as m
from reverse_dcf import implied_growth, implied_margin, implied_wacc

# ─── Brand styling ─────────────────────────────────────────────────────────
BRAND_ROSE  = "#D4829A"
BRAND_NAVY  = "#1F2940"
BRAND_LIGHT = "#FFE5DA"
BRAND_GRAY  = "#9AA0A6"

CHARTS_DIR = Path("data/gold/charts")

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial"],
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.labelcolor": BRAND_NAVY,
    "axes.edgecolor": BRAND_NAVY,
    "axes.titleweight": "bold",
    "axes.titlecolor": BRAND_NAVY,
    "xtick.color": BRAND_NAVY,
    "ytick.color": BRAND_NAVY,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "figure.dpi": 110,
})


def save(fig, name, today):
    out = CHARTS_DIR / f"{name}_{today}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def chart_sensitivity(df_proj, shares_out, price, today):
    wacc_range   = np.arange(0.08, 0.155, 0.005)
    growth_range = np.arange(0.015, 0.041, 0.005)

    fcffs = df_proj["fcff"].values
    n = len(fcffs)
    final = fcffs[-1]

    grid = np.full((len(wacc_range), len(growth_range)), np.nan)
    for i, w in enumerate(wacc_range):
        for j, g in enumerate(growth_range):
            if w <= g:
                continue
            sum_pv = sum(f / (1 + w) ** (k + 1) for k, f in enumerate(fcffs))
            tv     = final * (1 + g) / (w - g)
            pv_tv  = tv / (1 + w) ** n
            equity = sum_pv + pv_tv + m.CASH_AND_EQUIVALENTS - m.TRADITIONAL_DEBT
            grid[i, j] = equity / shares_out

    fig, ax = plt.subplots(figsize=(11, 7))
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rose", ["#FFE5DA", BRAND_ROSE, "#8E3D55"]
    )
    im = ax.imshow(grid, cmap=cmap, aspect="auto", origin="lower")

    median = np.nanmedian(grid)
    for i in range(len(wacc_range)):
        for j in range(len(growth_range)):
            v = grid[i, j]
            if np.isnan(v):
                continue
            color = "white" if v > median else BRAND_NAVY
            weight = "bold" if abs(v - price) < 15 else "normal"
            ax.text(j, i, f"${v:.0f}", ha="center", va="center",
                    color=color, fontsize=9, fontweight=weight)

    ax.set_xticks(range(len(growth_range)))
    ax.set_xticklabels([f"{g*100:.1f}%" for g in growth_range])
    ax.set_yticks(range(len(wacc_range)))
    ax.set_yticklabels([f"{w*100:.1f}%" for w in wacc_range])
    ax.set_xlabel("Terminal growth rate")
    ax.set_ylabel("WACC (cost of equity)")
    ax.set_title(
        f"LULU DCF sensitivity - intrinsic \\$/share\n"
        f"current price: \\${price:.2f}    base case: {m.RISK_FREE_RATE*100:.1f}% Rf, β={m.BETA}",
        loc="left",
    )

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("\\$ per share", color=BRAND_NAVY)
    cbar.outline.set_visible(False)

    fig.tight_layout()
    return save(fig, "sensitivity", today)


def chart_revenue_projection(df_silver, df_proj, today):
    # Pre-2020 XBRL fiscal-year tagging is unreliable for LULU; show post-COVID era
    clean = df_silver[df_silver.index >= 2020]
    hist = clean["revenue"].dropna() / 1e9
    proj = df_proj["rev"] / 1e9

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(hist.index, hist.values, color=BRAND_NAVY, linewidth=2.5,
            marker="o", markersize=5, label="Historical")
    ax.plot([hist.index[-1]] + list(proj.index),
            [hist.values[-1]] + list(proj.values),
            color=BRAND_ROSE, linewidth=2.5, marker="o", markersize=5,
            linestyle="--", label="Base-case projection")
    ax.axvspan(hist.index[-1], proj.index[-1], color=BRAND_LIGHT,
               alpha=0.35, zorder=0)

    for fy, g in zip(df_proj.index, m.REV_GROWTH_PATH):
        ax.annotate(
            f"+{g*100:.1f}%",
            xy=(fy, proj.loc[fy]), xytext=(0, 9),
            textcoords="offset points", ha="center",
            fontsize=9, color=BRAND_ROSE, fontweight="bold",
        )

    ax.set_xlabel("Fiscal year")
    ax.set_ylabel("Revenue ($B)")
    ax.set_title("LULU revenue: post-COVID era history + 5-year base case", loc="left")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.legend(loc="upper left", frameon=False)

    fig.tight_layout()
    return save(fig, "revenue_projection", today)


def chart_reverse_comparison(df_silver, last_rev, last_fy, wacc, shares_out, price, today):
    g  = implied_growth(price, last_rev, last_fy, wacc, shares_out)
    om = implied_margin(price, last_rev, last_fy, wacc, shares_out)
    w  = implied_wacc(price, last_rev, last_fy, shares_out)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))

    panels = [
        ("Revenue CAGR (5-yr)",
         ["Implied\nby market", f"FY{last_fy}\nactual", "Base\ncase avg", "5-yr\nactual avg"],
         [g*100,
          df_silver.loc[last_fy, "revenue_growth"]*100,
          sum(m.REV_GROWTH_PATH)/len(m.REV_GROWTH_PATH)*100,
          df_silver["revenue_growth"].dropna().tail(5).mean()*100],
         "%", "{:+.1f}%"),
        ("Operating margin",
         ["Implied\nby market", f"FY{last_fy}\nactual", f"FY{last_fy-1}\npeak", "5-yr\navg"],
         [om*100,
          df_silver.loc[last_fy, "op_margin"]*100,
          df_silver.loc[last_fy-1, "op_margin"]*100,
          df_silver["op_margin"].dropna().tail(5).mean()*100],
         "%", "{:.1f}%"),
        ("WACC",
         ["Implied\nby market", "Base case\n(CAPM)", "Risk-free\n(10y UST)"],
         [w*100, wacc*100, m.RISK_FREE_RATE*100],
         "%", "{:.1f}%"),
    ]

    for ax, (title, labels, values, ylabel, fmt) in zip(axes, panels):
        colors = [BRAND_ROSE] + [BRAND_NAVY] * (len(labels) - 2) + [BRAND_GRAY]
        bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=1.5)
        for bar, v in zip(bars, values):
            offset = 0.4 if v >= 0 else -1.5
            ax.text(bar.get_x() + bar.get_width() / 2, v + offset,
                    fmt.format(v), ha="center", fontsize=10,
                    fontweight="bold", color=BRAND_NAVY)
        if min(values) < 0:
            ax.axhline(0, color=BRAND_GRAY, linewidth=0.7)
        ax.set_title(title, loc="left")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle=":", alpha=0.4)

    fig.suptitle(
        f"What \\${price:.2f}/share implies - reverse DCF",
        fontsize=15, fontweight="bold", color=BRAND_NAVY,
        ha="left", x=0.04, y=1.02,
    )
    fig.tight_layout()
    return save(fig, "reverse_comparison", today)


def main():
    df_silver = m.load_silver()
    last_fy   = df_silver.index.max()
    last_rev  = df_silver.loc[last_fy, "revenue"]

    md = m.get_market_data()
    price = md["price"]
    shares_out = md["shares"] or df_silver.loc[last_fy, "shares_out"]

    wacc    = m.calc_wacc()
    df_proj = m.project(last_rev, last_fy, wacc)

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for fn, args in [
        (chart_sensitivity,         (df_proj, shares_out, price, today)),
        (chart_revenue_projection,  (df_silver, df_proj, today)),
        (chart_reverse_comparison,  (df_silver, last_rev, last_fy, wacc, shares_out, price, today)),
    ]:
        out = fn(*args)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
