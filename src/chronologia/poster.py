"""Mise en page « affiche » pour l'impression grand format.

Principe : la frise est calculée une fois dans des unités de conception (1 unité = 1 pixel de
police de 12 px), puis dessinée avec un facteur d'échelle uniforme pour remplir la page.
Le facteur d'échelle fixe la taille réelle du texte : on cherche donc l'échelle horizontale
(pixels par an) qui le rend le plus grand possible pour la page demandée.

Tout est dessiné avec ``QPainter`` : formes et texte restent vectoriels dans le PDF.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen

from .categories import CategoryRegistry
from .layout import (
    Layout,
    LayoutItem,
    LayoutOptions,
    TextMeasurer,
    compute_layout,
    elide,
    end_position,
    start_position,
    wrap_text,
)
from .model import Event
from .shapes import item_shape_path
from .theme import ACCENT

FONT_PX = 12.0  # taille du texte des événements, en unités de conception
TITLE_PX = 28.0
MARGIN = 24.0
NAME_COLUMN = 220.0  # colonne des noms de catégories
NAME_MAX_LINES = 2
HEADER = 30.0  # bande de l'axe, en haut et en bas
MAX_LABEL_WIDTH = 1500.0
DEFAULT_MAX_LABEL_LINES = 3
MEASURE_PX = 100  # on mesure sur une grande police : le PDF n'applique pas le hinting
MIN_DESIGN_WIDTH = 600.0
MAX_DESIGN_WIDTH = 300000.0
DEFAULT_FONT_PT = 8.0  # taille du texte sur la page, demandée par défaut
DEFAULT_EXTRA_SUBLANES = 6  # lignes de plus qu'un titre serré peut faire créer dans sa catégorie
MAX_SPACING_FACTOR = 24.0  # étirement vertical maximal des écarts entre lignes
POINTS_PER_MM = 72.0 / 25.4


@dataclass(frozen=True)
class PrintTheme:
    background: QColor
    text: QColor
    band: QColor
    grid: QColor
    axis: QColor


PRINT_THEME = PrintTheme(
    background=QColor("#ffffff"),
    text=QColor("#1a1a1a"),
    band=QColor("#f1f1f1"),
    grid=QColor("#cfcfcf"),
    axis=QColor("#555555"),
)


class _Metrics:
    """Mesures de texte indépendantes de l'écran et de la résolution."""

    def __init__(self, family: str) -> None:
        font = QFont(family)
        font.setPixelSize(MEASURE_PX)
        self._fm = QFontMetricsF(font)
        self._k = FONT_PX / MEASURE_PX
        self.line_height = self._fm.height() * self._k
        self.ascent = self._fm.ascent() * self._k

    def width(self, text: str, px: float = FONT_PX) -> float:
        return self._fm.horizontalAdvance(text) * px / MEASURE_PX

    @property
    def measurer(self) -> TextMeasurer:
        return self.width


@dataclass(frozen=True)
class PosterPlan:
    layout: Layout
    options: LayoutOptions
    title: str
    lane_names: tuple[tuple[str, ...], ...]  # lignes de texte du nom de chaque catégorie
    content_width: float  # unités de conception
    content_height: float
    page_width_pt: float
    page_height_pt: float
    scale: float  # points PDF par unité de conception
    ascent: float
    family: str
    requested_font_pt: float = 0.0  # taille de texte demandée (0 : non précisée)

    @property
    def titles_full(self) -> int:
        return self.layout.titles_full

    @property
    def titles_truncated(self) -> int:
        return self.layout.titles_truncated

    @property
    def titles_hidden(self) -> int:
        return self.layout.titles_hidden

    @property
    def font_pt(self) -> float:
        """Taille réelle, sur la page, du texte des événements."""
        return FONT_PX * self.scale

    @property
    def event_count(self) -> int:
        return sum(len(lane.items) for lane in self.layout.lanes)

    @property
    def title_height(self) -> float:
        return TITLE_PX * 1.6 if self.title else 0.0

    # --- géométrie : unités de conception <-> points de la page ---------------------------

    @property
    def origin_pt(self) -> QPointF:
        """Coin haut gauche du dessin sur la page : centré horizontalement, collé en haut."""
        return QPointF((self.page_width_pt - self.content_width * self.scale) / 2, 0.0)

    @property
    def x_offset(self) -> float:
        """x de la scène de conception pour x = 0 de la mise en page."""
        return MARGIN + NAME_COLUMN - self.layout.x_min

    @property
    def y_lanes(self) -> float:
        """y de la scène de conception pour y = 0 de la mise en page."""
        return MARGIN + self.title_height + HEADER + self.lane_pad

    @property
    def lane_pad(self) -> float:
        """Demi-écart entre deux lignes : les bandes de catégories se touchent, et la première
        et la dernière gardent cet espace avec les axes."""
        return self.options.lane_spacing / 2

    @property
    def y_axis_bottom(self) -> float:
        return self.y_lanes + self.layout.height + self.lane_pad

    def to_page(self, dx: float, dy: float) -> QPointF:
        o = self.origin_pt
        return QPointF(o.x() + dx * self.scale, o.y() + dy * self.scale)

    def to_design(self, x: float, y: float) -> QPointF:
        o = self.origin_pt
        return QPointF((x - o.x()) / self.scale, (y - o.y()) / self.scale)

    def design_rect(self, rect_pt: QRectF) -> QRectF:
        """Rectangle de la page (points) exprimé en unités de conception."""
        a = self.to_design(rect_pt.left(), rect_pt.top())
        b = self.to_design(rect_pt.right(), rect_pt.bottom())
        return QRectF(a, b)

    def item_design_rect(self, item: LayoutItem) -> QRectF:
        """Emprise d'un événement (forme et titre), en unités de conception."""
        top = self.y_lanes + item.y
        block = len(item.label_lines) * self.options.line_height
        height = max(item.height, block)
        centre = top + item.height / 2
        return QRectF(
            self.x_offset + item.left, centre - height / 2, item.right - item.left, height
        )

    def item_rect(self, item: LayoutItem) -> QRectF:
        """Emprise d'un événement (forme et titre), en points de la page."""
        r = self.item_design_rect(item)
        a = self.to_page(r.left(), r.top())
        return QRectF(a, QRectF(0, 0, r.width() * self.scale, r.height() * self.scale).size())

    def item_of(self, event: Event) -> LayoutItem | None:
        for item in self.layout.items():
            if item.event is event:
                return item
        return None

    def event_at(self, x: float, y: float, tolerance: float = 0.0) -> Event | None:
        """Événement sous le point (x, y) de la page, en points ; ``tolerance`` en points."""
        d = self.to_design(x, y)
        tol = tolerance / self.scale
        best: tuple[float, Event] | None = None
        for lane in self.layout.lanes:
            top = self.y_lanes + lane.y
            if (
                not top - self.lane_pad - 1 - tol
                <= d.y()
                <= top + lane.height + self.lane_pad + 1 + tol
            ):
                continue
            for item in lane.items:
                r = self.item_design_rect(item).adjusted(-tol, -tol, tol, tol)
                if r.contains(d):
                    area = r.width() * r.height()
                    if best is None or area < best[0]:
                        best = (area, item.event)
        return best[1] if best else None

    def year_at(self, x: float) -> float | None:
        """Année fractionnaire à l'abscisse x de la page (points), ``None`` sans frise."""
        if not self.layout.lanes:
            return None
        dx = self.to_design(x, 0).x()
        return self.layout.t_start + (dx - self.x_offset) / self.options.px_per_year

    def lane_color_at(self, y: float) -> str:
        """Couleur ``#rrggbb`` de la catégorie dont la ligne est à l'ordonnée y (points)."""
        dy = self.to_design(0, y).y()
        for lane in self.layout.lanes:
            top = self.y_lanes + lane.y - self.lane_pad  # les bandes se touchent
            if top <= dy < top + lane.height + 2 * self.lane_pad:
                return lane.color_hex
        return ""

    def apply_transform(self, painter: QPainter, device_per_point: float = 1.0) -> None:
        """Place le dessin centré sur la page. ``device_per_point`` : pixels par point."""
        k = self.scale * device_per_point
        painter.translate(
            (self.page_width_pt - self.content_width * self.scale) / 2 * device_per_point,
            (self.page_height_pt - self.content_height * self.scale) / 2 * device_per_point,
        )
        painter.scale(k, k)


def _title_height(title: str) -> float:
    return TITLE_PX * 1.6 if title else 0.0


def _build(
    events: list[Event],
    registry: CategoryRegistry,
    visible: set[str] | None,
    metrics: _Metrics,
    px_per_year: float,
    time_range: tuple[float, float] | None = None,
    max_label_lines: int = DEFAULT_MAX_LABEL_LINES,
    spacing_factor: float = 1.0,
    extra_sublanes: int = DEFAULT_EXTRA_SUBLANES,
    label_cache: dict | None = None,
) -> tuple[Layout, LayoutOptions]:
    opts = LayoutOptions(
        px_per_year=px_per_year,
        line_height=metrics.line_height,
        max_label_width=MAX_LABEL_WIDTH,
        max_label_lines=max_label_lines,
        extra_sublanes=extra_sublanes,
        lane_spacing=LayoutOptions().lane_spacing * spacing_factor,
        sublane_spacing=LayoutOptions().sublane_spacing * spacing_factor,
        min_lane_height=NAME_MAX_LINES * metrics.line_height,
    )
    layout = compute_layout(
        events,
        registry,
        metrics.measurer,
        opts,
        visible_categories=visible,
        time_range=time_range,
        label_cache=label_cache,
    )
    return layout, opts


def _content_size(layout: Layout, title: str, opts: LayoutOptions) -> tuple[float, float]:
    width = 2 * MARGIN + NAME_COLUMN + layout.width
    height = 2 * MARGIN + _title_height(title) + 2 * HEADER + layout.height + opts.lane_spacing
    return width, height


class PosterPlanner:
    """Calcule la mise en page de la feuille pour une taille de texte demandée.

    La frise est dessinée une fois en unités de conception puis mise à l'échelle sur la page : la
    taille du texte sur la page est donc ``12 × échelle``. Pour obtenir la taille demandée, on
    cherche l'échelle horizontale (années par unité) pour laquelle la frise, mise à l'échelle,
    occupe exactement la largeur de la page. Les mises en page essayées sont gardées : changer
    de format ou de taille de texte recalcule très peu de choses, même avec des milliers
    d'événements. Seuls les événements, les filtres, la période et les lignes par titre imposent
    de créer un nouveau planificateur.
    """

    def __init__(
        self,
        events: Iterable[Event],
        registry: CategoryRegistry,
        visible: set[str] | None = None,
        time_range: tuple[float, float] | None = None,
        family: str | None = None,
        max_label_lines: int = DEFAULT_MAX_LABEL_LINES,
        extra_sublanes: int = DEFAULT_EXTRA_SUBLANES,
    ) -> None:
        self.family = family or QFont().family()
        self._metrics = _Metrics(self.family)
        self._registry, self._visible = registry, visible
        self._time_range, self._max_lines = time_range, max_label_lines
        self._extra = extra_sublanes
        self._events = [
            e
            for e in events
            if (visible is None or registry.category_name(e) in visible)
            and (
                time_range is None
                or not (
                    end_position(e.end) < time_range[0] or start_position(e.start) > time_range[1]
                )
            )
        ]
        self._cache: dict[tuple[float, float, int], tuple[Layout, LayoutOptions]] = {}
        self._label_cache: dict = {}
        self._span = 1.0
        if self._events:
            if time_range:
                self._span = max(time_range[1] - time_range[0], 1.0)
            else:
                first = min(start_position(e.start) for e in self._events)
                last = max(end_position(e.end) for e in self._events)
                self._span = max(last - first, 1.0)
        self._ppy_min = MIN_DESIGN_WIDTH / self._span
        self._ppy_max = MAX_DESIGN_WIDTH / self._span

    @property
    def is_empty(self) -> bool:
        return not self._events

    def _layout(
        self, ppy: float, factor: float = 1.0, extra: int | None = None
    ) -> tuple[Layout, LayoutOptions]:
        extra = self._extra if extra is None else extra
        key = (round(ppy, 9), round(factor, 3), extra)
        if key not in self._cache:
            self._cache[key] = _build(
                self._events,
                self._registry,
                self._visible,
                self._metrics,
                ppy,
                self._time_range,
                self._max_lines,
                factor,
                extra,
                self._label_cache,
            )
        return self._cache[key]

    def _width_at(self, ppy: float, extra: int) -> float:
        layout, opts = self._layout(ppy, 1.0, extra)
        return _content_size(layout, "", opts)[0]

    def _ppy_for_width(self, target: float, extra: int) -> float:
        """Plus grande échelle (années ↔ unités) dont la frise tient dans ``target`` unités."""
        lo, hi = self._ppy_min, self._ppy_max
        w_lo = self._width_at(lo, extra)
        if w_lo > target:
            return lo  # même la plus étroite est trop large : le texte devra être réduit
        w_hi = self._width_at(hi, extra)
        if w_hi <= target:
            return hi  # la page est plus large que la plus large des frises
        # interpolation (la largeur croît à peu près linéairement avec l'échelle), bornée pour
        # garantir la convergence
        for _ in range(14):
            guess = lo + (hi - lo) * (target - w_lo) / (w_hi - w_lo)
            guess = min(max(guess, lo + 0.05 * (hi - lo)), hi - 0.05 * (hi - lo))
            width = self._width_at(guess, extra)
            if width <= target:
                lo, w_lo = guess, width
                if target - width <= 0.003 * target:
                    break
            else:
                hi, w_hi = guess, width
        return lo

    def _fit(
        self, extra: int, page_w: float, page_h: float, title: str, wanted: float
    ) -> tuple[float, int, Layout, LayoutOptions, float, float, float]:
        """Mise en page occupant la largeur de la page avec le texte demandé (si la hauteur le permet).

        Renvoie ``(échelle horizontale, lignes en plus, mise en page, options, largeur, hauteur,
        échelle de la page)``.
        """
        ppy = self._ppy_for_width(page_w / wanted, extra)
        layout, opts = self._layout(ppy, 1.0, extra)
        cw, ch = _content_size(layout, title, opts)
        scale = min(page_w / cw, page_h / ch, wanted)  # jamais plus grand que demandé
        return ppy, extra, layout, opts, cw, ch, scale

    def _stretched(
        self, ppy: float, extra_sublanes: int, extra: float
    ) -> tuple[Layout, LayoutOptions]:
        """La même mise en page, avec plus d'espace entre les lignes pour remplir la page.

        Les écarts (entre catégories et entre sous-lignes) sont multipliés d'un même facteur ;
        les barres et le texte gardent leur taille. Le facteur est borné : au-delà, le bas de la
        page reste vide plutôt que d'étirer démesurément les écarts.
        """
        layout, opts = self._layout(ppy, 1.0, extra_sublanes)
        sublane_gaps = sum(max((i.sublane for i in lane.items), default=0) for lane in layout.lanes)
        flexible = opts.lane_spacing * len(layout.lanes) + opts.sublane_spacing * sublane_gaps
        if flexible <= 0:
            return layout, opts
        factor = min(1.0 + extra / flexible, MAX_SPACING_FACTOR)
        return self._layout(ppy, factor, extra_sublanes)

    def plan(
        self,
        page_width_mm: float,
        page_height_mm: float,
        title: str = "",
        font_pt: float = DEFAULT_FONT_PT,
    ) -> PosterPlan:
        """Mise en page de la page, avec un texte de ``font_pt`` points si la page le permet.

        - La frise est élargie ou resserrée pour occuper toute la largeur de la page avec cette
          taille de texte : plus le texte est petit, plus elle est large et plus de titres tiennent.
        - La hauteur disponible sert d'abord à séparer les titres serrés (un élément dont le titre
          ne tient pas descend sur une ligne libre de sa catégorie), tant que le texte garde la
          taille demandée ; ce qui reste est réparti en espace entre les lignes.
        - Si la frise est trop haute même sans ces lignes en plus, le texte est réduit.
        """
        if self.is_empty:
            raise ValueError("aucun événement à exporter")
        title = title.strip()
        page_w = page_width_mm * POINTS_PER_MM
        page_h = page_height_mm * POINTS_PER_MM
        wanted = font_pt / FONT_PX  # échelle donnant la taille de texte demandée

        def holds(result) -> bool:
            return result[6] >= wanted * 0.999

        best = self._fit(self._extra, page_w, page_h, title, wanted)
        if not holds(best) and self._extra > 0:
            best = self._fit(0, page_w, page_h, title, wanted)
            if holds(best):  # recherche du plus grand nombre de lignes en plus qui garde le texte
                low, high = 0, self._extra
                while high - low > 1:
                    mid = (low + high) // 2
                    attempt = self._fit(mid, page_w, page_h, title, wanted)
                    if holds(attempt):
                        low, best = mid, attempt
                    else:
                        high = mid
        ppy, extra_sublanes, layout, opts, cw, ch, scale = best
        spare = page_h / scale - ch  # place verticale restante, en unités de conception
        if spare > 1.0:
            layout, opts = self._stretched(ppy, extra_sublanes, spare)
            cw, ch = _content_size(layout, title, opts)
            scale = min(page_w / cw, page_h / ch, wanted)
        names = tuple(tuple(_wrap_name(lane.name, self._metrics)) for lane in layout.lanes)
        return PosterPlan(
            layout=layout,
            options=opts,
            title=title,
            lane_names=names,
            content_width=cw,
            content_height=ch,
            page_width_pt=page_w,
            page_height_pt=page_h,
            scale=scale,
            ascent=self._metrics.ascent,
            family=self.family,
            requested_font_pt=font_pt,
        )


def plan_poster(
    events: Iterable[Event],
    registry: CategoryRegistry,
    visible: set[str] | None,
    page_width_mm: float,
    page_height_mm: float,
    title: str = "",
    time_range: tuple[float, float] | None = None,
    family: str | None = None,
    font_pt: float = DEFAULT_FONT_PT,
    max_label_lines: int = DEFAULT_MAX_LABEL_LINES,
) -> PosterPlan | None:
    """Raccourci : ``None`` s'il n'y a aucun événement à exporter."""
    planner = PosterPlanner(events, registry, visible, time_range, family, max_label_lines)
    if planner.is_empty:
        return None
    return planner.plan(page_width_mm, page_height_mm, title, font_pt)


def _wrap_name(name: str, metrics: _Metrics) -> list[str]:
    width = NAME_COLUMN - 24
    lines = wrap_text(name, width, metrics.measurer)
    if len(lines) > NAME_MAX_LINES:
        lines = lines[:NAME_MAX_LINES]
        lines[-1] = elide(lines[-1] + " …", width, metrics.measurer)
    return lines


# --- dessin ------------------------------------------------------------------------------


def paint_poster(
    painter: QPainter,
    plan: PosterPlan,
    theme: PrintTheme = PRINT_THEME,
    clip: QRectF | None = None,
    dimmed: Callable[[Event], bool] | None = None,
    selected: Event | None = None,
) -> None:
    """Dessine l'affiche. Le peintre doit déjà être en unités de conception.

    ``clip`` (unités de conception) : seule cette zone est dessinée (affichage à l'écran d'une
    très grande feuille) ; ``dimmed`` estompe les événements qui ne correspondent pas à la
    recherche ; ``selected`` entoure un événement.
    """
    layout = plan.layout
    font = QFont(plan.family)
    font.setPixelSize(round(FONT_PX))
    bold = QFont(font)
    bold.setBold(True)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(font)

    width, height = plan.content_width, plan.content_height
    painter.fillRect(QRectF(0, 0, width, height), theme.background)

    x_off = plan.x_offset  # x de la scène pour x = 0 de la mise en page
    y_axis_top = MARGIN + plan.title_height
    y_lanes = plan.y_lanes
    pad = plan.lane_pad
    y_rule_top = y_axis_top + HEADER
    y_axis_bottom = plan.y_axis_bottom
    inner_left, inner_right = MARGIN, width - MARGIN

    if plan.title:
        title_font = QFont(plan.family)
        title_font.setPixelSize(round(TITLE_PX))
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(theme.text)
        painter.drawText(QPointF(MARGIN, MARGIN + TITLE_PX), plan.title)
        painter.setFont(font)

    # bandes alternées et grille
    for i, lane in enumerate(layout.lanes):
        if i % 2 == 0:
            painter.fillRect(
                QRectF(
                    inner_left,
                    y_lanes + lane.y - pad,
                    inner_right - inner_left,
                    lane.height + 2 * pad,
                ),
                theme.band,
            )
    painter.setPen(QPen(theme.grid, 0.8, Qt.PenStyle.DotLine))
    for tick in layout.ticks:
        x = x_off + tick.x
        if clip is not None and not clip.left() - 60 <= x <= clip.right() + 60:
            continue
        painter.drawLine(QPointF(x, y_rule_top), QPointF(x, y_axis_bottom))

    # axes (haut et bas)
    for y, rule in ((y_axis_top, y_rule_top), (y_axis_bottom, y_axis_bottom)):
        painter.setPen(QPen(theme.axis, 1.0))
        painter.drawLine(QPointF(inner_left, rule), QPointF(inner_right, rule))
        painter.setPen(theme.text)
        for tick in layout.ticks:
            x = x_off + tick.x
            if clip is not None and not clip.left() - 60 <= x <= clip.right() + 60:
                continue
            painter.drawText(
                QRectF(x - 40, y, 80, HEADER), Qt.AlignmentFlag.AlignCenter, tick.label
            )

    # événements
    marker = plan.options.point_width
    accent = QColor(ACCENT)
    for lane in layout.lanes:
        if clip is not None and not (
            y_lanes + lane.y - pad - 1 <= clip.bottom()
            and y_lanes + lane.y + lane.height + pad + 1 >= clip.top()
        ):
            continue
        for item in lane.items:
            if clip is not None and not plan.item_design_rect(item).intersects(clip):
                continue
            painter.setOpacity(0.2 if dimmed is not None and dimmed(item.event) else 1.0)
            if selected is not None and item.event is selected:
                halo = plan.item_design_rect(item).adjusted(-4, -3, 4, 3)
                painter.setPen(QPen(accent, 2.0))
                fill = QColor(accent)
                fill.setAlpha(45)
                painter.setBrush(fill)
                painter.drawRect(halo)
            color = QColor(item.event.color_hex)
            path = item_shape_path(item, marker, x_off, y_lanes)
            painter.setPen(QPen(color.darker(130), 1.2))
            if item.is_point:
                painter.setBrush(color)
            else:
                painter.setBrush(_over(color, theme.background, 0.27))
            painter.drawPath(path)

            painter.setPen(theme.text)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            top = y_lanes + item.y
            first = top + (item.height - len(item.label_lines) * _line_height(plan)) / 2
            for k, line in enumerate(item.label_lines):
                painter.drawText(
                    QPointF(x_off + item.label_x, first + k * _line_height(plan) + plan.ascent),
                    line,
                )
    painter.setOpacity(1.0)

    # noms des catégories
    painter.setPen(theme.text)
    for lane, lines in zip(layout.lanes, plan.lane_names, strict=True):
        y = y_lanes + lane.y
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(lane.color_hex))
        painter.drawEllipse(QPointF(inner_left + 7, y + _line_height(plan) / 2 + 1), 5, 5)
        painter.setPen(theme.text)
        painter.setFont(bold)
        for k, line in enumerate(lines):
            painter.drawText(
                QPointF(inner_left + 20, y + k * _line_height(plan) + plan.ascent), line
            )
        painter.setFont(font)


def _line_height(plan: PosterPlan) -> float:
    return plan.options.line_height


def _over(color: QColor, background: QColor, opacity: float) -> QColor:
    """Couleur opaque équivalente à ``color`` à ``opacity`` sur ``background``."""

    def mix(a: int, b: int) -> int:
        return round(a * opacity + b * (1 - opacity))

    return QColor(
        mix(color.red(), background.red()),
        mix(color.green(), background.green()),
        mix(color.blue(), background.blue()),
    )


def render_preview(plan: PosterPlan, width_px: int = 900) -> QImage:
    """Aperçu raster de la page entière."""
    ratio = plan.page_height_pt / plan.page_width_pt
    image = QImage(width_px, max(round(width_px * ratio), 1), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    plan.apply_transform(painter, width_px / plan.page_width_pt)
    paint_poster(painter, plan)
    painter.end()
    return image
