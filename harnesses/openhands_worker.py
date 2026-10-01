"""Native OpenHands Agent/Conversation with only the study custom-tool set."""
import json
import os
import urllib.request
from collections.abc import Sequence
from typing import ClassVar

from pydantic import Field, SecretStr

from openhands.sdk import LLM, Agent, Conversation, TextContent, ToolDefinition
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool


def call_broker(name, arguments):
    request = urllib.request.Request(
        os.environ["STUDY_BROKER_URL"] + "/study/rpc",
        data=json.dumps({"method": "tools/call", "params": {"name": name, "arguments": arguments}}).encode(),
        headers={"Content-Type": "application/json", "X-Study-Run": os.environ["STUDY_RUN_TOKEN"]},
    )
    with urllib.request.urlopen(request, timeout=65) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(payload["error"]["message"])
    return json.loads(payload["result"]["content"][0]["text"])


class StudyObservation(Observation):
    value: dict = Field(default_factory=dict)

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        return [TextContent(text=json.dumps(self.value, ensure_ascii=False))]


class ReadAction(Action):
    path: str = Field(description="One of target.py, PROJECT_NOTE.md, public_cases.json")


class WriteAction(Action):
    path: str = Field(description="Must be target.py")
    content: str = Field(description="Complete replacement Python source")
    expected_sha256: str = Field(description="Exact hash from the latest read")


class TestAction(Action):
    pass


class StudyExecutor(ToolExecutor):
    def __init__(self, tool_name):
        self.tool_name = tool_name

    def __call__(self, action, conversation=None):
        parameters = action.model_dump(exclude={"kind", "security_risk", "summary"})
        return StudyObservation(value=call_broker(self.tool_name, parameters))


class ReadTool(ToolDefinition):
    name: ClassVar[str] = "study_read_file"

    @classmethod
    def create(cls, conv_state, **params) -> Sequence[ToolDefinition]:
        return [cls(description="Read a listed task file with full hash. Absent notes return exists:false.",
                    action_type=ReadAction, observation_type=StudyObservation,
                    executor=StudyExecutor(cls.name))]


class WriteTool(ToolDefinition):
    name: ClassVar[str] = "study_write_file"

    @classmethod
    def create(cls, conv_state, **params) -> Sequence[ToolDefinition]:
        return [cls(description="Replace only target.py with complete source and matching expected_sha256.",
                    action_type=WriteAction, observation_type=StudyObservation,
                    executor=StudyExecutor(cls.name))]


class TestTool(ToolDefinition):
    name: ClassVar[str] = "study_run_public_tests"

    @classmethod
    def create(cls, conv_state, **params) -> Sequence[ToolDefinition]:
        return [cls(description="Execute all public checks in a separate no-network worker. Run after edits.",
                    action_type=TestAction, observation_type=StudyObservation,
                    executor=StudyExecutor(cls.name))]


class StudyTools(ToolDefinition):
    @classmethod
    def create(cls, conv_state, **params) -> Sequence[ToolDefinition]:
        return [*ReadTool.create(conv_state), *WriteTool.create(conv_state), *TestTool.create(conv_state)]


register_tool("AjnasStudyTools", StudyTools)

if __name__ == "__main__":
    llm = LLM(
        model="openai/maqam-orchestrator-sol-6-1",
        model_canonical_name="openai/gpt-6.1-sol",
        api_mode="responses",
        capability_overrides={"supports_responses_api": True, "supports_reasoning_effort": True,
                              "supports_sampling_params": False, "supports_vision": False},
        api_key=SecretStr(os.environ["STUDY_RUN_TOKEN"]),
        base_url=os.environ["STUDY_BROKER_URL"] + "/v1",
        max_output_tokens=4096, reasoning_effort="low", enable_encrypted_reasoning=True,
        num_retries=0, usage_id="research",
    )
    agent = Agent(llm=llm, tools=[Tool(name="AjnasStudyTools")],
                  include_default_tools=["FinishTool"])
    conversation = Conversation(agent=agent, workspace="/task", persistence_dir="/tmp/openhands-state",
                                max_iteration_per_run=14, visualizer=None, delete_on_close=True)
    conversation.send_message(open("/run/prompt.txt", encoding="utf-8").read())
    try:
        conversation.run()
        print(json.dumps({"engine": "OpenHands native SDK", "status": str(conversation.state.execution_status)}))
    finally:
        conversation.close()
