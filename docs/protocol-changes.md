# Protocol changes before the pilot

October 1, 2026: the initial single-run smoke test completed a real refactor and
passed all 143 protected checks. Its six calls used 28,162 input and 501 output
tokens. This is an engineering preflight, not a trajectory reused in the pilot.

Before any pilot outcomes were inspected, version 2:

* Increased the request limit from 200 to 400 so 48 bounded, up-to-eight-step
  trajectories are not intrinsically impossible.
* Replaced the unavailable billing rates with an explicitly labelled public
  OpenAI Standard estimate ($2/$0.1/$10 per million input/cached/output tokens).
  Azure retail/contract rates were not established. Conservative planning uses
  twice the public uncached/output rates and treats all input as uncached.
  The $10 planning guard is not a guarantee of the Azure invoice.
* Compacted public-test tool feedback to its outcome vector and failed cases.
  Complete public assessment files remain recorded. This avoids resending large
  success-case payloads on every turn.
* Corrected `note_read` to require a successful read of a file actually present,
  rather than counting an unsuccessful absent-file request.
* Azure `response.model` may contain the deployment alias. Preserve it verbatim
  and combine it with freshly verified control-plane mapping; do not invent a
  stable model snapshot field.

The original smoke records and setup failures are retained. Version 2 was used
for the first attempted batch, which was subsequently aborted as described
below. The final pilot uses version 3 throughout. Model choice, trusted security
instructions, note texts and assessment challenge definitions did not change
in response to a security failure.

## Version 3: aborted runner-validation batch, not selective outcome removal

The first attempted version-2 batch was stopped as runner validation after its
first three completed records: one successful refactor and two unchanged programs
that hit the step limit. A fourth started trajectory was interrupted. Every
record, raw provider response and usage observation is retained in
`artifacts/agent_runs/pilot-delta-sol61-v2-20261001/`. The **whole** batch is
excluded from the fresh pilot, including the successful trajectory.

The trace established the engineering cause: reading the verbose public-case
file consumed the context allowance; Delta's rollover dropped the relevant
recent outcomes. The agent then reread the same files, including an absent note.
This was not a measured security failure and is not a reason to relabel an
unchanged program as a successful refactor.

Version 3 shares repeated invoice records by reference in a compact public JSON
bundle. A unit test expands it and verifies exact equality to every original
public case. No public or protected test case was removed. A request for an
absent `PROJECT_NOTE.md` now gets an explicit `exists:false` result. The step
limit is ten, with a 600-request ceiling; token and $10 conservative planning
caps remain. All fresh pilot and independent-control runs use these same
version-3 policies. The real Delta source/profile is not modified.
