"""Rules for text that appears on a public page: no markup, no links, no obvious abuse.

Both checks are deliberately simple and conservative. They refuse with fixed text and never say
which rule or which word matched, so the lists cannot be probed. They are not moderation: every
page also carries noindex, an "example page" banner, and expires after seven days.
"""

import re
import unicodedata

# Whole words only, lower case. Ordinary words that contain one (Essex, Scunthorpe, Gunjan,
# Therapist) are never blocked, because matching is on whole words, not substrings.
BLOCKED_TERMS = frozenset(
    {
        # adult content
        "porn", "porno", "pornography", "xxx", "nude", "nudes", "nsfw", "escort", "escorts",
        "hooker", "brothel",
        # gambling
        "casino", "gambling", "betting",
        # drugs
        "cocaine", "heroin", "meth", "fentanyl", "lsd", "mdma",
        # fraud
        "scam", "scammer", "phishing", "fraud", "ponzi", "counterfeit", "forged", "laundering",
        # weapons and violence
        "gun", "guns", "firearm", "firearms", "weapon", "weapons", "ammo", "explosive",
        "explosives", "kill", "murder", "rape", "rapist", "terrorist", "terrorism", "suicide",
        # hate
        "nazi", "hitler",
    }
)  # fmt: skip

_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-f]+|[a-z]+);", re.IGNORECASE)
_SCHEME = re.compile(r"\b[a-z][a-z0-9+.-]*\s*:\s*//", re.IGNORECASE)
_RISKY_SCHEME = re.compile(r"\b(?:javascript|data|vbscript|mailto|tel)\s*:", re.IGNORECASE)
_WWW = re.compile(r"\bw\s*w\s*w\s*\.", re.IGNORECASE)
# word.tld with a dot that is plain ("example.com") or spaced on both sides ("example . com").
# A dot followed by a space only ("nine. In the evening") is ordinary prose and is not matched.
_TLDS = (
    "com|net|org|in|co|io|me|app|dev|xyz|info|biz|shop|store|site|online|ly|uk|us|ai|edu|gov|tv"
    "|cc|club|link|click|top"
)
_DOMAIN = re.compile(rf"\b[\w-]+(?:\.[\w-]+)*(?:\.|\s\.\s)(?:{_TLDS})\b", re.IGNORECASE)


def contains_markup_or_link(text: str) -> bool:
    """True for HTML, entities, markdown links, web addresses, emails and handles."""
    plain = unicodedata.normalize("NFKC", text)
    return (
        "<" in plain
        or ">" in plain
        or "@" in plain
        or "](" in plain
        or _ENTITY.search(plain) is not None
        or _SCHEME.search(plain) is not None
        or _RISKY_SCHEME.search(plain) is not None
        or _WWW.search(plain) is not None
        or _DOMAIN.search(plain) is not None
    )


_LEET = str.maketrans("013457$@", "oieastsa")
_NON_LETTERS = re.compile(r"[^a-z]+")
_REPEATS = re.compile(r"(.)\1+")


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(c for c in folded if unicodedata.category(c) != "Cf")  # zero-width, etc.
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = folded.lower().translate(_LEET)
    words = [w for w in _NON_LETTERS.split(folded) if w]
    # "c a s i n o": runs of single letters read as one word.
    merged: list[str] = []
    run = ""
    for word in words:
        if len(word) == 1:
            run += word
            continue
        if run:
            merged.append(run)
            run = ""
        merged.append(word)
    if run:
        merged.append(run)
    return merged


def is_blocked(text: str) -> bool:
    """True if a whole word, in any simple disguise, is on the blocklist."""
    for word in _words(text):
        if word in BLOCKED_TERMS or _REPEATS.sub(r"\1", word) in BLOCKED_TERMS:
            return True
    return False
