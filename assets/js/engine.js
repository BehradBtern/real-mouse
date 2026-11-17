// RealMouse — the motion engine.
//
// Model: the drawn pointer chases the true pointer position through a
// frame-rate independent exponential filter whose rate (lambda) is a function
// of response weight, smoothing and instantaneous speed. Direct mode bypasses
// the filter entirely, so the cursor lands exactly under the pointer.
//
//   lambda = (60 + 300 * weightNorm) * (1 - 0.7 * smoothingNorm) * (1 + 0.6 * speedNorm)
//
// Everything below is measured: velocity, coalesced ratio, input→paint latency.

import { clamp, chase } from './math.js';

const CURSOR_STATES = {
  pointer: 'pointer',
  text: 'text',
  grab: 'grab',
  grabbing: 'grabbing',
  'ew-resize': 'resize',
  'ns-resize': 'resize',
  'col-resize': 'resize',
  'row-resize': 'resize',
  'nesw-resize': 'resize',
  'nwse-resize': 'resize',
  'not-allowed': 'not-allowed',
  crosshair: 'arrow',
  'cell': 'arrow',
  default: 'arrow',
  auto: 'arrow',
  none: 'arrow',
};

const SAMPLE_WINDOW = 120; // ms of motion used for velocity

export class PointerEngine {
  constructor({ settings, cursor, onHover }) {
    this.settings = settings;
    this.cursor = cursor;
    this.onHover = onHover || (() => {});

    this.x = window.innerWidth / 2;
    this.y = window.innerHeight / 2;
    this.tx = this.x;
    this.ty = this.y;
    this.seeded = false;

    this.offsetX = 0;
    this.offsetY = 0;

    this.samples = [];
    this.speed = 0;
    this.vx = 0;
    this.vy = 0;

    this.lastEventAt = 0;
    this.lastSampleAt = 0;
    this.firstEventAt = 0;
    this.eventCount = 0;
    this.coalescedCount = 0;
    this.moveEvents = 0;
    this.distance = 0;
    this.clicks = 0;

    this.pressed = false;
    this.state = 'arrow';
    this.stateTarget = null;
    this.stateAt = 0;

    this.hoverTargets = [];
    this.hoverTargetsAt = 0;
    this.magnetX = 0;
    this.magnetY = 0;

    this.enabled = true;
    this.lockState = false;
    this.reduced = false;
    this.qa = false;
    this.dragActive = false;
    this.frameCount = 0;
    this.prevFrameAt = 0;
    this.lastFrameAt = 0;
    this.lastPaintLatency = 0;

    this.#bind();
  }

  #bind() {
    this.onRaw = (event) => this.#ingest(event, true);
    this.onMove = (event) => {
      if (this.rawSupported) return;
      this.#ingest(event, false);
    };

    this.rawSupported = 'onpointerrawupdate' in window;
    if (this.rawSupported) {
      window.addEventListener('pointerrawupdate', this.onRaw, { passive: true });
      // Some engines fire raw updates only for touch/stylus; keep a light
      // pointermove listener as a safety net without double counting.
      window.addEventListener('pointermove', (event) => {
        if (event.pointerType !== 'mouse') this.#ingest(event, false);
      }, { passive: true });
    } else {
      window.addEventListener('pointermove', this.onMove, { passive: true });
    }

    window.addEventListener('pointerdown', (event) => this.#down(event), { passive: true });
    window.addEventListener('pointerup', (event) => this.#up(event), { passive: true });
    window.addEventListener('pointercancel', () => this.#up({ button: 0 }), { passive: true });
    window.addEventListener('blur', () => {
      this.pressed = false;
      this.cursor.setPressed(false);
    });

    // A real pointer disappears when it leaves the screen; so does this one.
    document.addEventListener('mouseleave', () => this.cursor.setHidden(true));
    document.addEventListener('mouseenter', () => this.cursor.setHidden(false));
  }

  #ingest(event, raw) {
    if (!this.enabled) return;
    const samples = raw && typeof event.getCoalescedEvents === 'function'
      ? event.getCoalescedEvents()
      : null;

    this.eventCount += 1;
    this.moveEvents += 1;

    if (samples && samples.length) {
      this.coalescedCount += samples.length;
      for (const sample of samples) {
        this.#push(sample.clientX, sample.clientY, sample.timeStamp || performance.now());
      }
    } else {
      this.coalescedCount += 1;
      this.#push(event.clientX, event.clientY, event.timeStamp || performance.now());
    }
  }

  #push(x, y, t) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    this.tx = x;
    this.ty = y;
    this.lastEventAt = t;
    if (!this.firstEventAt) this.firstEventAt = t;

    if (!this.seeded) {
      this.x = x;
      this.y = y;
      this.seeded = true;
    }

    const last = this.samples[this.samples.length - 1];
    if (last) {
      const dx = x - last.x;
      const dy = y - last.y;
      this.distance += Math.hypot(dx, dy);
    }
    this.samples.push({ x, y, t });
    if (this.samples.length > 96) this.samples.shift();
  }

  #down(event) {
    this.clicks += 1;
    this.pressed = true;
    this.cursor.setPressed(true);
    this.cursor.fireRing();
    if (event && Number.isFinite(event.clientX) && !this.seeded) {
      this.#push(event.clientX, event.clientY, event.timeStamp || performance.now());
    }
  }

  #up() {
    this.pressed = false;
    this.cursor.setPressed(false);
  }

  /** Relative movement used by the touch trackpad. */
  nudge(dx, dy) {
    this.offsetX += dx;
    this.offsetY += dy;
    const maxX = window.innerWidth;
    const maxY = window.innerHeight;
    this.offsetX = clamp(this.offsetX, -maxX, maxX);
    this.offsetY = clamp(this.offsetY, -maxY, maxY);
  }

  nudgeReset() {
    this.offsetX = 0;
    this.offsetY = 0;
  }

  /** Deterministic placement for QA and screenshots. */
  setPosition(x, y) {
    this.x = x;
    this.y = y;
    this.tx = x;
    this.ty = y;
    this.seeded = true;
    this.offsetX = 0;
    this.offsetY = 0;
    this.samples.length = 0;
  }

  setState(name) {
    this.state = name;
    this.cursor.setState(name);
  }

  #evaluateState() {
    if (!this.seeded) return;
    const el = document.elementFromPoint(
      clamp(this.x, 0, window.innerWidth - 1),
      clamp(this.y, 0, window.innerHeight - 1),
    );
    if (!el) return;

    const attr = el.closest('[data-cursor]')?.dataset.cursor;
    let next = 'arrow';

    if (attr) {
      next = attr;
    } else {
      const computed = window.getComputedStyle(el).cursor || 'auto';
      next = CURSOR_STATES[computed] || 'arrow';
    }

    if (this.pressed && (next === 'grab' || next === 'pointer')) next = 'grabbing';
    if (this.pressed && next === 'arrow' && this.dragActive) next = 'grabbing';

    if (next !== this.state) {
      this.state = next;
      this.cursor.setState(next);
      const target = el.closest('a,button,input,textarea,select,[role="button"],[data-cursor]');
      if (target && target !== this.stateTarget) {
        this.stateTarget = target;
        this.onHover(target, next);
      }
    } else if (this.stateTarget && !this.stateTarget.isConnected) {
      this.stateTarget = null;
    }
  }

  /** Cache hit rectangles so magnetism never reads layout inside the frame. */
  #refreshTargets(now) {
    if (now - this.hoverTargetsAt < 400) return;
    this.hoverTargetsAt = now;
    const nodes = document.querySelectorAll(
      'a,button,input,textarea,select,[role="button"],[data-cursor],.segmented__btn,.timing__target',
    );
    const list = [];
    for (const node of nodes) {
      const rect = node.getBoundingClientRect();
      if (rect.width < 4 || rect.height < 4) continue;
      if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
      list.push({
        node,
        cx: rect.left + rect.width / 2,
        cy: rect.top + rect.height / 2,
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
      });
    }
    this.hoverTargets = list;
  }

  #magnetism() {
    this.magnetX = 0;
    this.magnetY = 0;
    if (!this.settings.magnet || this.settings.mode === 'direct' || this.pressed) return;

    const reach = 10;
    let best = null;
    let bestDist = Infinity;
    for (const target of this.hoverTargets) {
      if (this.x < target.left - reach || this.x > target.right + reach) continue;
      if (this.y < target.top - reach || this.y > target.bottom + reach) continue;
      const dist = Math.hypot(target.cx - this.x, target.cy - this.y);
      if (dist < bestDist) {
        bestDist = dist;
        best = target;
      }
    }
    if (!best) return;

    const dx = best.cx - this.x;
    const dy = best.cy - this.y;
    const length = Math.hypot(dx, dy) || 1;
    const pull = Math.min(3, length * 0.22);
    this.magnetX = (dx / length) * pull;
    this.magnetY = (dy / length) * pull;
  }

  #tremor(now) {
    const amplitude = this.settings.mode === 'direct' || this.qa ? 0 : this.settings.tremor;
    if (!amplitude || this.reduced) return { x: 0, y: 0 };
    const t = now / 1000;
    const still = now - this.lastEventAt > 400;
    const gain = still ? 0.35 : 1;
    const ax = Math.sin(t * 11.3) * 0.6 + Math.sin(t * 3.7 + 1.2) * 0.4;
    const ay = Math.cos(t * 9.1 + 0.4) * 0.6 + Math.cos(t * 4.3 + 2.1) * 0.4;
    return { x: ax * amplitude * gain, y: ay * amplitude * gain };
  }

  frame(now, dt) {
    this.frameCount += 1;
    const hadInput = this.lastEventAt > this.prevFrameAt;

    // velocity over the trailing sample window
    const cutoff = now - SAMPLE_WINDOW;
    while (this.samples.length > 2 && this.samples[0].t < cutoff) this.samples.shift();
    const first = this.samples[0];
    const last = this.samples[this.samples.length - 1];
    if (first && last && last.t > first.t) {
      const span = last.t - first.t;
      this.vx = (last.x - first.x) / span;
      this.vy = (last.y - first.y) / span;
      this.speed = Math.hypot(this.vx, this.vy);
    } else {
      this.speed = 0;
    }

    const targetX = this.tx + this.offsetX;
    const targetY = this.ty + this.offsetY;

    if (!this.enabled) return { x: this.x, y: this.y };

    if (this.settings.mode === 'direct') {
      this.x = targetX;
      this.y = targetY;
    } else {
      const weightNorm = clamp((this.settings.weight - 0.4) / 2.6, 0, 1);
      const smoothNorm = clamp(this.settings.smoothing / 100, 0, 1);
      const speedNorm = clamp(this.speed / 1.5, 0, 1);
      const lambda =
        (60 + 300 * weightNorm) *
        (1 - 0.7 * smoothNorm) *
        (1 + 0.6 * speedNorm) *
        (this.reduced ? 0.45 : 1);

      this.x = chase(this.x, targetX, lambda, dt);
      this.y = chase(this.y, targetY, lambda, dt);
    }

    this.x = clamp(this.x, 0, window.innerWidth - 1);
    this.y = clamp(this.y, 0, window.innerHeight - 1);

    // offset from the touch trackpad decays once a real pointer moves again
    if (this.offsetX || this.offsetY) {
      const decay = Math.exp(-dt * 14);
      if (this.speed > 0.02) {
        this.offsetX *= decay;
        this.offsetY *= decay;
      }
    }

    this.#refreshTargets(now);
    this.#magnetism();
    if (!this.lockState) this.#evaluateState();

    const tremor = this.#tremor(now);
    const renderX = this.x + this.magnetX + tremor.x;
    const renderY = this.y + this.magnetY + tremor.y;

    this.cursor.render(renderX, renderY);

    if (hadInput) {
      // Only frames that actually consumed a fresh sample report a latency;
      // otherwise the number would grow while the pointer sits still.
      const latency = now - this.lastEventAt;
      if (latency >= 0 && latency < 100) this.lastPaintLatency = latency;
    }
    this.prevFrameAt = now;

    return { x: renderX, y: renderY };
  }
}
