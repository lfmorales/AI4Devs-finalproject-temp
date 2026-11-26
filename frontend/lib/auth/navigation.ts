export type Role = "operations" | "business" | "finance" | "trading";

export const ROLES: readonly Role[] = ["operations", "business", "finance", "trading"];

export interface NavigationLink {
  href: string;
  label: string;
  /** The roles that open the page: a user holding any one of them sees the link. */
  roles: readonly Role[];
}

/** The only table of the frontend that says who sees what; the order is the order of the navigation. */
export const NAVIGATION_LINKS: readonly NavigationLink[] = [
  { href: "/campaigns", label: "Campañas", roles: ["operations", "business", "finance"] },
  { href: "/status", label: "Estado", roles: ["operations", "business", "finance", "trading"] },
  { href: "/margin", label: "Margen", roles: ["operations", "finance"] },
  { href: "/billing", label: "Facturación", roles: ["operations", "finance"] },
  { href: "/exceptions", label: "Excepciones", roles: ["operations"] },
  { href: "/dsp-catalog", label: "Catálogo Adform", roles: ["operations"] },
];

/** The links the roles open, in navigation order, leaving out the pages the API has already refused. */
export function visibleLinks(roles: readonly Role[], hidden: ReadonlySet<string> = new Set()): NavigationLink[] {
  return NAVIGATION_LINKS.filter((link) => !hidden.has(link.href) && link.roles.some((role) => roles.includes(role)));
}

/** Where to send a user after signing in: the first link they can see, or null when they have none. */
export function firstPageFor(roles: readonly Role[]): string | null {
  return visibleLinks(roles)[0]?.href ?? null;
}
