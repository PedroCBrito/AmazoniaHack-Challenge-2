import pytest

from app.services.field_validation import is_valid_date, is_valid_time, parse_decimal


@pytest.mark.parametrize(
    "value, expected",
    [
        ("29/02/2024", True),
        ("29/02/2023", False),
        ("2026-01-01", False),
    ],
)
def test_date_validation(value: str, expected: bool) -> None:
    assert is_valid_date(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [("00:00", True), ("23:59", True), ("24:00", False), ("9:30", False)],
)
def test_time_validation(value: str, expected: bool) -> None:
    assert is_valid_time(value) is expected


@pytest.mark.parametrize(
    "printed, expected",
    [
        ("R$ 1.234,56", 1234.56),
        ("R$ 1,234.56", 1234.56),
        ("12,3456 ha", 12.3456),
        ("-1,00", None),
        ("12,5 de 20 hectares", None),
        ("not a number", None),
        ("--1", None),
    ],
)
def test_decimal_conversion_keeps_brazilian_meaning(
    printed: str, expected: float | None
) -> None:
    assert parse_decimal(printed) == expected
