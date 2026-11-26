"""How an author of a billing event is named on screen (finance/billing-report)."""


def author_name(full_name: str, email: str) -> str:
    """The user's name as stored, or the email when the name is blank."""
    name = full_name.strip()
    return name if name else email
