from app.domain.models.user import RoleName


def test_the_functional_roles_include_trading() -> None:
    assert {role.value for role in RoleName} == {"operations", "business", "finance", "trading"}
