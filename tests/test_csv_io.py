from pathlib import Path

import pytest

from chronologia.csv_io import CsvFormatError, parse_events, read_events, write_events

EXEMPLE = Path(__file__).parent.parent / "input_claude" / "exemple_timeline.csv"


def test_exemple_reel():
    if not EXEMPLE.exists():
        pytest.skip("CSV d'exemple absent")
    result = read_events(EXEMPLE)
    assert result.issues == []
    assert len(result.events) == 223


def test_lignes_courtes_et_colonne_source_optionnelle():
    result = parse_events(b"start,end,title,color,source\n1861,1861,Titre,green\n")
    assert len(result.events) == 1
    assert result.events[0].source == ""
    assert result.events[0].is_point


def test_sans_colonne_source():
    result = parse_events(b"start,end,title,color\n1861,1900,Titre,green\n")
    assert not result.events[0].is_point


def test_fin_avant_debut_est_corrigee_et_signalee():
    result = parse_events(b"start,end,title,color\n19600722,19050417,Loi,skyblue\n")
    event = result.events[0]
    assert event.start.value < event.end.value
    assert [i.line for i in result.issues] == [2]
    assert not result.issues[0].skipped


def test_couleur_inconnue_devient_grise_et_signalee():
    result = parse_events(b"start,end,title,color\n1990,1990,GATT,yallow\n")
    assert result.events[0].color_hex == "#808080"
    assert len(result.issues) == 1


def test_dates_invalides_et_titre_vide_sont_ignores():
    raw = b"start,end,title,color\nxx,1990,A,red\n1990,1990,,red\n1990,1990,B,red\n"
    result = parse_events(raw)
    assert [e.title for e in result.events] == ["B"]
    assert sorted(i.line for i in result.issues if i.skipped) == [2, 3]


def test_formats_de_dates_melanges():
    raw = b"start,end,title,color\n04/09/1870,1940,A,red\n187009,18700910,B,red\n"
    assert len(parse_events(raw).events) == 2


def test_separateur_point_virgule_et_cp1252():
    raw = "start;end;title;color\n1900;1900;Été;red\n".encode("cp1252")
    assert parse_events(raw).events[0].title == "Été"


def test_colonne_obligatoire_absente():
    with pytest.raises(CsvFormatError):
        parse_events(b"start,end,title\n1900,1900,A\n")


def test_fichier_vide():
    with pytest.raises(CsvFormatError):
        parse_events(b"")


def test_aller_retour_et_neutralisation_des_formules(tmp_path):
    raw = b"start,end,title,color,source\n1900,1901,=SOMME(A1),red,-cmd\n"
    events = parse_events(raw).events
    out = tmp_path / "out.csv"
    write_events(out, events)
    content = out.read_text(encoding="utf-8-sig")
    assert "'=SOMME(A1)" in content and "'-cmd" in content
    again = read_events(out).events
    assert again[0].title == "=SOMME(A1)" and again[0].source == "-cmd"


def test_export_de_l_exemple_conserve_les_donnees(tmp_path):
    if not EXEMPLE.exists():
        pytest.skip("CSV d'exemple absent")
    events = read_events(EXEMPLE).events
    assert events
    out = tmp_path / "out.csv"
    write_events(out, events)
    assert read_events(out).events == events
