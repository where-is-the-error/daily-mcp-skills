"""작업 기억 — 한 프로세스 안에서만. 파일로 남기지 않고 밖으로 보내지 않는다."""

from __future__ import annotations

from .types import Chart, Report


class Store:
    def __init__(self) -> None:
        self._charts: dict[str, Chart] = {}
        self._reports: dict[str, Report] = {}
        self._counters = {"c": 0, "r": 0}

    def _next(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]}"

    def add_chart(self, chart: Chart) -> str:
        ref = self._next("c")
        self._charts[ref] = chart
        return ref

    def add_report(self, report: Report) -> str:
        ref = self._next("r")
        report.ref = ref
        self._reports[ref] = report
        return ref

    def chart(self, ref: str) -> Chart:
        if ref not in self._charts:
            raise KeyError(f"차트 ref 가 없습니다: {ref} (read_chart 로 먼저 읽으세요)")
        return self._charts[ref]

    def report(self, ref: str) -> Report:
        if ref not in self._reports:
            raise KeyError(f"보고서 ref 가 없습니다: {ref} (chart_check 로 먼저 검사하세요)")
        return self._reports[ref]

    def clear(self) -> None:
        self._charts.clear()
        self._reports.clear()
        self._counters = {"c": 0, "r": 0}

    def counts(self) -> dict[str, int]:
        return {"charts": len(self._charts), "reports": len(self._reports)}


STORE = Store()
