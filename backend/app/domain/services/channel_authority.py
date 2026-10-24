from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelAuthorityOutcome:
    """What ingestion does with a DSP-reported line format, given the line's configured channel."""

    # Always the configured channel: it is the rebate accrual key, so a value GeoQ does not control must not move it.
    channel_name: str
    contrast_line_format: str | None
    has_channel_mismatch: bool


def apply_channel_authority(configured_channel: str, reported_line_format: str | None) -> ChannelAuthorityOutcome:
    """Keep the configured channel, store the reported format as contrast, and flag a disagreement."""
    contrast_line_format = (reported_line_format or "").strip() or None
    has_channel_mismatch = contrast_line_format is not None and _normalised(contrast_line_format) != _normalised(
        configured_channel
    )
    return ChannelAuthorityOutcome(
        channel_name=configured_channel,
        contrast_line_format=contrast_line_format,
        has_channel_mismatch=has_channel_mismatch,
    )


def _normalised(text: str) -> str:
    return " ".join(text.casefold().split())
