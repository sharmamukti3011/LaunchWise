"""Request and response models for the contact form.

The request rejects control characters and line separators outright, so nothing a visitor types
can become an extra mail header. It also forbids unknown fields, so a client cannot supply a
recipient (`to`, `cc`, `bcc`, ...): the recipient is set server-side only.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.text import reject_control_characters

# Plain ASCII addresses only: letters, digits, the usual local-part symbols, and a dotted domain.
# Deliberately simpler than the RFC, and it needs no extra dependency.
_EMAIL = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
_MAX_LOCAL_PART = 64


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=100)]
    email: Annotated[str, Field(max_length=254)]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    # Honeypot: hidden in the real form, so only bots fill it. Anything here is a bot.
    website: str = ""

    @field_validator("name")
    @classmethod
    def _name_is_one_clean_line(cls, value: str) -> str:
        return reject_control_characters(value)

    @field_validator("email")
    @classmethod
    def _email_is_a_plain_address(cls, value: str) -> str:
        reject_control_characters(value)
        local = value.split("@", 1)[0]
        if len(local) > _MAX_LOCAL_PART or not _EMAIL.fullmatch(value):
            raise ValueError("is not a valid email address")
        return value

    @field_validator("message")
    @classmethod
    def _message_is_clean_text(cls, value: str) -> str:
        reject_control_characters(value, allowed="\r\n\t")
        return value.replace("\r\n", "\n").replace("\r", "\n")


SENT_TEXT = "Thanks, your message has been sent."


class ContactResponse(BaseModel):
    """The same fixed answer for a real send and for a honeypot hit."""

    status: Literal["sent"] = "sent"
    message: str = SENT_TEXT
