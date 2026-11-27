"""화면 기하 — 겹침, 최소 이동, 상자 입력 검증."""

from __future__ import annotations

import json

import pytest

from conftest import make_media
from publish_guard.safearea import (
    CANVAS_1080,
    Box,
    BoxError,
    canvas_for,
    check_box,
    hide_ratio,
    inside,
    intersection,
    min_move,
    overlap_px,
    parse_boxes,
)
from publish_guard.types import Rect, Zone


class TestIntersection:
    def test_overlap(self):
        hit = intersection(Rect(0, 0, 100, 100), Rect(50, 50, 100, 100))
        assert hit == Rect(50, 50, 50, 50)

    def test_touching_edges_is_none(self):
        assert intersection(Rect(0, 0, 100, 100), Rect(100, 0, 100, 100)) is None

    def test_contained(self):
        assert intersection(Rect(10, 10, 20, 20), Rect(0, 0, 100, 100)) == Rect(10, 10, 20, 20)

    def test_disjoint(self):
        assert intersection(Rect(0, 0, 10, 10), Rect(50, 50, 10, 10)) is None

    def test_overlap_px(self):
        assert overlap_px(Rect(0, 0, 100, 100), Rect(50, 50, 100, 100)) == 2500
        assert overlap_px(Rect(0, 0, 10, 10), Rect(50, 50, 10, 10)) == 0


class TestInsideAndHide:
    def test_inside(self):
        assert inside(Rect(0, 0, 1080, 1920), CANVAS_1080) is True
        assert inside(Rect(1, 0, 1080, 1920), CANVAS_1080) is False
        assert inside(Rect(0, 0, 100, 100), CANVAS_1080) is True

    def test_hide_ratio_inside(self):
        assert hide_ratio(Rect(10, 10, 100, 100), CANVAS_1080) == 0

    def test_hide_ratio_half(self):
        assert hide_ratio(Rect(-50, 0, 100, 100), CANVAS_1080) == pytest.approx(0.5)

    def test_hide_ratio_outside(self):
        assert hide_ratio(Rect(2000, 0, 100, 100), CANVAS_1080) == 1.0


class TestMinMove:
    def test_move_down_from_top_zone(self):
        zone = Rect(0, 0, 1080, 384)
        box = Rect(0, 300, 900, 180)
        dx, dy, possible = min_move(box, zone, CANVAS_1080)
        assert possible is True
        assert (dx, dy) == (0, 84)

    def test_move_up_from_bottom_zone(self):
        zone = Rect(0, 1250, 1080, 670)
        box = Rect(0, 1200, 900, 180)
        dx, dy, possible = min_move(box, zone, CANVAS_1080)
        assert possible is True
        assert dy == -130  # 1250 - 1380

    def test_move_left_from_right_zone(self):
        zone = Rect(860, 900, 220, 1020)
        box = Rect(700, 1000, 300, 100)
        dx, dy, possible = min_move(box, zone, CANVAS_1080)
        assert possible is True
        assert dx == -140  # 860 - 1000

    def test_impossible_when_covering_canvas(self):
        _, _, possible = min_move(Rect(0, 0, 1080, 1920), Rect(0, 0, 1080, 1920), CANVAS_1080)
        assert possible is False

    def test_no_overlap_not_used(self):
        # 겹치지 않는 상자에도 함수는 답을 준다 — 호출 쪽이 겹칠 때만 부른다.
        dx, dy, possible = min_move(Rect(0, 500, 100, 100), Rect(0, 0, 1080, 384), CANVAS_1080)
        assert possible is True


def _box(x: int, y: int, w: int = 900, h: int = 180, label: str = "훅") -> Box:
    return Box(label=label, rect=Rect(x, y, w, h))


class TestCheckBox:
    def test_single_hit(self):
        hits = check_box(_box(0, 300), [Zone("상단", Rect(0, 0, 1080, 384), "house")], CANVAS_1080)
        assert len(hits) == 1
        assert hits[0].overlap == 900 * 84
        assert hits[0].dx == 0
        assert hits[0].dy == 84

    def test_multiple_zones(self):
        zones = [
            Zone("하단", Rect(0, 1250, 1080, 670), "house"),
            Zone("우측 버튼", Rect(860, 900, 220, 1020), "house"),
        ]
        hits = check_box(_box(800, 1200, 280, 200), zones, CANVAS_1080)
        assert {hit.zone.label for hit in hits} == {"하단", "우측 버튼"}

    def test_no_hits(self):
        assert check_box(_box(0, 500), [Zone("상단", Rect(0, 0, 1080, 384), "house")], CANVAS_1080) == []

    def test_area_ratio(self):
        box = _box(0, 300, 900, 100)
        hits = check_box(box, [Zone("상단", Rect(0, 0, 1080, 384), "house")], CANVAS_1080)
        assert hits[0].area_ratio == pytest.approx(84 / 100)

    def test_active_at(self):
        box = Box("자막", Rect(0, 500, 100, 100), t_start=2.0, t_end=4.0)
        assert box.active_at(None) is True
        assert box.active_at(3.0) is True
        assert box.active_at(1.0) is False
        assert box.active_at(5.0) is False


class TestParseBoxes:
    def test_empty(self):
        assert parse_boxes(None) == []
        assert parse_boxes("") == []
        assert parse_boxes([]) == []

    def test_list(self):
        boxes = parse_boxes([{"label": "훅", "x": 0, "y": 430, "w": 900, "h": 180}])
        assert boxes[0].label == "훅"
        assert boxes[0].rect == Rect(0, 430, 900, 180)

    def test_wrapped_dict(self):
        boxes = parse_boxes({"boxes": [{"x": 1, "y": 2, "w": 3, "h": 4}]})
        assert boxes[0].label == "상자1"

    def test_json_string(self):
        payload = json.dumps([{"name": "자막", "x": 10, "y": 20, "w": 30, "h": 40}])
        boxes = parse_boxes(payload)
        assert boxes[0].label == "자막"

    def test_timing(self):
        boxes = parse_boxes([{"x": 0, "y": 0, "w": 10, "h": 10, "t_start": 1, "t_end": 2.5}])
        assert boxes[0].t_start == 1.0
        assert boxes[0].t_end == 2.5

    def test_missing_field(self):
        with pytest.raises(BoxError, match="x"):
            parse_boxes([{"y": 0, "w": 10, "h": 10}])

    def test_float_pixel_rejected(self):
        with pytest.raises(BoxError, match="정수"):
            parse_boxes([{"x": 1.5, "y": 0, "w": 10, "h": 10}])

    def test_bool_rejected(self):
        with pytest.raises(BoxError):
            parse_boxes([{"x": True, "y": 0, "w": 10, "h": 10}])

    def test_non_numeric_rejected(self):
        with pytest.raises(BoxError):
            parse_boxes([{"x": "0", "y": 0, "w": 10, "h": 10}])

    def test_zero_size_rejected(self):
        with pytest.raises(BoxError, match="0 이하"):
            parse_boxes([{"x": 0, "y": 0, "w": 0, "h": 10}])

    def test_bad_json(self):
        with pytest.raises(BoxError, match="JSON"):
            parse_boxes("{not json")

    def test_non_list(self):
        with pytest.raises(BoxError, match="리스트"):
            parse_boxes({"boxes": "nope"})

    def test_non_object_item(self):
        with pytest.raises(BoxError, match="객체"):
            parse_boxes(["nope"])


class TestCanvas:
    def test_from_media(self):
        assert canvas_for(make_media(width=720, height=1280)) == (720, 1280)

    def test_default(self):
        assert canvas_for(None) == CANVAS_1080
        assert canvas_for(make_media(width=0, height=0)) == CANVAS_1080
