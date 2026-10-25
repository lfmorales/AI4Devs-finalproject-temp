"""Every route of the application is authenticated and role-guarded, derived from the registered routes.

The list of routes and the role each one requires are read from the application, not written here: a new
route without a role requirement fails the suite instead of going unnoticed.
"""

import pytest
from fastapi.routing import APIRoute

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


def test_the_routes_of_this_change_are_among_those_checked():
    checked = {
        (path, method) for path, route, _ in _protected_routes() for method in route.methods
    }

    assert ("/campaign-status", "GET") in checked
    assert ("/ingestion-exceptions", "GET") in checked
    assert ("/ingestion-exceptions/{exception_id}/resolve", "POST") in checked
    assert ("/campaign-lines/{campaign_line_id}/dsp-mappings", "POST") in checked
    assert ("/flights/preview", "POST") in checked
    assert ("/dsp-catalog", "GET") in checked
    assert ("/campaign-lines/unmapped", "GET") in checked
    assert ("/campaign-lines/{campaign_line_id}/dsp-mappings", "DELETE") in checked
    assert ("/ingestion-exceptions/{exception_id}/link", "POST") in checked


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
