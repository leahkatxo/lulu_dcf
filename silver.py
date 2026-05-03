"""LULU DCF silver - phase 2.

Reads the bronze companyfacts dump, normalizes XBRL tag variants into
logical concept names, computes derived DCF metrics (margins, growth,
NWC, FCFF), and persists as a year-indexed Parquet table.

Local run: python silver.py
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

TICKER = "LULU"
BRONZE_DIR = Path("data/bronze/sec") / TICKER
SILVER_DIR = Path("data/silver/sec") / TICKER

# Logical name → priority list of XBRL tags. First hit wins per company,
# so the same parser works across LULU, NKE, ADDYY, UAA without edits.
CONCEPT_MAP = {
    "revenue":        ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "cogs":           ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "gross_profit":   ["GrossProfit"],
    "sga":            ["SellingGeneralAndAdministrativeExpense"],
    "operating_inc":  ["OperatingIncomeLoss"],
    "tax_expense":    ["IncomeTaxExpenseBenefit"],
    "net_income":     ["NetIncomeLoss"],
    "da":             ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "capex":          ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "sbc":            ["ShareBasedCompensation"],
    "operating_cf":   ["NetCashProvidedByUsedInOperatingActivities"],
    "receivables":    ["ReceivablesNetCurrent", "AccountsReceivableNetCurrent"],
    "inventory":      ["InventoryNet"],
    "payables":       ["AccountsPayableCurrent"],
    "ppe_net":        ["PropertyPlantAndEquipmentNet"],
    "lt_debt":        ["LongTermDebtNoncurrent", "LongTermDebt"],
    "st_borrowings":  ["ShortTermBorrowings"],
    "op_lease_st":    ["OperatingLeaseLiabilityCurrent"],
    "op_lease_lt":    ["OperatingLeaseLiabilityNoncurrent"],
    "rou_asset":      ["OperatingLeaseRightOfUseAsset"],
    "shares_out":     ["CommonStockSharesOutstanding"],
}


def latest_bronze_file():
    files = sorted(BRONZE_DIR.glob("dcf_concepts_*.json"))
    if not files:
        raise FileNotFoundError("No bronze files. Run ingest.py first.")
    return files[-1]


def fy_value(concept_data, fy):
    """Latest-filed FY 10-K value for a fiscal year (handles restatements)."""
    units = concept_data.get("units", {})
    series = units.get("USD") or units.get("shares") or []
    candidates = [
        r for r in series
        if r.get("form") == "10-K" and r.get("fp") == "FY" and r.get("fy") == fy
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: r["filed"])[-1]["val"]


def all_fys(facts):
    fys = set()
    for concept_data in facts.values():
        units = concept_data.get("units", {})
        series = units.get("USD") or units.get("shares") or []
        for r in series:
            if r.get("form") == "10-K" and r.get("fp") == "FY":
                fys.add(r["fy"])
    return sorted(fys)


def build_silver(bronze_path):
    facts = json.loads(bronze_path.read_text())
    fys = all_fys(facts)

    rows = []
    for fy in fys:
        row = {"fy": fy}
        for logical, tags in CONCEPT_MAP.items():
            val = None
            for tag in tags:
                if tag in facts:
                    val = fy_value(facts[tag], fy)
                    if val is not None:
                        break
            row[logical] = val
        rows.append(row)

    df = pd.DataFrame(rows).set_index("fy").sort_index()

    # Margins + growth
    df["revenue_growth"]  = df["revenue"].pct_change()
    df["gross_margin"]    = df["gross_profit"]  / df["revenue"]
    df["op_margin"]       = df["operating_inc"] / df["revenue"]
    df["net_margin"]      = df["net_income"]    / df["revenue"]
    df["capex_pct_rev"]   = df["capex"]         / df["revenue"]
    df["da_pct_rev"]      = df["da"]            / df["revenue"]

    # Working capital (operating only - receivables + inventory - payables)
    df["nwc"] = (
        df["receivables"].fillna(0)
        + df["inventory"].fillna(0)
        - df["payables"].fillna(0)
    )
    df["change_in_nwc"] = df["nwc"].diff()

    # Effective tax rate - derived from pretax income
    df["pretax_income"]      = df["net_income"] + df["tax_expense"]
    df["effective_tax_rate"] = df["tax_expense"] / df["pretax_income"]

    # FCFF = NOPAT + D&A - Capex - ΔNWC
    df["nopat"] = df["operating_inc"] * (1 - df["effective_tax_rate"])
    df["fcff"]  = df["nopat"] + df["da"] - df["capex"] - df["change_in_nwc"]

    return df


def print_summary(df):
    print(f"\nshape: {df.shape}    years: {df.index.min()} → {df.index.max()}\n")
    print("=== last 5 fiscal years ===\n")
    print(f"{'FY':<6}{'Rev $B':>9}{'Growth':>9}{'Gross':>8}{'Op':>8}{'Net':>8}{'NOPAT $B':>11}{'FCFF $B':>10}")
    for fy, row in df.tail().iterrows():
        growth = f"{row['revenue_growth']*100:+.1f}%" if pd.notna(row['revenue_growth']) else "  -"
        fcff   = f"{row['fcff']/1e9:.2f}" if pd.notna(row['fcff']) else "  -"
        print(
            f"{fy:<6}"
            f"{row['revenue']/1e9:>9.2f}"
            f"{growth:>9}"
            f"{row['gross_margin']*100:>7.1f}%"
            f"{row['op_margin']*100:>7.1f}%"
            f"{row['net_margin']*100:>7.1f}%"
            f"{row['nopat']/1e9:>11.2f}"
            f"{fcff:>10}"
        )


def main():
    bronze_path = latest_bronze_file()
    df = build_silver(bronze_path)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out = SILVER_DIR / f"financials_{today}.parquet"
    df.to_parquet(out)

    print(f"wrote {out}")
    print_summary(df)


if __name__ == "__main__":
    main()
