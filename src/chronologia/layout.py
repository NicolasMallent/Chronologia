"""Moteur de mise en page de la frise, indépendant de Qt.

Entrée : événements, catégories, fonction de mesure du texte. Sortie : positions (x, y,
dimensions) dans une unité abstraite (pixels à l'écran, points pour le PDF), que la vue et
l'export dessinent à l'identique.

Principe :
- une ligne (« lane ») par catégorie visible, dans l'ordre du registre ;
- dans une ligne, les éléments sont rangés en sous-lignes : un élément va dans la première
  sous-ligne où il ne chevauche rien, titre compris ;
- titre d'une période : dans la barre s'il y tient, sinon à droite de la barre ;
  titre d'un événement ponctuel : à droite du losange ;
- ``wrap=True`` (export) : retour à la ligne automatique, titre toujours complet ;
  ``wrap=False`` (écran) : une ligne, tronquée avec « … » (le titre complet est en info-bulle).
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
    gap: float = 6.0  # espace horizontal minimal entre deux éléments d'une même sous-ligne
    max_label_width: float = 220.0  # largeur max d'un titre placé à côté d'un élément
    max_inside_lines: int = 3  # au-delà, le titre d'une période passe à droite de la barre
    min_inside_width: float = 40.0  # écran : largeur mini d'une barre pour y écrire le titre
    sublane_spacing: float = 4.0
    lane_spacing: float = 14.0
    min_lane_height: float = 0.0  # ex. : place pour le nom de la catégorie
    min_tick_px: float = 70.0
    wrap: bool = True

    def __post_init__(self) -> None:
        if self.px_per_year <= 0 or self.line_height <= 0 or self.max_label_width <= 0:
            raise ValueError("échelle, hauteur de ligne et largeur de titre doivent être > 0")


@dataclass(frozen=True)
class LayoutItem:
    event: Event
    x0: float  # début de la barre ; pour un événement ponctuel, centre du losange
    x1: float  # fin de la barre ; égal à x0 pour un événement ponctuel
    left: float  # emprise horizontale (marqueur + titre), utilisée contre les chevauchements
    right: float
    y: float  # haut de l'élément, relatif au haut de la mise en page
    height: float
    sublane: int
    label_lines: tuple[str, ...]
    label_inside: bool
    label_x: float  # début du texte

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


@dataclass
class _Draft:
    """Élément en cours de placement (la sous-ligne et le y sont encore inconnus)."""

    event: Event
    x0: float
    x1: float
    left: float
    right: float
    height: float
    lines: tuple[str, ...]
    inside: bool
    label_x: float
    sublane: int = 0


def _build_draft(
    event: Event,
    t0: float,
    opts: LayoutOptions,
    measure: TextMeasurer,
    x_limit: float | None = None,
) -> _Draft:
    half = opts.marker_size / 2
    pad = opts.padding
    x0 = (start_position(event.start) - t0) * opts.px_per_year
    if event.is_point:
        x1, left, bar_right = x0, x0 - half, x0 + half
    else:
        x1 = (end_position(event.end) - t0) * opts.px_per_year
        if x_limit is not None:  # période demandée : les barres qui dépassent sont rognées
            x0, x1 = max(x0, 0.0), min(x1, x_limit)
        x1 = max(x1, x0 + opts.marker_size)
        left, bar_right = x0, x1

    inside_width = (x1 - x0) - 2 * pad
    if not event.is_point and inside_width >= opts.min_inside_width:
        if opts.wrap:
            lines = wrap_text(event.title, inside_width, measure)
            # pas de mot coupé dans une barre : sinon le titre passe à droite
            fits = len(lines) <= opts.max_inside_lines and all(
                measure(word) <= inside_width for word in event.title.split()
            )
        else:
            lines = [elide(event.title, inside_width, measure)]
            fits = True
        if fits:
            height = max(opts.marker_size, len(lines) * opts.line_height + 2 * pad)
            return _Draft(event, x0, x1, left, bar_right, height, tuple(lines), True, x0 + pad)

    # titre à droite de l'élément
    if opts.wrap:
        lines = wrap_text(event.title, opts.max_label_width, measure)
    else:
        lines = [elide(event.title, opts.max_label_width, measure)]
    label_x = bar_right + pad
    label_w = max(measure(line) for line in lines)
    height = max(opts.marker_size, len(lines) * opts.line_height)
    return _Draft(event, x0, x1, left, label_x + label_w, height, tuple(lines), False, label_x)


def _pack(drafts: list[_Draft], gap: float) -> int:
    """Répartit les éléments en sous-lignes sans chevauchement. Renvoie leur nombre."""
    ends: list[float] = []  # bord droit de chaque sous-ligne
    for draft in sorted(drafts, key=lambda d: (d.left, -(d.right - d.left))):
        for i, end in enumerate(ends):
            if draft.left >= end + gap:
                draft.sublane, ends[i] = i, draft.right
                break
        else:
            draft.sublane = len(ends)
            ends.append(draft.right)
    return len(ends)


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

    lanes: list[LayoutLane] = []
    y = 0.0
    for name in lane_names:
        color_hex, lane_events = by_lane[name]
        x_limit = (t1 - t0) * opts.px_per_year if time_range else None
        drafts = [_build_draft(e, t0, opts, measure, x_limit) for e in lane_events]
        n_sub = _pack(drafts, opts.gap)
        heights = [0.0] * n_sub
        for d in drafts:
            heights[d.sublane] = max(heights[d.sublane], d.height)
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
                left=d.left,
                right=d.right,
                y=y + tops[d.sublane] + (heights[d.sublane] - d.height) / 2,
                height=d.height,
                sublane=d.sublane,
                label_lines=d.lines,
                label_inside=d.inside,
                label_x=d.label_x,
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
    )
