"use client";

import type { RolesState } from "./RolesContext";

/** The message for the two states in which the user can do nothing yet: the roles failed to load, or there are none. */
export function RolesNotice({ state }: { state: Extract<RolesState, { status: "error" | "no_profile" }> }) {
  if (state.status === "error") {
    return (
      <div role="alert" className="notice notice-error">
        <p>No se han podido cargar tus permisos</p>
        <button type="button" onClick={state.retry}>Reintentar</button>
      </div>
    );
  }
  return <div role="status" className="notice notice-info">Tu usuario no tiene ningún perfil asignado</div>;
}
