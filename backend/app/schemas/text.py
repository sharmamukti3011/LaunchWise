"""Shared text rules for request and content schemas."""

import re
import unicodedata

# Control characters (CR, LF, NUL, tab, escape, ...) and Unicode line and paragraph separators.
FORBIDDEN_CATEGORIES = {"Cc", "Zl", "Zp"}


def reject_control_characters(text: str, allowed: str = "") -> str:
    """Return `text` unchanged, or raise if it holds a control or line-separator character.

    `allowed` lists exceptions (a message body may keep newlines and tabs, for example).
    """
    for char in text:
        if unicodedata.category(char) in FORBIDDEN_CATEGORIES and char not in allowed:
            raise ValueError("contains characters that are not allowed")
    return text


# Plain ASCII addresses only: letters, digits, the usual local-part symbols, and a dotted domain.
# Deliberately simpler than the RFC, and it needs no extra dependency.
_EMAIL = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
MAX_EMAIL = 254
_MAX_LOCAL_PART = 64


def is_plain_email(value: str) -> bool:
    """True for a plain address of at most 254 characters, with no control characters."""
    if len(value) > MAX_EMAIL or any(
        unicodedata.category(c) in FORBIDDEN_CATEGORIES for c in value
    ):
        return False
    local = value.split("@", 1)[0]
    return len(local) <= _MAX_LOCAL_PART and _EMAIL.fullmatch(value) is not None
