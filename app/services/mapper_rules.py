"""Conservative Portuguese form rules. Matching keys may fold accents; values never do."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any

from app.schemas.extraction import FieldStatus, SourceEvidence
from app.services.ocr_text import SourceLine


def folded(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(c))


DOCUMENT_TITLES = {
    "auto de constatacao": "finding_notice",
    "termo de constatacao": "finding_notice",
    "auto de infracao": "infraction_notice",
    "auto de embargo": "embargo_notice",
    "termo de embargo": "embargo_notice",
    "auto de apreensao": "seizure_notice",
    "termo de apreensao": "seizure_notice",
    "notificacao": "notification",
    "ordem de fiscalizacao": "inspection_order",
    "registro de denuncia": "complaint_record",
    "ficha de denuncia": "complaint_record",
    "relatorio de fiscalizacao": "inspection_report",
    "capa de processo": "case_file_cover",
    "validacao de desmatamento": "deforestation_validation",
}
TITLE = re.compile("|".join(re.escape(key) for key in sorted(DOCUMENT_TITLES, key=len, reverse=True)))
NUMBER = re.compile(r"\s*(?:n(?:\.\s*)?[º°o]\.?|n\.|n[úu]mero)?\s*[:,\-]?\s*(?P<number>\d(?:[\dA-Za-z.-]*[\dA-Za-z])?)(?:(?:\s*/\s*|\s+ano\s*[/ :]\s*)(?P<year>\d{4}))?", re.I)
NUMBERED = re.compile(r"^(\d{1,3})(?:\s*[.)\-–—]\s*|\s+)([^\W\d_].*)$", re.S)

LABEL_GROUPS = {
    "number": ("numero", "nº", "n°", "numero do documento", "numero do auto"),
    "series": ("serie",),
    "year": ("ano", "ano de emissao"),
    "issued_date": ("data", "data de emissao", "data da lavratura", "data de lavratura"),
    "issued_time": ("hora", "horario", "hora da lavratura", "hora de emissao"),
    "municipality": ("municipio", "municipio de emissao"),
    "agency": ("orgao", "orgao emissor", "orgao ambiental"),
    "property_name": ("propriedade", "nome da propriedade", "nome do imovel", "imovel rural"),
    "car": ("car", "cadastro ambiental rural", "numero do car"),
    "coordinates": ("coordenadas", "coordenadas geograficas", "vertices"),
    "area_ha": ("area", "area (ha)", "area ha", "area em hectares", "area desmatada", "area embargada"),
    "legal_basis": ("fundamento legal", "fundamentacao legal", "base legal", "enquadramento legal", "dispositivos legais", "legislacao infringida/artigo", "legislacao infrigida/artigo"),
    "fine_brl": ("multa", "valor da multa", "multa (r$)", "valor da multa (r$)"),
    "references": ("referencia", "referencias", "documentos relacionados", "documentos referenciados"),
    "officer_registration": ("matricula do fiscal", "matricula do agente", "matricula do autuante", "matricula"),
    "party:cited_party": ("autuado", "autuada", "infrator", "notificado", "nome do autuado", "razao social do autuado"),
    "party:issuer": ("autuante", "fiscal", "agente autuante", "nome do fiscal"),
    "party:witness": ("testemunha", "testemunha 1", "testemunha 2"),
    "party:found_on_site": ("encontrado no local", "pessoa encontrada no local"),
    "party:representative": ("representante", "representante legal"),
    "party_name": ("nome", "razao social"),
    "party_document": ("cpf", "cnpj", "cpf/cnpj", "cpf / cnpj", "cnpj/cpf", "cnpj / cpf"),
    "party_address": ("endereco", "endereco completo"),
    "party_neighborhood": ("bairro",),
    "party_postal_code": ("cep",),
    "form_only": ("inscricao estadual", "atividade", "local"),
    "description": ("descricao da irregularidade", "descricao da infracao"),
    "officer_stamp": ("assinatura, carimbo e n° da matricula do", "assinatura, carimbo e nº da matricula do", "assinatura, carimbo e n da matricula do"),
    "secretary_stamp": ("assinatura do secretario/carimbo",),
    "signature:issuer": ("assinatura do fiscal", "assinatura do autuante", "assinatura do agente"),
    "signature:cited_party": ("assinatura do autuado", "assinatura do infrator", "assinatura do notificado"),
    "document_type": ("tipo de documento", "tipo do documento"),
}
LABELS = {label: name for name, labels in LABEL_GROUPS.items() for label in labels}
VERTEX = re.compile(r"^(?:vertice|ponto|v)\s*\d+$")


@dataclass
class Candidate:
    value: Any = None
    status: FieldStatus = FieldStatus.EXTRACTED
    evidence: list[SourceEvidence] = field(default_factory=list)
    confidence_cap: float = 0.65
    issues: tuple[str, ...] = ()


def label_value(text: str) -> tuple[str, str] | None:
    """Recognize explicit labels, including OCR that omitted punctuation."""
    numbered = NUMBERED.fullmatch(text)
    if numbered:
        text = numbered[2]
    heading, _, continuation = text.partition("\n")
    parts = re.split(r"\s*[:|]\s*", heading, maxsplit=1)
    key = folded(parts[0].strip())
    name = LABELS.get(key)
    if name is None:
        # OCR may omit the colon but retain an explicit known label prefix.
        for label in sorted(LABELS, key=len, reverse=True):
            if key.startswith(label + " "):
                name = LABELS[label]
                parts = [heading[:len(label)], heading[len(label):].strip()]
                break
    if name is None and VERTEX.fullmatch(key):
        name = "vertex"
    if name:
        value = parts[1].strip() if len(parts) == 2 else ""
        return name, "\n".join(part for part in (value, continuation.strip()) if part)
    return None


def missing_status(value: str) -> FieldStatus | None:
    key = folded(value.strip())
    if key in {"ausente", "nao consta", "nao informado", "nao possui", "inexistente", "nao se aplica"}:
        return FieldStatus.EXPLICITLY_ABSENT
    if re.search(r"\bilegivel\b", key):
        return FieldStatus.UNREADABLE
    if "?" in key or re.search(r"\bou\b", key):
        return FieldStatus.AMBIGUOUS
    if not key or key in {"-", "--", "___", "..."}:
        return FieldStatus.UNKNOWN
    return None


def brazilian_number(value: str, name: str) -> float:
    """Only the numeric schema fields accept conversion, with unambiguous units."""
    if name == "fine_brl":
        value = re.sub(r"^R\$\s*", "", value, flags=re.I)
    else:
        value = re.sub(r"\s*(?:ha|hectares?)$", "", value, flags=re.I)
    value = value.strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?", value):
        raise ValueError("Ambiguous numeric notation")
    try:
        number = Decimal(value.replace(".", "").replace(",", "."))
        result = float(number)
        if not number.is_finite() or result == float("inf"):
            raise ValueError("Non-finite number")
        return result
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric notation") from exc


def coordinate_points(value: str) -> list[str] | None:
    """Recognize paired axes, without converting notation or splitting decimal commas.

    This is a syntax check only, not geospatial validation. Unsupported notation
    remains unknown rather than treating a datum/zone label as a vertex.
    """
    atom = r"\d{1,3}\s*[°º]\s*\d{1,2}\s*['’′]\s*\d{1,2}(?:[,.]\d+)?\s*[\"”″]"
    pairs = list(re.finditer(atom + r"\s*[NS]\s+" + atom + r"\s*[EWO0]", value, re.I))
    if pairs:
        cursor = 0
        for pair in pairs:
            if value[cursor:pair.start()].strip(" ,;.\n\r\tEe"):
                return None
            cursor = pair.end()
        if value[cursor:].strip(" ,;.\n\r\tEe"):
            return None
        return [pair[0] for pair in pairs]
    points = [part.strip() for part in value.split(";") if part.strip()]
    for point in points:
        dms = re.findall(r"\d{1,3}\s*[°º]\s*\d{1,2}\s*['’′]\s*\d{1,2}(?:[,.]\d+)?\s*[\"”″]\s*([NSEWO])", point, re.I)
        decimal = re.findall(r"[+-]?\d{1,3}[,.]\d+", point)
        utm = re.findall(r"\d{5,7}(?:[,.]\d+)?", point)
        if len(dms) == 2 and {axis.upper() for axis in dms}.intersection({"N", "S"}) and {axis.upper() for axis in dms}.intersection({"E", "W", "O"}):
            continue
        if len(decimal) == 2 and "°" not in point and "º" not in point:
            continue
        if len(utm) == 2 and re.search(r"\b(?:UTM|E|N)\b", point, re.I):
            continue
        return None
    return points or None


class RuleCollector:
    def __init__(self) -> None:
        self.candidates: dict[str, list[Candidate]] = {}
        self.parties: list[dict] = []
        self.party_evidence: list[SourceEvidence] = []
        self.party: dict | None = None
        self.references_section = False
        self.reference_officer_context = False
        self.current_sources: list[SourceEvidence] = []
        self.current_association: str | None = None

    def add(self, name: str, value: Any, evidence: list[SourceEvidence], status=FieldStatus.EXTRACTED, *, issue: str | None = None):
        sources = self.current_sources if evidence == self.current_sources[:1] else evidence
        issues = tuple(code for code in ("layout_association" if self.current_association else None, issue) if code)
        cap = 0.35 if issue else 0.5 if self.current_association else 0.65
        self.candidates.setdefault(name, []).append(Candidate(value, status, list(sources), cap, issues))

    def read(self, lines: list[SourceLine]) -> dict[str, list[Candidate]]:
        for line in lines:
            self.current_sources = line.sources
            self.current_association = line.association
            # Multiple label/value pairs in a table row remain separate fields.
            # A label-only cell followed by its value is kept together.
            cells = re.split(r"\s+\|\s+", line.text)
            index = 0
            while index < len(cells):
                text = cells[index]
                pair = label_value(text)
                if pair and not pair[1] and index + 1 < len(cells) and not label_value(cells[index + 1]):
                    text = text.rstrip().removesuffix(":") + ": " + cells[index + 1]
                    index += 1
                self.read_line(text, line.evidence)
                index += 1
        populated = [party for party in self.parties if any(party[key] for key in ("name", "document_id", "address"))]
        if populated:
            self.current_association = "party_group" if len(self.party_evidence) > 1 else None
            self.add("parties", populated, self.party_evidence)
        return self.candidates

    def read_line(self, text: str, evidence: SourceEvidence) -> None:
        numbered = NUMBERED.fullmatch(text)
        if numbered:
            self.reference_officer_context = False
            self.add("fields", {numbered[1]: numbered[2]}, [evidence])
        pair = label_value(text)
        if pair:
            name, value = pair
            if name == "officer_registration" and self.reference_officer_context:
                self.add(name, None, [evidence], FieldStatus.UNKNOWN)
                return
            self.reference_officer_context = False
            # Generic numbering inside a reference/person section is not the
            # main document number. Another recognized field ends that scope.
            if name in {"number", "year", "series"} and (self.references_section or self.party is not None):
                if name == "number" and self.party is not None and numbered and missing_status(value) is None:
                    self.append_address(value, evidence)
                    return
                self.add("references" if self.references_section else "parties", None, [evidence], FieldStatus.UNKNOWN)
                return
            self.references_section = name == "references"
            if name.startswith("party:"):
                self.party = {"role": name.split(":")[1], "name": None, "document_id": None, "address": None}
                self.parties.append(self.party)
                self.party_evidence.extend(self.current_sources)
                if missing_status(value) is None:
                    self.party["name"] = value
                else:
                    status = missing_status(value)
                    self.add("parties", None, [evidence], FieldStatus.UNKNOWN if status == FieldStatus.EXPLICITLY_ABSENT else status)
                return
            if name in {"party_name", "party_document", "party_address", "party_neighborhood", "party_postal_code"}:
                if name in {"party_neighborhood", "party_postal_code"}:
                    if self.party is not None and missing_status(value) is None:
                        self.append_address(value, evidence)
                    return
                if self.party is not None and missing_status(value) is None:
                    member = {"party_name": "name", "party_document": "document_id", "party_address": "address"}[name]
                    if self.party[member] not in (None, value):
                        self.add("parties", None, [evidence], FieldStatus.AMBIGUOUS)
                    else:
                        self.party[member] = value
                        self.party_evidence.extend(self.current_sources)
                elif self.party is not None:
                    status = missing_status(value)
                    self.add("parties", None, [evidence], FieldStatus.UNKNOWN if status == FieldStatus.EXPLICITLY_ABSENT else status)
                return
            if name == "municipality" and self.party is not None and numbered:
                if missing_status(value) is None:
                    self.append_address(value, evidence)
                self.read_field(name, value, evidence)
                return
            if name == "form_only":
                if re.match(r"local\b", folded(numbered[2] if numbered else text)):
                    self.party = None
                return
            self.party = None
            self.read_field(name, value, evidence)
            return
        self.party = None
        key = folded(text)
        if key in {"referencias", "referencia", "documentos relacionados", "documentos referenciados"}:
            self.references_section = True
            return
        title = TITLE.match(key)
        if title and not self.references_section:
            rest = text[title.end():].strip()
            if folded(rest).startswith("com a penalidade de multa"):
                rest = rest[len("com a penalidade de multa"):].strip()
            number = NUMBER.fullmatch(rest) if rest else None
            # A title followed by narrative is not a document heading.
            if not rest or number:
                self.reference_officer_context = False
                self.add("document_type", DOCUMENT_TITLES[title[0]], [evidence])
                if number:
                    self.add_number(number, evidence)
                return
        self.read_narrative(text, evidence)

    def append_address(self, value: str, evidence: SourceEvidence) -> None:
        previous = self.party["address"]
        self.party["address"] = "\n".join(part for part in (previous, value) if part)
        self.party_evidence.extend(self.current_sources or [evidence])

    def add_number(self, number: re.Match, evidence: SourceEvidence) -> None:
        self.add("number", number["number"], [evidence])
        if number["year"]:
            self.add("year", number["year"], [evidence])

    def read_field(self, name: str, value: str, evidence: SourceEvidence) -> None:
        if name in {"description", "officer_stamp", "secretary_stamp"}:
            if name == "description":
                self.read_narrative(value, evidence)
            elif name == "officer_stamp":
                self.read_officer_stamp(value, evidence)
            return
        target = "coordinates" if name == "vertex" else "signatures" if name.startswith("signature:") else name
        status = missing_status(value)
        # Explicit signature absence/refusal is a transcribed description.
        if status and not (name.startswith("signature:") and status == FieldStatus.EXPLICITLY_ABSENT):
            self.add(target, None, [evidence], status)
            return
        if name == "references":
            if not self.read_references(value, evidence):
                self.add(name, None, [evidence], FieldStatus.UNKNOWN)
        elif name == "number":
            number = NUMBER.fullmatch(value)
            if number:
                self.add_number(number, evidence)
            else:
                self.add(name, None, [evidence], FieldStatus.AMBIGUOUS)
        elif name == "document_type":
            mapped = DOCUMENT_TITLES.get(folded(value))
            self.add(name, mapped, [evidence], FieldStatus.EXTRACTED if mapped else FieldStatus.UNKNOWN)
        elif name in {"fine_brl", "area_ha"}:
            try:
                self.add(name, brazilian_number(value, name), [evidence])
            except ValueError:
                self.add(name, None, [evidence], FieldStatus.AMBIGUOUS)
        elif name in {"coordinates", "vertex"}:
            # Complete axis pairs delimit DMS vertices; preserve decimal commas.
            points = coordinate_points(value)
            suspect = points and any(re.search(r'[\"”″]\s*0$', point) for point in points)
            self.add("coordinates", points, [evidence], FieldStatus.EXTRACTED if points else FieldStatus.UNKNOWN,
                     issue="ocr_coordinate_marker" if suspect else None)
        elif name == "legal_basis":
            self.add(name, [part.strip() for part in re.split(r";|\n", value) if part.strip()], [evidence])
        elif name.startswith("signature:"):
            # A blank line or an OCR name cannot establish visual signature presence.
            if folded(value) in {"ausente", "nao consta", "nao assinou", "recusou-se a assinar", "recusou assinar", "assinatura ausente", "assinado"}:
                self.add("signatures", {name.split(":")[1]: value}, [evidence])
            else:
                self.add("signatures", None, [evidence], FieldStatus.UNKNOWN)
        elif name == "year" and not re.fullmatch(r"\d{4}", value):
            self.add(name, None, [evidence], FieldStatus.AMBIGUOUS)
        else:
            self.add(name, value, [evidence])

    def read_narrative(self, text: str, evidence: SourceEvidence) -> None:
        if self.read_references(text, evidence):
            self.reference_officer_context = True
        key = folded(text)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            pair = label_value(line)
            if pair and pair[0] == "coordinates":
                parts = [pair[1]]
                for continuation in lines[i + 1:]:
                    if not re.match(r"\s*\d{1,3}\s*[°º]", continuation):
                        break
                    parts.append(continuation)
                self.read_field("coordinates", "\n".join(parts), evidence)
        quantity = r"(\d(?:[\d.,]*\d)?)"
        for match in re.finditer(r"\b(?:suprimir|desmatar|suprimiu|desmatou)\s+" + quantity + r"\s*ha\b", key):
            self.read_contextual_number("area_ha", text, match, evidence)
        for match in re.finditer(r"\b(?:imovel(?: rural)?|propriedade(?: rural)?)\s+denominad[oa]\s+([^,\n]+)", key):
            self.read_field("property_name", text[match.start(1):match.end(1)].strip(), evidence)
        for match in re.finditer(r"\bmulta\s+(?:equivalente a|no valor de|de)\s+r\$\s*" + quantity, key):
            self.read_contextual_number("fine_brl", text, match, evidence)
        if re.fullmatch(r"secretaria municipal (?:da gestao )?(?:do|de) meio ambiente", key.strip()):
            self.add("agency", text.strip(), [evidence])

    def read_contextual_number(self, name: str, text: str, match: re.Match, evidence: SourceEvidence) -> None:
        if re.match(r"\s*(?:ou\b|\?|/)", folded(text[match.end():])):
            self.add(name, None, [evidence], FieldStatus.AMBIGUOUS)
        else:
            self.read_field(name, text[match.start(1):match.end(1)], evidence)

    def read_officer_stamp(self, text: str, evidence: SourceEvidence) -> None:
        # Only the inspector's own stamp can establish the issuing officer.
        # A registration following a cited document belongs to that reference.
        for match in re.finditer(r"\bmatricula\s*[:.]?\s*(\d[\d.\-]*\d)", folded(text)):
            self.add("officer_registration", text[match.start(1):match.end(1)], [evidence])
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if i and folded(line).strip() == "agente de fiscalizacao ambiental":
                name = lines[i - 1].strip()
                if len(name.split()) >= 2 and not any(char.isdigit() for char in name):
                    self.parties.append({"role": "issuer", "name": name, "document_id": None, "address": None})
                    self.party_evidence.extend(self.current_sources)

    def read_references(self, text: str, evidence: SourceEvidence) -> bool:
        references = []
        key = folded(text)
        status = missing_status(text)
        if status and TITLE.search(key):
            self.add("references", None, [evidence], status)
            return True
        for title in TITLE.finditer(key):
            number = NUMBER.match(text[title.end():])
            if number and (not text[title.end() + number.end():] or re.match(r"[\s,;.)]", text[title.end() + number.end():])):
                references.append({"document_type": DOCUMENT_TITLES[title[0]], "number": number["number"], "year": number["year"]})
        if references:
            self.add("references", references, [evidence])
        return bool(references)
