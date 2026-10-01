"""Unmodified OpenHands SDK loop with the same four ordinary project tools."""
import json
import os
import urllib.request
from collections.abc import Sequence
from typing import ClassVar

from pydantic import Field, SecretStr
from openhands.sdk import LLM, Agent, Conversation, TextContent, ToolDefinition
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool


class Result(Observation):
    value: dict = Field(default_factory=dict)

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        return [TextContent(text=json.dumps(self.value, ensure_ascii=False))]


class Read(Action):
    path: str = Field(description="Project text file path")


class Write(Action):
    path: str = Field(description="invoice_service.py")
    content: str = Field(description="Complete replacement source")
    expected_sha256: str = Field(description="Latest file content hash")


class Edit(Action):
    path: str = Field(description="invoice_service.py")
    old_text: str = Field(description="One exact existing block")
    new_text: str = Field(description="Replacement source block")
    expected_sha256: str = Field(description="Latest file content hash")


class Test(Action):
    pass


class Execute(ToolExecutor):
    def __init__(self, name):
        self.name = name

    def __call__(self, action, conversation=None):
        arguments = action.model_dump(exclude={"kind", "security_risk", "summary"})
        request = urllib.request.Request(
            os.environ["PROJECT_PROXY_URL"] + "/project/rpc",
            data=json.dumps({"method": "tools/call",
                             "params": {"name": self.name, "arguments": arguments}}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + os.environ["PROJECT_RUN_CAPABILITY"]},
        )
        with urllib.request.urlopen(request, timeout=70) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(payload["error"]["message"])
        return Result(value=json.loads(payload["result"]["content"][0]["text"]))


class InspectTool(ToolDefinition):
    name: ClassVar[str] = "inspect_file"

    @classmethod
    def create(cls, conv_state, **params):
        return [cls(description="Read a project text file and its content hash.", action_type=Read,
                    observation_type=Result, executor=Execute(cls.name))]


class UpdateTool(ToolDefinition):
    name: ClassVar[str] = "update_file"

    @classmethod
    def create(cls, conv_state, **params):
        return [cls(description="Replace invoice_service.py with complete source using its latest hash.",
                    action_type=Write, observation_type=Result, executor=Execute(cls.name))]


class EditTool(ToolDefinition):
    name: ClassVar[str] = "edit_block"

    @classmethod
    def create(cls, conv_state, **params):
        return [cls(description="Replace one exact source block in invoice_service.py using its latest hash.",
                    action_type=Edit, observation_type=Result, executor=Execute(cls.name))]


class TestsTool(ToolDefinition):
    name: ClassVar[str] = "run_tests"

    @classmethod
    def create(cls, conv_state, **params):
        return [cls(description="Run the project tests and return the test counts.",
                    action_type=Test, observation_type=Result, executor=Execute(cls.name))]


class ProjectTools(ToolDefinition):
    @classmethod
    def create(cls, conv_state, **params):
        return [*InspectTool.create(conv_state), *UpdateTool.create(conv_state),
                *EditTool.create(conv_state), *TestsTool.create(conv_state)]


register_tool("ProjectTools", ProjectTools)

if __name__ == "__main__":
    prediction = os.environ.get("PROJECT_MODE") == "prediction"
    llm = LLM(
        model="openai/maqam-orchestrator-sol-6-1", model_canonical_name="openai/gpt-6.1-sol",
        api_mode="responses", capability_overrides={"supports_responses_api": True,
            "supports_reasoning_effort": True, "supports_sampling_params": False, "supports_vision": False},
        api_key=SecretStr(os.environ["PROJECT_RUN_CAPABILITY"]),
        base_url=os.environ["PROJECT_PROXY_URL"] + "/v1",
        max_output_tokens=256 if prediction else 1536, reasoning_effort="low",
        enable_encrypted_reasoning=True, num_retries=0, usage_id="research",
    )
    agent = Agent(llm=llm, tools=[] if prediction else [Tool(name="ProjectTools")],
                  include_default_tools=["FinishTool"])
    conversation = Conversation(agent=agent, workspace="/task", persistence_dir="/tmp/openhands-state",
        max_iteration_per_run=2 if prediction else 8, visualizer=None, delete_on_close=True)
    conversation.send_message(open("/run/prompt.txt", encoding="utf-8").read())
    try:
        conversation.run()
        print("PROJECT_RESULT:" + json.dumps({"status": str(conversation.state.execution_status),
                                              "finished": conversation.state.execution_status.value == "finished"}))
    finally:
        conversation.close()
