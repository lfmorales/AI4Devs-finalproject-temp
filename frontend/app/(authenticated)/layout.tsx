"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import Link from "next/link";

import { useAuth } from "@/lib/auth/AuthContext";
import { ForbiddenPagesProvider, useForbiddenPages } from "@/lib/auth/ForbiddenPages";
import { visibleLinks } from "@/lib/auth/navigation";
import { RolesProvider, useRoles } from "@/lib/auth/RolesContext";
import { RolesNotice } from "@/lib/auth/RolesNotice";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

/** The link of the section the path is in: the path itself or anything below it. */
function isCurrent(pathname: string | null, href: string): boolean {
  return pathname !== null && (pathname === href || pathname.startsWith(`${href}/`));
}

function Navigation() {
  const { hidden } = useForbiddenPages();
  const { signOut } = useAuth();
  const roles = useRoles();
  const pathname = usePathname();
  const links = roles.status === "ready" ? visibleLinks(roles.roles, hidden) : [];

  return (
    <nav aria-label="Principal">
      {links.map((link) => (
        <Link key={link.href} href={link.href} aria-current={isCurrent(pathname, link.href) ? "page" : undefined}>{link.label}</Link>
      ))}
      <button type="button" onClick={() => void signOut()}>
        Cerrar sesión
      </button>
    </nav>
  );
}

/** The page, unless the roles failed to load or there are none: then only the notice, which the pages cannot answer. */
function Content({ children }: { children: ReactNode }) {
  const roles = useRoles();
  if (roles.status === "error" || roles.status === "no_profile") return <RolesNotice state={roles} />;
  return <>{children}</>;
}

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { session, signIn } = useAuth();
  const pathname = usePathname();

  if (session.status === "loading") {
    return <div role="status" className="notice notice-info">Cargando…</div>;
  }

  if (session.status === "session_expired") {
    return <SessionExpiredPage />;
  }

  if (session.status === "unauthenticated") {
    return (
      <div className="card-page">
        <div className="card">
          <h1>Por favor, inicia sesión</h1>
          <p>
            Para continuar, necesitas autenticarte en el sistema.
          </p>
          <button
            className="btn-primary"
            onClick={() => signIn(pathname || "/")}
          >
            Iniciar sesión
          </button>
        </div>
      </div>
    );
  }

  return (
    <RolesProvider>
      <ForbiddenPagesProvider>
        <Navigation />
        <Content>{children}</Content>
      </ForbiddenPagesProvider>
    </RolesProvider>
  );
}
