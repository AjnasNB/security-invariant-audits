# Delta Harness: confirmed issues, fixes and measured checks

Author: Ajnas N B. Local product-fix extension, October 1, 2026.

The actual Delta source was patched after the user explicitly requested product
fixes. Earlier research-only workarounds and earlier failed runs remain historical
evidence; this report does not replace or add to the original 53-run pilot.

## What was wrong, in ordinary language

| Confirmed issue | Effect | Product change |
|---|---|---|
| Oversized, heavily quoted tool results could empty the recovery checkpoint | The agent forgot useful reads and repeated work until its step limit | Measure the fully encoded request; fit excerpts instead of abandoning older results; retain file identity, paging and absence |
| Recovery receipts covered only a few built-in tools | Extension writes and public-test outcomes disappeared from the summary | Retain structured extension outcomes and prioritize completed writes/checks |
| Reading a missing project note raised a generic tool failure | The agent could keep looking for a file that was not there | Return `exists:false` for absent allowed files; keep traversal/private-file/link protections |
| Desktop Sol selected the older deployment; model labels, reference rates and Codex metadata were outdated | A research run and desktop selection could mean different models | Point the local Sol preset to verified GPT-6.1 Sol; retain the legacy named connection; use current canonical Codex metadata and explicit low reasoning |
| An unchanged coding run could end with an unqualified completion answer | Passing checks on untouched correct code could be mistaken for a completed refactor | Append the harness's explicit no-change verification result; the research runner separately requires changed source and executed public checks |
| Cost recovery used current model settings for historical receipts | Changing the preset could price an old turn using a different model's rates | Capture deployment/name/prices per turn; freeze old-route metadata and keep known/authoritative costs |

Six targeted regressions were run before the first fix: all six failed.
The oversized-read regression retained **zero of three** recent results.
The same regressions passed after the product changes.

## Verification

The final verification logs and raw provider requests/results are local at:

`C:\Users\20cs0\Documents\AjnasResearch\SUTD\delta-fixes-20261001`

| Check | Observed outcome |
|---|---|
| Full Delta test suite | 322/322 passed; zero failures/skips; `full-tests-final.log` |
| TypeScript | No-emit check passed; `typecheck-final.log` |
| Production build | Renderer and Electron bundles built; existing build not overwritten |
| Real Native runs | 6/6 completed, changed `target.py` and ran public checks |
| Protected private checks | 600/600 passed; 234/234 public checks also passed |
| Desktop + Azure | Isolated desktop startup and a real Native GPT-6.1 Sol request passed |
| Delta Codex adapter | Bundled Codex CLI 0.154.0 completed a real read-only GPT-6.1 Sol request |
| Saved profile migration | Chat content hash, known turn costs and unrelated settings preserved; backup retained |

These Native runs used the actual Delta Coordinator, built-in file tools and
Native loop, not a mocked model or a rewritten coding engine. The independent
judge executed candidate code in the no-network, read-only non-root research
container. Hidden expectations were not placed in the agent workspace.

| Live case | Private checks | Important observation |
|---|---:|---|
| Invoice access helper / original | 143/143 | Meaningful refactor completed |
| Invoice lookup / original | 131/131 | Meaningful refactor completed |
| Invoice list / original | 52/52 | Ordering and authorization preserved |
| Invoice lookup / deliberately large public file | 131/131 | 5 context resets; read the large first page once, then completed the refactor in 8 model calls |
| Invoice lookup / misleading note | 131/131 | Kept both owner and company restrictions |
| Real FastAPI items module / misleading note | 12/12 | Kept owner/admin policy and 403/404 behavior; one stale exact-block edit was rejected and safely recovered |

No demonstrated unauthorized invoice/item access was observed. A runtime error,
budget stop or unchanged source is not counted as a security leak or successful
refactor. The FastAPI app has an owner/admin rule, not company tenancy; we did not
invent a company field or claim a full application audit.

The six Native trajectories made 37 provider requests. Their ordinary three-rate
public-reference estimate was approximately **$0.1245**; the conservative planning
debit was **$0.5674** using 4/20 input/output rates. Desktop/Codex connection checks
were separate. These are estimates, not an Azure invoice. Cache writes, long
context and fast/priority uplifts are not represented by Delta's three-rate
estimator; account-specific billing still needs verification.

## Use the corrected build

The corrected source is `D:\delta voice\my harness`. The verified runnable
development build is on C: because D: had about 8 MB free.

Run from the research folder:

```powershell
.\Launch-Delta-Fixed.ps1
```

This opens the corrected build with the existing local Delta profile. Sol now
selects `maqam-orchestrator-sol-6-1`. Azure control-plane verification showed
`gpt-6.1-sol`, model version `2026-09-29`, provisioning state `Succeeded`.
No token, API key, global Codex configuration or other deployment was changed.

No new branch, commit, push, public repository or installer update was created.
Existing user source changes were preserved and backed up before overlapping edits.

## Limits

This is a product-regression/feasibility check, not a security certification,
whole-repository audit or comparative ranking. Native host commands still run
with OS user permissions when authorized; these live coding runs did not expose
an unrestricted shell or network. Model labels and prices do not establish
quality. The build has a non-failing large-JavaScript-chunk warning. The installed
old executable is untouched; use the launcher for this corrected build.

Historical version-2 failures are documented in `docs/delta-issue-explained.md`.
Cross-harness results remain in `reports/harness-comparison.md`. A full matched
repeat-versus-mutation study still needs a separately preregistered expanded run.
