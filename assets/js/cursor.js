// RealMouse — the drawn pointer: glyph state machine + sub-pixel placement.

const GLYPHS = ['arrow', 'pointer', 'text', 'grab', 'grabbing', 'resize', 'not-allowed'];

export class Cursor {
  constructor(root = document) {
    this.el = root.getElementById('cursor');
    this.inner = root.getElementById('cursorInner');
    this.ring = root.getElementById('cursorRing');
    this.caret = root.getElementById('cursorCaret');
    this.nodes = new Map();
    for (const name of GLYPHS) {
      const node = this.el.querySelector(`[data-glyph="${name}"]`);
      if (node) this.nodes.set(name, node);
    }
    this.state = null;
    this.size = 24;
    this.pressed = false;
    this.x = 0;
    this.y = 0;
    this.scale = 1;
    this.visible = false;
    this.setState('arrow');
  }

  setState(name) {
    const next = this.nodes.has(name) ? name : 'arrow';
    if (next === this.state) return;
    if (this.state && this.nodes.has(this.state)) {
      this.nodes.get(this.state).classList.remove('is-active');
    }
    this.state = next;
    this.nodes.get(next)?.classList.add('is-active');
    const textual = next === 'text';
    this.caret?.classList.toggle('is-live', textual);
  }

  setSize(px) {
    this.size = px;
    this.el.style.setProperty('--cursor-size', `${px}px`);
  }

  setVisible(visible) {
    if (this.visible === visible) return;
    this.visible = visible;
    this.el.style.opacity = visible ? '1' : '0';
  }

  /** Hidden while the pointer is outside the window, like a hardware cursor. */
  setHidden(hidden) {
    this.hidden = Boolean(hidden);
    this.setVisible(!this.hidden);
  }

  /** Scale is separate from position so press feedback never moves the hotspot. */
  setPressed(pressed) {
    if (this.pressed === pressed) return;
    this.pressed = pressed;
    this.scale = pressed ? 0.9 : 1;
    this.inner.style.transform = `translate(-1px, -1px) scale(${this.scale})`;
    this.inner.style.transitionDuration = pressed ? '60ms' : '220ms';
  }

  render(x, y) {
    this.x = x;
    this.y = y;
    // A single composited translate keeps this off the layout path entirely.
    this.el.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0)`;
    if (!this.hidden) this.setVisible(true);
  }

  fireRing() {
    if (!this.ring) return;
    this.ring.classList.remove('is-firing');
    // Force a reflow so the animation can restart on rapid clicks.
    void this.ring.offsetWidth;
    this.ring.classList.add('is-firing');
  }

  setCaret(active) {
    this.caret?.classList.toggle('is-live', active && this.state === 'text');
  }
}
