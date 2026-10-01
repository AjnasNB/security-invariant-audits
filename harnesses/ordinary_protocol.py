"""Freeze a representative cross-harness study before live calls."""
from research.natural_tasks import TASKS, schedule

VERSION = "open-harness-ordinary-v1"
PRIMARY = ("codex", "opencode", "openhands")


def protocol():
    return {
        "version": VERSION, "date": "2026-10-01", "author": "Ajnas N B",
        "primary_agents": list(PRIMARY), "task_templates": list(TASKS),
        "schedule": schedule(), "schedule_seed": 20261003,
        "tool_policy": "Four ordinary brokered file/edit/test tools; read-only candidate mount, "
                       "isolated agent network, independent final judge; native system instructions differ",
        "model": {"deployment": "maqam-orchestrator-sol-6-1", "name": "gpt-6.1-sol",
                  "version": "2026-09-29", "reasoning_effort": "low"},
        "coding_limits_per_primary_agent": {
            "max_http_attempts": 144, "max_requests_per_run": 9,
            "max_output_tokens": 1536, "max_input_estimate": 22000,
            "reference_cap_usd": .38, "conservative_cap_usd": 3,
            "wall_seconds": 150,
        },
        "prediction_limits_per_primary_agent": {
            "max_http_attempts": 16, "max_requests_per_run": 2,
            "max_output_tokens": 256, "max_input_estimate": 22000,
            "reference_cap_usd": .035, "conservative_cap_usd": .3,
            "wall_seconds": 75,
        },
        "prediction_selection": ["HumanEvalTF447", "HumanEvalTF466", "HumanEvalTF547"],
        "prediction_status": "Known-positive author cases, six original/mutant questions per primary "
                             "agent; separate from unbiased coding study and archived-answer replay",
        "optional_agents": {"aider": {"reference_cap_usd": .06},
                            "goose": {"reference_cap_usd": .06}},
        "total_reference_cap_usd": 1.50,
        "setup_reference_estimate_usd": .0794804,
        "cap_allocation": "Three coding caps at $0.38, three prediction caps at $0.035, "
                          "optional agents $0.06 each, plus recorded setup: at most $1.4444804. "
                          "Recorded setup was excluded from measured trajectories; no extra paid "
                          "preflight is permitted under this allocation.",
        "no_failure_mining": "No example replacement, no repeated failed generation, no silent "
                            "model substitution; setup attempts and budget stops retained",
        "scope": "Representative named agents, not every open-source harness or a global ranking",
        "auth": "Controller Azure CLI Entra tokens; disposable per-run proxy capability in agents. "
                "No Azure credential in cloned repositories, candidate files, prompts or Git.",
    }
