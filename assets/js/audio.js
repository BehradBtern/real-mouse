// RealMouse — synthesised click/tick feedback. No audio files, no network.
// The AudioContext is created on the first real user gesture so browsers never
// block it and no autoplay warning is produced.

export class Sound {
  constructor({ enabled = true, volume = 35 } = {}) {
    this.enabled = enabled;
    this.volume = volume;
    this.ctx = null;
    this.master = null;
    this.noise = null;
    this.ready = false;
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (this.master) this.master.gain.value = this.enabled ? this.volume / 100 : 0;
  }

  setVolume(volume) {
    this.volume = Math.max(0, Math.min(100, Number(volume) || 0));
    if (this.master) this.master.gain.value = this.enabled ? this.volume / 100 : 0;
  }

  /** Must be called synchronously from a user gesture (pointerdown / keydown). */
  unlock() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {});
      return;
    }
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return;
    try {
      this.ctx = new Ctor({ latencyHint: 'interactive' });
      this.master = this.ctx.createGain();
      this.master.gain.value = this.enabled ? this.volume / 100 : 0;
      this.master.connect(this.ctx.destination);

      const frames = Math.floor(this.ctx.sampleRate * 0.2);
      const buffer = this.ctx.createBuffer(1, frames, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < frames; i += 1) data[i] = Math.random() * 2 - 1;
      this.noise = buffer;
      this.ready = true;
    } catch {
      this.ready = false;
    }
  }

  #noiseBurst({ at, type, frequency, q, gain, attack, decay }) {
    const ctx = this.ctx;
    const source = ctx.createBufferSource();
    source.buffer = this.noise;
    source.playbackRate.value = 1;

    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    filter.Q.value = q;

    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(Math.max(gain, 0.0002), at + attack);
    env.gain.exponentialRampToValueAtTime(0.0001, at + attack + decay);

    source.connect(filter);
    filter.connect(env);
    env.connect(this.master);
    source.start(at);
    source.stop(at + attack + decay + 0.02);
  }

  click(strength = 1) {
    if (!this.enabled || !this.ready) return;
    const ctx = this.ctx;
    const at = ctx.currentTime + 0.001;
    const s = Math.max(0.2, Math.min(1, strength));

    this.#noiseBurst({
      at,
      type: 'bandpass',
      frequency: 2200,
      q: 1.1,
      gain: 0.5 * s,
      attack: 0.003,
      decay: 0.055,
    });

    // low thump — the mass of the switch
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(132, at);
    osc.frequency.exponentialRampToValueAtTime(78, at + 0.055);
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(0.34 * s, at + 0.004);
    env.gain.exponentialRampToValueAtTime(0.0001, at + 0.07);
    osc.connect(env);
    env.connect(this.master);
    osc.start(at);
    osc.stop(at + 0.09);
  }

  tick(strength = 1) {
    if (!this.enabled || !this.ready) return;
    const at = this.ctx.currentTime + 0.001;
    this.#noiseBurst({
      at,
      type: 'bandpass',
      frequency: 4200,
      q: 2.4,
      gain: 0.18 * Math.max(0.3, Math.min(1, strength)),
      attack: 0.0015,
      decay: 0.024,
    });
  }

  hover() {
    if (!this.enabled || !this.ready) return;
    const at = this.ctx.currentTime + 0.001;
    this.#noiseBurst({
      at,
      type: 'highpass',
      frequency: 6800,
      q: 0.7,
      gain: 0.03,
      attack: 0.001,
      decay: 0.012,
    });
  }
}
