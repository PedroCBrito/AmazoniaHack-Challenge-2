import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def is_valid_date(value: str) -> bool:
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return False
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return False
    return True


def is_valid_time(value: str) -> bool:
    return re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is not None


def parse_decimal(value: str) -> float | None:
    tokens = re.findall(r"-?\d[\d.,]*", value)
    if len(tokens) != 1:
        return None
    cleaned = tokens[0]
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(".", "").replace(",", ".")
            if cleaned.rfind(",") > cleaned.rfind(".")
            else cleaned.replace(",", "")
        )
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None
    return float(parsed) if parsed.is_finite() and parsed >= 0 else None
