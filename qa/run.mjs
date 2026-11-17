/* RealMouse — acceptance harness.
   Drives the installed Chrome over raw CDP, measures the pointer, and fails
   loudly. Exit code 1 if any check does not hold. No npm dependencies.

   usage: node qa/run.mjs [--headed] */

import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  launch,
  evaluate,
  waitFor,
  move,
  press,
  release,
  click,
  wheel,
  key,
  screenshot,
  rect,
  sleep,
} from './cdp.mjs';

const HERE = resolve(fileURLToPath(new URL('.', import.meta.url)));
const ROOT = resolve(HERE, '..');
const EVIDENCE = join(HERE, 'evidence');
const PORT = 8099;
const BASE = `http://127.0.0.1:${PORT}`;
const URL_UNDER_TEST = `${BASE}/?qa=1`;

const results = [];
const record = (name, pass, detail) => {
  results.push({ name, pass: Boolean(pass), detail });
  const mark = pass ? 'PASS' : 'FAIL';
  process.stdout.write(`${mark}  ${name.padEnd(26)} ${detail}\n`);
};

const near = (a, b, tolerance) => Math.abs(a - b) <= tolerance;

async function main() {
  await mkdir(EVIDENCE, { recursive: true });

  const server = spawn(process.execPath, [join(HERE, 'serve.mjs')], {
    cwd: ROOT,
    stdio: 'ignore',
    windowsHide: true,
  });
  await sleep(600);

  const browser = await launch({ port: 9333 });
  const { cdp } = browser;

  /** Scroll a selector into the middle of the viewport and return its centre. */
  const center = async (selector) => {
    await evaluate(
      cdp,
      `(() => { const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) return false;
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        return true; })()`,
    );
    await sleep(260);
    const box = await rect(cdp, selector);
    if (!box) throw new Error(`Element not found: ${selector}`);
    return { x: Math.round(box.cx), y: Math.round(box.cy), box };
  };

  const consoleErrors = [];
  const pageErrors = [];
  const failures = [];
  const requests = [];

  cdp.on('Runtime.consoleAPICalled', (event) => {
    if (event.type === 'error' || event.type === 'warning') {
      const text = (event.args || []).map((a) => a.value ?? a.description ?? '').join(' ');
      consoleErrors.push(`${event.type}: ${text}`);
    }
  });
  cdp.on('Runtime.exceptionThrown', (event) => {
    pageErrors.push(event.exceptionDetails?.exception?.description || event.exceptionDetails?.text || 'exception');
  });
  cdp.on('Log.entryAdded', (event) => {
    if (event.entry?.level === 'error') consoleErrors.push(`${event.entry.source}: ${event.entry.text}`);
  });
  cdp.on('Network.loadingFailed', (event) => {
    if (!event.canceled) failures.push(`${event.errorText} (${event.requestId})`);
  });
  cdp.on('Network.requestWillBeSent', (event) => {
    requests.push(event.request.url);
  });

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  await cdp.send('Network.enable');

  await browser.viewport(1440, 900);
  await cdp.send('Page.navigate', { url: URL_UNDER_TEST });
  await waitFor(cdp, 'Boolean(window.__mouse && window.__mouse.snapshot)');
  await waitFor(cdp, "window.__mouse.store.get().mode === 'assisted' || window.__mouse.store.get().mode === 'direct'");
  await sleep(500);

  /* ---------------- 1. load integrity ---------------- */
  const external = requests.filter((url) => !url.startsWith(BASE) && !url.startsWith('data:'));
  record(
    'load · console',
    consoleErrors.length === 0 && pageErrors.length === 0,
    `${consoleErrors.length} console, ${pageErrors.length} exceptions`,
  );
  record('load · network', failures.length === 0 && external.length === 0, `${requests.length} requests, ${external.length} external, ${failures.length} failed`);

  /* ---------------- 2. motion fidelity ---------------- */
  const targetPoint = await center('#dblTarget');
  const target = targetPoint.box;
  await evaluate(cdp, "window.__mouse.store.set({ mode: 'direct', magnet: false })");
  await sleep(60);
  const startTransform = await evaluate(cdp, "document.getElementById('cursor').style.transform");
  await move(cdp, targetPoint.x, targetPoint.y, 10, 16);
  await sleep(260);

  const afterDirect = await evaluate(cdp, 'window.__mouse.snapshot()');
  const dX = afterDirect.position.x - target.cx;
  const dY = afterDirect.position.y - target.cy;
  const moved = startTransform !== (await evaluate(cdp, "document.getElementById('cursor').style.transform"));
  record(
    'motion · direct 1:1',
    near(dX, 0, 1.5) && near(dY, 0, 1.5) && moved,
    `Δx=${dX.toFixed(2)} Δy=${dY.toFixed(2)} (≤1.5), moved=${moved}`,
  );

  // assisted mode must lag behind and then settle: measure the residual distance
  await evaluate(cdp, "window.__mouse.store.set({ mode: 'assisted', smoothing: 60, weight: 0.6 })");
  await move(cdp, 120, 140, 6, 16);
  const assistedEarly = await evaluate(cdp, 'window.__mouse.snapshot()');
  await sleep(420);
  const assistedSettled = await evaluate(cdp, 'window.__mouse.snapshot()');
  const earlyGap = Math.hypot(assistedEarly.position.x - 120, assistedEarly.position.y - 140);
  const settledGap = Math.hypot(assistedSettled.position.x - 120, assistedSettled.position.y - 140);
  record(
    'motion · assisted curve',
    settledGap < 2 && settledGap < Math.max(earlyGap, 0.5),
    `lag during motion ${earlyGap.toFixed(1)}px → settled ${settledGap.toFixed(2)}px`,
  );
  await evaluate(cdp, "window.__mouse.store.set({ mode: 'direct', magnet: true })");

  /* ---------------- 3. click / double / context ---------------- */
  const btn = await center('#btnPrimary');
  await click(cdp, btn.x, btn.y);
  await sleep(120);
  const presses = await evaluate(cdp, "document.getElementById('btnCount').textContent.trim()");
  record('click · primary', presses === '1', `counter=${presses}`);

  const dblPoint = await center('#dblTarget');
  const dx = dblPoint.x;
  const dy = dblPoint.y;
  await move(cdp, dx, dy);
  await press(cdp, dx, dy, 'left', 1);
  await release(cdp, dx, dy, 'left', 1);
  await sleep(70);
  await press(cdp, dx, dy, 'left', 2);
  await release(cdp, dx, dy, 'left', 2);
  await sleep(200);
  const doubles = await evaluate(cdp, "document.getElementById('dblCount').textContent.trim()");
  record('click · double', doubles === '1', `double counter=${doubles}`);

  const ctxPoint = await center('#ctxTarget');
  await click(cdp, ctxPoint.x, ctxPoint.y, 'right');
  await sleep(260);
  const menuOpen = await evaluate(cdp, "document.getElementById('menu').classList.contains('is-open')");
  await key(cdp, 'Escape', 'Escape', 27);
  await sleep(180);
  const menuClosed = await evaluate(cdp, "!document.getElementById('menu').classList.contains('is-open')");
  record('click · context menu', menuOpen && menuClosed, `open=${menuOpen} esc-closed=${menuClosed}`);

  /* ---------------- 4. kinetic drag ---------------- */
  const cardPoint = await center('#dragCard');
  const card = cardPoint.box;
  const zone = await rect(cdp, '#dropZone');
  await move(cdp, cardPoint.x, cardPoint.y);
  await press(cdp, cardPoint.x, cardPoint.y);
  await move(cdp, Math.round(zone.cx), Math.round(zone.cy), 12, 18, 1);
  await sleep(120);
  const armed = await evaluate(cdp, "document.getElementById('dropZone').classList.contains('is-armed')");
  await release(cdp, Math.round(zone.cx), Math.round(zone.cy));
  await sleep(900);
  const dropText = await evaluate(cdp, "document.getElementById('dropState').textContent.trim()");
  const cardShift = await evaluate(
    cdp,
    "(() => { const t = document.getElementById('dragCard').style.transform; return t; })()",
  );
  record(
    'drag · drop',
    armed && dropText.includes('filled') && /translate3d\(-?[\d.]+px/.test(cardShift),
    `armed=${armed} state="${dropText}" transform="${cardShift}"`,
  );

  /* ---------------- 5. wheel detents ---------------- */
  const wellPoint = await center('#well');
  await move(cdp, wellPoint.x, wellPoint.y);
  await wheel(cdp, wellPoint.x, wellPoint.y, 120, 3);
  await sleep(700);
  const wheelState = await evaluate(
    cdp,
    "({ detents: window.__mouse.well.detents, top: window.__mouse.well.scrollTop, meta: document.getElementById('scrollMeta').textContent })",
  );
  record(
    'wheel · detents',
    wheelState.detents >= 3 && wheelState.top > 100,
    `${wheelState.detents} notches, scrollTop=${wheelState.top.toFixed(1)}px`,
  );

  /* ---------------- 6. keyboard scroll on the well ---------------- */
  await evaluate(cdp, "document.getElementById('well').focus()");
  await key(cdp, 'Home', 'Home', 36);
  await sleep(400);
  const home = await evaluate(cdp, 'Number(window.__mouse.well.scrollTop) || 0');
  await key(cdp, 'End', 'End', 35);
  await sleep(600);
  const end = await evaluate(cdp, 'Number(window.__mouse.well.scrollTop) || 0');
  record('wheel · keyboard', home < 2 && end > 100, `home=${home.toFixed(1)} end=${end.toFixed(1)}`);

  /* ---------------- 7. settings persistence ---------------- */
  await evaluate(
    cdp,
    `(() => { const el = document.getElementById('setSensitivity');
      el.value = '2.0';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return true; })()`,
  );
  await sleep(120);
  const beforeReload = await evaluate(cdp, 'window.__mouse.store.get().weight');
  await cdp.send('Page.reload', { ignoreCache: false });
  await waitFor(cdp, 'Boolean(window.__mouse && window.__mouse.snapshot)');
  await sleep(400);
  const afterReload = await evaluate(cdp, 'window.__mouse.store.get().weight');
  record('settings · persist', beforeReload === 2 && afterReload === 2, `before=${beforeReload} after reload=${afterReload}`);

  /* ---------------- 8. performance ---------------- */
  // Produce real input first, so the telemetry has something to measure.
  const btnAgain = await center('#btnPrimary');
  await click(cdp, btnAgain.x, btnAgain.y);
  await sleep(120);

  const perf = await evaluate(
    cdp,
    `new Promise((resolve) => {
      const times = [];
      let last = performance.now();
      let count = 0;
      const tick = (now) => {
        times.push(now - last); last = now; count += 1;
        if (count < 120) requestAnimationFrame(tick);
        else {
          const sorted = times.slice(5).sort((a, b) => a - b);
          const median = sorted[Math.floor(sorted.length / 2)];
          resolve({ median, fps: 1000 / median, frames: times.length });
        }
      };
      requestAnimationFrame(tick);
    })`,
    { awaitPromise: true },
  );
  record('perf · frame budget', Boolean(perf) && perf.median <= 20 && perf.fps >= 50, perf ? `median ${perf.median.toFixed(2)}ms · ${perf.fps.toFixed(1)}fps` : 'no measurement');

  const snapshot = (await evaluate(cdp, 'window.__mouse && window.__mouse.snapshot()')) || {};

  // Sample input→paint across sustained movement so one unlucky frame cannot
  // decide the check; report the median of the positive samples.
  const latencySamples = [];
  for (let i = 0; i < 18; i += 1) {
    await move(cdp, 320 + i * 7, 430 + (i % 2) * 10);
    await sleep(22);
    const value = await evaluate(cdp, 'window.__mouse.snapshot().inputToPaint');
    if (Number(value) > 0) latencySamples.push(Number(value));
  }
  latencySamples.sort((a, b) => a - b);
  const medianLatency = latencySamples.length
    ? latencySamples[Math.floor(latencySamples.length / 2)]
    : 0;

  record(
    'perf · telemetry',
    medianLatency > 0 && medianLatency < 40 && Number(snapshot.clicks) >= 1,
    `median input→paint ${medianLatency.toFixed(1)}ms over ${latencySamples.length} samples · coalesced×${Number(snapshot.coalesced || 0).toFixed(2)} · clicks ${snapshot.clicks || 0}`,
  );

  /* ---------------- 9. layout at three sizes ---------------- */
  const layout = [];
  for (const [w, h, label] of [
    [1440, 900, 'desktop'],
    [834, 1112, 'tablet'],
    [390, 844, 'phone'],
  ]) {
    await browser.viewport(w, h);
    await sleep(320);
    const info = await evaluate(
      cdp,
      `(() => {
        const de = document.documentElement;
        const stage = document.getElementById('stage').getBoundingClientRect();
        const rail = document.querySelector('.main__rail').getBoundingClientRect();
        return {
          overflow: de.scrollWidth - de.clientWidth,
          stageW: Math.round(stage.width),
          stageH: Math.round(stage.height),
          railW: Math.round(rail.width),
        };
      })()`,
    );
    layout.push({ label, ...info });
    record(
      `layout · ${label}`,
      info.overflow <= 1 && info.stageW > 200 && info.stageH > 200,
      `overflow=${info.overflow}px stage=${info.stageW}×${info.stageH} rail=${info.railW}px`,
    );
  }

  /* ---------------- 10. accessibility names ---------------- */
  const a11y = await evaluate(
    cdp,
    `(() => {
      const nodes = [...document.querySelectorAll('a[href], button, input, textarea, select, [role="button"]')]
        .filter((el) => el.getAttribute('aria-hidden') !== 'true');
      const nameless = nodes.filter((el) => {
        const label = el.getAttribute('aria-label');
        const labelled = el.getAttribute('aria-labelledby');
        const text = (el.textContent || '').trim();
        const id = el.id;
        const explicit = id ? document.querySelector('label[for="' + id + '"]') : null;
        const wrapping = el.closest('label');
        return !label && !labelled && !text && !explicit && !wrapping;
      }).map((el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''));
      return { total: nodes.length, nameless };
    })()`,
  );
  record(
    'a11y · names',
    a11y.nameless.length === 0,
    `${a11y.total} controls, ${a11y.nameless.length} nameless${a11y.nameless.length ? ': ' + a11y.nameless.join(', ') : ''}`,
  );

  const focusable = await evaluate(
    cdp,
    `(() => {
      const ring = getComputedStyle(document.documentElement);
      const rule = [...document.styleSheets].some((sheet) => {
        try { return [...sheet.cssRules].some((r) => r.selectorText && r.selectorText.includes(':focus-visible')); }
        catch { return false; }
      });
      return { hasFocusStyle: rule, outline: ring.getPropertyValue('--accent').trim() };
    })()`,
  );
  record('a11y · focus ring', focusable.hasFocusStyle, `focus-visible rule present, accent=${focusable.outline}`);

  /* ---------------- 11. deterministic screenshots ---------------- */
  const shots = [];
  for (const [w, h, name] of [
    [1440, 900, 'desktop'],
    [834, 1112, 'tablet'],
    [390, 844, 'phone'],
  ]) {
    await browser.viewport(w, h);
    await sleep(300);
    await evaluate(cdp, "window.scrollTo({ top: 0, behavior: 'auto' })");
    await evaluate(
      cdp,
      "window.__mouse.store.reset(); window.__mouse.telemetry.reset(); window.__mouse.well.reset(); window.__mouse.drag.reset(); true",
    );
    await sleep(260);
    await evaluate(cdp, `window.__mouse.setPos(${Math.round(w * 0.52)}, ${Math.round(Math.min(h, 900) * 0.46)})`);
    await sleep(240);

    const metrics = await cdp.send('Page.getLayoutMetrics');
    const pageHeight = Math.min(Math.ceil(metrics.cssContentSize.height), 4200);
    const path = join(EVIDENCE, `stage-${name}-${w}x${h}.png`);
    await cdp.send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: w, height: pageHeight, scale: 1 },
    }).then(async ({ data }) => {
      const { writeFile } = await import('node:fs/promises');
      await writeFile(path, Buffer.from(data, 'base64'));
    });
    shots.push(path);
  }
  record('capture · screenshots', shots.length === 3, shots.map((p) => p.replace(ROOT, '.')).join('  '));

  const summary = {
    at: new Date().toISOString(),
    url: URL_UNDER_TEST,
    chrome: browser.executablePath,
    checks: results,
    passed: results.filter((r) => r.pass).length,
    failed: results.filter((r) => !r.pass).length,
    telemetry: snapshot,
    layout,
    screenshots: shots,
  };
  await writeFile(join(EVIDENCE, 'report.json'), JSON.stringify(summary, null, 2), 'utf8');

  await browser.close();
  server.kill();

  process.stdout.write(
    `\n${summary.passed}/${results.length} checks passed` +
      (summary.failed ? ` — ${summary.failed} FAILED\n` : '\n'),
  );
  process.exit(summary.failed ? 1 : 0);
}

main().catch(async (error) => {
  process.stderr.write(`\nHarness error: ${error.stack || error.message}\n`);
  process.exit(1);
});
