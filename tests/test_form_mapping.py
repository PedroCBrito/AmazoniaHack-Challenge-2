import json
from pathlib import Path
import random

import pytest

from app.schemas.ocr import OCRRegion, OCRResult
from app.services.field_mapper import RuleBasedFieldMapper
from app.services.mapper_rules import NUMBERED


pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures"


async def mapped(text="", regions=()):
    return await RuleBasedFieldMapper().map(OCRResult(
        content=text, regions=list(regions), model_version="regression", duration_ms=0,
    ))


@pytest.mark.parametrize("variant", ["captured", "shuffled", "scaled"])
async def test_captured_infraction_ocr_matches_annotated_business_fields(variant):
    ocr = OCRResult.model_validate_json((FIXTURES / "infraction-image.ocr.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "infraction-image.expected.json").read_text(encoding="utf-8"))
    if variant == "shuffled":
        ocr.content = ""
        random.Random(42).shuffle(ocr.regions)
    elif variant == "scaled":
        for region in ocr.regions:
            region.bounding_box = [value * 2.5 + 15 for value in region.bounding_box]
    result = await RuleBasedFieldMapper().map(ocr)
    actual = result.model_dump(mode="json")
    assert {name: actual[name] for name in expected} == expected
    assert set(result.fields) == {str(i) for i in range(1, 18)}
    assert result.fields["5"] == "CEP\n68.372-140"
    assert "COORDENADAS:" in result.fields["13"]
    assert "00318/2026" in result.fields["13"]
    assert result.confidence.coordinates <= 0.35
    assert result.confidence.fields <= 0.5
    assert any(warning.code == "ocr_coordinate_marker" for warning in result.warnings)
    assert result.meta.mapper_model == "portuguese-form-rules-v2"
    by_id = {region.id: region for region in ocr.regions}
    for name, review in result.review.items():
        if getattr(result, name) is not None:
            assert review.evidence
        for evidence in review.evidence:
            assert evidence.region_reference in by_id
            assert evidence.source_excerpt in by_id[evidence.region_reference].text


@pytest.mark.parametrize("value", ["68.372-140", "638.204.112-90", "23,4187 HA", "17/03/2026", "117.093,50"])
async def test_identifiers_dates_and_amounts_are_not_form_field_numbers(value):
    assert NUMBERED.fullmatch(value) is None
    result = await mapped(value)
    assert result.fields is None


@pytest.mark.parametrize("heading", ["11 DATA", "11 - DATA", "11. DATA", "11 – DATA"])
async def test_numbered_label_and_adjacent_value(heading):
    result = await mapped(f"{heading}\n17/03/2026")
    assert result.issued_date == "17/03/2026"
    assert result.fields["11"].endswith("\n17/03/2026")
    assert len(result.review["issued_date"].evidence) == 2
    assert result.confidence.issued_date <= 0.5


async def test_values_in_separate_columns_do_not_follow_ocr_array_order():
    regions = [
        OCRRegion(id="hour", text="12 HORA", bounding_box=[200, 10, 250, 20]),
        OCRRegion(id="date", text="11 DATA", bounding_box=[10, 10, 60, 20]),
        OCRRegion(id="hour-value", text="14:10", bounding_box=[205, 25, 245, 35]),
        OCRRegion(id="date-value", text="17/03/2026", bounding_box=[15, 25, 100, 35]),
    ]
    result = await mapped(regions=regions)
    assert result.issued_date == "17/03/2026"
    assert result.issued_time == "14:10"
    assert {source.region_reference for source in result.review["issued_date"].evidence} == {"date", "date-value"}


async def test_value_straddling_columns_is_not_assigned():
    result = await mapped(regions=[
        OCRRegion(id="date", text="11 DATA", bounding_box=[10, 10, 60, 20]),
        OCRRegion(id="hour", text="12 HORA", bounding_box=[200, 10, 250, 20]),
        OCRRegion(id="uncertain", text="17/03/2026 14:10", bounding_box=[30, 25, 250, 35]),
    ])
    assert result.issued_date is None
    assert result.issued_time is None


async def test_no_geometry_does_not_guess_a_column_pairing():
    result = await mapped("11 DATA\n12 HORA\n17/03/2026\n14:10")
    assert result.issued_date is None
    assert result.issued_time is None


async def test_label_cannot_take_a_value_from_another_page():
    result = await mapped(regions=[
        OCRRegion(id="label", text="11 DATA", page=1, bounding_box=[10, 10, 60, 20]),
        OCRRegion(id="other-page", text="17/03/2026", page=2, bounding_box=[10, 25, 100, 40]),
    ])
    assert result.issued_date is None


async def test_reference_registration_is_not_the_issuing_officer():
    result = await mapped("Conforme o auto de constatação N°, 00318/2026 lavrado por\nAgente Referenciado MATRÍCULA 987.654-1")
    assert result.references[0].number == "00318"
    assert result.officer_registration is None
    assert result.parties is None


async def test_primary_area_and_total_fine_are_not_component_values():
    result = await mapped("SUPRIMIR 23,4187 HA, SENDO 2,489 HA EM APP E 20,9297 HA EM RESERVA.\nA SEMMA APLICA A MULTA EQUIVALENTE A R$ 117.093,50.\n(R$ 5.000,00 POR HECTARE SOBRE 23,4187 HA)")
    assert result.area_ha == 23.4187
    assert result.fine_brl == 117093.5


async def test_narrative_does_not_calculate_missing_total_fine():
    result = await mapped("SUPRIMIR 23,4187 HA.\n(R$ 5.000,00 POR HECTARE SOBRE 23,4187 HA)")
    assert result.area_ha == 23.4187
    assert result.fine_brl is None


async def test_conflicting_total_fines_remain_ambiguous():
    result = await mapped("A MULTA EQUIVALENTE A R$ 117.093,50.\nA MULTA EQUIVALENTE A R$ 118.000,00.")
    assert result.fine_brl is None
    assert result.review["fine_brl"].status == "ambiguous"


async def test_readable_coordinate_directions_are_not_flagged_as_zero():
    result = await mapped('Coordenadas: 3°17\'55,8"S 52°22\'58,3"O, 3°17\'55,1"S 52°22\'42,5"O')
    assert len(result.coordinates) == 2
    assert result.coordinates[0] == '3°17\'55,8"S 52°22\'58,3"O'
    assert not any(warning.code == "ocr_coordinate_marker" for warning in result.warnings)


async def test_partial_coordinate_pair_is_not_silently_dropped():
    result = await mapped('Coordenadas: 3°17\'55,8"S 52°22\'58,3"O, 3°17\'55,1"S')
    assert result.coordinates is None


async def test_ocr_inline_labels_without_colon():
    result = await mapped("11 DATA 17/03/2026\n12 HORA 14:10\n7 CNPJ/CPF 638.204.112-90")
    assert result.issued_date == "17/03/2026"
    assert result.issued_time == "14:10"
    assert result.parties is None  # No explicit person role was provided.


async def test_extended_header_split_into_number_and_year_lines():
    result = await mapped("AUTO DE INFRAÇÃO COM A PENALIDADE DE MULTA N°\n00092\nANO/2026\n1 NOME DO AUTUADO\nPessoa Exemplo")
    assert result.document_type == "infraction_notice"
    assert result.number == "00092"
    assert result.year == "2026"
    assert len(result.review["number"].evidence) == 3


async def test_registration_on_separate_reference_line_is_not_main_officer():
    result = await mapped("Conforme o auto de constatação N°, 00318/2026 lavrado por\nAgente Referenciado\nMatrícula 987.654-1")
    assert result.references[0].number == "00318"
    assert result.officer_registration is None


@pytest.mark.parametrize("text,field", [
    ("A MULTA EQUIVALENTE A R$ 117.093,50 OU R$ 118.000,00", "fine_brl"),
    ("SUPRIMIR 23 HA OU 24 HA", "area_ha"),
    ("NO IMÓVEL RURAL DENOMINADO FAZENDA A OU FAZENDA B", "property_name"),
])
async def test_narrative_alternatives_are_not_guessed(text, field):
    result = await mapped(text)
    assert getattr(result, field) is None
    assert result.review[field].status == "ambiguous"


async def test_overlapping_labels_do_not_select_one_column_arbitrarily():
    result = await mapped(regions=[
        OCRRegion(id="date", text="11 DATA", bounding_box=[10, 10, 70, 20]),
        OCRRegion(id="hour", text="12 HORA", bounding_box=[40, 10, 100, 20]),
        OCRRegion(id="value", text="14:10", bounding_box=[50, 25, 95, 35]),
    ])
    assert result.issued_date is None
    assert result.issued_time is None


async def test_header_cannot_borrow_a_distant_year():
    result = await mapped(regions=[
        OCRRegion(id="title", text="AUTO DE INFRAÇÃO N°", bounding_box=[10, 10, 200, 30]),
        OCRRegion(id="number", text="00092", bounding_box=[10, 35, 90, 55]),
        OCRRegion(id="year", text="ANO/2025", bounding_box=[10, 500, 100, 520]),
    ])
    assert result.number == "00092"
    assert result.year is None
