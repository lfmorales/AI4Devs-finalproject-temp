"""The configured channel is authoritative; the DSP's line_format is contrast data only."""

from dataclasses import FrozenInstanceError

import pytest

from app.domain.services.channel_authority import apply_channel_authority


def test_a_differing_line_format_leaves_the_configured_channel_unchanged():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="Deal")

    assert outcome.channel_name == "Directo"


def test_a_differing_line_format_is_stored_as_contrast():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="Deal")

    assert outcome.contrast_line_format == "Deal"


def test_a_differing_line_format_raises_the_mismatch_flag():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="Deal")

    assert outcome.has_channel_mismatch is True


def test_an_agreeing_line_format_raises_no_flag_and_is_still_stored():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="Directo")

    assert (outcome.has_channel_mismatch, outcome.contrast_line_format) == (False, "Directo")


def test_agreement_ignores_case_and_surrounding_whitespace():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="  directo ")

    assert outcome.has_channel_mismatch is False


@pytest.mark.parametrize("reported_line_format", [None, "", "   "])
def test_a_line_format_the_dsp_did_not_report_is_not_a_mismatch(reported_line_format):
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format=reported_line_format)

    assert (outcome.has_channel_mismatch, outcome.contrast_line_format) == (False, None)


def test_the_outcome_cannot_be_used_to_reclassify_the_channel():
    outcome = apply_channel_authority(configured_channel="Directo", reported_line_format="Deal")

    with pytest.raises(FrozenInstanceError):
        outcome.channel_name = "Deal"  # type: ignore[misc]
