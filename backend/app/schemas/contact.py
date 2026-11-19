"""Request and response models for the contact form.

The request rejects control characters and line separators outright, so nothing a visitor types
can become an extra mail header. It also forbids unknown fields, so a client cannot supply a
recipient (`to`, `cc`, `bcc`, ...): the recipient is set server-side only.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.text import is_plain_email, reject_control_characters


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
        if not is_plain_email(value):
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
