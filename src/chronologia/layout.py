"""Moteur de mise en page de la frise, indépendant de Qt.

Entrée : événements, catégories, fonction de mesure du texte. Sortie : positions (x, y,
dimensions) dans une unité abstraite (pixels à l'écran, points pour le PDF), que la vue et
l'export dessinent à l'identique.

Principe :
- une ligne (« lane ») par catégorie visible, dans l'ordre du registre ;
- dans une ligne, les éléments sont rangés en sous-lignes **d'après le temps** : deux éléments
  qui ont lieu en même temps (périodes qui se recouvrent, même date, événement dans une période)
  vont sur des sous-lignes différentes ; des éléments qui se suivent partagent la même sous-ligne.
  Le nombre de sous-lignes ne dépend donc ni du zoom ni des titres ;
- le titre n'est affiché que s'il a la place : dans la barre d'une période, ou à droite de
  l'élément jusqu'à l'élément suivant de la même sous-ligne. S'il n'a qu'une place partielle il
  est tronqué avec « … », et caché si la place est vraiment trop petite (le titre complet reste
  disponible en info-bulle). Plus on zoome, plus les titres se dévoilent.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from .categories import CategoryRegistry
from .dates import PartialDate, Precision
from .model import Event

TextMeasurer = Callable[[str], float]
"""Largeur d'une chaîne, dans la même unité que la mise en page."""

ELLIPSIS = "…"
_TICK_STEPS = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)


@dataclass(frozen=True)
class LayoutOptions:
    px_per_year: float = 10.0
    line_height: float = 14.0
    marker_size: float = 12.0  # losange des événements ponctuels, hauteur minimale d'une barre
    padding: float = 3.0
    gap: float = 6.0  # espace minimal entre la fin d'un titre et l'élément suivant
    max_label_width: float = 1000.0  # largeur max d'un titre placé à côté d'un élément
    min_label_width: float = 30.0  # en dessous, le titre est caché plutôt que réduit à « … »
    max_label_lines: int = 1  # > 1 : un titre trop long passe sur plusieurs lignes (export)
    sublane_spacing: float = 4.0
    lane_spacing: float = 14.0
    min_lane_height: float = 0.0  # ex. : place pour le nom de la catégorie
    min_tick_px: float = 70.0

    def __post_init__(self) -> None:
        if self.px_per_year <= 0 or self.line_height <= 0 or self.max_label_width <= 0:
            raise ValueError("échelle, hauteur de ligne et largeur de titre doivent être > 0")
        if self.max_label_lines < 1:
            raise ValueError("un titre doit pouvoir tenir sur au moins une ligne")

    @property
    def row_height(self) -> float:
        """Hauteur de toutes les barres et de toutes les sous-lignes."""
        return max(self.marker_size, self.line_height + 2 * self.padding)


LABEL_FULL = "full"
LABEL_TRUNCATED = "truncated"
LABEL_HIDDEN = "hidden"


@dataclass(frozen=True)
class LayoutItem:
    event: Event
    x0: float  # début de la barre ; pour un événement ponctuel, centre du losange
    x1: float  # fin de la barre ; égal à x0 pour un événement ponctuel
    left: float  # emprise horizontale (forme + titre affiché)
    right: float
    y: float  # haut de la forme, relatif au haut de la mise en page
    height: float  # hauteur de la forme (barre ou losange) ; le titre est centré dessus
    sublane: int
    label_lines: tuple[str, ...]  # vide si le titre est caché
    label_inside: bool
    label_x: float  # début du texte
    label_state: str = LABEL_HIDDEN

    @property
    def is_point(self) -> bool:
        return self.event.is_point


@dataclass(frozen=True)
class LayoutLane:
    name: str
    color_hex: str
    y: float
    height: float
    items: tuple[LayoutItem, ...]


@dataclass(frozen=True)
class Tick:
    x: float
    label: str


@dataclass(frozen=True)
class Layout:
    lanes: tuple[LayoutLane, ...]
    ticks: tuple[Tick, ...]
    x_min: float
    x_max: float
    height: float
    t_start: float  # début de l'axe, en années fractionnaires
    t_end: float
    titles_full: int = 0  # titres affichés en entier
    titles_truncated: int = 0  # titres affichés avec « … »
    titles_hidden: int = 0  # titres cachés faute de place

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    def items(self) -> Iterable[LayoutItem]:
        for lane in self.lanes:
            yield from lane.items


# --- temps -------------------------------------------------------------------------------


def to_years(d: date) -> float:
    """Date → année fractionnaire (1er janvier 1900 = 1900.0)."""
    start = date(d.year, 1, 1).toordinal()
    length = date(d.year + 1, 1, 1).toordinal() - start if d.year < 9999 else 365
    return d.year + (d.toordinal() - start) / length


def start_position(d: PartialDate) -> float:
    return to_years(d.value)


def end_position(d: PartialDate) -> float:
    """Fin d'une période : une fin « 1950 » ou « 195003 » couvre l'année ou le mois entier."""
    v = d.value
    if d.precision is Precision.YEAR and v.year < 9999:
        return to_years(date(v.year + 1, 1, 1))
    if d.precision is Precision.MONTH:
        if v.month == 12:
            return to_years(date(v.year + 1, 1, 1)) if v.year < 9999 else to_years(v)
        return to_years(date(v.year, v.month + 1, 1))
    return to_years(v)


# --- texte -------------------------------------------------------------------------------


def elide(text: str, max_width: float, measure: TextMeasurer) -> str:
    """Tronque ``text`` avec « … » pour qu'il tienne dans ``max_width``."""
    if measure(text) <= max_width:
        return text
    lo, hi = 0, len(text)  # plus grand préfixe tel que préfixe + « … » tienne
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid].rstrip() + ELLIPSIS) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS


def wrap_text(text: str, max_width: float, measure: TextMeasurer) -> list[str]:
    """Retour à la ligne aux espaces ; un mot trop long est coupé au caractère."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        while measure(word) > max_width and len(word) > 1:  # mot plus large que la ligne
            if current:
                lines.append(current)
                current = ""
            cut = 1
            while cut < len(word) and measure(word[: cut + 1]) <= max_width:
                cut += 1
            lines.append(word[:cut])
            word = word[cut:]
        candidate = f"{current} {word}" if current else word
        if current and measure(candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


# --- axe ---------------------------------------------------------------------------------


def make_ticks(t_start: float, t_end: float, opts: LayoutOptions) -> tuple[Tick, ...]:
    """Graduations en années, avec un pas « rond » assez grand pour rester lisible."""
    min_years = opts.min_tick_px / opts.px_per_year
    step = next((s for s in _TICK_STEPS if s >= min_years), _TICK_STEPS[-1])
    first = math.ceil(t_start / step) * step
    count = int((t_end - first) // step) + 1
    return tuple(
        Tick((first + i * step - t_start) * opts.px_per_year, str(first + i * step))
        for i in range(max(count, 0))
    )


# --- mise en page ------------------------------------------------------------------------

_POINT_SPAN = 1e-7  # durée (en années, ~3 s) d'un événement ponctuel pour détecter la simultanéité


def _span(event: Event) -> tuple[float, float]:
    start = start_position(event.start)
    if event.is_point:
        return start, start + _POINT_SPAN
    return start, max(end_position(event.end), start + _POINT_SPAN)


def assign_sublanes(events: list[Event]) -> list[int]:
    """Numéro de sous-ligne de chaque événement : simultanés = lignes différentes.

    Algorithme glouton par début croissant (la période la plus longue d'abord) : un événement
    prend la première sous-ligne dont le dernier élément est terminé. Le résultat ne dépend que
    des dates.
    """
    spans = [_span(e) for e in events]
    order = sorted(range(len(events)), key=lambda i: (spans[i][0], spans[i][0] - spans[i][1], i))
    ends: list[float] = []
    result = [0] * len(events)
    for i in order:
        start, end = spans[i]
        for k, busy_until in enumerate(ends):
            if start >= busy_until:
                result[i], ends[k] = k, end
                break
        else:
            result[i] = len(ends)
            ends.append(end)
    return result


@dataclass
class _Draft:
    """Élément en cours de placement."""

    event: Event
    x0: float
    x1: float
    sublane: int
    height: float  # hauteur de la forme
    lines: tuple[str, ...] = ()
    inside: bool = False
    label_x: float = 0.0
    state: str = LABEL_HIDDEN
    right: float = 0.0  # fin de la forme, puis du titre affiché
    block: float = 0.0  # hauteur du bloc de titre

    @property
    def is_point(self) -> bool:
        return self.event.is_point


def _shape_left(draft: _Draft, half: float) -> float:
    return draft.x0 - half if draft.is_point else draft.x0


def _fit_lines(title: str, width: float, max_lines: int, measure: TextMeasurer) -> list[str] | None:
    """Titre complet sur au plus ``max_lines`` lignes, sans mot coupé ; ``None`` sinon."""
    if width <= 0 or any(measure(word) > width for word in title.split()):
        return None
    lines = wrap_text(title, width, measure)
    return lines if len(lines) <= max_lines else None


def _truncated_lines(title: str, width: float, max_lines: int, measure: TextMeasurer) -> list[str]:
    """Titre sur au plus ``max_lines`` lignes, la dernière tronquée avec « … »."""
    if max_lines > 1 and all(measure(word) <= width for word in title.split()):
        lines = wrap_text(title, width, measure)
        if len(lines) > max_lines:
            tail = " ".join(lines[max_lines - 1 :])
            return [*lines[: max_lines - 1], elide(tail, width, measure)]
        return lines
    return [elide(title, width, measure)]


def _place_label(
    draft: _Draft,
    limit: float | None,
    opts: LayoutOptions,
    measure: TextMeasurer,
) -> None:
    """Choisit où et comment afficher le titre. ``limit`` : x à ne pas dépasser (élément suivant).

    Ordre de préférence : titre complet sur une ligne (dans la barre, sinon à côté), puis complet
    sur plusieurs lignes si permis (le moins de lignes possible, dans la barre en cas d'égalité),
    puis tronqué avec « … » dans l'emplacement le plus large, enfin caché.
    """
    half = opts.marker_size / 2
    pad = opts.padding
    lh = opts.line_height
    title = draft.event.title
    full = measure(title)
    shape_right = draft.x0 + half if draft.is_point else draft.x1
    outside_x = shape_right + pad
    outside = opts.max_label_width
    if limit is not None:
        outside = min(outside, limit - opts.gap - outside_x)
    inside = (draft.x1 - draft.x0) - 2 * pad if not draft.is_point else -1.0

    lines: list[str] | None = None
    where = False
    if full <= inside:
        lines, where = [title], True
    elif full <= outside:
        lines, where = [title], False
    elif opts.max_label_lines > 1:
        in_fit = _fit_lines(title, inside, opts.max_label_lines, measure)
        out_fit = _fit_lines(title, outside, opts.max_label_lines, measure)
        if in_fit and (not out_fit or len(in_fit) <= len(out_fit)):
            lines, where = in_fit, True
        elif out_fit:
            lines, where = out_fit, False
    if lines is None:
        where = inside >= outside
        width = inside if where else outside
        if width < opts.min_label_width:
            return  # pas de place : titre caché
        lines = _truncated_lines(title, width, opts.max_label_lines, measure)

    draft.inside = where
    draft.lines = tuple(lines)
    draft.state = LABEL_FULL if " ".join(lines) == " ".join(title.split()) else LABEL_TRUNCATED
    draft.block = len(lines) * lh
    draft.label_x = draft.x0 + pad if where else outside_x
    if where:
        draft.height = max(draft.height, draft.block + 2 * pad)  # barre plus haute si besoin
    else:
        draft.right = max(draft.right, outside_x + max(measure(line) for line in lines))


def compute_layout(
    events: Iterable[Event],
    registry: CategoryRegistry,
    measure: TextMeasurer,
    options: LayoutOptions | None = None,
    visible_categories: set[str] | None = None,
    time_range: tuple[float, float] | None = None,
) -> Layout:
    """Calcule la frise.

    ``visible_categories`` : noms de catégories à afficher (``None`` = toutes).
    ``time_range`` : (début, fin) en années ; seuls les événements qui l'intersectent sont gardés.
    """
    opts = options or LayoutOptions()
    selected: list[tuple[str, str, Event]] = []
    for event in events:
        name = registry.category_name(event)
        if visible_categories is not None and name not in visible_categories:
            continue
        if time_range is not None and (
            end_position(event.end) < time_range[0] or start_position(event.start) > time_range[1]
        ):
            continue
        found = registry.for_color(event.color)
        selected.append((name, found.color_hex if found else event.color_hex, event))

    if not selected:
        t0, t1 = time_range if time_range else (0.0, 0.0)
        return Layout((), (), 0.0, 0.0, 0.0, t0, t1)

    if time_range:
        t0, t1 = time_range
    else:
        t0 = min(start_position(e.start) for _, _, e in selected)
        t1 = max(end_position(e.end) for _, _, e in selected)

    # ordre des lignes : celui du registre, puis les catégories implicites par première apparition
    order = {c.name: i for i, c in enumerate(registry)}
    by_lane: dict[str, tuple[str, list[Event]]] = {}
    for name, color_hex, event in sorted(selected, key=lambda s: start_position(s[2].start)):
        by_lane.setdefault(name, (color_hex, []))[1].append(event)
    lane_names = sorted(by_lane, key=lambda n: (order.get(n, len(order)),))  # tri stable

    half = opts.marker_size / 2
    row_h = opts.row_height
    x_limit = (t1 - t0) * opts.px_per_year if time_range else None
    counts = {LABEL_FULL: 0, LABEL_TRUNCATED: 0, LABEL_HIDDEN: 0}
    lanes: list[LayoutLane] = []
    y = 0.0
    for name in lane_names:
        color_hex, lane_events = by_lane[name]
        sublanes = assign_sublanes(lane_events)
        drafts: list[_Draft] = []
        for event, sub in zip(lane_events, sublanes, strict=True):
            x0 = (start_position(event.start) - t0) * opts.px_per_year
            if event.is_point:
                x1 = x0
                right = x0 + half
            else:
                x1 = (end_position(event.end) - t0) * opts.px_per_year
                if x_limit is not None:  # période demandée : les barres qui dépassent sont rognées
                    x0, x1 = max(x0, 0.0), min(x1, x_limit)
                x1 = max(x1, x0 + opts.marker_size)
                right = x1
            drafts.append(_Draft(event, x0, x1, sub, row_h, right=right))

        n_sub = max(sublanes) + 1
        for k in range(n_sub):
            row = sorted((d for d in drafts if d.sublane == k), key=lambda d: d.x0)
            for i, draft in enumerate(row):
                limit = _shape_left(row[i + 1], half) if i + 1 < len(row) else None
                _place_label(draft, limit, opts, measure)
                counts[draft.state] += 1

        heights = [row_h] * n_sub  # hauteur de chaque sous-ligne : le plus haut de ses éléments
        for d in drafts:
            heights[d.sublane] = max(heights[d.sublane], d.height, d.block)
        tops: list[float] = []
        cursor = 0.0
        for h in heights:
            tops.append(cursor)
            cursor += h + opts.sublane_spacing
        lane_height = max(cursor - opts.sublane_spacing, opts.min_lane_height)
        items = tuple(
            LayoutItem(
                event=d.event,
                x0=d.x0,
                x1=d.x1,
                left=_shape_left(d, half),
                right=d.right,
                y=y + tops[d.sublane] + (heights[d.sublane] - d.height) / 2,
                height=d.height,
                sublane=d.sublane,
                label_lines=d.lines,
                label_inside=d.inside,
                label_x=d.label_x,
                label_state=d.state,
            )
            for d in drafts
        )
        lanes.append(LayoutLane(name, color_hex, y, lane_height, items))
        y += lane_height + opts.lane_spacing

    all_items = [item for lane in lanes for item in lane.items]
    return Layout(
        lanes=tuple(lanes),
        ticks=make_ticks(t0, t1, opts),
        x_min=min(i.left for i in all_items),
        x_max=max(i.right for i in all_items),
        height=y - opts.lane_spacing,
        t_start=t0,
        t_end=t1,
        titles_full=counts[LABEL_FULL],
        titles_truncated=counts[LABEL_TRUNCATED],
        titles_hidden=counts[LABEL_HIDDEN],
    )
