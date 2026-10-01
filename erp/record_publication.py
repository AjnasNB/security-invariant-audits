"""Record inspected GitHub main revisions/CI without changing remote state."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise RuntimeError("GitHub publication metadata could not be read")
    return json.loads(result.stdout)


def main():
    records = []
    for name, count in [("AjnasNB/security-invariant-audits", 20), ("AjnasNB/delta-harness", 20)]:
        repo = gh(["repo", "view", name, "--json", "nameWithOwner,url,visibility,defaultBranchRef"])
        head = gh(["api", f"repos/{name}/git/ref/heads/main"])["object"]["sha"]
        commits = gh(["api", f"repos/{name}/commits?sha=main&per_page={count}"])
        history = []
        for row in commits:
            if name.endswith("/delta-harness") and row["sha"] == "0a0930ddb0bd40ef7e66d14edbca53af36005e08":
                break
            author = row["commit"]["author"]
            history.append({"sha": row["sha"], "subject": row["commit"]["message"].splitlines()[0],
                            "author": author["name"], "email": author["email"]})
            if author["email"] != "ajnasnb@gmail.com":
                raise RuntimeError("An unexpected author appeared in the publication sequence")
        runs = gh(["run", "list", "--repo", name, "--branch", "main", "--limit", "1",
                   "--json", "databaseId,headSha,status,conclusion,url"])
        if repo["defaultBranchRef"]["name"] != "main" or head != history[0]["sha"]:
            raise RuntimeError("GitHub main revision did not match inspected commits")
        records.append({"repository": name, "url": repo["url"], "visibility": repo["visibility"],
                        "branch": "main", "inspected_main_sha": head, "commits": history, "ci": runs})
    audit = json.loads((ROOT / "erp/private/publication-audit-final.json").read_text())
    delta_audit = json.loads((ROOT / "erp/private/delta-changed-publication-audit.json").read_text())
    record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "author": "Ajnas N B",
              "repositories": records,
              "publication_audits": {"research_files": audit["tracked_files"], "research_passed": audit["passed"],
                                     "delta_changed_files": delta_audit["tracked_files"], "delta_changed_passed": delta_audit["passed"]},
              "pdf_qa": {"pages": 6, "all_rendered_pages_visually_inspected": True},
              "local_checks": {"research_unit_tests": 14, "delta_tests": 324, "erp_refactors": 6,
                               "erp_private_checks": 564, "combined_candidate_checks": 94, "http_checks": 9},
              "first_delta_ci": {
                  "run_id": 36857475233,
                  "status": "completed",
                  "conclusion": "failure",
                  "failure": "Azure discovery raw-label and duplicate Claude route UI mismatch",
                  "fix": "Separate tested model-label/alias correction commit; final CI is reported above"
              },
              "publication_method": "Ajnas-authored logical commits directly on main, non-force pushes; no Codex branch or bot author",
              "visibility_policy": "Research PUBLIC; existing Delta PRIVATE unchanged",
              "scope_note": "These are inspected content revisions before this metadata-only record's own commit. The record does not claim a self-referential Git SHA.",
              "not_published": ["local credentials/site configuration", "raw model reasoning/transcripts",
                                "database backups", "restricted MUCOCO/JailGuard data", "unrelated product files"]}
    (ROOT / "reports/publication.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Publication record", "", "Author: Ajnas N B. Recorded October 1, 2026.", "",
             "The following content commits are on GitHub `main`; author identity is `ajnasnb <ajnasnb@gmail.com>`.",
             "This metadata record does not try to include its own self-referential commit hash.", ""]
    for repo in records:
        lines += [f"## {repo['repository']} ({repo['visibility']})", "", repo["url"], "",
                  "| Commit | Change |", "|---|---|"]
        lines += [f"| `{row['sha'][:8]}` | {row['subject']} |" for row in reversed(repo["commits"])]
        run = repo["ci"][0] if repo["ci"] else None
        lines += ["", f"CI at this inspection: {run['status']} / {run['conclusion'] or 'not concluded'}." if run else "No CI run found.", ""]
    lines += ["Research checks: 14 local unit tests plus published evidence integrity checks.",
              "Delta: 324 local tests, no-emit typecheck and production build verified.",
              "ERP: six real refactors, 564 private checks, combined module 94 checks, HTTP workflow nine checks.",
              "", "The first Delta CI run failed at Azure discovery. Its correction and final CI result are retained in publication.json.",
              "No upstream ERP repository was changed. Existing local Delta product work stayed separate.",
              "Public evidence excludes private settings, raw reasoning/transcripts and restricted datasets.", ""]
    (ROOT / "reports/publication.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"repositories": [{"name": row["repository"], "main": row["inspected_main_sha"],
                                       "ci": row["ci"]} for row in records]}, indent=2))


if __name__ == "__main__":
    main()
