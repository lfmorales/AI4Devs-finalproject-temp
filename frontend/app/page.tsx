"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth/AuthContext";

export default function HomePage() {
  const { session, signIn } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (session.status === "authenticated") {
      // Redirect authenticated users to campaigns list
      router.replace("/campaigns");
    }
  }, [session.status, router]);

  if (session.status === "loading") {
    return <p role="status" className="notice notice-info">Checking your session…</p>;
  }

  if (session.status === "authenticated") {
    // Redirect in progress
    return null;
  }

  // Unauthenticated: show login page
  return (
    <section>
      <div style={{ textAlign: "center", padding: "2rem" }}>
        <h1>AdOps360</h1>
        <p>Campaign intake, delivery performance and margins in one place.</p>
        <p>Sign in to your account to continue.</p>
        <button type="button" onClick={() => void signIn("/campaigns")}>
          Iniciar sesión
        </button>
      </div>
    </section>
  );
}
