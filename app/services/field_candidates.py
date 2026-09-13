import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.schemas.ocr import OCRResult


MAX_CANDIDATES = 200
LABEL_VALUE = re.compile(r"^[^:\n]{1,80}[:：]\s*(.+)$")
NUMBER_YEAR = re.compile(
    r"(?:N(?:[º°o.]|[uú]mero)?\s*)?([A-Z]?\d[\w.-]*?)\s*/\s*(\d{4})",
    re.IGNORECASE,
)
DATE_TOKEN = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
TIME_TOKEN = re.compile(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b")


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    id: str
    value: str
    source_excerpt: str
    region_reference: str | None
    bounding_box: tuple[int, int, int, int] | None
    kind: str


@dataclass(frozen=True, slots=True)
class CandidateCatalog:
    items: tuple[FieldCandidate, ...]
    truncated: bool = False

    def get(self, candidate_id: str) -> FieldCandidate | None:
        return next((item for item in self.items if item.id == candidate_id), None)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items)


class _HTMLTextLines(HTMLParser):
    _blocks = {"br", "div", "p", "li", "table", "tr", "section", "h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._blocks:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._blocks:
            self._flush()

    def handle_data(self, data: str) -> None:
        parts = data.splitlines()
        for index, part in enumerate(parts):
            if index:
                self._flush()
            self._parts.append(part)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = "".join(self._parts).strip()
        if text:
            self.lines.append(text)
        self._parts.clear()


def build_candidate_catalog(ocr: OCRResult) -> CandidateCatalog:
    candidates: list[FieldCandidate] = []
    seen: set[tuple[str, str | None]] = set()
    for text, region_reference, bounding_box in _source_lines(ocr):
        variants = [(text, "line"), *_derived_values(text)]
        for value, kind in variants:
            key = (value, region_reference)
            if not value or key in seen:
                continue
            seen.add(key)
            candidates.append(FieldCandidate(
                id=f"c{len(candidates) + 1:04d}",
                value=value,
                source_excerpt=text,
                region_reference=region_reference,
                bounding_box=bounding_box,
                kind=kind,
            ))
    return CandidateCatalog(
        items=tuple(candidates[:MAX_CANDIDATES]),
        truncated=len(candidates) > MAX_CANDIDATES,
    )


def _source_lines(
    ocr: OCRResult,
) -> list[tuple[str, str | None, tuple[int, int, int, int] | None]]:
    regions = [region for region in ocr.regions if region.text and region.text.strip()]
    if regions:
        return [
            (region.text.strip(), region.id, _bounding_box(region))
            for region in regions
        ]
    parser = _HTMLTextLines()
    parser.feed(ocr.content)
    parser.close()
    return [(line, None, None) for line in parser.lines]


def _bounding_box(region: object) -> tuple[int, int, int, int] | None:
    value = getattr(region, "bounding_box", None)
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if not all(isinstance(item, int) for item in value):
        return None
    return tuple(value)


def _derived_values(text: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    label_match = LABEL_VALUE.fullmatch(text)
    if label_match:
        values.append((label_match.group(1).strip(), "label_value"))
    for match in NUMBER_YEAR.finditer(text):
        values.extend([
            (match.group(1), "number"),
            (match.group(2), "year"),
        ])
    values.extend((match.group(), "date") for match in DATE_TOKEN.finditer(text))
    values.extend((match.group(), "time") for match in TIME_TOKEN.finditer(text))
    return values
