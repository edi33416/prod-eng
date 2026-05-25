import pytest

from bookshelf import services
from bookshelf.models import BookCreate


# TODO: Convert to @pytest.mark.parametrize with at least 8 cases.
#       Use pytest.param(..., id="descriptive-name") for each case.

def test_validate_isbn_valid_13_digit() -> None:
    assert services.validate_isbn("9780132350884") is True


def test_validate_isbn_valid_10_digit() -> None:
    assert services.validate_isbn("0132350882") is True


def test_validate_isbn_too_short() -> None:
    assert services.validate_isbn("123") is False


# TODO: Add cases for: empty string, too-long, non-numeric characters, hyphenated valid ISBN.

# TODO: Add a parametrized test for year validation (see parametrize.rst).
