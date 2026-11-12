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
- **THEN** the request is rejected with 403 `identity_link_conflict` and the stored link does not change

#### Scenario: An unlinked identity without an email is forbidden
- **WHEN** a valid token carries no email and its pair is not linked to any user
- **THEN** the request is rejected with 403 `user_not_registered` and nothing is stored

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

The system SHALL let a user with the `operations` role set another user as inactive or active through `POST /users/activation`, with the email and the wanted state in the request body (never in the path, so the email does not reach the access logs), and SHALL reject every request of an inactive user on its next request, whatever its token says. The response SHALL carry only the email and the resulting state. Setting the state a user already has SHALL succeed. An email that matches no user SHALL be answered 404 `user_not_found`, and an invalid body 422, without echoing the body.

#### Scenario: An inactive user is rejected at once
- **WHEN** operations deactivates a user whose token is still valid
- **THEN** that user's next request is rejected with 403 `user_inactive`

#### Scenario: A reactivated user gets in again
- **WHEN** operations reactivates that user
- **THEN** the user's next request with the same token is accepted

#### Scenario: Other roles cannot change the state
- **WHEN** a user without `operations` calls the endpoint
- **THEN** the request is rejected with 403 and nothing changes

#### Scenario: An unknown email is not found
- **WHEN** operations sets the state of an email that matches no user
- **THEN** the request is rejected with 404 `user_not_found`

#### Scenario: Setting the state a user already has succeeds
- **WHEN** operations deactivates an inactive user or activates an active one
- **THEN** the request succeeds and the state is unchanged

#### Scenario: The response carries no other data of the user
- **WHEN** the endpoint answers, with success or with an error
- **THEN** a success carries only the email and the state, and an error only a code and a message

### Requirement: Operations cannot lock itself out

The system SHALL reject, with 409, the deactivation of the caller's own account (`cannot_deactivate_self`) and the deactivation of the last active user holding `operations` (`last_active_operations_user`), and SHALL decide the second in the database inside the transaction that changes the state, so that two simultaneous deactivations cannot leave no active operations user. Reactivation SHALL never be rejected for these reasons.

#### Scenario: Operations cannot deactivate itself
- **WHEN** an operations user deactivates its own account
- **THEN** the request is rejected with 409 `cannot_deactivate_self` and the account stays active

#### Scenario: The last active operations user cannot be deactivated
- **WHEN** a deactivation would leave no active user holding `operations`, for instance two operations users deactivating each other at the same time
- **THEN** the request is rejected with 409 `last_active_operations_user` and that user stays active

#### Scenario: Another operations user can be deactivated while one remains
- **WHEN** an operations user deactivates a different operations user and the caller remains active
- **THEN** the request succeeds

### Requirement: The administration script sets the active state

The system SHALL provide `scripts/set_user_active.py`, which sets a user active or inactive by email using the same connection as `grant_roles.py`, without the lock-out protections of the endpoint, and which reports clearly when the email matches no user, without echoing it.

#### Scenario: The script deactivates and reactivates a user
- **WHEN** the script runs with an existing email and `--inactive`, then `--active`
- **THEN** the user is inactive, then active again

#### Scenario: The script reports an unknown email
- **WHEN** the script runs with an email that matches no user
- **THEN** it reports that the user was not found, exits with its own code and changes nothing

### Requirement: A user can read its own roles

The system SHALL expose `GET /users/me` to users holding the `operations`, `business`, `finance` or `trading` role, answering the names of the roles the caller holds in the database, ordered by name, and nothing else, so that the interface can show only the links and buttons the caller may use. The roles SHALL come from the database and never from the token.

#### Scenario: A user with two roles receives both, ordered by name
- **WHEN** a user holding `operations` and `finance` calls the endpoint
- **THEN** the response lists `finance` and then `operations`

#### Scenario: A user with one role receives that role
- **WHEN** a user holding only `trading` calls the endpoint
- **THEN** the response lists only `trading`

#### Scenario: A user with no known role is forbidden
- **WHEN** a user holding none of the four roles calls the endpoint
- **THEN** the request is rejected with 403, as on every other protected route

#### Scenario: The response carries only the roles
- **WHEN** the endpoint answers, with success or with an error
- **THEN** a success holds only the list of roles, and neither response holds an email, an identifier or a money figure

#### Scenario: An inactive user is forbidden
- **WHEN** a user who has been deactivated calls the endpoint with a token that is still valid
- **THEN** the request is rejected with 403 `user_inactive`

#### Scenario: A request without a valid token is unauthenticated
- **WHEN** the endpoint is called without a valid token
- **THEN** the request is rejected with 401
