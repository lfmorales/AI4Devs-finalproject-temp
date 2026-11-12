"""Every route of the application is authenticated and role-guarded, derived from the registered routes.

The list of routes and the role each one requires are read from the application, not written here: a new
route without a role requirement fails the suite instead of going unnoticed.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.domain.models.user import RoleName
from app.main import create_app

# The only route that is public on purpose: deployment health checks call it without a token.
PUBLIC_PATHS = frozenset({"/health"})


def _registered_routes() -> list[tuple[str, APIRoute, list]]:
    """Every API route of the application with its full path and the dependencies its include added."""
    found: list[tuple[str, APIRoute, list]] = []

    def walk(routes, prefix: str, inherited: list) -> None:
        for route in routes:
            if hasattr(route, "original_router"):  # an included router: look inside it
                context = route.include_context
                walk(route.original_router.routes, prefix + context.prefix, inherited + list(context.dependencies))
            elif isinstance(route, APIRoute):
                found.append((prefix + route.path, route, inherited))

    walk(create_app().routes, "", [])
    return found


def _accepted_roles(route: APIRoute, inherited: list) -> frozenset[RoleName] | None:
    """The roles the route's own `require_roles` dependency accepts, or None when it declares none."""
    pending = list(route.dependant.dependencies) + [d.dependency for d in inherited]
    while pending:
        dependency = pending.pop()
        call = getattr(dependency, "call", dependency)
        roles = getattr(call, "accepted_roles", None)
        if roles is not None:
            return frozenset(roles)
        pending.extend(getattr(dependency, "dependencies", []))
    return None


def _protected_routes() -> list[tuple[str, APIRoute, list]]:
    return [entry for entry in _registered_routes() if entry[0] not in PUBLIC_PATHS]


def _cases() -> list:
    return [
        pytest.param(path, route, inherited, method, id=f"{method} {path}")
        for path, route, inherited in _protected_routes() for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    ]


def _call(client, path: str, route: APIRoute, method: str):
    # Path parameters get a plausible value; the guard runs before the path or the body is looked at.
    for parameter in route.dependant.path_params:
        path = path.replace("{" + parameter.name + "}", "1")
    return client.request(method, path)


def test_the_routes_found_are_the_ones_the_application_publishes():
    published = {
        (path, method.upper()) for path, item in create_app().openapi()["paths"].items() for method in item
    }
    found = {
        (path, method)
        for path, route, _ in _registered_routes() for method in route.methods - {"HEAD", "OPTIONS"}
    }

    assert found == published


OPERATIONS = frozenset({RoleName.OPERATIONS})
READERS = frozenset({RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE})
MARGIN_READERS = frozenset({RoleName.OPERATIONS, RoleName.FINANCE})
EVERYONE = frozenset({RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE, RoleName.TRADING})
ALL_ROLES = (RoleName.OPERATIONS, RoleName.FINANCE, RoleName.BUSINESS, RoleName.TRADING)

# The access matrix of the identity/access-matrix specification, route by route. /health is public on purpose.
ACCESS_MATRIX: dict[tuple[str, str], frozenset[RoleName]] = {
    ("/campaigns", "GET"): READERS,
    ("/campaigns", "POST"): OPERATIONS,
    **{(f"/masters/{name}", "GET"): READERS
       for name in ("agencies", "advertisers", "dsps", "channels", "formats", "campaign-types", "sectors", "sales-reps")},
    ("/campaign-status", "GET"): EVERYONE,
    ("/campaign-lines/unmapped", "GET"): OPERATIONS,
    ("/campaign-lines/{campaign_line_id}/dsp-mappings", "POST"): OPERATIONS,
    ("/campaign-lines/{campaign_line_id}/dsp-mappings", "DELETE"): OPERATIONS,
    ("/dsp-catalog", "GET"): OPERATIONS,
    ("/flights/preview", "POST"): OPERATIONS,
    ("/ingestion-exceptions", "GET"): OPERATIONS,
    ("/ingestion-exceptions/{exception_id}/resolve", "POST"): OPERATIONS,
    ("/ingestion-exceptions/{exception_id}/link", "POST"): OPERATIONS,
    ("/margin", "GET"): MARGIN_READERS,
    ("/margin/closings", "POST"): MARGIN_READERS,
    ("/margin/rebate-schedules", "POST"): OPERATIONS,
    ("/margin/platform-rates", "POST"): OPERATIONS,
}


def test_the_access_matrix_has_an_entry_for_every_route_and_no_entry_without_a_route() -> None:
    routes = {
        (path, method) for path, route, _ in _protected_routes() for method in (route.methods or set()) - {"HEAD", "OPTIONS"}
    }

    assert routes - set(ACCESS_MATRIX) == set(), "routes missing from the access matrix"
    assert set(ACCESS_MATRIX) - routes == set(), "matrix entries without a real route"


def test_there_are_routes_to_check():
    # An empty parametrization is skipped silently by pytest: fail loudly instead.
    assert len(_cases()) >= 5


@pytest.mark.parametrize(("path", "route", "inherited", "method"), _cases())
def test_a_route_declares_the_roles_it_requires(path, route, inherited, method):
    assert _accepted_roles(route, inherited), f"{method} {path} has no require_roles dependency"


@pytest.mark.parametrize(("path", "route", "inherited", "method"), _cases())
def test_a_request_without_a_token_is_unauthenticated(client, path, route, inherited, method):
    response = _call(client, path, route, method)

    assert response.status_code == 401
    assert set(response.json()) == {"code", "message"}


@pytest.mark.parametrize(("path", "route", "inherited", "method"), _cases())
def test_a_user_holding_only_the_other_roles_is_forbidden(client_for_roles, path, route, inherited, method):
    accepted = _accepted_roles(route, inherited)
    assert accepted
    other_roles = sorted(role.value for role in RoleName if role not in accepted)

    response = _call(client_for_roles(*other_roles), path, route, method)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}


def test_the_margin_routes_are_the_four_of_this_change() -> None:
    margin = {key for key in ACCESS_MATRIX if key[0] == "/margin" or key[0].startswith("/margin/")}

    assert margin == {
        ("/margin", "GET"),
        ("/margin/closings", "POST"),
        ("/margin/rebate-schedules", "POST"),
        ("/margin/platform-rates", "POST"),
    }


@pytest.mark.parametrize(("path", "route", "inherited", "method"), _cases())
def test_a_route_declares_exactly_the_roles_of_the_access_matrix(
    path: str, route: APIRoute, inherited: list[Any], method: str
) -> None:
    assert _accepted_roles(route, inherited) == ACCESS_MATRIX[(path, method)]


@pytest.mark.parametrize("role", ALL_ROLES, ids=lambda role: role.value)
@pytest.mark.parametrize(("path", "route", "inherited", "method"), _cases())
def test_each_role_gets_the_outcome_of_the_access_matrix_on_every_route(
    client_for_roles: Callable[..., TestClient], path: str, route: APIRoute, inherited: list[Any], method: str, role: RoleName
) -> None:
    response = _call(client_for_roles(role.value), path, route, method)

    if role in ACCESS_MATRIX[(path, method)]:
        # The guard lets the request through; what follows (a 422 for a missing body, a 404...) is not its business.
        assert response.status_code not in (401, 403)
    else:
        assert response.status_code == 403
        assert set(response.json()) == {"code", "message"}
        assert not any(word in response.text.lower() for word in ("revenue", "rebate", "margin", "cost", "platform"))
