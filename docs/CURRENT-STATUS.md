# Current and historical status — October 1, 2026

Author: Ajnas N B.

The root README and versioned correction reports are the current status.
Older reports describe the batch actually run then; their “not yet run,”
“local only,” “no product fix,” or narrower totals must not be treated as the
latest project status.

| Phase | What happened | Where to read it |
|---|---|---|
| Initial version-2 attempt | Context integration stalled; entire attempted batch retained and excluded from fresh pilot | `docs/protocol-changes.md` |
| Defended version-3 pilot | 48 synthetic tasks and five FastAPI tasks; exact rule/warnings provided | `reports/results.md`, historical `protocol.json` |
| Cross-harness extension | Restricted Codex/OpenHands/Claude smoke; one Claude budget stop | `reports/harness-comparison.md` |
| Delta product fixes | Actual source corrections, six live smoke tasks and product verification | `reports/delta-product-fixes.md` |
| ERP extension | Complete local app installed; only three Frappe handlers refactored and combined | `reports/erpnext-detailed-report.md` |
| Authorized publication | Ajnas-authored research and private Delta commits on main | `reports/publication.md`, later publication records |
| Measurement correction | Four scorer findings fixed; 83 saved files replayed/reexecuted without new model calls | `reports/measurement-correction-v4.md` |
| New ordinary prompts | 23/24 completed tasks; one frozen attempt-cap stop; no observed access violations | `reports/ordinary-v1-results.md` |
| Original-paper follow-up | Three archived failures confirmed offline; fresh eleven-query Sol sample clean | `reports/mucoco-reproduction-v1.md` |

## Current counts

Historical core tasks: 82 completed refactors, 83 saved final files and
8,396 independent checks including the unfinished Claude file.
Completed refactors alone have 8,253 checks.

New ordinary tasks: 23 completed refactors, 24 saved files and 2,608 checks
including the incomplete helper file. Completed refactors alone have 2,465
checks. These new tasks are not retroactively substituted for the defended
pilot, and three known-positive paper replays are not added to the ordinary
sample.

The combined inventory is 105 completed core refactors and 107 saved files.
Counts do not include oracle self-tests, setup attempts, author prediction
queries or separate combined-app/HTTP checks. A saved file or repeated test
case is not an independent research finding.

## Current interpretation

The MVP executes, has improved measurement controls and preserves evidence.
It found no access regression in its retained fresh samples. It has not
established that controlled variants outperform equal-budget repeats or
established generalized model/harness safety.

The ordinary comparison is nominally matched at three benign conditions versus
three independently initialized unchanged runs per template. One benign run
hit the batch cap, so completed counts are not balanced. We did not raise caps
or pay for replacement generations.

The ERP ordinary preparation profile is implemented and unit-tested, but no
new ordinary-profile ERP agent batch was run in this correction. The six ERP
trajectories remain historical defended trials.

## Costs and external state

This correction added approximately $0.321614 of reference-priced provider
usage. All recorded experiments estimate $2.499110 with the documented
cache-write assumption. These are not Azure invoice totals or credit balances.
Historical subscription snapshots are dated in `reports/all-experiment-costs.json`
and were not refreshed or altered during the correction.

No unrelated Delta product changes, credential profiles, Azure deployments,
cloud resources, database volumes or historical source outputs were reset.
