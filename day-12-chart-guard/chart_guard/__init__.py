"""chart-guard — 차트를 올리기 전에, 축·형식·색·글이 숫자를 왜곡하는지 잰다.

    from chart_guard import normalize, check
    chart = normalize.normalize(open("chart.json").read())
    report = check.run(chart)
    print(report.score, report.verdict)
"""

from . import alttext, check, color, compare, fix, geometry, normalize, report, rules
from .types import Axis, Chart, Finding, Report, Series

__all__ = [
    "Axis",
    "Chart",
    "Finding",
    "Report",
    "Series",
    "alttext",
    "check",
    "color",
    "compare",
    "fix",
    "geometry",
    "normalize",
    "report",
    "rules",
]
__version__ = "0.1.0"
