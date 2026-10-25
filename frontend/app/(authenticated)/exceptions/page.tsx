"use client";

import { useState } from "react";

import { ExceptionList, type FatalKind } from "@/features/exceptions/ExceptionList";
import type { ExceptionStatus } from "@/lib/api/exceptions";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

const TABS: { status: ExceptionStatus; label: string }[] = [
  { status: "open", label: "Abiertas" },
  { status: "resolved", label: "Resueltas" },
];

export default function ExceptionsPage() {
  const [active, setActive] = useState<ExceptionStatus>("open");
  const [fatal, setFatal] = useState<FatalKind | null>(null);

  if (fatal === "unauthenticated") return <SessionExpiredPage />;
  if (fatal === "forbidden") return <AccessDeniedPage message="No tienes permiso para ver la cola de excepciones." />;

  return (
    <div style={{ padding: "2rem" }}>
      <h1 style={{ fontSize: "1.875rem", fontWeight: "bold", marginBottom: "1rem" }}>Excepciones de ingesta</h1>
      <div role="tablist" aria-label="Estado de las excepciones" style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
        {TABS.map((tab) => (
          <button
            key={tab.status}
            type="button"
            role="tab"
            id={`exceptions-tab-${tab.status}`}
            aria-selected={active === tab.status}
            aria-controls="exceptions-panel"
            onClick={() => setActive(tab.status)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="exceptions-panel" aria-labelledby={`exceptions-tab-${active}`}>
        <ExceptionList key={active} status={active} onFatal={setFatal} />
      </div>
    </div>
  );
}
