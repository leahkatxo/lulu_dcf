"""LULU DCF model - phase 4.

Reads the silver financial table, projects 5 years of FCFF, discounts
at WACC, adds Gordon-growth terminal value, bridges to equity, and
produces a per-share intrinsic value plus a WACC × terminal-growth
sensitivity table.

Local run: python dcf.py
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

TICKER = "LULU"
SILVER_DIR = Path("data/silver/sec") / TICKER
GOLD_DIR = Path("data/gold/sec") / TICKER

# ─── Assumptions: base case ─────────────────────────────────────────────────

# Revenue growth path: gentle reaccel from FY25's +4.9%, taper to terminal.
# Bear/bull cases would override this list.
REV_GROWTH_PATH = [0.050, 0.060, 0.060, 0.050, 0.040]

# Operating margin: partial recovery from FY25's 19.9% toward FY24's 23.7%
OP_MARGIN_PATH = [0.205, 0.215, 0.220, 0.220, 0.220]

# Steady-state ratios (% of revenue, ~5-yr historical averages)
DA_PCT_REV    = 0.045
CAPEX_PCT_REV = 0.060
NWC_PCT_REV   = 0.10  # ΔNWC as % of ΔRevenue

TAX_RATE = 0.27  # historical effective ~27%

# WACC inputs (snapshot - update from FRED + Damodaran when refreshing)
RISK_FREE_RATE      = 0.042  # 10-yr UST
EQUITY_RISK_PREMIUM = 0.055  # Damodaran 2026
BETA                = 1.40   # LULU 5-yr levered

# Terminal value
TERMINAL_GROWTH = 0.025

# Equity bridge (TODO: pull cash from balance sheet in v2)
CASH_AND_EQUIVALENTS = 2.0e9    # LULU runs ~$1.6-2.4B
TRADITIONAL_DEBT     = 0        # LULU is essentially debt-free

# Reverse-DCF cross-check (manual snapshot - update before publishing)
CURRENT_PRICE = 280.0


def load_silver():
    files = sorted(SILVER_DIR.glob("financials_*.parquet"))
    if not files:
        raise FileNotFoundError("No silver files. Run silver.py first.")
    return pd.read_parquet(files[-1])


def calc_wacc():
    cost_of_equity = RISK_FREE_RATE + BETA * EQUITY_RISK_PREMIUM
    # No traditional debt → WACC reduces to cost of equity
    return cost_of_equity


def project(last_revenue, last_fy, wacc):
    rows = []
    rev = last_revenue
    for i, (g, op_m) in enumerate(zip(REV_GROWTH_PATH, OP_MARGIN_PATH), 1):
        prev_rev = rev
        rev = rev * (1 + g)
        op_inc     = rev * op_m
        nopat      = op_inc * (1 - TAX_RATE)
        da         = rev * DA_PCT_REV
        capex      = rev * CAPEX_PCT_REV
        change_nwc = (rev - prev_rev) * NWC_PCT_REV
        fcff       = nopat + da - capex - change_nwc
        discount   = (1 + wacc) ** i
        pv_fcff    = fcff / discount
        rows.append({
            "fy": last_fy + i,
            "rev": rev,
            "growth": g,
            "op_margin": op_m,
            "op_inc": op_inc,
            "nopat": nopat,
            "da": da,
            "capex": capex,
            "change_nwc": change_nwc,
            "fcff": fcff,
            "discount": discount,
            "pv_fcff": pv_fcff,
        })
    return pd.DataFrame(rows).set_index("fy")


def value(df_proj, wacc, terminal_growth, shares_out):
    sum_pv_fcff = df_proj["pv_fcff"].sum()
    final_fcff  = df_proj["fcff"].iloc[-1]
    tv          = final_fcff * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_tv       = tv / df_proj["discount"].iloc[-1]
    ev          = sum_pv_fcff + pv_tv
    equity      = ev + CASH_AND_EQUIVALENTS - TRADITIONAL_DEBT
    per_share   = equity / shares_out
    return {
        "sum_pv_fcff": sum_pv_fcff,
        "terminal_value": tv,
        "pv_terminal_value": pv_tv,
        "tv_pct_of_value": pv_tv / ev,
        "enterprise_value": ev,
        "equity_value": equity,
        "per_share": per_share,
    }


def sensitivity(df_proj, shares_out, wacc_range, growth_range):
    fcffs = df_proj["fcff"].values
    n = len(fcffs)
    final = fcffs[-1]
    grid = {}
    for w in wacc_range:
        for g in growth_range:
            if w <= g:
                grid[(w, g)] = float("nan")
                continue
            sum_pv = sum(f / (1 + w) ** (i + 1) for i, f in enumerate(fcffs))
            tv = final * (1 + g) / (w - g)
            pv_tv = tv / (1 + w) ** n
            equity = (sum_pv + pv_tv) + CASH_AND_EQUIVALENTS - TRADITIONAL_DEBT
            grid[(w, g)] = equity / shares_out
    return pd.DataFrame(
        {f"g={g:.1%}": [grid[(w, g)] for w in wacc_range] for g in growth_range},
        index=[f"WACC={w:.1%}" for w in wacc_range],
    )


def main():
    df_silver = load_silver()
    last_fy = df_silver.index.max()
    last_rev = df_silver.loc[last_fy, "revenue"]
    shares_out = df_silver.loc[last_fy, "shares_out"]
    if pd.isna(shares_out):
        shares_out = 121e6  # fallback
        print("  warning: shares_out missing in silver, using 121M fallback")

    wacc = calc_wacc()
    df_proj = project(last_rev, last_fy, wacc)
    val = value(df_proj, wacc, TERMINAL_GROWTH, shares_out)

    print(f"\n=== {TICKER} DCF - Base Case ===\n")
    print(f"Anchored on FY{last_fy} revenue:        ${last_rev/1e9:.2f}B")
    print(f"Cost of equity (= WACC, no debt):    {wacc:.2%}")
    print(f"Terminal growth:                     {TERMINAL_GROWTH:.2%}")
    print(f"Shares outstanding:                  {shares_out/1e6:.1f}M")

    print(f"\n=== 5-year projection ===\n")
    print(f"{'FY':<6}{'Rev $B':>10}{'Growth':>8}{'OpMrg':>8}{'NOPAT $B':>11}{'FCFF $B':>10}{'PV FCFF $B':>13}")
    for fy, row in df_proj.iterrows():
        print(
            f"{fy:<6}"
            f"{row['rev']/1e9:>10.2f}"
            f"{row['growth']*100:>7.1f}%"
            f"{row['op_margin']*100:>7.1f}%"
            f"{row['nopat']/1e9:>11.2f}"
            f"{row['fcff']/1e9:>10.2f}"
            f"{row['pv_fcff']/1e9:>13.2f}"
        )

    print(f"\n=== Valuation bridge ===\n")
    print(f"Sum of PV(FCFF) over 5 yrs:    ${val['sum_pv_fcff']/1e9:>7.2f}B")
    print(f"Terminal value (undiscounted): ${val['terminal_value']/1e9:>7.2f}B")
    print(f"PV of terminal value:          ${val['pv_terminal_value']/1e9:>7.2f}B  ({val['tv_pct_of_value']:.0%} of EV)")
    print(f"Enterprise value:              ${val['enterprise_value']/1e9:>7.2f}B")
    print(f"  + Cash:                      ${CASH_AND_EQUIVALENTS/1e9:>7.2f}B")
    print(f"  - Traditional debt:          ${TRADITIONAL_DEBT/1e9:>7.2f}B")
    print(f"Equity value:                  ${val['equity_value']/1e9:>7.2f}B")

    print(f"\nIntrinsic value / share:       ${val['per_share']:>7.2f}")
    print(f"Current price:                 ${CURRENT_PRICE:>7.2f}")
    upside = (val['per_share'] / CURRENT_PRICE - 1) * 100
    print(f"Implied upside / (downside):    {upside:>+6.1f}%")

    print(f"\n=== Sensitivity: $ per share ===\n")
    wacc_range   = [0.10, 0.11, 0.12, 0.13, 0.14]
    growth_range = [0.020, 0.025, 0.030, 0.035]
    sens = sensitivity(df_proj, shares_out, wacc_range, growth_range)
    print(sens.map(lambda x: f"${x:,.0f}" if pd.notna(x) else "-").to_string())

    # Persist to gold
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    df_proj.to_parquet(GOLD_DIR / f"projection_{today}.parquet")
    sens.to_parquet(GOLD_DIR / f"sensitivity_{today}.parquet")
    summary = {
        "ticker": TICKER,
        "valuation_date": today,
        "anchor_fy": int(last_fy),
        "anchor_revenue": float(last_rev),
        "wacc": wacc,
        "terminal_growth": TERMINAL_GROWTH,
        "shares_out": float(shares_out),
        **{k: float(v) for k, v in val.items()},
        "current_price": CURRENT_PRICE,
        "upside_pct": upside / 100,
    }
    (GOLD_DIR / f"valuation_{today}.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {GOLD_DIR}/projection_{today}.parquet, sensitivity, valuation.json")


if __name__ == "__main__":
    main()
