"""Real candidate HTTP observations; credentials/cookies never enter evidence."""
import argparse
import json
from pathlib import Path

from wholeapp.cases import cases
from wholeapp.judge import assess_saved
from wholeapp.runtime import AREA, metadata, start_server, stop_server, WORKSPACES, checked, NETWORK, linux_path
from research.io import read_json, write_json, utc_now


def run(workspace, output, public=False, overlays=None, selected_ids=None):
    output = Path(output)
    if output.exists():
        raise RuntimeError("Do not overwrite a prior HTTP experiment")
    fixture = read_json(AREA / "fixture.json")
    challenges = cases(fixture, public)
    if selected_ids is not None:
        challenges = [case for case in challenges if case["id"] in selected_ids]
    output.mkdir(parents=True)
    write_json(output / "cases.json", challenges)
    try:
        start_server(workspace, overlays)
        password = metadata()["login_password"]
        payload = {"login_password": password, "credentials": read_json(AREA / "api-credentials.json")
                   if (AREA / "api-credentials.json").exists() else {}, "requests": [
            {key: case[key] for key in ("id", "user", "method", "route", "payload") if key in case}
            for case in challenges]}
        response = checked(["run", "--rm", "-i", "--network", NETWORK, "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534", "--memory", "128m",
            "--pids-limit", "64", "--cpus", "1",
            "--mount", f"type=bind,source={linux_path(Path(__file__).with_name('http_worker.py'))},target=/client.py,readonly",
            "python:3.12-slim", "python", "-B", "/client.py"], input=json.dumps(payload).encode(),
            timeout=180)
        observed = json.loads(response.stdout)
        result = assess_saved(challenges, observed, fixture)
        write_json(output / "observations.json", observed)
        write_json(output / "assessment.json", result)
        write_json(output / "execution.json", {"completed_at": utc_now(), "real_http": True,
            "candidate_workspace": str(workspace), "public_smoke": public,
            "isolated_database": True, "cookies_credentials_private": True,
            "overlay_controls": sorted((overlays or {}).keys())})
        return result
    finally:
        stop_server()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=WORKSPACES / "baseline")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--selected", nargs="*")
    args = parser.parse_args()
    result = run(args.workspace, args.output, args.public, selected_ids=args.selected)
    print(json.dumps({key: value for key, value in result.items() if key not in ("checks", "by_surface")}))
