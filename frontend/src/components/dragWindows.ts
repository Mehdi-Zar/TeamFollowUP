// Every window of the app can be moved: grab it by its title bar and it follows the
// pointer. One listener for the whole document, so every window gets it, today's and
// tomorrow's, without each screen having to ask: the shared Modal (its .modal-head)
// and the older .modal windows (their title, the h3 or the first header row).
//
// The window moves with a CSS translate, so its layout is untouched, and it never
// leaves the screen far enough to lose its title bar. A window that closes takes its
// position with it: the next one opens centred again.

const HANDLE = ".modal-head, .modal > h3:first-child, .modal > .between:first-child";
const WINDOW = ".modal-card, .modal";
const INTERACTIVE = "button, a, input, select, textarea, label, summary, [role='button'], [contenteditable='true']";

let installed = false;

export function installDraggableWindows(): void {
  if (installed || typeof document === "undefined") return;
  installed = true;

  document.addEventListener("pointerdown", (e: PointerEvent) => {
    if (e.button !== 0) return;
    const target = e.target as Element | null;
    if (!target || target.closest(INTERACTIVE)) return;
    const handle = target.closest(HANDLE) as HTMLElement | null;
    if (!handle) return;
    const win = handle.closest(WINDOW) as HTMLElement | null;
    if (!win) return;

    const start = { x: e.clientX, y: e.clientY };
    const prev = { x: Number(win.dataset.dx || 0), y: Number(win.dataset.dy || 0) };
    const box = win.getBoundingClientRect();
    const headH = handle.getBoundingClientRect().height || 40;
    win.classList.add("dragging-window");

    let moved = false;
    const move = (ev: PointerEvent) => {
      if (Math.abs(ev.clientX - start.x) + Math.abs(ev.clientY - start.y) > 3) moved = true;
      let dx = prev.x + ev.clientX - start.x;
      let dy = prev.y + ev.clientY - start.y;
      // Keep the title bar reachable: at least 80 px of the window inside the
      // screen sideways, and its top between the top edge and the bottom edge.
      const left = box.left - prev.x + dx;
      const top = box.top - prev.y + dy;
      if (left + box.width < 80) dx += 80 - (left + box.width);
      if (left > window.innerWidth - 80) dx -= left - (window.innerWidth - 80);
      if (top < 0) dy -= top;
      if (top > window.innerHeight - headH) dy -= top - (window.innerHeight - headH);
      win.dataset.dx = String(dx);
      win.dataset.dy = String(dy);
      win.style.translate = `${dx}px ${dy}px`;
    };
    const up = () => {
      win.classList.remove("dragging-window");
      // Released over the dimmed background, the browser sends it a click, and a
      // click there closes the window: the one that follows a drag is swallowed.
      if (moved) {
        const swallow = (ce: MouseEvent) => { ce.stopPropagation(); ce.preventDefault(); };
        window.addEventListener("click", swallow, { capture: true, once: true });
        setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
      }
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", up);
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", up);
    e.preventDefault();   // no text selection while dragging
  });
}
