# Local operator walkthrough

Stage 11 is a local inspection/control surface over real canonical records. It
does not call a live model, execute production tools, or approve agent actions.
Use Python 3.13 and the repository `.venv`. Commands below are PowerShell; select
fresh database paths if these already contain a demo. Never delete user data to reseed.

## Seed, provision, serve

```powershell
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli bootstrap --canonical .local/aurora.sqlite --identity .local/operators.sqlite
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli seed-aurora --canonical .local/aurora.sqlite --identity .local/operators.sqlite
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli provision --canonical .local/aurora.sqlite --identity .local/operators.sqlite --workspace aurora-workspace-0001 --operator local-auditor --role auditor
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli serve --canonical .local/aurora.sqlite --identity .local/operators.sqlite --port 8787
```

Provisioning prints the generated credential once; store it privately, never in
Git or a URL. Enter it at `http://127.0.0.1:8787/`. Sessions last 15 minutes; sign in
again when expired. Login is limited to five attempts per minute per host process,
including successful attempts. No network exposure, proxy or tunnel is supported.
Stop the host with Ctrl+C. Bootstrap is the explicit migration command, not seeding.

## Inspect the actual fixture

1. Open Organization and Organization versions, then Departments and Agents.
   Research, Product and Marketing are canonical graph records; inspect exact
   Agent versions rather than assuming mutable current configuration.
2. Open Goals → **Aurora Desk cross-department competitor brief** → **Inspect
   related lineage**. The nested lists contain the accepted plan, materialization,
   Tasks, Delegations, attempts and results.
3. Follow a Task and inspect its related AgentRuns. A run shows exact configuration,
   budgets/deadline, observation/tool counts and pack IDs, not hidden reasoning.
4. Open Messages, Message threads and Handoffs. The fixture has a Research→Product
   clarification and a completed handoff. Message bodies stay protected.
5. Open Action intents. One fixture delivery was approved/consumed; another waits
   for human approval. Inspect related lineage to follow request/decision, claim,
   invocation and receipt. No screen can approve, retry or edit this state.
6. Open a Goal → **View timeline**. IDs, safe reasons and versions correlate the
   committed history. Full prompts, source content, messages and Tool payloads are omitted.
7. Open Recovery cases. Read the reason/explanation and follow its related record.
   These are classifications, not commands. Time-dependent cases may become expired
   after the absolute deadline; refreshing never grants more time.
8. Empty categories explicitly say there are no records. Counts cap at 100 and lists
   page at 25 by default. Static offset pages are not a snapshot across mutations.

## Restore drill and release

Quiesce all workers for the source workspace. The inspection host runs no workers.
Provision a separate admin locally (change `--operator` to `local-admin`, `--role`
to `admin`). Protect both configured roots with OS filesystem access controls.

```powershell
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli backup --canonical .local/aurora.sqlite --identity .local/operators.sqlite --workspace aurora-workspace-0001 --name drill-before --backups .local/backups --restores .local/restores
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli restore --canonical .local/aurora.sqlite --identity .local/operators.sqlite --workspace aurora-workspace-0001 --name drill-before --destination drill-restored --backups .local/backups --restores .local/restores
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli serve --canonical .local/restores/drill-restored/canonical.sqlite --identity .local/operators.sqlite --port 8788
```

Backup/restore commands prompt privately for the admin credential, not a CLI flag.
The destination must not exist. Identity and the independent fixture-remote DB are
**not** restored. Open port 8788 and sign in as admin. The quarantine banner and
Restore incident page expose backup ID/digest, schema, generation, restore time,
held intent IDs and release attempts. Inspect Recovery cases first.

**Validate and release quarantine** performs current integrity/canonical checks,
recovery classification and a single audited mode transition. It does not run
anything. Every intent present in the snapshot remains permanently held in this
stage, even if its restored approval says approved. There is no hold-removal API.
Existing claims may be reconciled by trusted host recovery code against the
independent remote fixture; neither lookup nor reconciliation is a UI command.
If the snapshot predates a claim, it may lack the remote lookup key: do not guess
or create replacement work merely to bypass the hold. Investigate the original timeline.

Release can coexist with individually blocked unknown cases. Missing provenance,
failed validation/classification or an unfenced consequential intent denies release.
A manually restricted workspace without restore provenance cannot use this release.
There is no maintenance-clear command in Stage 11.

## Diagnostics and safe boundaries

`/health/live` means the process responds. `/health/ready` opens both migrated
databases and composes canonical services; quarantine/unknown outcomes do not alone
make inspection unready. Admin Host diagnostics provides safe startup and cumulative
request counters. No credential or session appears there.

The host refuses decoding above 10,000 canonical/audit records, 32 MiB total payload
or 1 MiB per record (HTTP 503 `inspection_capacity_exceeded`). Relational auxiliary
tables are also row-bounded. Four request workers and SQLite busy/socket timeouts
bound local contention; these are not production latency or DoS guarantees.

Backups are plaintext, not encrypted or signed. Checksums detect accidental change
only under trusted-file assumptions. POSIX mode hints are restrictive; Windows
requires checking/configuring the parent ACL. Link/junction paths are rejected but
hostile administrators or a concurrent filesystem attacker are not defended against.
Ordinary failed operations remove their exact partial files; abrupt process death
may leave a private `.incomplete` staging directory for trusted inspection/cleanup.

See [Stage 11 evidence](../STAGE_11_REPORT.md) for automated stale-revocation,
remote-effect-after-backup and release-race drills. Stage 12 is not implemented.
