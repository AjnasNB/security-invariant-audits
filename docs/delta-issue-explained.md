# Was there a Delta problem?

Update, October 1, 2026: after the user explicitly requested product fixes,
Delta's original source and saved Sol preset were corrected and checked.
See `reports/delta-product-fixes.md`: six real Native refactors completed,
600 private checks passed, and desktop/Native/Codex connections were verified.
The sections below describe the **earlier investigation phase**, when only
research-integration workarounds had been applied.

Yes, in the tested research integration. It was an engineering/continuation
failure, not evidence that Delta exposed an invoice.

## In ordinary language

Think of the assistant as a worker with a small notepad. We handed it a long
test file containing the same invoice list over and over. Its notepad filled
up. Delta summarized the recent work to make space, but the useful "already
read this file" details did not survive well. It returned to the same files and
tried to read a project note that did not exist. It used up its eight allowed
steps without making the requested change.

## Recorded evidence

`artifacts/agent_runs/pilot-delta-sol61-v2-20261001/` contains:

* one successful, edited list-filter run;
* two invoice-lookup trajectories that ended at the step limit without edits;
* a fourth trajectory started and was interrupted when the whole batch stopped.

The failed lookups still passed invoice checks because the original correct
code remained unchanged. That did **not** mean the refactoring task succeeded.
No invoice access violation was observed in that batch.

The trace showed the large `public_cases.json` read followed by context
rollovers, repeated file reads and requests for absent `PROJECT_NOTE.md`.
The provider did respond; this was not a missing deployment or server outage.

## What was corrected

Only the research package was changed:

1. Share repeated invoice records by reference in a compact JSON test bundle.
   A unit test expands it and verifies every original public case is still there.
2. Return an explicit `exists:false` result for an absent project note.
3. Use ten bounded steps and compact public-test feedback consistently.

We did not patch Delta's original context-rollover implementation or change
the user's desktop model profile. These are integration workarounds, not proof
the general product issue is fixed.

The entire version-2 batch, including its successful run, was excluded from
the fresh version-3 pilot. All records and observed costs remain available.
The new pilot completed 48 meaningful refactors and 5,216 protected checks.
Five real FastAPI module runs added 60 passing checks. Zero demonstrated leaks
is a result for those cases, not a promise that Delta is safe for every project.

## Configuration issue too

Delta's saved desktop `sol` preset pointed to the older
`maqam-orchestrator-sol`, not requested `maqam-orchestrator-sol-6-1`.
The research runner uses a separate, verified configuration; the app profile
was not silently changed.

The first connection check also expected the response's `model` field to
contain the underlying model name. Azure returned the deployment alias.
The research checker now records that alias and the independently verified
Azure mapping (`gpt-6.1-sol`, version `2026-09-29`) instead of treating a
correct alias response as a model mismatch.

## What this suggests for a future Delta fix

Test context resets with large structured tool output, and confirm important
completed-action receipts survive. Test absent files as ordinary observations,
not repeated tool errors. Add a regression test for meaningful task completion
versus an unchanged program that passes safety tests. These product changes
need their own implementation and review; this investigation did not claim
to have made them.
