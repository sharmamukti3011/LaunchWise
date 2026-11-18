"""A small .dockerignore matcher, faithful to Docker's rules for the patterns we use.

Docker matches patterns against the path relative to the build context root with Go's
filepath.Match rules: `*` never crosses a `/`, `**` does, and a pattern that matches a directory
excludes everything below it. A later `!pattern` re-includes. The matcher has its own tests so
the deploy checks built on it can be trusted.
"""

import re


def parse_dockerignore(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _to_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.lstrip("/").rstrip("/")
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def is_excluded(path: str, patterns: list[str]) -> bool:
    """True if Docker would leave `path` (relative to the context root) out of the build."""
    parts = path.strip("/").split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    excluded = False
    for raw in patterns:
        negated = raw.startswith("!")
        regex = _to_regex(raw[1:] if negated else raw)
        if any(regex.fullmatch(prefix) for prefix in prefixes):
            excluded = not negated
    return excluded
