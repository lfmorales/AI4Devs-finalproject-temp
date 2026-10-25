"""The master data loader against PostgreSQL: additive, idempotent, atomic, and silent about the file's content."""

import json

from sqlalchemy import func, select

from app.infrastructure.persistence.models.masters import (
    AdvertiserRecord,
    AgencyRecord,
    CampaignTypeRecord,
    ChannelRecord,
    DSPRecord,
    FormatRecord,
    HoldingGroupRecord,
    SalesRepRecord,
    SectorRecord,
)
from scripts.load_masters import EXIT_FAILED, EXIT_OK, main

# Distinctive synthetic names: any of them in the output would be a leak of the file's content.
FILE_CONTENT = {
    "holding_groups": [{"name": "Zanzibar Holding"}, {"name": "Quimera Group"}],
    "agencies": [
        {"name": "Zanzibar Madrid", "holding_group": "Zanzibar Holding"},
        {"name": "Quimera Sur", "holding_group": "Quimera Group"},
        {"name": "Quimera Norte", "holding_group": "Quimera Group"},
    ],
    "advertisers": [{"name": "Marca Ficticia Uno"}, {"name": "Marca Ficticia Dos"}],
    "dsps": [{"name": "Adform"}, {"name": "Equativ"}, {"name": "Displayce", "is_active": False}],
    "channels": [{"name": "Canal Quimera"}],
    "formats": [{"name": "Formato Zanzibar"}],
    "campaign_types": [{"name": "Tipo Quimera"}],
    "sectors": [{"name": "Sector Zanzibar"}],
    "sales_reps": [{"name": "Comercial Quimera"}],
}
MODELS = {
    "holding_groups": HoldingGroupRecord, "agencies": AgencyRecord, "advertisers": AdvertiserRecord,
    "dsps": DSPRecord, "channels": ChannelRecord, "formats": FormatRecord, "campaign_types": CampaignTypeRecord,
    "sectors": SectorRecord, "sales_reps": SalesRepRecord,
}


def _write(tmp_path, content=None) -> str:
    path = tmp_path / "masters.json"
    path.write_text(json.dumps(FILE_CONTENT if content is None else content), encoding="utf-8")
    return str(path)


def _run(session, path: str, *flags: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main([path, *flags], out=lines.append, session_factory=lambda: session)
    return code, lines


def _rows(session) -> dict[str, int]:
    return {section: session.scalar(select(func.count()).select_from(model)) for section, model in MODELS.items()}


def test_a_full_load_on_an_empty_database_creates_every_row(rolled_back_session, tmp_path):
    before = _rows(rolled_back_session)

    code, lines = _run(rolled_back_session, _write(tmp_path))

    assert code == EXIT_OK
    after = _rows(rolled_back_session)
    assert {section: after[section] - before[section] for section in MODELS} == {
        section: len(items) for section, items in FILE_CONTENT.items()
    }
    assert "agencies: created 3, existing 0" in lines
    assert "dsps: created 3, existing 0" in lines


def test_an_agency_is_stored_under_its_group(rolled_back_session, tmp_path):
    _run(rolled_back_session, _write(tmp_path))

    group = rolled_back_session.scalar(
        select(HoldingGroupRecord.name).join(AgencyRecord, AgencyRecord.holding_group_id == HoldingGroupRecord.id)
        .where(AgencyRecord.name == "Quimera Sur"))
    assert group == "Quimera Group"


def test_a_dsp_without_is_active_is_active_and_an_explicit_false_is_kept(rolled_back_session, tmp_path):
    _run(rolled_back_session, _write(tmp_path))

    states = dict(rolled_back_session.execute(select(DSPRecord.name, DSPRecord.is_active)).all())
    assert states["Equativ"] is True
    assert states["Displayce"] is False


def test_a_second_run_changes_nothing(rolled_back_session, tmp_path):
    path = _write(tmp_path)
    _run(rolled_back_session, path)
    after_first = _rows(rolled_back_session)

    code, lines = _run(rolled_back_session, path)

    assert code == EXIT_OK
    assert _rows(rolled_back_session) == after_first
    assert "agencies: created 0, existing 3" in lines
    assert "holding_groups: created 0, existing 2" in lines


def test_an_existing_row_is_left_as_it_was(rolled_back_session, tmp_path):
    other_group = HoldingGroupRecord(name="Grupo Previo")
    rolled_back_session.add(other_group)
    rolled_back_session.flush()
    rolled_back_session.add(AgencyRecord(name="Quimera Sur", holding_group_id=other_group.id))
    rolled_back_session.add(DSPRecord(name="Displayce", is_active=True))
    rolled_back_session.flush()

    code, lines = _run(rolled_back_session, _write(tmp_path))

    assert code == EXIT_OK
    stored = rolled_back_session.scalar(
        select(HoldingGroupRecord.name).join(AgencyRecord, AgencyRecord.holding_group_id == HoldingGroupRecord.id)
        .where(AgencyRecord.name == "Quimera Sur"))
    assert stored == "Grupo Previo"
    assert rolled_back_session.scalar(select(DSPRecord.is_active).where(DSPRecord.name == "Displayce")) is True
    assert "agencies: created 2, existing 1" in lines
    assert "dsps: created 2, existing 1" in lines


def test_a_failure_half_way_stores_nothing(rolled_back_session, tmp_path):
    before = _rows(rolled_back_session)

    class FailsOnTheSixthStatement:
        def __init__(self, session):
            self._session = session
            self._executed = 0

        def execute(self, *args, **kwargs):
            self._executed += 1
            if self._executed == 6:
                raise RuntimeError("connection lost while loading Zanzibar Holding")
            return self._session.execute(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._session, name)

    lines: list[str] = []
    code = main([_write(tmp_path)], out=lines.append, session_factory=lambda: FailsOnTheSixthStatement(rolled_back_session))

    assert code == EXIT_FAILED
    assert _rows(rolled_back_session) == before
    assert "Zanzibar" not in "\n".join(lines)


def test_the_output_carries_only_counts_and_no_name_from_the_file(rolled_back_session, tmp_path):
    path = _write(tmp_path)
    _, first = _run(rolled_back_session, path)
    _, second = _run(rolled_back_session, path)

    output = "\n".join(first + second)
    names = [item["name"] for items in FILE_CONTENT.values() for item in items]
    assert not [name for name in names if name in output]
    assert not [word for word in ("Zanzibar", "Quimera", "Ficticia") if word in output]
