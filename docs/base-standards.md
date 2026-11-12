---
description: This document contains all development rules and guidelines for this project, applicable to all AI agents (Claude, Cursor, Codex, Gemini, etc.).
alwaysApply: true
---

## 1. Core Principles

- **Small tasks, one at a time**: Always work in baby steps, one at a time. Never go forward more than one step.
- **Test-Driven Development**: Start with failing tests for any new functionality (TDD), according to the task details.
- **Type Safety**: All code must be fully typed.
- **Clear Naming**: Use clear, descriptive names for all variables and functions.
- **Incremental Changes**: Prefer incremental, focused changes over large, complex modifications.
- **Question Assumptions**: Always question assumptions and inferences.
- **Pattern Detection**: Detect and highlight repeated code patterns.

## 2. Language Standards
- **English Only**: All technical artifacts must always use English, including:
    - Code (variables, functions, classes, comments, error messages, log messages)
    - Documentation (README, guides, API docs)
    - Jira tickets (titles, descriptions, comments)
    - Data schemas and database names
    - Configuration files and scripts
    - Git commit messages
    - Test names and descriptions

## 3. Product Context

AdOps360 centralises the management of GeoQ's out-of-home and digital advertising campaigns. It replaces a chain of spreadsheets on OneDrive, manual report downloads and Qlik Sense dashboards with a single system of record.

Four functional roles use it, and **a user may hold several of them at once**:

| Role | What they do in the system |
|---|---|
| Operations | Global control: register campaigns from the purchase order, map them to the DSP, work ingestion exceptions, read the margin and close months, maintain rebate schedules and platform rates, activate and deactivate users |
| Business | Manage the commercial offer that becomes a purchase order, read campaign status |
| Finance | Reviewer: read margins, rebate accruals and period roll-ups, and close months |
| Trading | Read the daily delivery status, without any cost, revenue, rebate or margin figure |

The system integrates three concerns:

1. **Intake** of purchase orders and commercial offers, today held in Excel on OneDrive.
2. **Delivery performance** retrieved from the Adform, Equativ and Displayce APIs.
3. **Margin and roll-up calculation**, today performed in Qlik Sense.

The economic model, the domain entities and the decisions behind them are specified in [Product Description](./product-description.md). That document is the source of truth for *what* the system computes; this one is the source of truth for *how* it is built.

## 4. Technology Stack

### Backend
- **Python 3.12**: Runtime.
- **FastAPI**: Web framework and API layer.
- **SQLAlchemy**: ORM and data model.
- **Alembic**: Database migrations.
- **pandas** and **openpyxl**: Parsing of commercial-offer spreadsheets and DSP report files.

### Frontend
- **Node.js 22 LTS**: Runtime and build tooling.
- **Next.js**: Application framework.
- **TypeScript**: Type-safe development across the whole frontend.
- Routes and views are **guarded by role** (see §6).

### Database
- **PostgreSQL**, running in its own container with a named volume for persistence.
- Managed database services are deliberately not used for the MVP, to keep deployment to a single machine.

### Authentication
- **Microsoft Entra ID** handles credentials, tokens and session, with every user in the company tenant.
- **AWS Cognito (User Pool)** is kept as a second configured issuer for development and the end-to-end tests.
- The backend accepts tokens only from the configured issuers (issuer, audience, key address, user identifier claim and, optionally, a mandatory scope each). Tenant and application identifiers live only in `.env`.
- **Authorisation remains the application's own responsibility** (see §6).

### File storage
- **Amazon S3** for uploaded purchase-order and commercial-offer spreadsheets, and for reports downloaded from the DSPs.

### DSP API credentials
- Held as **environment variables in a `.env` file with restricted permissions** on the EC2 instance.
- Secrets Manager is a future improvement and is explicitly out of scope for the MVP.

### Testing
- **Backend**: `pytest` with `httpx` for API-level tests.
- **Frontend**: `Vitest` with Testing Library.
- **End-to-end**: `Playwright`, covering the three role flows.

## 5. Repository Structure

Application code lives at the repository root, one directory per deployable service. `packages/` is reserved for internal tooling and is not part of the runtime.

```
.
├── backend/                 # Python 3.12 + FastAPI service
├── frontend/                # Node 22 + Next.js application
├── nginx/                   # Reverse proxy configuration and TLS
├── docs/                    # Standards and product documentation
├── openspec/                # Change specifications
├── ai-specs/                # Canonical agent artifacts (agents, skills, scripts)
├── packages/                # Internal tooling, not deployed
├── docker-compose.yml       # Four services: backend, frontend, db, nginx
└── .env.example             # Required environment variables, no real values
```

Internal layout of `backend/` and `frontend/` is defined in [Backend Standards](./backend-standards.md) and [Frontend Standards](./frontend-standards.md).

## 6. Authorization Model

Authentication and authorisation are deliberately split. **The identity provider answers "who is this?"; the application answers "what may they do?"**

### Identity

A user authenticates against a configured issuer (Entra ID, or Cognito in development) and presents a JWT. The backend validates the token against that issuer's public keys and joins it to the local `users` table by the pair **(issuer, subject)**: `oid` for Entra, `sub` for Cognito. The **email claim** is used only on the first access, to link a registered user that has no link yet.

```
Issuer ──token (issuer, subject)──> users ──> user_roles ──> roles
```

`users.email` is unique, and the (issuer, subject) pair is unique once stored. Authentication never creates a user. Operational consequences that must be handled explicitly:

- A user who authenticates successfully but has no matching `users` row, by pair or by email, is **authenticated but unauthorised**. The request is rejected; it must not auto-provision a user.
- The first access of a registered user with no link stores the pair. A user already linked to a different pair is rejected and the link is not changed. If the token carries no email and the pair is not linked, the user is treated as not registered.
- Once linked, a change of email at the provider does not lose the user's roles. Before the link exists, the `users` row must carry the same email as the provider.
- Operations can set a user inactive; it takes effect on the next request, whatever the token says.

### Roles

Roles live **only in the database**. The identity provider holds no role information that the application reads (a `roles` claim in an Entra token is ignored), so there is one source of truth and nothing to keep in sync.

A user may hold several roles simultaneously, so the relationship is modelled as a **bridge table, never as a single column on `users`**:

```
users                 user_roles                 roles
-----                 ----------                 -----
id (PK)         ┌──── user_id (FK)               id (PK)
email (unique) ─┘     role_id (FK) ──────────┐   name
                      PK (user_id, role_id)  └── (operations | business | finance | trading)
```

### Enforcement

Every endpoint declares the role or roles it requires, and the requirement is checked against `user_roles` for the authenticated user on each request.

- Authorisation is enforced **at the endpoint**, not in the frontend. Role-guarded routes in Next.js are a usability measure that hides what a user cannot use; they are not a security control and must never be the only check.
- A user holding any one of an endpoint's accepted roles is authorised. Roles are additive, never exclusive.
- Failing authorisation returns a distinct outcome from failing authentication: an invalid or missing token is rejected as unauthenticated, while a valid token without the required role is rejected as forbidden.
- Endpoints that expose cost or margin figures are restricted to the Operations and Finance roles, per the access rules in [Product Description](./product-description.md). The roles each route accepts are the access matrix of the `identity/access-matrix` specification.

## 7. Deployment

The MVP runs as a **containerised monolith on a single EC2 instance** (t3.small or t3.medium), orchestrated with Docker Compose. This is chosen to match the scope of an internal MVP, not as a long-term architecture.

Four services:

| Service | Role |
|---|---|
| `backend` | FastAPI application |
| `frontend` | Next.js application |
| `db` | PostgreSQL, with a named volume for persistence |
| `nginx` | Reverse proxy and TLS termination, with Certbot for certificates |

Cognito and S3 are managed AWS services and are not part of the Compose stack. Only the configuration needed for `backend` and `frontend` to reach them is declared, via environment variables.

Configuration rules:

- All configuration is supplied through environment variables, declared in `.env.example` with no real values.
- `.env` is never committed. On the instance it carries restricted file permissions, since it holds the DSP API credentials.
- Database persistence depends on the named volume. Removing it destroys the data.

## 8. Specific standards

For detailed standards and guidelines specific to different areas of the project, refer to:

- [Product Description](./product-description.md) - Product context, domain model, economic model and the decisions behind them
- [Backend Standards](./backend-standards.md) - API development, database patterns, testing, security and backend best practices
- [Frontend Standards](./frontend-standards.md) - Next.js components, UI/UX guidelines, and frontend architecture
- [Documentation Standards](./documentation-standards.md) - Technical documentation structure, formatting, and maintenance guidelines, including AI standards like this document
- [OpenSpec Tasks Mandatory Steps](./openspec-tasks-mandatory-steps.md) - Required checklist and execution rules when creating or updating OpenSpec `tasks.md` files

## 9. Project Skills

- Skills live in `ai-specs/skills`.
- When a request matches a skill, load and follow the corresponding `SKILL.md` automatically before continuing.
- Also load any referenced files in the skill folder (for example, `references/*.md`) when the skill requires them.

## 10. Planning Model Requirement

Planning workflows must run with Opus high reasoning.

This requirement applies to:
- `enrich-us`
- `openspec-ff-change`
- `openspec-continue-change`

Before starting any of these workflows, verify the session is using Opus high reasoning. If it is not, **self-correct** by adding `"model": "claude-opus-4-7"` to `.claude/settings.json` (use the `update-config` skill or edit directly), then continue — do not stop and ask the user. Do the same to come back to sonnet medium for any other step.

## 11. Symlink Integrity and Multi-Agent Portability

- **Canonical Source**: Keep reusable artifacts in `ai-specs` as the canonical source. Agent-specific paths (such as `.claude` and `.cursor`) should reference them through symlinks when possible.
- **Update Safety**: Whenever a file is renamed, moved, or its suffix changes, verify and update all symlinks that target it before considering the change complete.
- **New Artifact Linking**: Whenever creating a new artifact that requires multi-agent exposure (for example new agents or skills in `ai-specs`), create the corresponding symlinks from the expected agent-specific reference paths.
- **External Customization Review**: Whenever customization is introduced outside `ai-specs`, evaluate whether it should be moved into `ai-specs` and replaced with symlinks from the original locations.
- **Completion Gate**: A change is incomplete if it leaves broken symlinks, stale targets, or duplicated canonical artifacts across agent-specific folders.

## 12. Mandatory OpenSpec Artifact Updates for Post-Apply Changes

When a new fix/change request appears after `opsx:apply` (or `/apply`) and before `opsx:archive` (or `/archive`), agents must treat it as a spec update first, not as an informal "fix this quickly". It's the core principle of openspec, documentation is the source of truth.

Required order:

1. Update the current OpenSpec change artifacts that are affected (for example: scenarios, requirements/specs, and `tasks.md`). Don't add tasks as "bugfixes" but as part of the initial design, thus in the proper section
2. If artifact regeneration is needed, run the corresponding OpenSpec step (`opsx:continue`, `opsx:ff`, or equivalent) before coding.
3. Implement code only after artifacts reflect the new request.
4. Re-run verification against the updated artifacts before archiving.

Do not apply direct code-only fixes in this window without updating OpenSpec artifacts.
