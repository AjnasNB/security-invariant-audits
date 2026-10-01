"""Replay archived MUCOCO failures, not new model discovery or full-paper accuracy."""
import argparse
import ast
import csv
import hashlib
import io
import json
import re
import typing
import urllib.request
import zipfile
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json
from research.sandbox import run_container
from research.scoring import same_value

ARTICLE = "https://api.figshare.com/v2/articles/30402541"
RESULT_MEMBER = "MuCoCo_experiment_results/output_prediction/gpt-4o/HumanEval_few_shot_"
PACKAGE_ROOT = "MuCoCo-Replicate-Package/"
ARCHIVES = {
    "MuCoCo_experiment_results.zip": ("58899583", "4951a5f3840aee897ec5bbbaf6cf7194"),
    "MuCoCo-Replicate-Package.zip": ("58910683", "9adc6e59b555bb8cf624871374bf1e4c"),
}


def selected_function(source, name, namespace):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<reviewed-author-aggregation>", "exec"), namespace)
    return namespace[name], digest(ast.get_source_segment(source, node))


def read_member(archive, name, limit=8_000_000):
    if archive.getinfo(name).file_size > limit:
        raise RuntimeError("Selected archive member exceeds its size limit")
    return archive.read(name).decode("utf-8-sig")


def saved_answer(text):
    matched = re.fullmatch(r"\((.*), <class '([A-Za-z]+)'>\)", text, re.S)
    if not matched:
        raise ValueError("Unsupported saved model-output serialization")
    value = ast.literal_eval(matched[1])
    if type(value).__name__ != matched[2]:
        raise ValueError("Serialized saved model output has inconsistent type metadata")
    return value


def benchmark_parts(row):
    code = row["prompt"].split("# Code Snippet\n", 1)[1].split("# Input\n", 1)[0].strip() + "\n"
    inputs = row["prompt"].split("# Input\n", 1)[1].split("# Examples", 1)[0].strip()
    function = next(node for node in ast.parse(code).body if isinstance(node, ast.FunctionDef))
    value = ast.literal_eval(inputs)
    arguments = list(value) if len(function.args.args) > 1 else [value]
    return code, function.name, arguments


def acquire(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ARTICLE, timeout=30) as response:
        metadata = json.load(response)
    write_json(directory / "figshare-metadata.json", metadata)
    for filename, (file_id, expected_md5) in ARCHIVES.items():
        destination = directory / filename
        if destination.exists():
            continue
        # Download source archives only; never extract or execute an entire package.
        with urllib.request.urlopen("https://ndownloader.figshare.com/files/" + file_id, timeout=60) as response:
            body = response.read(100_000_001)
        if len(body) > 100_000_000 or hashlib.md5(body).hexdigest() != expected_md5:
            raise RuntimeError("Source archive size/checksum validation failed")
        destination.write_bytes(body)


def replay(directory, destination):
    import pandas as pd

    directory, destination = Path(directory), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    archive_hashes = {}
    for filename, (_, expected_md5) in ARCHIVES.items():
        body = (directory / filename).read_bytes()
        if hashlib.md5(body).hexdigest() != expected_md5:
            raise RuntimeError("Archived source checksum mismatch")
        archive_hashes[filename] = digest(body)
    with zipfile.ZipFile(directory / "MuCoCo_experiment_results.zip") as results, \
         zipfile.ZipFile(directory / "MuCoCo-Replicate-Package.zip") as package:
        baseline_text = read_member(results, RESULT_MEMBER + "no_mutation.csv")
        mutant_text = read_member(results, RESULT_MEMBER + "boolean_literal.csv")
        baseline = list(csv.DictReader(io.StringIO(baseline_text)))
        mutants = list(csv.DictReader(io.StringIO(mutant_text)))
        source = read_member(package, PACKAGE_ROOT + "utility/data_log_functions.py")
        author_class = next(node for node in ast.parse(source).body
                            if isinstance(node, ast.ClassDef) and node.name == "DataLogHelper")
        comparison_node = next(node for node in author_class.body if isinstance(node, ast.FunctionDef)
                               and node.name == "compare_code_generation_dataframe_results")
        # This inspected definition is read-only DataFrame arithmetic. No notebook,
        # file operations, generated program or arbitrary archive import runs on the host.
        comparison, comparison_hash = selected_function(
            ast.get_source_segment(source, comparison_node), comparison_node.name,
            {"pd": pd, "Tuple": typing.Tuple})
        notebook = json.loads(read_member(package, PACKAGE_ROOT + "MuCoCo_results/notebooks/RQ1_results_aggregation.ipynb"))
        alignment_source = next("".join(cell["source"]) for cell in notebook["cells"]
                                if cell["cell_type"] == "code"
                                and "".join(cell["source"]).startswith("def standardize_two_df"))
        alignment, alignment_hash = selected_function(alignment_source, "standardize_two_df",
                                                     {"pd": pd, "Tuple": typing.Tuple})
        first, second = alignment(pd.read_csv(io.StringIO(baseline_text)), pd.read_csv(io.StringIO(mutant_text)))
        aggregate = comparison(first, second)

    by_id = {row["task_id"]: row for row in baseline}
    positive = [row for row in mutants if row["task_id"] in by_id
                and not by_id[row["task_id"]]["failure_type"]
                and row["failure_type"].startswith("AssertionError")]
    cases, selected, functions = [], [], set()
    problems = {row["payload"]["entry_point"]: row["payload"]
                for row in (json.loads(line) for line in (ROOT / "datasets/humaneval.jsonl").read_text().splitlines())}
    format_failures = 0
    wrong_values = []
    for row in sorted(positive, key=lambda item: int(item["task_id"].split("TF")[-1])):
        answer = saved_answer(row["model_output"])
        if type(answer) is str and "```" in answer:
            format_failures += 1
            continue
        wrong_values.append(row)
    for row in wrong_values:
        original = by_id[row["task_id"]]
        original_code, function, arguments = benchmark_parts(original)
        mutant_code, mutant_function, mutant_arguments = benchmark_parts(row)
        if function in functions:
            continue
        if function != mutant_function or not same_value(arguments, mutant_arguments):
            raise RuntimeError("Archived pair does not have matched program/input identity")
        expected_metadata = ast.literal_eval(row["expected_output"])
        expected = (expected_metadata["args"] if expected_metadata["metadata"] == "str"
                    else ast.literal_eval(expected_metadata["args"]))
        if not same_value(saved_answer(original["model_output"]), expected):
            raise RuntimeError("Selected baseline is not independently correct")
        if same_value(saved_answer(row["model_output"]), expected):
            raise RuntimeError("Selected mutant answer is not actually different")
        functions.add(function)
        selected.append({
            "task_id": row["task_id"], "humaneval_task_id": problems[function]["task_id"],
            "function": function, "input": arguments, "expected": expected,
            "original_saved_answer": saved_answer(original["model_output"]),
            "mutant_saved_answer": saved_answer(row["model_output"]),
            "original_failure_type": original["failure_type"], "mutant_failure_type": row["failure_type"],
            "original_prompt_sha256": digest(original["prompt"]), "mutant_prompt_sha256": digest(row["prompt"]),
            "original_program_sha256": digest(original_code), "mutant_program_sha256": digest(mutant_code),
            "failure_kind": "Wrong value, not Markdown/output-format-only",
        })
        public = destination / row["task_id"]
        public.mkdir()
        (public / "original.py").write_text(original_code, encoding="utf-8", newline="\n")
        (public / "mutant.py").write_text(mutant_code, encoding="utf-8", newline="\n")
        for label, code in (("original", original_code), ("mutant", mutant_code)):
            cases.append({"id": row["task_id"] + ":" + label, "program": code,
                          "entry_point": function, "args": arguments,
                          "author_tests": problems[function]["test"]})
        if len(selected) == 3:
            break
    if len(selected) != 3:
        raise RuntimeError("The fixed three-distinct-function failure replay could not be assembled")
    write_json(directory / "selection-before-execution.json", {
        "recorded_at": utc_now(), "selection": selected,
        "basis": "First saved wrong-value failure per distinct function, numeric task-ID order; stop at three",
        "positive_case_selection": True, "not_an_unbiased_discovery_sample": True,
    })
    execution = run_container(ROOT / "tasks/access_helper", ["/adapter/author_replay_worker.py"],
        json.dumps({"cases": cases}), [(ROOT / "research/author_replay_worker.py", "/adapter/author_replay_worker.py")],
        timeout=45)
    if execution.returncode:
        raise RuntimeError(execution.stderr[-1800:])
    observations = json.loads(execution.stdout)
    observed = {item["id"]: item for item in observations}
    for item in selected:
        first, second = (observed[item["task_id"] + ":" + label] for label in ("original", "mutant"))
        item["programs_pass_author_tests"] = first["author_tests_passed"] and second["author_tests_passed"]
        item["original_runtime_output"], item["mutant_runtime_output"] = first.get("value"), second.get("value")
        item["replay_confirmed"] = (item["programs_pass_author_tests"]
            and same_value(first.get("value"), item["expected"]) and same_value(second.get("value"), item["expected"])
            and not same_value(item["mutant_saved_answer"], item["expected"]))
        write_json(destination / item["task_id"] / "case.json", item)
    report = {
        "recorded_at": utc_now(), "experiment": "MUCOCO archived-output failure replay",
        "upstream_article_id": 30402541, "upstream_article_version": 2,
        "artifact_terms": "CC BY 4.0 for the Figshare artifacts; not a blanket license for GitHub checkouts",
        "archive_sha256": archive_hashes,
        "members": {RESULT_MEMBER + "no_mutation.csv": digest(baseline_text),
                    RESULT_MEMBER + "boolean_literal.csv": digest(mutant_text)},
        "author_definitions_sha256": {"RQ1.standardize_two_df": alignment_hash,
                                     "DataLogHelper.compare_code_generation_dataframe_results": comparison_hash},
        "pandas_version": pd.__version__,
        "model_in_saved_results": "gpt-4o", "task": "HumanEval output prediction, few-shot, Boolean-literal mutation",
        "author_aggregation": {key: int(value) for key, value in aggregate.items()},
        "matched_original_correct_mutant_wrong_rows": len(positive),
        "wrong_value_rows": len(wrong_values), "format_only_rows": format_failures,
        "selected": selected, "confirmed_selected_failures": sum(item["replay_confirmed"] for item in selected),
        "azure_calls": 0, "new_model_generation": False,
        "claim": "Reproduced saved failure classifications and original/mutant runtime equivalence for three "
                 "known archived failures; not regenerated historical GPT-4o responses or replicated full-paper rates",
        "selection": "Explicit positive-case reproduction: first wrong-value case per distinct function, "
                     "not added to the ordinary-v1 or fresh MUCOCO discovery denominator",
    }
    write_json(destination / "report.json", report)
    write_json(ROOT / "reports/mucoco-author-replay-v1.json", report)
    write_json(destination / "manifest.json", {
        "files": {path.relative_to(destination).as_posix(): digest(path.read_bytes())
                  for path in sorted(destination.rglob("*")) if path.is_file()},
        "attribution": "MuCoCo: Code Consistency Testing Framework Replication Package, Figshare article "
                       "30402541 version 2, CC BY 4.0. HumanEval retains its MIT notice.",
        "changes": "Program sections extracted from saved prompts, matched selected examples and local replay evidence; "
                   "full prompts, archive contents and private traces are not copied",
    })
    print(json.dumps({key: report[key] for key in (
        "author_aggregation", "matched_original_correct_mutant_wrong_rows", "wrong_value_rows",
        "format_only_rows", "confirmed_selected_failures", "azure_calls",
    )}, indent=2))
    if report["confirmed_selected_failures"] != 3:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-directory", type=Path, default=ROOT / "artifacts/private/mucoco-author-replay")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/mucoco-author-replay-v1")
    parser.add_argument("--acquire", action="store_true")
    args = parser.parse_args()
    if args.acquire:
        acquire(args.archive_directory)
    replay(args.archive_directory, args.output)


if __name__ == "__main__":
    main()
