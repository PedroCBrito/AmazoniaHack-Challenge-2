# Provenance

`infraction-image.ocr.json` is an actual response captured from the user's locally
running OCR adapter, using `infraction-image.jpg` after the application's OpenCV
preparation. It was saved by `scripts.diagnose_extraction` during this correction.
The photographed document itself explicitly states it is fictitious/synthetic.
The model identifier is retained exactly as reported by that adapter; it does not
independently establish which inference provider was configured.

The expected JSON was annotated by inspecting the image and the captured text.
It tests mapping of that fixed OCR, not OCR accuracy or a live service. Longitude
markers recognized as digit `0` are intentionally preserved and require a warning
and low confidence; no silent replacement by letter `O` is expected. Series and
CAR are unresolved; OCR stamp text alone cannot establish visual signatures.

The original `test.json` returned only erroneous `fields` entries for `5`, `68`,
and `638`. Regression tests require the actual 17 numbered fields and distinguish
the document number from the address, references, areas, and per-hectare price.
