/* RealMouse — a minimal Chrome DevTools Protocol client.
   Node 22 ships fetch and WebSocket, so this needs no packages at all. */

import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function pickBrowser() {
  const { access } = await import('node:fs/promises');
  for (const candidate of CANDIDATES) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      /* keep looking */
    }
  }
  throw new Error('No Chrome or Edge executable found. Set CHROME_PATH.');
}

export class CDP {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();

    ws.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(`${message.error.message} (${message.error.code})`));
        else resolve(message.result);
        return;
      }
      if (message.method) {
        const handlers = this.listeners.get(message.method);
        if (handlers) for (const handler of handlers) handler(message.params);
      }
    });
  }

  on(method, handler) {
    if (!this.listeners.has(method)) this.listeners.set(method, new Set());
    this.listeners.get(method).add(handler);
    return () => this.listeners.get(method)?.delete(handler);
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 20000);
    });
  }

  close() {
    try {
      this.ws.close();
    } catch {
      /* already gone */
    }
  }
}

export async function launch({ port = 9333, width = 1440, height = 900 } = {}) {
  const executablePath = await pickBrowser();
  const userDataDir = await mkdtemp(join(tmpdir(), 'realmouse-'));

  const child = spawn(
    executablePath,
    [
      '--headless=new',
      '--remote-debugging-port=' + port,
      '--user-data-dir=' + userDataDir,
      `--window-size=${width},${height}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-sync',
      '--metrics-recording-only',
      '--mute-audio',
      '--hide-scrollbars',
      'about:blank',
    ],
    { stdio: 'ignore', windowsHide: true },
  );

  const deadline = Date.now() + 25000;
  let target = null;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`);
      const list = await res.json();
      target = list.find((entry) => entry.type === 'page');
      if (target?.webSocketDebuggerUrl) break;
    } catch {
      /* browser is still starting */
    }
    await sleep(150);
  }

  if (!target?.webSocketDebuggerUrl) {
    child.kill();
    throw new Error('Chrome did not expose a debugging target in time.');
  }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', () => reject(new Error('WebSocket connection failed')), { once: true });
  });

  const cdp = new CDP(ws);

  return {
    cdp,
    executablePath,
    async viewport(w, h, mobile = false) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width: w,
        height: h,
        deviceScaleFactor: 1,
        mobile,
        screenWidth: w,
        screenHeight: h,
      });
    },
    async close() {
      cdp.close();
      child.kill();
      await sleep(200);
      await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
    },
  };
}

export { sleep };

/* ---------- page helpers ---------- */

export async function evaluate(cdp, expression, { awaitPromise = false } = {}) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const message = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(`Page exception: ${message}`);
  }
  return result.result?.value;
}

export async function waitFor(cdp, expression, { timeout = 8000, interval = 80 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      if (await evaluate(cdp, expression)) return true;
    } catch {
      /* not ready yet */
    }
    await sleep(interval);
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

let lastPos = { x: 0, y: 0 };

export async function move(cdp, x, y, steps = 1, stepDelay = 12, buttons = 0) {
  const from = { ...lastPos };
  for (let i = 1; i <= steps; i += 1) {
    const t = i / steps;
    const px = Math.round(from.x + (x - from.x) * t);
    const py = Math.round(from.y + (y - from.y) * t);
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved',
      x: px,
      y: py,
      button: buttons ? 'left' : 'none',
      buttons,
      pointerType: 'mouse',
    });
    if (steps > 1) await sleep(stepDelay);
  }
  lastPos = { x, y };
}

export async function press(cdp, x, y, button = 'left', clickCount = 1) {
  lastPos = { x, y };
  await cdp.send('Input.dispatchMouseEvent', {
    type: 'mousePressed',
    x,
    y,
    button,
    buttons: button === 'left' ? 1 : button === 'right' ? 2 : 4,
    clickCount,
    pointerType: 'mouse',
  });
}

export async function release(cdp, x, y, button = 'left', clickCount = 1) {
  lastPos = { x, y };
  await cdp.send('Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    x,
    y,
    button,
    buttons: 0,
    clickCount,
    pointerType: 'mouse',
  });
}

export async function click(cdp, x, y, button = 'left') {
  await move(cdp, x, y);
  await press(cdp, x, y, button);
  await release(cdp, x, y, button);
}

export async function wheel(cdp, x, y, deltaY, times = 1) {
  for (let i = 0; i < times; i += 1) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x,
      y,
      deltaX: 0,
      deltaY,
      pointerType: 'mouse',
    });
    await sleep(40);
  }
}

export async function key(cdp, keyName, code = keyName, keyCode = 0) {
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyDown',
    key: keyName,
    code,
    windowsVirtualKeyCode: keyCode,
    nativeVirtualKeyCode: keyCode,
  });
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyUp',
    key: keyName,
    code,
    windowsVirtualKeyCode: keyCode,
    nativeVirtualKeyCode: keyCode,
  });
}

export async function screenshot(cdp, path, format = 'png') {
  const { data } = await cdp.send('Page.captureScreenshot', { format, captureBeyondViewport: false });
  const { writeFile } = await import('node:fs/promises');
  await writeFile(path, Buffer.from(data, 'base64'));
  return path;
}

export async function rect(cdp, selector) {
  return evaluate(
    cdp,
    `(() => { const el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
    })()`,
  );
}
