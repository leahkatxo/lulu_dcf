"""LULU DCF scenarios - bear / base / bull comparison.

Runs the forward DCF under three scenario configurations and produces
a side-by-side valuation table plus an FCFF projection chart.

Local run: python scenarios.py
"""

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import dcf as m

# ─── Scenario definitions ───────────────────────────────────────────────────
# Each scenario fixes the 5-year revenue growth path and operating margin
# path. WACC, tax, terminal growth, NWC %, capex %, D&A % are held common.

SCENARIOS = {
    "Bear": {
        # Continued deceleration → near-stagnation; permanent margin compression
        "growth_path": [0.020, 0.015, 0.020, 0.025, 0.025],
        "margin_path": [0.180, 0.175, 0.175, 0.180, 0.185],
        "color": "#9AA0A6",
    },
    "Base": {
        # Mid-single-digit growth, partial margin recovery toward 22%
        "growth_path": list(m.REV_GROWTH_PATH),
        "margin_path": list(m.OP_MARGIN_PATH),
        "color": "#1F2940",
    },
    "Bull": {
        # Reacceleration toward FY23-24 levels; margins recover to peak
        "growth_path": [0.080, 0.100, 0.100, 0.080, 0.060],
        "margin_path": [0.215, 0.225, 0.235, 0.235, 0.235],
        "color": "#D4829A",
    },
}


def run_one(name, params, last_rev, last_fy, wacc, shares_out, price):
    df_proj = m.project(
        last_rev, last_fy, wacc,
        growth_path=params["growth_path"],
        margin_path=params["margin_path"],
    )
    val = m.value(df_proj, wacc, m.TERMINAL_GROWTH, shares_out)
    cagr = (df_proj["rev"].iloc[-1] / last_rev) ** (1 / len(df_proj)) - 1
    avg_margin = sum(params["margin_path"]) / len(params["margin_path"])
    return {
        "name": name,
        "df_proj": df_proj,
        "5y_cagr": cagr,
        "avg_op_margin": avg_margin,
        "ev": val["enterprise_value"],
        "equity": val["equity_value"],
        "per_share": val["per_share"],
        "upside_pct": (val["per_share"] / price - 1),
    }


def chart_fcff_paths(results, today, charts_dir):
    fig, ax = plt.subplots(figsize=(11, 6))
    for r in results:
        years = list(r["df_proj"].index)
        fcff = (r["df_proj"]["fcff"] / 1e9).values
        ax.plot(years, fcff, marker="o", linewidth=2.5, markersize=6,
                color=SCENARIOS[r["name"]]["color"], label=r["name"])
    years = list(results[0]["df_proj"].index)
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_xlabel("Fiscal year")
    ax.set_ylabel("FCFF ($B)")
    ax.set_title("LULU 5-year FCFF projection - three scenarios", loc="left")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    out = charts_dir / f"scenarios_fcff_{today}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main():
    df_silver = m.load_silver()
    last_fy = df_silver.index.max()
    last_rev = df_silver.loc[last_fy, "revenue"]

    md = m.get_market_data()
    price = md["price"]
    shares_out = md["shares"] or df_silver.loc[last_fy, "shares_out"]
    wacc = m.calc_wacc()

    results = [
        run_one(name, params, last_rev, last_fy, wacc, shares_out, price)
        for name, params in SCENARIOS.items()
    ]

    print(f"\n=== {m.TICKER} DCF - bear / base / bull ===\n")
    print(f"  Anchor: FY{last_fy} revenue ${last_rev/1e9:.2f}B    "
          f"WACC {wacc:.2%}    terminal {m.TERMINAL_GROWTH:.2%}    "
          f"market price ${price:.2f}\n")

    print(f"{'Scenario':<10}{'5y CAGR':>10}{'Avg OpMrg':>12}{'EV ($B)':>11}"
          f"{'Equity ($B)':>14}{'$/share':>10}{'vs Mkt':>10}")
    print("-" * 77)
    for r in results:
        print(
            f"{r['name']:<10}"
            f"{r['5y_cagr']*100:>9.1f}%"
            f"{r['avg_op_margin']*100:>11.1f}%"
            f"{r['ev']/1e9:>11.2f}"
            f"{r['equity']/1e9:>14.2f}"
            f"{r['per_share']:>10.2f}"
            f"{r['upside_pct']*100:>+9.1f}%"
        )

    # Persist
    today = datetime.utcnow().strftime("%Y-%m-%d")
    gold = Path("data/gold/sec") / m.TICKER
    gold.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame([
        {k: r[k] for k in ["name", "5y_cagr", "avg_op_margin", "ev", "equity", "per_share", "upside_pct"]}
        for r in results
    ])
    summary.to_parquet(gold / f"scenarios_{today}.parquet", index=False)

    charts_dir = Path("data/gold/charts")
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart = chart_fcff_paths(results, today, charts_dir)
    print(f"\nwrote {gold}/scenarios_{today}.parquet")
    print(f"wrote {chart}")


if __name__ == "__main__":
    main()
