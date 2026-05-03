"""LULU reverse DCF - phase 6.

Holds base-case margins, WACC, and terminal growth fixed and solves
(scipy.optimize.brentq) for the constant 5-yr revenue CAGR that
makes the model output equal the current market price.

Local run: python reverse_dcf.py
"""

from scipy.optimize import brentq

import dcf as m  # reuse forward-DCF logic + assumptions


def implied_growth(target_price, last_rev, last_fy, wacc, shares_out):
    n = len(m.REV_GROWTH_PATH)

    def gap(g):
        df_proj = m.project(last_rev, last_fy, wacc, growth_path=[g] * n)
        v = m.value(df_proj, wacc, m.TERMINAL_GROWTH, shares_out)
        return v["per_share"] - target_price

    return brentq(gap, -0.10, 0.30)


def implied_margin(target_price, last_rev, last_fy, wacc, shares_out):
    """Steady-state op margin (applied to all 5 years) implied by price."""
    n = len(m.OP_MARGIN_PATH)

    def gap(op_m):
        df_proj = m.project(last_rev, last_fy, wacc, margin_path=[op_m] * n)
        v = m.value(df_proj, wacc, m.TERMINAL_GROWTH, shares_out)
        return v["per_share"] - target_price

    return brentq(gap, 0.05, 0.40)


def implied_wacc(target_price, last_rev, last_fy, shares_out):
    """WACC implied by the price, holding all other assumptions at base."""
    def gap(w):
        df_proj = m.project(last_rev, last_fy, w)
        v = m.value(df_proj, w, m.TERMINAL_GROWTH, shares_out)
        return v["per_share"] - target_price

    return brentq(gap, 0.05, 0.20)


def main():
    df_silver = m.load_silver()
    last_fy = df_silver.index.max()
    last_rev = df_silver.loc[last_fy, "revenue"]
    shares_out = df_silver.loc[last_fy, "shares_out"]

    wacc = m.calc_wacc()
    price = m.CURRENT_PRICE

    g = implied_growth(price, last_rev, last_fy, wacc, shares_out)
    om = implied_margin(price, last_rev, last_fy, wacc, shares_out)
    w = implied_wacc(price, last_rev, last_fy, shares_out)

    # Reference points from history
    hist_growths = df_silver["revenue_growth"].dropna()
    hist_op_margins = df_silver["op_margin"].dropna()
    fy25_growth = df_silver.loc[last_fy, "revenue_growth"]
    fy25_op_m = df_silver.loc[last_fy, "op_margin"]

    print(f"\n=== {m.TICKER} reverse DCF - what does ${price:.0f} imply? ===\n")
    print("Anchor: holding all other base-case assumptions fixed, solve for ONE\n"
          "parameter that makes the model output equal the current price.\n")

    print("─── implied constant 5-yr revenue CAGR ───")
    print(f"  Market is pricing in:        {g*100:>5.1f}%")
    print(f"  My base case avg:            {sum(m.REV_GROWTH_PATH)/len(m.REV_GROWTH_PATH)*100:>5.1f}%")
    print(f"  FY{last_fy} actual:               {fy25_growth*100:>5.1f}%")
    print(f"  Last 5-yr avg:               {hist_growths.tail(5).mean()*100:>5.1f}%")
    print(f"  Last 10-yr avg:              {hist_growths.tail(10).mean()*100:>5.1f}%")

    print("\n─── implied flat operating margin ───")
    print(f"  Market is pricing in:        {om*100:>5.1f}%")
    print(f"  FY{last_fy} actual:               {fy25_op_m*100:>5.1f}%")
    print(f"  FY24 peak:                   {df_silver.loc[last_fy-1, 'op_margin']*100:>5.1f}%")
    print(f"  Last 5-yr avg:               {hist_op_margins.tail(5).mean()*100:>5.1f}%")

    print("\n─── implied WACC ───")
    print(f"  Market is pricing in:        {w*100:>5.1f}%")
    print(f"  My base case (CAPM):         {wacc*100:>5.1f}%")
    print(f"  Implied beta @ ERP=5.5%:     {(w - m.RISK_FREE_RATE) / m.EQUITY_RISK_PREMIUM:>5.2f}")

    print("\n=== Story ===\n")
    if g > fy25_growth + 0.03:
        print(f"  Market believes FY{last_fy}'s {fy25_growth*100:.1f}% deceleration is CYCLICAL - pricing in")
        print(f"  reaccel back to {g*100:.1f}% CAGR (vs. base case {sum(m.REV_GROWTH_PATH)/len(m.REV_GROWTH_PATH)*100:.1f}%).")
    elif g < fy25_growth - 0.01:
        print(f"  Market expects further deceleration below FY{last_fy}'s {fy25_growth*100:.1f}%.")
    else:
        print(f"  Market roughly accepts FY{last_fy}'s {fy25_growth*100:.1f}% growth as the new run-rate.")


if __name__ == "__main__":
    main()
