"""Canonical text normalization for skill keywords.

Skill matching is the graded core of this application, so normalization has to
be *deterministic and lossless in the ways that matter*. Two rules drive the
implementation:

1. Case and whitespace never change meaning  -> fold them away.
2. ``+`` and ``#`` **do** change meaning     -> never strip them, or ``C++``,
   ``C#`` and ``F#`` all collapse into ``c``.

Anything this function cannot reconcile (``js`` vs ``javascript``) is handled by
the ``skill_aliases`` table instead, so that fuzzy behaviour stays explicit,
reviewable data rather than hidden string heuristics.
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.,;:]+$")


def normalize_skill(raw: str) -> str:
    """Return the canonical lookup form of a skill keyword.

    >>> normalize_skill("  React.JS  ")
    'react.js'
    >>> normalize_skill("C++")
    'c++'
    >>> normalize_skill("Machine   Learning.")
    'machine learning'
    """
    if raw is None:
        return ""
    # NFKC folds full-width and ligature characters onto their ASCII forms.
    text = unicodedata.normalize("NFKC", str(raw))
    text = text.replace(" ", " ").strip()
    text = _WHITESPACE.sub(" ", text)
    text = _TRAILING_PUNCT.sub("", text)
    return text.casefold()


def normalize_display_name(raw: str) -> str:
    """Tidy a human-facing skill label without altering its casing."""
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = text.replace(" ", " ").strip()
    return _WHITESPACE.sub(" ", text)


def normalize_search_term(raw: str | None) -> str | None:
    """Collapse a free-text search box value, or ``None`` when it is empty."""
    if raw is None:
        return None
    text = _WHITESPACE.sub(" ", str(raw).strip())
    return text or None
