import itertools
from datetime import date
from pathlib import Path

import pytest

from chronologia.categories import default_registry
from chronologia.csv_io import parse_events, read_events
from chronologia.dates import PartialDate, Precision
from chronologia.layout import (
    LayoutOptions,
    _span,
    compute_layout,
    elide,
    end_position,
    make_ticks,
    to_years,
    wrap_text,
)

EXEMPLE = Path(__file__).parent.parent / "input_claude" / "exemple_timeline.csv"


def measure(text: str) -> float:
    return 6.0 * len(text)  # police à chasse fixe


def events(csv_body: str):
    return parse_events(("start,end,title,color\n" + csv_body).encode()).events


# --- temps -----------------------------------------------------------------------------


def test_to_years():
    assert to_years(date(1900, 1, 1)) == 1900.0
    assert 1900.49 < to_years(date(1900, 7, 1)) < 1900.51


def test_fin_d_annee_ou_de_mois_couvre_la_periode_entiere():
    assert end_position(PartialDate(date(1950, 1, 1), Precision.YEAR)) == 1951.0
    assert end_position(PartialDate(date(1950, 12, 1), Precision.MONTH)) == 1951.0
    assert end_position(PartialDate(date(1950, 3, 4), Precision.DAY)) == to_years(date(1950, 3, 4))


def test_graduations_rondes_et_espacees():
    opts = LayoutOptions(px_per_year=10, min_tick_px=70)
    ticks = make_ticks(1861, 1990, opts)
    assert [t.label for t in ticks][:3] == ["1870", "1880", "1890"]  # pas de 10 ans
    assert all(b.x - a.x >= 70 for a, b in itertools.pairwise(ticks))


# --- texte -----------------------------------------------------------------------------


def test_wrap_text():
    assert wrap_text("un deux trois", 30, measure) == ["un", "deux", "trois"]
    assert wrap_text("un deux", 60, measure) == ["un deux"]
    assert wrap_text("", 60, measure) == [""]


def test_wrap_coupe_un_mot_trop_long():
    lines = wrap_text("abcdefghij", 24, measure)  # 4 caractères par ligne
    assert lines == ["abcd", "efgh", "ij"]
    assert wrap_text("abc", 0, measure) == ["a", "b", "c"]  # largeur nulle : pas de boucle infinie


def test_elide():
    assert elide("court", 100, measure) == "court"
    out = elide("un titre bien trop long", 60, measure)
    assert out.endswith("…") and measure(out) <= 60
    assert elide("abc", 1, measure) == "…"


# --- placement -------------------------------------------------------------------------


def test_une_ligne_par_categorie_dans_l_ordre_du_registre():
    evs = events("1900,1900,A,skyblue\n1910,1910,B,black\n1920,1920,C,purple\n")
    layout = compute_layout(evs, default_registry(), measure)
    assert [lane.name for lane in layout.lanes] == [
        "Contexte politique international",
        "Législation française",
        "#800080",  # catégorie implicite
    ]


def test_filtre_par_categorie():
    evs = events("1900,1900,A,skyblue\n1910,1910,B,black\n")
    layout = compute_layout(
        evs, default_registry(), measure, visible_categories={"Législation française"}
    )
    assert [lane.name for lane in layout.lanes] == ["Législation française"]
    assert len(list(layout.items())) == 1
    assert compute_layout(evs, default_registry(), measure, visible_categories=set()).lanes == ()


def test_filtre_par_periode():
    evs = events("1800,1800,Avant,red\n1900,1950,Dedans,red\n2000,2000,Apres,red\n")
    layout = compute_layout(evs, default_registry(), measure, time_range=(1920, 1930))
    assert [i.event.title for i in layout.items()] == ["Dedans"]
    assert layout.t_start == 1920


def test_sans_evenement():
    layout = compute_layout([], default_registry(), measure)
    assert layout.lanes == () and layout.height == 0


def sublanes(evs, **kw):
    lane = compute_layout(evs, default_registry(), measure, LayoutOptions(**kw)).lanes[0]
    return {i.event.title: i.sublane for i in lane.items}


def test_evenements_simultanes_vont_sur_des_lignes_differentes():
    evs = events("1900,1900,A,red\n1900,1900,B,red\n")  # même date
    assert sorted(sublanes(evs).values()) == [0, 1]


def test_periodes_qui_se_recouvrent_vont_sur_des_lignes_differentes():
    evs = events("1900,1920,A,red\n1910,1930,B,red\n1925,1940,C,red\n")
    sub = sublanes(evs)
    assert sub["A"] != sub["B"]
    assert sub["C"] == sub["A"]  # A est terminée quand C commence


def test_evenement_dans_une_periode_passe_sur_une_autre_ligne():
    evs = events("1900,1950,Periode,red\n1920,1920,Dans,red\n1960,1960,Apres,red\n")
    sub = sublanes(evs)
    assert sub["Dans"] != sub["Periode"]
    assert sub["Apres"] == sub["Periode"]


def test_evenements_qui_se_suivent_restent_sur_la_meme_ligne_meme_colles():
    evs = events("1900,1900,A,red\n1901,1901,B,red\n1902,1902,C,red\n")
    # à 0,5 px par an, les losanges se recouvrent visuellement, mais ils se suivent dans le temps
    assert set(sublanes(evs, px_per_year=0.5).values()) == {0}


def test_fin_d_une_periode_et_debut_de_la_suivante_partagent_la_ligne():
    evs = events("1900,1909,A,red\n1910,1920,B,red\n")  # A couvre jusqu'à 1910 exclu
    assert set(sublanes(evs).values()) == {0}


def test_sous_lignes_independantes_du_zoom_et_des_titres():
    evs = read_events(EXEMPLE).events if EXEMPLE.exists() else events("1900,1950,A,red\n")
    reference = None
    for ppy in (0.5, 5.0, 50.0, 500.0):
        layout = compute_layout(evs, default_registry(), measure, LayoutOptions(px_per_year=ppy))
        found = [[i.sublane for i in lane.items] for lane in layout.lanes]
        reference = reference or found
        assert found == reference


def test_titres_caches_puis_tronques_puis_complets_en_zoomant():
    evs = events("1900,1900,Un titre assez long,red\n1901,1901,Suivant,red\n")
    etats = []
    for ppy in (0.1, 60.0, 400.0):
        layout = compute_layout(evs, default_registry(), measure, LayoutOptions(px_per_year=ppy))
        first = layout.lanes[0].items[0]
        etats.append((first.label_state, layout.titles_hidden))
    assert etats[0] == ("hidden", 1)
    assert etats[1][0] == "truncated"
    assert etats[2][0] == "full"
    assert layout.titles_full == 2


def test_titre_de_periode_dans_la_barre_ou_a_droite():
    evs = events(
        "1900,1950,Long,red\n1900,1900,Ponctuel,red\n1960,1961,Titre qui ne tient pas,red\n"
    )
    items = {i.event.title: i for i in compute_layout(evs, default_registry(), measure).items()}
    assert items["Long"].label_inside and items["Long"].label_state == "full"  # 500 px de large
    assert not items["Ponctuel"].label_inside
    assert items["Ponctuel"].label_x > items["Ponctuel"].x1
    assert not items["Titre qui ne tient pas"].label_inside  # barre de 10 px, rien après


def test_titre_tronque_dans_une_barre_etroite():
    evs = events("1900,1909,Un titre bien trop long pour la barre,red\n1910,1911,Suivant,red\n")
    item = compute_layout(evs, default_registry(), measure).lanes[0].items[0]
    # barre de 100 px, suivant à 100 px : place à droite quasi nulle → titre dans la barre
    assert item.label_inside and item.label_state == "truncated"
    assert item.label_lines[0].endswith("…") and measure(item.label_lines[0]) <= 94


def test_un_titre_n_empiete_jamais_sur_l_element_suivant():
    evs = events("1900,1900,Un titre vraiment très long,red\n1902,1902,Suivant,red\n")
    layout = compute_layout(evs, default_registry(), measure)
    first, second = layout.lanes[0].items
    assert first.sublane == second.sublane
    assert first.right <= second.left - LayoutOptions().gap + 1e-9


def test_periode_plus_courte_que_le_marqueur_reste_visible():
    evs = events("19000101,19000102,Court,red\n")
    item = compute_layout(evs, default_registry(), measure).lanes[0].items[0]
    assert item.x1 - item.x0 >= LayoutOptions().marker_size


def test_hauteurs_coherentes():
    evs = events("1900,1900,A,red\n1900,1900,B,red\n1900,1900,C,black\n")
    layout = compute_layout(evs, default_registry(), measure)
    lanes = layout.lanes
    assert lanes[0].y == 0 and lanes[1].y >= lanes[0].y + lanes[0].height
    assert layout.height == pytest.approx(lanes[-1].y + lanes[-1].height)


# --- invariants sur le vrai fichier ----------------------------------------------------


@pytest.mark.skipif(not EXEMPLE.exists(), reason="CSV d'exemple absent")
@pytest.mark.parametrize("ppy", [2.0, 10.0, 40.0, 200.0])
def test_exemple_reel_invariants(ppy):
    evs = read_events(EXEMPLE).events
    opts = LayoutOptions(px_per_year=ppy)
    layout = compute_layout(evs, default_registry(), measure, opts)
    assert len(list(layout.items())) == len(evs)  # rien n'est perdu
    assert layout.titles_full + layout.titles_truncated + layout.titles_hidden == len(evs)
    for lane in layout.lanes:
        by_sub: dict[int, list] = {}
        for item in lane.items:
            by_sub.setdefault(item.sublane, []).append(item)
        for items in by_sub.values():
            items.sort(key=lambda i: i.x0)
            for a, b in itertools.pairwise(items):
                # successifs dans le temps : jamais simultanés
                assert _span(a.event)[1] <= _span(b.event)[0] + 1e-9
                # le titre affiché de a s'arrête avant l'élément suivant
                if a.label_lines and not a.label_inside:
                    assert a.right <= b.left - opts.gap + 1e-9
        for item in lane.items:  # tout reste dans la ligne
            assert item.y >= lane.y - 1e-9
            assert item.y + item.height <= lane.y + lane.height + 1e-9
            assert item.label_state in ("full", "truncated", "hidden")
            assert bool(item.label_lines) == (item.label_state != "hidden")
        for a, b in itertools.combinations(lane.items, 2):  # sous-lignes distinctes : disjointes
            if a.sublane != b.sublane:
                assert a.y + a.height <= b.y + 1e-9 or b.y + b.height <= a.y + 1e-9
    assert layout.x_min <= min(i.left for i in layout.items())
    assert layout.x_max >= max(i.right for i in layout.items())


@pytest.mark.skipif(not EXEMPLE.exists(), reason="CSV d'exemple absent")
def test_exemple_reel_plus_on_zoome_plus_les_titres_se_devoilent():
    evs = read_events(EXEMPLE).events
    full = []
    for ppy in (1.0, 4.0, 16.0, 64.0, 256.0):
        layout = compute_layout(evs, default_registry(), measure, LayoutOptions(px_per_year=ppy))
        full.append(layout.titles_full)
    assert full == sorted(full) and full[-1] > full[0]


def test_hauteur_minimale_de_ligne():
    evs = events("1900,1900,A,red\n")
    opts = LayoutOptions(min_lane_height=50)
    lane = compute_layout(evs, default_registry(), measure, opts).lanes[0]
    assert lane.height == 50
    item = lane.items[0]
    assert item.y >= lane.y and item.y + item.height <= lane.y + lane.height


# --- titres sur plusieurs lignes (export) ----------------------------------------------


def lanes_for(csv_body, **kw):
    evs = events(csv_body)
    return compute_layout(evs, default_registry(), measure, LayoutOptions(**kw)).lanes[0]


def test_titre_long_passe_sur_plusieurs_lignes_si_permis():
    body = "1900,1900,Un titre assez long pour deux lignes,red\n1902,1902,Suivant,red\n"
    une = lanes_for(body, px_per_year=60, max_label_lines=1).items[0]
    trois = lanes_for(body, px_per_year=60, max_label_lines=3).items[0]
    assert une.label_state == "truncated" and len(une.label_lines) == 1
    assert trois.label_state == "full" and len(trois.label_lines) > 1
    assert " ".join(trois.label_lines) == "Un titre assez long pour deux lignes"
    limit = 120 - LayoutOptions().gap  # place avant l'élément suivant (losange compris)
    assert all(trois.label_x + measure(line) <= limit - 6 + 1e-9 for line in trois.label_lines)


def test_sous_ligne_plus_haute_pour_un_titre_multiligne_sans_chevauchement():
    body = (
        "1900,1900,Un titre assez long pour trois lignes ici,red\n"
        "1900,1900,Simultane,red\n1902,1902,Suivant,red\n"
    )
    lane = lanes_for(body, px_per_year=40, max_label_lines=3)
    tall = max(lane.items, key=lambda i: len(i.label_lines))
    assert len(tall.label_lines) >= 2
    row = LayoutOptions().row_height
    block = len(tall.label_lines) * LayoutOptions().line_height
    assert block > row
    by_sub = {}
    for item in lane.items:
        by_sub.setdefault(item.sublane, []).append(item)
    spans = []
    for items in by_sub.values():
        centers = [i.y + i.height / 2 for i in items]
        assert max(centers) - min(centers) < 1e-6  # formes centrées dans la sous-ligne
        height = max(max(i.height, len(i.label_lines) * 14.0) for i in items)
        spans.append((min(centers) - height / 2, min(centers) + height / 2))
    spans.sort()
    assert all(b[0] >= a[1] - 1e-6 for a, b in itertools.pairwise(spans))
    assert lane.height >= spans[-1][1] - lane.y - 1e-6


def test_barre_plus_haute_pour_un_titre_multiligne_dans_la_barre():
    lane = lanes_for(
        "1900,1909,Un titre de période bien trop long,red\n1910,1910,Suivant,red\n",
        max_label_lines=3,
    )
    item = next(i for i in lane.items if not i.is_point)  # barre de 100 px, suivant collé
    assert item.label_inside and item.label_state == "full" and len(item.label_lines) > 1
    assert item.height >= len(item.label_lines) * LayoutOptions().line_height


def test_une_seule_ligne_reste_le_defaut():
    assert LayoutOptions().max_label_lines == 1
    with pytest.raises(ValueError):
        LayoutOptions(max_label_lines=0)
