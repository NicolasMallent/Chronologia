import json

import pytest

from chronologia.formats import (
    MAX_FORMATS,
    MAX_SIDE_MM,
    MIN_SIDE_MM,
    STANDARD_FORMATS,
    FormatError,
    PageFormat,
    PageSettings,
    check_format,
    load_formats,
    save_formats,
)
from chronologia.pdf_export import PAGE_SIZES_MM, PDF_COMFORT_LIMIT_MM, export_divisor


def test_formats_normalises_de_a6_a_a0():
    assert [f.name for f in STANDARD_FORMATS] == ["A6", "A5", "A4", "A3", "A2", "A1", "A0"]
    assert PAGE_SIZES_MM["A6"] == (105.0, 148.0) and PAGE_SIZES_MM["A0"] == (841.0, 1189.0)
    assert all(f.width_mm < f.height_mm for f in STANDARD_FORMATS)


def test_orientation():
    a4 = PageFormat("A4", 210, 297)
    assert a4.oriented(landscape=True) == (297, 210)
    assert a4.oriented(landscape=False) == (210, 297)
    banderole = PageFormat("Banderole", 10000, 1000)  # enregistrée en paysage
    assert banderole.oriented(landscape=True) == (10000, 1000)
    assert banderole.oriented(landscape=False) == (1000, 10000)


def test_reglages_paysage():
    assert PageSettings(1189, 841).landscape and not PageSettings(841, 1189).landscape


def test_verification_d_un_nouveau_format():
    fmt = check_format("  Banderole  ", 10000, 1000, [])
    assert fmt == PageFormat("Banderole", 10000.0, 1000.0)
    for name, w, h, code in (
        ("", 100, 100, FormatError.NAME_INVALID),
        ("x" * 61, 100, 100, FormatError.NAME_INVALID),
        ("Ok", MIN_SIDE_MM - 1, 100, FormatError.SIZE_INVALID),
        ("Ok", 100, MAX_SIDE_MM + 1, FormatError.SIZE_INVALID),
        ("Ok", float("nan"), 100, FormatError.SIZE_INVALID),
        ("Ok", float("inf"), 100, FormatError.SIZE_INVALID),
        ("a0", 100, 100, FormatError.NAME_EXISTS),  # nom d'un format normalisé
        ("BANDEROLE", 100, 100, FormatError.NAME_EXISTS),
    ):
        with pytest.raises(FormatError) as info:
            check_format(name, w, h, [fmt])
        assert info.value.code == code, name
    pleins = [PageFormat(f"F{i}", 100, 100) for i in range(MAX_FORMATS)]
    with pytest.raises(FormatError) as info:
        check_format("Un de plus", 100, 100, pleins)
    assert info.value.code == FormatError.TOO_MANY


def test_enregistrement_et_relecture(tmp_path):
    path = tmp_path / "sous" / "formats.json"
    formats = [PageFormat("Banderole", 10000, 1000), PageFormat("Affiche œuvre", 600, 800)]
    save_formats(formats, path)
    assert load_formats(path) == (formats, None)
    assert not list(path.parent.glob("*.tmp"))  # écriture atomique


def test_fichier_absent_ou_illisible(tmp_path):
    assert load_formats(tmp_path / "absent.json") == ([], None)
    bad = tmp_path / "formats.json"
    for content in ("pas du json", '{"formats": 3}', '{"formats": [{"name": "x"}]}', "[]"):
        bad.write_text(content, encoding="utf-8")
        formats, warning = load_formats(bad)
        assert formats == [] and warning and "formats.json" in warning
        assert bad.read_text(encoding="utf-8") == content  # jamais écrasé


def test_fichier_hostile_borne(tmp_path):
    path = tmp_path / "formats.json"
    too_big = {
        "formats": [{"name": f"f{i}", "width_mm": 100, "height_mm": 100} for i in range(9000)]
    }
    path.write_text(json.dumps(too_big), encoding="utf-8")
    assert load_formats(path)[0] == [] and load_formats(path)[1]
    absurde = {"formats": [{"name": "x", "width_mm": 1e12, "height_mm": 100}]}
    path.write_text(json.dumps(absurde), encoding="utf-8")
    assert load_formats(path)[0] == [] and load_formats(path)[1]
    doublon = {"formats": [{"name": "a", "width_mm": 100, "height_mm": 100}] * 2}
    path.write_text(json.dumps(doublon), encoding="utf-8")
    assert load_formats(path)[0] == []


@pytest.mark.parametrize(
    "w, h, expected",
    [
        (297, 210, 1),
        (PDF_COMFORT_LIMIT_MM, 1000, 1),
        (PDF_COMFORT_LIMIT_MM + 1, 1000, 2),
        (10000, 1000, 2),  # banderole de 10 m → PDF de 5 m
        (20000, 1000, 4),
    ],
)
def test_diviseur_d_export(w, h, expected):
    assert export_divisor(w, h) == expected
    assert export_divisor(h, w) == expected
    assert max(w, h) / export_divisor(w, h) <= PDF_COMFORT_LIMIT_MM
