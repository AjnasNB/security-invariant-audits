"""Execution adapter for multi-file candidates; receives no expected answers."""
import contextlib
import copy
import importlib.util
import io
import json
import sys


def run(payload):
    sys.path.insert(0, "/task")
    spec = importlib.util.spec_from_file_location("service", "/task/service.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    observations = []
    for case in payload["cases"]:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                value = module.run(*copy.deepcopy(case["args"]))
            observations.append({"id": case["id"], "value": value,
                                 "return_type": type(value).__name__,
                                 "item_types": [type(item).__name__ for item in value] if isinstance(value, list) else None})
        except Exception as error:
            observations.append({"id": case["id"], "error": type(error).__name__ + ": " + str(error)[:350]})
    return observations


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
