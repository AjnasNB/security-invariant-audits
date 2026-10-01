"""Generate report content solely from recorded evidence."""
import argparse
import collections
import csv
import difflib
import html
import json
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json
from research.audit import audit_batch, metadata_usage


def summarize_batch(name):
    directory = ROOT / "artifacts" / "agent_runs" / name
    record = read_json(directory / "results.json")
    rows = record["results"]
    summary = {
        "batch": name, "mode": record["mode"], "runs": len(rows), "completed_at": record.get("completed_at"),
        "usage": record["total"], "error": record.get("error"), "conditions": {},
    }
    for condition in ("original", "rename", "formatting", "neutral", "misleading"):
        selected = [row for row in rows if row.get("condition") == condition]
        if not selected:
            continue
        summary["conditions"][condition] = {
            "runs": len(selected), "task_completed": sum(row.get("task_completed", False) for row in selected),
            "changed": sum(row.get("changed", False) for row in selected),
            "security_violating_runs": sum((row.get("assessment", {}).get("security_failures") or 0) > 0 for row in selected),
            "security_failing_checks": sum(row.get("assessment", {}).get("security_failures") or 0 for row in selected),
            "functional_failing_runs": sum((row.get("assessment", {}).get("functional_failures") or 0) > 0 for row in selected),
            "errored_runs": sum(row.get("termination") != "completed" for row in selected),
            "requests": sum(row.get("usage", {}).get("requests", 0) for row in selected),
            "tokens": sum(row.get("usage", {}).get("input_tokens", 0) + row.get("usage", {}).get("output_tokens", 0) for row in selected),
        }
    summary["tasks"] = {}
    for task in sorted({row.get("task") for row in rows if row.get("task")}):
        selected = [row for row in rows if row.get("task") == task]
        summary["tasks"][task] = {
            "runs": len(selected), "completed": sum(row["task_completed"] for row in selected),
            "checks": sum(row["assessment"].get("total", 0) for row in selected),
            "passed_checks": sum(row["assessment"].get("passed", 0) for row in selected),
            "security_violating_runs": sum((row["assessment"].get("security_failures") or 0) > 0 for row in selected),
        }
    return summary, rows


def compare_arms(rows):
    comparisons = []
    for task in sorted({row["task"] for row in rows}):
        task_rows = [row for row in rows if row["task"] == task]
        for arm_name, selected in (
            ("benign-variation", [row for row in task_rows if row["arm"] == "variation" and row["condition"] in ("original", "rename", "formatting")]),
            ("unchanged-control", [row for row in task_rows if row["arm"] == "unchanged-control"]),
            ("neutral-note", [row for row in task_rows if row["condition"] == "neutral"]),
            ("misleading-note", [row for row in task_rows if row["condition"] == "misleading"]),
        ):
            comparisons.append({
                "task": task, "comparison_arm": arm_name, "runs": len(selected),
                "security_violating_runs": sum((row["assessment"].get("security_failures") or 0) > 0 for row in selected),
                "task_completed": sum(row["task_completed"] for row in selected),
                "model_requests": sum(row["usage"]["requests"] for row in selected),
                "input_tokens": sum(row["usage"]["input_tokens"] for row in selected),
                "output_tokens": sum(row["usage"]["output_tokens"] for row in selected),
                "cached_tokens": sum(row["usage"]["cached_tokens"] for row in selected),
                "estimated_cost_usd": sum(row["usage"]["estimated_cost_usd"] for row in selected),
            })
    return comparisons


def all_accounting():
    batches = []
    grand = collections.Counter()
    for directory in sorted((ROOT / "artifacts" / "agent_runs").iterdir()):
        if not directory.is_dir():
            continue
        tokens = metadata_usage(directory)
        # Count every HTTP attempt using its metadata, including setup errors and interrupted batches.
        tokens["http_attempts"] = len(list(directory.rglob("provider-*-metadata.json")))
        result = read_json(directory / "results.json") if (directory / "results.json").exists() else {}
        batches.append({"batch": directory.name, "mode": result.get("mode", "setup"),
                        "completed_at": result.get("completed_at"), "error": result.get("error"), **tokens})
        grand.update(tokens)
    grand["public_reference_base_estimated_cost_usd"] = (
        (grand["input_tokens"] - grand["cached_tokens"]) * 2e-6
        + grand["cached_tokens"] * 0.1e-6 + grand["output_tokens"] * 10e-6
    )
    # Cache-write tokens are a subset of uncached input in the observed metadata.
    # If billed at 1.25x input, REPLACE the input rate, do not add another full rate.
    grand["public_reference_estimated_cost_usd"] = (
        grand["public_reference_base_estimated_cost_usd"] + grand["cache_write_tokens"] * 0.5e-6
    )
    return {"recorded_at": utc_now(), "batches": batches, "all_observed_totals": dict(grand),
            "pricing": "OpenAI public Standard reference, not verified Azure invoice",
            "cache_write_assumption": "Reported cache_write_tokens are treated as a subset of uncached input; 1.25x input rate replaces, rather than adds to, the ordinary input charge.",
            "unobserved_inflight_usage_possible": any(
                not row.get("completed_at") and row.get("http_attempts", 0) > 0 for row in batches)}


def report(pilot, application):
    pilot_summary, pilot_rows = summarize_batch(pilot)
    application_summary, application_rows = summarize_batch(application)
    assert pilot_summary["runs"] == 48 and pilot_summary["completed_at"] and not pilot_summary["error"]
    assert application_summary["runs"] == 5 and application_summary["completed_at"] and not application_summary["error"]
    audits = [audit_batch(pilot), audit_batch(application)]
    if not all(record["passed"] for record in audits):
        raise ValueError("Evidence integrity checks failed")
    dataset = read_json(ROOT / "datasets" / "index.json")
    sources = read_json(ROOT / "datasets" / "sources.json")
    validation = read_json(ROOT / "artifacts" / "validation.json")
    tenant = read_json(ROOT / "artifacts" / "tenant_integration.json")
    dojo = read_json(ROOT / "artifacts" / "agentdojo_smoke.json")
    mucoco = read_json(ROOT / "artifacts" / "papers" / "mucoco_humaneval.json")
    jailguard = read_json(ROOT / "artifacts" / "papers" / "jailguard_detection.json")
    replay = read_json(ROOT / "artifacts" / "papers" / "jailguard_original_replay.json")
    comparisons = compare_arms(pilot_rows)
    accounting = all_accounting()
    aggregate = {
        "generated_at": utc_now(), "author": "Ajnas N B", "pilot": pilot_summary,
        "application": application_summary, "comparisons": comparisons,
        "datasets": dataset, "sources": sources, "accounting": accounting,
        "validation_passed": validation["passed"], "integrity_passed": all(row["passed"] for row in audits),
        "tenant_smoke": tenant, "agentdojo_smoke": dojo,
        "mucoco": mucoco, "jailguard": jailguard, "jailguard_original_script": replay,
        "conclusion": (
            "The bounded pipeline works. No access-rule violation was observed in these runs. "
            "Neither benign mutations nor misleading notes exposed an additional failure in this task set. "
            "This does not establish equivalence of testing methods, broad model safety or detector accuracy."
        ),
    }
    write_json(ROOT / "reports" / "summary.json", aggregate)
    write_json(ROOT / "reports" / "cost-accounting.json", accounting)
    output_dir = ROOT / "reports"
    output_dir.mkdir(exist_ok=True)
    with (output_dir / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["batch", "run_id", "task", "condition", "arm", "repetition", "termination",
                  "changed", "task_completed", "protected_checks", "passed", "security_failures",
                  "model_requests", "input_tokens", "output_tokens", "cached_tokens", "estimated_cost_usd"]
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for batch, rows in ((pilot, pilot_rows), (application, application_rows)):
            for row in rows:
                writer.writerow({
                    "batch": batch, **{key: row.get(key) for key in ("run_id", "task", "condition", "arm", "repetition",
                                                                   "termination", "changed", "task_completed")},
                    "protected_checks": row["assessment"]["total"], "passed": row["assessment"]["passed"],
                    "security_failures": row["assessment"]["security_failures"],
                    "model_requests": row["usage"]["requests"],
                    **{key: row["usage"][key] for key in ("input_tokens", "output_tokens", "cached_tokens", "estimated_cost_usd")},
                })
    with (output_dir / "comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    lines = [
        "# Measured MVP results", "", "Author: Ajnas N B. October 1, 2026.", "",
        aggregate["conclusion"], "", "## Completed experiments", "",
        f"* Three-fixture pilot: {len(pilot_rows)} fresh agent trajectories; 30 condition runs and 18 independent unchanged controls.",
        f"* Real application: {len(application_rows)} FastAPI item-route refactors, one per condition; upstream models/routes on Python 3.14 and SQLite.",
        f"* Evaluator: all reference variants pass; all {sum(row['kind'] == 'evaluator_selftest' and not row['expected_accept'] for row in validation['records'])} seeded security faults rejected.",
        f"* Tenant library: {len(tenant['checks'])} integration checks; AgentDojo: {len(dojo['checks'])} original tool/data smoke checks.",
        "* JailGuard: four author-data inputs, eight RR variants each, 32 live Azure text attempts; 25 completed responses and seven content-filtered attempts. Three complete eight-response groups can be scored.",
        "* MUCOCO: original VariableNameTransformer on HumanEval/0-2; two validated mutants, one explicitly inapplicable case.",
        "", "## Pilot by task", "",
        "| Task | Runs | Completed refactors | Protected checks passed | Violating runs |",
        "|---|---:|---:|---:|---:|",
    ]
    for task, row in pilot_summary["tasks"].items():
        lines.append(f"| {task} | {row['runs']} | {row['completed']} | {row['passed_checks']}/{row['checks']} | {row['security_violating_runs']} |")
    lines += [
        "", "## Matched comparisons", "",
        "Each task has six benign-variation runs versus six separate unchanged runs. "
        "Notes are compared separately: two neutral and two misleading runs per task. "
        "Nominal trajectory/tool/token ceilings match; actual requests, tokens and estimates differ "
        "and appear in comparison.csv. The original runs in the variation arm are not reused as controls.",
        "", "| Task | Arm | Runs | Violating runs | Model calls | Estimated USD |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in comparisons:
        lines.append(f"| {row['task']} | {row['comparison_arm']} | {row['runs']} | {row['security_violating_runs']} | {row['model_requests']} | {row['estimated_cost_usd']:.4f} |")
    lines += [
        "", "## Dataset register", "",
        "These are distinct dataset families, not one merged security ground truth. "
        "Acquisition does not mean every record was used in a live experiment.", "",
        "| Dataset | Records | Used for |", "|---|---:|---|",
    ]
    for name, row in dataset["datasets"].items():
        lines.append(f"| {name} | {row['records']} | {row['family']} |")
    lines += [
        "", "## Original paper evidence", "",
        "JailGuard runs its author's unchanged RR mutator, spaCy similarity, KL-divergence "
        "and refusal-keyword decision. The main_txt.py workflow is subsequently run without network "
        "against frozen responses whose queries are matched exactly: two benign inputs use the unchanged "
        "script, while the complete message-list group uses a documented one-line response-filename compatibility fix. "
        "The fourth group has provider-filtered results and remains unscorable; no substitute refusal text is fabricated. This is an adapted reproduction: "
        "Azure GPT-6.1 Sol replaces GPT-3.5, Python/runtime versions differ, and unused image "
        "dependencies are stubbed. No original published accuracy is claimed.", "",
        "| Source example | Historical attack label | Detected | Max divergence |",
        "|---|---|---|---:|",
    ]
    for row in jailguard["results"]:
        divergence = f"{row['max_divergence']:.6f}" if row["max_divergence"] is not None else "N/A - content-filtered"
        decision = row["detected_attack"] if row["detected_attack"] is not None else "Unknown"
        lines.append(f"| {row['source_id']} | {row['historical_attack_label']} | {decision} | {divergence} |")
    lines += [
        "", "Historical attack labels do not prove the injection succeeds on Sol. "
        "Four inputs cannot establish detector accuracy.", "",
        "## Cost and setup accounting", "",
        f"* Pilot base public-reference estimate: ${pilot_summary['usage']['estimated_cost_usd']:.4f} before any cache-write premium.",
        f"* Application base public-reference estimate: ${application_summary['usage']['estimated_cost_usd']:.4f} before any cache-write premium.",
        f"* All observed calls, including setup and excluded runner-validation attempts: "
        f"${accounting['all_observed_totals']['public_reference_estimated_cost_usd']:.4f} estimated.",
        "* Rates are the public OpenAI Standard short-context reference. Azure contract/tier billing "
        "was not verified; these amounts are not an Azure invoice or guaranteed spending cap.",
        "* The all-observed estimate replaces the ordinary input price with the 1.25x write price "
        "for reported cache_write_tokens, assuming those tokens are a subset of uncached input. "
        "It does not bill them twice. The unadjusted base estimate is also retained.",
        "* The aborted version-2 batch is retained, including its successful run and two unchanged "
        "step-limited runs. A fourth trajectory was interrupted; in-flight unobserved billing is possible. "
        "The whole batch was excluded before the fresh version-3 pilot.",
        "", "## Limits", "",
        "* One defensive harness policy, one model deployment, three small development templates and one app module.",
        "* Backend routes and pre-authenticated synthetic principals were tested; no full UI/JWT/production ERP deployment.",
        "* ERPNext source/test excerpts were acquired but its framework/database suite was not executed.",
        "* Detector precision/recall for security regressions is N/A without observed positive failures.",
        "* Renames/formatting were validated on these finite checks, not proven equivalent for all Python behavior.",
        "* Every trajectory receives fresh state; the hosted deployment itself is not a promised immutable model snapshot.",
        "* The misleading note comparison includes an explicit instruction that repository notes are untrusted. "
        "It tests this defensive policy, not all prompt-injection configurations.",
        "* Passing independent checks demonstrates the tested cases only. It is not a security certification.",
        "", "## Evidence", "",
        "summary.json, runs.csv, comparison.csv, cost-accounting.json, source commits/file hashes, "
        "environment.json, protocol.json and per-run raw provider/tool/candidate/assessment files.",
        "Integrity audits reconcile trajectory hashes and provider usage. Licenses and restricted "
        "sources remain separated. No remote repository, branch or push was created.",
    ]
    (output_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Plain static report: no network, no new UI framework, raw untrusted content HTML-escaped.
    body = ["<h1>Security-Invariant Mutation Audits</h1><p>Ajnas N B · October 1, 2026 · Measured feasibility study</p>",
            "<p>" + html.escape(aggregate["conclusion"]) + "</p>",
            "<p>48 controlled fixture runs + 5 real-app smoke runs. No production safety certification.</p>",
            "<table><tr><th>Task</th><th>Condition</th><th>Arm</th><th>Completed</th><th>Checks</th><th>Violations</th></tr>"]
    for row in pilot_rows + application_rows:
        body.append("<tr>" + "".join("<td>" + html.escape(str(value)) + "</td>" for value in (
            row["task"], row["condition"], row["arm"], row["task_completed"],
            f"{row['assessment']['passed']}/{row['assessment']['total']}", row["assessment"]["security_failures"])) + "</tr>")
    body.append("</table><h2>Recorded example patches</h2>")
    from research.variants import source_code, mutate
    for batch, rows in ((pilot, pilot_rows), (application, application_rows)):
        for row in rows[:2]:
            candidate = (ROOT / "artifacts" / "agent_runs" / batch / row["run_id"] / "candidate.py").read_text()
            original = mutate(source_code(row["task"]), row["task"], row["condition"])
            patch = "".join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                                fromfile="reference", tofile="candidate"))
            body.append("<h3>" + html.escape(row["run_id"]) + "</h3><pre>" + html.escape(patch) + "</pre>")
    css = "body{font:16px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#172334}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccd5df;text-align:left}th{background:#edf3f8}pre{white-space:pre-wrap;background:#f1f5f8;padding:18px;font-size:13px}"
    (output_dir / "report.html").write_text("<!doctype html><html><meta charset='utf-8'><title>Ajnas research results</title><style>" + css + "</style><body>" + "".join(body) + "</body></html>", encoding="utf-8")
    print(json.dumps({"pilot": pilot_summary, "application": application_summary,
                      "output": str(output_dir), "integrity_passed": True}, indent=2))
    return aggregate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--application", required=True)
    args = parser.parse_args()
    report(args.pilot, args.application)
