// RealMouse — small numeric helpers. No dependencies, deterministic.

export const clamp = (v, min, max) => (v < min ? min : v > max ? max : v);
export const lerp = (a, b, t) => a + (b - a) * t;
export const invLerp = (a, b, v) => (b === a ? 0 : (v - a) / (b - a));
export const smoothstep = (t) => {
  const x = clamp(t, 0, 1);
  return x * x * (3 - 2 * x);
};

/** Frame-rate independent exponential chase. lambda is 1/seconds. */
export const chase = (current, target, lambda, dt) =>
  current + (target - current) * (1 - Math.exp(-lambda * dt));

/** mulberry32 — tiny deterministic PRNG so the feel is reproducible. */
export function rng(seed = 0x9e3779b9) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Smooth 1-D value noise in [-1, 1]. */
export class Noise {
  constructor(seed = 7) {
    this.random = rng(seed);
    this.size = 512;
    this.table = new Float32Array(this.size);
    for (let i = 0; i < this.size; i += 1) this.table[i] = this.random() * 2 - 1;
  }

  sample(x) {
    const i = Math.floor(x);
    const f = x - i;
    const a = this.table[((i % this.size) + this.size) % this.size];
    const b = this.table[(((i + 1) % this.size) + this.size) % this.size];
    return lerp(a, b, smoothstep(f));
  }
}

/** Critically-damped-ish spring integrator (semi-implicit Euler). */
export class Spring {
  constructor({ stiffness = 180, damping = 26, mass = 1, value = 0 } = {}) {
    this.k = stiffness;
    this.c = damping;
    this.m = mass;
    this.x = value;
    this.v = 0;
  }

  step(target, dt) {
    const dtc = Math.min(dt, 1 / 30);
    const force = -this.k * (this.x - target) - this.c * this.v;
    this.v += (force / this.m) * dtc;
    this.x += this.v * dtc;
    return this.x;
  }

  settled(target, epsilon = 0.15, velocity = 0.6) {
    return Math.abs(this.x - target) < epsilon && Math.abs(this.v) < velocity;
  }
}

/**
 * One-Euro style low-pass used for the trace and for the assisted curve.
 * Kept separate from the chase so the feel model stays readable.
 */
export class OneEuro {
  constructor({ minCutoff = 1.2, beta = 0.02, dCutoff = 1 } = {}) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    this.xPrev = null;
    this.dxPrev = 0;
  }

  static alpha(cutoff, dt) {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(value, dt) {
    if (this.xPrev === null) {
      this.xPrev = value;
      return value;
    }
    const dx = (value - this.xPrev) / Math.max(dt, 1e-4);
    const aD = OneEuro.alpha(this.dCutoff, dt);
    this.dxPrev = this.dxPrev + aD * (dx - this.dxPrev);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dxPrev);
    const a = OneEuro.alpha(cutoff, dt);
    this.xPrev = this.xPrev + a * (value - this.xPrev);
    return this.xPrev;
  }
}

export const format = {
  int: (v) => Math.round(v).toLocaleString('en-US'),
  fixed: (v, d = 1) => Number(v).toFixed(d),
};
