"""Container-side MCP stdio client. No provider key or hidden judge data."""
import json
import os
import sys
import urllib.error
import urllib.request


def broker(message):
    request = urllib.request.Request(
        os.environ["STUDY_BROKER_URL"] + "/study/rpc",
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Study-Run": os.environ["STUDY_RUN_TOKEN"]},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=65) as response:
        return json.load(response)


def process(message):
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "Ajnas protected research tools", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method in ("tools/list", "tools/call"):
        response = broker({"method": method, "params": message.get("params", {})})
        if "error" in response:
            return {"jsonrpc": "2.0", "id": request_id, "error": response["error"]}
        result = response["result"]
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not supported"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = process(message)
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": message.get("id") if "message" in locals() else None,
                        "error": {"code": -32000, "message": type(error).__name__ + ": " + str(error)}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
