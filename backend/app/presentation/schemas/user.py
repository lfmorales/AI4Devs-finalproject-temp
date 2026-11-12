from pydantic import BaseModel, ConfigDict, Field, StrictBool


class ActivationRequest(BaseModel):
    """The email is in the body, not in the path, so it does not reach the access logs."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    active: StrictBool


class ActivationResponse(BaseModel):
    """Nothing but the email and the resulting state: no roles and no other data of the user."""

    email: str
    is_active: bool


class OwnRolesResponse(BaseModel):
    """Nothing but the names of the caller's roles: no email, no identifier, no other data."""

    roles: list[str]
