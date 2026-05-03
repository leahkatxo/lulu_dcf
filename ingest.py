"""LULU DCF ingest - phase 1.

Pulls Lululemon's XBRL facts from SEC EDGAR's companyfacts endpoint
and saves both the raw JSON and a filtered DCF-relevant subset.

Local run:    SEC_USER_AGENT="Your Name email@example.com" python ingest.py
Lambda:       handler = ingest.lambda_handler
              env: SEC_USER_AGENT, BUCKET
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

TICKER = "LULU"
USER_AGENT = os.environ["SEC_USER_AGENT"]  # SEC blocks requests without identifying UA
BUCKET = os.environ.get("BUCKET")

DCF_CONCEPTS = [
    # Income statement
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfGoodsAndServicesSold",
    "GrossProfit",
    "SellingGeneralAndAdministrativeExpense",
    "OperatingIncomeLoss",
    "IncomeTaxExpenseBenefit",
    "NetIncomeLoss",
    # Cash flow
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "PaymentsToAcquirePropertyPlantAndEquipment",  # capex
    "ShareBasedCompensation",
    "NetCashProvidedByUsedInOperatingActivities",
    # Balance sheet (working capital + capital structure)
    "AccountsReceivableNetCurrent",
    "InventoryNet",
    "AccountsPayableCurrent",
    "PropertyPlantAndEquipmentNet",
    "LongTermDebt",
    "CommonStockSharesOutstanding",
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def lookup_cik(ticker):
    data = get("https://www.sec.gov/files/company_tickers.json")
    for entry in data.values():
        if entry["ticker"] == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"ticker {ticker} not found")


def fetch_company_facts(cik):
    return get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")


def extract_concepts(facts, concepts):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    return {c: gaap[c] for c in concepts if c in gaap}


def write_output(filename, data):
    body = json.dumps(data, indent=2)
    key = f"bronze/sec/{TICKER}/{filename}"
    if BUCKET:
        import boto3
        boto3.client("s3").put_object(
            Bucket=BUCKET, Key=key, Body=body, ContentType="application/json"
        )
        return f"s3://{BUCKET}/{key}"
    out = Path("data") / key
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    return str(out)


def lambda_handler(event, context):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cik = lookup_cik(TICKER)
    facts = fetch_company_facts(cik)
    extracted = extract_concepts(facts, DCF_CONCEPTS)

    raw_path = write_output(f"companyfacts_{today}.json", facts)
    dcf_path = write_output(f"dcf_concepts_{today}.json", extracted)

    return {
        "statusCode": 200,
        "ticker": TICKER,
        "cik": cik,
        "raw": raw_path,
        "filtered": dcf_path,
        "concepts_found": list(extracted.keys()),
        "concepts_missing": [c for c in DCF_CONCEPTS if c not in extracted],
    }


if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2))
