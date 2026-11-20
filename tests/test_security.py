"""Tests de robustesse, de confidentialité et de sécurité (voir SECURITY.md et PRIVACY.md)."""

import getpass
import os
import re
import socket
import stat
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from chronologia import categories as cat
from chronologia.csv_io import (
    MAX_FILE_BYTES,
    CsvFormatError,
    parse_events,
    read_events,
    write_events,
)
from chronologia.main_window import MainWindow
from chronologia.model import MAX_EVENTS, MAX_SOURCE_LENGTH, MAX_TITLE_LENGTH, ImportIssue
from chronologia.textutil import plain

HEADER = b"start,end,title,color\n"
SRC = Path(__file__).parent.parent / "src" / "chronologia"
posix_only = pytest.mark.skipif(os.name != "posix", reason="droits POSIX")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# --- fichiers CSV hostiles -----------------------------------------------------------------


def test_champ_demesure_donne_une_erreur_claire_et_non_un_plantage():
    with pytest.raises(CsvFormatError) as error:
        parse_events(HEADER + b"1900,1900," + b"x" * 200_000 + b",red\n")
    assert error.value.code == CsvFormatError.MALFORMED


@pytest.mark.parametrize(
    "raw", [bytes(range(256)) * 50, b"\x00" * 1000, b"\xff\xfe" * 100, b"a,\n" * 50]
)
def test_contenu_binaire_ou_incoherent_ne_plante_pas(raw):
    try:
        parse_events(raw)
    except CsvFormatError:
        pass  # refus propre


def test_nombre_d_evenements_borne():
    body = b"".join(b"1900,1900,T%d,red\n" % i for i in range(MAX_EVENTS + 50))
    result = parse_events(HEADER + body)
    assert len(result.events) == MAX_EVENTS
    assert result.issues[-1].code == ImportIssue.TOO_MANY_EVENTS and result.issues[-1].skipped


def test_titre_et_source_tronques_et_signales():
    raw = HEADER[:-1] + b",source\n1900,1900," + b"t" * 5000 + b",red," + b"s" * 20000 + b"\n"
    result = parse_events(raw)
    event = result.events[0]
    assert len(event.title) == MAX_TITLE_LENGTH and len(event.source) == MAX_SOURCE_LENGTH
    assert {i.code for i in result.issues} == {
        ImportIssue.TITLE_TRUNCATED,
        ImportIssue.SOURCE_TRUNCATED,
    }


def test_fichier_trop_gros_refuse_sans_tout_lire(tmp_path):
    big = tmp_path / "big.csv"
    with open(big, "wb") as f:
        f.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(CsvFormatError) as error:
        read_events(big)
    assert error.value.code == CsvFormatError.FILE_TOO_LARGE


@posix_only
def test_fichier_special_infini_ne_sature_pas_la_memoire():
    with pytest.raises(CsvFormatError):
        read_events("/dev/zero")


# --- droits des fichiers écrits ------------------------------------------------------------


@posix_only
def test_ecraser_un_fichier_garde_ses_droits_et_un_nouveau_suit_l_umask(tmp_path):
    events = parse_events(HEADER + b"1900,1900,A,red\n").events
    existing = tmp_path / "partage.csv"
    existing.write_text("x")
    existing.chmod(0o640)
    write_events(existing, events)
    assert stat.S_IMODE(existing.stat().st_mode) == 0o640

    old = os.umask(0o077)
    try:
        fresh = tmp_path / "neuf.csv"
        write_events(fresh, events)
    finally:
        os.umask(old)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


# --- texte venant d'un fichier -------------------------------------------------------------


def test_html_dans_un_titre_est_neutralise():
    hostile = '<img src="file:///etc/hostname"><a href="http://x">lien</a>'
    safe = plain(hostile)
    assert "<img" not in safe and "<a href" not in safe
    assert "&lt;img" in safe


def test_infobulle_et_confirmation_utilisent_du_texte_neutralise(app):
    from chronologia.timeline_view import TimelineView, event_tooltip

    view = TimelineView()
    events = parse_events(HEADER + b'1900,1900,"<b>gras</b>",red\n').events
    view.set_data(events, cat.default_registry())
    tips = [g.toolTip() for g in view._groups]
    assert tips and all("<b>" not in t for t in tips)
    assert "<b>gras</b>" in event_tooltip(events[0])  # le texte d'origine reste intact


# --- configuration des catégories ----------------------------------------------------------


def test_configuration_demesuree_ignoree(tmp_path):
    path = tmp_path / "categories.json"
    path.write_text(" " * (cat.MAX_CONFIG_BYTES + 1), encoding="utf-8")
    registry, warning = cat.load_registry(path)
    assert len(registry) == 10 and warning


def test_nombre_de_categories_borne():
    registry = cat.CategoryRegistry()
    for i in range(cat.MAX_CATEGORIES):
        registry.add(f"C{i}", f"#{i:06x}")
    with pytest.raises(cat.CategoryError):
        registry.add("de trop", "#ffffff")


# --- confidentialité -----------------------------------------------------------------------


def test_aucun_module_reseau_ou_execution_dynamique_dans_le_code():
    forbidden = re.compile(
        r"^\s*(?:import|from)\s+(socket|urllib|http|ftplib|smtplib|requests|subprocess|"
        r"webbrowser|ctypes|pickle|marshal|PySide6\.QtNetwork|PySide6\.QtWebEngine\w*)\b",
        re.MULTILINE,
    )
    offenders = [
        f"{p.name}: {m.group(1)}"
        for p in SRC.glob("*.py")
        for m in forbidden.finditer(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_qt_reseau_jamais_charge_pendant_une_session_complete(app, tmp_path):
    from chronologia.pdf_export import write_pdf
    from chronologia.poster import plan_poster

    csv = tmp_path / "t.csv"
    csv.write_bytes(HEADER + b"1900,1950,A,red\n1930,1930,B,black\n")
    window = MainWindow()
    window.load_file(csv)
    plan = plan_poster(window.document.events, cat.default_registry(), None, 420, 297)
    write_pdf(tmp_path / "out.pdf", plan)
    window.close()
    assert "PySide6.QtNetwork" not in sys.modules


def test_une_session_n_ecrit_que_les_fichiers_demandes(app, tmp_path):
    """Ouvrir, modifier, exporter : seuls le CSV et le PDF choisis par l'utilisateur apparaissent."""
    from chronologia.event_form import build_event
    from chronologia.pdf_export import write_pdf
    from chronologia.poster import plan_poster

    csv = tmp_path / "frise.csv"
    csv.write_bytes(HEADER + b"1900,1950,A,red\n")
    before = {p for p in tmp_path.rglob("*")}
    window = MainWindow()
    window.load_file(csv)
    event, _ = build_event("Nouveau", "1960", "", "red", "")
    window.add_event(event)
    window.save()
    write_pdf(
        tmp_path / "frise.pdf",
        plan_poster(window.document.events, cat.default_registry(), None, 420, 297),
    )
    window.close()
    created = {p.name for p in set(tmp_path.rglob("*")) - before}
    assert created == {"frise.pdf"}  # frise.csv existait déjà (écrasé), rien d'autre


def test_le_pdf_ne_contient_aucune_donnee_personnelle_de_la_machine(app, tmp_path):
    from chronologia.pdf_export import write_pdf
    from chronologia.poster import plan_poster

    events = parse_events(HEADER + b"1900,1950,A,red\n").events
    out = tmp_path / "f.pdf"
    write_pdf(out, plan_poster(events, cat.default_registry(), None, 420, 297, title="Titre"))
    data = out.read_bytes()
    for secret in (getpass.getuser(), socket.gethostname(), str(Path.home()), str(tmp_path)):
        if len(secret) > 2:
            assert secret.encode() not in data and secret.encode("utf-16-be") not in data
