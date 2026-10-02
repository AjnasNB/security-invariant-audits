"""Confirmed token identity for unsafe HTTP checks; no CSRF false successes."""
import gzip
import json
import secrets

from erp.evaluate import IMAGE
from research.io import read_json, write_json, digest, utc_now
from wholeapp.runtime import AREA, WORKSPACES, reset, checked, NETWORK, mount_options, DATABASE, metadata


def setup():
    reset()
    users = ["Administrator", *read_json(AREA / "fixture.json")["source"]["users"].values()]
    credentials = {user: {"api_key": secrets.token_hex(16), "api_secret": secrets.token_hex(24)} for user in users}
    write_json(AREA / "api-credentials.json", credentials)
    completed = checked(["run", "--rm", "-i", "--network", NETWORK, "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "1000:1000",
        "--memory", "600m", "--pids-limit", "96", "--tmpfs", "/tmp:rw,size=67108864",
        *mount_options(WORKSPACES / "baseline"), "--entrypoint", "/home/frappe/frappe-bench/env/bin/python",
        "-e", "PYTHONDONTWRITEBYTECODE=1", IMAGE, "-B", "/adapter/auth_worker.py"],
        input=json.dumps({"credentials": credentials}).encode(), timeout=45)
    private = metadata()
    snapshot = checked(["exec", "-i", DATABASE, "sh", "-c",
        "read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb-dump -uroot "
        f"--single-transaction --skip-lock-tables --no-tablespaces --hex-blob {private['database']}"],
        input=(private["root_password"] + "\n").encode(), timeout=50).stdout
    previous = AREA / "fixture-snapshot.sql.gz"
    previous.rename(AREA / "fixture-before-api-auth.sql.gz")
    with gzip.open(previous, "wb") as handle:
        handle.write(snapshot)
    write_json(AREA / "fixture-api-auth-receipt.json", {"created_at": utc_now(), "snapshot_sha256": digest(snapshot),
        "database": "Disposable copy only", "authentication": "Per-user study-only API token, identity confirmed before writes",
        "credentials_excluded_from_agent_and_public_export": True})
    print(completed.stdout.decode().strip())


if __name__ == "__main__":
    setup()
