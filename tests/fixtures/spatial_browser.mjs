// Live, offline browser acceptance through Chromium's private CDP pipe.
// Data is served by the real authenticated SQLite-backed operator host.
import {spawn} from 'node:child_process';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import assert from 'node:assert/strict';

const cfg = JSON.parse(readFileSync(0, 'utf8'));
const chrome = spawn(cfg.chrome, ['--headless=new', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-pipe',
  '--user-data-dir=' + cfg.profile, 'about:blank'],
  {stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'], windowsHide: true});
let sequence = 0, buffer = '', session, closing = false, browserLog = '';
const pending = new Map(), dialogs = [], exceptions = [], requests = [], checks = [];
chrome.stderr.on('data', data => {browserLog = (browserLog + data.toString()).slice(-6000);});
chrome.stdio[4].on('data', data => {
  buffer += data.toString();
  let end;
  while ((end = buffer.indexOf('\0')) >= 0) {
    const message = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    if (message.id) {
      const result = pending.get(message.id);
      pending.delete(message.id);
      if (result) {
        clearTimeout(result.timer);
        message.error ? result.reject(new Error(JSON.stringify(message.error))) : result.resolve(message.result);
      }
    }
    if (message.method === 'Page.javascriptDialogOpening') dialogs.push(message.params.type);
    if (message.method === 'Runtime.exceptionThrown') {
      const detail = message.params.exceptionDetails;
      exceptions.push({text: detail.text, url: detail.url, line: detail.lineNumber + 1,
        column: detail.columnNumber + 1, description: detail.exception?.description});
    }
    if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request);
  }
});
chrome.on('exit', (code, signal) => {
  for (const result of pending.values()) {
    clearTimeout(result.timer);
    closing ? result.resolve({}) : result.reject(new Error('Browser exited before acceptance completed: ' +
      (signal || code) + '\n' + browserLog));
  }
  pending.clear();
});
function send(method, params = {}, sessionId = session) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('CDP timeout: ' + method));
    }, 15000);
    pending.set(id, {resolve, reject, timer});
    chrome.stdio[3].write(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true, replMode: true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression, label = expression) {
  for (let index = 0; index < 120; index++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('DOM condition timed out: ' + label);
}
async function click(selector) {
  await evaluate(`(() => {const target = document.querySelector(${JSON.stringify(selector)});
    if (!target) throw new Error('Missing interaction target'); target.click();})()`);
}
async function key(key, code, modifiers = 0) {
  const virtualKey = {Tab: 9, Enter: 13, Escape: 27, PageDown: 34, KeyK: 75}[code] || 0;
  const values = {key, code, modifiers, windowsVirtualKeyCode: virtualKey, nativeVirtualKeyCode: virtualKey};
  await send('Input.dispatchKeyEvent', {type: 'rawKeyDown', ...values});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', ...values});
}
async function screenshot(name) {
  mkdirSync(cfg.snapshots, {recursive: true});
  const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  writeFileSync(join(cfg.snapshots, name + '.png'), Buffer.from(result.data, 'base64'));
}
async function settleScroll(selector) {
  let previous, stable = 0;
  for (let index = 0; index < 60; index++) {
    const position = await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollTop`);
    stable = position === previous ? stable + 1 : 0;
    if (stable >= 3) return;
    previous = position;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error('Scroll did not settle');
}
async function view(name) {
  await click(`#navigation button[data-view="${name}"]`);
  await until(`document.querySelector('#navigation [data-view="${name}"]').classList.contains('active')`);
  await until(`document.getElementById('data').getAttribute('aria-busy') !== 'true'`);
}
async function assertMuted() {
  assert.equal(await evaluate(`document.getElementById('sound-toggle').getAttribute('aria-pressed')`), 'false');
  assert.equal(await evaluate('window.__audioStarts.context'), 0, 'AudioContext activated without consent');
  assert.equal(await evaluate('window.__audioStarts.capture'), 0, 'Microphone activated without consent');
  assert.equal(await evaluate('window.__audioStarts.speech'), 0, 'Speech output started while muted');
}
const instrumentation = `
window.cspViolations = [];
document.addEventListener('securitypolicyviolation', event => window.cspViolations.push(event.violatedDirective));
window.__audioStarts = {context: 0, capture: 0, speech: 0};
for (const name of ['AudioContext', 'webkitAudioContext']) {
  const original = window[name];
  if (original) window[name] = new Proxy(original, {construct(target, args) {
    window.__audioStarts.context++; return Reflect.construct(target, args);
  }});
}
if (navigator.mediaDevices?.getUserMedia) {
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = (...args) => {window.__audioStarts.capture++; return original(...args);};
}
for (const name of ['SpeechRecognition', 'webkitSpeechRecognition']) {
  const original = window[name];
  if (original) window[name] = new Proxy(original, {construct(target, args) {
    const recognition = Reflect.construct(target, args);
    const start = recognition.start.bind(recognition);
    recognition.start = (...values) => {window.__audioStarts.capture++; return start(...values);};
    return recognition;
  }});
}
if (window.speechSynthesis) {
  const original = window.speechSynthesis.speak.bind(window.speechSynthesis);
  window.speechSynthesis.speak = (...args) => {window.__audioStarts.speech++; return original(...args);};
}
const originalContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
  if (String(kind).startsWith('webgl')) return null;
  return originalContext.call(this, kind, ...args);
};
`;

try {
  const target = await send('Target.createTarget', {url: 'about:blank'}, null);
  session = (await send('Target.attachToTarget', {targetId: target.targetId, flatten: true}, null)).sessionId;
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
  await send('Emulation.setEmulatedMedia', {features: [{name: 'prefers-reduced-motion', value: 'reduce'}]});
  await send('Page.addScriptToEvaluateOnNewDocument', {source: instrumentation});
  await send('Page.navigate', {url: cfg.origin + '/command'});
  await until(`document.getElementById('login') && !document.getElementById('login').hidden`, 'signed-out gate');
  assert.equal(await evaluate(`document.getElementById('content').hidden`), true);
  await assertMuted();
  await evaluate(`document.getElementById('credential').value = ${JSON.stringify(cfg.credential)};
    document.getElementById('login-form').requestSubmit();`);
  await until(`!document.getElementById('content').hidden && document.getElementById('login').hidden`, 'authenticated shell');
  await until(`document.getElementById('data').getAttribute('aria-busy') !== 'true'`);
  await assertMuted();
  checks.push('real_login', 'muted_by_default', 'webgl_unavailable_fallback');

  const agents = await evaluate(`(await api('/api/v1/inspect/agents?limit=100')).items`);
  const goals = await evaluate(`(await api('/api/v1/inspect/goals?limit=100')).items`);
  assert.equal(agents.length > 0, cfg.populated);
  assert.equal(goals.length > 0, cfg.populated);
  assert(await evaluate(`document.getElementById('connection').textContent.length > 0`));
  assert(await evaluate(`(() => {const canvas = document.querySelector('.core-region canvas');
    if (!canvas || canvas.hidden || canvas.width < 100 || canvas.height < 100) return false;
    return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some((value, index) => index % 4 === 3 && value > 0);
  })()`), 'Spatial core failed to render without WebGL');
  assert.equal(await evaluate(`document.documentElement.scrollWidth > innerWidth + 1`), false, 'desktop horizontal overflow');
  await screenshot('command-core-desktop');

  await send('Network.emulateNetworkConditions', {offline: false, latency: 250,
    downloadThroughput: -1, uploadThroughput: -1});
  await evaluate(`void setView('agents'); true`);
  await until(`document.getElementById('data').getAttribute('aria-busy') === 'true'`, 'announced loading state');
  await send('Network.emulateNetworkConditions', {offline: false, latency: 0,
    downloadThroughput: -1, uploadThroughput: -1});
  await until(`document.getElementById('data').getAttribute('aria-busy') === 'false'`, 'completed loading state');
  checks.push('live_loading_state');

  await view('agents');
  if (cfg.populated) {
    await until(`document.querySelector('[data-agent-id]') !== null`, 'canonical agent selection');
    const selected = await evaluate(`document.querySelector('[data-agent-id]').dataset.agentId`);
    assert(agents.some(agent => agent.id === selected), 'Agent node does not identify a canonical definition');
    await click('[data-agent-id]');
    await until(`document.getElementById('detail-dialog').open && document.getElementById('detail').textContent.includes(${JSON.stringify(selected)})`, 'agent readable detail');
    await click('#detail-close');
    checks.push('canonical_agent_selection');

    const goal = goals.find(row => JSON.stringify(row.fields).includes('cross-department'));
    assert(goal, 'Aurora seed must include canonical collaboration goal');
    await evaluate(`await openRecord('goals', ${JSON.stringify(goal.id)}); true`);
    await until(`document.querySelectorAll('#execution-stack .stack-layer').length > 0`, 'execution stack');
    const lineage = await evaluate(`await api('/api/v1/lineage/goals/' + ${JSON.stringify(goal.id)})`);
    const realIds = new Set([goal.id, ...lineage.sections.flatMap(section => section.records.map(record => record.id))]);
    const displayedIds = await evaluate(`[...document.querySelectorAll('#execution-stack [data-record-id]')].map(node => node.dataset.recordId)`);
    assert(displayedIds.length > 0, 'Execution layers must expose the canonical record they describe');
    assert(displayedIds.every(id => realIds.has(id)), 'Execution stack fabricated a record outside canonical lineage');
    assert(displayedIds.includes(goal.id), 'Stack lost its goal root');
    await click('#detail-close');
    await evaluate(`document.getElementById('execution-stack').focus()`);
    await key('PageDown', 'PageDown');
    await until(`document.getElementById('execution-stack').scrollTop > 0`, 'keyboard execution-depth navigation');
    await settleScroll('#execution-stack');
    await evaluate(`[...document.querySelectorAll('.stack-nav button')].find(button => button.textContent === 'Reset stack').click()`);
    await until(`document.getElementById('execution-stack').scrollTop === 0`, 'execution stack reset');
    await evaluate(`[...document.querySelectorAll('.stack-nav button')].find(button => button.textContent === 'Go deeper').click()`);
    await until(`document.getElementById('execution-stack').scrollTop > 0`, 'equivalent stack navigation control');
    await settleScroll('#execution-stack');
    await evaluate(`[...document.querySelectorAll('.stack-nav button')].find(button => button.textContent === 'Reset stack').click()`);
    await until(`document.getElementById('execution-stack').scrollTop === 0`);
    await screenshot('execution-stack-desktop');
    checks.push('canonical_execution_stack');

    const delivery = goals.find(row => JSON.stringify(row.fields).includes('Deliver synthetic brief'));
    assert(delivery, 'Aurora seed must include observed tool-delivery lineage');
    await evaluate(`await openRecord('goals', ${JSON.stringify(delivery.id)}); true`);
    await until(`document.querySelector('#execution-stack [data-kind="receipts"][data-record-id]') !== null`, 'observed receipt layer');
    const deliveryLineage = await evaluate(`await api('/api/v1/lineage/goals/' + ${JSON.stringify(delivery.id)})`);
    const receipts = deliveryLineage.sections.find(section => section.kind === 'receipts').records;
    const receiptIds = await evaluate(`[...document.querySelectorAll('#execution-stack [data-kind="receipts"][data-record-id]')].map(node => node.dataset.recordId)`);
    assert(receiptIds.every(id => receipts.some(receipt => receipt.id === id)), 'Displayed receipt is outside actual tool lineage');
    assert(await evaluate(`document.getElementById('execution-stack').textContent.toLowerCase().replaceAll('_', ' ').includes('observed success')`), 'Receipt must retain canonical outcome certainty');
    await click('#detail-close');
    checks.push('canonical_tool_receipt');

    await evaluate(`await openRecord('goals', ${JSON.stringify(cfg.hostileGoal)}); true`);
    await until(`document.getElementById('detail').textContent.includes(${JSON.stringify(cfg.marker)})`, 'escaped stored goal');
    for (const kind of ['departments', 'knowledge', 'messages']) {
      await evaluate(`await setView(${JSON.stringify(kind)});
        detail((await api('/api/v1/inspect/' + ${JSON.stringify(kind)} + '?limit=100')).items.find(row => JSON.stringify(row.fields).includes(${JSON.stringify(cfg.marker)}))); true`);
      assert(await evaluate(`document.getElementById('detail').textContent.includes(${JSON.stringify(cfg.marker)})`), kind);
      assert.equal(await evaluate(`document.querySelectorAll('#detail script, #detail img').length`), 0, kind);
    }
    await click('#detail-close');
    checks.push('stored_xss_escaped');
    await view('recovery');
    assert(await evaluate(`document.getElementById('data').textContent.length > 0`));
    assert(await evaluate(`(await api('/api/v1/recovery')).items.length > 0`));
    checks.push('canonical_recovery');
  } else {
    assert.equal(await evaluate(`document.querySelectorAll('[data-agent-id]').length`), 0, 'Empty backend gained fake agents');
    assert(await evaluate(`document.getElementById('data').textContent.toLowerCase().includes('no ')`), 'Helpful empty agent state missing');
    await view('goals');
    assert(await evaluate(`document.getElementById('data').textContent.toLowerCase().includes('no ')`), 'Helpful empty goal state missing');
    checks.push('real_empty_workspace');
  }

  // Keyboard open, focus containment, and return focus without mouse-only controls.
  await evaluate(`document.getElementById('sound-toggle').focus()`);
  await key('k', 'KeyK', 2);
  await until(`document.getElementById('command-palette').open`, 'Ctrl+K command palette');
  assert.equal(await evaluate(`document.activeElement.id`), 'command-search');
  await key('Tab', 'Tab', 1);
  assert(await evaluate(`document.getElementById('command-palette').contains(document.activeElement)`), 'Palette let keyboard focus escape');
  await key('Escape', 'Escape');
  await until(`!document.getElementById('command-palette').open`, 'Escape palette close');
  assert.equal(await evaluate(`document.activeElement.id`), 'sound-toggle');
  await key('k', 'KeyK', 2);
  await until(`document.getElementById('command-palette').open`);
  await evaluate(`document.getElementById('command-search').value = 'Recovery';
    document.getElementById('command-search').dispatchEvent(new Event('input', {bubbles: true}));`);
  await until(`document.getElementById('command-results').textContent.toLowerCase().includes('recovery')`);
  await key('Enter', 'Enter');
  await until(`!document.getElementById('command-palette').open && document.querySelector('#navigation [data-view="recovery"]').classList.contains('active')`, 'keyboard command navigation');
  checks.push('keyboard_palette_focus');

  // This is an explicit test-owned authorized maintenance transition, not a UI action capability.
  await evaluate(`await api('/api/v1/mode/restrict', {method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Operator-Request': '1'},
    body: JSON.stringify({mode: 'restore_quarantine'})}); await setView('overview'); true`);
  await until(`!document.getElementById('quarantine').hidden`, 'persistent restore quarantine');
  assert(await evaluate(`document.getElementById('quarantine').textContent.toLowerCase().includes('blocked')`));
  await view('recovery');
  assert.equal(await evaluate(`document.getElementById('quarantine').hidden`), false);
  checks.push('restore_quarantine_persistent');

  // Network failure remains an honest error state with no fabricated successful snapshot.
  await send('Network.setBlockedURLs', {urls: [cfg.origin + '/api/v1/inspect/*']});
  await evaluate(`await setView('agents'); true`);
  assert(await evaluate(`document.getElementById('data').querySelector('.error, [role="alert"]') !== null`), 'API failure lacks a readable error');
  await send('Network.setBlockedURLs', {urls: []});
  await evaluate(`await setView('agents'); true`);
  checks.push('api_failure_and_recovery');

  const motion = await evaluate(`(() => {
    const seconds = value => value.split(',').map(item => parseFloat(item) * (item.trim().endsWith('ms') ? .001 : 1));
    return [...document.querySelectorAll('body *')].filter(node => !node.hidden && node.getClientRects().length)
      .flatMap(node => {const style = getComputedStyle(node); return [...seconds(style.animationDuration), ...seconds(style.transitionDuration)];});
  })()`);
  assert(motion.every(duration => duration <= .011), 'Reduced motion retained visible animation');
  checks.push('reduced_motion');

  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await evaluate(`await setView('overview'); window.scrollTo(0, 0); true`);
  assert.equal(await evaluate(`document.documentElement.scrollWidth > innerWidth + 1`), false, 'mobile horizontal overflow');
  assert(await evaluate(`document.getElementById('quarantine').getBoundingClientRect().width <= innerWidth`));
  for (const name of ['goals', 'conversation', 'approvals', 'recovery']) {
    await view(name);
    assert.equal(await evaluate(`document.documentElement.scrollWidth > innerWidth + 1`), false, 'mobile ' + name + ' overflow');
  }
  await screenshot('recovery-mobile');
  await assertMuted();
  checks.push('mobile_operational_views');

  await click('#sound-toggle');
  assert.equal(await evaluate(`document.getElementById('sound-toggle').getAttribute('aria-pressed')`), 'true');
  await click('#sound-toggle');
  assert.equal(await evaluate(`document.getElementById('sound-toggle').getAttribute('aria-pressed')`), 'false');
  const violations = await evaluate('window.cspViolations');
  await send('Page.reload');
  await until(`document.getElementById('content') && !document.getElementById('content').hidden`, 'persisted session after reload');
  await assertMuted();
  checks.push('mute_preference_persisted');

  const privateTranscript = 'Session-local operator transcript: spatial acceptance';
  if (cfg.populated) {
    await evaluate(`await setView('conversation'); true`);
    await evaluate(`const input = document.querySelector('.conversation-stage form input');
      input.value = ${JSON.stringify(privateTranscript)}; input.form.requestSubmit();`);
    await until(`document.getElementById('transcript').textContent.includes(${JSON.stringify(privateTranscript)})`, 'visible operator transcript');
  }
  await click('#logout');
  await until(`document.getElementById('content').hidden && !document.getElementById('login').hidden`, 'logout session gate');
  assert.equal(await evaluate(`document.getElementById('data').textContent`), '');
  assert.equal(await evaluate(`document.getElementById('detail').textContent`), '');
  assert.equal(await evaluate(`document.getElementById('workspace-name').textContent`), 'Local workspace');
  const signedOutText = await evaluate('document.body.textContent');
  assert.equal(signedOutText.includes(privateTranscript), false, 'Operator transcript survived logout');
  assert(agents.every(agent => !signedOutText.includes(agent.id)), 'Prior agent identities survived logout');
  assert(goals.every(goal => !signedOutText.includes(goal.id)), 'Prior goal identities survived logout');
  checks.push('logout_clears_workspace_and_transcript');

  assert.deepEqual([...violations, ...await evaluate('window.cspViolations')], [], 'CSP violations');
  assert.deepEqual(dialogs, [], 'Unexpected script dialogs');
  assert.deepEqual(exceptions, [], 'Unhandled script exceptions');
  const posts = requests.filter(request => request.method === 'POST').map(request => new URL(request.url).pathname);
  assert(posts.every(path => ['/api/v1/login', '/api/v1/logout', '/api/v1/mode/restrict'].includes(path)), 'Read UI introduced an unauthorized mutation');
  console.log(JSON.stringify({result: 'spatial_browser_acceptance_passed', populated: cfg.populated,
    checks, csp_violations: 0, script_exceptions: 0, snapshots: cfg.snapshots}));
} catch (error) {
  console.error(error.stack || String(error));
  console.error(JSON.stringify({exceptions, dialogs,
    page: await evaluate(`({title: document.title, text: document.body?.innerText.slice(0, 1000), csp: window.cspViolations})`).catch(() => null)}));
  process.exitCode = 1;
} finally {
  closing = true;
  await send('Browser.close', {}, null).catch(() => {});
  chrome.kill();
  for (const result of pending.values()) clearTimeout(result.timer);
}
