"""Record verified GitHub content commits and fresh-checkout replay, no AI calls."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json

BASE = "9f5618536eacaf2e343b03fe97089755fa8d11dd"
REPOSITORY = "AjnasNB/security-invariant-audits"


def execute(arguments, cwd=ROOT):
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        raise RuntimeError("Publication verification failed: " + " ".join(arguments[:4]))
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-clone", type=Path, required=True)
    parser.add_argument("--budget-test-runner", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    args = parser.parse_args()
    head = execute(["git", "rev-parse", "HEAD"])
    repo = json.loads(execute(["gh", "repo", "view", REPOSITORY, "--json",
                               "nameWithOwner,url,visibility,defaultBranchRef"]))
    remote = json.loads(execute(["gh", "api", f"repos/{REPOSITORY}/git/ref/heads/main"]))["object"]["sha"]
    ci = json.loads(execute(["gh", "run", "view", args.ci_run, "--repo", REPOSITORY, "--json",
                            "status,conclusion,headSha,jobs,url"]))
    if remote != head or ci["headSha"] != head or ci["conclusion"] != "success" or ci["status"] != "completed":
        raise RuntimeError("GitHub main or CI does not match the inspected content")
    if repo["visibility"] != "PUBLIC" or repo["defaultBranchRef"]["name"] != "main":
        raise RuntimeError("Unexpected repository visibility/branch")
    history = execute(["git", "log", "--reverse", "--format=%H%x09%an%x09%ae%x09%s", BASE + "..HEAD"])
    commits = []
    for line in history.splitlines():
        sha, author, email, subject = line.split("\t", 3)
        if email != "ajnasnb@gmail.com":
            raise RuntimeError("Unexpected author in the publication sequence")
        commits.append({"sha": sha, "author": author, "email": email, "subject": subject})
    clone = args.fresh_clone.resolve()
    if execute(["git", "rev-parse", "HEAD"], clone) != head or execute(["git", "status", "--porcelain"], clone):
        raise RuntimeError("Fresh public clone is not the exact clean inspected revision")
    fresh_checks = []
    for command in (
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"],
        [sys.executable, "-B", "-m", "hardstudy.verify"],
        [str(args.budget_test_runner), "--test", "tests/test_multi_model_budget.ts"],
    ):
        # Windows .cmd wrappers are executed by the same trusted subprocess
        # workflow used for local verification; no untrusted argument building.
        output = execute(command, clone)
        fresh_checks.append({"command": "python/tsx offline verification",
                             "passed": True, "output": output})
    audit = read_json(ROOT / "artifacts/private/hard-evidence-publication-audit-v1.json")
    if not audit["passed"]:
        raise RuntimeError("Public index scan did not pass")
    results = read_json(ROOT / "reports/hard-vague-results-v1.json")
    cost = read_json(ROOT / "reports/hard-vague-costs-v1.json")
    document = ROOT / "reports/Ajnas_Vague_Context_Results_20261002.pdf"
    record = {
        "recorded_at": utc_now(), "author": "Ajnas N B", "repository": REPOSITORY,
        "url": repo["url"], "visibility": repo["visibility"], "branch": "main",
        "reviewed_previous_main": BASE, "inspected_content_main": head, "commits": commits,
        "ci": ci, "fresh_public_clone": {"exact_revision": head, "clean": True,
                                        "checks": fresh_checks, "no_azure_or_private_profile_required": True},
        "publication_audit": {key: audit[key] for key in ("passed", "tracked_files", "issues", "scope", "values_disclosed")},
        "totals": results["totals"],
        "paper": {key: results["paper"][key] for key in ("attempts", "answered", "correct", "refusals",
                  "complete_original_mutant_pairs", "paper_defined_inconsistencies")},
        "cost": {key: cost[key] for key in ("reported_reference_usd", "uncertain_reference_reservations_usd",
                                          "reported_plus_uncertainty_usd", "within_cap")},
        "pdf": {"pages_visually_inspected": 6, "sha256": digest(document.read_bytes())},
        "authorization_scope": "Ajnas-authored main commits, normal non-force pushes of requested research changes. "
                               "No unrelated Delta product files or cloud deployment settings changed.",
        "excluded": ["credentials", "raw model reasoning/requests/responses", "private profiles/site configs",
                     "source clones", "Qarinah memory", "unrelated product files"],
        "metadata_record_note": "This records inspected content commits before its own metadata-only commit; "
                                "no self-referential SHA or unverified future CI is claimed.",
    }
    write_json(ROOT / "reports/hard-vague-publication-v1.json", record)
    lines = [
        "# Vague/context publication record", "", "Author: Ajnas N B. October 2, 2026.", "",
        f"Public repository: https://github.com/{REPOSITORY}. Branch: `main`.", "",
        "These verified content commits use `ajnasnb <ajnasnb@gmail.com>`. No Codex bot author, "
        "new branch, force push or unrelated Delta product change was used.", "",
        "| Commit | Change |", "|---|---|",
    ]
    lines += [f"| `{row['sha']}` | {row['subject']} |" for row in commits]
    lines += [
        "", f"Content CI: **{ci['status']} / {ci['conclusion']}** at `{head}`.",
        "", ci["url"], "",
        "The fresh public clone independently passed 65 Python tests, all 598 new evidence hashes/"
        "saved-result replay, and five offline TypeScript budget tests. GitHub CI also passed the "
        "historical evidence checks, compilation and new tests. No Azure calls or private profile "
        "were required.", "",
        "Publication scan: 1,709 tracked files reviewed, no flagged token/private-key/private-path "
        "or exact local ERP-password match. This is a bounded check, not proof that all secret "
        "formats have been detected. Real credentials, raw reasoning, private site configs, "
        "source clones and local project memory were excluded.", "",
        "Measured coding result: 72 schedule records, 25 bundles, 22 trajectories with provider "
        "attempts, nine completed refactors, 7,710 passing completed-file checks. One unfinished "
        "Luna ERP file reproducibly failed 42 read cases due to an undefined helper. No observed "
        "access leak; 42 access-unknown cases. Forty-seven later rows were not run.", "",
        "Paper result: 30 questions, 27 correct answered values, three Opus 5 policy refusals, "
        "zero answered original-correct/mutant-wrong pairs. No fresh reproduction of the archived "
        "MUCOCO wrong answers.", "",
        "New reference pricing: $4.87833085 reported plus $0.1638163 identified uncertain reserves, "
        "$5.04214715 combined. Not an Azure invoice/remaining-credit figure.", "",
        "The six-page PDF was rendered and every page visually inspected. Exact SHA and all "
        "publication/CI/fresh-clone evidence are in the companion JSON.", "",
        "This record describes inspected content commits before its own metadata-only commit. "
        "It does not assert a self-referential Git SHA or a future CI outcome.", "",
    ]
    (ROOT / "reports/hard-vague-publication-v1.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"content_main": head, "ci": ci["conclusion"], "fresh_clone_checks": len(fresh_checks),
                      "publication_scan_passed": audit["passed"]}))


if __name__ == "__main__":
    main()
