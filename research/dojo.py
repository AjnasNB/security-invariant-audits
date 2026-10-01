import json

from research.io import ROOT, utc_now, write_json
from research.sandbox import run_container

if __name__ == "__main__":
    result = run_container(
        ROOT / "_sources" / "agentdojo", ["/adapter/dojo_worker.py"],
        extra_mounts=[(ROOT / "research" / "dojo_worker.py", "/adapter/dojo_worker.py")], timeout=60,
    )
    if result.returncode:
        write_json(ROOT / "artifacts" / "agentdojo_smoke.json", {
            "tested_at": utc_now(), "passed": False, "error": result.stderr[-2000:],
        })
        raise RuntimeError(result.stderr[-2000:])
    record = {"tested_at": utc_now(), **json.loads(result.stdout)}
    write_json(ROOT / "artifacts" / "agentdojo_smoke.json", record)
    print(json.dumps(record, indent=2))
    if not record["passed"]:
        raise SystemExit(1)
