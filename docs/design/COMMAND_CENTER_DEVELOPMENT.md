# Run and verify the command center

The command center is part of the Python package, not a separate frontend service.
It adds no npm dependencies or build requirement. The existing Stage 11 host serves
`/command`; the established metadata console remains at `/` and links to it.

## Start with a fresh canonical Aurora Desk seed

Use fresh paths. Do not overwrite or reseed an existing database. Bootstrap owns
schema migrations. The seed executes only the established offline deterministic
Aurora fixture; the inspection host starts no worker or tool executor.

```powershell
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli bootstrap --canonical .local/command-demo.sqlite --identity .local/command-operators.sqlite
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli seed-aurora --canonical .local/command-demo.sqlite --identity .local/command-operators.sqlite
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli provision --canonical .local/command-demo.sqlite --identity .local/command-operators.sqlite --workspace aurora-workspace-0001 --operator command-auditor --role auditor
.\.venv\Scripts\python.exe -m agent_company_os.operator_cli serve --canonical .local/command-demo.sqlite --identity .local/command-operators.sqlite --port 8791
```

Enter the provisioned credential at `http://127.0.0.1:8791/command`. Credentials
and sessions retain the host's existing lifetime and protection. Demo deadlines
are absolute; an older seed can correctly show expired work or recovery cases.

## Operator-directed showcase

1. Command: inspect presence, goal, and canonical attention counts.
2. Company: focus Research; use bounded zoom/tilt and reset.
3. Agents: inspect Research identity and exact configuration; choose Talk.
4. Talk: type “What are you working on?”; read the recorded summary. Enable sound
   and choose Read response if desired; Stop speaking interrupts immediately.
5. Goals: select the cross-department brief. Scroll or use Go deeper to traverse
   actual Goal/Plan/Task/Run lineage. Select Deliver synthetic brief to inspect its
   real invocation and receipt. Missing layers are explicitly omitted.
6. Brain: inspect source/version/chunk metadata and the separate memory capsule.
   Aurora currently has no recorded retrieval packs; no retrieval is simulated.
7. Tools: follow sender, recipient, correlation and task IDs for messages/handoffs.
8. Approvals: inspect policy, digest, expiry and decisions; actions are disabled.
9. Recovery: distinguish unknown outcome from expired/repair classifications.
10. Audit: select a goal and inspect the ordered committed event timeline.

Ctrl/Cmd+K opens the command palette. Escape closes dialogs and restores focus.
Reduced motion is automatic or selectable. `/command?test=1` freezes camera/core
motion for reproducible screenshots; sound remains off until operator action.

## Verification

```powershell
node tests/fixtures/audio_contract.mjs
node tests/fixtures/spatial_data_contract.mjs
.\.venv\Scripts\python.exe -m pytest tests/test_spatial_projections.py tests/test_spatial_console.py -q
```

Browser acceptance uses local Chromium through a private pipe, real authenticated
HTTP, and a fresh canonical seed or real empty workspace. It does not substitute
production data. Snapshots freeze motion, test mobile compositions, and disable
WebGL. Host security/redaction regressions and the wider offline suite remain
required. On Windows, Chromium may require the approved unsandboxed test runner
because its GPU broker cannot start inside the execution sandbox; use a fresh
workspace-scoped `--basetemp` and `-p no:cacheprovider` rather than deleting data.

`window.commandDiagnostics()` provides local development load/frame/API/speech
measurements. No external telemetry service or account data transmission is added.

## Contract limitations

There is no live model chat, authorized approval mutation, tool execution command,
or runtime intervention API on this surface. Text/voice route read contexts and
read visible metadata only. Browser recognition depends on browser/vendor support;
the UI discloses it before microphone activation. Audio identity does not grant
runtime authority. Public hosting is inappropriate for the loopback-only host.
