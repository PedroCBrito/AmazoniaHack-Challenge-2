# Local field mapping and JSON export

`POST /extract` now runs `RuleBasedFieldMapper` after OCR. The mapper receives the
existing `OCRResult`; it neither calls another model nor needs credentials. Both
Chandra and Textract use the same mapping path. The rule version is
`portuguese-form-rules-v2`, returned in `_meta.mapper_model`.

## Correction based on infraction-image.jpg

The first rules version mapped none of the 18 business fields in this photographed
form and misclassified a CPF/CEP as numbered fields. A live request to the local
OCR adapter captured 73 regions; the text was present but its labels and values
were separated, arranged in columns, or embedded in paragraphs.

The captured response is now a regression fixture at
`tests/fixtures/infraction-image.ocr.json`, with separately annotated expected
business fields and a provenance note. The photograph labels itself as a
fictitious/synthetic document; the OCR capture is real, not a fabricated OCR response.

Version 2 addresses the failures in these stages:

1. Field prefixes accept `11 DATA` and punctuation variants while excluding
   CPF, CEP, dates, and decimal amounts. Inline labels may omit their colon.
2. `form_layout.py` reconstructs numbered form cells from label rows and region
   boxes. Columns, pages, overlapping labels, and large gaps limit associations.
   Coordinate labels inside a numbered description remain part of that field.
   Without geometry, an immediate value can follow a label, but rows of multiple
   labels followed by values remain unresolved. Original excerpts stay in evidence.
3. Extended document headings and nearby split number/year lines are recognized.
   Party address fragments are joined with newlines in printed field order;
   the address number does not replace the document number.
4. Specific narrative patterns identify the named property, the area after
   `SUPRIMIR`, and the explicit total after `MULTA EQUIVALENTE A R$`. Subareas and
   per-hectare prices do not replace those totals. No totals are calculated.
5. Multiline legal citations and references are retained. Issuing-officer stamp
   text is handled separately from names/registrations in cited documents.
6. Complete DMS pairs delimit vertices across commas, semicolons, or lines.
   A direction recognized as digit `0` is preserved, flagged, and given a lower
   score. The mapper does not silently change the OCR to letter `O`.

Replaying this capture fills 15 of 18 business fields and all 17 numbered fields.
Series, CAR, and visual signatures remain unresolved. Examples: document `00092`,
reference `00318/2026`, date `17/03/2026`, area `23.4187`, fine `117093.50`.
This is a regression result for a fixed OCR capture, not a general accuracy rate.

After updating the code, restart the API (or rebuild its Docker image) and check
that responses report `_meta.mapper_model = portuguese-form-rules-v2`.

## Implementation and review sequence

1. Align `app/schemas/extraction.py` with `schema-hackathon.md`: coordinates are a
   list of strings, optional numbered `fields` are supported, and every field has
   confidence/review. Reject inconsistent value/status/confidence combinations.
2. Read OCR content through `app/services/ocr_text.py`, preserving line and table
   boundaries and connecting excerpts to region IDs. Exact matching is preferred;
   full content/region sequence alignment disambiguates repeated text. HTML entities
   are decoded; only label matching folds accents/case. Region text is a fallback
   when content is empty. Unmatched excerpts have no invented region ID.
3. Collect candidates with `app/services/mapper_rules.py`. Match explicit titles,
   labels, party sections, reference sections, and numbered form fields. Keep
   references separate from the main document's number and year.
4. Resolve candidates in `app/services/field_mapper.py`. Conflicting scalar values
   become null. Combine supported list entries and retain their evidence. Check
   dates, hours, numeric formats, and schema types before constructing the result.
5. Inject the concrete mapper in `app/main.py`. `ExtractionService` already calls
   it and records total processing duration; FastAPI serializes the result using
   `_meta`, `_review`, and `_warnings`. These aliases are also accepted on input
   for response validation/export. The former pending mapper and environment-only
   model label were removed. `FieldMapper` remains an injectable interface.
6. Export using `python -m scripts.export_json IMAGE --output-dir outputs`.
   Validate the API response and write one UTF-8 JSON per image basename.

Each stage has contract or behavior tests. The integration test runs actual image
cleaning, API/adapter ASGI requests, Textract block conversion, mapping, and output
validation; only the AWS response is simulated.

## Supported forms

The complete alias lists are `DOCUMENT_TITLES` and `LABEL_GROUPS` in
`app/services/mapper_rules.py`. All ten hackathon document types have Portuguese
title rules. Examples of supported inputs:

```text
AUTO DE INFRAÇÃO Nº 00831/2026
Data de emissão: 13/09/2026
Município: São Félix do Xingu
Autuado: Pessoa Exemplo
CPF/CNPJ: 000.000.000-00
Endereço: Rua Exemplo, 10
Área (ha): 1.234,56 ha
Valor da multa: R$ 12.345,67
Vértice 1: 2°58'36,2"S 54°12'01,0"W
Referências: Auto de constatação nº 00318/2026
Assinatura do autuado: recusou-se a assinar
01 - Nome da propriedade: Sítio Exemplo
```

- Keep identifiers as printed, including leading zeros and punctuation. Never
  derive the year from the current date or repair an OCR digit.
- Convert only `area_ha` and `fine_brl` using Brazilian numeric notation. Thus
  `1.234,56` becomes `1234.56`; ambiguous/unsupported notation or units become null.
  No area or currency conversion is performed.
- Preserve each coordinate pair verbatim. Supported paired DMS, decimal, and
  explicitly labeled UTM syntax is checked without coordinate conversion. DMS
  vertices can span lines and be separated by commas or semicolons; decimal commas
  within an axis are never treated as vertex boundaries.
  This is not geospatial validation. Datum names alone are not vertices.
- Semicolon-separated legal citations and references become list entries.
- Party roles establish local context for following name, CPF/CNPJ, and address
  labels. Address number, neighborhood, CEP, and municipality can continue that
  context; location/description sections end it. Generic numbers
  inside person/reference sections cannot replace the main document number.
- Signatures are only explicit textual descriptions such as `ausente`,
  `recusou-se a assinar`, or `assinado`. A recognized name does not prove that a
  signature exists, and absence of OCR text does not prove a missing signature.
- `fields` preserves the text after a numbered prefix, keyed by the printed
  number. Conflicting entries with the same number are retained in review evidence
  and produce null instead of overwriting one another.

## Review and confidence

`_review[field].evidence` contains all contributing/conflicting excerpts and
optional region IDs. The singular excerpt/region properties mirror the first
entry for compatibility. The source is OCR output, not a verified transcription
of the image. Composite fields currently have evidence at field level, not a
separate score for each list member.

| Status | Meaning |
|---|---|
| `extracted` | A supported explicit rule produced a validated value |
| `unknown` | OCR/rules cannot establish a value; not proof of absence |
| `explicitly_absent` | Source explicitly says absent/not applicable |
| `unreadable` | Source explicitly marks the value unreadable |
| `ambiguous` | Conflicting candidates, uncertainty markers, or invalid format |

`not_present` and `not_processed` remain accepted schema statuses for compatibility;
the local mapper does not use them to describe missing OCR output. Null values
always have zero confidence. Extracted values require source evidence.

Scores are review heuristics capped at 0.65 for explicit rules, 0.5 for layout or
multiline associations, and 0.35 for suspect coordinate direction markers. OCR
warnings or partially mapped entries additionally cap scores at 0.5. The presence
of a region ID alone no longer raises a score. These are not calibrated accuracy probabilities.
Original Textract block confidences are not currently carried through the adapter.
`_meta.review_required` remains true. `rule_mapper_limitations` always explains
the supported-rule boundary; `partial_field` marks incomplete composite results.

## Validation and remaining limits

Run `python -m pytest -q`. Relevant files are `tests/test_extraction_schema.py`,
`tests/test_field_mapper.py`, `tests/test_extraction_pipeline.py`,
`tests/test_api.py`, and `tests/test_export_json.py`.

`tests/fixtures/labeled_infraction.txt` and its expected JSON are **synthetic,
annotated fixtures**, not proof of accuracy on real environmental documents.
Tests cover both text and layout HTML, supported titles, multiple vertices,
references, leading zeros, locale numbers, invalid dates, conflicts, missing text,
party boundaries, explicit signature descriptions, and export failure behavior.

The mapper leaves unsupported prose, unfamiliar labels, and uncertain readings
unresolved. It supports numbered form columns and nearby label/value associations,
but arbitrary layouts, merged regions spanning columns, and unreadable boundaries
can still require review. Narrative extraction uses explicit patterns, not general
language interpretation. Add new
aliases/rules with annotated regressions rather than globally searching for the
first number, CPF, or date. Printed identifiers are not checked against registries
or repaired using checksums. Visual signatures require an image-aware stage.

Live OCR quality, handwriting, coverage across municipalities, latency on target
hardware, and confidence calibration still require annotated real photographs
and a running backend. Unknown results can be legitimate API successes; network,
OCR, or processing failures remain HTTP errors and must not become empty successes.

## Export behavior

The API does not persist uploaded images or results. The optional client CLI writes
the validated response, including review extensions permitted by the hackathon.
Use `--api-url` to choose the API and `--timeout` to change the 180-second timeout.
It refuses existing outputs and basename collisions before making requests. It
stops on an error with exit code 1, retaining successful files from earlier images.
Use a fresh output directory for subsequent evaluation runs.

## Save and replay OCR explicitly

The diagnostic CLI saves `ocr.json` and `mapped.json` in a new directory. Capture a
prepared image through the local adapter:

```powershell
python -m scripts.diagnose_extraction infraction-image.jpg --output-dir outputs/infraction-live
```

Replay the regression capture with the current mapper, without another OCR call:

```powershell
python -m scripts.diagnose_extraction tests/fixtures/infraction-image.ocr.json --from-ocr --output-dir outputs/infraction-replay
```

Both commands refuse to overwrite an existing run. Persisting OCR is an explicit
diagnostic action; normal API requests still do not store image/OCR data.
