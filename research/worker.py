"""Untrusted-side execution adapter. It outputs observations, never safety labels."""
import contextlib
import importlib.util
import io
import json
import sys


def run_fixture(payload):
    spec = importlib.util.spec_from_file_location("candidate", "/task/target.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    function = getattr(module, {
        "access_helper": "can_read",
        "invoice_lookup": "read_invoice",
        "invoice_list": "list_invoices",
    }[payload["task_id"]])
    observations = []
    for case in payload["cases"]:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                value = function(*case["args"])
            observations.append({"id": case["id"], "value": value})
        except Exception as error:
            observations.append({"id": case["id"], "error": type(error).__name__ + ": " + str(error)[:300]})
    return observations


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    if payload["task_id"] == "fastapi_items":
        from app_worker import run_application
        observations = run_application(payload)
    else:
        observations = run_fixture(payload)
    print(json.dumps(observations))
