"""Execute selected archived benchmark programs in the existing no-network worker."""
import contextlib
import copy
import io
import json
import sys

payload = json.load(sys.stdin)
observations = []
for case in payload["cases"]:
    scope = {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(case["program"] + "\n" + case["author_tests"], "<archived-benchmark>", "exec"), scope)
            scope["check"](scope[case["entry_point"]])
            output = scope[case["entry_point"]](*copy.deepcopy(case["args"]))
        observations.append({"id": case["id"], "author_tests_passed": True,
                             "value": output, "return_type": type(output).__name__})
    except Exception as error:
        observations.append({"id": case["id"], "author_tests_passed": False,
                             "error": type(error).__name__ + ": " + str(error)})
print(json.dumps(observations))
