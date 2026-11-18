import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from chronologia.categories import default_registry
from chronologia.csv_io import parse_events, read_events
from chronologia.export_dialog import ExportDialog
from chronologia.main_window import MainWindow
from chronologia.pdf_export import write_pdf
from chronologia.poster import PosterPlanner, plan_poster, render_preview

EXEMPLE = Path(__file__).parent.parent / "input_claude" / "exemple_timeline.csv"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def events(app):
    if not EXEMPLE.exists():
        pytest.skip("CSV d'exemple absent")
    return read_events(EXEMPLE).events


def media_box(path: Path) -> tuple[float, float]:
    match = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", path.read_bytes())
    assert match
    return float(match.group(1)), float(match.group(2))


@pytest.mark.parametrize(
    "w_mm, h_mm", [(1189, 841), (841, 1189), (297, 210), (3000, 1000), (1000, 3000)]
)
def test_taille_de_page_exacte(events, tmp_path, w_mm, h_mm):
    plan = plan_poster(events, default_registry(), None, w_mm, h_mm)
    out = tmp_path / "f.pdf"
    write_pdf(out, plan)
    width, height = media_box(out)
    assert width == pytest.approx(w_mm / 25.4 * 72, abs=1.5)
    assert height == pytest.approx(h_mm / 25.4 * 72, abs=1.5)


def test_pdf_vectoriel(events, tmp_path):
    out = tmp_path / "f.pdf"
    write_pdf(out, plan_poster(events, default_registry(), None, 1189, 841, title="Titre"))
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"/Font" in data  # texte = polices, pas de pixels
    assert b"/Subtype /Image" not in data and b"/Subtype/Image" not in data
    assert len(data) < 500_000


def test_le_contenu_tient_dans_la_page_et_remplit_une_dimension(events):
    plan = plan_poster(events, default_registry(), None, 1189, 841)
    assert plan.content_width * plan.scale <= plan.page_width_pt + 1e-6
    assert plan.content_height * plan.scale <= plan.page_height_pt + 1e-6
    fills = max(
        plan.content_width * plan.scale / plan.page_width_pt,
        plan.content_height * plan.scale / plan.page_height_pt,
    )
    assert fills == pytest.approx(1.0)


def test_plus_grande_page_donne_un_texte_plus_grand(events):
    small = plan_poster(events, default_registry(), None, 594, 420)
    large = plan_poster(events, default_registry(), None, 2000, 1000)
    assert large.font_pt > small.font_pt


def test_titres_complets_dans_l_export(events):
    plan = plan_poster(events, default_registry(), None, 1189, 841)
    for item in (i for lane in plan.layout.lanes for i in lane.items):
        assert " ".join(item.label_lines).replace(" …", "") == " ".join(item.event.title.split())


def test_filtre_categories_et_periode(events):
    reg = default_registry()
    only = plan_poster(events, reg, {"Luttes agricoles"}, 1189, 841)
    assert [lane.name for lane in only.layout.lanes] == ["Luttes agricoles"]
    assert only.event_count == 41
    ranged = plan_poster(events, reg, None, 1189, 841, time_range=(1960.0, 1971.0))
    assert ranged.layout.t_start == 1960.0 and ranged.layout.t_end == 1971.0
    assert 0 < ranged.event_count < len(events)
    assert plan_poster(events, reg, set(), 1189, 841) is None


def test_periode_rogne_les_barres_et_garde_le_contenu_dans_l_axe(events):
    plan = plan_poster(events, default_registry(), None, 1189, 841, time_range=(1960.0, 1971.0))
    layout = plan.layout
    limit = (layout.t_end - layout.t_start) * plan.options.px_per_year
    for item in layout.items():
        if not item.is_point:
            assert item.x0 >= -1e-9 and item.x1 <= limit + plan.options.marker_size + 1e-9


def test_planner_instantane_pour_un_autre_format(events):
    planner = PosterPlanner(events, default_registry())
    a = planner.plan(1189, 841)
    b = planner.plan(594, 420)
    assert a.layout is not None and b.scale < a.scale


def test_apercu_est_une_image_de_la_bonne_proportion(events):
    plan = plan_poster(events, default_registry(), None, 1000, 500)
    image = render_preview(plan, 800)
    assert image.width() == 800 and image.height() == 400


def test_evenement_unique_et_dates_proches(app):
    evs = parse_events(b"start,end,title,color\n1900,1900,Seul,red\n").events
    plan = plan_poster(evs, default_registry(), None, 420, 297, title="x")
    assert plan is not None and plan.event_count == 1


def test_dialogue_formats_et_dimensions(events):
    dialog = ExportDialog(events, default_registry(), None)
    assert (dialog.width_cm.value(), dialog.height_cm.value()) == (118.9, 84.1)  # A0 paysage
    dialog.landscape.setCurrentIndex(1)  # portrait
    assert (dialog.width_cm.value(), dialog.height_cm.value()) == (84.1, 118.9)
    dialog.width_cm.setValue(300.0)  # modification manuelle → personnalisé
    assert dialog.format.currentData() == "custom"
    dialog.refresh()
    assert dialog.plan().page_width_pt == pytest.approx(3000 / 25.4 * 72)


def test_dialogue_avertit_pour_grande_page_et_sans_evenement(events):
    dialog = ExportDialog(events, default_registry(), None)
    dialog.width_cm.setValue(700.0)
    dialog.refresh()
    assert "5 m" in dialog._warning.text()
    empty = ExportDialog(events, default_registry(), set())
    assert empty.plan() is None


def test_export_depuis_la_fenetre(app, tmp_path, monkeypatch):
    w = MainWindow()
    csv = tmp_path / "t.csv"
    csv.write_bytes(b"start,end,title,color\n1900,1950,A,red\n1930,1930,B,black\n")
    w.load_file(csv)
    out = tmp_path / "sortie"  # sans extension : .pdf est ajouté
    monkeypatch.setattr(ExportDialog, "exec", lambda self: 1)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    w.export_pdf()
    assert (tmp_path / "sortie.pdf").read_bytes().startswith(b"%PDF")
    w.close()


def test_echec_d_ecriture_ne_plante_pas(app, tmp_path, monkeypatch):
    w = MainWindow()
    csv = tmp_path / "t.csv"
    csv.write_bytes(b"start,end,title,color\n1900,1950,A,red\n")
    w.load_file(csv)
    errors = []
    monkeypatch.setattr(ExportDialog, "exec", lambda self: 1)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "absent" / "x.pdf"), "")
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a))
    w.export_pdf()
    assert errors and not (tmp_path / "absent").exists()
    w.close()
