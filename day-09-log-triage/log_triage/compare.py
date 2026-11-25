"""두 창 비교 — '고친 뒤'에 새로 생긴 것.

before(장애 전)/after(조치 후)든, 어제/오늘 배포 전후든, 두 파일의 같은 서명을
짝지어 **분당 비율**로 비교한다. 개수로 비교하면 긴 창이 늘 이겨서, 3시간 로그가
30분 로그보다 모든 항목이 '증가'로 보인다.

판정은 네 가지뿐이다: 새로 생김 / 사라짐 / 늘어남 / 줄어남.
그리고 '드물게 한 번'은 새로 생김과 구분한다 — 한 번 본 에러로 배포를 되돌리면
그게 더 큰 사고다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .signature import Cluster, by_signature, cluster
from .types import LogFile

STATUS_LABELS = {
    "new": "새로 생김",
    "new-rare": "새로 생김(드묾)",
    "gone": "사라짐",
    "gone-rare": "사라짐(드묾)",
    "grew": "늘어남",
    "shrank": "줄어남",
    "same": "그대로",
}

STATUS_ORDER = ["new", "grew", "new-rare", "gone", "shrank", "gone-rare", "same"]


@dataclass(slots=True)
class Row:
    signature: str
    template: str
    before_count: int
    after_count: int
    before_rate: float          # 분당
    after_rate: float
    status: str
    level: str = ""
    first_after: str = ""

    @property
    def ratio(self) -> float:
        if self.before_rate <= 0:
            return float("inf") if self.after_rate > 0 else 1.0
        return self.after_rate / self.before_rate

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


@dataclass(slots=True)
class Comparison:
    before_path: str
    after_path: str
    before_minutes: float
    after_minutes: float
    rows: list[Row] = field(default_factory=list)
    before_total: int = 0
    after_total: int = 0
    before_errors: int = 0
    after_errors: int = 0

    def with_status(self, *statuses: str) -> list[Row]:
        wanted = set(statuses)
        return [r for r in self.rows if r.status in wanted]

    @property
    def error_rate_change(self) -> float:
        before = self.before_errors / max(self.before_minutes, 1e-9)
        after = self.after_errors / max(self.after_minutes, 1e-9)
        if before <= 0:
            return float("inf") if after > 0 else 1.0
        return after / before


def _status(before: Cluster | None, after: Cluster | None, before_rate: float,
            after_rate: float, rare: int, grew_ratio: float) -> str:
    if before is None and after is not None:
        return "new-rare" if after.count < rare else "new"
    if after is None and before is not None:
        return "gone-rare" if before.count < rare else "gone"
    if before is None or after is None:
        return "same"
    if after_rate >= before_rate * grew_ratio and after.count >= rare:
        return "grew"
    if before_rate >= after_rate * grew_ratio and before.count >= rare:
        return "shrank"
    return "same"


def compare(before: LogFile, after: LogFile, rare: int = 3, grew_ratio: float = 2.0) -> Comparison:
    before_clusters = by_signature(cluster(before))
    after_clusters = by_signature(cluster(after))
    before_minutes = before.duration_minutes()
    after_minutes = after.duration_minutes()

    rows: list[Row] = []
    for sig in set(before_clusters) | set(after_clusters):
        b = before_clusters.get(sig)
        a = after_clusters.get(sig)
        b_rate = (b.count / before_minutes) if b else 0.0
        a_rate = (a.count / after_minutes) if a else 0.0
        status = _status(b, a, b_rate, a_rate, rare, grew_ratio)
        rows.append(Row(
            signature=sig,
            template=(a or b).template,
            before_count=b.count if b else 0,
            after_count=a.count if a else 0,
            before_rate=b_rate,
            after_rate=a_rate,
            status=status,
            level=(a or b).level,
            first_after=a.first_clock if a else "",
        ))

    order = {name: index for index, name in enumerate(STATUS_ORDER)}
    rows.sort(key=lambda r: (order.get(r.status, 99), -r.after_count, -r.before_count))

    return Comparison(
        before_path=before.path,
        after_path=after.path,
        before_minutes=before_minutes,
        after_minutes=after_minutes,
        rows=rows,
        before_total=len(before.records),
        after_total=len(after.records),
        before_errors=sum(1 for r in before.records if r.is_error),
        after_errors=sum(1 for r in after.records if r.is_error),
    )


def same_pair(before: LogFile, after: LogFile) -> bool:
    """같은 파일을 두 번 읽었을 때 비교가 조용히 '전부 그대로'가 되는지 확인용."""
    return before.fingerprint == after.fingerprint != ""
