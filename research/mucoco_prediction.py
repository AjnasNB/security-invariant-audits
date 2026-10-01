"""Controller preparation/scoring for a small actual MUCOCO model experiment."""
import argparse
import ast
import json
from pathlib import Path

from research.io import ROOT, digest, utc_now
from research.sandbox import run_container
from research.scoring import same_value

SELECTION = [
    ("HumanEval/0", [[1.0, 2.0, 3.9, 4.0, 5.0, 2.2], .05]),
    ("HumanEval/1", ["(()()) ((())) () ((())()())"]),
    ("HumanEval/3", [[1, 2, -4, 5]]),
]


def prepare(source, output):
    source, output = Path(source), Path(output)
    examples = {row["record_id"]: row for row in
                (json.loads(line) for line in (ROOT / "datasets/humaneval.jsonl").read_text().splitlines())}
    selected = [{**examples[name], "input": inputs} for name, inputs in SELECTION]
    payload = {"command": "mucoco-prediction-inputs", "examples": selected}
    result = run_container(source, ["/adapter/paper_worker.py"], json.dumps(payload),
                           extra_mounts=[(ROOT / "research/paper_worker.py", "/adapter/paper_worker.py")],
                           timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr[-1800:])
    data = json.loads(result.stdout)
    output.mkdir(parents=True, exist_ok=False)
    (output / "queries.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    protocol = {"version": "mucoco-prediction-v1", "frozen_at": utc_now(), "selection": SELECTION,
                "query_ids": [row["id"] for row in data["variants"]], "queries_sha256": digest(json.dumps(data)),
                "source_register": {key: data[key] for key in ("mutation_source", "template_source", "adaptations")},
                "limits": {"max_http_attempts": 20, "reference_estimate_cap_usd": .05,
                           "conservative_debit_cap_usd": .20, "max_output_tokens": 256},
                "failure_definition": "Original answer correct, validated semantics-preserving mutant answer incorrect",
                "no_failure_mining": "Selection/inputs/operators fixed before model calls; no replacing failed or safe examples"}
    (ROOT / "protocols/mucoco-prediction-v1.json").write_text(json.dumps(protocol, indent=2) + "\n",
                                                          encoding="utf-8", newline="\n")
    print(json.dumps({"queries": len(data["variants"]), "skipped": data["skipped"], "protocol": protocol}, indent=2))


def score(output):
    output = Path(output)
    queries = json.loads((output / "queries.json").read_text())["variants"]
    responses = json.loads((output / "responses.json").read_text())["responses"]
    by_id = {row["id"]: row for row in responses}
    scored = []
    for query in queries:
        response = by_id.get(query["id"], {"termination": "unattempted", "text": None})
        value = None
        parsed = False
        if response.get("termination") == "completed":
            try:
                value = ast.literal_eval(response["text"].strip())
                parsed = True
            except (SyntaxError, ValueError, TypeError):
                pass
        valid = parsed and type(value).__name__ == query["expected_type"]
        scored.append({"id": query["id"], "task_id": query["task_id"], "condition": query["condition"],
                       "termination": response["termination"], "text": response.get("text"),
                       "expected": query["expected"], "observed": value,
                       "output_valid": valid, "correct": valid and same_value(value, query["expected"]),
                       "program_sha256": query["program_sha256"],
                       "author_test_suite_passed": query["author_test_suite_passed"]})
    comparisons = []
    for task_id, _ in SELECTION:
        group = {row["condition"]: row for row in scored if row["task_id"] == task_id}
        base = group["original"]
        for condition in ("rename", "boolean_literal"):
            if condition not in group:
                continue
            mutant = group[condition]
            assessed = base["termination"] == mutant["termination"] == "completed"
            comparisons.append({"task_id": task_id, "mutation": condition,
                                "status": "assessed" if assessed else "unknown",
                                "original_correct": base["correct"], "mutant_correct": mutant["correct"],
                                "paper_defined_inconsistency": assessed and base["correct"] and not mutant["correct"]})
    record = {"recorded_at": utc_now(), "experiment": "MUCOCO output-prediction model pilot",
              "results": scored, "comparisons": comparisons,
              "attempted_queries": len(responses), "correct": sum(row["correct"] for row in scored),
              "inconsistencies": sum(row["paper_defined_inconsistency"] for row in comparisons),
              "unknown_comparisons": sum(row["status"] != "assessed" for row in comparisons),
              "source": json.loads((ROOT / "protocols/mucoco-prediction-v1.json").read_text())["source_register"],
              "conclusion": "A small reproduction attempt of the original-correct/mutant-incorrect failure pattern; not published accuracy or a requirement to discover a failure"}
    (ROOT / "reports/mucoco-model-v1.json").write_text(json.dumps(record, indent=2) + "\n",
                                                   encoding="utf-8", newline="\n")
    print(json.dumps({"queries": len(scored), "correct": record["correct"],
                      "comparisons": len(comparisons), "inconsistencies": record["inconsistencies"],
                      "unknown": record["unknown_comparisons"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "score"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output) if args.command == "prepare" else score(args.output)
