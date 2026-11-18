"""Shared text rules for request and content schemas."""

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
