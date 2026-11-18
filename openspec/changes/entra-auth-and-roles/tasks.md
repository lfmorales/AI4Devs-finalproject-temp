> Reports go in `docs/reports/`, as in the previous deliveries. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/`.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Create or switch to feature branch `feature/entra-auth-and-roles` and verify `git branch --show-current` reports it

## 1. Rules and Documentation First

- [x] 1.1 Update `CLAUDE.md` (`docs/base-standards.md`: §3, §4, §6) and `docs/product-description.md` with the issuers, the `trading` role, operations as global control, finance as reviewer and the cost-figure rule; verify with a read-through of both files against the specs of this change

## 2. Configuration

- [x] 2.1 Write failing tests that `Settings` reads a list of issuers (issuer, audience, key address, user claim, optional scope) and still derives `cognito_issuer` and `cognito_jwks_url`, then implement it and verify `tests/test_config.py` passes (Superseded by 21.3 and 21.7: the test issuer is added to the list and the Cognito settings are removed)

## 3. Generic Token Verifier

- [x] 3.1 Write failing tests with synthetic tokens and a simulated key address for issuer, audience, key address and subject claim configurable, a missing mandatory scope rejected, and an Entra identity token rejected
- [x] 3.2 Generalise the verifier, move the Cognito identity-token and verified-email checks to the Cognito entry, and verify the tests of 3.1 and `test_cognito_token_verifier.py` pass (Superseded by 21.7: the Cognito entry, its checks and `test_cognito_token_verifier.py` are removed)

## 4. Composite Verifier

- [x] 4.1 Write failing tests that an unknown `iss` gives 401 with no user lookup, that each issuer validates its own tokens and that a token for another audience is rejected
- [x] 4.2 Implement the composite behind `IdentityTokenVerifier` and verify the tests pass

## 5. Wiring and Environment

- [x] 5.1 Write a failing test that the verifier built by `providers.py` reflects the configured issuers, then wire it and add placeholders to `.env.example` and both compose files; verify no real identifier appears in tracked files

## 6. Database: Identity Columns (migration)

- [x] 6.1 Write failing tests for the issuer and subject columns on `users` (nullable, unique on the pair, existing rows unaffected)
- [x] 6.2 Add the columns and generate the Alembic migration with `--autogenerate`, review it by hand, and verify `upgrade head`, `downgrade -1` and `upgrade head` on a database holding data, and the schema-sync test

## 7. Repository by Identifier

- [x] 7.1 Write failing tests, shared by the real and the in-memory repositories, for lookup by pair, lookup by email and storing a link; then implement both

## 8. Authentication Service

- [x] 8.1 Write failing tests for lookup by pair, fall back to email for an unlinked user, link on first access, a linked user found with a changed email, a conflicting link rejected with 403 and unchanged, an unregistered identity rejected with 403 `user_not_registered` and no user created, and an unlinked identity whose token carries no email rejected with 403 `user_not_registered` and nothing stored
- [x] 8.2 Write failing tests that the roles of a request are the stored ones for both issuers, that an Entra token whose `roles` claim differs from the database is authorised with the database roles, that a user without roles gets 403 on every protected route, and that two stored roles compose
- [x] 8.3 Implement 8.1 and 8.2 in the service and verify all pass without a database

## 9. Role `trading`

- [x] 9.1 Write failing tests that `RoleName` has `trading`, that the migration inserts its row, and that `grant_roles` and the seeds accept it
- [x] 9.2 Implement the enum, an Alembic migration that inserts the role, the script and the seeds, and verify the tests pass

## 10. Access Matrix

- [x] 10.1 Write failing tests rewriting `test_route_protection.py` around the matrix: margin routes accept operations and finance, schedule and platform-rate writes accept operations only, the delivery status accepts the four roles, and `trading` is forbidden on every other route
- [x] 10.2 Change `require_roles` in `margin.py`, `masters.py`, `campaigns.py` and `campaign_status.py` to the matrix and verify the tests of 10.1 pass
- [x] 10.3 Rewrite the negative cases of `test_margin_endpoint.py`, `test_margin_closings_endpoint.py` and `test_margin_masters_endpoints.py` so that a user WITHOUT the accepted roles is forbidden on `GET /margin`, `POST /margin/closings`, `POST /margin/rebate-schedules` and `POST /margin/platform-rates`, and that finance alone is forbidden on the two writes
- [x] 10.4 Write failing tests that the delivery status for a user with only `business` or only `trading` contains no cost, revenue, rebate or margin field, then verify the existing response satisfies them

## 11. Active Switch

- [x] 11.1 Write failing tests for the endpoint: operations sets a user inactive and active, an inactive user's next request with a still valid token is 403 `user_inactive`, and a user WITHOUT `operations` is forbidden
- [x] 11.2 Implement the endpoint and the `set_user_active.py` script, and verify the tests pass

## 12. Frontend and E2E

- [x] 12.1 Write failing Vitest tests that the provider is chosen by environment variable, that Entra requests `api://<client>/access_as_user` with `openid profile email` and sends the access token, and that Cognito still sends the identity token (Superseded by 21.6: the frontend signs in with Entra only and the provider choice is removed)
- [x] 12.2 Split `cognito-config.ts` by provider, update `AuthProvider` and `lib/api/client.ts`, and verify the tests pass (Superseded by 21.6: `cognito-config.ts` and the Cognito branches are removed)
- [x] 12.3 Add `operations` and `trading` sessions to `e2e/support/fixtures.ts` and a navigation spec per role, and verify they pass against the stack
- [x] 12.4 Add `GET /users/me`, which answers the caller's roles from the database, with its spec scenarios, its row in the access matrix and its API tests
- [x] 12.5 Use the roles of `GET /users/me` in the frontend to show only the links and the buttons the user may use, replacing the links hidden after a 403 and the buttons shown to profiles that would receive 403

## 13. Review and Update Existing Unit Tests (MANDATORY)

- [x] 13.1 Review every existing test that names a role (the files listed by `grep` for `RoleName` and the role strings in `backend/tests`, `e2e` and `frontend/tests`) and update the ones the matrix changes

## 14. Run Unit Tests and Verify Database State (MANDATORY)

- [x] 14.1 Capture the database state, run the targeted tests and then the full backend and frontend suites, re-check the state and restore any change, and create the report at `docs/reports/YYYY-MM-DD-step-14-unit-test-and-db-verification.md`

## 15. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 15.1 With curl, check a token from an unknown issuer (401), a valid user without the role (403) on each guarded route changed by the matrix, an unregistered user (403) and the active switch taking effect on the next request; restore the database state afterwards

## 16. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [x] 16.1 Run the Playwright specs for the finance, operations and trading sessions and record the result

## 17. Manual Entra Sign-in Check

- [ ] 17.1 Sign in once with the real Entra tenant, confirm the user is authorised with the roles stored in the database, and record the result in a report under `docs/reports/` (no identifier in the report)

## 18. Update Technical Documentation (MANDATORY)

- [x] 18.1 Update `docs/deploy.md` and `.env.example` documentation for the issuer variables and the Entra application settings, with placeholders only
- [x] 18.2 Update README §3 and the data model documentation so they show the `identity_issuer` and `identity_subject` columns of `users`, their unique pair and the check that sets them together
- [x] 18.3 Verify `openspec validate entra-auth-and-roles` passes before archiving

## 19. Key Download Hardening

- [x] 19.1 Limit the key reload rate and the download timeout, with a test
- [x] 19.2 Insert all four roles from a migration, idempotently, so a fresh database does not depend on the seed script
- [x] 19.3 Remove count_active_with_role, which nothing uses in production, with its tests; done together with 21.7 (the removal of CognitoTokenVerifier moved to 21.7)

## 20. Test Fixtures

- [x] 20.1 Extract the token and key helpers shared by the identity API tests into tests/fixtures (Absorbed by 21.1)

## 21. Entra Only, with a Test Issuer

> Each task leaves the backend, frontend and E2E suites green. Cognito keeps working until nothing uses it (21.6 and 21.7). The mandatory steps 13 to 18 are run again after this section.

- [x] 21.1 Extract the RSA test key, the static key provider and an Entra-shaped token builder (`iss`, `aud`, `ver` 2.0, `scp`, `oid`, `tid`, `email`) shared by the identity tests into `tests/fixtures`, and move the existing tests onto them; verify the same tests pass unchanged in number
- [x] 21.2 Write failing tests for a production static key provider that reads one PEM public key and resolves a token signed with the matching private key, and rejects one signed with another key; then implement it next to `IssuerTokenVerifier` and verify the tests pass
- [x] 21.3 Write failing tests that `Settings` adds the test issuer (fixed `iss` `http://localhost/test-issuer/v2.0`, audience `api://adops360-test-issuer`, `entra` kind, `oid`, `access_as_user`) only with `TEST_ISSUER_PUBLIC_KEY_FILE` set and `APP_ENV` `development` or `test`; that it refuses to start, naming both variables, with the key set and `APP_ENV` absent, `production` or any other value; that the issuer is absent without the key; that `providers.py` injects the static provider for it; and that a test-issuer token without `scp`, without `oid` or with another `ver` is rejected and a test-issuer token is rejected when the issuer is not active. Then implement and verify the tests pass
- [x] 21.4 Write a failing test for a script that generates the test key pair in a directory ignored by git, with the private key at mode 600 and no overwrite of an existing pair; then implement it, exclude the key directory in `.gitignore` and in the `.dockerignore` of each build context (backend and frontend), with a check that proves it (`git check-ignore` on both keys and no key in the build context sent to Docker), mount the public key into the backend and set `APP_ENV=development` in `docker-compose.yml`, set `APP_ENV=production` under `environment:` in `docker-compose.prod.yml`, and extend `scripts/verify_prod_images.sh` to check that the backend does not start with the test key; verify no key enters an image
- [x] 21.5 Move the E2E to the test issuer: write failing unit tests for the token signing of the global setup and the storage key built from the frontend's Entra authority and client; then sign one token per role on every run, seed one user per role with `*.example.test` addresses, inject the token as the access token, and remove `get-token.sh`, its test, the role backup of `e2e/support/roles.ts` and `login.spec.ts`; rebuild the frontend of the stack with Entra and verify every E2E spec passes with no sign-out pressed
- [x] 21.6 Write failing Vitest tests that the frontend signs in with Entra only (settings, access token, sign-out through Entra) with no provider variable; then remove `NEXT_PUBLIC_AUTH_PROVIDER`, `cognito-config.ts` (moving `CALLBACK_PATH`), `getLogoutUrl`, the Cognito branches of `AuthProvider` and `lib/api/client.ts`, and the `NEXT_PUBLIC_COGNITO_*` build variables of the Dockerfile and both compose files; verify the Vitest suite and the E2E pass
- [x] 21.7 Write failing tests that `Settings` requires `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` and has no Cognito setting or kind; then remove the Cognito settings, the `cognito` kind and its checks, `CognitoTokenVerifier` and their tests, and `count_active_with_role` with its tests (19.3), the `COGNITO_*` variables of both compose files, `.env.example` and `verify_prod_images.sh`, and the Cognito comments in `alembic/env.py`, `run_ingestion.py` and the domain; verify the backend suite and the E2E pass and `git grep -i cognito` finds nothing outside documentation and reports
- [x] 21.8 Update the documentation for Entra only and the test issuer (README authentication, installation and architecture; `docs/deploy.md` with the Entra registration settings; `.env.example`; `docs/backend-standards.md`, `docs/frontend-standards.md` and `docs/base-standards.md`; `openspec/config.yaml`; `ai-specs/agents`), with placeholders only; verify no UUID and no real address in the touched files, then mark 18.1 and run `openspec validate entra-auth-and-roles` for 18.3
