"""The loader validates the whole file before writing, names sections and positions only, and --check writes nothing."""

import copy
import json

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.masters import AdvertiserRecord, AgencyRecord, DSPRecord, HoldingGroupRecord
from scripts.load_masters import EXIT_INVALID, EXIT_OK, main
from tests.scripts.test_load_masters import FILE_CONTENT, MODELS, _rows


def _file(tmp_path, content) -> str:
    path = tmp_path / "masters.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return str(path)


def _run(session, path: str, *flags: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main([path, *flags], out=lines.append, session_factory=lambda: session)
    return code, lines


def _valid() -> dict:
    return copy.deepcopy(FILE_CONTENT)


def _assert_rejected_and_nothing_written(session, tmp_path, content, expected_fragment: str):
    before = _rows(session)

    code, lines = _run(session, _file(tmp_path, content))

    assert code == EXIT_INVALID
    assert any(expected_fragment in line for line in lines), lines
    assert _rows(session) == before
    return lines


def test_a_name_repeated_within_a_section_is_rejected_by_section_and_position(rolled_back_session, tmp_path):
    content = _valid()
    content["advertisers"].append({"name": "Marca Ficticia Uno"})

    lines = _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "advertisers[2]")

    assert "Marca Ficticia" not in "\n".join(lines)


def test_a_repeat_that_differs_only_in_surrounding_spaces_is_still_a_repeat(rolled_back_session, tmp_path):
    content = _valid()
    content["channels"].append({"name": "  Canal Quimera "})

    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "channels[1]")


@pytest.mark.parametrize("item", [{}, {"name": ""}, {"name": "   "}, {"name": 7}, {"name": None}, "text"])
def test_an_item_without_a_usable_name_is_rejected(rolled_back_session, tmp_path, item):
    content = _valid()
    content["sectors"].append(item)

    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "sectors[1]")


def test_an_agency_whose_group_is_not_defined_anywhere_is_rejected(rolled_back_session, tmp_path):
    content = _valid()
    content["agencies"].append({"name": "Agencia Huerfana", "holding_group": "Grupo Inexistente"})

    lines = _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "agencies[3]")

    assert "Inexistente" not in "\n".join(lines)
    assert "Huerfana" not in "\n".join(lines)


def test_an_agency_without_a_group_is_rejected(rolled_back_session, tmp_path):
    content = _valid()
    del content["agencies"][0]["holding_group"]

    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "agencies[0]")


def test_an_agency_may_use_a_group_that_is_already_stored(rolled_back_session, tmp_path):
    rolled_back_session.add(HoldingGroupRecord(name="Grupo Ya Guardado"))
    rolled_back_session.flush()
    content = _valid()
    content["agencies"].append({"name": "Agencia Nueva", "holding_group": "Grupo Ya Guardado"})

    code, _ = _run(rolled_back_session, _file(tmp_path, content))

    assert code == EXIT_OK
    assert rolled_back_session.scalar(select(AgencyRecord.id).where(AgencyRecord.name == "Agencia Nueva")) is not None


def test_a_file_without_an_adform_dsp_is_rejected_when_the_database_has_none(rolled_back_session, tmp_path):
    content = _valid()
    content["dsps"] = [dsp for dsp in content["dsps"] if dsp["name"] != "Adform"]
    rolled_back_session.execute(DSPRecord.__table__.delete().where(DSPRecord.name == "Adform"))

    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "dsps")


def test_a_file_without_adform_is_accepted_when_the_database_already_has_it(rolled_back_session, tmp_path):
    rolled_back_session.add(DSPRecord(name="Adform", is_active=True))
    rolled_back_session.flush()
    content = _valid()
    content["dsps"] = [dsp for dsp in content["dsps"] if dsp["name"] != "Adform"]

    code, _ = _run(rolled_back_session, _file(tmp_path, content))

    assert code == EXIT_OK


def test_an_unknown_section_or_key_is_rejected(rolled_back_session, tmp_path):
    with_section = _valid()
    with_section["agencys"] = [{"name": "Typo"}]
    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, with_section, "agencys")

    with_key = _valid()
    with_key["formats"][0]["colour"] = "red"
    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, with_key, "formats[0]")


def test_is_active_must_be_a_boolean(rolled_back_session, tmp_path):
    content = _valid()
    content["dsps"][1]["is_active"] = "yes"

    _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "dsps[1]")


def test_every_problem_is_reported_at_once(rolled_back_session, tmp_path):
    content = _valid()
    content["advertisers"].append({"name": "Marca Ficticia Uno"})
    content["sectors"].append({})

    lines = _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, content, "advertisers[2]")

    assert any("sectors[1]" in line for line in lines)


@pytest.mark.parametrize("text", ["{not json", "[]", '"text"', ""])
def test_a_file_that_is_not_a_json_object_is_rejected_without_echoing_it(rolled_back_session, tmp_path, text):
    lines = _assert_rejected_and_nothing_written(rolled_back_session, tmp_path, text, "file")

    assert "not json" not in "\n".join(lines)


def test_a_missing_file_is_rejected(rolled_back_session, tmp_path):
    code, lines = _run(rolled_back_session, str(tmp_path / "absent.json"))

    assert code == EXIT_INVALID
    assert any("file" in line for line in lines)


def test_check_validates_and_writes_nothing(rolled_back_session, tmp_path):
    before = _rows(rolled_back_session)

    code, lines = _run(rolled_back_session, _file(tmp_path, _valid()), "--check")

    assert code == EXIT_OK
    assert _rows(rolled_back_session) == before
    assert "agencies: would create 3, existing 0" in lines
    assert "dsps: would create 3, existing 0" in lines


def test_check_counts_what_already_exists(rolled_back_session, tmp_path):
    path = _file(tmp_path, _valid())
    _run(rolled_back_session, path)

    code, lines = _run(rolled_back_session, path, "--check")

    assert code == EXIT_OK
    assert "agencies: would create 0, existing 3" in lines


def test_check_rejects_an_invalid_file_and_still_writes_nothing(rolled_back_session, tmp_path):
    content = _valid()
    content["advertisers"].append({"name": "Marca Ficticia Uno"})
    before = _rows(rolled_back_session)

    code, _ = _run(rolled_back_session, _file(tmp_path, content), "--check")

    assert code == EXIT_INVALID
    assert _rows(rolled_back_session) == before


def test_no_output_of_any_mode_carries_a_name_from_the_file(rolled_back_session, tmp_path):
    invalid = _valid()
    invalid["advertisers"].append({"name": "Marca Ficticia Uno"})
    outputs: list[str] = []
    for content, flags in ((_valid(), ("--check",)), (invalid, ()), (_valid(), ())):
        outputs += _run(rolled_back_session, _file(tmp_path, content), *flags)[1]

    text = "\n".join(outputs)
    assert not [word for word in ("Zanzibar", "Quimera", "Ficticia") if word in text]
