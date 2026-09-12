ALLOWED_TAGS = [
    "math", "br", "i", "b", "u", "del", "sup", "sub", "table", "tr",
    "td", "p", "th", "div", "pre", "h1", "h2", "h3", "h4", "h5",
    "ul", "ol", "li", "input", "a", "span", "img", "hr", "tbody",
    "small", "caption", "strong", "thead", "big", "code", "chem",
]

ALLOWED_ATTRIBUTES = [
    "class", "colspan", "rowspan", "display", "checked", "type", "border",
    "value", "style", "href", "alt", "align", "data-bbox", "data-label",
]

OCR_LAYOUT_PROMPT = f"""
OCR this image to HTML, arranged as layout blocks. Each layout block should be a
div with the data-bbox attribute in x0 y0 x1 y1 format. Bboxes are normalized
0-1000. The data-label attribute is the label for the block.

Use these labels: Caption, Footnote, Equation-Block, List-Group, Page-Header,
Page-Footer, Image, Section-Header, Table, Text, Complex-Block, Code-Block,
Form, Table-Of-Contents, Figure, Chemical-Block, Diagram, Bibliography,
Blank-Page.

Only use these tags {ALLOWED_TAGS}, and these attributes {ALLOWED_ATTRIBUTES}.

Guidelines:
* Put inline and block math in <math> tags using KaTeX-compatible LaTeX.
* Preserve table structure with colspan and rowspan.
* Preserve formatting, spacing, indentation, and special characters.
* Describe images in an img alt attribute. Do not set src.
* Mark checkboxes and radio buttons properly.
* Join text into natural paragraphs and preserve the reading order.
* Preserve list markers and indentation.
* Use the simplest HTML structure that represents the document accurately.
""".strip()
