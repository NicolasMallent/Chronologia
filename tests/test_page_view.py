import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from chronologia.categories import default_registry
from chronologia.csv_io import parse_events
from chronologia.page_view import ZOOM_MAX, PageContainer, PageView
from chronologia.poster import plan_poster
from chronologia.rulers import format_length, nice_step_mm, scale_bar

CSV = (
    b"start,end,title,color\n"
    b"1900,1950,Periode longue,red\n1920,1920,Evenement,black\n"
    b"1960,1960,Autre evenement,red\n1930,1940,Une periode,skyblue\n"
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def events(app):
    return parse_events(CSV).events


def make_view(events, w_mm, h_mm, size=(900, 600)):
    view = PageView()
    view.resize(*size)
    view.show()
    QApplication.processEvents()
    view.set_plan(plan_poster(events, default_registry(), None, w_mm, h_mm, "Titre"))
    QApplication.processEvents()
    return view


def wheel(view, delta_y, modifiers=Qt.KeyboardModifier.NoModifier, pos=None):
    pos = pos or QPointF(300, 200)
    event = QWheelEvent(
        pos,
        view.viewport().mapToGlobal(pos),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


FORMATS = [("A6 portrait", 105, 148), ("A0 paysage", 1189, 841), ("banderole", 10000, 1000)]


@pytest.mark.parametrize("name, w, h", FORMATS)
def test_feuille_entiere_visible_et_zoom_borne(events, name, w, h):
    view = make_view(events, w, h)
    page = view.page_rect()
    assert page.width() == pytest.approx(w / 25.4 * 72)
    view.fit_page()
    visible = view.visible_scene_rect()
    assert visible.contains(page)  # toute la feuille est visible
    assert view.min_zoom() <= view.zoom <= ZOOM_MAX
    view.set_zoom(1e9)
    assert view.zoom == ZOOM_MAX
    view.set_zoom(1e-12)
    assert view.zoom == pytest.approx(view.min_zoom())


@pytest.mark.parametrize("name, w, h", FORMATS)
def test_largeur_hauteur_et_taille_reelle(events, name, w, h):
    view = make_view(events, w, h)
    page = view.page_rect()
    view.fit_width()
    visible = view.visible_scene_rect()
    assert visible.width() >= page.width() * 0.999  # toute la largeur
    assert visible.top() <= page.top()  # on voit le haut de la feuille
    view.fit_height()
    visible = view.visible_scene_rect()
    assert visible.height() >= page.height() * 0.999
    assert visible.left() <= page.left()
    view.actual_size()
    assert view.zoom == pytest.approx(view.real_size_zoom())
    # 10 cm de feuille = 10 cm à l'écran (à la densité de l'écran près)
    cm = view.mapFromScene(QPointF(10 / 2.54 * 72, 0)).x() - view.mapFromScene(QPointF(0, 0)).x()
    assert cm == pytest.approx(10 / 2.54 * view.screen_dpi(), rel=0.02)


def test_molette_zoome_autour_du_curseur(events):
    view = make_view(events, 1189, 841)
    view.set_zoom(view.real_size_zoom())
    pos = QPoint(300, 200)
    under = view.mapToScene(pos)
    before = view.zoom
    wheel(view, 120, pos=QPointF(pos))
    assert view.zoom > before
    after = view.mapToScene(pos)
    tolerance = 2.0 / view.zoom  # arrondi des barres de défilement : quelques pixels
    assert after.x() == pytest.approx(under.x(), abs=tolerance * 3)
    assert after.y() == pytest.approx(under.y(), abs=tolerance * 3)
    wheel(view, -120)
    assert view.zoom == pytest.approx(before, rel=1e-6)


def test_maj_et_alt_molette_font_defiler(events):
    view = make_view(events, 10000, 1000)
    view.set_zoom(view.real_size_zoom())
    h, v = view.horizontalScrollBar(), view.verticalScrollBar()
    h.setValue(h.maximum() // 2)
    v.setValue(v.maximum() // 2)
    zoom = view.zoom
    h0, v0 = h.value(), v.value()
    wheel(view, -120, Qt.KeyboardModifier.AltModifier)
    assert h.value() > h0 and v.value() == v0 and view.zoom == zoom
    h1 = h.value()
    wheel(view, -120, Qt.KeyboardModifier.ShiftModifier)
    assert v.value() >= v0 and h.value() == h1 and view.zoom == zoom


def test_sans_evenement(events):
    view = make_view(events, 1189, 841)
    view.set_plan(None)
    assert view.plan is None and view._event_at(QPoint(10, 10)) is None
    assert view.lane_color_at(10) == "" and view._year_hint(QPoint(10, 10)) == ""
    view.grab()  # le message « Aucun événement » se dessine sans erreur


def test_changement_de_format_recadre_la_vue(events):
    view = make_view(events, 1189, 841)
    view.set_zoom(view.real_size_zoom())
    plan_same = plan_poster(events, default_registry(), None, 1189, 841)
    view.set_plan(plan_same)
    assert view.zoom == pytest.approx(view.real_size_zoom())  # même format : la caméra reste
    view.set_plan(plan_poster(events, default_registry(), None, 210, 297))
    assert view.visible_scene_rect().contains(view.page_rect())  # nouveau format : feuille entière


def test_recherche_estompe(events):
    view = make_view(events, 1189, 841)
    assert view.match_count is None
    view.set_search("evenement")
    assert view.match_count == 2
    titles = {e.title: view.dimmed(e) for e in events}
    assert titles["Periode longue"] and not titles["Evenement"]
    view.set_search("")
    assert view.match_count is None


# --- règles, échelle, mini-carte ---------------------------------------------------------------


@pytest.mark.parametrize("px_per_mm", [0.0008, 0.05, 0.3, 1.0, 3.78, 40.0])
def test_pas_de_graduation_rond_et_espace(px_per_mm):
    step = nice_step_mm(px_per_mm, 70.0)
    assert step * px_per_mm >= 70.0 - 1e-9
    assert step * px_per_mm < 70.0 * 2.51  # pas plus de 2,5 fois trop large
    mantissa = step / 10 ** (len(str(int(step))) - 1) if step >= 1 else None
    assert mantissa is None or round(mantissa, 6) in (1.0, 2.0, 5.0)


def test_formats_de_longueur():
    assert format_length(5) == "5 mm"
    assert format_length(25) == "2,5 cm"
    assert format_length(1000) == "1 m"
    assert format_length(2500) == "2,5 m"
    assert format_length(0) == "0 mm"
    mm, px = scale_bar(1.0)
    assert px >= 80 and mm > 0


def test_regles_alignees_sur_la_feuille(events):
    container = PageContainer()
    container.resize(1000, 500)
    container.show()
    QApplication.processEvents()
    view = container.view
    view.set_plan(plan_poster(events, default_registry(), None, 1189, 841))
    QApplication.processEvents()
    ticks = container.ruler_h.ticks()
    assert ticks and ticks[0][1] >= 0 - 1e-6
    # une graduation de x mm est bien à x mm du bord de la feuille
    first, last = ticks[0], ticks[-1]
    px_per_mm = (last[0] - first[0]) / (last[1] - first[1])
    assert px_per_mm == pytest.approx(view.zoom * 72 / 25.4, rel=0.02)
    origin_x = view.mapFromScene(QPointF(0, 0)).x()
    assert first[0] == pytest.approx(origin_x + first[1] * px_per_mm, abs=1.0)
    assert container.ruler_v.ticks()
    container.set_rulers_visible(False)
    assert not container.ruler_h.isVisibleTo(container)
    container.grab()


def test_mini_carte_recentre_la_vue(events):
    view = make_view(events, 10000, 1000)
    view.set_zoom(view.real_size_zoom())
    nav = view.navigator
    assert nav.isVisibleTo(view) and nav.thumb_size()[0] > 0  # la feuille déborde : visible
    w, h = nav.thumb_size()
    target = nav.scene_point(4 + w * 0.9, 4 + h * 0.5)  # près de l'extrémité droite
    assert target.x() == pytest.approx(view.page_rect().width() * 0.9, rel=1e-6)
    view.centerOn(target)
    assert view.visible_scene_rect().center().x() == pytest.approx(target.x(), rel=0.02)
    rect = nav.viewport_rect()
    assert rect.width() < w and rect.right() <= 4 + w + 1e-6
    view.fit_page()
    assert not nav.isVisibleTo(view)  # feuille entière visible : pas de mini-carte
    view.set_zoom(view.real_size_zoom())
    view.navigator_enabled = False
    nav.refresh()
    assert not nav.isVisibleTo(view)


def test_survol_et_edition(events):
    view = make_view(events, 1189, 841)
    item = next(i for i in view.plan.layout.items() if i.event.title == "Periode longue")
    rect = view.plan.item_rect(item)
    pos = view.mapFromScene(rect.center())
    view.set_zoom(view.real_size_zoom())  # le centre a changé : recalcule la position
    view.centerOn(rect.center())
    pos = view.mapFromScene(rect.center())
    assert view._event_at(pos).title in ("Periode longue", "Evenement")  # recouvrement possible
    got = []
    view.editRequested.connect(got.append)
    view.select(view._event_at(pos))
    assert view.selected_event is not None
    view.deleteRequested.connect(got.append)
    from PySide6.QtTest import QTest

    QTest.keyClick(view, Qt.Key.Key_Delete)
    assert got and got[-1] is view.selected_event
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert view.selected_event is None
    assert view._year_hint(pos).isdigit() and len(view._year_hint(pos)) == 4
    assert view.lane_color_at(pos.y()) != ""
