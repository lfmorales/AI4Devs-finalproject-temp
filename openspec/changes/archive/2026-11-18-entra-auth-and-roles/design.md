## Context

See `proposal.md` — Why. Today one `CognitoTokenVerifier` fixes issuer, audience, key address and the `email` claim in its constructor (`backend/app/infrastructure/auth/cognito_token_verifier.py`), roles come only from `user_roles`, and `users.email` is the only link to the identity provider (`models/identity.py`). `is_active` already exists and is already checked on every request (`authentication_service.py`), so the active switch needs no new column.

Constraints that shape the approach: authentication stays behind the `IdentityTokenVerifier` contract in the domain; the layering `presentation -> application -> domain` with infrastructure depending inward is kept; no secret or tenant identifier is committed.

## Goals / Non-Goals

**Goals**

- A list of issuers in configuration: Entra always, and a test issuer only in development and test. Cognito is removed.
- Role and identity resolution that is testable without a database or a network.
- The access matrix enforced at each endpoint and audited by the existing route-protection test.

**Non-Goals**

- A screen for users, trading views of the control desk, roles by Entra group, a test instance with HTTPS (see proposal, Non-goals).

## Decisions

**D1. Issuers are configuration.** `Settings` exposes a list of issuer entries: issuer, audience, key source, the claim that identifies the user and an optional mandatory scope. Entra is the only real issuer: `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` are required, and without them the backend refuses to start. The test issuer of D11 is added to the list only when D11 allows it. The Cognito variables, `cognito_issuer`, `cognito_jwks_url`, the `cognito` kind and its checks (identity token, verified email) are removed. A composite verifier implementing `IdentityTokenVerifier` reads `iss` without verifying, looks it up in the list and delegates to a generic verifier built for that entry; an unknown `iss` is an invalid token before any user lookup. The key source is the issuer's key address for Entra and a static provider holding one local public key for the test issuer; both feed the same `IssuerTokenVerifier`. `Settings`, the issuer list and the verifiers are built when the application starts, so any invalid or incomplete configuration stops it from starting instead of failing on the first request. Alternative rejected: one verifier class per provider chosen by a flag, because it cannot serve two issuers at once.

**D2. Roles come only from the database.** Decided by the product owner: `CLAUDE.md` §6 stands. The verified identity carries no roles; the roles of a request are the user's rows in `user_roles`, whatever the issuer. The `roles` claim of an Entra token is ignored, and no Entra application roles are defined.

**D3. Stable identifier.** Two optional columns on `users` (issuer and subject) with a unique constraint on the pair; Entra and the test issuer use `oid`. They are optional so existing rows migrate untouched. The repository gains a lookup by pair next to the lookup by email, in the real and the in-memory implementations.

**D4. Link on first access.** The authentication service looks up by pair, then by email for a user with no link, and stores the pair in the same request. A user already linked to another pair is rejected with 403 and left unchanged. Nothing creates users.

**D5. Active switch.** `is_active` is kept. A new endpoint for operations, `POST /users/activation`, changes it, and a new script, `scripts/set_user_active.py`, does the same for whoever administers the database. The endpoint refuses to deactivate the caller and the last active operations user, deciding the second under row locks in the transaction of the change. The check on every request is what makes it immediate.

**D6. Token the API receives.** The frontend signs in with Entra only and sends the access token, requesting `api://<client>/access_as_user` plus `openid profile email`. In development the browser uses the real tenant through the development registration, whose redirect URIs are `http://localhost/callback` and `http://localhost`; production has its own registration. `NEXT_PUBLIC_AUTH_PROVIDER`, the `NEXT_PUBLIC_COGNITO_*` build variables, `cognito-config.ts` and the Cognito sign-out URL are removed. The test issuer has no sign-in page and the frontend knows nothing of it. The production build of the frontend fails, naming the variable, when `NEXT_PUBLIC_ENTRA_TENANT_ID` or `NEXT_PUBLIC_ENTRA_CLIENT_ID` is empty, instead of failing in the browser.

**D7. Matrix.** A product decision of 2026-11-12: operations has global control and finance is the reviewer. `docs/base-standards.md` (`CLAUDE.md` §3, §4, §6) and `docs/product-description.md` are updated by task 1.1 of this change. The daily status returns no cost field to any role and stays as it is. The roles of each route change in the routers' `require_roles`; `RoleName` gains `TRADING`. The route-protection test derives the roles from the application, so its expectations are rewritten around the matrix.

**D8. Tests.** Backend unit and API tests sign Entra-shaped tokens with a test key through shared helpers in `tests/fixtures`, with a static key provider or a simulated key address. The E2E global setup signs a test-issuer token for each role on every run with the local private key, and seeds one user per role with an `*.example.test` address; the session is injected into the browser storage under the key of the frontend's Entra authority and client, with the token as the access token. `get-token.sh`, its test, the role backup of `e2e/support/roles.ts` and `login.spec.ts` are removed, and no E2E presses sign-out, which would leave for the real tenant. `SEED_USER_EMAIL` stays for manual use with the real tenant. The real Entra sign-in is checked by hand and recorded in a report of the change.

**D9. Identifiers.** Tenant and application identifiers only in `.env`; placeholders everywhere else.

**D10. Navigation by role.** The navigation is driven by the roles from GET /users/me, loaded once per session and kept in memory. The 403 handling stays as a safety net. A change of roles applies on the next page load.

**D11. Test issuer and `APP_ENV`.** A test issuer shaped like Entra serves the E2E tests and API calls in development; it signs in no person. Its `iss` is `http://localhost/test-issuer/v2.0` and its audience is `api://adops360-test-issuer`, both constants in the code and not configurable, so a token of this issuer can never pass for one of the real tenant. It uses the `entra` kind: version 2, `scp` containing `access_as_user`, `oid` as the user claim and the optional `email`, verified by `IssuerTokenVerifier` against a static key provider that reads the PEM public key at the path in `TEST_ISSUER_PUBLIC_KEY_FILE`. It is on the issuer list only when that variable is set and `APP_ENV` is `development` or `test`. It fails closed: with the variable set and `APP_ENV` absent, `production` or any other value, the backend refuses to start with an error that names both variables. `docker-compose.prod.yml` sets `APP_ENV=production` under `environment:`, which takes precedence over `env_file`, and `scripts/verify_prod_images.sh` checks that the backend does not start with the test key. A script generates the key pair in a directory ignored by git, the private key with mode 600; neither key enters an image. Alternative rejected: an `iss` shaped like Entra's, because a leaked test key could then forge tokens for a misconfigured real issuer.

## Risks / Trade-offs

- [A first-access link by email could attach an identity to the wrong person if two tenants share an address] → the link needs a configured issuer; an existing link is never overwritten.
- [Finance loses the writes of schedules and platform rates] → breaking by intent; the existing finance tests change with the matrix.
- [An Entra access token does not carry `email` by default] → see Entra configuration requirement below.
- Mitigated: the Entra keys are cached for an hour and reloaded at most once a minute whatever the kid, with a five-second download timeout, so a token with an unknown kid cannot force downloads (task 19.1).
- The first-access link trusts the email claim of the Entra token, which Entra does not verify. In a single-tenant deployment with pre-registered users and an issuer pinned to the company tenant, the exposure is limited to those who can edit mail attributes, and it applies only to the first access: once linked, only the subject counts.
- [A leaked test private key could forge tokens] → the test issuer has its own fixed `iss`, which no real issuer shares, so a forged token is accepted only by a backend that lists the test issuer; and `APP_ENV` fails closed (D11): with the key set, the backend does not start unless `APP_ENV` is `development` or `test`, production pins `APP_ENV=production` outside `.env`, and `verify_prod_images.sh` checks the refusal.
- [The interface in development depends on the real tenant] → signing in from the browser needs network access, the development registration and a user of the tenant assigned to it; without them only the API can be called, with test-issuer tokens.
- [Development databases hold links to Cognito's `iss`] → a user linked to Cognito is rejected with `identity_link_conflict` when it presents an Entra or test-issuer token, because a user has a single (issuer, subject) link; `reset-data.sh` recreates the database, or both columns are set to NULL by hand. The E2E users are separate from `SEED_USER_EMAIL`, so the test issuer and the real tenant never compete for the same user.
- Activating and deactivating users leaves no audit trail yet; record who changed what and when before production.
- The post-logout redirect URI of the Entra registration must include the application origin, besides the callback URL.
- With Entra, the session lasts as long as the access token (about an hour) and is not renewed silently, so a long form can be lost at expiry. Silent renewal needs offline_access and is out of scope.

## Entra Configuration Requirement

The Entra application must be configured to put an `email` claim in the access token (an optional claim of the version 2 access token); it is required, because the link of the first access (D4) uses that email and no tool writes `identity_issuer` or `identity_subject` in advance. If the token carries no email and the pair (issuer, subject) is not yet linked, the result is 403 `user_not_registered` and nothing is stored, so the first access of that user cannot be linked. A user already linked is unaffected by a missing email.

The application defines no Entra application roles: the `roles` claim is ignored (D2).
