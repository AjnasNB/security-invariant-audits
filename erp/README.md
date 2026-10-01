# ERPNext selected-handler integration study

Current correction: scorer 4.0 fixes pagination leak classification, validates
return shapes and marks uncertain results unknown. Named-container timeout
cleanup was tested against the actual runtime. Historical six agent trials are
still defended-prompt trials. `--prompt-profile=ordinary-v1` is an explicit new
preparation/runner profile, but no paid ERP run of that profile was performed
in the correction. See the root README and `docs/CURRENT-STATUS.md`.

The complete local application is ERPNext 16.37.0 / Frappe 16.36.0 with MariaDB,
Redis, workers, scheduler, websocket server and the web UI. AI refactors affect
three actual Frappe request-handling functions used by this ERP; we do not claim
to have rewritten or audited every application feature.

All companies, users, customers, items and invoices are fictional. Country is
India and currency INR. The 18 percent arithmetic fixture is not a real GST
calculation, filing, e-invoice, or compliance integration.

## Reproduce

Python 3.12+, Docker and Docker Compose are required. Windows uses the configured
Ubuntu WSL Docker daemon. `erp/manage.py` currently locates Compose at
`/usr/libexec/docker/cli-plugins/docker-compose`; change that path for a different
installation.

```powershell
python -B -m erp.manage init
python -B -m erp.manage pull
python -B -m erp.manage up
python -B -m erp.manage seed
python -B -m erp.manage baseline
```

Private random local passwords are generated in `erp/private/experiment.env`.
They must never be committed. The UI is bound to `127.0.0.1:18080`; use the
Administrator password from that private file. No public deployment is made.
The internal app/database network is isolated; only the frontend has a separate
edge network for the loopback web port.

Acquire the pinned reference source (ignored locally) and validate the judge:

```powershell
git clone --depth 1 --branch v16.36.0 https://github.com/frappe/frappe.git erp/vendor/frappe
python -B -m erp.evaluate init
python -B -m erp.evaluate validate
python -B -m erp.validate
python -B -m erp.http_smoke
```

`erp.evaluate init` now verifies source before changing the protected reference.
It intentionally fails if the current backend already mounts a refactored
`client.py`; do not overwrite the reference or reset the database to bypass
that check. Return the backend's source mount to the pinned baseline first.

`erp/run_delta.ts` imports the actual Delta Native loop, not a mock. It reads
the user's separately configured local Delta profile; set paths via command
options as appropriate. GPT-6.1 Sol must be explicitly selected. Billing and
credentials are never mounted in the agent workspace. Fixed broker tools allow
only named context reads, `client.py` edits and public checks.

```powershell
tsx erp/run_delta.ts --delta-root=C:/path/to/delta-harness --profile=C:/path/to/Delta-profile --python=C:/path/to/python.exe
python -B -m erp.integrate
```

Generated candidates run in an additional read-only non-root container on the
isolated ERP network. The test adapter receives case inputs but not expected
results. It can reach only this synthetic site's database/Redis. A database
savepoint rolls back each tested update/delete/cancel. This is meaningful
integration isolation, not proof against malicious database introspection or
container/kernel attacks.

The accepted combined module can be mounted read-only:

```powershell
docker compose --env-file erp/private/experiment.env -f erp/compose.yml -f erp/compose.candidate.yml up -d backend
python -B -m erp.http_smoke
```

On Windows use the WSL Compose executable with translated absolute paths, as
`erp/manage.py` does. Remove the candidate override and recreate the backend to
return to the pinned baseline. `python -B -m erp.manage stop` stops only this
experiment; it does not delete volumes or data.

## Publication and licensing

`erp/private`, `erp/protected`, `erp/vendor`, `erp/runs` and `erp/runtime` are
excluded from Git. Scrubbed accepted candidates and result summaries are
published separately under `evidence/erp`. Derived Frappe source remains MIT;
ERPNext stays GPL-3.0 and is fetched using its pinned upstream image/source.
This repository does not relicense those projects.
