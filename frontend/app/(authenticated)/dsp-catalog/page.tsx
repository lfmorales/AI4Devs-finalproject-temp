"use client";

import { useState } from "react";

import { CatalogueView } from "@/features/catalogue/CatalogueView";
import type { FatalKind } from "@/features/linking/LinePickerDialog";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

export default function DspCatalogPage() {
  const [fatal, setFatal] = useState<FatalKind | null>(null);
  useReportForbidden("/dsp-catalog", fatal === "forbidden");

  if (fatal === "unauthenticated") return <SessionExpiredPage />;
  if (fatal === "forbidden") return <AccessDeniedPage message="No tienes permiso para ver el catálogo de Adform." />;

  return (
    <div>
      <h1>Catálogo Adform</h1>
      <CatalogueView onFatal={setFatal} />
    </div>
  );
}
