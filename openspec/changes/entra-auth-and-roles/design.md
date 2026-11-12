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

**D2. Roles come only from the database.** Decided by the product owner: `CLAUDE.md` §6 stands. The verified identity carries no roles; the roles of a request are the user's rows in `user_roles`, for Entra and for Cognito alike. The `roles` claim of an Entra token is ignored, and no Entra application roles are defined.

**D3. Stable identifier.** Two optional columns on `users` (issuer and subject) with a unique constraint on the pair; Entra uses `oid`, Cognito `sub`. They are optional so existing rows migrate untouched. The repository gains a lookup by pair next to the lookup by email, in the real and the in-memory implementations.

**D4. Link on first access.** The authentication service looks up by pair, then by email for a user with no link, and stores the pair in the same request. A user already linked to another pair is rejected with 403 and left unchanged. Nothing creates users.

**D5. Active switch.** `is_active` is kept. A new endpoint for operations, `POST /users/activation`, changes it, and a new script, `scripts/set_user_active.py`, does the same for whoever administers the database. The endpoint refuses to deactivate the caller and the last active operations user, deciding the second under row locks in the transaction of the change. The check on every request is what makes it immediate.

**D6. Token the API receives.** With Entra the frontend sends the access token and requests `api://<client>/access_as_user` plus `openid profile email`; with Cognito it sends the identity token. The provider is chosen by an environment variable, and the `cognito-config.ts` logic is split by provider.

**D7. Matrix.** A product decision of 2026-11-12: operations has global control and finance is the reviewer. `docs/base-standards.md` (`CLAUDE.md` §3, §4, §6) and `docs/product-description.md` are updated by task 1.1 of this change. The daily status returns no cost field to any role and stays as it is. The roles of each route change in the routers' `require_roles`; `RoleName` gains `TRADING`. The route-protection test derives the roles from the application, so its expectations are rewritten around the matrix.

**D8. Tests.** Development and E2E stay on Cognito. Entra is exercised with synthetic tokens signed by a test key and a simulated key address; the real Entra sign-in is checked by hand and recorded in a report of the change.

**D9. Identifiers.** Tenant and application identifiers only in `.env`; placeholders everywhere else.

## Risks / Trade-offs

- [A first-access link by email could attach an identity to the wrong person if two tenants share an address] → the link needs a configured issuer; an existing link is never overwritten.
- [Finance loses the writes of schedules and platform rates] → breaking by intent; the existing finance tests change with the matrix.
- [An Entra access token does not carry `email` by default] → see Entra configuration requirement below.
- [An unknown kid makes PyJWKClient download the key set again on every request; someone without a session can force downloads] → before deploying, limit how often the keys are reloaded and shorten the download timeout.
- The first-access link trusts the email claim of the Entra token, which Entra does not verify. In a single-tenant deployment with pre-registered users and an issuer pinned to the company tenant, the exposure is limited to those who can edit mail attributes, and it applies only to the first access: once linked, only the subject counts.
- A user has a single (issuer, subject) link. A user linked to Cognito is rejected with identity_link_conflict when presenting an Entra token, and vice versa. In production only Entra is used. In development, reset-data.sh recreates the database; to unlink by hand, set both columns to NULL. If both issuers must work against one database, move to a table of identities.
- Activating and deactivating users leaves no audit trail yet; record who changed what and when before production.
- The post-logout redirect URI of the Entra registration must include the application origin, besides the callback URL.

## Entra Configuration Requirement

The email fallback of D4 only works if the Entra application is configured to put an `email` claim in the access token (an optional claim of the version 2 access token). The link of the first access uses that email. If the token carries no email and the pair (issuer, subject) is not yet linked, the result is 403 `user_not_registered` and nothing is stored. A user already linked is unaffected by a missing email. The administrator therefore either configures the optional claim or links users beforehand.

The application defines no Entra application roles: the `roles` claim is ignored (D2).
