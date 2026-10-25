"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import Link from "next/link";

import { useAuth } from "@/lib/auth/AuthContext";
import { ForbiddenPagesProvider, useForbiddenPages } from "@/lib/auth/ForbiddenPages";
import { getUserManager } from "@/lib/auth/user-manager";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

const LINKS = [
  { href: "/campaigns", label: "Campañas" },
  { href: "/status", label: "Estado" },
  { href: "/exceptions", label: "Excepciones" },
];

function Navigation() {
  const { hidden } = useForbiddenPages();

  const handleSignOut = async () => {
    await getUserManager().removeUser();
    // The session will update through the AuthProvider's userUnloaded listener
  };

  return (
    <nav aria-label="Principal" style={{ display: "flex", gap: "1.5rem", alignItems: "center", padding: "0.75rem 2rem", borderBottom: "1px solid #e5e7eb" }}>
      {LINKS.filter((link) => !hidden.has(link.href)).map((link) => (
        <Link key={link.href} href={link.href}>{link.label}</Link>
      ))}
      <button type="button" onClick={() => void handleSignOut()} style={{ marginLeft: "auto" }}>
        Cerrar sesión
      </button>
    </nav>
  );
}

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { session, signIn } = useAuth();
  const pathname = usePathname();

  if (session.status === "loading") {
    return <div role="status">Cargando…</div>;
  }

  if (session.status === "session_expired") {
    return <SessionExpiredPage />;
  }

  if (session.status === "unauthenticated") {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", backgroundColor: "#f9fafb" }}>
        <div style={{ width: "100%", maxWidth: "28rem", padding: "3rem 1.5rem", textAlign: "center" }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: "bold", marginBottom: "1rem" }}>Por favor, inicia sesión</h1>
          <p style={{ color: "#4b5563", marginBottom: "2rem" }}>
            Para continuar, necesitas autenticarte en el sistema.
          </p>
          <button
            onClick={() => signIn(pathname || "/")}
            style={{ width: "100%", padding: "0.5rem 1rem", backgroundColor: "#2563eb", color: "white", fontWeight: "600", borderRadius: "0.375rem" }}
          >
            Iniciar sesión
          </button>
        </div>
      </div>
    );
  }

  return (
    <ForbiddenPagesProvider>
      <Navigation />
      {children}
    </ForbiddenPagesProvider>
  );
}
