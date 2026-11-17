// RealMouse — wheel feel: detents, trackpad detection, rubber-band overscroll.
//
// A real wheel does not emit pixels, it emits notches. We classify the device
// from the event rhythm (fast, small deltas = trackpad) and either snap to a
// 100px detent grid or integrate continuously with momentum.

import { clamp, chase } from './math.js';

const DETENT = 100;
const RUBBER = 0.32;

export class WheelWell {
  constructor({ well, inner, thumb, onDetent, onEdge }) {
    this.well = well;
    this.inner = inner;
    this.thumb = thumb;
    this.onDetent = onDetent || (() => {});
    this.onEdge = onEdge || (() => {});

    this.current = 0;
    this.target = 0;
    this.velocity = 0;
    this.maxScroll = 0;
    this.detents = 0;
    this.lastWheelAt = 0;
    this.lastDelta = 0;
    this.trackpad = false;
    this.lastNotchIndex = 0;
    this.raf = 0;

    this.#measure();
    this.well.addEventListener('wheel', (event) => this.#onWheel(event), { passive: false });
    this.well.addEventListener('keydown', (event) => this.#onKey(event));
    window.addEventListener('resize', () => this.#measure());
    this.#paint();
  }

  #measure() {
    this.maxScroll = Math.max(0, this.inner.scrollHeight - this.well.clientHeight);
    const trackHeight = Math.max(0, this.well.clientHeight - 16);
    const thumbHeight = this.maxScroll > 0
      ? Math.max(28, (this.well.clientHeight / this.inner.scrollHeight) * trackHeight)
      : trackHeight;
    if (this.thumb) this.thumb.style.height = `${thumbHeight}px`;
    this.trackHeight = trackHeight;
    this.thumbHeight = thumbHeight;
  }

  #normalize(event) {
    const mode = event.deltaMode;
    if (mode === 1) return event.deltaY * 16;
    if (mode === 2) return event.deltaY * this.well.clientHeight;
    return event.deltaY;
  }

  #onWheel(event) {
    event.preventDefault();
    const now = performance.now();
    const delta = this.#normalize(event);
    const gap = now - this.lastWheelAt;
    const magnitude = Math.abs(delta);

    // Trackpads stream many small deltas; wheels arrive as sharp spikes.
    if (gap < 30 && magnitude < 40) this.trackpad = true;
    else if (gap > 90 || magnitude > 60) this.trackpad = false;

    this.lastWheelAt = now;
    this.lastDelta = delta;

    if (this.trackpad) {
      this.target = clamp(this.target - delta, -this.maxScroll - 140, 140);
    } else {
      const notches = Math.max(1, Math.round(magnitude / 100));
      const direction = Math.sign(delta) || 1;
      this.target = this.target - direction * notches * DETENT;
      const index = Math.round(this.target / DETENT);
      if (index !== this.lastNotchIndex) {
        this.lastNotchIndex = index;
        this.detents += 1;
        this.onDetent(notches);
      }
    }

    // Rubber band: the further past the edge, the harder it resists.
    const overTop = this.target > 0 ? this.target : 0;
    const overBottom = this.target < -this.maxScroll ? -this.maxScroll - this.target : 0;
    if (overTop) this.target = overTop * RUBBER;
    if (overBottom) this.target = -this.maxScroll - overBottom * RUBBER;

    this.#start();
  }

  #onKey(event) {
    const keys = ['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' '];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const step = event.key === 'PageDown' || event.key === 'PageUp' ? this.well.clientHeight * 0.9 : 48;

    if (event.key === 'ArrowDown' || event.key === 'PageDown' || event.key === ' ') {
      this.target = clamp(this.target - step, -this.maxScroll, 0);
    } else if (event.key === 'ArrowUp' || event.key === 'PageUp') {
      this.target = clamp(this.target + step, -this.maxScroll, 0);
    } else if (event.key === 'Home') {
      this.target = 0;
    } else if (event.key === 'End') {
      this.target = -this.maxScroll;
    }
    this.target = clamp(this.target, -this.maxScroll, 0);
    this.detents += 1;
    this.onDetent(1);
    this.#start();
  }

  #start() {
    if (this.raf) return;
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;

      const stiffness = this.trackpad ? 26 : 19;
      this.current = chase(this.current, this.target, stiffness, dt);

      // return to the legal band when the overscroll input stops
      if (this.lastWheelAt && now - this.lastWheelAt > 120) {
        if (this.target > 0) this.target = chase(this.target, 0, 14, dt);
        if (this.target < -this.maxScroll) {
          this.target = chase(this.target, -this.maxScroll, 14, dt);
        }
      }

      this.#paint();

      const settled =
        Math.abs(this.current - this.target) < 0.2 &&
        now - this.lastWheelAt > 180 &&
        this.target >= -this.maxScroll - 0.5 &&
        this.target <= 0.5;

      if (settled) {
        this.current = this.target;
        this.#paint();
        this.raf = 0;
        return;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  #paint() {
    this.inner.style.transform = `translate3d(0, ${this.current.toFixed(2)}px, 0)`;
    if (this.thumb) {
      const progress = this.maxScroll > 0 ? clamp(-this.current / this.maxScroll, 0, 1) : 0;
      const travel = Math.max(0, this.trackHeight - this.thumbHeight);
      this.thumb.style.transform = `translateY(${(progress * travel).toFixed(1)}px)`;
    }
  }

  /** Page-level affordance: scroll the document too when the well is at an edge. */
  get scrollTop() {
    return -this.current;
  }

  reset() {
    this.current = 0;
    this.target = 0;
    this.detents = 0;
    this.lastNotchIndex = 0;
    this.#paint();
  }
}
