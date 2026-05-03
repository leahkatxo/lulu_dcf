"""LULU DCF gold - phase 3.

Runs SQL window functions over the silver parquet via DuckDB (in-process).
Same SQL is portable to Databricks SQL warehouse - only the connection
boilerplate changes (CREATE OR REPLACE TABLE silver USING DELTA on Databricks
vs. CREATE VIEW from parquet here).

Window-function flavors used:
  * LAG       - year-over-year deltas (growth rates, margin changes)
  * AVG OVER  - rolling N-year averages with ROWS BETWEEN frame
  * MAX OVER  - peak-to-current gap (margin compression vs. peak)
  * RANK      - best/worst years for revenue and margin
  * CASE      - protect against divide-by-zero in conversion ratios

Local run: python gold.py
"""

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

TICKER = "LULU"
SILVER_DIR = Path("data/silver/sec") / TICKER
GOLD_DIR = Path("data/gold/sec") / TICKER

SQL_TRENDS = """
WITH base AS (
    SELECT
        fy,
        revenue,
        gross_profit,
        operating_inc,
        net_income,
        operating_cf,
        capex,
        fcff,
        gross_margin,
        op_margin,
        net_margin
    FROM silver
    WHERE fy >= 2020  -- pre-2020 XBRL fiscal-year labels misalign for LULU
      AND revenue IS NOT NULL
)
SELECT
    fy,
    revenue,
    revenue / 1e9 AS revenue_b,

    -- Year-over-year growth via LAG (canonical window function)
    (revenue - LAG(revenue, 1) OVER w_chrono) /
        NULLIF(LAG(revenue, 1) OVER w_chrono, 0) AS yoy_growth,

    -- 3-yr and 5-yr rolling averages of revenue (frame: ROWS PRECEDING)
    AVG(revenue) OVER (ORDER BY fy ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
        / 1e9 AS rolling_3y_rev_b,
    AVG(revenue) OVER (ORDER BY fy ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
        / 1e9 AS rolling_5y_rev_b,

    -- Rolling 5-year CAGR (geometric proxy: last year / 5 years ago, ^(1/5) - 1)
    POWER(
        revenue / NULLIF(LAG(revenue, 5) OVER w_chrono, 0),
        1.0 / 5
    ) - 1 AS rolling_5y_cagr,

    -- Margin trajectory + peak comparison (MAX OVER)
    op_margin,
    op_margin - MAX(op_margin) OVER w_chrono AS op_margin_vs_peak_pp,
    AVG(op_margin) OVER (ORDER BY fy ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
        AS op_margin_5y_avg,

    -- Capex intensity & investment burden
    capex / NULLIF(revenue, 0) AS capex_intensity,

    -- FCF conversion: fraction of net income that becomes free cash
    CASE WHEN net_income > 0 THEN fcff / net_income ELSE NULL END
        AS fcf_conversion,

    -- Best/worst-year ranks across the full window
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    RANK() OVER (ORDER BY op_margin DESC) AS op_margin_rank,
    RANK() OVER (ORDER BY fcff DESC NULLS LAST) AS fcff_rank

FROM base
WINDOW w_chrono AS (ORDER BY fy)
ORDER BY fy
"""


def latest_silver():
    files = sorted(SILVER_DIR.glob("financials_*.parquet"))
    if not files:
        raise FileNotFoundError("No silver file. Run silver.py first.")
    return files[-1]


def main():
    silver_path = latest_silver()

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW silver AS SELECT * FROM '{silver_path}'")
    df = con.execute(SQL_TRENDS).df()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out = GOLD_DIR / f"trends_{today}.parquet"
    df.to_parquet(out)

    # Headline summary
    cur = df.iloc[-1]
    peak_growth_idx = df["rolling_5y_cagr"].idxmax()
    peak_growth_yr = int(df.loc[peak_growth_idx, "fy"])
    peak_growth = df.loc[peak_growth_idx, "rolling_5y_cagr"]
    peak_margin_idx = df["op_margin"].idxmax()
    peak_margin_yr = int(df.loc[peak_margin_idx, "fy"])
    peak_margin = df.loc[peak_margin_idx, "op_margin"]

    print(f"wrote {out}\n")
    print("=== Headline trend signals ===\n")
    print(f"  Rolling 5-yr CAGR peaked FY{peak_growth_yr} at {peak_growth*100:.1f}% - currently {cur['rolling_5y_cagr']*100:.1f}%")
    print(f"  Op margin peaked FY{peak_margin_yr} at {peak_margin*100:.1f}% - currently {cur['op_margin']*100:.1f}% ({cur['op_margin_vs_peak_pp']*100:+.1f}pp gap)")
    print(f"  FY{int(cur['fy'])} FCF conversion: {cur['fcf_conversion']*100:.0f}% (FCFF / NetIncome)")
    print(f"  Capex intensity: {cur['capex_intensity']*100:.1f}% of revenue")

    print(f"\n=== Last 8 fiscal years ===\n")
    show_cols = [
        "fy", "revenue_b", "yoy_growth", "rolling_5y_cagr",
        "op_margin", "op_margin_vs_peak_pp", "capex_intensity", "fcf_conversion",
    ]
    formatters = {
        "fy":                   "{:.0f}".format,
        "revenue_b":            "${:.2f}B".format,
        "yoy_growth":           lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "-",
        "rolling_5y_cagr":      lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "-",
        "op_margin":            "{:.1%}".format,
        "op_margin_vs_peak_pp": lambda x: f"{x*100:+.1f}pp",
        "capex_intensity":      "{:.1%}".format,
        "fcf_conversion":       lambda x: f"{x*100:.0f}%" if pd.notna(x) else "-",
    }
    print(df[show_cols].tail(8).to_string(index=False, formatters=formatters))


if __name__ == "__main__":
    main()
