import json

from research.io import ROOT, utc_now, write_json
from research.sandbox import run_container

if __name__ == "__main__":
    result = run_container(
        ROOT / "_sources" / "django_multitenant", ["/adapter/tenant_worker.py"],
        extra_mounts=[(ROOT / "research" / "tenant_worker.py", "/adapter/tenant_worker.py")],
        image="ajnas-security-tenant:20261001", timeout=60,
    )
    if result.returncode:
        record = {"tested_at": utc_now(), "passed": False, "status": "environment_error", "error": result.stderr[-2500:]}
        write_json(ROOT / "artifacts" / "tenant_integration.json", record)
        raise RuntimeError(result.stderr[-2000:])
    record = {"tested_at": utc_now(), **json.loads(result.stdout)}
    write_json(ROOT / "artifacts" / "tenant_integration.json", record)
    print(json.dumps(record, indent=2))
    if not record["passed"]:
        raise SystemExit(1)
