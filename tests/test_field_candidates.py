from app.schemas.ocr import OCRRegion, OCRResult
from app.services.field_candidates import build_candidate_catalog


def _ocr(content: str, regions: list[OCRRegion] | None = None) -> OCRResult:
    return OCRResult(
        content=content,
        regions=regions or [],
        model_version="test-ocr",
        duration_ms=1,
    )


def test_candidates_preserve_source_text_and_split_generic_labels() -> None:
    catalog = build_candidate_catalog(
        _ocr(
            "ignored when regions exist",
            [OCRRegion(id="r1", text="Número: 00831")],
        )
    )

    number = next(item for item in catalog.items if item.value == "00831")
    assert number.source_excerpt == "Número: 00831"
    assert number.region_reference == "r1"
    assert number.kind == "label_value"


def test_candidates_keep_printed_coordinates_unchanged() -> None:
    printed = '2°58\'36,2"S'
    catalog = build_candidate_catalog(
        _ocr(printed, [OCRRegion(id="coord-1", text=printed)])
    )

    assert catalog.items[0].value == printed
    assert catalog.items[0].source_excerpt == printed


def test_candidates_fall_back_to_text_from_html_content() -> None:
    catalog = build_candidate_catalog(
        _ocr("<div>Município: Paragominas</div><div>Ano: 2026</div>")
    )

    assert [item.value for item in catalog.items if item.kind == "label_value"] == [
        "Paragominas",
        "2026",
    ]
    assert all(item.region_reference is None for item in catalog.items)


def test_number_and_year_are_candidates_without_template_rules() -> None:
    catalog = build_candidate_catalog(_ocr("AUTO DE INFRAÇÃO Nº 000123/2026"))

    assert {item.value for item in catalog.items} >= {"000123", "2026"}


def test_date_and_time_tokens_do_not_require_a_known_label() -> None:
    catalog = build_candidate_catalog(_ocr("Lavrado em 13/09/2026 às 09:45"))

    assert {(item.value, item.kind) for item in catalog.items} >= {
        ("13/09/2026", "date"),
        ("09:45", "time"),
    }
