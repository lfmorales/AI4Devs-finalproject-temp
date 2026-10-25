"use client";

import { useState } from "react";

import { ExceptionList, type FatalKind } from "@/features/exceptions/ExceptionList";
import { NO_FILTER, type ExceptionFilter } from "@/features/exceptions/filter";
import type { ExceptionStatus } from "@/lib/api/exceptions";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

const TABS: { status: ExceptionStatus; label: string }[] = [
  { status: "open", label: "Abiertas" },
  { status: "resolved", label: "Resueltas" },
];

export default function ExceptionsPage() {
  const [active, setActive] = useState<ExceptionStatus>("open");
  // Held here, above the tabs, so it survives a change of tab. Never in the URL or the browser storage.
  const [filter, setFilter] = useState<ExceptionFilter>(NO_FILTER);
  const [fatal, setFatal] = useState<FatalKind | null>(null);
  useReportForbidden("/exceptions", fatal === "forbidden");

  if (fatal === "unauthenticated") return <SessionExpiredPage />;
  if (fatal === "forbidden") return <AccessDeniedPage message="No tienes permiso para ver la cola de excepciones." />;

  return (
    <div>
      <h1>Excepciones de ingesta</h1>
      <div role="tablist" aria-label="Estado de las excepciones">
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
        <ExceptionList key={active} status={active} filter={filter} onFilterChange={setFilter} onFatal={setFatal} />
      </div>
    </div>
  );
}
