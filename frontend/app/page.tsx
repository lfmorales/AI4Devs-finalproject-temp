"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth/AuthContext";
import { firstPageFor } from "@/lib/auth/navigation";
import { RolesProvider, useRoles } from "@/lib/auth/RolesContext";
import { RolesNotice } from "@/lib/auth/RolesNotice";

/** Sends the signed-in user to the first screen their roles open. */
function RedirectToFirstPage() {
  const roles = useRoles();
  const router = useRouter();
  const target = roles.status === "ready" ? firstPageFor(roles.roles) : null;

  useEffect(() => {
    if (target !== null) router.replace(target);
  }, [target, router]);

  if (roles.status === "error" || roles.status === "no_profile") return <RolesNotice state={roles} />;
  // Loading, or the redirect in progress
  return null;
}

export default function HomePage() {
  const { session, signIn } = useAuth();

  if (session.status === "loading") {
    return <p role="status" className="notice notice-info">Checking your session…</p>;
  }

  if (session.status === "authenticated") {
    return (
      <RolesProvider>
        <RedirectToFirstPage />
      </RolesProvider>
    );
  }

  // Unauthenticated: show login page
  return (
    <section className="card-page">
      <div className="card">
        <h1>AdOps360</h1>
        <p>Campaign intake, delivery performance and margins in one place.</p>
        <p>Sign in to your account to continue.</p>
        <button type="button" className="btn-primary" onClick={() => void signIn("/campaigns")}>
          Iniciar sesión
        </button>
      </div>
    </section>
  );
}
