// RealMouse — measured telemetry. Nothing here is decorative: every value is
// sampled from the live loop and throttled to 4Hz before touching the DOM.

import { clamp } from './math.js';

const TRACE_POINTS = 220;

export class Telemetry {
  constructor({ engine, els, traceCanvas, traceWrap, traceToggle, onToggle }) {
    this.engine = engine;
    this.els = els;
    this.canvas = traceCanvas;
    this.wrap = traceWrap;
    this.ctx = traceCanvas?.getContext('2d') || null;
    this.traceEnabled = true;
    this.onToggle = onToggle || (() => {});

    this.frameTimes = [];
    this.lastFrameAt = 0;
    this.lastPublishAt = 0;
    this.lastEventCount = 0;
    this.lastEventAt = performance.now();
    this.rate = 0;
    this.points = [];
    this.dropped = 0;
    this.paintLatency = 0;
    this.medianFrame = 16.7;
    this.fps = 60;

    this.traceToggle = traceToggle;
    traceToggle?.addEventListener('click', () => {
      this.setTrace(!this.traceEnabled);
      this.onToggle(this.traceEnabled);
    });

    this.#resize();
    window.addEventListener('resize', () => this.#resize());
  }

  setTrace(enabled) {
    this.traceEnabled = Boolean(enabled);
    if (this.wrap) this.wrap.hidden = !this.traceEnabled;
    if (this.traceToggle) {
      this.traceToggle.setAttribute('aria-pressed', String(this.traceEnabled));
      this.traceToggle.textContent = this.traceEnabled ? 'trace · on' : 'trace · off';
    }
  }

  #resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    this.ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.width = rect.width;
    this.height = rect.height;
  }

  frame(now, pos) {
    if (this.lastFrameAt) {
      const dt = now - this.lastFrameAt;
      this.frameTimes.push(dt);
      if (this.frameTimes.length > 120) this.frameTimes.shift();
      if (dt > 34) this.dropped += 1;
    }
    this.lastFrameAt = now;

    const engine = this.engine;
    this.paintLatency = engine.lastPaintLatency || 0;

    if (this.traceEnabled) {
      this.points.push({ x: pos.x, y: pos.y, t: now });
      if (this.points.length > TRACE_POINTS) this.points.shift();
    }

    if (now - this.lastPublishAt > 250) {
      this.#publish(now);
      this.lastPublishAt = now;
    }
    if (this.traceEnabled) this.#draw();
  }

  #publish(now) {
    const times = this.frameTimes;
    if (times.length) {
      const sorted = [...times].sort((a, b) => a - b);
      this.medianFrame = sorted[Math.floor(sorted.length / 2)];
      this.fps = 1000 / Math.max(1, this.medianFrame);
    }

    const span = (now - this.lastEventAt) / 1000;
    if (span > 0.25) {
      this.rate = (this.engine.eventCount - this.lastEventCount) / span;
      this.lastEventCount = this.engine.eventCount;
      this.lastEventAt = now;
    }

    const e = this.els;
    if (e.fps) e.fps.textContent = String(Math.round(this.fps));
    if (e.frame) e.frame.innerHTML = `${this.medianFrame.toFixed(1)}<small>ms</small>`;
    if (e.latency) e.latency.innerHTML = `${this.paintLatency.toFixed(1)}<small>ms</small>`;
    if (e.dropped) e.dropped.textContent = String(this.dropped);
    if (e.events) e.events.innerHTML = `${Math.round(this.rate)}<small>/s</small>`;
    if (e.travel) e.travel.innerHTML = `${Math.round(this.engine.distance)}<small>px</small>`;
    if (e.chipFps) e.chipFps.textContent = String(Math.round(this.fps));
    if (e.chipLatency) e.chipLatency.textContent = `${this.paintLatency.toFixed(0)} ms`;
  }

  #draw() {
    const ctx = this.ctx;
    if (!ctx || !this.width) return;
    const { width, height } = this;

    ctx.clearRect(0, 0, width, height);
    if (this.points.length < 2) return;

    const xs = this.points.map((p) => p.x);
    const ys = this.points.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const pad = 4;
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY, 3.2);

    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;

    ctx.beginPath();
    this.points.forEach((p, index) => {
      const x = offsetX + (p.x - minX) * scale;
      const y = offsetY + (p.y - minY) * scale;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = 'rgba(168, 70, 28, 0.55)';
    ctx.lineWidth = 1;
    ctx.lineJoin = 'round';
    ctx.stroke();

    const lastPoint = this.points[this.points.length - 1];
    const lx = offsetX + (lastPoint.x - minX) * scale;
    const ly = offsetY + (lastPoint.y - minY) * scale;
    ctx.beginPath();
    ctx.arc(lx, ly, 1.8, 0, Math.PI * 2);
    ctx.fillStyle = '#a8461c';
    ctx.fill();
  }

  reset() {
    this.frameTimes.length = 0;
    this.points.length = 0;
    this.dropped = 0;
    this.lastFrameAt = 0;
    this.#draw();
  }

  /** Compact snapshot used by the QA harness. */
  snapshot() {
    return {
      fps: Number(this.fps.toFixed(1)),
      medianFrame: Number(this.medianFrame.toFixed(2)),
      inputToPaint: Number(this.paintLatency.toFixed(2)),
      dropped: this.dropped,
      eventsPerSecond: Number(this.rate.toFixed(1)),
      travel: Math.round(this.engine.distance),
      clicks: this.engine.clicks,
      state: this.engine.state,
      coalesced: clamp(
        this.engine.eventCount ? this.engine.coalescedCount / this.engine.eventCount : 1,
        0,
        8,
      ),
    };
  }
}
