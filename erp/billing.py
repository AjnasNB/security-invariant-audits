"""Read-only Azure Cost Management queries; private resource IDs never published."""
import json
import argparse
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PRIVATE = Path(__file__).resolve().parent / "private"
AZURE_PYTHON = os.environ.get("STUDY_AZURE_PYTHON")


def az(args):
    command = [AZURE_PYTHON, "-IBm", "azure.cli"] if AZURE_PYTHON else ["az"]
    result = subprocess.run([*command, *args, "-o", "json"],
                            capture_output=True, text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        raise RuntimeError("Azure CLI query unavailable: " + result.stderr[-500:])
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=("all", "september", "october-1"), default="all")
    args = parser.parse_args()
    PRIVATE.mkdir(exist_ok=True)
    account = az(["account", "show"])
    token = az(["account", "get-access-token", "--resource", "https://management.azure.com/"])["accessToken"]
    base = "https://management.azure.com/subscriptions/" + account["id"]
    prior = PRIVATE / "billing-summary.json"
    outputs = json.loads(prior.read_text()) if prior.exists() else {}
    for label, start, end in [("october-1", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
                              ("september", "2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z")]:
        if args.period != "all" and label != args.period:
            continue
        payload = {"type": "ActualCost", "timeframe": "Custom",
                   "timePeriod": {"from": start, "to": end},
                   "dataset": {"granularity": "None",
                               "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                               "grouping": [{"type": "Dimension", "name": "ServiceName"},
                                            {"type": "Dimension", "name": "ResourceId"}]}}
        req = urllib.request.Request(base + "/providers/Microsoft.CostManagement/query?api-version=2023-03-01",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                                     method="POST")
        try:
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        result = json.load(response)
                    break
                except urllib.error.HTTPError as error:
                    if error.code != 429 or attempt:
                        raise
                    delay = error.headers.get("Retry-After", "15")
                    if not delay.isdigit() or int(delay) > 30:
                        raise
                    time.sleep(int(delay))
            (PRIVATE / ("azure-cost-" + label + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
            properties = result["properties"]
            columns = [row["name"] for row in properties["columns"]]
            records = [dict(zip(columns, row)) for row in properties["rows"]]
            cost_column = next((column for column in columns if "cost" in column.lower()), None)
            ai = [row for row in records if any(word in (str(row.get("ServiceName", "")) + str(row.get("ResourceId", ""))).lower()
                                               for word in ("cognitive", "openai", "foundry", "/accounts/erpseeker-ai", "/accounts/astra-guard"))]
            outputs[label] = {"period": {"from": start, "to": end}, "available": True,
                              "subscription_posted_cost": sum(float(row.get(cost_column) or 0) for row in records),
                              "ai_service_posted_cost": sum(float(row.get(cost_column) or 0) for row in ai),
                              "currency": sorted({str(row.get("Currency", "unknown")) for row in records}),
                              "rows": len(records), "ai_rows": len(ai),
                              "attribution": "Subscription/service aggregates, not uniquely attributable to this experiment",
                              "has_more_pages": bool(properties.get("nextLink"))}
        except Exception as error:
            outputs[label] = {"available": False, "reason": type(error).__name__, "error": str(error)[:400]}
    (PRIVATE / "billing-summary.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
