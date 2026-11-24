from enum import StrEnum


class VolumeCommitment(StrEnum):
    """What a campaign line's volume means to the buyer. Declared on the line, never derived from its channel.

    COMMITTED: the buyer committed to the volume; revenue is the contracted volume times the sale CPM.
    TARGET: the volume is an objective the buyer may miss or exceed; revenue is what the DSP reports.
    """

    COMMITTED = "committed"
    TARGET = "target"
