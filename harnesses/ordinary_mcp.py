"""Container MCP transport. Its run capability is not an Azure credential."""
import json
import os
import sys
import urllib.request


def process(message):
    method, request_id = message.get("method"), message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "project-tools", "version": "2.0.0"}}
    elif method == "ping":
        result = {}
    elif method in ("tools/list", "tools/call"):
        request = urllib.request.Request(
            os.environ["PROJECT_PROXY_URL"] + "/project/rpc",
            data=json.dumps({"method": method, "params": message.get("params", {})}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + os.environ["PROJECT_RUN_CAPABILITY"]},
        )
        with urllib.request.urlopen(request, timeout=70) as response:
            payload = json.load(response)
        if "error" in payload:
            return {"jsonrpc": "2.0", "id": request_id, "error": payload["error"]}
        result = payload["result"]
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not supported"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


if __name__ == "__main__":
    for line in sys.stdin:
        message = {}
        try:
            message = json.loads(line)
            response = process(message)
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": message.get("id"),
                        "error": {"code": -32000, "message": type(error).__name__ + ": " + str(error)}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
