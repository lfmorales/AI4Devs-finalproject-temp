## Purpose

Defines how an authenticated identity is joined to a registered user, who may create users, which roles exist, and how a user is switched off without waiting for the token to expire.

## ADDED Requirements

### Requirement: A user is linked to its identity by issuer and subject

The system SHALL identify a registered user by the pair formed by the issuer and the subject claim configured for that issuer, and SHALL fall back to the email only for a user with no link yet.

#### Scenario: The first access links the identity
- **WHEN** an authenticated identity has no linked user and its email matches a registered user with no link
- **THEN** the pair is stored on that user and the request proceeds

#### Scenario: A linked user is found even if the email changed
- **WHEN** a token carries a pair already linked to a user and a different email
- **THEN** the request is authenticated as that user

#### Scenario: A conflicting link is rejected
- **WHEN** the email matches a user already linked to a different pair
- **THEN** the request is rejected with 403 and the stored link does not change

### Requirement: Users are never created by authentication

The system SHALL NOT create a user when an authenticated identity matches none.

#### Scenario: An unregistered identity is forbidden
- **WHEN** a valid token matches no registered user, by pair or by email
- **THEN** the request is rejected with 403 `user_not_registered` and no user is created

### Requirement: There is a trading role

The system SHALL define the role `trading` alongside `operations`, `business` and `finance`.

#### Scenario: The role exists after the migration
- **WHEN** the migrations have run
- **THEN** the roles table holds `trading`

### Requirement: Operations can deactivate and reactivate a user

The system SHALL let a user with the `operations` role set another user as inactive or active, and SHALL reject every request of an inactive user on its next request, whatever its token says.

#### Scenario: An inactive user is rejected at once
- **WHEN** operations deactivates a user whose token is still valid
- **THEN** that user's next request is rejected with 403 `user_inactive`

#### Scenario: Other roles cannot change the state
- **WHEN** a user without `operations` calls the endpoint
- **THEN** the request is rejected with 403
