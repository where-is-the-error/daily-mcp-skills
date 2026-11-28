#!/usr/bin/env python3
"""렌더 교차 검증 — 우리 계산과 실제 픽셀을 맞대어 본다.

    python3 tools/render_check.py

차트를 matplotlib 으로 실제로 그리고(PNG), 막대의 높이를 **이미지 픽셀에서 재어**,
chart_guard 의 기하 모델(축 하한이 만드는 화면 비율)과 비교한다.
모델이 맞다면 두 값의 차이는 1% 안이어야 한다.

matplotlib 은 이 검증에만 쓴다 — 도구의 의존성은 아니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chart_guard import geometry, normalize  # noqa: E402

OUT = Path(__file__).resolve().parent / "render-result.json"
TMP = Path("/tmp") / "chart-guard-render"
BAR = (214, 39, 40)  # #d62728


def make_chart(min_y: float, values: list[float]) -> dict:
    return {
        "type": "bar",
        "categories": [f"C{i}" for i in range(len(values))],
        "series": [{"name": "값", "values": values}],
        "y": {"min": min_y, "title": "값(개)"},
        "palette": ["#d62728"],
        "title": "렌더 검증",
        "source": "tools/render_check.py",
        "alt": "막대 차트.",
    }


def render(spec: dict, name: str) -> tuple[Path, dict]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    TMP.mkdir(parents=True, exist_ok=True)
    path = TMP / f"{name}.png"
    values = spec["series"][0]["values"]
    labels = spec["categories"]
    lo = spec["y"]["min"]
    hi = max(values) * 1.05

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    bars = ax.bar(range(len(values)), values, color="#d62728", width=0.8, bottom=0)
    ax.set_ylim(lo, hi)
    ax.set_xlim(-0.5, len(values) - 0.5)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels)
    ax.grid(False)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    centers = [ax.transData.transform((i, values[i])) for i in range(len(values))]
    tops = [int(round(centers[i][1])) for i in range(len(values))]
    bottoms = [int(round(ax.transData.transform((i, lo))[1])) for i in range(len(values))]
    xs = [int(round(centers[i][0])) for i in range(len(values))]
    plt.close(fig)
    return path, {"xs": xs, "tops": tops, "bottoms": bottoms}


def measure_pixels(path: Path, geom: dict) -> list[int]:
    """이미지에서 막대 높이를 직접 잰다 — 위쪽에서 내려오며 막대 색이 처음 나오는 행."""
    from PIL import Image

    image = Image.open(path).convert("RGB")
    width, height = image.size
    heights = []
    for x, bottom in zip(geom["xs"], geom["bottoms"]):
        column_top = None
        x = min(max(x, 0), width - 1)
        for y in range(height):
            pixel = image.getpixel((x, y))
            if sum(abs(pixel[i] - BAR[i]) for i in range(3)) < 60:
                column_top = y
                break
        if column_top is None:
            heights.append(0)
        else:
            y_bottom = height - 1 - bottom  # matplotlib 좌표는 아래가 0
            heights.append(max(0, int(y_bottom) - column_top))
    return heights


def check_one(name: str, spec: dict) -> dict:
    chart = normalize.normalize(spec)
    info = geometry.exaggeration(chart)
    path, geom = render(spec, name)
    heights = measure_pixels(path, geom)
    values = spec["series"][0]["values"]
    low_index = values.index(min(values))
    high_index = values.index(max(values))
    measured = heights[high_index] / heights[low_index] if heights[low_index] else float("inf")
    predicted = info["drawn_ratio"]
    error = abs(measured - predicted) / predicted * 100
    # 픽셀은 1px 단위로만 읽히므로, 짧은 막대에서 1px 은 그만큼 큰 비율 오차다
    quantum = 100 * (2.0 / max(1, min(heights))) + 0.5
    return {
        "name": name,
        "y_min": spec["y"]["min"],
        "values": values,
        "predicted_ratio": round(predicted, 4),
        "measured_ratio": round(measured, 4),
        "error_pct": round(error, 2),
        "tolerance_pct": round(quantum, 2),
        "pixels": heights,
        "model_pixels": [round(info["pixel_low"], 1), round(info["pixel_high"], 1)],
    }


def main() -> int:
    cases = {
        "truncated-20": make_chart(20, [25, 45]),
        "truncated-1150": make_chart(1150, [1180, 1240]),
        "zero-baseline": make_chart(0, [25, 45]),
    }
    results = [check_one(name, spec) for name, spec in cases.items()]
    for item in results:
        print(
            f"{item['name']:16s} 하한 {item['y_min']:>6} · 예측 {item['predicted_ratio']:.4f}배"
            f" · 픽셀 {item['measured_ratio']:.4f}배 · 오차 {item['error_pct']:.2f}%"
            f" (허용 {item['tolerance_pct']:.2f}%) · 높이 {item['pixels']}px"
            f" (모델은 1080px 기준 {item['model_pixels']}px)"
        )
    worst = max(item["error_pct"] for item in results)
    allowed = all(item["error_pct"] <= item["tolerance_pct"] for item in results)
    print(f"최대 오차 {worst:.2f}% — 허용치는 1px 양자화에서 오는 몫이다.")
    print("판정: " + ("같은 비율을 말한다" if allowed else "어긋난다 — 모델을 확인하세요"))
    OUT.write_text(
        json.dumps({"cases": results, "max_error_pct": worst, "passed": allowed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(OUT)
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
