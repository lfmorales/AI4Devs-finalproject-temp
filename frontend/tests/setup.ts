import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom has no HTMLDialogElement.showModal() or close(). This is the minimum the tests rely on, and nothing more:
// showModal() sets `open` and moves the focus to the first focusable element inside (or the dialog itself);
// Escape fires a cancelable `cancel` event and, unless it is prevented, closes the dialog; close() removes `open`
// and fires `close`. The top layer, the backdrop and the focus trap are the browser's and are not simulated.
const FOCUSABLE = "button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])";
const escapeListeners = new WeakMap<HTMLDialogElement, (event: KeyboardEvent) => void>();

HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
  this.setAttribute("open", "");
  const first = this.querySelector<HTMLElement>(FOCUSABLE);
  if (first) first.focus();
  else {
    this.tabIndex = -1;
    this.focus();
  }
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Escape") return;
    const cancel = new Event("cancel", { cancelable: true });
    this.dispatchEvent(cancel);
    if (!cancel.defaultPrevented) this.close();
  };
  escapeListeners.set(this, onKeyDown);
  document.addEventListener("keydown", onKeyDown);
};

HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
  if (!this.hasAttribute("open")) return;
  this.removeAttribute("open");
  const listener = escapeListeners.get(this);
  if (listener) document.removeEventListener("keydown", listener);
  this.dispatchEvent(new Event("close"));
};
