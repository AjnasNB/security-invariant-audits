"""Host-side ERP lifecycle. No provider credentials enter the ERP containers."""
import argparse
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "erp" / "private"
ENV = PRIVATE / "experiment.env"
COMPOSE = os.environ.get("STUDY_COMPOSE", "/usr/libexec/docker/cli-plugins/docker-compose")


def linux_path(path):
    path = Path(path).resolve()
    return "/mnt/" + path.drive[0].lower() + "/" + path.as_posix()[3:] if os.name == "nt" else str(path)


def prefix():
    return ["wsl", "-d", "Ubuntu", "--"] if os.name == "nt" else []


def compose(args, **kwargs):
    return subprocess.run(prefix() + [COMPOSE, "--env-file", linux_path(ENV),
        "-f", linux_path(ROOT / "erp" / "compose.yml"), *args],
        cwd=ROOT, encoding="utf-8", **kwargs)


def initialize():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if not ENV.exists():
        ENV.write_text("ERP_DB_PASSWORD=" + secrets.token_hex(24) +
                       "\nERP_ADMIN_PASSWORD=" + secrets.token_hex(24) + "\n",
                       encoding="utf-8")
    return ENV


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "pull", "up", "status", "logs", "stop", "seed", "source", "baseline"))
    args = parser.parse_args()
    initialize()
    if args.command == "init":
        print("Private experiment credentials generated. Do not publish erp/private.")
        return
    commands = {"pull": ["pull"], "up": ["up", "-d"],
        "status": ["ps", "-a"], "logs": ["logs", "--tail", "30", "create-site", "backend"],
        "stop": ["stop"], "source": ["exec", "-T", "backend", "bash", "-c",
            "cat sites/apps.json; ./env/bin/python -c 'import frappe,erpnext; print(frappe.__version__,erpnext.__version__)'"]}
    if args.command in commands:
        result = compose(commands[args.command])
        raise SystemExit(result.returncode)
    script = ROOT / "erp" / ("seed.py" if args.command == "seed" else "observations.py")
    content = script.read_text(encoding="utf-8")
    code = "import os\nos.chdir('/home/frappe/frappe-bench/sites')\nimport frappe\nfrappe.init(site='audit.local',sites_path='.')\nfrappe.connect()\n" + content
    result = compose(["exec", "-T", "backend", "./env/bin/python", "-"], input=code, capture_output=True)
    (PRIVATE / (args.command + ".stdout")).write_text(result.stdout, encoding="utf-8")
    (PRIVATE / (args.command + ".stderr")).write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        print(result.stderr[-2500:])
        raise SystemExit(result.returncode)
    print(result.stdout[-3500:])


if __name__ == "__main__":
    main()
