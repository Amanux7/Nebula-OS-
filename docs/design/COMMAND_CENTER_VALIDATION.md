# Command center validation

Validated on 1 October 2026 against the loopback Stage 11 host with fresh SQLite
databases. The populated case uses the canonical Aurora Desk seed; the empty case
uses a real empty workspace. Production rendering is not replaced with mock data.

## Automated checks

- Initial full Python suite: 578 passed. Three Chromium startup failures were
  caused by Windows process restrictions in the execution sandbox.
- The existing console browser regression passed with the approved browser runner.
- The populated spatial browser case passed independently after the driver waited
  for native keyboard scrolling to settle before asserting stack reset.
- Final spatial acceptance suite: all 4 cases passed in 64.09 seconds, covering
  the populated/empty browser cases and both spatial HTTP cases.
- Operator HTTP and additive projection checks: 8 passed.
- Audio contracts: 13 passed. Spatial data/session contracts: 15 passed.
- Ruff lint, Ruff format, strict mypy for changed Python files, and JavaScript module
  syntax checks passed.

Browser coverage includes authentication, canonical entity IDs, delayed loading,
empty/error states, stored XSS escaping, agent selection, goal/plan/task/run/receipt
lineage, native keyboard scrolling, palette focus restoration, quarantine,
reduced motion, mobile overflow, muted audio preferences, session logout privacy,
and the projected core with WebGL disabled. Audio contracts cover speech state
changes, cancellation, arbitration, denied capture, and no automatic microphone.

## Visual review and limits

Reviewed the command core, organization and execution views. Local screenshots are
stored in `.local/command-center-snapshots`; they are development artifacts, not
account telemetry. Test mode freezes motion for reproducible captures.

The core projects 3D geometry through Canvas2D, so it does not require WebGL. This
surface remains read-only for runtime operations. Speech can navigate inspection
contexts and read visible metadata; there is no live model conversation endpoint.
Aurora has no recorded evidence packs, so the brain view reports their absence
instead of simulating a retrieval. Microphone recognition requires explicit action
and browser/vendor support.
