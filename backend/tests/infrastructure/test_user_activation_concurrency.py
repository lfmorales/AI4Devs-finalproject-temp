"""Two simultaneous deactivations of the last two holders of a role must not leave the role without an active user."""

import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models.user import RoleName
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository

ROLE = RoleName.TRADING


@pytest.fixture
def two_trading_users(test_engine: Engine) -> Iterator[tuple[sessionmaker[Session], int, int]]:
    """Two committed active holders of the role and no other, removed afterwards."""
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:8]
    with factory() as session:
        role = session.query(RoleRecord).filter_by(name=ROLE.value).one_or_none()
        if role is None:
            role = RoleRecord(name=ROLE.value)
            session.add(role)
            session.flush()
        others = session.query(UserRoleRecord).filter_by(role_id=role.id).count()
        assert others == 0, "the test database already has holders of the role"
        users = [UserRecord(email=f"race-{tag}-{n}@example.com", full_name="Race", is_active=True) for n in (1, 2)]
        session.add_all(users)
        session.flush()
        session.add_all([UserRoleRecord(user_id=user.id, role_id=role.id) for user in users])
        session.commit()
        ids = (users[0].id, users[1].id)
    try:
        yield factory, ids[0], ids[1]
    finally:
        with factory() as session:
            session.query(UserRoleRecord).filter(UserRoleRecord.user_id.in_(ids)).delete(synchronize_session=False)
            session.query(UserRecord).filter(UserRecord.id.in_(ids)).delete(synchronize_session=False)
            session.commit()


def test_two_simultaneous_deactivations_leave_one_active_holder(
    two_trading_users: tuple[sessionmaker[Session], int, int],
) -> None:
    factory, first, second = two_trading_users
    first_is_at_its_update = threading.Event()
    second_may_start = threading.Event()
    results: dict[str, bool] = {}

    first_session = factory()
    second_session = factory()

    def _hold_the_first_before_its_update(
        conn: Connection, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        # Pauses the first transaction after it has taken its locks and before it changes the state.
        if statement.lstrip().upper().startswith("UPDATE USERS") and not first_is_at_its_update.is_set():
            first_is_at_its_update.set()
            assert second_may_start.wait(timeout=10)

    first_connection = first_session.connection()
    event.listen(first_connection, "before_cursor_execute", _hold_the_first_before_its_update)

    def run(name: str, session: Session, user_id: int) -> None:
        results[name] = SqlAlchemyUserRepository(session).set_active(user_id, False, keep_one_active_with_role=ROLE)

    thread_first = threading.Thread(target=run, args=("first", first_session, first))
    thread_second = threading.Thread(target=run, args=("second", second_session, second))
    thread_first.start()
    assert first_is_at_its_update.wait(timeout=10)
    thread_second.start()
    # Gives the second transaction time to reach the lock the first one holds.
    threading.Event().wait(0.7)
    second_may_start.set()
    thread_first.join(timeout=20)
    thread_second.join(timeout=20)
    event.remove(first_connection, "before_cursor_execute", _hold_the_first_before_its_update)
    first_session.close()
    second_session.close()

    assert sorted(results.values()) == [False, True]
    with factory() as session:
        assert SqlAlchemyUserRepository(session).count_active_with_role(ROLE) == 1
