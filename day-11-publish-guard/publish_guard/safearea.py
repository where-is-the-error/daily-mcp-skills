"""Safe Zone 기하 — 선언된 문구 상자가 UI 덮개에 걸리는지, 걸리면 몇 px 옮기면 되는지.

상자 좌표는 편집 파이프라인이 선언한 값이다. 이 모듈은 픽셀을 읽지 않는다 —
영상 안에 구워진 글자를 찾아내지 못한다는 한계가 여기서 시작한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .types import Rect, Zone

CANVAS_1080 = (1080, 1920)


class BoxError(ValueError):
    pass


@dataclass(frozen=True)
class Box:
    label: str
    rect: Rect
    t_start: float | None = None
    t_end: float | None = None

    def active_at(self, t: float | None) -> bool:
        if t is None:
            return True
        if self.t_start is not None and t < self.t_start:
            return False
        if self.t_end is not None and t > self.t_end:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"label": self.label, **self.rect.to_dict()}
        if self.t_start is not None:
            data["t_start"] = self.t_start
        if self.t_end is not None:
            data["t_end"] = self.t_end
        return data


@dataclass(frozen=True)
class BoxHit:
    box: Box
    zone: Zone
    overlap: int
    dx: int
    dy: int
    possible: bool

    @property
    def area_ratio(self) -> float:
        return self.overlap / self.box.rect.area if self.box.rect.area else 0.0


def intersection(a: Rect, b: Rect) -> Rect | None:
    x0 = max(a.x, b.x)
    y0 = max(a.y, b.y)
    x1 = min(a.right, b.right)
    y1 = min(a.bottom, b.bottom)
    if x1 <= x0 or y1 <= y0:
        return None
    return Rect(x0, y0, x1 - x0, y1 - y0)


def overlap_px(a: Rect, b: Rect) -> int:
    hit = intersection(a, b)
    return hit.area if hit else 0


def inside(rect: Rect, canvas: tuple[int, int]) -> bool:
    width, height = canvas
    return rect.x >= 0 and rect.y >= 0 and rect.right <= width and rect.bottom <= height


def hide_ratio(rect: Rect, canvas: tuple[int, int]) -> float:
    """상자가 화면 밖으로 나간 넓이의 비율."""
    width, height = canvas
    visible = intersection(rect, Rect(0, 0, width, height))
    if rect.area == 0:
        return 1.0
    return 1.0 - (visible.area / rect.area if visible else 0.0)


def min_move(box: Rect, zone: Rect, canvas: tuple[int, int]) -> tuple[int, int, bool]:
    """덮개를 완전히 벗어나는 가장 짧은 이동 (dx, dy) 와 가능 여부.

    네 방향만 본다. 대각선 이동은 두 축을 함께 움직이므로 최소가 아니다.
    """
    width, height = canvas
    candidates: list[tuple[int, int]] = [
        (zone.x - box.right, 0),      # 왼쪽
        (zone.right - box.x, 0),      # 오른쪽
        (0, zone.y - box.bottom),     # 위
        (0, zone.bottom - box.y),     # 아래
    ]
    best: tuple[int, int] | None = None
    for dx, dy in candidates:
        moved = Rect(box.x + dx, box.y + dy, box.w, box.h)
        if not inside(moved, (width, height)):
            continue
        if overlap_px(moved, zone) != 0:
            continue
        distance = abs(dx) + abs(dy)
        if best is None or distance < abs(best[0]) + abs(best[1]):
            best = (dx, dy)
    if best is None:
        return 0, 0, False
    return best[0], best[1], True


def check_box(box: Box, zones: list[Zone], canvas: tuple[int, int]) -> list[BoxHit]:
    hits = []
    for zone in zones:
        overlap = overlap_px(box.rect, zone.rect)
        if overlap == 0:
            continue
        dx, dy, possible = min_move(box.rect, zone.rect, canvas)
        hits.append(BoxHit(box=box, zone=zone, overlap=overlap, dx=dx, dy=dy, possible=possible))
    return hits


# ---------------------------------------------------------------- 입력

def _require_int(data: dict[str, Any], key: str, label: str) -> int:
    if key not in data:
        raise BoxError(f"상자 '{label}' 에 {key} 가 없습니다")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BoxError(f"상자 '{label}' 의 {key} 는 숫자여야 합니다: {value!r}")
    if float(value) != int(value):
        raise BoxError(f"상자 '{label}' 의 {key} 는 정수 픽셀이어야 합니다: {value!r}")
    return int(value)


def parse_boxes(payload: str | list[dict[str, Any]] | dict[str, Any] | None) -> list[Box]:
    """JSON 문자열·리스트·딕셔너리를 상자 목록으로. 빈 값이면 빈 목록."""
    if payload in (None, "", []):
        return []
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise BoxError(f"상자 JSON 을 읽지 못했습니다: {exc}") from exc
    else:
        data = payload

    if isinstance(data, dict):
        data = data.get("boxes", [])
    if not isinstance(data, list):
        raise BoxError("상자는 리스트이거나 {'boxes': [...]} 여야 합니다")

    boxes: list[Box] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise BoxError(f"{index}번째 상자가 객체가 아닙니다")
        label = str(item.get("label") or item.get("name") or f"상자{index}")
        rect = Rect(
            x=_require_int(item, "x", label),
            y=_require_int(item, "y", label),
            w=_require_int(item, "w", label),
            h=_require_int(item, "h", label),
        )
        if rect.w <= 0 or rect.h <= 0:
            raise BoxError(f"상자 '{label}' 의 크기가 0 이하입니다: {rect.w}x{rect.h}")
        t_start = item.get("t_start")
        t_end = item.get("t_end")
        boxes.append(
            Box(
                label=label,
                rect=rect,
                t_start=float(t_start) if t_start is not None else None,
                t_end=float(t_end) if t_end is not None else None,
            )
        )
    return boxes


def canvas_for(media: Any | None) -> tuple[int, int]:
    if media is not None and getattr(media, "width", 0) and getattr(media, "height", 0):
        return int(media.width), int(media.height)
    return CANVAS_1080
