"""작업 기억 — 한 프로세스 안에서만. 파일로 남기지 않고, 아무것도 밖으로 보내지 않는다."""

from __future__ import annotations

from .types import CaptionFacts, MediaFacts, Report


class Store:
    def __init__(self) -> None:
        self._media: dict[str, MediaFacts] = {}
        self._captions: dict[str, CaptionFacts] = {}
        self._reports: dict[str, Report] = {}
        self._counters = {"m": 0, "c": 0, "r": 0}

    def _next(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]}"

    def add_media(self, facts: MediaFacts) -> str:
        ref = self._next("m")
        self._media[ref] = facts
        return ref

    def add_caption(self, facts: CaptionFacts) -> str:
        ref = self._next("c")
        self._captions[ref] = facts
        return ref

    def add_report(self, report: Report) -> str:
        ref = self._next("r")
        report.ref = ref
        self._reports[ref] = report
        return ref

    def media(self, ref: str) -> MediaFacts:
        if ref not in self._media:
            raise KeyError(f"미디어 ref 가 없습니다: {ref} (read_media 로 먼저 읽으세요)")
        return self._media[ref]

    def caption(self, ref: str) -> CaptionFacts:
        if ref not in self._captions:
            raise KeyError(f"캡션 ref 가 없습니다: {ref} (read_caption 으로 먼저 읽으세요)")
        return self._captions[ref]

    def report(self, ref: str) -> Report:
        if ref not in self._reports:
            raise KeyError(f"보고서 ref 가 없습니다: {ref} (publish_check 로 먼저 검사하세요)")
        return self._reports[ref]

    def clear(self) -> None:
        self._media.clear()
        self._captions.clear()
        self._reports.clear()
        self._counters = {"m": 0, "c": 0, "r": 0}

    def counts(self) -> dict[str, int]:
        return {
            "media": len(self._media),
            "captions": len(self._captions),
            "reports": len(self._reports),
        }


STORE = Store()
