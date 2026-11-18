---
description: Frontend standards and best practices for the AdOps360 application.
alwaysApply: false
---

# Frontend Project Configuration and Best Practices

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Coding Standards](#coding-standards)
5. [Role-Based Access](#role-based-access)
6. [Data Access](#data-access)
7. [UI/UX Standards](#uiux-standards)
8. [Testing Standards](#testing-standards)
9. [Configuration Standards](#configuration-standards)
10. [Performance Best Practices](#performance-best-practices)
11. [Development Workflow](#development-workflow)

## Overview

This document outlines the best practices, conventions and standards used in the AdOps360 frontend. The application serves three roles — operations, business and finance — and a user may hold several at once, so the interface is composed from what the current user may do rather than switched between three fixed modes.

## Technology Stack

### Core Technologies
- **Node.js 22 LTS**: Runtime and build tooling.
- **Next.js**: Application framework and routing.
- **TypeScript**: Type-safe development across the whole codebase.

### Authentication
- **Microsoft Entra ID**: The only identity provider. The frontend signs the user in with Entra (`oidc-client-ts`, authorization code with PKCE), requests `api://<client-id>/access_as_user` besides `openid profile email`, and attaches the **access token** to API requests. It does not decide what the user may do: the roles come from `GET /users/me`, which reads them from the database. The test issuer of the end-to-end tests has no sign-in page and the frontend knows nothing of it.

### Testing Framework
- **Vitest**: Unit and component testing.
- **Testing Library**: Component interaction and assertions.
- **Playwright**: End-to-end testing, covering the three role flows.

## Project Structure

```
frontend/
├── app/                      # Next.js routes and layouts
│   ├── (auth)/               # Sign-in and session handling
│   ├── campaigns/            # Operations and business views
│   ├── offers/               # Commercial offer views
│   ├── finance/              # Margin and roll-up views
│   └── layout.tsx
├── components/               # Reusable UI components
├── features/                 # Feature modules, grouped by domain area
├── lib/
│   ├── api/                  # API client and typed endpoint wrappers
│   ├── auth/                 # Entra session and access token handling
│   └── types/                # Shared domain types
├── tests/
│   └── unit/                 # Vitest component and unit tests
├── public/                   # Static assets
├── next.config.ts
├── tsconfig.json
├── vitest.config.ts
├── playwright.config.ts
├── package.json
└── Dockerfile
```

Group by feature, not by file type. A feature owns its components, hooks and types; shared pieces move to `components/` or `lib/` only once a second feature genuinely needs them.

## Coding Standards

### Type Safety

Per the core principles, **all code is fully typed**. `any` is not acceptable; use `unknown` and narrow it. API responses are typed at the client boundary in `lib/api/`, so that a shape change surfaces at compile time rather than as an undefined value in a table cell.

Domain types use the vocabulary of [Product Description](./product-description.md). `contractedImpressions` and `deliveredImpressions` are distinct fields with distinct meanings; a single `impressions` field is a bug waiting to be written.

### Naming

- Components: `PascalCase`, in files named after the component.
- Hooks: `useCamelCase`.
- Variables and functions: `camelCase`.
- Types and interfaces: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.

### Components

- Small, single-purpose, and composed rather than configured through proliferating boolean props.
- Presentational components receive data through props and do not fetch.
- Data fetching lives in the route or feature layer.
- Derive state rather than duplicating it.

### Money and Numbers

Financial figures are formatted for display only. Never round or recompute a monetary value in the frontend: margin, rebate and platform cost arrive calculated by the backend, and recomputing them client-side would create a second source of truth for the exact numbers this product exists to make reliable.

Amounts are displayed in euros with explicit currency, consistent with the single-currency scope recorded in [Product Description](./product-description.md).

## Role-Based Access

Routes and views are guarded by role. The rules mirror the server's, but they are a **usability measure, not a security control**: they hide what a user cannot use, so the interface stays legible for a user who holds one role and for a user who holds all three.

- The authenticated user's roles are read once after sign-in and made available through a session context.
- A route guard checks the required role or roles before rendering; a user holding **any** of the accepted roles passes, since roles are additive.
- Navigation renders only the destinations the user can reach. A guard that lets a user click through to a rejected request is a worse experience than one that never offered the link.
- Cost and margin views are restricted to the operations and finance roles.
- **Every guarded view is backed by a server-side check.** The frontend never assumes the API will not be called directly. See [Backend Standards](./backend-standards.md#authentication-and-authorization).

## Data Access

- All API calls go through the typed client in `lib/api/`. Components never call `fetch` directly.
- The Entra access token is attached by the client, in one place.
- Handle the three failure cases distinctly: unauthenticated (session expired — re-authenticate), forbidden (the role is missing — explain, do not retry), and failed (show the error and allow a retry).
- Loading and empty states are designed, not left as blank space. An empty campaign list and a list that has not loaded yet must not look the same.

## UI/UX Standards

- The three roles share one application. Composition is driven by the user's roles rather than by three parallel interfaces.
- Data tables are the primary surface: campaign status, delivery against contract, margin roll-ups. They must support sorting and filtering on the dimensions the business uses — period, agency, advertiser, channel.
- Provisional figures are labelled as provisional. Campaign margin is an estimate until the year closes, and current-month figures are accruals; presenting either as a settled result would misinform the user.
- Exceptions are surfaced, not buried: a campaign line with no DSP mapping, a period with no delivery, a served volume below contract. These are the states the product exists to make visible.
- Forms validate inline, and submit errors from the API are shown against the field that caused them.

## Testing Standards

### Test-Driven Development

Per the core principles, new functionality starts with a failing test.

### Unit and Component Tests — Vitest and Testing Library

- Test behaviour through the interface a user sees, not implementation details.
- Query by role and label rather than by test id where possible.
- Every role-guarded component has a test asserting what a user **without** the role sees.
- Location: `tests/unit/`, mirroring the source structure.

### End-to-End Tests — Playwright

Three flows, one per role, covering the path each role actually takes:

| Flow | Covers |
|---|---|
| Operations | Register a campaign from a purchase order, map it to the DSP, review an ingestion exception |
| Business | Create a commercial offer and follow it through to a campaign |
| Finance | Read campaign margin and period roll-ups |

A fourth case is worth carrying: a user holding several roles at once, since that is the normal case for this team and the one a three-flow suite would otherwise never exercise.

Location: `e2e/` at the repository root, outside `frontend/`.

## Configuration Standards

- Configuration comes from environment variables, declared in `.env.example` with no real values.
- The Entra settings needed by the browser — tenant id and client id — are exposed as the public build variables `NEXT_PUBLIC_ENTRA_TENANT_ID` and `NEXT_PUBLIC_ENTRA_CLIENT_ID`, which Compose derives from `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID`; the production build fails, naming the variable, when either is empty. Anything that must stay secret does not belong in the frontend.
- `.env` is never committed.

## Performance Best Practices

- Paginate and filter on the server. Delivery data runs to millions of rows, and no view should attempt to hold a period's raw delivery in the browser.
- Aggregate server-side. The frontend renders figures the backend computed.
- Use Next.js server rendering for the initial view where it reduces time to first meaningful content.
- Keep the client bundle lean; load heavy views on demand.

## Development Workflow

1. Work in baby steps, one at a time.
2. Write the failing test first.
3. Implement the smallest change that passes it.
4. Keep types honest — widening a type to silence an error is a defect, not a fix.
5. Run unit tests and the relevant Playwright flow before committing.
6. Commit messages, code, comments and test names in English.
