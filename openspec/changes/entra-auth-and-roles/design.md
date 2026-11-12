## Context

See `proposal.md` — Why. Today one `CognitoTokenVerifier` fixes issuer, audience, key address and the `email` claim in its constructor (`backend/app/infrastructure/auth/cognito_token_verifier.py`), roles come only from `user_roles`, and `users.email` is the only link to the identity provider (`models/identity.py`). `is_active` already exists and is already checked on every request (`authentication_service.py`), so the active switch needs no new column.

Constraints that shape the approach: authentication stays behind the `IdentityTokenVerifier` contract in the domain; the layering `presentation -> application -> domain` with infrastructure depending inward is kept; no secret or tenant identifier is committed.

## Goals / Non-Goals

**Goals**

- A list of issuers in configuration, with Cognito kept as one entry built from its current variables.
- Role and identity resolution that is testable without a database or a network.
- The access matrix enforced at each endpoint and audited by the existing route-protection test.

**Non-Goals**

- A screen for users, trading views of the control desk, roles by Entra group, a test instance with HTTPS (see proposal, Non-goals).

## Decisions

**D1. Issuers are configuration.** `Settings` exposes a list of issuer entries: issuer, audience, key address, the claim that identifies the user and an optional mandatory scope. The Cognito variables stay, and `cognito_issuer` and `cognito_jwks_url` keep their meaning. A composite verifier implementing `IdentityTokenVerifier` reads `iss` without verifying, looks it up in the list and delegates to a generic verifier built for that entry; an unknown `iss` is an invalid token before any user lookup. Cognito's extra checks (identity token, verified email) move to its entry rather than staying in the generic code. Alternative rejected: one verifier class per provider chosen by a flag, because it cannot serve two issuers at once.

**D2. Roles by issuer.** The verified identity carries the roles read from the token for Entra (only known names) and none for Cognito, whose roles are read from `user_roles`. The two are never merged. Consequence: an Entra user needs a registered local user, but the stored roles of that user are ignored.

**D3. Stable identifier.** Two optional columns on `users` (issuer and subject) with a unique constraint on the pair; Entra uses `oid`, Cognito `sub`. They are optional so existing rows migrate untouched. The repository gains a lookup by pair next to the lookup by email, in the real and the in-memory implementations.

**D4. Link on first access.** The authentication service looks up by pair, then by email for a user with no link, and stores the pair in the same request. A user already linked to another pair is rejected with 403 and left unchanged. Nothing creates users.

**D5. Active switch.** `is_active` is kept. A new endpoint for operations changes it, and `scripts/grant_roles.py` gets an option for it. The check on every request is what makes it immediate.

**D6. Token the API receives.** With Entra the frontend sends the access token and requests `api://<client>/access_as_user` plus `openid profile email`; with Cognito it sends the identity token. The provider is chosen by an environment variable, and the `cognito-config.ts` logic is split by provider.

**D7. Matrix.** The roles of each route change in the routers' `require_roles`; `RoleName` gains `TRADING`. The route-protection test derives the roles from the application, so its expectations are rewritten around the matrix.

**D8. Tests.** Development and E2E stay on Cognito. Entra is exercised with synthetic tokens signed by a test key and a simulated key address; the real Entra sign-in is checked by hand and recorded in a report of the change.

**D9. Identifiers.** Tenant and application identifiers only in `.env`; placeholders everywhere else.

## Risks / Trade-offs

- [Roles from the token are issued by the identity provider, not the application] → the spec limits them to known names and gives no access without one; see Open Questions, since `CLAUDE.md` §6 says roles live only in the database.
- [A first-access link by email could attach an identity to the wrong person if two tenants share an address] → the link needs a configured issuer; an existing link is never overwritten.
- [Finance loses the writes of schedules and platform rates] → breaking by intent; the existing finance tests change with the matrix.
- [An Entra access token does not carry `email` by default] → the optional claim must be configured in Entra for the email fallback to work.

## Open Questions

These contradict an existing rule and are not resolved here; they need a decision before `/opsx:apply`.

1. `CLAUDE.md` §6 ("Roles live only in the database") against D2 (roles from the Entra token).
2. `CLAUDE.md` §6 ("restricted to the Finance role") and the finance-only specs against D7 (operations also sees cost and margin). Task 1 updates `CLAUDE.md`, but that is a decision for the owner of the rules.
3. Task 10 of the draft mentions "the cost field of the daily status", but the existing scenario "The response carries no cost field" says none exists, and the spec keeps it.
4. The requirement name "The daily status is read through one endpoint for operations and business" is kept exactly for MODIFIED and is now inaccurate; a rename needs a RENAMED entry.
5. Whether `GET /margin` etc. must also accept `trading`: the matrix says no.
