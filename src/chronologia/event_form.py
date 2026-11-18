"""Validation d'un événement saisi dans le formulaire (sans Qt, donc testable)."""

from __future__ import annotations

from .colors import resolve_color
from .dates import DateParseError, parse_date
from .model import Event

MAX_TITLE_LENGTH = 500
MAX_SOURCE_LENGTH = 5000

# codes d'erreur, traduits par l'interface
TITLE_EMPTY = "title_empty"
TITLE_TOO_LONG = "title_too_long"
START_INVALID = "start_invalid"
END_INVALID = "end_invalid"
END_BEFORE_START = "end_before_start"
COLOR_INVALID = "color_invalid"
SOURCE_TOO_LONG = "source_too_long"


def build_event(
    title: str, start: str, end: str, color: str, source: str
) -> tuple[Event | None, dict[str, str]]:
    """Renvoie ``(événement, {})`` si tout est valide, sinon ``(None, {champ: code})``.

    Une fin vide donne un événement ponctuel.
    """
    errors: dict[str, str] = {}
    title = title.strip()
    source = source.strip()
    color = color.strip()
    if not title:
        errors["title"] = TITLE_EMPTY
    elif len(title) > MAX_TITLE_LENGTH:
        errors["title"] = TITLE_TOO_LONG
    if len(source) > MAX_SOURCE_LENGTH:
        errors["source"] = SOURCE_TOO_LONG
    if resolve_color(color) is None:
        errors["color"] = COLOR_INVALID

    start_date = end_date = None
    try:
        start_date = parse_date(start)
    except DateParseError:
        errors["start"] = START_INVALID
    if end.strip():
        try:
            end_date = parse_date(end)
        except DateParseError:
            errors["end"] = END_INVALID
    else:
        end_date = start_date
    if start_date and end_date and end_date.value < start_date.value:
        errors["end"] = END_BEFORE_START

    if errors or start_date is None or end_date is None:
        return None, errors
    return Event(start_date, end_date, title, color, source), {}
