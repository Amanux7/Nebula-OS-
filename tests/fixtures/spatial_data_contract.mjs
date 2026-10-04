// Read-provider contracts with deterministic fetch/timer mocks. No host or browser required.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../src/agent_company_os/operator_ui/spatial-data.js", import.meta.url), "utf8");
const { InspectionPort, ActivityFeedPort, ApiError, fields, title, recordState, reviewState } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const tests = [];
const test = (name, run) => tests.push({ name, run });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const ok = body => ({ ok: true, status: 200, json: async () => body });
const abortError = () => Object.assign(new Error("Canceled"), { name: "AbortError" });
const saved = { fetch: globalThis.fetch, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval, document: globalThis.document };

test("feed stop discards an in-flight successful status response", async () => {
  const pending = deferred(); const callbacks = new Map(); let sequence = 0, requests = 0;
  globalThis.document = { hidden: false };
  globalThis.setInterval = callback => { callbacks.set(++sequence, callback); return sequence; };
  globalThis.clearInterval = id => callbacks.delete(id);
  const updates = [], errors = [];
  const feed = new ActivityFeedPort({ request: async path => { assert.equal(path, "/api/v1/status"); requests++; return pending.promise; } });
  feed.start(value => updates.push(value), error => errors.push(error));
  const running = callbacks.get(feed.timer)(); assert.equal(requests, 1);
  feed.stop(); pending.resolve({ mode: "normal", recovery_count: 3 }); await running;
  assert.deepEqual(updates, []); assert.deepEqual(errors, []); assert.equal(callbacks.size, 0); assert.equal(feed.busy, false);
});

test("feed stop discards an in-flight failure and restarting keeps callbacks isolated", async () => {
  const callbacks = new Map(); let sequence = 0; const first = deferred(), second = deferred(); let requests = 0;
  globalThis.document = { hidden: false };
  globalThis.setInterval = callback => { callbacks.set(++sequence, callback); return sequence; };
  globalThis.clearInterval = id => callbacks.delete(id);
  const oldErrors = [], newUpdates = [];
  const feed = new ActivityFeedPort({ request: () => (++requests === 1 ? first.promise : second.promise) });
  feed.start(() => assert.fail("Old update was published"), error => oldErrors.push(error));
  const oldTick = callbacks.get(feed.timer)();
  feed.start(value => newUpdates.push(value)); first.reject(new Error("Signed out")); await oldTick;
  assert.deepEqual(oldErrors, []);
  const newTick = callbacks.get(feed.timer)(); second.resolve({ mode: "restore_quarantine" }); await newTick;
  assert.deepEqual(newUpdates, [{ mode: "restore_quarantine" }]); feed.stop();
});

test("polling pauses while document hidden and prevents concurrent requests", async () => {
  const callbacks = new Map(); let sequence = 0, requests = 0; const pending = deferred();
  globalThis.document = { hidden: true };
  globalThis.setInterval = callback => { callbacks.set(++sequence, callback); return sequence; };
  globalThis.clearInterval = id => callbacks.delete(id);
  const feed = new ActivityFeedPort({ request: () => { requests++; return pending.promise; } });
  feed.start(() => {}); const tick = callbacks.get(feed.timer);
  await tick(); assert.equal(requests, 0); globalThis.document.hidden = false;
  const running = tick(); await tick(); assert.equal(requests, 1);
  pending.resolve({}); await running; feed.stop();
});

test("clear aborts an outstanding fetch and clears cached workspace records", async () => {
  let signal;
  globalThis.fetch = (path, options) => new Promise((resolve, reject) => {
    signal = options.signal; signal.addEventListener("abort", () => reject(abortError()), { once: true });
  });
  const port = new InspectionPort(); port.cache.set("agents", { items: [{ id: "old-workspace" }] });
  port.latencies.push({ path: "/api/v1/audit/goals/previous-account-goal", ms: 20 });
  const request = port.page("agents"); assert.equal(signal.aborted, false); assert.equal(port.controllers.size, 1);
  port.clear(); assert.equal(signal.aborted, true); assert.equal(port.cache.size, 0); assert.deepEqual(port.latencies, []);
  await assert.rejects(request, error => error.name === "AbortError"); assert.equal(port.controllers.size, 0);
});

test("clear also cancels the body-read phase and rejects stale collection cache writes", async () => {
  const body = deferred(); let signal;
  globalThis.fetch = async (path, options) => { signal = options.signal; return { ok: true, status: 200, json: () => body.promise }; };
  const port = new InspectionPort(); const collection = port.collection("agents");
  // Yield until fetch has resolved and request is awaiting its JSON body.
  await Promise.resolve(); await Promise.resolve();
  port.clear(); assert.equal(signal.aborted, true, "Abort controller must remain owned until the response body has settled");
  body.resolve({ items: [{ id: "previous-session-agent" }], next_cursor: null });
  await assert.rejects(collection, error => error.name === "AbortError"); assert.equal(port.cache.size, 0);
});

test("cleared sessions suppress late malformed JSON and collection-resolution races", async () => {
  const body = deferred();
  globalThis.fetch = async () => ({ ok: true, status: 200, json: () => body.promise });
  const port = new InspectionPort(); const request = port.page("goals");
  await Promise.resolve(); await Promise.resolve(); port.clear(); body.reject(new Error("Invalid old-session JSON"));
  await assert.rejects(request, error => error.name === "AbortError");
  assert.equal(port.latencies.length, 0, "Discarded sessions do not populate current diagnostics");
  port.page = async () => { port.clear(); return { items: [{ id: "previous-workspace-goal" }] }; };
  await assert.rejects(port.collection("goals"), error => error.name === "AbortError");
  assert.equal(port.cache.size, 0);
});

test("caller options cannot replace the cancellation signal owned by InspectionPort", async () => {
  const caller = new AbortController(); let signal;
  globalThis.fetch = (path, options) => new Promise((resolve, reject) => {
    signal = options.signal; signal.addEventListener("abort", () => reject(abortError()), { once: true });
  });
  const port = new InspectionPort(); const request = port.request("/api/v1/status", { signal: caller.signal });
  assert.notEqual(signal, caller.signal); port.clear();
  await assert.rejects(request, error => error.name === "AbortError"); assert.equal(caller.signal.aborted, false);
});

test("collection/audit requests stay bounded and IDs/cursors cannot alter the request", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => { calls.push({ path, options }); return ok({ items: [], next_cursor: null }); };
  const port = new InspectionPort(); const cursor = "cursor&limit=1000?/# space";
  await port.page("agents/../goals", cursor);
  let url = new URL(calls.at(-1).path, "http://localhost");
  assert.equal(url.pathname, "/api/v1/inspect/agents%2F..%2Fgoals"); assert.equal(url.searchParams.get("limit"), "100"); assert.equal(url.searchParams.get("cursor"), cursor);
  assert.equal(calls.at(-1).options.credentials, "same-origin"); assert.ok(calls.at(-1).options.signal instanceof AbortSignal);
  const id = "task/../other?role=admin&limit=1000#";
  await port.record("tasks", id); url = new URL(calls.at(-1).path, "http://localhost");
  assert.equal(url.searchParams.get("id"), id); assert.equal(url.searchParams.has("role"), false); assert.equal(url.searchParams.has("limit"), false);
  await port.lineage("runs", id); assert.equal(calls.at(-1).path, "/api/v1/lineage/runs/" + encodeURIComponent(id));
  await port.audit(id, cursor); url = new URL(calls.at(-1).path, "http://localhost");
  assert.equal(url.pathname, "/api/v1/audit/goals/" + encodeURIComponent(id)); assert.equal(url.searchParams.get("limit"), "100"); assert.equal(url.searchParams.get("cursor"), cursor);
});

test("network/authentication/invalid-response errors preserve useful classification", async () => {
  const port = new InspectionPort();
  globalThis.fetch = async () => { throw new Error("Offline"); };
  await assert.rejects(port.page("goals"), error => error instanceof ApiError && error.status === 0);
  globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => ({ error: { code: "authentication_required" } }) });
  await assert.rejects(port.page("goals"), error => error.code === "authentication_required" && error.status === 401);
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new Error("Invalid JSON"); } });
  await assert.rejects(port.page("goals"), error => error.code === "Invalid API response" && error.status === 200);
  assert.equal(port.controllers.size, 0);
});

test("titles/states preserve canonical labels and unknown outcomes as literal text", () => {
  assert.equal(title(null), "Record"); assert.equal(recordState(undefined), "recorded"); assert.deepEqual(fields({}), {});
  const record = { id: "agent-1", fields: [["definition.name", "Research Agent"], ["status", "waiting_for_approval"]] };
  assert.equal(title(record), "Research Agent"); assert.equal(recordState(record), "waiting_for_approval");
  assert.equal(recordState({ fields: [["outcome_certainty", "outcome_unknown"]] }), "outcome_unknown");
  assert.equal(recordState({ reason: "connector_reconciliation_required" }), "connector_reconciliation_required");
  assert.equal(recordState({ event_kind: "Tool requested" }), "Tool requested");
  const untrusted = '<img src=x onerror="throw new Error()">';
  assert.equal(title({ fields: [["title", untrusted]] }), untrusted, "The renderer must insert the returned label with textContent");
  const suspicious = fields({ fields: [["__proto__", { polluted: true }], ["name", "Literal label"]] });
  assert.equal(Object.prototype.polluted, undefined); assert.equal(suspicious.name, "Literal label");
});

const reviewRecord = values => ({ fields: Object.entries(values) });
const reviewNow = Date.parse("2026-10-01T12:00:00Z");

test("restored holds remain explicit even alongside decisions and terminal flags", () => {
  assert.equal(reviewState(reviewRecord({ restore_hold: "True", cancelled: "True", consumed: "True", "decisions.0.kind": "approved" }), reviewNow), "restore hold");
  assert.equal(reviewState(reviewRecord({ restore_hold: "False", "decisions.0.kind": "approved" }), reviewNow), "approved");
});

test("cancelled and consumed records do not return to the awaiting-review state", () => {
  assert.equal(reviewState(reviewRecord({ cancelled: "True", consumed: "True", "request.expires_at": "2026-09-01T00:00:00Z" }), reviewNow), "cancelled");
  assert.equal(reviewState(reviewRecord({ consumed: "True", "decisions.0.kind": "approved" }), reviewNow), "consumed");
});

test("latest rejected/revoked decision uses numeric sequence rather than field insertion order", () => {
  assert.equal(reviewState(reviewRecord({ "decisions.10.kind": "revoked", "decisions.2.kind": "approved", "decisions.9.kind": "rejected" }), reviewNow), "revoked");
  assert.equal(reviewState(reviewRecord({ "decisions.3.kind": "approved", "decisions.11.kind": "rejected", "decisions.1.kind": "revoked", "request.expires_at": "2026-09-01T00:00:00Z" }), reviewNow), "rejected");
  assert.equal(reviewState(reviewRecord({ "decisions.2.kind": "rejected", "decisions.12.kind": "approved" }), reviewNow), "approved");
});

test("an approved review expires at its request or intent expiry without suggesting authority", () => {
  assert.equal(reviewState(reviewRecord({ "decisions.0.kind": "approved", "request.expires_at": "2026-10-01T12:00:00Z" }), reviewNow), "expired");
  assert.equal(reviewState(reviewRecord({ "decisions.0.kind": "approved", "intent.expires_at": "2026-09-30T12:00:00Z" }), reviewNow), "expired");
  assert.equal(reviewState(reviewRecord({ "decisions.0.kind": "approved", "request.expires_at": "2026-10-02T12:00:00Z" }), reviewNow), "approved");
});

test("awaiting label does not invent a missing request and expired records are never pending", () => {
  const missingRequest = reviewRecord({ "intent.id": "intent-no-request" });
  const pending = reviewRecord({ "request.intent_id": "intent-pending", "request.expires_at": "2026-10-02T12:00:00Z" });
  const expired = reviewRecord({ "request.intent_id": "intent-expired", "request.expires_at": "2026-09-30T12:00:00Z" });
  const reviewed = reviewRecord({ "request.intent_id": "intent-approved", "decisions.0.kind": "approved" });
  assert.equal(reviewState(missingRequest, reviewNow), "awaiting review");
  assert.equal(reviewState(expired, reviewNow), "expired");
  const pendingRecords = [missingRequest, pending, expired, reviewed].filter(record => Boolean(fields(record)["request.intent_id"]) && reviewState(record, reviewNow) === "awaiting review");
  assert.deepEqual(pendingRecords, [pending]);
});

for (const { name, run } of tests) {
  try { await run(); process.stdout.write(`PASS ${name}\n`); }
  catch (error) { process.stderr.write(`FAIL ${name}\n${error.stack}\n`); process.exitCode = 1; }
  finally {
    globalThis.fetch = saved.fetch; globalThis.setInterval = saved.setInterval; globalThis.clearInterval = saved.clearInterval;
    if (saved.document === undefined) delete globalThis.document; else globalThis.document = saved.document;
  }
}
if (!process.exitCode) process.stdout.write(`Spatial data contract: ${tests.length} checks passed.\n`);
