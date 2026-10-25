import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { Modal } from "@/lib/components/Modal";

function Harness({ closable = true, onClose = () => {} }: { closable?: boolean; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Abrir</button>
      {open && (
        <Modal title="Título de prueba" closable={closable} onClose={() => { onClose(); setOpen(false); }}>
          <button type="button">Dentro</button>
        </Modal>
      )}
    </>
  );
}

describe("Modal", () => {
  it("is a native dialog element, open, named by its visible title", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Abrir" }));

    const dialog = screen.getByRole("dialog", { name: "Título de prueba" });
    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAttribute("aria-labelledby");
    expect(screen.getByRole("heading", { name: "Título de prueba" })).toBeInTheDocument();
  });

  it("moves the focus into the dialog when it opens", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Abrir" }));

    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes with Escape and gives the focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir" })).toHaveFocus();
  });

  it("does not close with Escape while it is not closable", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness closable={false} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("gives the focus back to the opener when it is unmounted by its parent", async () => {
    const user = userEvent.setup();
    function Parent() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Abrir</button>
          {open && <Modal title="T" closable onClose={() => {}}><button type="button" onClick={() => setOpen(false)}>Cerrar ya</button></Modal>}
        </>
      );
    }
    render(<Parent />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.click(screen.getByRole("button", { name: "Cerrar ya" }));

    expect(screen.getByRole("button", { name: "Abrir" })).toHaveFocus();
  });
});
