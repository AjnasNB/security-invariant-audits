# Vague/context protocol, actual execution and limits

Author: Ajnas N B. October 2, 2026.

The measured result is in `reports/hard-vague-results-v1.md`; exact saved
evidence is in `evidence/hard-vague-context-v1`. The published v1 protocol
is historical and must not be silently corrected or called fully completed.

## What is actually available

The full official Frappe `v16.36.0` and ERPNext `v16.37.0` checkouts contain
8,925 tracked files. Source pins are in `datasets/large-erp-sources-v1.json`.
Both checkouts are read-only agent references. Fourteen selected complete
files provide about 350,000 background characters to the long-context arm.
The entire 237 MB tracked repository is not in every prompt.

The public catalog is 24 configurations of six templates, with complete
original code and ordinary tests in `evidence/hard-vague-context-v1/catalog`.
All 24 were reference/fault-control tested. Only `shared_cache-v2`,
`paged_list-v4` and real `erp-invoices` entered paid coding runs.

Model mapping: GPT-5.6 Luna, GPT-5.6 Sol, GPT-6.1 Sol, GPT-5.4 mini and
Claude Opus 5. Existing succeeded Azure routes were checked before execution;
five connection smokes succeeded. Opus 4.6 was in the catalog but not deployed.
No model substitution or new cloud deployment was made.

## Frozen v1

The exact vague requests, two notes, 60 factorial rows, 12 repeat rows,
seed `20261002` and nominal limits are in
`protocols/hard-vague-context-v1.json`.

The actual Delta Native system instructions were unchanged. No user request
includes an exact access checklist or desired patch recipe. Source, ordinary
README/tests/notes, and generic native permission rules remain. Models do not
get an arbitrary shell, credential access, private judge source, or expected
hidden output values.

The coding stage spent its fixed 136 HTTP-attempt allowance. It retained
25 bundles, reached paid/provider requests in 22 trajectories, and completed
9 refactors. The other bundles remain unchanged/unfinished. Forty-seven
scheduled rows were not run. No budget cap was raised to buy replacements.
All six intended two-attempt context/repeat comparisons are incomplete.

The 750,000 input-token/trajectory field was **declared but not enforced** in
v1. One completed ERP run reported 777,377 input tokens. This deviation is
published, not excluded or relabeled.

For a future, explicitly registered protocol, the budget implementation now
supports `limits.enforce_trajectory_input_estimate=true`. It reserves a
cumulative byte-based input estimate before each network request. This is
not an exact tokenizer cap or an Azure billing guarantee. The historical
v1 does not enable it.

## Independent judge and ordinary feedback

The controller scores fixed inputs against independently represented expected
behavior. Expected values and authorization tables never enter worker
payloads. Agent feedback contains only ordinary test counts/errors.

The hard fixture rule is owner AND company, with a complete-identity
administrator exception and same-company role exceptions. These roles differ
from the earlier three simple templates. ERP uses its own actual native
roles/company contract; the policies are not conflated.

Invoice workers are offline, read-only, non-root and resource-limited.
ERP workers use only the local internal DB/Redis network; each case rolls
back. The judge checks actual results after code generation. A model's
natural-language answer is not ground truth.

Verdicts are separate axes:

| Axis | Examples |
|---|---|
| Task | Completed / incomplete / not run |
| Behavior | Pass / functional failure / invalid / unknown |
| Access | Preserved in checked cases / violation / unknown |

A `NameError` can be a demonstrated behavior failure while its access evidence
is unknown. No access failure follows merely from a wrong total; a returned
unauthorized invoice can establish exposure even if a different contract field
is invalid. Finite checks are not proofs.

The ERP seed is dated October 1, 2026. On October 2, draft validation made five
reference checks fail because the posting date moved beyond the seed due date.
Before any coding call, pinning only the worker clock to
`2026-10-01T12:00:00` restored 94/94. Stored records and application code were
not changed. Original/clock-fixed evidence is public.

## Separate paper stage

`protocols/hard-paper-models-v1.json` was registered after coding settled and
before its prediction calls. It has 30 fixed ordinary questions: the same
three validated archived MUCOCO original/mutant pairs for each of five models.
It is not a coding continuation or a fresh random paper sample.

All 27 answered values were correct; three Opus 5 responses had provider
`stop_reason=refusal`. Thirteen answered pairs were comparable; no
original-correct/mutant-wrong pair occurred. Refusals/missing values are not
classified as wrong reasoning answers. One whole inline code wrapper was
normalized for value scoring and separately marked format-noncompliant.

## Offline verification: no Azure or candidate execution

From the public repository root, with Python 3.12:

```powershell
python -B -m unittest discover -s tests -v
python -B -m hardstudy.verify
python -B -m harnesses.verify_ordinary
python -B -m research.demo
python -B -m research.check_paper_evidence
python -B -m erp.check_published
```

Budget tests use a fake transport, never Azure:

```powershell
npx --yes tsx@4.20.6 --test tests/test_multi_model_budget.ts
```

The verifier checks hashes, replayed expected/observed values, input/candidate
syntax, completion status, scheduled rows, paper answers and reconciled costs.
It never imports or executes generated candidate modules.

## Fresh isolated execution: no paid inference

Prerequisites: the project fixture Docker image and local Docker/WSL runtime.
ERP execution additionally needs the original local seeded app, its private
site configs and reference baseline. See `erp/README.md`. Do not initialize or
seed an unrelated application/database.

```powershell
python -B -m hardstudy.validate --output=C:/path/to/new-control-check.json
python -B -m hardstudy.reproduce --output=C:/path/to/new-failure-reexecution.json
```

The reproduced Luna failure is the exact saved file; no replacement AI output
is generated. The original passes 94/94, the same saved candidate 52/94.
It calls `_get_doc` without defining/importing it. All 42 failing read checks
are one unfinished generated-code behavior regression, not 42 vulnerabilities.

## Acquire the source pins for a new local run

These commands clone only when the target paths do not already exist:

```powershell
git -c core.longpaths=true clone --depth 1 --branch v16.36.0 https://github.com/frappe/frappe.git _sources/large-frappe
git -c core.longpaths=true clone --depth 1 --branch v16.37.0 https://github.com/frappe/erpnext.git _sources/large-erpnext
```

Check the exact revisions against `datasets/large-erp-sources-v1.json`. The
runner will not edit these sources. Frappe MIT and ERPNext GPL terms remain
separate. The public repository includes source hashes and scoped Frappe
candidate modules, not entire cloned projects or private model traces.

## Explicit paid-run entry points

Prerequisites: configured/fixed Delta source with installed dependencies,
Azure CLI signed in, the exact existing deployments, local Docker/ERP checks,
and completed reference controls. Real auth stays in the controller, never
in a cloned project or candidate. Do not paste credentials into source files.

Use a new private output directory. The runner loads the normal saved profile
but does not edit it. It checks Azure deployment identities before calling
models. On Windows, `--azure-python` accepts the Azure CLI Python executable
to avoid quoting problems in the `az.cmd` wrapper.

```powershell
# PAID, fresh coding generation; defaults to historical v1 unless --protocol is supplied.
tsx runner/hard-study.ts --delta-root=C:/path/to/fixed-delta --profile=C:/path/to/Delta-profile --python=C:/path/to/python.exe --azure-python=C:/path/to/AzureCLI/python.exe --output=C:/path/to/new-private-batch

# Optional PAID connection mode, also use a new output directory:
tsx runner/hard-study.ts --mode=connection --delta-root=C:/path/to/fixed-delta --profile=C:/path/to/Delta-profile --python=C:/path/to/python.exe --azure-python=C:/path/to/AzureCLI/python.exe --output=C:/path/to/new-connection-batch

# For an explicitly reviewed, newly registered protocol with cumulative guard:
tsx runner/hard-study.ts --protocol=C:/path/to/new-registered-protocol.json --delta-root=C:/path/to/fixed-delta --profile=C:/path/to/Delta-profile --python=C:/path/to/python.exe --output=C:/path/to/new-private-batch
```

When a path contains spaces, quote the **whole** `--name=value` argument.
Protocol input limits apply to a byte-based estimate, not guaranteed billed
tokens. Output/attempt/reference/wall caps may stop before a useful refactor.

The optional paper runner uses the already registered
`protocols/hard-paper-models-v1.json`:

```powershell
# PAID questions; no answer in model input. New output directory only.
tsx runner/hard-paper.ts --delta-root=C:/path/to/fixed-delta --profile=C:/path/to/Delta-profile --output=C:/path/to/new-paper-batch
```

For a different paper/model/task selection, register a new protocol first;
do not reuse v1's name or pick inputs after seeing model failures.

## Cost and evidence boundaries

New stages: $4.87833085 reported reference usage plus $0.1638163 uncertain
reserves, combined $5.04214715. This includes connection and paper calls.
Three unreported Luna responses retain uncertain reservations; an HTTP 429
reports no inference cost. These are not Azure invoice/credit figures.

The public evidence selection excludes whole raw request/response/event/
checkpoint files and reasoning, profiles, credentials, database/site configs,
source clones and Qarinah memory. Exact initial/candidate bytes, ordinary
files, fixed expected/observed checks, usage metadata and upstream/context
hashes remain. No generated candidate was integrated into the running ERP.

For a next balanced study, schedule complete model/task blocks and set enough
requests for all matched comparisons. Register long-context/caching changes
separately. The present result does not establish harness/model rankings,
variant superiority, full-paper reproduction or production safety.
