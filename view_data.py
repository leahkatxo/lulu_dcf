"""LULU DCF data viewer.

Quick CLI for inspecting data at any pipeline layer.

Examples:
    python view_data.py                       # default: silver, last 10 yrs, key cols
    python view_data.py silver --all          # silver with every column
    python view_data.py silver --csv out.csv  # export silver to CSV (opens in Excel)
    python view_data.py trends                # gold trends layer
    python view_data.py projection            # 5-yr forward DCF projection
    python view_data.py scenarios             # bear / base / bull side-by-side
    python view_data.py valuation             # final DCF summary JSON
    python view_data.py bronze                # list raw JSON files
    python view_data.py list                  # show every available data file
"""

import argparse
import json
from pathlib import Path

import pandas as pd

TICKER = "LULU"
DATA = Path(__file__).parent / "data"

# Most-useful columns per layer (override with --all)
KEY_COLS = {
    "silver":     ["revenue", "revenue_growth", "gross_margin", "op_margin", "net_margin", "fcff", "shares_out"],
    "trends":     ["fy", "revenue_b", "yoy_growth", "rolling_5y_cagr", "op_margin", "op_margin_vs_peak_pp", "fcf_conversion"],
    "projection": ["rev", "growth", "op_margin", "nopat", "fcff", "pv_fcff"],
    "scenarios":  ["name", "5y_cagr", "avg_op_margin", "ev", "equity", "per_share", "upside_pct"],
}


def latest(layer_dir, prefix):
    files = sorted(layer_dir.glob(f"{prefix}_*.parquet"))
    if not files:
        raise SystemExit(f"No {prefix} files in {layer_dir}. Run the pipeline first.")
    return files[-1]


def trim(df, key_cols, years_tail=None, all_cols=False):
    if not all_cols:
        cols = [c for c in key_cols if c in df.columns]
        if cols:
            df = df[cols]
    if years_tail and len(df) > years_tail:
        df = df.tail(years_tail)
    return df


def cmd_silver(args):
    path = latest(DATA / "silver/sec" / TICKER, "financials")
    df = pd.read_parquet(path)
    df = df[df.index >= 2020]  # post-COVID era is the clean data window
    df = trim(df, KEY_COLS["silver"], args.years, args.all)
    print(f"# Silver: {path.name}\n")
    print(df.to_string())
    return df


def cmd_trends(args):
    path = latest(DATA / "gold/sec" / TICKER, "trends")
    df = pd.read_parquet(path)
    df = trim(df, KEY_COLS["trends"], args.years, args.all)
    print(f"# Gold trends: {path.name}\n")
    print(df.to_string(index=False))
    return df


def cmd_projection(args):
    path = latest(DATA / "gold/sec" / TICKER, "projection")
    df = pd.read_parquet(path)
    df = trim(df, KEY_COLS["projection"], None, args.all)
    print(f"# Gold projection: {path.name}\n")
    print(df.to_string())
    return df


def cmd_scenarios(args):
    path = latest(DATA / "gold/sec" / TICKER, "scenarios")
    df = pd.read_parquet(path)
    df = trim(df, KEY_COLS["scenarios"], None, args.all)
    print(f"# Gold scenarios: {path.name}\n")
    print(df.to_string(index=False))
    return df


def cmd_valuation(args):
    files = sorted((DATA / "gold/sec" / TICKER).glob("valuation_*.json"))
    if not files:
        raise SystemExit("No valuation files. Run dcf.py first.")
    path = files[-1]
    print(f"# Gold valuation: {path.name}\n")
    print(json.dumps(json.loads(path.read_text()), indent=2))
    return None


def cmd_bronze(args):
    bronze = DATA / "bronze/sec" / TICKER
    print(f"# Bronze: raw JSON in {bronze}\n")
    if not bronze.exists():
        print("  (no files; run ingest.py)")
        return None
    for f in sorted(bronze.glob("*.json")):
        kb = f.stat().st_size / 1024
        print(f"  {f.name:<40} {kb:>7,.0f} KB")
    print("\nView a file:")
    print(f"  jq . {bronze}/dcf_concepts_*.json | less")
    print(f"  open {bronze}")
    return None


def cmd_list(args):
    print(f"# All data files under {DATA}\n")
    if not DATA.exists():
        print("  (no data dir; run the pipeline)")
        return None
    for f in sorted(DATA.rglob("*")):
        if f.is_file():
            kb = f.stat().st_size / 1024
            print(f"  {f.relative_to(DATA)!s:<60} {kb:>7,.0f} KB")
    return None


COMMANDS = {
    "silver":     cmd_silver,
    "trends":     cmd_trends,
    "projection": cmd_projection,
    "scenarios":  cmd_scenarios,
    "valuation":  cmd_valuation,
    "bronze":     cmd_bronze,
    "list":       cmd_list,
}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "layer",
        nargs="?",
        default="silver",
        choices=list(COMMANDS.keys()),
        help="data layer to view (default: silver)",
    )
    parser.add_argument("--all",   action="store_true", help="show every column, not just the key ones")
    parser.add_argument("--years", type=int, default=10, help="show only the last N years (default: 10)")
    parser.add_argument("--csv",   type=Path, help="also export the table to CSV (opens cleanly in Excel)")
    args = parser.parse_args()

    pd.options.display.max_columns = None
    pd.options.display.width = 200

    df = COMMANDS[args.layer](args)
    if args.csv and df is not None:
        df.to_csv(args.csv)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
