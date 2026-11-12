## Purpose

Defines which bearer tokens the system trusts, from which issuers, and where the roles of a request come from, so that authentication stays the identity provider's concern and authorisation stays the application's.

## ADDED Requirements

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

### Requirement: Cognito tokens keep their current checks

The system SHALL keep for the Cognito issuer the requirement of an identity token with a verified email and the client as audience.

#### Scenario: A Cognito token without a verified email is rejected
- **WHEN** a Cognito identity token has `email_verified` other than true
- **THEN** the request is rejected with 401

### Requirement: Roles come from the token for Entra and from the database for Cognito

The system SHALL take the roles of a request from the `roles` claim of the token for an Entra issuer, keeping only known role names, and from the user's stored roles for a Cognito issuer. The two sources SHALL NOT be combined.

#### Scenario: Entra roles are read from the token
- **WHEN** an Entra token carries `roles` with `finance` and the user's stored roles are `operations`
- **THEN** the request is authorised as `finance` only

#### Scenario: An Entra token without a known role gets no access
- **WHEN** an Entra token carries no known role
- **THEN** every protected route answers 403

#### Scenario: Several roles are composed
- **WHEN** a token carries two known roles
- **THEN** a route is allowed if either role is accepted by it
