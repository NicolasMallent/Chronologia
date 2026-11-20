import itertools
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from chronologia.categories import default_registry
from chronologia.csv_io import parse_events, read_events
from chronologia.main_window import MainWindow
from chronologia.pdf_export import PDF_COMFORT_LIMIT_MM, export_divisor, write_pdf
from chronologia.poster import PosterPlanner, paint_poster, plan_poster, render_preview

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


def test_plus_grande_page_affiche_plus_de_titres_a_texte_constant(events):
    planner = PosterPlanner(events, default_registry(), extra_sublanes=0)
    small = planner.plan(594, 420, font_pt=8)
    large = planner.plan(2000, 1000, font_pt=8)
    assert large.titles_full > small.titles_full
    assert small.font_pt == pytest.approx(8, abs=0.01) and large.font_pt == pytest.approx(
        8, abs=0.01
    )


def test_la_taille_du_texte_demandee_est_respectee_quand_la_page_le_permet(events):
    for w, h in ((1189, 841), (5000, 1000), (10000, 1000)):
        for size in (6, 8, 12):
            plan = plan_poster(events, default_registry(), None, w, h, font_pt=size)
            assert plan.font_pt == pytest.approx(size, abs=0.02 * size), (w, h, size)
            assert plan.requested_font_pt == size
            used = plan.content_width * plan.scale / plan.page_width_pt
            assert used == pytest.approx(1.0, abs=0.01) or used < 1.0  # largeur occupée


def test_texte_plus_petit_donne_une_frise_plus_large_et_plus_de_titres(events):
    planner = PosterPlanner(events, default_registry(), extra_sublanes=0)
    gros = planner.plan(5000, 800, font_pt=14)
    petit = planner.plan(5000, 800, font_pt=5)
    assert petit.titles_full >= gros.titles_full
    assert petit.font_pt < gros.font_pt
    assert petit.options.px_per_year > gros.options.px_per_year  # frise plus large


def test_texte_reduit_si_la_page_est_trop_basse_pour_la_frise(events):
    plan = plan_poster(events, default_registry(), None, 105, 148, font_pt=8)  # A6 : trop haute
    assert plan is not None and plan.event_count == len(events)
    assert plan.font_pt < 8 - 0.05  # réduit pour tenir en hauteur
    assert plan.content_height * plan.scale <= plan.page_height_pt + 1e-6


def test_aucun_titre_perdu_si_la_page_est_trop_petite_pour_le_texte_demande(events):
    plan = plan_poster(events, default_registry(), None, 210, 297, font_pt=48)
    assert plan is not None
    assert plan.event_count == len(events)


def test_titres_serres_descendent_sur_une_ligne_libre_quand_la_page_est_haute(events):
    planner = PosterPlanner(events, default_registry())
    sans = PosterPlanner(events, default_registry(), extra_sublanes=0)
    avec_plan, sans_plan = planner.plan(1189, 841, font_pt=8), sans.plan(1189, 841, font_pt=8)
    assert avec_plan.titles_hidden + avec_plan.titles_truncated < (
        sans_plan.titles_hidden + sans_plan.titles_truncated
    )
    assert avec_plan.font_pt == pytest.approx(8, abs=0.1)  # sans réduire le texte
    total = len(events)
    assert avec_plan.titles_full + avec_plan.titles_truncated + avec_plan.titles_hidden == total
    assert avec_plan.titles_full >= total - 5  # presque tous les titres sont visibles


def test_sur_une_petite_page_le_texte_garde_sa_taille_au_prix_de_titres_masques(events):
    plan = plan_poster(events, default_registry(), None, 420, 297, font_pt=8)  # A3 paysage
    assert plan.font_pt == pytest.approx(8, abs=0.1)  # le texte n'est pas sacrifié
    assert plan.titles_hidden > 0  # faute de hauteur pour tout séparer


def test_planificateur_reutilise_les_mises_en_page(events):
    planner = PosterPlanner(events, default_registry())
    planner.plan(1189, 841, font_pt=8)
    count = len(planner._cache)
    planner.plan(1189, 841, "avec un titre", font_pt=8)  # seul le titre change
    assert len(planner._cache) <= count + 3  # presque rien de nouveau à calculer


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
    assert a.layout is not None and b.titles_full <= a.titles_full


def test_apercu_est_une_image_de_la_bonne_proportion(events):
    plan = plan_poster(events, default_registry(), None, 1000, 500)
    image = render_preview(plan, 800)
    assert image.width() == 800 and image.height() == 400


def test_evenement_unique_et_dates_proches(app):
    evs = parse_events(b"start,end,title,color\n1900,1900,Seul,red\n").events
    plan = plan_poster(evs, default_registry(), None, 420, 297, title="x")
    assert plan is not None and plan.event_count == 1


def test_export_depuis_la_fenetre(app, tmp_path, monkeypatch):
    w = MainWindow()
    csv = tmp_path / "t.csv"
    csv.write_bytes(b"start,end,title,color\n1900,1950,A,red\n1930,1930,B,black\n")
    w.load_file(csv)
    out = tmp_path / "sortie"  # sans extension : .pdf est ajouté
    w.set_mode(True)  # l'export part de la feuille réglée
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
    w.set_mode(True)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "absent" / "x.pdf"), "")
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a))
    w.export_pdf()
    assert errors and not (tmp_path / "absent").exists()
    w.close()


def test_titres_sur_plusieurs_lignes_en_affichent_plus(events):
    reg = default_registry()
    une = PosterPlanner(events, reg, max_label_lines=1, extra_sublanes=0).plan(5000, 800, font_pt=8)
    trois = PosterPlanner(events, reg, max_label_lines=3, extra_sublanes=0).plan(
        5000, 800, font_pt=8
    )
    assert trois.titles_full > une.titles_full
    assert max(len(i.label_lines) for i in trois.layout.items()) > 1


# --- géométrie de la feuille (vue Feuille) ----------------------------------------------------


def test_correspondance_page_et_conception_dans_les_deux_sens(events):
    plan = plan_poster(events, default_registry(), None, 1189, 841, title="T")
    for dx, dy in ((0, 0), (123.4, 56.7), (plan.content_width, plan.content_height)):
        p = plan.to_page(dx, dy)
        back = plan.to_design(p.x(), p.y())
        assert back.x() == pytest.approx(dx) and back.y() == pytest.approx(dy)
    page = plan.design_rect(QRectF(0, 0, plan.page_width_pt, plan.page_height_pt))
    assert page.width() >= plan.content_width - 1e-6  # la page contient le dessin


def test_evenement_sous_le_point_et_emprise(events):
    plan = plan_poster(events, default_registry(), None, 5000, 700)
    found = 0
    for item in plan.layout.items():
        rect = plan.item_rect(item)
        assert rect.width() > 0 and rect.height() > 0
        # le centre de la forme désigne l'événement (le plus petit rectangle gagne)
        shape_centre = plan.to_page(
            plan.x_offset + (item.x0 + item.x1) / 2, plan.y_lanes + item.y + item.height / 2
        )
        hit = plan.event_at(shape_centre.x(), shape_centre.y())
        assert hit is not None
        found += hit is item.event
    assert found / plan.event_count > 0.9  # quelques recouvrements possibles entre éléments
    assert plan.event_at(-50, -50) is None  # hors du dessin
    assert plan.item_of(plan.layout.lanes[0].items[0].event) is plan.layout.lanes[0].items[0]


def test_tolerance_de_survol(events):
    plan = plan_poster(events, default_registry(), None, 5000, 700)
    item = plan.layout.lanes[0].items[0]
    r = plan.item_rect(item)
    just_outside = (r.right() + 1.0, r.center().y())
    assert plan.event_at(*just_outside, tolerance=3.0) is not None


def test_annee_et_couleur_de_ligne_a_la_position(events):
    plan = plan_poster(events, default_registry(), None, 5000, 700)
    layout = plan.layout
    lane = layout.lanes[1]
    y = plan.to_page(0, plan.y_lanes + lane.y + lane.height / 2).y()
    assert plan.lane_color_at(y) == lane.color_hex
    assert plan.lane_color_at(0) == ""  # marge supérieure
    x0 = plan.to_page(plan.x_offset, 0).x()
    assert plan.year_at(x0) == pytest.approx(layout.t_start)
    x1 = plan.to_page(
        plan.x_offset + (layout.t_end - layout.t_start) * plan.options.px_per_year, 0
    ).x()
    assert plan.year_at(x1) == pytest.approx(layout.t_end)


def test_dessin_partiel_identique_au_dessin_complet_dans_la_zone(events):
    """Le découpage (clip) n'altère pas ce qui est visible dans la zone."""
    from PySide6.QtGui import QImage, QPainter

    plan = plan_poster(events, default_registry(), None, 2000, 400)
    zone_pt = QRectF(plan.page_width_pt * 0.55, 0, plan.page_width_pt * 0.1, plan.page_height_pt)

    def render(clip):
        width = 600
        k = width / zone_pt.width()
        image = QImage(width, round(zone_pt.height() * k), QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.scale(k, k)
        painter.translate(-zone_pt.left(), -zone_pt.top())
        plan.apply_transform(painter)
        paint_poster(painter, plan, clip=plan.design_rect(zone_pt) if clip else None)
        painter.end()
        return image

    assert render(clip=True) == render(clip=False)


def test_evenements_estompes_et_selection_ne_plantent_pas(events):
    from PySide6.QtGui import QImage, QPainter

    plan = plan_poster(events, default_registry(), None, 1000, 300)
    first = plan.layout.lanes[0].items[0].event
    image = QImage(500, 150, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    plan.apply_transform(painter, 0.5)
    paint_poster(painter, plan, dimmed=lambda e: e is not first, selected=first)
    painter.end()


def test_banderole_de_10_m_exportee_a_5_m(app, tmp_path):
    evs = parse_events(b"start,end,title,color\n1900,1950,A,red\n1930,1930,B,black\n").events
    plan = plan_poster(evs, default_registry(), None, 10000, 1000)
    out = tmp_path / "banderole.pdf"
    divisor = export_divisor(10000, 1000)
    assert divisor == 2
    write_pdf(out, plan, divisor=divisor)
    width, height = media_box(out)
    assert width == pytest.approx(5000 / 25.4 * 72, rel=1e-3)
    assert height == pytest.approx(500 / 25.4 * 72, rel=1e-3)
    assert width * 25.4 / 72 <= PDF_COMFORT_LIMIT_MM + 1
    with pytest.raises(ValueError):
        write_pdf(tmp_path / "x.pdf", plan, divisor=0)


def test_a6_et_a5(app, tmp_path):
    evs = parse_events(b"start,end,title,color\n1900,1950,A,red\n").events
    for name, size in (("A6", (105, 148)), ("A5", (148, 210))):
        plan = plan_poster(evs, default_registry(), None, *size)
        out = tmp_path / f"{name}.pdf"
        write_pdf(out, plan)
        w, h = media_box(out)
        assert w == pytest.approx(size[0] / 25.4 * 72, rel=1e-2)
        assert h == pytest.approx(size[1] / 25.4 * 72, rel=1e-2)


# --- remplissage de la feuille ---------------------------------------------------------------


def test_la_frise_remplit_la_feuille_en_partant_du_haut(events):
    for w, h in ((1189, 841), (297, 420), (2000, 600), (10000, 1000)):
        plan = plan_poster(events, default_registry(), None, w, h, title="T")
        used_w = plan.content_width * plan.scale / plan.page_width_pt
        used_h = plan.content_height * plan.scale / plan.page_height_pt
        assert used_w == pytest.approx(1.0, abs=0.01) or used_h == pytest.approx(1.0, abs=0.01)
        assert used_h >= 0.99  # remplie verticalement (écarts étirés)
        assert plan.origin_pt.y() == 0.0  # collée en haut de la feuille
        assert plan.origin_pt.x() >= -1e-6


def test_l_etirement_garde_la_taille_des_barres_et_du_texte(events):
    planner = PosterPlanner(events, default_registry())
    wide = planner.plan(5000, 1500)  # beaucoup de place verticale : écarts très étirés
    tight = planner.plan(5000, 1000)  # moins de place : écarts moins étirés
    assert wide.options.lane_spacing > tight.options.lane_spacing > 14.0
    assert wide.options.line_height == tight.options.line_height  # même police
    assert wide.options.row_height == tight.options.row_height  # mêmes barres
    assert wide.options.px_per_year == tight.options.px_per_year  # mêmes largeurs


def test_l_etirement_est_borne(events):
    from chronologia.poster import MAX_SPACING_FACTOR

    plan = plan_poster(events, default_registry(), None, 600, 4000)  # page très haute
    assert plan.options.lane_spacing <= 14.0 * MAX_SPACING_FACTOR + 1e-6
    used_h = plan.content_height * plan.scale / plan.page_height_pt
    assert used_h <= 1.0 + 1e-6  # le bas reste vide plutôt que d'étirer sans limite


def test_bandes_de_categories_se_touchent_et_restent_entre_les_axes(events):
    plan = plan_poster(events, default_registry(), None, 1189, 841)
    pad = plan.lane_pad
    lanes = plan.layout.lanes
    for a, b in itertools.pairwise(lanes):
        assert a.y + a.height + pad == pytest.approx(b.y - pad)  # bandes jointives
    assert plan.y_lanes - pad == pytest.approx(30 + 24 + plan.title_height)  # sous l'axe du haut
    assert plan.y_axis_bottom == pytest.approx(plan.y_lanes + plan.layout.height + pad)
    lane = lanes[2]  # le test de survol suit la bande élargie
    y = plan.to_page(0, plan.y_lanes + lane.y - pad + 0.5).y()
    assert plan.lane_color_at(y) == lane.color_hex


def test_banderole_contenue_dans_la_page_apres_etirement(events, tmp_path):
    plan = plan_poster(events, default_registry(), None, 10000, 1000)
    write_pdf(tmp_path / "b.pdf", plan, divisor=2)
    assert plan.content_height * plan.scale <= plan.page_height_pt + 1e-6
    assert plan.content_width * plan.scale <= plan.page_width_pt + 1e-6
