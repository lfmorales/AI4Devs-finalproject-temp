# Step 17: sign-in against the real Entra tenant

Date: 2026-11-18. Change: entra-auth-and-roles. Branch: feature/entra-auth-and-roles at f70cb1d.

This check is done by hand because no automated test signs in against the real tenant: the end-to-end tests use the test issuer and never reach Microsoft (design D8).

## Environment

- Development stack of the worktree, Compose project adops360-entra, frontend and backend built from f70cb1d.
- The development app registration of the company tenant: single organisation, single-page application platform with the redirect URIs `<origin>/callback` and `<origin>`, where `<origin>` is `http://localhost`.
- The development user given in SEED_USER_EMAIL, assigned to the application, with the roles operations and finance in the database.
- Fresh data from `e2e/scripts/reset-data.sh`, so the user starts with no identity link.

No tenant, application or user identifier, and no address, is recorded in this report.

## Checks

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Identity link of the user before the first access (issuer set, subject set) | f, f | f, f |
| 2 | Sign-in from the browser with the Microsoft account and multi-factor authentication | The application opens with the links of the operations and finance profiles | As expected |
| 3 | Identity link after the first access, and whether the issuer is the Entra issuer | t, t, Entra | t, t, Entra |
| 4 | Sign-out | Goes through Microsoft and returns to the application | As expected |
| 5 | Second sign-in | Enters without errors, now by the stored (issuer, oid) pair | As expected |
| 6 | Identity link after the second access | Unchanged: t, t, Entra | t, t, Entra |

The link check reads only whether the two identity columns are set and whether the issuer starts with the Entra authority; it prints neither the tenant nor the subject.

## What this covers

- The frontend signs in with Entra only and sends the access token with the access_as_user scope.
- The backend accepts a real Entra access token through the cached key provider of task 19.1.
- The first access links an existing user by the email claim and stores the (issuer, oid) pair; later accesses use the pair. Authentication creates no user.
- Sign-out returns to `<origin>`, which confirms that redirect URI in the registration.

## Covered elsewhere

- Missing, altered or foreign-key tokens (401), unregistered user (403), missing role (403) and the active-user switch: unit and API tests, and the curl checks of step 15 with test-issuer tokens.
- The access matrix in the browser for every profile: the end-to-end tests of step 16.
