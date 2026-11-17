// RealMouse — coarse-pointer trackpad. Touch has no absolute pointer, so the
// trackpad drives the cursor relatively: drag to move, tap to click, long press
// for the context menu, two fingers to scroll the page.

export class TouchPad {
  constructor({ el, engine, onTap, onLongPress, onMove }) {
    this.el = el;
    this.engine = engine;
    this.onTap = onTap;
    this.onLongPress = onLongPress;
    this.onMove = onMove || (() => {});

    this.active = false;
    this.last = null;
    this.startAt = 0;
    this.startPoint = null;
    this.moved = 0;
    this.longPressTimer = 0;
    this.consumed = false;
    this.touches = 0;

    el.addEventListener('pointerdown', (event) => this.#down(event));
    el.addEventListener('pointermove', (event) => this.#move(event));
    el.addEventListener('pointerup', (event) => this.#up(event));
    el.addEventListener('pointercancel', (event) => this.#up(event, true));
    el.addEventListener('touchstart', (event) => {
      this.touches = event.touches.length;
    }, { passive: true });
    el.addEventListener('touchend', () => {
      this.touches = 0;
    }, { passive: true });
  }

  #down(event) {
    if (event.pointerType === 'mouse') return;
    this.active = true;
    this.consumed = false;
    this.moved = 0;
    this.last = { x: event.clientX, y: event.clientY };
    this.startPoint = { x: event.clientX, y: event.clientY };
    this.startAt = performance.now();
    this.el.setPointerCapture?.(event.pointerId);
    this.el.classList.add('is-active');

    if (this.touches <= 1) {
      this.longPressTimer = window.setTimeout(() => {
        if (this.active && this.moved < 12) {
          this.consumed = true;
          this.onLongPress?.(this.engine.x, this.engine.y);
        }
      }, 450);
    }
    event.preventDefault();
  }

  #move(event) {
    if (!this.active || event.pointerType === 'mouse') return;
    if (this.touches >= 2) {
      const dy = this.last ? event.clientY - this.last.y : 0;
      window.scrollBy({ top: -dy * 1.1, behavior: 'auto' });
      this.last = { x: event.clientX, y: event.clientY };
      this.consumed = true;
      return;
    }
    if (!this.last) return;
    const dx = event.clientX - this.last.x;
    const dy = event.clientY - this.last.y;
    this.moved += Math.hypot(dx, dy);
    this.engine.nudge(dx * 1.6, dy * 1.6);
    this.last = { x: event.clientX, y: event.clientY };
    this.onMove();
    event.preventDefault();
  }

  #up(event, cancelled) {
    if (!this.active) return;
    this.active = false;
    this.el.classList.remove('is-active');
    clearTimeout(this.longPressTimer);

    const elapsed = performance.now() - this.startAt;
    const isTap = !cancelled && !this.consumed && this.moved < 10 && elapsed < 500;
    if (isTap) this.onTap?.(this.engine.x, this.engine.y);
    this.last = null;
  }
}
