"""Acquire provenance and normalize different source families without conflating them."""
import ast
import csv
import gzip
import json
import shutil
import subprocess
from pathlib import Path

from research.cases import fixture_cases
from research.io import ROOT, digest, utc_now, write_json, write_jsonl

SOURCES = [
    ("mucoco", "mucoco-tester/mucoco-tester.github.io", "unknown", False),
    ("jailguard", "shiningrain/JailGuard", "unknown", False),
    ("humaneval", "openai/human-eval", "MIT", True),
    ("django_multitenant", "citusdata/django-multitenant", "MIT", True),
    ("agentdojo", "ethz-spylab/agentdojo", "MIT", True),
    ("fastapi_app", "fastapi/full-stack-fastapi-template", "MIT", True),
    ("erpnext", "frappe/erpnext", "GPL-3.0", False),
]


def source_info(name, repo, license_name, shareable):
    location = ROOT / "_sources" / name
    commit = subprocess.check_output(["git", "-C", str(location), "rev-parse", "HEAD"], text=True).strip()
    metadata = json.loads(subprocess.check_output([
        "gh", "api", f"repos/{repo}", "--jq",
        "{stars:.stargazers_count,license:.license.spdx_id,branch:.default_branch}"
    ], text=True))
    return {
        "id": name, "repository": f"https://github.com/{repo}", "commit": commit,
        "acquired_at": utc_now(), "stars_at_acquisition": metadata["stars"],
        "license": license_name, "redistributable_in_project": shareable,
        "local_path": str(location), "sparse_checkout": name in ("mucoco", "jailguard", "erpnext"),
    }


def base_record(source, path, record_id, role, payload):
    return {
        "record_id": record_id, "source_id": source["id"],
        "repository": source["repository"], "commit": source["commit"], "source_path": path,
        "role": role, "payload_sha256": digest(json.dumps(payload, sort_keys=True, ensure_ascii=False)),
        "payload": payload,
    }


def static_test_records(source, patterns):
    location = ROOT / "_sources" / source["id"]
    records = []
    for pattern in patterns:
        for path in sorted(location.glob(pattern)):
            if not path.is_file() or path.suffix != ".py":
                continue
            content = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    snippet = ast.get_source_segment(content, node)
                    records.append(base_record(source, path.relative_to(location).as_posix(),
                                               f"{path.relative_to(location)}::{node.name}:{node.lineno}",
                                               "upstream-test-code-not-executed-by-ingestion",
                                               {"name": node.name, "line": node.lineno, "code": snippet}))
    return records


def ingest():
    sources = [source_info(*row) for row in SOURCES]
    by_id = {source["id"]: source for source in sources}
    summary = {}
    license_dir = ROOT / "THIRD_PARTY_LICENSES"
    license_dir.mkdir(exist_ok=True)

    for source in sources:
        if source["redistributable_in_project"]:
            for filename in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
                license_path = ROOT / "_sources" / source["id"] / filename
                if license_path.exists():
                    shutil.copyfile(license_path, license_dir / f"{source['id']}-{filename}")
                    break

    human_source = by_id["humaneval"]
    human_path = ROOT / "_sources" / "humaneval" / "data" / "HumanEval.jsonl.gz"
    with gzip.open(human_path, "rt", encoding="utf-8") as handle:
        human_records = [
            base_record(human_source, "data/HumanEval.jsonl.gz", row["task_id"], "general-code-benchmark", row)
            for line in handle if (row := json.loads(line))
        ]
    write_jsonl(ROOT / "datasets" / "humaneval.jsonl", human_records)
    summary["humaneval"] = {"records": len(human_records), "family": "general-code", "path": "datasets/humaneval.jsonl"}

    mu_records = []
    for path in sorted((ROOT / "_sources" / "mucoco" / "datasets" / "open_ended_format").glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle)):
                mu_records.append(base_record(by_id["mucoco"], path.relative_to(ROOT / "_sources" / "mucoco").as_posix(),
                                              f"{path.stem}:{index}", "mucoco-bundled-benchmark", row))
    write_jsonl(ROOT / "datasets" / "restricted" / "mucoco.jsonl", mu_records)
    summary["mucoco"] = {"records": len(mu_records), "family": "general-code",
                         "path": "datasets/restricted/mucoco.jsonl", "redistribution": "not-established"}

    # Data-only loading: scan every opcode first and prohibit all executable constructs.
    # Run only this decoder inside the restricted container, not pickle.load on the developer host.
    from research.sandbox import run_container
    result = run_container(
        ROOT / "_sources" / "jailguard",
        ["/decoder/plain_pickle.py"],
        extra_mounts=[(ROOT / "research", "/decoder")], timeout=45, output_limit=15_000_000,
    )
    if result.returncode:
        raise RuntimeError("Restricted JailGuard decoder failed: " + result.stderr[-1500:])
    jail_data = json.loads(result.stdout)
    jail_records = []
    for index, (query, key) in enumerate(zip(jail_data["data"], jail_data["keys"])):
        jail_records.append(base_record(by_id["jailguard"], "dataset/text/dataset.pkl", f"jailguard-text:{index}",
                                        "historical-text-attack-benchmark",
                                        {"input": query, "source_key": key, "label_caution": "historical label, not observed Sol success"}))
    write_jsonl(ROOT / "datasets" / "restricted" / "jailguard.jsonl", jail_records)
    write_json(ROOT / "artifacts" / "jailguard_pickle_audit.json", jail_data["audit"])
    summary["jailguard"] = {"records": len(jail_records), "family": "text-injection",
                            "path": "datasets/restricted/jailguard.jsonl", "redistribution": "not-established"}

    tenant_records = static_test_records(by_id["django_multitenant"], ["django_multitenant/tests/test_*.py"])
    write_jsonl(ROOT / "datasets" / "django_multitenant_tests.jsonl", tenant_records)
    summary["django_multitenant"] = {"records": len(tenant_records), "family": "tenant-upstream-tests",
                                     "path": "datasets/django_multitenant_tests.jsonl"}

    from research.sandbox import run_container
    yaml_result = run_container(
        ROOT / "_sources" / "agentdojo",
        ["/decoder/yaml_extract.py"],
        extra_mounts=[(ROOT / "research", "/decoder")], timeout=45,
    )
    if yaml_result.returncode:
        raise RuntimeError(yaml_result.stderr[-1000:])
    dojo_records = [
        base_record(by_id["agentdojo"], row["path"], f"agentdojo:{index}", "agent-injection-environment", row["data"])
        for index, row in enumerate(json.loads(yaml_result.stdout))
    ]
    # Also extract original v1 task methods, preserving code rather than importing a plugin.
    for path in sorted((ROOT / "_sources" / "agentdojo" / "src" / "agentdojo" / "default_suites" / "v1").rglob("*tasks.py")):
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                dojo_records.append(base_record(by_id["agentdojo"], path.relative_to(ROOT / "_sources" / "agentdojo").as_posix(),
                                                f"agentdojo:{node.name}", "agent-task-definition",
                                                {"class": node.name, "code": ast.get_source_segment(content, node)}))
    write_jsonl(ROOT / "datasets" / "agentdojo.jsonl", dojo_records)
    summary["agentdojo"] = {"records": len(dojo_records), "family": "agent-injection",
                            "path": "datasets/agentdojo.jsonl"}

    app_records = static_test_records(by_id["fastapi_app"], ["backend/tests/api/routes/test_items.py"])
    write_jsonl(ROOT / "datasets" / "fastapi_upstream_tests.jsonl", app_records)
    summary["fastapi_app"] = {"records": len(app_records), "family": "application-owner-tests",
                             "path": "datasets/fastapi_upstream_tests.jsonl"}
    erp_records = static_test_records(by_id["erpnext"], [
        "erpnext/accounts/doctype/sales_invoice/test_sales_invoice.py",
        "erpnext/accounts/doctype/purchase_invoice/test_purchase_invoice.py",
    ])
    write_jsonl(ROOT / "datasets" / "restricted" / "erpnext_tests.jsonl", erp_records)
    summary["erpnext"] = {"records": len(erp_records), "family": "erp-source-tests-not-executed",
                          "path": "datasets/restricted/erpnext_tests.jsonl", "redistribution": "GPL-3.0-separate"}

    synthetic = []
    for task in ("access_helper", "invoice_lookup", "invoice_list"):
        for case in fixture_cases(task):
            synthetic.append({
                "record_id": f"{task}:{case['id']}", "source_id": "ajnas-synthetic",
                "role": "declared-owner-company-challenge", "task": task, **case,
            })
    write_jsonl(ROOT / "datasets" / "synthetic_invoice_cases.jsonl", synthetic)
    summary["ajnas_synthetic"] = {"records": len(synthetic), "family": "owner-company", "path": "datasets/synthetic_invoice_cases.jsonl"}
    for source in sources:
        location = ROOT / "_sources" / source["id"]
        selected = ["README.md"] + [
            str(path.relative_to(location)) for path in location.rglob("LICENSE*") if ".git" not in path.parts
        ]
        source["selected_file_hashes"] = {path: digest((location / path).read_bytes()) for path in selected if (location / path).is_file()}
    write_json(ROOT / "datasets" / "sources.json", {"schema_version": 1, "created_at": utc_now(), "sources": sources})
    write_json(ROOT / "datasets" / "index.json", {"created_at": utc_now(), "families_kept_separate": True, "datasets": summary})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ingest()
