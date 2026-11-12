> Reports go in `docs/reports/`, as in the previous deliveries. This differs from the rule in `openspec/config.yaml`, which asks for `specs/<change-name>/reports/`.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Create or switch to feature branch `feature/entra-auth-and-roles` and verify `git branch --show-current` reports it

## 1. Rules and Documentation First

- [x] 1.1 Update `CLAUDE.md` (`docs/base-standards.md`: §3, §4, §6) and `docs/product-description.md` with the issuers, the `trading` role, operations as global control, finance as reviewer and the cost-figure rule; verify with a read-through of both files against the specs of this change

## 2. Configuration

- [ ] 2.1 Write failing tests that `Settings` reads a list of issuers (issuer, audience, key address, user claim, optional scope) and still derives `cognito_issuer` and `cognito_jwks_url`, then implement it and verify `tests/test_config.py` passes

## 3. Generic Token Verifier

- [ ] 3.1 Write failing tests with synthetic tokens and a simulated key address for issuer, audience, key address and subject claim configurable, a missing mandatory scope rejected, and an Entra identity token rejected
- [ ] 3.2 Generalise the verifier, move the Cognito identity-token and verified-email checks to the Cognito entry, and verify the tests of 3.1 and `test_cognito_token_verifier.py` pass

## 4. Composite Verifier

- [ ] 4.1 Write failing tests that an unknown `iss` gives 401 with no user lookup, that each issuer validates its own tokens and that a token for another audience is rejected
- [ ] 4.2 Implement the composite behind `IdentityTokenVerifier` and verify the tests pass

## 5. Wiring and Environment

- [ ] 5.1 Write a failing test that the verifier built by `providers.py` reflects the configured issuers, then wire it and add placeholders to `.env.example` and both compose files; verify no real identifier appears in tracked files

## 6. Database: Identity Columns (migration)

- [ ] 6.1 Write failing tests for the issuer and subject columns on `users` (nullable, unique on the pair, existing rows unaffected)
- [ ] 6.2 Add the columns and generate the Alembic migration with `--autogenerate`, review it by hand, and verify `upgrade head`, `downgrade -1` and `upgrade head` on a database holding data, and the schema-sync test

## 7. Repository by Identifier

- [ ] 7.1 Write failing tests, shared by the real and the in-memory repositories, for lookup by pair, lookup by email and storing a link; then implement both

## 8. Authentication Service

- [ ] 8.1 Write failing tests for lookup by pair, fall back to email for an unlinked user, link on first access, a linked user found with a changed email, a conflicting link rejected with 403 and unchanged, an unregistered identity rejected with 403 `user_not_registered` and no user created, and an unlinked identity whose token carries no email rejected with 403 `user_not_registered` and nothing stored
- [ ] 8.2 Write failing tests that the roles of a request are the stored ones for both issuers, that an Entra token whose `roles` claim differs from the database is authorised with the database roles, that a user without roles gets 403 on every protected route, and that two stored roles compose
- [ ] 8.3 Implement 8.1 and 8.2 in the service and verify all pass without a database

## 9. Role `trading`

- [ ] 9.1 Write failing tests that `RoleName` has `trading`, that the migration inserts its row, and that `grant_roles` and the seeds accept it
- [ ] 9.2 Implement the enum, an Alembic migration that inserts the role, the script and the seeds, and verify the tests pass

## 10. Access Matrix

- [ ] 10.1 Write failing tests rewriting `test_route_protection.py` around the matrix: margin routes accept operations and finance, schedule and platform-rate writes accept operations only, the delivery status accepts the four roles, and `trading` is forbidden on every other route
- [ ] 10.2 Change `require_roles` in `margin.py`, `masters.py`, `campaigns.py` and `campaign_status.py` to the matrix and verify the tests of 10.1 pass
- [ ] 10.3 Rewrite the negative cases of `test_margin_endpoint.py`, `test_margin_closings_endpoint.py` and `test_margin_masters_endpoints.py` so that a user WITHOUT the accepted roles is forbidden on `GET /margin`, `POST /margin/closings`, `POST /margin/rebate-schedules` and `POST /margin/platform-rates`, and that finance alone is forbidden on the two writes
- [ ] 10.4 Write failing tests that the delivery status for a user with only `business` or only `trading` contains no cost, revenue, rebate or margin field, then verify the existing response satisfies them

## 11. Active Switch

- [ ] 11.1 Write failing tests for the endpoint: operations sets a user inactive and active, an inactive user's next request with a still valid token is 403 `user_inactive`, and a user WITHOUT `operations` is forbidden
- [ ] 11.2 Implement the endpoint and the `grant_roles` option, and verify the tests pass

## 12. Frontend and E2E

- [ ] 12.1 Write failing Vitest tests that the provider is chosen by environment variable, that Entra requests `api://<client>/access_as_user` with `openid profile email` and sends the access token, and that Cognito still sends the identity token
- [ ] 12.2 Split `cognito-config.ts` by provider, update `AuthProvider` and `lib/api/client.ts`, and verify the tests pass
- [ ] 12.3 Add `operations` and `trading` sessions to `e2e/support/fixtures.ts` and a navigation spec per role, and verify they pass against the stack

## 13. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 13.1 Review every existing test that names a role (the files listed by `grep` for `RoleName` and the role strings in `backend/tests`, `e2e` and `frontend/tests`) and update the ones the matrix changes

## 14. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 14.1 Capture the database state, run the targeted tests and then the full backend and frontend suites, re-check the state and restore any change, and create the report at `docs/reports/YYYY-MM-DD-step-14-unit-test-and-db-verification.md`

## 15. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 15.1 With curl, check a token from an unknown issuer (401), a valid user without the role (403) on each guarded route changed by the matrix, an unregistered user (403) and the active switch taking effect on the next request; restore the database state afterwards

## 16. E2E Testing with Playwright (MANDATORY - AGENT MUST EXECUTE)

- [ ] 16.1 Run the Playwright specs for the finance, operations and trading sessions and record the result

## 17. Manual Entra Sign-in Check

- [ ] 17.1 Sign in once with the real Entra tenant, confirm the user is authorised with the roles stored in the database, and record the result in a report under `docs/reports/` (no identifier in the report)

## 18. Update Technical Documentation (MANDATORY)

- [ ] 18.1 Update `docs/deploy.md` and `.env.example` documentation for the issuer variables and the Entra application settings, with placeholders only
- [ ] 18.2 Verify `openspec validate entra-auth-and-roles` passes before archiving
