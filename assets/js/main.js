// RealMouse — application wiring.

import { DEFAULTS, createStore } from './settings.js';
import { Cursor } from './cursor.js';
import { PointerEngine } from './engine.js';
import { Sound } from './audio.js';
import { Telemetry } from './telemetry.js';
import { WheelWell } from './wheel.js';
import { DragController, ResizeHandle } from './drag.js';
import { ContextMenu } from './menu.js';
import { TouchPad } from './touch.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);
const QA = params.get('qa') === '1';

const store = createStore();
const announcer = $('announcer');
const announce = (text) => {
  if (!announcer) return;
  announcer.textContent = '';
  window.setTimeout(() => {
    announcer.textContent = text;
  }, 30);
};

const sound = new Sound({ enabled: store.get().sound, volume: store.get().volume });
const cursor = new Cursor(document);
cursor.setSize(store.get().size);

const engine = new PointerEngine({
  settings: store.get(),
  cursor,
  onHover: (_target, state) => {
    if (state === 'pointer' && store.get().sound) sound.hover();
  },
});

/* ---------------- stage controllers ---------------- */

const well = new WheelWell({
  well: $('well'),
  inner: $('wellInner'),
  thumb: $('wellThumb'),
  onDetent: (count) => {
    sound.tick(Math.min(1, count));
    const meta = $('scrollMeta');
    if (meta) meta.textContent = `${well.detents} notch${well.detents === 1 ? '' : 'es'}`;
  },
});

const drag = new DragController({
  card: $('dragCard'),
  stage: $('stage'),
  dropZone: $('dropZone'),
  dropState: $('dropState'),
  meta: $('dragMeta'),
  dot: $('dragDot'),
  hint: $('dragHintText'),
  onEvent: (type) => {
    engine.dragActive = type === 'dragstart';
    if (type === 'dragstart') sound.tick(0.6);
    if (type === 'drop') {
      sound.click(0.8);
      announce('Card docked in the drop target.');
    }
    if (type === 'release') announce('Card released outside the target, returning.');
  },
});

const resize = new ResizeHandle({
  panel: $('resizePanel'),
  handle: $('resizeHandle'),
  readout: $('resizeReadout'),
  onEvent: () => sound.tick(0.5),
});

const menu = new ContextMenu({
  el: $('menu'),
  onAction: (action) => {
    if (action === 'copy') {
      const text = `${engine.x.toFixed(0)}, ${engine.y.toFixed(0)}`;
      navigator.clipboard?.writeText(text).then(
        () => announce(`Cursor position ${text} copied.`),
        () => announce('Clipboard unavailable.'),
      );
    } else if (action === 'recalibrate') {
      engine.samples.length = 0;
      engine.nudgeReset();
      announce('Pointer recalibrated.');
    } else if (action === 'reset') {
      applyReset();
    }
  },
});

const telemetry = new Telemetry({
  engine,
  els: {
    fps: $('mFps'),
    frame: $('mFrame'),
    latency: $('mLatency'),
    dropped: $('mDropped'),
    events: $('mEvents'),
    travel: $('mTravel'),
    chipFps: $('chipFps'),
    chipLatency: $('chipLatency'),
  },
  traceCanvas: $('trace'),
  traceWrap: $('traceWrap'),
  traceToggle: $('traceToggle'),
  onToggle: (enabled) => store.set({ trace: enabled }),
});

/* ---------------- settings → UI ---------------- */

const controls = {
  assisted: $('modeAssisted'),
  direct: $('modeDirect'),
  weight: $('setSensitivity'),
  weightVal: $('valSensitivity'),
  smoothing: $('setSmooth'),
  smoothingVal: $('valSmooth'),
  tremor: $('setTremor'),
  tremorVal: $('valTremor'),
  size: $('setSize'),
  sizeVal: $('valSize'),
  volume: $('setVolume'),
  volumeVal: $('valVolume'),
  magnet: $('swMagnet'),
  haptics: $('swHaptics'),
  sound: $('swSound'),
  system: $('swSystem'),
  modeVal: $('modeVal'),
};

function fillTrack(input) {
  if (!input) return;
  const min = Number(input.min);
  const max = Number(input.max);
  const value = Number(input.value);
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
  input.style.setProperty('--fill', `${pct}%`);
}

function syncControls(settings) {
  if (controls.assisted) controls.assisted.setAttribute('aria-pressed', String(settings.mode === 'assisted'));
  if (controls.direct) controls.direct.setAttribute('aria-pressed', String(settings.mode === 'direct'));
  if (controls.modeVal) controls.modeVal.textContent = settings.mode === 'direct' ? 'direct 1:1' : 'assisted';

  if (controls.weight) controls.weight.value = String(settings.weight);
  if (controls.weightVal) controls.weightVal.textContent = `${settings.weight.toFixed(2)}×`;

  if (controls.smoothing) controls.smoothing.value = String(settings.smoothing);
  if (controls.smoothingVal) controls.smoothingVal.textContent = String(Math.round(settings.smoothing));

  if (controls.tremor) controls.tremor.value = String(settings.tremor);
  if (controls.tremorVal) controls.tremorVal.textContent = `${settings.tremor.toFixed(2)}px`;

  if (controls.size) controls.size.value = String(settings.size);
  if (controls.sizeVal) controls.sizeVal.textContent = `${Math.round(settings.size)}px`;

  if (controls.volume) controls.volume.value = String(settings.volume);
  if (controls.volumeVal) controls.volumeVal.textContent = String(Math.round(settings.volume));

  if (controls.magnet) controls.magnet.checked = settings.magnet;
  if (controls.haptics) controls.haptics.checked = settings.haptics;
  if (controls.sound) controls.sound.checked = settings.sound;
  if (controls.system) controls.system.checked = settings.system;

  for (const input of [controls.weight, controls.smoothing, controls.tremor, controls.size, controls.volume]) {
    fillTrack(input);
  }
}

function applySettings(settings) {
  engine.settings = settings;
  cursor.setSize(settings.size);
  sound.setEnabled(settings.sound && !QA);
  sound.setVolume(settings.volume);

  const custom = !settings.system;
  document.body.classList.toggle('rm-custom-cursor', custom);
  document.body.classList.toggle('rm-system-cursor', !custom);
  if (!custom) cursor.setVisible(false);
}

syncControls(store.get());
applySettings(store.get());

store.subscribe((state) => {
  applySettings(state);
  syncControls(state);
});

/* ---------------- control events ---------------- */

const bindRange = (input, key, transform = Number) => {
  if (!input) return;
  input.addEventListener('input', () => {
    const value = transform(input.value);
    store.set({ [key]: value });
    fillTrack(input);
  });
};

bindRange(controls.weight, 'weight');
bindRange(controls.smoothing, 'smoothing');
bindRange(controls.tremor, 'tremor');
bindRange(controls.size, 'size');
bindRange(controls.volume, 'volume');

controls.assisted?.addEventListener('click', () => store.set({ mode: 'assisted' }));
controls.direct?.addEventListener('click', () => store.set({ mode: 'direct' }));
controls.magnet?.addEventListener('change', () => store.set({ magnet: controls.magnet.checked }));
controls.haptics?.addEventListener('change', () => store.set({ haptics: controls.haptics.checked }));
controls.sound?.addEventListener('change', () => {
  store.set({ sound: controls.sound.checked });
  if (controls.sound.checked) sound.unlock();
});
controls.system?.addEventListener('change', () => store.set({ system: controls.system.checked }));

function applyReset() {
  store.reset();
  well.reset();
  drag.reset();
  telemetry.reset();
  engine.nudgeReset();
  announce('Feel settings restored to defaults.');
}

$('btnReset')?.addEventListener('click', applyReset);
$('btnCalm')?.addEventListener('click', () => {
  store.set({ smoothing: 55, tremor: 0, magnet: false, mode: 'assisted' });
  announce('Calm motion applied: heavy smoothing, no tremor, no magnetism.');
});

/* ---------------- stage interactions ---------------- */

let primaryCount = 0;
const btnPrimary = $('btnPrimary');
btnPrimary?.addEventListener('click', () => {
  primaryCount += 1;
  const label = $('btnCount');
  if (label) {
    label.textContent = String(primaryCount);
    label.setAttribute('aria-label', `${primaryCount} presses`);
  }
  btnPrimary.classList.add('is-pressed');
  window.setTimeout(() => btnPrimary.classList.remove('is-pressed'), 140);
  if (store.get().haptics) navigator.vibrate?.(8);
  announce(`Primary button pressed ${primaryCount} time${primaryCount === 1 ? '' : 's'}.`);
});

$('btnSecondary')?.addEventListener('click', () => {
  if (store.get().haptics) navigator.vibrate?.(5);
  announce('Secondary button pressed.');
});

let dblCount = 0;
$('dblTarget')?.addEventListener('dblclick', () => {
  dblCount += 1;
  const el = $('dblCount');
  if (el) el.textContent = String(dblCount);
  if (store.get().haptics) navigator.vibrate?.([6, 20, 6]);
  announce(`Double-click registered: ${dblCount}.`);
});

let ctxCount = 0;
const ctxTarget = $('ctxTarget');
const openMenuAt = (x, y) => {
  ctxCount += 1;
  const el = $('ctxCount');
  if (el) el.textContent = String(ctxCount);
  menu.show(x, y);
};

ctxTarget?.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  openMenuAt(event.clientX, event.clientY);
});

$('stage')?.addEventListener('contextmenu', (event) => {
  const tag = event.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (event.target.closest('#ctxTarget')) return;
  event.preventDefault();
  openMenuAt(event.clientX, event.clientY);
});

/* ---------------- typing readouts ---------------- */

const inputDemo = $('inputDemo');
const caretReadout = $('caretReadout');
const textareaDemo = $('textareaDemo');

inputDemo?.addEventListener('focus', () => {
  if (caretReadout) caretReadout.textContent = 'focused';
});
inputDemo?.addEventListener('blur', () => {
  if (caretReadout) caretReadout.textContent = 'idle';
});
inputDemo?.addEventListener('input', () => {
  if (caretReadout) caretReadout.textContent = `${inputDemo.value.length} chars`;
});
textareaDemo?.addEventListener('focus', () => {
  if (caretReadout) caretReadout.textContent = 'note focused';
});

/* ---------------- input → paint latency on click ---------------- */

let clickStamp = 0;
window.addEventListener('pointerdown', (event) => {
  clickStamp = event.timeStamp || performance.now();
  sound.unlock();
  if (event.button === 0 || event.pointerType !== 'mouse') sound.click(event.pointerType === 'mouse' ? 0.85 : 0.6);
  if (store.get().haptics && event.pointerType === 'touch') navigator.vibrate?.(4);
}, { passive: true });

window.addEventListener('keydown', () => sound.unlock(), { passive: true });

/* ---------------- keyboard shortcuts ---------------- */

window.addEventListener('keydown', (event) => {
  const tag = document.activeElement?.tagName;
  const typing = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable;

  if (event.key === 'Escape') {
    menu.close('escape');
    return;
  }
  if (typing) return;

  if (event.key === '1') {
    store.set({ mode: 'direct' });
    announce('Direct 1:1 mode.');
  } else if (event.key === '2') {
    store.set({ mode: 'assisted' });
    announce('Assisted curve mode.');
  } else if (event.key.toLowerCase() === 't') {
    telemetry.setTrace(!telemetry.traceEnabled);
    store.set({ trace: telemetry.traceEnabled });
  } else if (event.key.toLowerCase() === 'r' && !event.shiftKey) {
    applyReset();
  } else if (event.key === 'R' && event.shiftKey) {
    applyReset();
  }
});

/* ---------------- touch trackpad ---------------- */

const coarse = window.matchMedia('(pointer: coarse)');
const trackpadEl = $('trackpad');

const touch = new TouchPad({
  el: trackpadEl,
  engine,
  onTap: (x, y) => {
    const target = document.elementFromPoint(x, y);
    if (!target) return;
    if (target.matches('input,textarea')) target.focus();
    target.dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window }),
    );
    if (store.get().haptics) navigator.vibrate?.(6);
  },
  onLongPress: (x, y) => {
    const target = document.elementFromPoint(x, y);
    target?.dispatchEvent(
      new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window }),
    );
    if (store.get().haptics) navigator.vibrate?.(12);
  },
});

function syncTrackpad() {
  if (!trackpadEl) return;
  const show = coarse.matches || 'ontouchstart' in window;
  trackpadEl.classList.toggle('is-visible', show);
  document.body.classList.toggle('has-trackpad', show);
}

syncTrackpad();
coarse.addEventListener?.('change', syncTrackpad);

/* ---------------- reduced motion ---------------- */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
engine.reduced = reduceMotion.matches;
reduceMotion.addEventListener?.('change', (event) => {
  engine.reduced = event.matches;
});

engine.qa = QA;
if (QA) {
  sound.setEnabled(false);
}

/* ---------------- the single animation loop ---------------- */

let lastFrame = performance.now();

function loop(now) {
  const dt = Math.min(0.05, Math.max(0.0001, (now - lastFrame) / 1000));
  lastFrame = now;

  const pos = engine.frame(now, dt);
  telemetry.frame(now, pos);

  if (clickStamp) {
    const measured = now - clickStamp;
    if (measured >= 0 && measured < 200) {
      const el = $('clickLatency');
      if (el) el.textContent = `${measured.toFixed(1)} ms`;
    }
    clickStamp = 0;
  }

  requestAnimationFrame(loop);
}

requestAnimationFrame((now) => {
  lastFrame = now;
  engine.frame(now, 1 / 60);
  telemetry.frame(now, { x: engine.x, y: engine.y });
  requestAnimationFrame(loop);
});

/* ---------------- QA surface ---------------- */

window.__mouse = {
  version: '1.0.0',
  qa: QA,
  engine,
  store,
  telemetry,
  cursor,
  well,
  drag,
  setPos(x, y) {
    engine.setPosition(x, y);
    engine.frame(performance.now(), 1 / 60);
    telemetry.frame(performance.now(), { x, y });
  },
  setState(name) {
    engine.lockState = true;
    engine.setState(name);
  },
  releaseState() {
    engine.lockState = false;
  },
  snapshot() {
    return {
      ...telemetry.snapshot(),
      settings: store.get(),
      position: { x: Number(engine.x.toFixed(2)), y: Number(engine.y.toFixed(2)) },
      ready: true,
    };
  },
};
