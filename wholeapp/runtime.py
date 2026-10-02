"""Disposable database/site/server. The existing ERP database is never rewritten."""
import gzip
import hashlib
import json
import os
import re
import secrets
import subprocess
import tarfile
import time
from pathlib import Path

from erp.evaluate import IMAGE, parse_record, seed
from erp.manage import ROOT, PRIVATE, linux_path, prefix
from research.io import digest, read_json, utc_now, write_json

AREA = ROOT / "artifacts/private/wholeapp-v1"
NETWORK = "ajnas-wholeapp-20261002"
DATABASE = "ajnas-wholeapp-db-20261002"
REDIS = "ajnas-wholeapp-redis-20261002"
SERVER = "ajnas-wholeapp-server-20261002"
PORT = 18081
FIXTURE_DATE = "2026-10-01T12:00:00"
SOURCES = {"frappe": ROOT / "_sources/large-frappe", "erpnext": ROOT / "_sources/large-erpnext"}
WORKSPACES = Path("C:/AjnasResearch/ERPRewrite20261002") if os.name == "nt" else AREA / "source-copies"


def docker(arguments, **kwargs):
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("timeout", 50)
    return subprocess.run(prefix() + ["docker", *arguments], **kwargs)


def checked(arguments, **kwargs):
    result = docker(arguments, **kwargs)
    if result.returncode:
        if AREA.is_dir():
            stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else result.stderr
            if (AREA / "private-runtime.json").exists():
                for value in metadata().values():
                    if isinstance(value, str) and len(value) > 20:
                        stderr = stderr.replace(value, "[redacted]")
            (AREA / "last-runtime-error.txt").write_text(stderr[-5000:], encoding="utf-8")
        # No raw Docker diagnostic: a runtime command may contain private config.
        raise RuntimeError("Disposable ERP operation failed: " + arguments[0])
    return result


def metadata():
    return read_json(AREA / "private-runtime.json")


def setup():
    if AREA.exists() and any(AREA.iterdir()):
        raise RuntimeError("Existing study evidence must not be overwritten")
    AREA.mkdir(parents=True, exist_ok=True)
    original_config = read_json(ROOT / "erp/protected/site_config.json")
    original_db = original_config["db_name"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", original_db):
        raise RuntimeError("Unexpected source experiment database name")
    old_values = dict(line.split("=", 1) for line in (PRIVATE / "experiment.env").read_text().splitlines())
    # Passwords are stdin/environment data, never persisted in public evidence.
    sql = (
        "read -r MYSQL_PWD; export MYSQL_PWD; "
        f"exec mariadb-dump --user=root "
        f"--single-transaction --skip-lock-tables --no-tablespaces --hex-blob {original_db}"
    )
    dump = checked(["exec", "-i", "ajnas-erp-security-20261001-db-1", "sh", "-c", sql],
                   input=(old_values["ERP_DB_PASSWORD"] + "\n").encode(), timeout=60)
    if not dump.stdout or len(dump.stdout) > 80_000_000:
        raise RuntimeError("Source experiment dump was empty or unexpectedly large")
    with gzip.open(AREA / "source-snapshot.sql.gz", "wb") as handle:
        handle.write(dump.stdout)
    archive = checked(["exec", "ajnas-erp-security-20261001-backend-1", "tar", "-C",
                       "/home/frappe/frappe-bench/sites", "-cf", "-", "audit.local", "apps.txt", "apps.json"],
                      timeout=40).stdout
    site_root = AREA / "sites"
    site_root.mkdir()
    import io
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        for member in source.getmembers():
            target = (site_root / member.name).resolve()
            if not target.is_relative_to(site_root.resolve()) or member.issym() or member.islnk():
                raise RuntimeError("Unsafe experiment site archive member")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                if member.size > 10_000_000:
                    raise RuntimeError("Unexpected site file size")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(member).read())
    config = {"db_name": original_db, "db_user": "ajnas_wholeapp", "db_password": secrets.token_hex(24),
              "db_type": "mariadb", "db_host": DATABASE, "db_port": 3306, "installed_apps": ["frappe", "erpnext"],
              "developer_mode": 0, "pause_scheduler": 1, "disable_website_cache": 1}
    common = {"db_host": DATABASE, "db_port": 3306, "redis_cache": f"redis://{REDIS}:6379",
              "redis_queue": f"redis://{REDIS}:6379", "redis_socketio": f"redis://{REDIS}:6379",
              "socketio_port": 9000, "serve_default_site": True}
    write_json(site_root / "audit.local/site_config.json", config)
    write_json(site_root / "common_site_config.json", common)
    for folder in ("logs", "sites/audit.local/private/files", "sites/audit.local/public/files"):
        (AREA / folder).mkdir(parents=True, exist_ok=True)
    private = {"database": original_db, "root_password": secrets.token_hex(24),
               "app_password": config["db_password"], "login_password": secrets.token_hex(24)}
    write_json(AREA / "private-runtime.json", private)
    if docker(["network", "inspect", NETWORK]).returncode == 0:
        raise RuntimeError("Disposable network name already exists; do not reuse a prior run")
    checked(["network", "create", "--internal", NETWORK])
    checked(["run", "-d", "--name", DATABASE, "--network", NETWORK, "--memory", "750m", "--cpus", "1",
             "--pids-limit", "128", "--tmpfs", "/var/lib/mysql:rw,nosuid,size=536870912",
             "--env", "MARIADB_ROOT_PASSWORD=" + private["root_password"], "mariadb:11.8"])
    checked(["run", "-d", "--name", REDIS, "--network", NETWORK, "--memory", "96m", "--cpus", ".3",
             "--pids-limit", "64", "--read-only", "--tmpfs", "/data:rw,size=16777216",
             "redis:6.2-alpine", "redis-server", "--save", "", "--appendonly", "no"])
    for _ in range(30):
        probe = docker(["exec", "-i", DATABASE, "sh", "-c",
                        "read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb -uroot --batch --skip-column-names -e 'SELECT 1'"],
                       input=(private["root_password"] + "\n").encode(), timeout=5)
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Disposable database did not become ready")
    initialize_sql = (f"CREATE DATABASE `{original_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                      f"CREATE USER 'ajnas_wholeapp'@'%' IDENTIFIED BY '{private['app_password']}';"
                      f"GRANT ALL ON `{original_db}`.* TO 'ajnas_wholeapp'@'%';")
    root_sql(initialize_sql.encode())
    root_sql(dump.stdout, database=True, timeout=60)
    dump_hash = hashlib.sha256(dump.stdout).hexdigest()
    record = {"created_at": utc_now(), "isolated": True, "source_database_read_only_export": True,
              "source_snapshot_sha256": dump_hash, "source_dump_bytes": len(dump.stdout),
              "database_storage": "Disposable RAM tmpfs, not the almost-full D: disk",
              "network": NETWORK, "candidate_http": f"http://127.0.0.1:{PORT}",
              "source_seed": seed(), "existing_application_unchanged": True}
    write_json(AREA / "setup-receipt.json", record)
    return record


def root_sql(data, database=False, timeout=50):
    private = metadata()
    target = private["database"] if database else ""
    command = f"read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb -uroot {target}"
    return checked(["exec", "-i", DATABASE, "sh", "-c", command],
                   input=(private["root_password"] + "\n").encode() + data, timeout=timeout)

def resume_setup():
    """Resume only the recorded, partially prepared disposable instance."""
    private = metadata()
    if (AREA / "setup-receipt.json").exists():
        raise RuntimeError("Setup is already complete; do not restore it over evidence")
    if docker(["inspect", DATABASE]).returncode:
        raise RuntimeError("Recorded disposable database is unavailable")
    database = private["database"]
    sql = (f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
           f"CREATE USER IF NOT EXISTS 'ajnas_wholeapp'@'%' IDENTIFIED BY '{private['app_password']}';"
           f"GRANT ALL ON `{database}`.* TO 'ajnas_wholeapp'@'%';")
    root_sql(sql.encode())
    with gzip.open(AREA / "source-snapshot.sql.gz", "rb") as handle:
        snapshot = handle.read()
    root_sql(snapshot, database=True, timeout=60)
    record = {"created_at": utc_now(), "isolated": True, "source_database_read_only_export": True,
              "source_snapshot_sha256": digest(snapshot), "source_dump_bytes": len(snapshot),
              "database_storage": "Disposable RAM tmpfs", "network": NETWORK,
              "candidate_http": f"http://127.0.0.1:{PORT}", "source_seed": seed(),
              "existing_application_unchanged": True, "setup_readiness_retry_retained": True}
    write_json(AREA / "setup-receipt.json", record)
    inventory = prepare_workspace(AREA / "baseline-workspace")
    write_json(AREA / "source-inventory.json", inventory)
    return record


def prepare_workspace(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    inventory = {}
    for name, source in SOURCES.items():
        tracked = subprocess.check_output(["git", "-C", str(source), "ls-files"], text=True).splitlines()
        for filename in tracked:
            origin = (source / filename).resolve()
            if not origin.is_relative_to(source.resolve()) or not origin.is_file():
                raise RuntimeError("Unexpected upstream tracked file")
            target = destination / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(origin.read_bytes())
            inventory[name + "/" + filename] = digest(target.read_bytes())
    (destination / "README.md").write_text(
        "# ERP application workspace\n\nFrappe provides the web, document and API framework. ERPNext provides "
        "the business modules. Both source trees are available here. Start with their READMEs and the "
        "application's request and document paths. The project test tool runs a small application smoke.\n",
        encoding="utf-8", newline="\n")
    return inventory


def mount_options(workspace, overlays=None):
    mounts = []
    for name in ("frappe", "erpnext"):
        mounts += ["--mount", f"type=bind,source={linux_path(Path(workspace) / name)},"
                   f"target=/home/frappe/frappe-bench/apps/{name},readonly"]
    mounts += ["--mount", f"type=bind,source={linux_path(AREA / 'sites')},target=/home/frappe/frappe-bench/sites",
               "--mount", f"type=bind,source={linux_path(AREA / 'logs')},target=/home/frappe/frappe-bench/logs",
               "--mount", f"type=bind,source={linux_path(ROOT / 'wholeapp')},target=/adapter,readonly"]
    if (AREA / "assets").is_dir():
        mounts += ["--mount", f"type=bind,source={linux_path(AREA / 'assets')},"
                   "target=/home/frappe/frappe-bench/assets,readonly"]
    for relative, origin in (overlays or {}).items():
        if not relative.startswith(("frappe/", "erpnext/")) or ".." in Path(relative).parts:
            raise RuntimeError("Invalid controlled overlay path")
        mounts += ["--mount", f"type=bind,source={linux_path(origin)},"
                   f"target=/home/frappe/frappe-bench/apps/{relative},readonly"]
    return mounts


def seed_fixtures(workspace):
    private = metadata()
    completed = checked(["run", "--rm", "-i", "--network", NETWORK, "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "1000:1000", "--memory", "900m", "--cpus", "1",
        "--pids-limit", "96", "--tmpfs", "/tmp:rw,size=134217728", *mount_options(workspace),
        "--entrypoint", "/home/frappe/frappe-bench/env/bin/python", "-e", "PYTHONDONTWRITEBYTECODE=1",
        IMAGE, "-B", "/adapter/seed_worker.py"],
        input=json.dumps({"source": seed(), "login_password": private["login_password"]}).encode(), timeout=60)
    fixture = parse_record(completed.stdout.decode("utf-8"))
    write_json(AREA / "fixture.json", fixture)
    snapshot = checked(["exec", "-i", DATABASE, "sh", "-c",
        f"read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb-dump -uroot "
        f'--single-transaction --skip-lock-tables --no-tablespaces --hex-blob {private["database"]}'],
        input=(private["root_password"] + "\n").encode(), timeout=50).stdout
    with gzip.open(AREA / "fixture-snapshot.sql.gz", "wb") as handle:
        handle.write(snapshot)
    write_json(AREA / "fixture-snapshot-receipt.json", {"sha256": digest(snapshot),
               "bytes": len(snapshot), "fictional_data_only": True, "exported_at": utc_now()})
    return fixture


def stop_server():
    if docker(["inspect", SERVER]).returncode == 0:
        checked(["rm", "-f", SERVER])


def reset():
    stop_server()
    with gzip.open(AREA / "fixture-snapshot.sql.gz", "rb") as handle:
        root_sql(handle.read(), database=True, timeout=60)
    checked(["exec", REDIS, "redis-cli", "FLUSHALL"])

def recover_runtime():
    """Rehydrate the same RAM database after a host/WSL shutdown."""
    for name in (DATABASE, REDIS):
        info = docker(["inspect", name])
        if info.returncode:
            raise RuntimeError("Recorded experiment container is missing")
        import json
        if not json.loads(info.stdout)[0]["State"]["Running"]:
            checked(["start", name])
    private = metadata()
    for _ in range(30):
        probe = docker(["exec", "-i", DATABASE, "sh", "-c",
            "read -r MYSQL_PWD; export MYSQL_PWD; exec mariadb -uroot --batch --skip-column-names -e 'SELECT 1'"],
            input=(private["root_password"] + "\n").encode(), timeout=5)
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Recovered database is not ready")
    create = (f"CREATE DATABASE IF NOT EXISTS `{private['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
              f"CREATE USER IF NOT EXISTS 'ajnas_wholeapp'@'%' IDENTIFIED BY '{private['app_password']}';"
              f"GRANT ALL ON `{private['database']}`.* TO 'ajnas_wholeapp'@'%';")
    root_sql(create.encode())
    reset()
    write_json(AREA / "runtime-recovery.json", {"at": utc_now(), "same_snapshot_restored": True,
        "new_model_generations": 0, "original_erp_not_modified": True,
        "reason": "WSL stopped mid-experiment; checkpoint and snapshot retained"})
    return {"recovered": True, "same_snapshot": True}

def start_server(workspace, overlays=None):
    reset()
    checked(["run", "-d", "--name", SERVER, "--network", NETWORK,
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "1000:1000",
        "--memory", "950m", "--cpus", "1.5", "--pids-limit", "128", "--tmpfs", "/tmp:rw,size=134217728",
        *mount_options(workspace, overlays), "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "FRAPPE_STREAM_LOGGING=1",
        "--entrypoint", "/home/frappe/frappe-bench/env/bin/python", IMAGE, "-B", "/adapter/server_boot.py"])
    for _ in range(25):
        ready = docker(["exec", SERVER, "/home/frappe/frappe-bench/env/bin/python", "-c",
            "import json,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/api/method/ping',"
            "headers={'X-Frappe-Site-Name':'audit.local'});assert json.load(urllib.request.urlopen(r,timeout=2))['message']=='pong'"],
            timeout=5)
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("Candidate application did not start; treat execution as unknown")


def cleanup():
    # Only fixed, explicitly created experiment container names are removed.
    stop_server()
    for name in (DATABASE, REDIS):
        if docker(["inspect", name]).returncode == 0:
            checked(["rm", "-f", name])
    if docker(["network", "inspect", NETWORK]).returncode == 0:
        checked(["network", "rm", NETWORK])
    return {"experiment_containers_removed": True, "ram_database_discarded": True,
            "private_snapshot_and_evidence_retained": True, "existing_erp_untouched": True}
