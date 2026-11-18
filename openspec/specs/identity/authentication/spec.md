# identity/authentication Specification

## Purpose
Defines which bearer tokens the system trusts, from which issuers, and where the roles of a request come from, so that authentication stays the identity provider's concern and authorisation stays the application's.

## Requirements

### Requirement: Bearer tokens are accepted only from configured issuers

The system SHALL accept a bearer token only when its issuer is on the list of configured issuers, and SHALL verify its signature against the keys of that issuer, its audience and its expiry. A token from any other issuer SHALL be rejected as an invalid token.

#### Scenario: A token from a configured issuer is accepted
- **WHEN** a valid token signed by the keys of a configured issuer reaches a protected route
- **THEN** the request is authenticated

#### Scenario: A token from an unknown issuer is rejected
- **WHEN** a token whose issuer is not on the list reaches a protected route
- **THEN** the request is rejected with 401 and no user lookup happens

#### Scenario: A token for another audience is rejected
- **WHEN** a correctly signed token carries an audience other than the one configured for its issuer
- **THEN** the request is rejected with 401

### Requirement: Entra access tokens must carry the application scope

The system SHALL require, for tokens of an Entra issuer, a version 2 access token whose `scp` claim contains `access_as_user`, and SHALL reject an identity token.

#### Scenario: A token without the scope is rejected
- **WHEN** an Entra token has a valid signature and audience but no `access_as_user` in `scp`
- **THEN** the request is rejected with 401

### Requirement: Entra is a required issuer

The system SHALL require `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` to build the Entra issuer, and SHALL refuse to start without either of them, with an error that names the missing variable.

#### Scenario: The backend does not start without an Entra variable
- **WHEN** the backend starts without `ENTRA_TENANT_ID` or without `ENTRA_CLIENT_ID`
- **THEN** it refuses to start with an error that names the missing variable

### Requirement: The test issuer is active only in development and test

The system SHALL add to the configured issuers a test issuer, whose `iss` is `http://localhost/test-issuer/v2.0` and whose audience is `api://adops360-test-issuer`, both fixed in the code, only when the variable `TEST_ISSUER_PUBLIC_KEY_FILE` names a PEM public key and `APP_ENV` is `development` or `test`, and SHALL verify its tokens against that key. When `TEST_ISSUER_PUBLIC_KEY_FILE` is set and `APP_ENV` is absent or has any other value, including `production`, the system SHALL refuse to start with an error that names both variables. When `TEST_ISSUER_PUBLIC_KEY_FILE` is set and `APP_ENV` is `development` or `test` but the file does not exist, cannot be read or does not hold a valid PEM public key, the system SHALL refuse to start with an error that names `TEST_ISSUER_PUBLIC_KEY_FILE`. Without `TEST_ISSUER_PUBLIC_KEY_FILE` the test issuer SHALL NOT be configured, whatever `APP_ENV` says.

#### Scenario: A test-issuer token is accepted in development and test
- **WHEN** `TEST_ISSUER_PUBLIC_KEY_FILE` names the public key, `APP_ENV` is `development` or `test`, and a valid token signed with the matching private key reaches a protected route
- **THEN** the request is authenticated

#### Scenario: The backend does not start with the test key outside development and test
- **WHEN** the backend starts with `TEST_ISSUER_PUBLIC_KEY_FILE` set and `APP_ENV` set to `production`, absent, or any value other than `development` and `test`
- **THEN** it refuses to start with an error that names `TEST_ISSUER_PUBLIC_KEY_FILE` and `APP_ENV`

#### Scenario: The backend does not start with an unusable test key
- **WHEN** the backend starts with `APP_ENV` set to `development` or `test` and `TEST_ISSUER_PUBLIC_KEY_FILE` naming a file that does not exist, cannot be read or does not hold a valid PEM public key
- **THEN** it refuses to start with an error that names `TEST_ISSUER_PUBLIC_KEY_FILE`

#### Scenario: A token with the test issuer is rejected when the issuer is not active
- **WHEN** `TEST_ISSUER_PUBLIC_KEY_FILE` is not set and a token whose `iss` is `http://localhost/test-issuer/v2.0` reaches a protected route
- **THEN** the request is rejected with 401 and no user lookup happens

### Requirement: Test-issuer tokens follow the Entra rules

The system SHALL verify tokens of the test issuer with the same rules as Entra tokens: a version 2 token whose `scp` claim contains `access_as_user`, with `oid` as the claim that identifies the user and the `email` claim as the address used on the first access.

#### Scenario: A test-issuer token without the scope is rejected
- **WHEN** a test-issuer token has a valid signature and audience but no `access_as_user` in `scp`
- **THEN** the request is rejected with 401

#### Scenario: A test-issuer token without oid is rejected
- **WHEN** a test-issuer token has a valid signature, audience and scope but no `oid` claim
- **THEN** the request is rejected with 401

#### Scenario: A test-issuer token of another version is rejected
- **WHEN** a test-issuer token has a valid signature, audience and scope but a `ver` other than `2.0`
- **THEN** the request is rejected with 401

#### Scenario: A test-issuer token signed with another key is rejected
- **WHEN** a token carries the `iss` `http://localhost/test-issuer/v2.0` and the audience `api://adops360-test-issuer` but is signed with a key other than the one configured in `TEST_ISSUER_PUBLIC_KEY_FILE`
- **THEN** the request is rejected with 401

### Requirement: Roles come only from the database

The system SHALL take the roles of every request from the user's stored roles, whatever the issuer of the token, and SHALL ignore any role information the token carries, including the `roles` claim of an Entra token.

#### Scenario: A token whose roles differ from the database is authorised with the database roles
- **WHEN** an Entra token carries `roles` with `finance` and the user's stored roles are `operations`
- **THEN** the request is authorised as `operations` only

#### Scenario: A user without roles is forbidden everywhere
- **WHEN** a valid token belongs to a registered user with no stored role
- **THEN** every protected route answers 403

#### Scenario: Several roles are composed
- **WHEN** a user holds two stored roles
- **THEN** a route is allowed if either role is accepted by it
