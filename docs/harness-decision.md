# Harness decision

Subsequent October 1 update: the tested Delta product fixes and GPT-6.1 Sol
preset are now implemented. Codex/OpenHands/Claude Code smoke results and the
complete ERPNext extension are recorded separately. The original choice and
local-only assumptions below describe the initial MVP phase, not today's
publication status or a claim that other engines were never tested.

Decision date: October 1, 2026. Requested model: **Azure GPT-6.1 Sol**, not the
older Sol preset and not an automatically selected alternative.

Use Delta Native's actual `runNative` agent loop for this MVP with an external,
restricted research broker. The Delta code is imported from the existing local
project. No desktop source or profile is edited. Record its Git HEAD **and** file
hashes because the existing checkout contains local changes.

Why this is suitable for this experiment:

* We already have its provider parser, tool-call loop and event recording.
* Its extension interface supports read, target-only write and fixed tests
  without enabling a host shell.
* The requested Azure model works through its actual Responses parser and
  fresh CLI authentication.
* We can hold model, tools and permissions fixed between conditions.
* Public and independent assessment occur outside the agent's assertions.

Focused local Delta provider/tool/extension tests: 40 passed. Those establish
component behaviour, not the new study's security validity. Our separate
reference/seeded-fault checks validate the assessor. Live preflight validates
the integration.

Codex CLI is a reasonable automated comparison runner: official documentation
provides non-interactive `codex exec`, JSONL and explicit sandbox settings.
It is not evaluated here, so this project does **not** claim Delta outperforms
Codex, OpenHands, SWE-agent or any other engine. Swapping engines during the
pilot would make it harder to attribute differences.

HumanEval, MUCOCO, JailGuard and AgentDojo are benchmarks/method artefacts, not
interchangeable coding harnesses. They serve different roles in the source
and dataset register.

The saved Delta desktop `sol` selection points to `maqam-orchestrator-sol`
(older GPT-5.6), so the study uses a separate named research model key with
deployment `maqam-orchestrator-sol-6-1`. Azure control plane reports model
`gpt-6.1-sol`, version `2026-09-29`. Responses may report the deployment alias;
both pieces of evidence are retained. This is not a guaranteed immutable
provider snapshot.

Official guidance inspected:

* https://learn.chatgpt.com/docs/non-interactive-mode
* https://developers.openai.com/api/docs/models/gpt-6.1-sol
* https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses

Provider function calling uses Responses. The fixed research reasoning setting
is `low`, 4,096 output tokens per request, ten steps, no memory/plugins/teams,
and bounded execution. These settings define the experiment; they are not
a general claim about the globally "optimal" engine or decoding parameters.
