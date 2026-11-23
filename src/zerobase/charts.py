"""Geometry for the server-drawn SVG charts (TASK-M003).

Plain numbers only: the template draws the marks and CSS classes colour them, since the CSP
allows no inline styles or scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HEIGHT = 260
LEFT, RIGHT, TOP, BOTTOM = 64, 12, 12, 28
MIN_WIDTH = 720
MIN_SLOT = 26  # per month; a long range makes the chart wider, and it scrolls
MAX_BAR = 24
GAP = 2


@dataclass
class Bar:
    x: float
    y: float
    width: float
    height: float
    series: str
    title: str


@dataclass
class Chart:
    width: float
    height: float
    ticks: list[tuple[float, int]]  # y, value in pence
    labels: list[tuple[float, str]]  # x, text
    baseline: float
    bars: list[Bar] = field(default_factory=list)
    line: list[tuple[float, float, str]] = field(default_factory=list)  # x, y, title
    left: int = LEFT
    right: int = RIGHT

    @property
    def points(self) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in self.line)


def tick_step(span: int, wanted: int = 4) -> int:
    """A round number of pence (1, 2 or 5 times a power of ten) giving about that many ticks."""
    raw = max(1, span / wanted)
    power = 10 ** (len(str(int(raw))) - 1)
    return next(int(m * power) for m in (1, 2, 5, 10) if m * power >= raw)


def _frame(labels: list[str], low: int, high: int):
    width = max(MIN_WIDTH, LEFT + RIGHT + MIN_SLOT * len(labels))
    low, high = min(0, low), max(0, high)
    step = tick_step(max(high - low, 100))
    bottom, top = low // step * step, -(-high // step) * step
    if top == bottom:
        top = step
    scale = (HEIGHT - TOP - BOTTOM) / (top - bottom)

    def y(value: int) -> float:
        return HEIGHT - BOTTOM - (value - bottom) * scale

    slot = (width - LEFT - RIGHT) / len(labels)
    centres = [LEFT + slot * (i + 0.5) for i in range(len(labels))]
    every = -(-56 // int(slot)) if slot < 56 else 1  # don't let month names collide
    chart = Chart(
        width=width,
        height=HEIGHT,
        ticks=[(y(v), v) for v in range(bottom, top + 1, step)],
        labels=[(centres[i], labels[i]) for i in range(0, len(labels), every)],
        baseline=y(0),
    )
    return chart, y, slot, centres


def grouped(labels: list[str], series: dict[str, list[int]], names, money) -> Chart:
    """Side-by-side bars, one per series, in each month."""
    values = [v for amounts in series.values() for v in amounts]
    chart, y, slot, centres = _frame(labels, min(values), max(values))
    width = min(MAX_BAR, (slot - 6) / len(series) - GAP)
    whole = len(series) * width + (len(series) - 1) * GAP
    for i, label in enumerate(labels):
        for n, (key, amounts) in enumerate(series.items()):
            value = amounts[i]
            if not value:
                continue
            top = min(y(value), y(0))
            chart.bars.append(
                Bar(
                    centres[i] - whole / 2 + n * (width + GAP),
                    top,
                    width,
                    abs(y(value) - y(0)),
                    key,
                    f"{label}: {names[key]} {money(value)}",
                )
            )
    return chart


def stacked(
    labels: list[str], series: dict[str, list[int]], total: list[int], names, money
) -> Chart:
    """Positive values stacked up from zero and negative ones down, with a line for the total."""
    highs = [sum(max(0, a[i]) for a in series.values()) for i in range(len(labels))]
    lows = [sum(min(0, a[i]) for a in series.values()) for i in range(len(labels))]
    chart, y, slot, centres = _frame(labels, min(lows), max(highs))
    width = min(MAX_BAR, slot - 6)
    for i, label in enumerate(labels):
        up = down = 0
        for key, amounts in series.items():
            value = amounts[i]
            if not value:
                continue
            base = up if value > 0 else down
            top = min(y(base), y(base + value))
            height = abs(y(base + value) - y(base))
            chart.bars.append(
                Bar(
                    centres[i] - width / 2,
                    top,
                    width,
                    max(0.5, height - GAP),
                    key,
                    f"{label}: {names[key]} {money(value)}",
                )
            )
            if value > 0:
                up += value
            else:
                down += value
        chart.line.append((centres[i], y(total[i]), f"{label}: net worth {money(total[i])}"))
    return chart


@dataclass
class Row:
    name: str
    value: int
    y: float
    width: float


ROW_HEIGHT, ROW_LEFT, ROW_WIDTH, ROW_VALUE, MAX_ROWS = 28, 190, 400, 120, 12


@dataclass
class RowChart:
    rows: list[Row]
    height: int
    width: int = ROW_LEFT + ROW_WIDTH + ROW_VALUE
    left: int = ROW_LEFT


def ranked(items: list[tuple[str, int]]) -> RowChart:
    """Horizontal bars, largest first; the smallest are folded together past MAX_ROWS.

    Only positive amounts are drawn: a category with more refunds than spending is in the table.
    """
    items = sorted((i for i in items if i[1] > 0), key=lambda item: -item[1])
    if len(items) > MAX_ROWS:
        rest = items[MAX_ROWS - 1 :]
        items = items[: MAX_ROWS - 1]
        items.append((f"{len(rest)} smaller categories", sum(v for _, v in rest)))
    top = max((v for _, v in items), default=1)
    rows = [
        Row(
            name if len(name) <= 26 else f"{name[:25]}…",
            value,
            i * ROW_HEIGHT,
            max(1, ROW_WIDTH * value / top),
        )
        for i, (name, value) in enumerate(items)
    ]
    return RowChart(rows, len(rows) * ROW_HEIGHT)
