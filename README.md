# Lululemon DCF Pipeline

A full-stack 5-year discounted cash flow valuation of **Lululemon Athletica (NASDAQ: LULU)**, built as a real data engineering pipeline rather than a one-off spreadsheet.

Part of the [Forecasting & Finance Suite](https://leahkatinsights.com) - a portfolio of finance projects that double as data engineering exercises.

## Architecture

```
SEC EDGAR  ─►  Lambda (XBRL pull)        →  Bronze (raw JSON)
                       │
                       ▼
              Python parser + tag normalization  →  Silver (Parquet, year × concept)
                       │
                       ▼
              DuckDB SQL window functions        →  Gold (trends, rolling avgs, ranks)
                       │
                       ▼
              DCF model + sensitivity + reverse  →  Gold (valuation, charts)
```

Same SQL is portable to a Databricks Delta Lake medallion architecture - only the connection layer changes.

## Phase status

| # | Phase | Tool | Status |
|---|---|---|---|
| 1 | SEC EDGAR ingest → Bronze | Lambda-shaped Python, urllib | ✅ |
| 2 | XBRL parse → Silver | pandas + pyarrow | ✅ |
| 3 | Historical SQL → Gold | DuckDB (Databricks-portable) | ✅ |
| 4 | DCF model (FCFF, WACC, TV) | numpy + pandas | ✅ |
| 5 | Charts (sensitivity, projection, reverse) | matplotlib | ✅ |
| 6 | Reverse DCF | scipy.optimize.brentq | ✅ |
| 7 | Bear / base / bull scenarios | - | ✅ |

## Quickstart

```bash
export SEC_USER_AGENT="Your Name you@example.com"

python ingest.py        # phase 1 - pull from SEC EDGAR → bronze
python silver.py        # phase 2 - XBRL → year-indexed Parquet
python gold.py          # phase 3 - SQL window functions → trends
python dcf.py           # phase 4 + 5 - base-case valuation, charts, sensitivity
python reverse_dcf.py   # phase 6 - what does the market price imply?
python scenarios.py     # phase 7 - bear / base / bull comparison
python viz.py           # rebuild all charts

python view_data.py     # inspect any layer; --help for options
```

## Headline output (FY2025 anchor, May 2026 spot)

Live LULU price: **$133.58**

| Scenario | 5-yr CAGR | Avg op-margin | $/share intrinsic | vs market |
|---|---|---|---|---|
| Bear  | 2.1% | 17.9% | $135 | +1% |
| **Base**  | **5.2%** | **21.6%** | **$179** | **+34%** |
| Bull  | 8.4% | 22.9% | $213 | +59% |

**Reverse DCF - what $134 implies:**
- Revenue CAGR: -4% (revenue *decline*)
- Op margin: 16.5% (further compression below FY25)
- Implied WACC: 15.4% (β = 2.05 vs actual ~1.4)

The market is simultaneously pricing in revenue contraction, margin compression, and a distressed-level discount rate.

## Why `companyfacts`?

SEC requires all filings in XBRL - structured XML where every line item is tagged (`us-gaap:Revenues`, etc.). The `companyfacts` endpoint returns every XBRL fact a company has ever reported in a single JSON, already structured. No PDF parsing, no per-filing iteration.

## Why this is a DE project, not a finance project

Same valuation could be done in Excel in an afternoon. The point is the pipeline:

- **Bronze / Silver / Gold** medallion architecture on S3 (or local Parquet)
- **SQL window functions** in DuckDB / Databricks (LAG, AVG OVER, MAX OVER, RANK)
- **Reusable concept normalizer** - `CONCEPT_MAP` in `silver.py` makes the parser portable to NKE / ADDYY / UAA without code changes
- **Lambda + EventBridge** for scheduled ingest as filings drop (config-as-env-var)

The finance output is the deliverable; the pipeline is the portfolio piece.

## Stack

| Layer | Tool |
|---|---|
| Ingest | Python stdlib (local) → AWS Lambda |
| Storage | S3 + Parquet (Delta Lake on Databricks port) |
| Transform | DuckDB locally, Databricks SQL warehouse for production |
| Modeling | numpy, scipy.optimize |
| Visualization | matplotlib (Inter / brand styling) |
| Live data | yfinance (current price + diluted shares) |

## Caveats

- Pre-2020 XBRL fiscal-year labels misalign for LULU (some old filings tag under different `fy` conventions). Charts and SQL filter to FY2020+ where data is reliable.
- `CASH_AND_EQUIVALENTS` and `BETA` are hardcoded snapshots; pulled from balance sheet / Yahoo respectively in v2.
- Operating leases (ASC 842) treated as operating, not as part of WACC weighting - defensible for LULU because traditional debt is essentially zero.

## License

MIT
