from dataclasses import dataclass
from html.parser import HTMLParser

from ocr_adapter.schemas import OCRRegion


@dataclass(frozen=True)
class LayoutBlock:
    """Parsed top-level Chandra layout block."""

    attributes: dict[str, str | None]
    text: str


class ChandraLayoutParser(HTMLParser):
    """Collect top-level div blocks without changing Chandra's source HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[LayoutBlock] = []
        self._div_depth = 0
        self._attributes: dict[str, str | None] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "div":
            if self._div_depth == 0:
                self._attributes = dict(attrs)
                self._text_parts = []
            self._div_depth += 1
        elif self._attributes is not None and tag in {"br", "p", "li", "tr"}:
            self._text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._div_depth == 0:
            return
        self._div_depth -= 1
        if self._div_depth == 0 and self._attributes is not None:
            text = " ".join("".join(self._text_parts).split())
            self.blocks.append(LayoutBlock(self._attributes, text))
            self._attributes = None
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._attributes is not None:
            self._text_parts.append(data)


def parse_regions(
    content: str, width: int, height: int
) -> tuple[list[OCRRegion], list[str]]:
    """Convert normalized Chandra layout blocks into stable pixel regions."""
    parser = ChandraLayoutParser()
    parser.feed(content)
    regions = [
        _region_from_block(block, index, width, height)
        for index, block in enumerate(parser.blocks, start=1)
    ]
    warnings: list[str] = []
    if not regions:
        warnings.append("layout_metadata_unavailable")
    elif any(region.bounding_box is None for region in regions):
        warnings.append("layout_metadata_partial")
    return regions, warnings


def _region_from_block(
    block: LayoutBlock, index: int, width: int, height: int
) -> OCRRegion:
    return OCRRegion(
        id=f"page-1-region-{index:04d}",
        text=block.text or None,
        kind=block.attributes.get("data-label"),
        bounding_box=_pixel_box(block.attributes.get("data-bbox"), width, height),
    )


def _pixel_box(value: str | None, width: int, height: int) -> list[int] | None:
    if value is None:
        return None
    try:
        normalized = [int(part) for part in value.split()]
    except ValueError:
        return None
    if len(normalized) != 4:
        return None
    x0, y0, x1, y1 = normalized
    if x1 < x0 or y1 < y0:
        return None
    return [
        max(0, min(width, round(x0 * width / 1000))),
        max(0, min(height, round(y0 * height / 1000))),
        max(0, min(width, round(x1 * width / 1000))),
        max(0, min(height, round(y1 * height / 1000))),
    ]
