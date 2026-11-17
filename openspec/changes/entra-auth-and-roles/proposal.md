## Why

AdOps360 moves to Microsoft Entra ID as its only identity provider, with every user in the company tenant, in development, in the end-to-end tests and in production; Cognito is removed. The end-to-end tests and API calls in development use a test issuer shaped like Entra, active only outside production, so the backend accepts tokens from a list of issuers. The business also needs a `trading` profile, and operations becomes the global control profile that sees the margin and maintains the rebate and platform-rate data, and finance becomes the reviewer.

**Phase 1** per `docs/product-description.md` §6: this is cross-cutting access work on top of the phase 1 views, and it adds no domain entity of the economic model.

## What Changes

- **Configurable token issuers.** A list of allowed issuers, each with issuer, audience, key source, the claim that identifies the user and, optionally, a mandatory scope. Entra is always on the list; the Cognito variables and the Cognito issuer are removed. A token whose `iss` is not on the list is rejected.
- **Entra access tokens** (version 2) must carry the scope `access_as_user`; identity tokens are rejected.
- **Test issuer.** An issuer with a fixed `iss` of its own and a fixed test audience, verified with the Entra rules against a local public key. It is on the list only when the variable with the key path is set and `APP_ENV` is `development` or `test`; with the key set and any other `APP_ENV`, or none, the backend refuses to start. It signs in no person: it serves the end-to-end tests and API calls in development.
- **Stable user identity.** A user is linked to the pair (issuer, subject): `oid` for Entra and for the test issuer. The first access links a registered user with no link by email; a conflicting link is rejected. Authentication never creates users.
- **Roles come only from the database**, for every issuer. The Entra token only authenticates; its `roles` claim is ignored. A first access with no email in the token and no stored link is rejected as not registered.
- **New role `trading`.**
- **Active switch.** An endpoint for operations, and an option of the administration script, set a user active or inactive; it takes effect on the next request.
- **Access matrix** applied to the existing routes. **BREAKING**: finance loses `POST /margin/rebate-schedules` and `POST /margin/platform-rates`, and operations gains the margin reads and the month closing. Cost, revenue, rebate and margin figures are returned only to operations and finance; the daily status carries none of them for any role.
- **Frontend** signs in with Entra only, in development too (the development registration with `http://localhost` redirect URIs): it requests `api://<client>/access_as_user` and sends the access token. The provider variable and the Cognito code are removed.
- **End-to-end tests** sign a test-issuer token in their global setup on every run and seed one user per role with `*.example.test` addresses; the Cognito token script and the real sign-in spec are removed.
- Tenant and application identifiers live only in `.env`; documents and tests use placeholders.

## Capabilities

### New Capabilities

- `identity/authentication`: which tokens the system accepts, from which issuers, and where the roles of a request come from.
- `identity/user-identity`: how a token is joined to a registered user, the `trading` role and the active switch.
- `identity/access-matrix`: the roles each existing route accepts and the restriction on money figures.

### Modified Capabilities

- `campaign/daily-status`: who reads the daily status, and who may receive cost and margin figures.
- `finance/margin-calculation`: margin access moves from finance only to operations and finance.
- `finance/margin-reporting`: reporting access and `GET /margin` move to operations and finance.
- `finance/rebate-accrual`: `POST /margin/closings` moves to operations and finance.
- `finance/rebate-schedule`: schedules and platform rates are created by operations.
- `finance/platform-rate`: overrides are configured by operations.

## Impact

- Backend: `Settings`, the token verifier and its wiring, `AuthenticationService`, `User` and `VerifiedIdentity`, `UserRepository`, `RoleName`, every `require_roles` of the routers, `scripts/grant_roles.py` and the seeds; one Alembic migration (identity columns and the `trading` row).
- Frontend: `lib/auth` and `lib/api/client.ts`; E2E sessions for `operations` and `trading`.
- Configuration: `.env.example`, `docker-compose*.yml`.
- Documentation: `CLAUDE.md` §6, `docs/product-description.md`, `docs/deploy.md`.

## Non-goals

- The screen to activate and deactivate users.
- The trading views of the control desk and their purchase cost.
- Assigning Entra roles by group.
- The test instance with HTTPS.
