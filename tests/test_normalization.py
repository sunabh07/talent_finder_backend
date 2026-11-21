"""Skill normalization - the foundation of Story 3's matching.

Pure functions, no database. These are the cheapest tests in the suite and
they guard the rule that decides whether two skill strings are "the same".
"""

import pytest

from app.core.normalization import (
    normalize_display_name,
    normalize_search_term,
    normalize_skill,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Python", "python"),
        ("  Python  ", "python"),
        ("PYTHON", "python"),
        ("Machine   Learning", "machine learning"),
        ("Machine Learning.", "machine learning"),
        ("React.js", "react.js"),
        ("", ""),
        ("   ", ""),
        ("Node JS", "node js"),  # non-breaking space
    ],
)
def test_normalize_skill(raw: str, expected: str) -> None:
    assert normalize_skill(raw) == expected


@pytest.mark.parametrize("raw", ["C++", "C#", "F#"])
def test_significant_symbols_survive_normalization(raw: str) -> None:
    """``+`` and ``#`` carry meaning; stripping them would merge C, C++ and C#."""
    assert normalize_skill(raw) == raw.casefold()
    assert normalize_skill(raw) != "c"


def test_normalization_is_idempotent() -> None:
    once = normalize_skill("  React.JS  ")
    assert normalize_skill(once) == once


def test_display_name_keeps_casing_but_tidies_whitespace() -> None:
    assert normalize_display_name("  React   Native ") == "React Native"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  react ", "react"), ("", None), ("   ", None), (None, None)],
)
def test_normalize_search_term(raw: str | None, expected: str | None) -> None:
    assert normalize_search_term(raw) == expected
