"""Consolidate recorded experiment costs; no claim of an invoice reconciliation."""
import json
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from erp.manage import ROOT, PRIVATE

def rates(model):
    return (5, .5, 25, 6.25) if model == "claude-opus-5" else (2, .1, 10, 2.5)


def normalize(raw, claude=False):
    if claude:
        cached = int(raw.get("cache_read_input_tokens") or 0)
        written = int(raw.get("cache_creation_input_tokens") or 0)
        return {"input_tokens": int(raw.get("input_tokens") or 0) + cached + written,
                "output_tokens": int(raw.get("output_tokens") or 0), "cached_tokens": cached,
                "cache_write_tokens": written}
    return {"input_tokens": int(raw.get("input_tokens") or 0), "output_tokens": int(raw.get("output_tokens") or 0),
            "cached_tokens": int((raw.get("input_tokens_details") or {}).get("cached_tokens") or 0),
            "cache_write_tokens": int((raw.get("input_tokens_details") or {}).get("cache_write_tokens") or 0)}


def price(usage, model):
    inp, cached_rate, output, write = rates(model)
    cached = min(usage["cached_tokens"], usage["input_tokens"])
    uncached = usage["input_tokens"] - cached
    written = min(usage["cache_write_tokens"], uncached)
    base = (uncached * inp + cached * cached_rate + usage["output_tokens"] * output) / 1e6
    return base, base + written * (write - inp) / 1e6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path,
                        help="Parent directory containing retained Delta/cross-harness evidence")
    parser.add_argument("--original-root", required=True, type=Path,
                        help="Original study folder containing reports/cost-accounting.json")
    args = parser.parse_args()
    evidence_root, original_root = args.evidence_root, args.original_root
    records = []
    old = json.loads((original_root / "reports" / "cost-accounting.json").read_text())
    for batch in old["batches"]:
        if batch.get("requests", 0):
            usage = {key: int(batch.get(key, 0)) for key in
                     ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")}
            base, estimate = price(usage, "gpt-6.1-sol")
            records.append({"group": "original-research", "batch": batch["batch"], "model": "gpt-6.1-sol",
                "requests": batch["requests"], **usage, "base_estimate_usd": base,
                "cache_write_estimate_usd": estimate, "status": batch.get("error") or "recorded"})
    seen = set()
    unknown = []

    def ingest(path, group, model, response_id):
        value = json.loads(path.read_text())
        identifier = value.get(response_id)
        key = (model, identifier) if identifier else (model, str(path))
        if key in seen:
            return
        seen.add(key)
        raw = value.get("usage")
        if not raw:
            unknown.append({"group": group, "path": path.name, "status": value.get("http_status", value.get("httpStatus"))})
            return
        usage = normalize(raw, model.startswith("claude"))
        base, estimate = price(usage, model)
        records.append({"group": group, "batch": path.parent.name, "model": model,
                        "requests": 1, **usage, "base_estimate_usd": base,
                        "cache_write_estimate_usd": estimate})

    cross = evidence_root / "harness-comparison-20261001" / "runs"
    for path in sorted(cross.rglob("provider-*-metadata.json")):
        model = "claude-opus-5" if "claude" in str(path).lower() else "gpt-6.1-sol"
        ingest(path, "cross-harness-including-preflights", model, "response_id")
    delta = evidence_root / "delta-fixes-20261001"
    for path in sorted((delta / "live-runs").rglob("metadata-*.json")):
        ingest(path, "delta-product-fixes", "gpt-6.1-sol", "responseId")
    # These are distinct paid smoke calls, not duplicate report files.
    for directory in ("desktop-smoke-v2", "desktop-final", "codex-smoke"):
        value = json.loads((delta / directory / "result.json").read_text())
        raw = value["liveTask"]["usage"] if "liveTask" in value else value["usage"]
        usage = {"input_tokens": raw["inputTokens"], "output_tokens": raw["outputTokens"],
                 "cached_tokens": raw["cachedTokens"], "cache_write_tokens": 0}
        base, estimate = price(usage, "gpt-6.1-sol")
        records.append({"group": "delta-connection-smokes", "batch": directory, "model": "gpt-6.1-sol",
            "requests": raw["modelCalls"], **usage, "base_estimate_usd": base,
            "cache_write_estimate_usd": estimate, "cache_write_metadata_unavailable": True})
    for path in sorted((ROOT / "erp/runs").rglob("metadata-*.json")):
        ingest(path, "full-ERP-extension", "gpt-6.1-sol", "responseId")
    groups = defaultdict(lambda: defaultdict(float))
    for row in records:
        for key in ("requests", "input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens",
                    "base_estimate_usd", "cache_write_estimate_usd"):
            groups[row["group"]][key] += row[key]
    totals = {key: sum(group[key] for group in groups.values()) for key in next(iter(groups.values()))}
    billing = json.loads((PRIVATE / "billing-summary.json").read_text())
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "groups": dict(groups), "totals": totals,
        "record_count": len(records), "unknown_usage_attempts": unknown,
        "public_reference_rates": {"gpt-6.1-sol": {"input": 2, "cached": .1, "output": 10, "cache_write": 2.5},
                                   "claude-opus-5": {"input": 5, "cached": .5, "output": 25, "cache_write": 6.25}},
        "currency": "USD", "pricing_status": "Reference token estimate, not verified Azure invoice",
        "cache_write_assumption": "Cache writes are a subset of uncached input; replace ordinary charge with 1.25x, do not double count.",
        "azure_posted_billing": billing,
        "scope": "Observed SUTD experiment/provider calls, preflights and Delta smoke calls. Excludes this Codex desktop conversation and unrelated Azure workloads.",
        "limitations": ["Possible interrupted unreported calls; metadata missing for some attempts",
                       "Claude Opus 5 public pricing checked October 1; actual Azure offer/cache lifetime can differ",
                       "GPT prompts are below the long-context price threshold in these batches",
                       "Subscription charges cannot be attributed solely to this study",
                       "No new cloud ERP infrastructure was provisioned; the ERP ran locally",
                       "No credit, tax, invoice or exchange-rate reconciliation"] }
    report["pricing_sources"] = ["https://developers.openai.com/api/docs/models/gpt-6.1-sol",
                                 "https://platform.claude.com/docs/en/about-claude/pricing"]
    (ROOT / "reports" / "all-experiment-costs.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (PRIVATE / "cost-records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(json.dumps({"groups": report["groups"], "totals": totals, "unknown_attempts": len(unknown)}, indent=2))


if __name__ == "__main__":
    main()
