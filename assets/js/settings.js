// RealMouse — persisted feel settings.

export const STORAGE_KEY = 'realmouse.settings.v1';

export const DEFAULTS = Object.freeze({
  mode: 'assisted', // 'assisted' | 'direct'
  weight: 1, // 0.4 .. 3.0 — response weight
  smoothing: 15, // 0 .. 100
  tremor: 0.28, // px, 0 .. 1.2
  magnet: true,
  haptics: true,
  sound: true,
  volume: 35, // 0 .. 100
  size: 24, // px, 16 .. 40
  system: false, // native cursor escape hatch
  trace: true,
});

const RANGES = {
  weight: [0.4, 3],
  smoothing: [0, 100],
  tremor: [0, 1.2],
  volume: [0, 100],
  size: [16, 40],
};

const BOOLEANS = ['magnet', 'haptics', 'sound', 'system', 'trace'];

function coerce(raw) {
  const out = { ...DEFAULTS };
  if (!raw || typeof raw !== 'object') return out;

  if (raw.mode === 'direct' || raw.mode === 'assisted') out.mode = raw.mode;

  for (const [key, [min, max]] of Object.entries(RANGES)) {
    const value = Number(raw[key]);
    if (Number.isFinite(value)) out[key] = Math.min(max, Math.max(min, value));
  }

  for (const key of BOOLEANS) {
    if (typeof raw[key] === 'boolean') out[key] = raw[key];
  }

  return out;
}

export function readSettings() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    return coerce(JSON.parse(raw));
  } catch {
    return { ...DEFAULTS };
  }
}

export function writeSettings(settings) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;
  }
}

export function createStore(initial = readSettings()) {
  let state = coerce(initial);
  const listeners = new Set();

  const emit = (patch) => {
    for (const fn of listeners) fn(state, patch);
  };

  return {
    get: () => state,
    set(patch) {
      const next = coerce({ ...state, ...patch });
      const changed = Object.keys(patch).filter((k) => next[k] !== state[k]);
      if (changed.length === 0) return state;
      state = next;
      writeSettings(state);
      emit(patch);
      return state;
    },
    reset() {
      state = { ...DEFAULTS };
      writeSettings(state);
      emit({ ...DEFAULTS, reset: true });
      return state;
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
