"""Mise en page « affiche » pour l'impression grand format.

Principe : la frise est calculée une fois dans des unités de conception (1 unité = 1 pixel de
police de 12 px), puis dessinée avec un facteur d'échelle uniforme pour remplir la page.
Le facteur d'échelle fixe la taille réelle du texte : on cherche donc l'échelle horizontale
(pixels par an) qui le rend le plus grand possible pour la page demandée.

Tout est dessiné avec ``QPainter`` : formes et texte restent vectoriels dans le PDF.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen

from .categories import CategoryRegistry
from .layout import (
    Layout,
    LayoutOptions,
    TextMeasurer,
    compute_layout,
    elide,
    wrap_text,
)
from .model import Event
from .shapes import item_shape_path

FONT_PX = 12.0  # taille du texte des événements, en unités de conception
TITLE_PX = 28.0
MARGIN = 24.0
NAME_COLUMN = 220.0  # colonne des noms de catégories
NAME_MAX_LINES = 2
HEADER = 30.0  # bande de l'axe, en haut et en bas
MAX_LABEL_WIDTH = 1500.0
DEFAULT_MAX_LABEL_LINES = 3
MEASURE_PX = 100  # on mesure sur une grande police : le PDF n'applique pas le hinting
_CANDIDATES = 48
MIN_DESIGN_WIDTH = 600.0
MAX_DESIGN_WIDTH = 300000.0
DEFAULT_MIN_FONT_PT = 8.0  # taille mini du texte sur la page
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
) -> tuple[Layout, LayoutOptions]:
    opts = LayoutOptions(
        px_per_year=px_per_year,
        line_height=metrics.line_height,
        max_label_width=MAX_LABEL_WIDTH,
        max_label_lines=max_label_lines,
        min_lane_height=NAME_MAX_LINES * metrics.line_height,
    )
    layout = compute_layout(
        events,
        registry,
        metrics.measurer,
        opts,
        visible_categories=visible,
        time_range=time_range,
    )
    return layout, opts


def _content_size(layout: Layout, title: str) -> tuple[float, float]:
    width = 2 * MARGIN + NAME_COLUMN + layout.width
    height = 2 * MARGIN + _title_height(title) + 2 * HEADER + layout.height
    return width, height


class PosterPlanner:
    """Calcule les mises en page candidates une fois, puis choisit la meilleure pour chaque page.

    Les candidats ne dépendent ni de la taille de page ni du titre : changer de format est donc
    instantané. Seuls les événements, les filtres et la période demandent un nouveau calcul.
    """

    def __init__(
        self,
        events: Iterable[Event],
        registry: CategoryRegistry,
        visible: set[str] | None = None,
        time_range: tuple[float, float] | None = None,
        family: str | None = None,
        max_label_lines: int = DEFAULT_MAX_LABEL_LINES,
    ) -> None:
        self.family = family or QFont().family()
        self._metrics = _Metrics(self.family)
        selected = list(events)
        self._candidates: list[tuple[Layout, LayoutOptions]] = []
        probe, _ = _build(
            selected, registry, visible, self._metrics, 1.0, time_range, max_label_lines
        )
        if not probe.lanes:
            return
        span = max(probe.t_end - probe.t_start, 1.0)
        # largeurs de conception réparties géométriquement
        for i in range(_CANDIDATES):
            ratio = MAX_DESIGN_WIDTH / MIN_DESIGN_WIDTH
            design_width = MIN_DESIGN_WIDTH * ratio ** (i / (_CANDIDATES - 1))
            self._candidates.append(
                _build(
                    selected,
                    registry,
                    visible,
                    self._metrics,
                    design_width / span,
                    time_range,
                    max_label_lines,
                )
            )

    @property
    def is_empty(self) -> bool:
        return not self._candidates

    def plan(
        self,
        page_width_mm: float,
        page_height_mm: float,
        title: str = "",
        min_font_pt: float = DEFAULT_MIN_FONT_PT,
    ) -> PosterPlan:
        """Meilleure mise en page pour la page : le plus de titres, texte au moins ``min_font_pt``.

        Plus la frise est large (en unités de conception), plus les titres ont de la place, mais
        plus le texte rétrécit sur la page. On retient donc la frise la plus large dont le texte
        reste lisible (``min_font_pt``) ; si même la plus étroite est trop petite, on garde celle
        qui donne le plus grand texte.
        """
        if self.is_empty:
            raise ValueError("aucun événement à exporter")
        title = title.strip()
        page_w = page_width_mm * POINTS_PER_MM
        page_h = page_height_mm * POINTS_PER_MM
        scored: list[tuple[float, Layout, LayoutOptions]] = []
        for layout, opts in self._candidates:
            cw, ch = _content_size(layout, title)
            scored.append((min(page_w / cw, page_h / ch), layout, opts))
        readable = [c for c in scored if c[0] * FONT_PX >= min_font_pt]
        if readable:
            best = max(readable, key=lambda c: (c[1].titles_full, c[1].titles_truncated, c[0]))
        else:
            best = max(scored, key=lambda c: c[0])
        scale, layout, opts = best
        cw, ch = _content_size(layout, title)
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
    min_font_pt: float = DEFAULT_MIN_FONT_PT,
    max_label_lines: int = DEFAULT_MAX_LABEL_LINES,
) -> PosterPlan | None:
    """Raccourci : ``None`` s'il n'y a aucun événement à exporter."""
    planner = PosterPlanner(events, registry, visible, time_range, family, max_label_lines)
    if planner.is_empty:
        return None
    return planner.plan(page_width_mm, page_height_mm, title, min_font_pt)


def _wrap_name(name: str, metrics: _Metrics) -> list[str]:
    width = NAME_COLUMN - 24
    lines = wrap_text(name, width, metrics.measurer)
    if len(lines) > NAME_MAX_LINES:
        lines = lines[:NAME_MAX_LINES]
        lines[-1] = elide(lines[-1] + " …", width, metrics.measurer)
    return lines


# --- dessin ------------------------------------------------------------------------------


def paint_poster(painter: QPainter, plan: PosterPlan, theme: PrintTheme = PRINT_THEME) -> None:
    """Dessine l'affiche. Le peintre doit déjà être en unités de conception."""
    layout = plan.layout
    font = QFont(plan.family)
    font.setPixelSize(round(FONT_PX))
    bold = QFont(font)
    bold.setBold(True)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(font)

    width, height = plan.content_width, plan.content_height
    painter.fillRect(QRectF(0, 0, width, height), theme.background)

    x_off = MARGIN + NAME_COLUMN - layout.x_min  # x de la scène pour x = 0 de la mise en page
    y_axis_top = MARGIN + plan.title_height
    y_lanes = y_axis_top + HEADER
    y_axis_bottom = y_lanes + layout.height
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
                    inner_left, y_lanes + lane.y - 7, inner_right - inner_left, lane.height + 14
                ),
                theme.band,
            )
    painter.setPen(QPen(theme.grid, 0.8, Qt.PenStyle.DotLine))
    for tick in layout.ticks:
        x = x_off + tick.x
        painter.drawLine(QPointF(x, y_lanes - 4), QPointF(x, y_axis_bottom + 4))

    # axes (haut et bas)
    for y, rule in ((y_axis_top, y_lanes), (y_axis_bottom, y_axis_bottom)):
        painter.setPen(QPen(theme.axis, 1.0))
        painter.drawLine(QPointF(inner_left, rule), QPointF(inner_right, rule))
        painter.setPen(theme.text)
        for tick in layout.ticks:
            x = x_off + tick.x
            painter.drawText(
                QRectF(x - 40, y, 80, HEADER), Qt.AlignmentFlag.AlignCenter, tick.label
            )

    # événements
    marker = plan.options.marker_size
    for lane in layout.lanes:
        for item in lane.items:
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
