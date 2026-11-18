import itertools
from datetime import date
from pathlib import Path

import pytest

from chronologia.categories import default_registry
from chronologia.csv_io import parse_events, read_events
from chronologia.dates import PartialDate, Precision
from chronologia.layout import (
    LayoutOptions,
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


def test_evenements_proches_vont_sur_des_sous_lignes_differentes():
    evs = events("1900,1900,Un titre assez long,red\n1900,1900,Autre titre,red\n")
    lane = compute_layout(evs, default_registry(), measure).lanes[0]
    assert {i.sublane for i in lane.items} == {0, 1}


def test_evenements_eloignes_partagent_la_sous_ligne():
    evs = events("1700,1700,A,red\n1900,1900,B,red\n")
    lane = compute_layout(evs, default_registry(), measure).lanes[0]
    assert {i.sublane for i in lane.items} == {0}


def test_titre_de_periode_dans_la_barre_ou_a_droite():
    evs = events(
        "1900,1950,Long,red\n1900,1900,Ponctuel,red\n1900,1901,Titre qui ne tient pas,red\n"
    )
    items = {i.event.title: i for i in compute_layout(evs, default_registry(), measure).items()}
    assert items["Long"].label_inside  # 500 px de large
    assert not items["Ponctuel"].label_inside
    assert items["Ponctuel"].label_x > items["Ponctuel"].x1
    assert not items["Titre qui ne tient pas"].label_inside  # barre de 20 px


def test_export_garde_le_titre_complet_et_ecran_le_tronque():
    titre = "Un titre extrêmement long qui doit rester lisible une fois imprimé " * 3
    evs = events(f"1900,1900,{titre.strip()},red\n")
    export = compute_layout(evs, default_registry(), measure, LayoutOptions(wrap=True))
    ecran = compute_layout(evs, default_registry(), measure, LayoutOptions(wrap=False))
    lignes = export.lanes[0].items[0].label_lines
    assert " ".join(lignes) == titre.strip()
    assert len(lignes) > 1 and all(measure(x) <= 220 for x in lignes)
    assert len(ecran.lanes[0].items[0].label_lines) == 1
    assert ecran.lanes[0].items[0].label_lines[0].endswith("…")


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
@pytest.mark.parametrize("wrap", [True, False])
@pytest.mark.parametrize("ppy", [2.0, 10.0, 40.0])
def test_exemple_reel_aucun_chevauchement(wrap, ppy):
    evs = read_events(EXEMPLE).events
    opts = LayoutOptions(px_per_year=ppy, wrap=wrap)
    layout = compute_layout(evs, default_registry(), measure, opts)
    assert len(list(layout.items())) == len(evs)  # rien n'est perdu
    for lane in layout.lanes:
        by_sub: dict[int, list] = {}
        for item in lane.items:
            by_sub.setdefault(item.sublane, []).append(item)
        for items in by_sub.values():
            items.sort(key=lambda i: i.left)
            for a, b in itertools.pairwise(items):
                assert b.left >= a.right + opts.gap - 1e-9
        for item in lane.items:  # tout reste dans la ligne
            assert item.y >= lane.y - 1e-9
            assert item.y + item.height <= lane.y + lane.height + 1e-9
        for a, b in itertools.combinations(lane.items, 2):  # sous-lignes distinctes : disjointes
            if a.sublane != b.sublane:
                assert a.y + a.height <= b.y + 1e-9 or b.y + b.height <= a.y + 1e-9
    assert layout.x_min <= min(i.left for i in layout.items())


def test_hauteur_minimale_de_ligne():
    evs = events("1900,1900,A,red\n")
    opts = LayoutOptions(min_lane_height=50)
    lane = compute_layout(evs, default_registry(), measure, opts).lanes[0]
    assert lane.height == 50
    item = lane.items[0]
    assert item.y >= lane.y and item.y + item.height <= lane.y + lane.height


def test_pas_de_mot_coupe_dans_une_barre():
    evs = events(
        "1900,1904,Indépendance totale,red\n"
    )  # barre de 40 px : « Indépendance » ne tient pas
    item = compute_layout(evs, default_registry(), measure).lanes[0].items[0]
    assert not item.label_inside
    assert item.label_lines == ("Indépendance totale",)
