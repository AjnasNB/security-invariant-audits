"""Generate correction/cost summaries from retained evidence, without API calls."""
from research.io import ROOT, read_json, utc_now, write_json
from research.scoring import SCORER_VERSION


def priced(usage):
    inputs, cached = usage["input_tokens"], usage["cached_tokens"]
    outputs, written = usage["output_tokens"], usage["cache_write_tokens"]
    base = ((inputs - cached) * 2 + cached * .1 + outputs * 10) / 1_000_000
    reference = base + written * .5 / 1_000_000
    if abs(reference - usage["reference_estimate_usd"]) > 1e-9:
        raise RuntimeError("New experiment reference cost does not reconcile")
    return {**usage, "base_estimate_usd": base, "cache_write_estimate_usd": reference}


def main():
    reassessment = read_json(ROOT / "reports/reassessment-v4-executed.json")
    rows = reassessment["records"]
    before = read_json(ROOT / "reports/checker-probes-before.json")
    after = read_json(ROOT / "reports/checker-probes-after.json")
    probes = []
    for first, second in zip(before["probes"], after["probes"]):
        if first["probe"] != second["probe"]:
            raise RuntimeError("Before/after probe identities do not match")
        probes.append({
            "probe": first["probe"],
            "before": {key: first["score"].get(key) for key in
                       ("passed", "security_failures", "invalid_outputs", "invariant_preserved")},
            "after": {key: second["score"].get(key) for key in
                      ("passed", "security_failures", "invalid_outputs", "invariant_preserved")},
        })
    controls = read_json(ROOT / "reports/ordinary-controls-v1.json")
    record = {
        "recorded_at": utc_now(), "scorer_version": SCORER_VERSION,
        "four_review_findings_reproduced": len(probes), "probes": probes,
        "not_model_or_paper_failures": True,
        "historical_saved_files": len(rows),
        "historical_completed_refactors": sum(row["task_completed"] for row in rows),
        "unique_fresh_runtime_executions": reassessment["unique_runtime_executions"],
        "checks_all_saved_files": sum(row["reexecuted"]["total"] for row in rows),
        "passed_all_saved_files": sum(row["reexecuted"]["passed"] or 0 for row in rows),
        "checks_completed_refactors": sum(row["reexecuted"]["total"] for row in rows if row["task_completed"]),
        "security_failures": sum(row["reexecuted"]["security_failures"] or 0 for row in rows),
        "unknown_files": sum(row["reexecuted"]["invariant_preserved"] is None for row in rows),
        "historical_pass_or_leak_labels_changed": reassessment["changed_historical_pass_or_security_labels"],
        "ordinary_controls_passed": controls["passed"],
        "ordinary_seeded_faults_rejected": controls["seeded_faults"],
        "erp_timeout_cleanup": read_json(ROOT / "reports/runtime-validation-v4.json"),
        "azure_calls_for_correction": 0,
        "scope": "Old saved observations replayed, candidate code reexecuted, labels reconciled; "
                 "no historical AI generations overwritten or regenerated",
    }
    write_json(ROOT / "reports/measurement-correction-v4.json", record)
    ordinary = priced(read_json(ROOT / "evidence/ordinary-v1/usage.json"))
    paper = priced(read_json(ROOT / "artifacts/private/mucoco-prediction-v1/usage.json"))
    old = read_json(ROOT / "reports/all-experiment-costs.json")
    cost = {
        "recorded_at": utc_now(),
        "groups_added": {"ordinary-v1": ordinary, "mucoco-prediction-v1": paper},
        "new_total": {
            "http_attempts": ordinary["http_attempts"] + paper["http_attempts"],
            "base_estimate_usd": ordinary["base_estimate_usd"] + paper["base_estimate_usd"],
            "cache_write_estimate_usd": ordinary["cache_write_estimate_usd"] + paper["cache_write_estimate_usd"],
            "unknown_usage_attempts": ordinary["unknown_usage_attempts"] + paper["unknown_usage_attempts"],
        },
        "prior_recorded_estimate": old["totals"],
        "all_recorded_total": {
            "reported_requests": int(old["totals"]["requests"]) + ordinary["requests"] + paper["requests"],
            "base_estimate_usd": old["totals"]["base_estimate_usd"]
                + ordinary["base_estimate_usd"] + paper["base_estimate_usd"],
            "cache_write_estimate_usd": old["totals"]["cache_write_estimate_usd"]
                + ordinary["cache_write_estimate_usd"] + paper["cache_write_estimate_usd"],
        },
        "zero_model_cost_work": ["Checker regression probes", "83-file replay/reexecution",
                                "Ordinary evaluator controls", "ERP timeout cleanup",
                                "Author archived failure replay", "Offline evidence verification"],
        "rates_per_million_tokens": {"input": 2, "cached": .1, "output": 10, "cache_write": 2.5},
        "source": "Previously verified official GPT-6.1 Sol Standard reference pricing; "
                  "model response usage from the saved new requests",
        "pricing_url": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
        "scope": "Observed research provider requests only; not Azure invoice/credit reconciliation",
        "limitations": [
            "Reference estimate, not guaranteed account-specific Azure billing",
            "Cache writes assumed to replace ordinary uncached-input rate at 1.25x",
            "Historical interrupted/unreported usage uncertainty remains; new 143 calls have reported usage",
            "Excludes this Codex chat, other Azure workloads, taxes and exchange conversion",
            "No new paid cloud ERP infrastructure; local CPU/storage/electricity are not billed here",
            "Ordinary-v1 stopped at 132 HTTP attempts, below its $0.45 reference-estimate cap",
        ],
    }
    write_json(ROOT / "reports/cost-accounting-v4.json", cost)
    print("Correction: 83 saved files, 8,396 checks; new reference estimate "
          f"${cost['new_total']['cache_write_estimate_usd']:.6f}; "
          f"all recorded ${cost['all_recorded_total']['cache_write_estimate_usd']:.6f}.")


if __name__ == "__main__":
    main()
