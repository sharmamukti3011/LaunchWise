"""The request for /api/intake: the owner's description, as plain text."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.schemas.text import reject_control_characters

MAX_TEXT = 1500


def _no_control_characters(value: str) -> str:
    # Line breaks and tabs are fine in a description; other control characters are not.
    return reject_control_characters(value, allowed="\r\n\t")


class IntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT),
        AfterValidator(_no_control_characters),
    ]
