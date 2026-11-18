"""Import et export CSV des événements.

Import tolérant : une ligne douteuse est corrigée ou ignorée et signalée dans
``ImportResult.issues``, sans bloquer le fichier. Tout reste local (aucun accès réseau).
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

from .colors import DEFAULT_COLOR_HEX, resolve_color
from .dates import DateParseError, parse_date
from .model import Event, ImportIssue, ImportResult

REQUIRED_COLUMNS = ("start", "end", "title", "color")
OPTIONAL_COLUMNS = ("source",)
MAX_FILE_BYTES = 20 * 1024 * 1024  # garde-fou contre un fichier démesuré
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class CsvFormatError(ValueError):
    """Le fichier est inutilisable (colonne obligatoire absente, trop gros...).

    ``code`` et ``detail`` permettent à l'interface de traduire le message.
    """

    EMPTY_FILE = "empty_file"
    MISSING_COLUMNS = "missing_columns"
    FILE_TOO_LARGE = "file_too_large"

    def __init__(self, message: str, code: str = "", detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _unescape(text: str) -> str:
    """Retire l'apostrophe ajoutée à l'export pour neutraliser une formule."""
    if len(text) > 1 and text[0] == "'" and text[1] in _FORMULA_PREFIXES:
        return text[1:]
    return text


def _escape(text: str) -> str:
    """Neutralise les formules (``=``, ``+``, ``-``, ``@``) à l'ouverture dans un tableur."""
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _detect_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def read_events(path: str | Path) -> ImportResult:
    """Lit un fichier CSV (UTF-8 avec ou sans BOM, sinon Windows-1252)."""
    p = Path(path)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise CsvFormatError("fichier trop volumineux", CsvFormatError.FILE_TOO_LARGE)
    return parse_events(p.read_bytes())


def parse_events(raw: bytes) -> ImportResult:
    text = _decode(raw)
    first_line = text.split("\n", 1)[0]
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_detect_delimiter(first_line))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvFormatError("fichier vide", CsvFormatError.EMPTY_FILE) from None

    names = [h.strip().lower() for h in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in names]
    if missing:
        raise CsvFormatError(
            "colonnes obligatoires absentes : " + ", ".join(missing),
            CsvFormatError.MISSING_COLUMNS,
            ", ".join(missing),
        )
    index = {
        name: names.index(name) for name in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if name in names
    }

    def cell(row: list[str], name: str) -> str:
        i = index.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    result = ImportResult()
    for row in reader:
        line = reader.line_num
        if not any(c.strip() for c in row):
            continue
        title = _unescape(cell(row, "title"))
        if not title:
            result.issues.append(
                ImportIssue(line, "titre vide", skipped=True, code=ImportIssue.EMPTY_TITLE)
            )
            continue
        start_text, end_text = cell(row, "start"), cell(row, "end")
        try:
            start = parse_date(start_text)
        except DateParseError as exc:
            result.issues.append(
                ImportIssue(line, str(exc), True, ImportIssue.INVALID_START, start_text)
            )
            continue
        try:
            end = parse_date(end_text) if end_text else start
        except DateParseError as exc:
            result.issues.append(
                ImportIssue(line, str(exc), True, ImportIssue.INVALID_END, end_text)
            )
            continue
        if end.value < start.value:
            start, end = end, start
            result.issues.append(
                ImportIssue(
                    line,
                    "fin avant début : dates remises dans l'ordre",
                    code=ImportIssue.END_BEFORE_START,
                )
            )
        color = cell(row, "color")
        if resolve_color(color) is None:
            result.issues.append(
                ImportIssue(
                    line,
                    f"couleur inconnue {color!r} : {DEFAULT_COLOR_HEX} utilisée",
                    code=ImportIssue.UNKNOWN_COLOR,
                    detail=color,
                )
            )
            color = DEFAULT_COLOR_HEX
        result.events.append(Event(start, end, title, color, _unescape(cell(row, "source"))))
    return result


def write_events(path: str | Path, events: list[Event]) -> None:
    """Écrit les événements en CSV UTF-8 avec BOM (lisible par les tableurs).

    L'écriture est atomique : en cas d'échec, l'ancien fichier reste intact.
    """
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
            for e in events:
                writer.writerow(
                    [e.start.to_csv(), e.end.to_csv(), _escape(e.title), e.color, _escape(e.source)]
                )
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
