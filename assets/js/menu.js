// RealMouse — context menu with real keyboard behaviour.

export class ContextMenu {
  constructor({ el, onAction, onOpenChange }) {
    this.el = el;
    this.onAction = onAction;
    this.onOpenChange = onOpenChange || (() => {});
    this.open = false;
    this.items = [...el.querySelectorAll('.menu__item')];

    for (const item of this.items) {
      item.addEventListener('click', () => {
        this.close('action');
        this.onAction(item.dataset.action, item);
      });
    }

    this.el.addEventListener('keydown', (event) => this.#onKey(event));

    document.addEventListener(
      'pointerdown',
      (event) => {
        if (!this.open) return;
        if (this.el.contains(event.target)) return;
        this.close('outside');
      },
      true,
    );

    window.addEventListener('blur', () => this.close('blur'));
    window.addEventListener('resize', () => this.close('resize'));
  }

  #onKey(event) {
    const index = this.items.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      this.close('escape');
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const dir = event.key === 'ArrowDown' ? 1 : -1;
      const next = (index + dir + this.items.length) % this.items.length;
      this.items[next]?.focus();
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      this.items[0]?.focus();
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      this.items[this.items.length - 1]?.focus();
    }
  }

  show(x, y) {
    this.el.classList.add('is-open');
    this.el.setAttribute('aria-hidden', 'false');
    this.open = true;

    const rect = this.el.getBoundingClientRect();
    const margin = 10;
    const left = Math.min(Math.max(margin, x), window.innerWidth - rect.width - margin);
    const top = Math.min(Math.max(margin, y), window.innerHeight - rect.height - margin);
    this.el.style.left = `${Math.round(left)}px`;
    this.el.style.top = `${Math.round(top)}px`;

    this.items[0]?.focus({ preventScroll: true });
    this.onOpenChange(true);
  }

  close(reason = 'manual') {
    if (!this.open) return;
    this.open = false;
    this.el.classList.remove('is-open');
    this.el.setAttribute('aria-hidden', 'true');
    this.onOpenChange(false, reason);
  }
}
