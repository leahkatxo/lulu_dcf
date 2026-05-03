# Lululemon DCF Pipeline

A 5-year discounted cash flow valuation of **Lululemon Athletica (NASDAQ: LULU)**, built as a real data engineering pipeline instead of a one-off spreadsheet.

Part of the [Forecasting & Finance Suite](https://leahkatinsights.com) - a portfolio of finance projects that double as data engineering exercises.

## Architecture

```
SEC EDGAR  ─┬─►  Lambda (XBRL pull)  ─►  S3 Bronze
            │                              │
            │                              ▼
            │                   Databricks: parse → Silver Delta
            │                              │
            │                              ▼
            │                   SQL window funcs → Gold Delta
            │                              │
            │                              ▼
            └─────────────────►   DCF model + sensitivity + reverse DCF
```

## Phase status

| # | Phase | Status |
|---|---|---|
| 1 | SEC EDGAR ingest → S3 Bronze | in progress |
| 2 | XBRL parse → Silver Delta | - |
| 3 | Historical growth/margin SQL → Gold Delta | - |
| 4 | DCF model (FCFF, WACC, terminal value) | - |
| 5 | Sensitivity heatmap | - |
| 6 | Reverse DCF (scipy.optimize) | - |

## Quickstart

Local ingest (stdlib only):

```bash
export SEC_USER_AGENT="Your Name you@example.com"
python ingest.py
```

Output:
- `data/bronze/sec/LULU/companyfacts_YYYY-MM-DD.json` - every XBRL fact LULU has reported
- `data/bronze/sec/LULU/dcf_concepts_YYYY-MM-DD.json` - filtered to the ~20 GAAP concepts needed for valuation

The handler returns a `concepts_missing` list so you can see which tags LULU reports under non-standard names.

## Why `companyfacts`?

SEC requires all filings in XBRL - structured XML where every line item is tagged (`us-gaap:Revenues`, etc.). The `companyfacts` endpoint returns every XBRL fact a company has ever reported in a single JSON, already structured. No PDF parsing, no per-filing iteration.

## Why this is a DE project, not a finance project

Same valuation could be done in Excel in an afternoon. The point is the pipeline:

- **Bronze / Silver / Gold** medallion architecture on S3 + Delta Lake
- **SQL window functions** for cohort-style historical analysis (LAG, AVG OVER, growth rates)
- **MLflow** for tracking valuation scenarios as parameter runs
- **Lambda + EventBridge** for scheduled ingest as filings drop

The finance output is the deliverable; the pipeline is the portfolio piece.

## Stack

| Layer | Tool |
|---|---|
| Ingest | Python stdlib (local) → AWS Lambda |
| Storage | S3 + Delta Lake |
| Transform | Databricks notebooks, SQL window functions |
| Valuation | scipy.optimize (reverse DCF), matplotlib (sensitivity) |
| Orchestration | EventBridge (quarterly cadence) |

## License

MIT
