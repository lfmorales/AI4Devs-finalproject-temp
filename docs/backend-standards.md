---
description: Backend standards and best practices for the AdOps360 API.
alwaysApply: false
---

# Backend Project Standards and Best Practices

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Architecture Overview](#architecture-overview)
4. [Domain-Driven Design Principles](#domain-driven-design-principles)
5. [SOLID and DRY Principles](#solid-and-dry-principles)
6. [Coding Standards](#coding-standards)
7. [API Design Standards](#api-design-standards)
8. [Authentication and Authorization](#authentication-and-authorization)
9. [Database Patterns](#database-patterns)
10. [Spreadsheet and DSP Report Ingestion](#spreadsheet-and-dsp-report-ingestion)
11. [Testing Standards](#testing-standards)
12. [Performance Best Practices](#performance-best-practices)
13. [Security Best Practices](#security-best-practices)
14. [Development Workflow](#development-workflow)
15. [Deployment](#deployment)

## Overview

This document outlines the best practices, conventions and standards used in the AdOps360 backend. The backend follows Domain-Driven Design (DDD) principles and a layered architecture, so that the economic rules specified in [Product Description](./product-description.md) live in one place and can be tested without a database, an HTTP server or a DSP.

That constraint is not stylistic. The margin calculation is the product: it carries tiered rebate accrual, versioned purchase orders, frozen applied rates and chronological bracket attribution. Rules of that shape belong in a domain layer with no infrastructure dependencies, where they can be exercised directly.

## Technology Stack

### Core Technologies
- **Python 3.12**: Runtime.
- **FastAPI**: Web framework, request validation and OpenAPI generation.
- **Pydantic**: Request and response models, supplied by FastAPI.

### Database & ORM
- **PostgreSQL**: Relational database, running in its own container with a named volume.
- **SQLAlchemy**: ORM and query layer.
- **Alembic**: Schema migrations.

### Data Processing
- **pandas**: Tabular processing of commercial-offer spreadsheets and DSP reports.
- **openpyxl**: Reading and writing `.xlsx` files.

### Authentication
- **Microsoft Entra ID**: The only identity provider. The backend validates its access tokens; it does not issue them. In development and the end-to-end tests a test issuer shaped like Entra is also accepted (see [Token Verification](#token-verification)).

### File Storage
- **Amazon S3**: Uploaded purchase-order and offer spreadsheets, and reports downloaded from the DSPs.

### Testing Framework
- **pytest**: Test framework.
- **httpx**: HTTP client for API-level tests against the FastAPI application.
- **Test Location**: `tests/`, mirroring the package structure under test.

## Architecture Overview

### Domain-Driven Design (DDD)

Domain-Driven Design focuses on modelling software according to business logic and domain knowledge. Centring development on a deep understanding of the domain makes complex systems tractable.

**Benefits:**
- **Improved Communication**: Promotes a common language between developers and domain experts, reducing interpretation errors. In this project that language is already written down — campaign period, purchase order version, rebate bracket, applied rate — and the code must use the same words.
- **Clear Domain Models**: Models reflect business rules and processes accurately.
- **High Maintainability**: Dividing the system into subdomains eases maintenance and evolution.

### Layered Architecture

**Presentation Layer** (`app/presentation/`)
- Routers declare API endpoints and the roles they require.
- Handlers translate HTTP to and from application services. They contain no business logic.

**Application Layer** (`app/application/`)
- Services contain orchestration and use-case logic.
- Services depend on repository interfaces, never on SQLAlchemy directly.

**Domain Layer** (`app/domain/`)
- Entities and value objects define the core model.
- Repository interfaces define data access contracts.
- Pure business logic with no external dependencies. The economic model lives here.

**Infrastructure Layer** (`app/infrastructure/`)
- SQLAlchemy repository implementations satisfying domain interfaces.
- DSP API clients, S3 access, spreadsheet parsers, token verification for the configured issuers.

The dependency rule is one-directional: presentation depends on application, application depends on domain, infrastructure depends on domain. **Nothing depends on infrastructure.**

### Project Structure

```
backend/
├── app/
│   ├── domain/
│   │   ├── models/           # Entities and value objects
│   │   ├── services/         # Pure domain services (margin, rebate brackets)
│   │   └── repositories/     # Repository interfaces
│   ├── application/
│   │   └── services/         # Use-case orchestration
│   ├── presentation/
│   │   ├── routers/          # FastAPI routers
│   │   ├── schemas/          # Pydantic request/response models
│   │   └── dependencies/     # Auth and role dependencies
│   ├── infrastructure/
│   │   ├── persistence/      # SQLAlchemy models and repository implementations
│   │   ├── dsp/              # Adform, Equativ and Displayce clients
│   │   ├── spreadsheets/     # pandas/openpyxl parsers
│   │   ├── storage/          # S3 access
│   │   └── auth/             # Token verification, one verifier per configured issuer
│   ├── config.py             # Settings loaded from environment variables
│   └── main.py               # Application entry point
├── alembic/
│   ├── versions/             # Migration scripts
│   └── env.py
├── tests/
│   ├── domain/
│   ├── application/
│   ├── api/                  # httpx tests against the app
│   └── fixtures/             # Builders and sample files
├── alembic.ini
├── pyproject.toml
└── Dockerfile
```

## Domain-Driven Design Principles

### Entities

Entities have identity that persists over time. Behaviour lives with the data it governs, not in a service that reaches into a dictionary.

**Avoid:**
```python
# Campaign data as a bare dict, with rules scattered across callers
campaign = {"contracted_impressions": 726202, "sale_cpm": 5.0}
revenue = campaign["contracted_impressions"] * campaign["sale_cpm"] / 1000
```

**Prefer:**
```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ContractedVolume:
    """Volume and price agreed on the purchase order version in force."""

    impressions: int
    sale_cpm: Decimal

    def revenue(self) -> Decimal:
        return Decimal(self.impressions) * self.sale_cpm / 1000
```

### Value Objects

Quantities defined by their value, not by identity, are modelled as frozen dataclasses. Money, rates, impression counts and bracket thresholds are value objects.

**Monetary amounts and rates use `Decimal`, never `float`.** Rebate rates are applied to revenue and accumulate across a year; binary floating point introduces drift that shows up in reconciliation.

### Repositories

The domain declares what it needs; infrastructure decides how to provide it.

```python
from abc import ABC, abstractmethod


class CampaignRepository(ABC):
    @abstractmethod
    def get_by_id(self, campaign_id: int) -> Campaign | None: ...

    @abstractmethod
    def list_by_period(self, year: int, month: int) -> list[Campaign]: ...
```

The SQLAlchemy implementation lives in `app/infrastructure/persistence/` and is injected where the interface is required. Domain and application tests use in-memory implementations and need no database.

### Domain Exceptions

The domain raises its own exceptions. It never raises `HTTPException`, and it never knows about status codes. The presentation layer maps domain exceptions to HTTP responses.

```python
class DomainError(Exception):
    """Base class for domain rule violations."""


class UnmappedCampaignLineError(DomainError):
    """A campaign line has no DSP mapping and cannot ingest delivery."""
```

## SOLID and DRY Principles

- **Single Responsibility**: A module has one reason to change. Parsing a DSP report, mapping it to campaign lines and computing a margin are three responsibilities, not one function.
- **Open/Closed**: Adding a DSP must not modify existing clients. Each client implements a common interface; the ingestion service depends on the interface.
- **Liskov Substitution**: Any repository implementation is substitutable for its interface, including test doubles.
- **Interface Segregation**: Narrow interfaces. A service that only reads campaigns depends on a read interface, not one that also writes.
- **Dependency Inversion**: High-level policy depends on abstractions. The margin calculation depends on a repository interface, never on a SQLAlchemy session.
- **DRY**: A business rule is expressed once. The rebate bracket ladder, the applied-rate freezing rule and the channel resolution rule each exist in exactly one place — duplicating them is how two systems end up disagreeing about the same number, which is the failure this product exists to correct.

## Coding Standards

### Type Safety

Per the core principles, **all code is fully typed**. Every function signature carries parameter and return annotations, including `None` returns. Untyped `dict` and `Any` are not acceptable in domain or application code; define a dataclass or a Pydantic model.

### Naming

Names come from the domain vocabulary in [Product Description](./product-description.md). Use `contracted_impressions` and `delivered_impressions`, never `impressions` — the distinction between them carries the revenue model, and a name that hides it invites the exact conflation §5 warns against.

- Modules and functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private helpers: a single leading underscore

### Functions

- Prefer small functions with one responsibility.
- Prefer explicit arguments over flags that change behaviour.
- Return values rather than mutating arguments.
- Raise domain exceptions rather than returning error sentinels.

### Comments

Comments explain *why*, never *what*. A comment restating the code is noise; a comment recording that a rule is deliberate — that the platform cost is included in the margin while the Equativ-facing figure excludes it — is worth keeping.

## API Design Standards

### Resource Naming

- Plural nouns for collections: `/campaigns`, `/agencies`, `/purchase-orders`
- Nested resources reflect the domain hierarchy: `/campaigns/{id}/periods`
- `kebab-case` in paths, `snake_case` in JSON bodies

### HTTP Semantics

| Method | Use |
|---|---|
| `GET` | Retrieve, never mutate |
| `POST` | Create, or trigger an operation such as an ingestion run |
| `PUT` | Replace a resource in full |
| `PATCH` | Partial update |
| `DELETE` | Remove |

### Status Codes

- `200` retrieved or updated, `201` created, `204` deleted
- `400` malformed request, `422` validation failure (FastAPI's default for Pydantic)
- `401` missing or invalid token, `403` valid token without the required role
- `404` not found, `409` conflict with current state
- `500` unexpected failure, never used to signal a business rule violation

### Schemas

Request and response models are Pydantic models in `app/presentation/schemas/`, separate from domain entities. The two diverge deliberately: the API surface must be free to change without disturbing the domain, and domain entities must never be serialised directly.

### Errors

Errors return a consistent body with a machine-readable code and a human-readable message. Never leak stack traces, SQL or DSP credentials in a response.

## Authentication and Authorization

The split is defined in [Base Standards §6](./base-standards.md#6-authorization-model). This section covers implementation.

### Token Verification

Every request carrying a bearer token has it verified against the configured issuers, which `Settings` builds when the application starts. A composite verifier reads the unverified `iss`, picks that issuer's verifier and delegates; an unknown `iss` is an invalid token before any user lookup. Each issuer's verifier checks signature, expiry, issuer and audience, and the rules of the `entra` kind: version 2 and the scope `access_as_user`. Verification lives in `app/infrastructure/auth/`.

- **Entra** is always configured: `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` are required, and without them the backend refuses to start. Its keys come from the tenant's key address.
- **The test issuer** is configured only when `TEST_ISSUER_PUBLIC_KEY_FILE` is set and `APP_ENV` is exactly `development` or `test`. Its `iss` and audience are fixed in code, and its key is a local PEM public key. With the key set and any other `APP_ENV`, or an unusable key file, the backend refuses to start.

### Resolving the User

The user is joined to the token by the pair **(issuer, subject)**, where the subject is the `oid` claim. The **email claim** is used only on the first access, to link a registered user that has no link yet. `AuthenticationService` does it:

```python
def authenticate(self, token: str) -> User:
    identity = self._token_verifier.verify(token)                 # 401 if invalid
    user = self._user_repository.get_by_identity(identity.issuer, identity.subject)
    if user is None:
        user = self._find_unlinked_user_by_email(identity)        # 403 if not registered or linked elsewhere
    if not user.is_active:
        raise InactiveUserError("Authenticated user is inactive")  # 403
    if user.identity_issuer is None:
        user = self._link(user, identity)                         # stores the pair
    return user
```

- A valid token that matches no registered user, by pair or by email, is **forbidden, not created** (`user_not_registered`). The backend never auto-provisions users, because doing so would grant an identity a foothold in the system without anyone deciding it should have one.
- A user has a single identity: an email that matches a user already linked to another pair is rejected with `identity_link_conflict`, and the stored link does not change. A token without email and without a stored link is `user_not_registered`.
- An inactive user is rejected with `user_inactive` on every request, whatever the token says.

### Enforcing Roles

Roles are read from `user_roles` for the resolved user, whatever the issuer; a `roles` claim in the token is ignored. Endpoints declare their requirement as a dependency:

```python
@router.get("/campaigns/{campaign_id}/margin")
async def get_campaign_margin(
    campaign_id: int,
    user: User = Depends(require_roles(RoleName.OPERATIONS, RoleName.FINANCE)),
) -> MarginResponse:
    ...
```

- `require_roles` accepts one or more role names and authorises a user holding **any** of them. Roles are additive.
- Every endpoint declares its requirement explicitly. There is no implicit default, and an endpoint without a declared requirement is a review failure, not an open endpoint.
- Cost and margin endpoints are restricted to `operations` and `finance`, per the access matrix of the `identity/access-matrix` specification.
- The frontend's role-guarded routes are a usability measure and are never the only check.

## Database Patterns

### Migrations

Schema changes go through Alembic. The schema is never modified by hand, and models are never allowed to drift from migrations.

```bash
# Create a migration from model changes
alembic revision --autogenerate -m "add user_roles bridge table"

# Apply migrations
alembic upgrade head
```

Autogenerated migrations are reviewed before committing. Alembic detects added and removed columns reliably; renames it detects as a drop plus an add, which destroys data.

### The Roles Bridge Table

A user may hold several roles, so the relationship is many-to-many:

```python
class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
```

A single `role` column on `users` is incorrect for this product and must not be introduced.

### Query Discipline

- Load relationships explicitly. Lazy loading across an 8.5-million-row delivery table is how a report becomes a timeout.
- Aggregate in the database. Fetching delivery rows to sum them in Python does not scale to the volumes in [Product Description](./product-description.md).
- Use transactions for multi-step writes. An ingestion batch either lands whole or not at all.

### Financial Data

- Monetary columns use `Numeric`, never floating point.
- Applied rebate and platform rates are **stored on the campaign line at calculation time**, together with their provenance. They are never recomputed from master tables at read time.
- Purchase orders are versioned rather than updated in place.

## Spreadsheet and DSP Report Ingestion

Three routes reach the same delivery model: DSP API, manual upload and (later) email. They share one ingestion contract, and no part of the domain knows which route a row arrived by.

- Every ingestion run records its source, route, file and outcome as a batch. The hand-typed load labels of the current system are exactly what this replaces.
- Parsing lives in `app/infrastructure/spreadsheets/`, behind an interface. pandas and openpyxl appear nowhere else.
- Parsers validate structure before content and fail with a precise message naming the file, sheet and row.
- Ingestion is **idempotent**. Re-running a batch for a date range replaces that range rather than appending to it, because DSPs restate figures and a rolling reprocessing window is required.
- Unmatched rows are recorded as exceptions to be worked, in **both directions**: delivery with no campaign line and campaign lines with no delivery. Neither is silently discarded.

## Testing Standards

### Test-Driven Development

Per the core principles, new functionality starts with a failing test. This matters most in the domain layer, where the economic rules live and where a wrong number is invisible until someone reconciles a year of data.

### Structure

- `tests/domain/` — pure unit tests, no database, no HTTP. The margin calculation, the bracket ladder and the rate-resolution ladder are tested here.
- `tests/application/` — use-case tests with in-memory repositories.
- `tests/api/` — endpoint tests using `httpx` against the FastAPI application, covering status codes, schemas and **role enforcement**.
- `tests/fixtures/` — builders and sample spreadsheet files.

### Conventions

- Test names state the behaviour: `test_rebate_applies_marginal_rate_when_campaign_straddles_bracket`.
- Arrange, act, assert, with one behaviour per test.
- Builders construct domain objects; literal dictionaries are not used as test data.
- Every role-guarded endpoint has a test asserting that a user **without** the role is forbidden. An endpoint is not covered until its negative authorisation case is.
- Worked examples from [Product Description](./product-description.md) are encoded as tests. They are the specification of the economic model and the reference against which parity with the current Qlik figures is judged.

## Performance Best Practices

- Delivery volumes are in the millions of rows. Ingestion is processed in batches and streamed; a full report is never held in memory as a list of objects.
- Index the columns that joins and filters use: the DSP mapping, the campaign period, and the delivery date.
- Aggregations that reports read repeatedly are computed once and stored, not recalculated per request.
- Long-running operations — an ingestion run, a year-restatement after a rebate rate change — do not block a request/response cycle.

## Security Best Practices

- **Configuration comes from environment variables.** Credentials never appear in code, and `.env` is never committed.
- **DSP API credentials** are held in `.env` with restricted permissions on the instance. Secrets Manager is a future improvement, out of scope for the MVP.
- **Validate every input** at the API boundary with Pydantic. Trust nothing from a request, an uploaded file or a DSP response.
- **Never interpolate SQL.** Use SQLAlchemy's parameter binding.
- **Uploaded files are untrusted.** Validate type and size before parsing, and store them in S3 rather than on the instance filesystem.
- **Log operations, never secrets.** Tokens, credentials and full request bodies stay out of the logs.
- **Authorise on the server, every time.** See [Authentication and Authorization](#authentication-and-authorization).

## Development Workflow

1. Work in baby steps, one at a time.
2. Write the failing test first.
3. Implement the smallest change that passes it.
4. Keep the layering intact — if a rule needs the database to be tested, it is in the wrong layer.
5. Create and review an Alembic migration for any model change.
6. Run the full suite before committing.
7. Commit messages, code, comments and test names in English.

## Deployment

The backend ships as a Docker image and runs as the `backend` service in the Compose stack on a single EC2 instance, behind nginx. See [Base Standards §7](./base-standards.md#7-deployment).

- The image installs dependencies at build time; nothing is installed at container start.
- Configuration arrives entirely through environment variables.
- Migrations are applied as a deliberate step on deployment, not implicitly at application start.
- The service exposes a health endpoint for nginx and for verifying a deployment.
