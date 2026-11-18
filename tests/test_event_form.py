import pytest

from chronologia import event_form as f
from chronologia.event_form import build_event


def test_evenement_valide_et_ponctuel_si_fin_vide():
    event, errors = build_event(" Loi ", "1901", "", "skyblue", "")
    assert errors == {} and event.title == "Loi" and event.is_point and event.color == "skyblue"


def test_periode_et_formats_melanges():
    event, errors = build_event("Guerre", "28/07/1914", "19181111", "#FF0000", " note ")
    assert errors == {} and not event.is_point and event.source == "note"


@pytest.mark.parametrize(
    "args, field, code",
    [
        (("", "1900", "", "red", ""), "title", f.TITLE_EMPTY),
        (("x" * 501, "1900", "", "red", ""), "title", f.TITLE_TOO_LONG),
        (("A", "abc", "", "red", ""), "start", f.START_INVALID),
        (("A", "1900", "zz", "red", ""), "end", f.END_INVALID),
        (("A", "1950", "1900", "red", ""), "end", f.END_BEFORE_START),
        (("A", "1900", "", "yallow", ""), "color", f.COLOR_INVALID),
        (("A", "1900", "", "", ""), "color", f.COLOR_INVALID),
        (("A", "1900", "", "red", "s" * 5001), "source", f.SOURCE_TOO_LONG),
    ],
)
def test_erreurs(args, field, code):
    event, errors = build_event(*args)
    assert event is None and errors[field] == code


def test_plusieurs_erreurs_a_la_fois():
    _, errors = build_event("", "x", "", "nope", "")
    assert set(errors) == {"title", "start", "color"}
