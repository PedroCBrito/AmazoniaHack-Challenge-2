# Output schema

This is the shape we ask for in Challenge 2, and the reason is practical: twelve
teams producing twelve formats cannot be compared, and we want to learn which
approach to build into the app.

**One JSON file per image, same basename.** For
`documents/03-auto-de-infracao-00831__infraction-notice-00831.jpg`, write
`03-auto-de-infracao-00831__infraction-notice-00831.json`.

## Common fields

Every document, whatever the municipality, maps onto these. Use `null` when the
document does not carry the field, and never guess.

| Field | Type | Notes |
|---|---|---|
| `document_type` | string | `finding_notice`, `infraction_notice`, `embargo_notice`, `seizure_notice`, `notification`, `inspection_order`, `complaint_record`, `inspection_report`, `case_file_cover`, `deforestation_validation` |
| `number` | string | as printed, keeping leading zeros: `"00831"` |
| `series` | string or null | some forms carry one |
| `year` | string | |
| `issued_date` | string | `DD/MM/YYYY` as printed |
| `issued_time` | string or null | `HH:MM` |
| `municipality` | string | |
| `agency` | string | |
| `parties` | list | see below |
| `property_name` | string or null | |
| `car` | string or null | the rural property registry code, as printed |
| `area_ha` | number or null | decimal point, not comma |
| `coordinates` | list of strings | exactly as printed, one per vertex. Do not convert |
| `legal_basis` | list of strings | articles, decrees and laws cited |
| `fine_brl` | number or null | |
| `references` | list | documents this one names, see below |
| `officer_registration` | string or null | the inspector's staff number |
| `signatures` | object | `{"issuer": ..., "cited_party": ...}`, and say so when a signature was refused or absent |
| `fields` | object | free form: the form's own numbered fields, verbatim. Optional |
| `confidence` | object | one entry per field above, `0.0` to `1.0` |

`parties` entries:

```json
{"role": "cited_party", "name": "...", "document_id": "...", "address": "..."}
```

`role` is one of `cited_party`, `issuer`, `witness`, `found_on_site`,
`representative`. `document_id` is the CPF or CNPJ as printed.

`references` entries:

```json
{"document_type": "finding_notice", "number": "00318", "year": "2026"}
```

This one matters more than it looks. The paperwork is a chain: the fine names
the finding notice, the embargo names the fine. Getting those numbers right is
what lets an auditor follow a case, and it is the part a generic extractor
usually drops.

## Two rules

**Transcribe, do not normalise.** If the form says `2°58'36,2"S`, that is what
goes in. Each municipality writes coordinates differently and that difference is
real. The same goes for the comma as decimal separator inside a text field.

**Confidence is not decoration.** A field you could not read is `null` with a
low confidence, never a plausible guess. A wrong value stated confidently is
worse than an admitted gap, because a person downstream signs the document.

## If you extend it

Adding fields is fine and expected. Keep the ones above under the same names so
the outputs stay comparable.
