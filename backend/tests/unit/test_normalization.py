import pytest

from app.evaluation.normalization import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Paris", "paris"),
        ("  Paris.  ", "paris"),
        ('"Paris!"', "paris"),
        ("Pacific   Ocean\n", "pacific ocean"),
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),  # casefold, not lower
        ("ＨＯＬＡ", "hola"),  # noqa: RUF001 -- NFKC folds full-width "HOLA"
        ("3.14", "3.14"),  # internal punctuation kept
        ('{"is_prime": true}', 'is_prime": true'),
        ("", ""),
        ("...", ""),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalization_does_not_strip_symbols() -> None:
    # "$" is a currency symbol (Sc), not punctuation, so it must survive.
    assert normalize_text("$5") == "$5"
