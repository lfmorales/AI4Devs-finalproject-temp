"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

interface ModalProps {
  /** Visible heading; it is also the dialog's accessible name. */
  title: string;
  /** When false (a request is in flight) Escape does nothing. */
  closable: boolean;
  /** Called when the user dismisses the dialog with Escape. The parent decides to unmount it. */
  onClose: () => void;
  children: ReactNode;
}

/**
 * A native <dialog> opened with showModal(): the browser draws it in the top layer over a dimmed page, closes it
 * with Escape and keeps the focus inside, with no CSS needed. Unmounting it gives the focus back to the element
 * that had it when the dialog opened (the button that opened it).
 */
export function Modal({ title, closable, onClose, children }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const latest = useRef({ closable, onClose });
  latest.current = { closable, onClose };

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={(event) => {
        // Escape: never let the browser close it by itself; the parent unmounts it.
        event.preventDefault();
        if (latest.current.closable) latest.current.onClose();
      }}
      style={{ maxWidth: "40rem", width: "calc(100% - 2rem)", padding: "1rem", border: "1px solid #d1d5db" }}
    >
      <h2 id={titleId} style={{ fontSize: "1.125rem", fontWeight: "600", marginTop: 0 }}>{title}</h2>
      {children}
    </dialog>
  );
}
