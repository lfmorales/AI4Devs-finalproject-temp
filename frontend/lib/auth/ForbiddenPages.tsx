"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/**
 * The pages the backend has answered 403 for. Roles are never decoded in the browser: the 403 is the source of
 * truth, so the navigation shows every link until a page has been refused and hides that page's link afterwards.
 */
interface ForbiddenPagesValue {
  hidden: ReadonlySet<string>;
  markForbidden: (path: string) => void;
}

const ForbiddenPagesContext = createContext<ForbiddenPagesValue>({ hidden: new Set(), markForbidden: () => {} });

export function ForbiddenPagesProvider({ children }: { children: ReactNode }) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const markForbidden = useCallback((path: string) => setHidden((current) => new Set(current).add(path)), []);
  const value = useMemo(() => ({ hidden, markForbidden }), [hidden, markForbidden]);
  return <ForbiddenPagesContext.Provider value={value}>{children}</ForbiddenPagesContext.Provider>;
}

export function useForbiddenPages(): ForbiddenPagesValue {
  return useContext(ForbiddenPagesContext);
}

/** Tells the navigation that the page at `path` was refused with a 403, once `forbidden` is true. */
export function useReportForbidden(path: string, forbidden: boolean): void {
  const { markForbidden } = useForbiddenPages();
  useEffect(() => {
    if (forbidden) markForbidden(path);
  }, [forbidden, markForbidden, path]);
}
