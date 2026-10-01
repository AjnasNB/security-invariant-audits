"""Isolated launch/configuration for pinned actual open-source agent releases."""
import json
import secrets
import subprocess
import time

from research.io import ROOT, read_json, write_json

IMAGE = "ajnas-open-harness-ordinary:20261001"
NETWORK = "ajnas-study-internal"
HOST_IP = "172.30.100.1"


def configuration(engine, mode, settings, url):
    prediction = mode == "prediction"
    if engine == "codex":
        catalog = read_json(ROOT / "_sources/codex_cli/codex-rs/models-manager/models.json")
        model = next(model for model in catalog["models"] if model["slug"] == "gpt-6.1-sol").copy()
        model.update({"slug": "maqam-orchestrator-sol-6-1", "tool_mode": "direct",
                      "supports_search_tool": False, "apply_patch_tool_type": None,
                      "shell_type": "disabled", "use_responses_lite": False, "prefer_websockets": False})
        write_json(settings / "models.json", {"models": [model]})
        content = "\n".join([
            'model = "maqam-orchestrator-sol-6-1"', 'model_provider = "azure_research"',
            'model_catalog_json = "/run/models.json"', 'model_reasoning_effort = "low"',
            'model_context_window = 28000', 'model_auto_compact_token_limit = 26000',
            'approval_policy = "never"', 'sandbox_mode = "read-only"', 'web_search = "disabled"',
            '[features]', 'shell_tool = false', 'multi_agent = false', 'view_image = false',
            '[model_providers.azure_research]', 'name = "Azure research relay"',
            f'base_url = "{url}/v1"', 'env_key = "PROJECT_RUN_CAPABILITY"', 'wire_api = "responses"',
            'supports_websockets = false', 'request_max_retries = 0', 'stream_max_retries = 0',
            '[history]', 'persistence = "none"', '[analytics]', 'enabled = false',
            '[feedback]', 'enabled = false',
        ])
        if not prediction:
            content += "\n" + "\n".join([
                '[mcp_servers.project]', 'command = "python"', 'args = ["/opt/project/ordinary_mcp.py"]',
                'startup_timeout_sec = 20', 'tool_timeout_sec = 75', 'required = true',
                'default_tools_approval_mode = "auto"',
                'env_vars = ["PROJECT_PROXY_URL", "PROJECT_RUN_CAPABILITY"]',
            ])
        (settings / "config.toml").write_text(content + "\n", encoding="utf-8", newline="\n")
        return ["sh", "-c", "mkdir -p /tmp/home/.codex && cp /run/config.toml /tmp/home/.codex/config.toml && "
                "exec codex exec --skip-git-repo-check --ephemeral --ignore-rules --json --color never "
                "-C /task - < /run/prompt.txt"], {}
    if engine == "opencode":
        permissions = {"*": "deny", **({} if prediction else {"project_*": "allow"})}
        model_id = "openai/maqam-orchestrator-sol-6-1"
        config = {
            "$schema": "https://opencode.ai/config.json", "model": model_id, "small_model": model_id,
            "enabled_providers": ["openai"], "share": "disabled", "autoupdate": False,
            "snapshot": False, "formatter": False, "lsp": False,
            "compaction": {"auto": False, "prune": False}, "permission": permissions,
            "provider": {"openai": {"npm": "@ai-sdk/openai", "options": {
                "baseURL": url + "/v1", "apiKey": "{env:PROJECT_RUN_CAPABILITY}", "timeout": 90000,
            }, "whitelist": ["maqam-orchestrator-sol-6-1"], "models": {"maqam-orchestrator-sol-6-1": {
                "name": "Azure GPT-6.1 Sol", "reasoning": True, "temperature": False, "tool_call": True,
                "limit": {"context": 28000, "output": 256 if prediction else 1536},
                "options": {"reasoningEffort": "low", "store": False},
                "variants": {"low": {"reasoningEffort": "low"}},
            }}}},
            "agent": {"build": {"steps": 1 if prediction else 8, "permission": permissions}},
        }
        if not prediction:
            config["mcp"] = {"project": {"type": "local", "command": ["python", "/opt/project/ordinary_mcp.py"],
                "enabled": True, "environment": {"PROJECT_PROXY_URL": url}, "timeout": 75000}}
        write_json(settings / "opencode.json", config)
        return ["sh", "-c", "export OPENCODE_CONFIG_CONTENT=\"$(cat /run/opencode.json)\"; "
                "exec opencode run --format json --model openai/maqam-orchestrator-sol-6-1 "
                "--variant low --dir /task < /run/prompt.txt"], {
            "OPENCODE_TEST_HOME": "/tmp/home", "OPENCODE_PURE": "1",
            "OPENCODE_AUTH_CONTENT": "{}", "OPENCODE_DISABLE_AUTOCOMPACT": "1",
        }
    if engine == "openhands":
        return ["python", "/opt/project/ordinary_openhands.py"], {}
    raise ValueError("Unknown primary agent")


def launch(engine, mode, workspace, directory, prompt, capability, port, timeout):
    settings = directory / "settings"
    settings.mkdir()
    (settings / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
    url = f"http://{HOST_IP}:{port}"
    arguments, additional_environment = configuration(engine, mode, settings, url)
    environment = {"PROJECT_PROXY_URL": url, "PROJECT_RUN_CAPABILITY": capability,
                   "PROJECT_MODE": mode, **additional_environment}
    name = "ajnas-ordinary-" + secrets.token_hex(6)
    command = [
        "docker", "run", "--rm", "--name", name, "--network", NETWORK,
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--memory", "1536m", "--cpus", "2", "--pids-limit", "100",
        "--tmpfs", "/tmp:rw,nosuid,size=384m", "--workdir", "/task",
        "--mount", f"type=bind,source={workspace},target=/task,readonly",
        "--mount", f"type=bind,source={settings},target=/run,readonly",
    ]
    for key, value in environment.items():
        command += ["-e", f"{key}={value}"]
    command += [IMAGE, *arguments]
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                "elapsed_seconds": time.monotonic() - started, "timeout": False}
    except subprocess.TimeoutExpired as error:
        cleanup = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        return {"exit_code": 124, "stdout": error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or "",
                "stderr": error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or "",
                "elapsed_seconds": time.monotonic() - started, "timeout": True,
                "cleanup_confirmed": cleanup.returncode == 0}
