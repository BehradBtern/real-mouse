// RealMouse — kinetic drag, rubber-band clamping, drop snapping, edge resize.

import { clamp, Spring } from './math.js';

const THRESHOLD = 4;
const DROP_TOLERANCE = 8;

export class DragController {
  constructor({ card, stage, dropZone, dropState, meta, dot, hint, onEvent }) {
    this.card = card;
    this.stage = stage;
    this.dropZone = dropZone;
    this.dropState = dropState;
    this.meta = meta;
    this.dot = dot;
    this.hint = hint;
    this.onEvent = onEvent || (() => {});

    this.active = false;
    this.armed = false;
    this.pointerId = null;
    this.startPointer = { x: 0, y: 0 };
    this.origin = { x: 0, y: 0 };
    this.offset = { x: 0, y: 0 };
    this.velocity = { x: 0, y: 0 };
    this.lastMove = { x: 0, y: 0, t: 0 };
    this.spring = new Spring({ stiffness: 210, damping: 24 });
    this.springY = new Spring({ stiffness: 210, damping: 24 });
    this.raf = 0;
    this.dropped = false;
    this.restRect = null;

    this.card.addEventListener('pointerdown', (event) => this.#down(event));
    this.card.addEventListener('pointermove', (event) => this.#move(event));
    this.card.addEventListener('pointerup', (event) => this.#up(event));
    this.card.addEventListener('pointercancel', (event) => this.#up(event));
    this.card.addEventListener('dragstart', (event) => event.preventDefault());
    window.addEventListener('resize', () => {
      this.restRect = null;
    });
  }

  #stageBounds() {
    const pad = 10;
    const rect = this.stage.getBoundingClientRect();
    return {
      left: rect.left + pad,
      top: rect.top + pad,
      right: rect.right - pad,
      bottom: rect.bottom - pad,
    };
  }

  #down(event) {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    this.pointerId = event.pointerId;
    this.active = false;
    this.startPointer = { x: event.clientX, y: event.clientY };
    this.lastMove = { x: event.clientX, y: event.clientY, t: performance.now() };
    this.origin = { ...this.offset };
    this.velocity = { x: 0, y: 0 };
    this.restRect = this.card.getBoundingClientRect();
    this.card.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  #move(event) {
    if (this.pointerId === null || event.pointerId !== this.pointerId) return;

    const dx = event.clientX - this.startPointer.x;
    const dy = event.clientY - this.startPointer.y;

    if (!this.active) {
      if (Math.hypot(dx, dy) < THRESHOLD) return;
      this.active = true;
      this.card.classList.add('is-dragging');
      this.card.classList.remove('is-returning', 'is-dropped');
      this.dropped = false;
      this.meta.textContent = 'dragging';
      this.dot.classList.add('dot--live');
      this.onEvent('dragstart');
    }

    const now = performance.now();
    const span = Math.max(1, now - this.lastMove.t);
    this.velocity.x = ((event.clientX - this.lastMove.x) / span) * 1000;
    this.velocity.y = ((event.clientY - this.lastMove.y) / span) * 1000;
    this.lastMove = { x: event.clientX, y: event.clientY, t: now };

    let nx = this.origin.x + dx;
    let ny = this.origin.y + dy;

    // rubber band against the stage edges
    const bounds = this.#stageBounds();
    const rect = this.restRect;
    if (rect) {
      const minX = bounds.left - rect.left;
      const maxX = bounds.right - rect.right;
      const minY = bounds.top - rect.top;
      const maxY = bounds.bottom - rect.bottom;
      nx = nx < minX ? minX + (nx - minX) * 0.3 : nx > maxX ? maxX + (nx - maxX) * 0.3 : nx;
      ny = ny < minY ? minY + (ny - minY) * 0.3 : ny > maxY ? maxY + (ny - maxY) * 0.3 : ny;
    }

    this.offset = { x: nx, y: ny };
    this.#paint();

    const armed = this.#isOverDrop();
    if (armed !== this.armed) {
      this.armed = armed;
      this.dropZone.classList.toggle('is-armed', armed);
      this.dropState.textContent = armed ? 'armed · release to drop' : 'empty · armed on drag';
    }
  }

  #isOverDrop() {
    const card = this.card.getBoundingClientRect();
    const zone = this.dropZone.getBoundingClientRect();
    const cx = card.left + card.width / 2;
    const cy = card.top + card.height / 2;
    return (
      cx > zone.left - DROP_TOLERANCE &&
      cx < zone.right + DROP_TOLERANCE &&
      cy > zone.top - DROP_TOLERANCE &&
      cy < zone.bottom + DROP_TOLERANCE
    );
  }

  #up(event) {
    if (this.pointerId === null) return;
    if (event && event.pointerId !== undefined && event.pointerId !== this.pointerId) return;
    this.card.releasePointerCapture?.(this.pointerId);
    this.pointerId = null;

    if (!this.active) return;
    this.active = false;
    this.card.classList.remove('is-dragging');

    const armed = this.#isOverDrop();
    this.armed = false;
    this.dropZone.classList.toggle('is-armed', false);

    let targetX = 0;
    let targetY = 0;

    if (armed) {
      // The card must sit fully inside the zone, so aim for the centre.
      const zone = this.dropZone.getBoundingClientRect();
      const rect = this.restRect || this.card.getBoundingClientRect();
      // targets are absolute offsets from the card's untransformed position
      targetX = zone.left + zone.width / 2 - (rect.left + rect.width / 2) + this.origin.x;
      targetY = zone.top + zone.height / 2 - (rect.top + rect.height / 2) + this.origin.y;
      this.dropped = true;
      this.dropZone.classList.add('is-filled');
      this.dropState.textContent = 'filled · card docked';
      this.card.classList.add('is-dropped');
      this.meta.textContent = 'docked';
      this.onEvent('drop');
    } else {
      this.dropZone.classList.remove('is-filled');
      this.dropState.textContent = 'empty · armed on drag';
      this.meta.textContent = 'returning';
      this.onEvent('release');
    }

    this.dot.classList.remove('dot--live');
    this.card.classList.add('is-returning');
    if (this.hint) {
      this.hint.textContent = armed ? 'docked · grab again to move' : 'spring back · friction 0.92';
    }

    this.spring.x = this.offset.x;
    this.spring.v = clamp(this.velocity.x, -2600, 2600) * 0.55;
    this.springY.x = this.offset.y;
    this.springY.v = clamp(this.velocity.y, -2600, 2600) * 0.55;
    this.#run(targetX, targetY);
  }

  #run(targetX, targetY) {
    if (this.raf) cancelAnimationFrame(this.raf);
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(0.04, (now - last) / 1000);
      last = now;

      const x = this.spring.step(targetX, dt);
      const y = this.springY.step(targetY, dt);
      this.offset = { x, y };
      this.#paint();

      const settled = this.spring.settled(targetX) && this.springY.settled(targetY);
      if (settled) {
        this.offset = { x: targetX, y: targetY };
        this.#paint();
        this.card.classList.remove('is-returning');
        this.raf = 0;
        if (!this.dropped) {
          this.meta.textContent = 'idle';
          if (this.hint) this.hint.textContent = 'threshold 4px · friction 0.92';
        }
        return;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  #paint() {
    this.card.style.transform = `translate3d(${this.offset.x.toFixed(2)}px, ${this.offset.y.toFixed(2)}px, 0)`;
  }

  reset() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.offset = { x: 0, y: 0 };
    this.velocity = { x: 0, y: 0 };
    this.dropped = false;
    this.#paint();
    this.card.classList.remove('is-dragging', 'is-dropped', 'is-returning');
    this.dropZone.classList.remove('is-armed', 'is-filled');
    this.dropState.textContent = 'empty · armed on drag';
    this.meta.textContent = 'idle';
    if (this.hint) this.hint.textContent = 'threshold 4px · friction 0.92';
  }
}

export class ResizeHandle {
  constructor({ panel, handle, readout, onEvent }) {
    this.panel = panel;
    this.handle = handle;
    this.readout = readout;
    this.onEvent = onEvent || (() => {});
    this.dragging = false;
    this.startX = 0;
    this.startWidth = 0;
    this.pointerId = null;

    handle.addEventListener('pointerdown', (event) => this.#down(event));
    handle.addEventListener('pointermove', (event) => this.#move(event));
    handle.addEventListener('pointerup', (event) => this.#up(event));
    handle.addEventListener('pointercancel', (event) => this.#up(event));
    handle.addEventListener('keydown', (event) => this.#key(event));

    this.#report();
  }

  #bounds() {
    const cell = this.panel.parentElement.getBoundingClientRect();
    return { min: 140, max: Math.max(160, cell.width - 8) };
  }

  #down(event) {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    this.dragging = true;
    this.pointerId = event.pointerId;
    this.startX = event.clientX;
    this.startWidth = this.panel.getBoundingClientRect().width;
    this.handle.setPointerCapture?.(event.pointerId);
    this.handle.classList.add('is-active');
    event.preventDefault();
  }

  #move(event) {
    if (!this.dragging || event.pointerId !== this.pointerId) return;
    const { min, max } = this.#bounds();
    const width = clamp(this.startWidth + (event.clientX - this.startX), min, max);
    this.panel.style.width = `${Math.round(width)}px`;
    this.#report();
  }

  #up(event) {
    if (!this.dragging) return;
    if (event && event.pointerId !== undefined && event.pointerId !== this.pointerId) return;
    this.dragging = false;
    this.handle.releasePointerCapture?.(this.pointerId);
    this.pointerId = null;
    this.handle.classList.remove('is-active');
    this.onEvent('resize', this.panel.getBoundingClientRect().width);
  }

  #key(event) {
    const { min, max } = this.#bounds();
    const step = event.shiftKey ? 32 : 8;
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const width = this.panel.getBoundingClientRect().width;
    const next = clamp(width + (event.key === 'ArrowRight' ? step : -step), min, max);
    this.panel.style.width = `${Math.round(next)}px`;
    this.#report();
    this.onEvent('resize', next);
  }

  #report() {
    const width = this.panel.getBoundingClientRect().width;
    const cell = this.panel.parentElement.getBoundingClientRect().width;
    const pct = cell ? Math.round((width / cell) * 100) : 100;
    this.readout.textContent = `width ${Math.round(width)}px · ${pct}%`;
  }
}
