import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

import { AuthProvider } from "@/lib/auth/AuthProvider";

export const metadata: Metadata = {
  title: "AdOps360",
  description: "Campaign intake, delivery performance and margins for GeoQ.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#contenido">Saltar al contenido</a>
        <AuthProvider>
          <main id="contenido">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
