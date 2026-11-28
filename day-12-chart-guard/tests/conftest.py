"""테스트 공용 — 스펙을 손으로 만들고, 실제 파일 없이 차트 사실을 만든다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chart_guard.normalize import normalize  # noqa: E402
from chart_guard.types import Axis, Chart, Series  # noqa: E402

REGIONS = ["서울", "부산", "인천", "대전", "대구", "광주"]
SALES = [1240, 1180, 1060, 810, 790, 660]


def guard(**overrides) -> dict:
    spec = {
        "type": "bar",
        "categories": list(REGIONS),
        "series": [{"name": "2026", "values": list(SALES)}],
        "y": {"min": 0, "title": "매출(억원)", "zero": True},
        "palette": ["#1f6fd0"],
        "title": "서울 1,240억으로 1위, 광주는 660억",
        "source": "테스트 데이터",
        "alt": "막대 차트. 서울 1,240억원이 가장 크고 광주 660억원이 가장 작다.",
    }
    spec.update(overrides)
    return spec


def chart(**overrides) -> Chart:
    return normalize(guard(**overrides))


def spec_file(tmp_path: Path, spec: dict, name: str = "chart.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def sales() -> Chart:
    return chart()


@pytest.fixture
def truncated() -> Chart:
    return chart(y={"min": 600, "title": "매출(억원)", "zero": False})


@pytest.fixture
def squeezed() -> Chart:
    """값이 거의 같은 두 막대 — 축을 자르면 4배로 보인다."""
    return chart(categories=["서울", "부산"], series=[{"name": "매출", "values": [52, 58]}], y={"min": 50, "title": "매출(억원)"})


@pytest.fixture
def clean() -> Chart:
    return normalize(
        {
            "type": "bar",
            "categories": ["A", "B", "C"],
            "series": [{"name": "값", "values": [30, 20, 10]}],
            "y": {"min": 0, "title": "개수(개)"},
            "title": "A가 가장 많다, C의 세 배",
            "source": "테스트",
            "alt": "막대 차트. A 30개, B 20개, C 10개.",
        }
    )


@pytest.fixture
def before_chart() -> Chart:
    return normalize((ROOT / "examples" / "before.json").read_text(encoding="utf-8"))


@pytest.fixture
def pie_before() -> Chart:
    return normalize((ROOT / "examples" / "pie-before.json").read_text(encoding="utf-8"))


@pytest.fixture
def empty_axis() -> Chart:
    return Chart(kind="bar", categories=[], series=[Series(values=[])], y=Axis(), x=Axis())
