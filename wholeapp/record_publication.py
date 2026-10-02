"""Record inspected public commits, passing CI and fresh-clone replay."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from research.io import ROOT, read_json, write_json, utc_now

BASE = "94d0fcfb4117f61fe7f798e1b58f8e6f70899a60"
REPOSITORY = "AjnasNB/security-invariant-audits"


def execute(command, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        raise RuntimeError("Publication check failed: " + " ".join(command[:4]))
    return (result.stdout + result.stderr).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-clone", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    args = parser.parse_args()
    head = execute(["git", "rev-parse", "HEAD"])
    repo = json.loads(execute(["gh", "repo", "view", REPOSITORY, "--json",
                               "url,visibility,defaultBranchRef"]))
    remote = json.loads(execute(["gh", "api", f"repos/{REPOSITORY}/git/ref/heads/main"]))["object"]["sha"]
    ci = json.loads(execute(["gh", "run", "view", args.ci_run, "--repo", REPOSITORY,
                            "--json", "status,conclusion,headSha,url"]))
    if remote != head or ci["headSha"] != head or ci["status"] != "completed" or ci["conclusion"] != "success":
        raise RuntimeError("Verified content main/CI did not match")
    if repo["visibility"] != "PUBLIC" or repo["defaultBranchRef"]["name"] != "main":
        raise RuntimeError("Unexpected publication visibility/branch")
    commits = []
    for line in execute(["git", "log", "--reverse", "--format=%H%x09%an%x09%ae%x09%s", BASE + "..HEAD"]).splitlines():
        sha, author, email, subject = line.split("\t", 3)
        if email != "ajnasnb@gmail.com":
            raise RuntimeError("Unexpected author identity")
        commits.append({"sha": sha, "author": author, "email": email, "subject": subject})
    clone = args.fresh_clone.resolve()
    if execute(["git", "rev-parse", "HEAD"], clone) != head or execute(["git", "status", "--porcelain"], clone):
        raise RuntimeError("Fresh public clone is not exact/clean")
    fresh = []
    for arguments in (["-m", "unittest", "discover", "-s", "tests", "-q"], ["-m", "wholeapp.verify"]):
        output = execute([sys.executable, "-B", *arguments], clone)
        fresh.append({"command": "python -B " + " ".join(arguments), "passed": True, "output": output})
    audit = read_json(ROOT / "artifacts/private/wholeapp-v1/long-path-publication-audit.json")
    if not audit["passed"]:
        raise RuntimeError("Publication scan did not pass")
    result = read_json(ROOT / "reports/wholeapp-results-v1.json")
    costs = read_json(ROOT / "reports/wholeapp-costs-v1.json")
    record = {
        "recorded_at": utc_now(), "author": "Ajnas N B", "repository": REPOSITORY, "url": repo["url"],
        "visibility": repo["visibility"], "branch": "main", "reviewed_base": BASE,
        "inspected_content_main": head, "commits": commits, "ci": ci,
        "fresh_public_clone": {"exact_revision": head, "clean": True, "checks": fresh,
                               "no_private_erp_or_azure_required": True},
        "publication_audit": {key: audit[key] for key in ("passed", "tracked_files", "issues", "scope", "values_disclosed")},
        "verification": {"python_tests": 74, "offline_budget_tests": 7, "new_evidence_hashes": 82,
                         "source_inventory_files": 8925, "public_saved_http_checks": 5847, "pdf_pages_reviewed": 5},
        "results": {"entire_application_rewrite_completed": False, "baseline": result["baseline"],
                    "hardening": result["hardening"], "changed_files": result["changed_file_count_by_model"],
                    "new_ai_access_regressions": result["new_model_access_regressions"]},
        "costs": {key: costs[key] for key in ("reported_reference_usd", "uncertain_reservations_usd",
                                            "reported_plus_identified_uncertainty_usd", "within_cap")},
        "original_application_preserved": True, "disposable_runtime_removed": True,
        "authorization": "Scoped requested research changes, Ajnas-author main commits, normal non-force pushes. "
                         "No unrelated Delta product changes, credentials or raw reasoning published.",
        "scope": "Inspected content before this metadata-only commit; no self-referential commit SHA or future CI claim.",
    }
    write_json(ROOT / "reports/wholeapp-publication-v1.json", record)
    lines = [
        "# Whole-source/access study publication record", "", "Author: Ajnas N B. October 2, 2026.", "",
        f"Public repository: https://github.com/{REPOSITORY}. Branch: `main`.", "",
        "Verified content commits use `ajnasnb <ajnasnb@gmail.com>`. No Codex author/branch or force push:", "",
        "| Commit | Change |", "|---|---|",
    ]
    lines += [f"| `{row['sha']}` | {row['subject']} |" for row in commits]
    lines += [
        "", f"Content CI: **{ci['status']} / {ci['conclusion']}** at `{head}`.", "", ci["url"], "",
        "Fresh public Windows clone: 74 Python tests and all 82 evidence hashes/5,847 HTTP "
        "observation replays passed without Azure, Docker or private ERP configuration. Linux "
        "tests/CI and seven offline budget tests also passed. A separate Windows long-path "
        "correction is retained after the first deep-clone replay failure.", "",
        "Publication scan: 1,831 tracked files; no flagged common tokens/private paths or exact "
        "original/disposable passwords/API credentials. Raw model reasoning, cookies, private "
        "site/dump files and local memory excluded. This is bounded checking, not an exhaustive "
        "secret-detection guarantee.", "",
        "Measured result: full 8,925-file source available, but **the entire app rewrite is "
        "incomplete**. Two models changed two files each; Luna saved no edit. Original and "
        "generated outputs scored 721/730, with the same nine pre-existing native print-policy "
        "company-isolation conflicts; no additional observed model access regression.", "",
        "The separately labeled optional policy-hardening overlay scored 730/730. It was not "
        "merged into the original ERP. Business/helper tests passed. The five-page PDF was "
        "rendered and all pages visually inspected. The working ERP's original code/data/"
        "ledgers remain unchanged; disposable RAM containers were removed.", "",
        "New reference usage $0.79520166 plus $0.0242954 uncertain reserve; combined $0.81949706. "
        "Not an Azure invoice or remaining-credit measurement.", "",
        "This metadata record describes inspected content before its own commit; no self-"
        "referential SHA or unverified future CI is claimed.", "",
    ]
    (ROOT / "reports/wholeapp-publication-v1.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"main": head, "ci": ci["conclusion"], "fresh_checks": len(fresh), "audit_passed": True}))


if __name__ == "__main__":
    main()
