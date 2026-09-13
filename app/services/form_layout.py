"""Associate form labels with nearby values while respecting columns and pages."""

from dataclasses import replace
from collections import Counter
import re

from app.services.mapper_rules import NUMBER, NUMBERED, TITLE, folded, label_value
from app.services.ocr_text import SourceLine


def _anchor(line: SourceLine) -> bool:
    pair = label_value(line.text)
    return bool(NUMBERED.fullmatch(line.text) or pair)


def assemble_form(lines: list[SourceLine]) -> list[SourceLine]:
    lines = _join_headings(lines)
    anchors = [i for i, line in enumerate(lines) if _anchor(line)]
    # In a numbered form, unnumbered labels within a cell (e.g. coordinates
    # inside the description) belong to that numbered field, not a new row.
    numbered_counts = Counter(line.page for line in lines if line.bounding_box and NUMBERED.fullmatch(line.text))
    numbered_pages = {page for page, count in numbered_counts.items() if count >= 2}
    anchors = [i for i in anchors if lines[i].page not in numbered_pages or NUMBERED.fullmatch(lines[i].text)]
    assigned: dict[int, list[int]] = {i: [] for i in anchors}
    consumed: set[int] = set()
    geometric = [i for i in anchors if lines[i].bounding_box is not None]
    ordered_values = sorted(
        (i for i, line in enumerate(lines) if line.bounding_box is not None),
        key=lambda i: (lines[i].page, lines[i].bounding_box[1], lines[i].bounding_box[0]),
    )
    # Label rows define column ownership; OCR reading order need not be correct.
    rows: list[list[int]] = []
    for i in sorted(geometric, key=lambda i: (lines[i].page, lines[i].bounding_box[1])):
        box = lines[i].bounding_box
        if rows:
            previous = lines[rows[-1][0]]
            tolerance = max(box[3] - box[1], previous.bounding_box[3] - previous.bounding_box[1])
            same_row = previous.page == lines[i].page and abs(box[1] - previous.bounding_box[1]) <= tolerance * 0.65
        else:
            same_row = False
        if same_row:
            rows[-1].append(i)
        else:
            rows.append([i])
    for row_index, row in enumerate(rows):
        row.sort(key=lambda i: lines[i].bounding_box[0])
        page = lines[row[0]].page
        bottom = float("inf")
        if row_index + 1 < len(rows) and lines[rows[row_index + 1][0]].page == page:
            bottom = min(lines[i].bounding_box[1] for i in rows[row_index + 1])
        for column, i in enumerate(row):
            label = lines[i]
            if (column and lines[row[column - 1]].bounding_box[2] >= label.bounding_box[0]) or (
                column + 1 < len(row) and label.bounding_box[2] >= lines[row[column + 1]].bounding_box[0]
            ):
                continue  # Overlapping label boxes do not define unique columns.
            pair = label_value(label.text)
            if pair and pair[1] and pair[0] not in {"coordinates", "description", "legal_basis"}:
                continue
            x0, y0, x1, y1 = label.bounding_box
            margin = (y1 - y0) * 0.8
            right = lines[row[column + 1]].bounding_box[0] - margin if column + 1 < len(row) else float("inf")
            for j in ordered_values:
                value = lines[j]
                if j in anchors or j in consumed or value.page != page or value.bounding_box is None:
                    continue
                vx0, vy0, vx1, vy1 = value.bounding_box
                # Reject values straddling columns, and never cross the next label row.
                if vy0 >= bottom or (vy0 + vy1) / 2 <= (y0 + y1) / 2:
                    continue
                if vx0 < x0 - margin or vx1 > right:
                    continue
                if pair and pair[0] == "coordinates" and not re.match(r"\s*\d{1,3}\s*[°º]", value.text):
                    continue
                # A large blank gap does not authorize attaching the page footer.
                previous_bottom = max([y1, *(lines[k].bounding_box[3] for k in assigned[i])])
                if vy0 - previous_bottom > max(y1 - y0, vy1 - vy0) * 4:
                    continue
                assigned[i].append(j)
                consumed.add(j)
    for i in anchors:
        if lines[i].bounding_box is not None:
            continue
        pair = label_value(lines[i].text)
        if pair and pair[1]:
            continue
        # Without geometry, a row of labels followed by values is ambiguous.
        if (i > 0 and _anchor(lines[i - 1])) or (i + 1 < len(lines) and _anchor(lines[i + 1])):
            continue
        j = i + 1
        while j < len(lines) and j not in anchors and j not in consumed and lines[j].page == lines[i].page:
            if TITLE.match(folded(lines[j].text)) or label_value(lines[j].text):
                break
            assigned[i].append(j)
            consumed.add(j)
            j += 1
            # Unnumbered scalar labels may only take their immediate next value.
            if not NUMBERED.fullmatch(lines[i].text):
                break
    output_order = list(range(len(lines)))
    if all(line.bounding_box for line in lines):
        row_top = {i: min(lines[j].bounding_box[1] for j in row) for row in rows for i in row}
        output_order.sort(key=lambda i: (lines[i].page, row_top.get(i, lines[i].bounding_box[1]), lines[i].bounding_box[0]))
    result = []
    for i in output_order:
        line = lines[i]
        if i in consumed:
            continue
        members = assigned.get(i, [])
        if members:
            members.sort(key=lambda j: (lines[j].bounding_box[1], lines[j].bounding_box[0]) if lines[j].bounding_box else (j, 0))
            result.append(replace(
                line, text="\n".join([line.text, *(lines[j].text for j in members)]),
                related_evidence=tuple(source for j in members for source in lines[j].sources),
                association="geometry" if line.bounding_box else "adjacent_line",
            ))
        else:
            result.append(line)
    return result


def _join_headings(lines: list[SourceLine]) -> list[SourceLine]:
    result = []
    index = 0
    while index < len(lines):
        line = lines[index]
        title = TITLE.match(folded(line.text))
        rest = folded(line.text)[title.end():].strip() if title else None
        if rest is not None and re.fullmatch(r"(?:com a penalidade de multa\s*)?(?:n[º°o.]|numero)?\s*", rest) and index + 1 < len(lines):
            following = lines[index + 1]
            number = NUMBER.fullmatch(following.text)
            if number and _nearby(line, following):
                sources = [*line.related_evidence, *following.sources]
                text = line.text + "\n" + following.text
                index += 1
                if not number["year"] and index + 1 < len(lines):
                    year_line = lines[index + 1]
                    if _nearby(following, year_line) and re.fullmatch(r"ano\s*[/ :]\s*\d{4}", folded(year_line.text)):
                        text += "\n" + year_line.text
                        sources.extend(year_line.sources)
                        index += 1
                line = replace(line, text=text, related_evidence=tuple(sources), association="header_lines")
        result.append(line)
        index += 1
    return result


def _nearby(first: SourceLine, second: SourceLine) -> bool:
    if first.page != second.page:
        return False
    if first.bounding_box and second.bounding_box:
        a, b = first.bounding_box, second.bounding_box
        return abs(b[1] - a[3]) <= 3 * max(a[3] - a[1], b[3] - b[1])
    return True  # Only used for immediate neighbors in the OCR text.
