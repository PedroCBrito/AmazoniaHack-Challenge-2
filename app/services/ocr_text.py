"""Read OCR text without losing line/table boundaries or source attribution."""

from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re

from app.schemas.extraction import SourceEvidence
from app.schemas.ocr import OCRResult


@dataclass(frozen=True)
class SourceLine:
    text: str
    evidence: SourceEvidence
    bounding_box: tuple[float, float, float, float] | None = None
    page: int = 1
    related_evidence: tuple[SourceEvidence, ...] = ()
    association: str | None = None

    @property
    def sources(self) -> list[SourceEvidence]:
        return [self.evidence, *self.related_evidence]


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"div", "p", "tr", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"div", "p", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_data(self, data):
        self.parts.append(data)


def source_lines(ocr: OCRResult) -> list[SourceLine]:
    content = ocr.content
    if re.search(r"</?(?:div|p|table|h[1-6]|br|span)\b", content, re.I):
        parser = _TextParser()
        parser.feed(content)
        content = "".join(parser.parts)
    lines: list[SourceLine] = []
    visible = [raw.strip().strip("|").strip() for raw in content.splitlines() if raw.strip().strip("|").strip()]
    normalized = lambda text: " ".join(text.split())
    aligned = len(visible) == len(ocr.regions) and all(
        normalized(text) == normalized(region.text or "")
        for text, region in zip(visible, ocr.regions)
    )
    for index, text in enumerate(visible):
        # Only assign an ID when this excerpt identifies one source region.
        exact = [region for region in ocr.regions if region.text and normalized(text) == normalized(region.text)]
        matches = exact or [
            region for region in ocr.regions
            if region.text and " ".join(text.split()) in " ".join(region.text.split())
        ]
        region = ocr.regions[index] if aligned else matches[0] if len(matches) == 1 else None
        lines.append(SourceLine(text, SourceEvidence(
            source_excerpt=text, region_reference=region.id if region else None,
        ), _region_box(region), getattr(region, "page", 1) if region else 1))
    if not lines:
        for region in ocr.regions:
            for text in (region.text or "").splitlines():
                if text.strip():
                    lines.append(SourceLine(text.strip(), SourceEvidence(
                        source_excerpt=text.strip(), region_reference=region.id,
                    ), _region_box(region), getattr(region, "page", 1)))
    return lines


def _region_box(region) -> tuple[float, float, float, float] | None:
    box = getattr(region, "bounding_box", None)
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in box):
        return None
    if not (0 <= box[0] < box[2] and 0 <= box[1] < box[3]):
        return None
    return tuple(box)
