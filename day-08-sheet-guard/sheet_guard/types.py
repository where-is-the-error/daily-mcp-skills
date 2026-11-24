"""칸 하나의 값 종류, 칸 하나의 통계.

표를 읽을 때 가장 많이 하는 실수는 **보이는 글자를 값으로 착각하는 것**이다.
`00123`은 숫자 123이 아니라 우편번호일 수 있고, `1,234`는 숫자 1234지만 그대로 두면
엑셀에서 글자로 남는다. 여기서는 원문(raw)을 버리지 않고 종류(kind)만 판정한다.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

PAD_CHARS = "\u00a0\u200b\u200c\u200d\ufeff\u3000"      # NBSP, 제로폭, 전각 공백
FULLWIDTH = {chr(0xFF10 + i): str(i) for i in range(10)}
FULLWIDTH.update({"\uff0e": ".", "\uff0c": ",", "\uff0b": "+", "\uff0d": "-", "\uff05": "%",
                  "\uff08": "(", "\uff09": ")"})

KINDS = ("empty", "int", "float", "code", "date", "datetime", "percent", "currency",
         "quantity", "phone", "bool", "text")

KIND_LABELS = {
    "empty": "빈칸", "int": "정수", "float": "실수", "code": "코드(앞자리 0 유지)",
    "date": "날짜", "datetime": "날짜시각", "percent": "백분율", "currency": "금액",
    "quantity": "수량+단위", "phone": "전화번호", "bool": "참/거짓", "text": "글자",
}

UNITS = ("㎡", "m²", "m2", "㎢", "평", "kg", "g", "km", "cm", "mm", "GB", "MB", "TB", "시간",
         "분", "초", "개", "명", "건", "세", "도", "℃", "원", "천원", "만원", "억원", "달러", "USD")

_DATE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("YYYY-MM-DD", re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")),
    ("YYYY.MM.DD", re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})\.?$")),
    ("YYYY/MM/DD", re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")),
    ("YYYY년M월D일", re.compile(r"^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일$")),
    ("YY.MM.DD", re.compile(r"^(\d{2})\.(\d{1,2})\.(\d{1,2})\.?$")),
    ("YY-MM-DD", re.compile(r"^(\d{2})-(\d{1,2})-(\d{1,2})$")),
    ("YY/MM/DD", re.compile(r"^(\d{2})/(\d{1,2})/(\d{1,2})$")),
    ("YYYYMMDD", re.compile(r"^(\d{4})(\d{2})(\d{2})$")),
)

_MONTH_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("YYYY-MM", re.compile(r"^(\d{4})-(\d{1,2})$")),
    ("YYYY.MM", re.compile(r"^(\d{4})\.(\d{1,2})$")),
    ("YYYY년M월", re.compile(r"^(\d{4})\s*년\s*(\d{1,2})\s*월$")),
    ("YYYYMM", re.compile(r"^(\d{4})(\d{2})$")),
)

_TIME_TAIL = re.compile(r"^(.+?)[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")

_PHONE = re.compile(r"^\+?82[-\s]?\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}$|^0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}$"
                    r"|^0\d{8,10}$")
_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?\d+\.\d+$|^[+-]?\.\d+$")
_PERCENT = re.compile(r"^[+-]?\d{1,3}(,\d{3})*(\.\d+)?\s*%$")
_CURRENCY = re.compile(r"^[₩$¥]\s?[+-]?\d{1,3}(,\d{3})*(\.\d+)?$|^[+-]?\d{1,3}(,\d{3})*(\.\d+)?\s*(원|천원|만원|억원|달러|USD)$")
_ACCOUNTING = re.compile(r"^\([+-]?\d{1,3}(,\d{3})*(\.\d+)?\)$")
_QUANTITY = re.compile(r"^[+-]?\d{1,3}(,\d{3})*(\.\d+)?\s*(%s)$" % "|".join(re.escape(u) for u in UNITS))
_BOOL = re.compile(r"^(Y|N|YES|NO|TRUE|FALSE|예|아니오|아니요|참|거짓)$", re.IGNORECASE)

HEADER_HINTS = {
    "code": ("코드", "번호", "우편", "사업자", "법인", "계좌", "관리번", "접수", "고객", "code", "no.", "id"),
    "phone": ("전화", "휴대", "연락", "핸드폰", "tel", "phone", "mobile"),
    "date": ("일자", "날짜", "일시", "기간", "기준일", "작성일", "등록일", "date", "time", "년월", "월"),
    "money": ("금액", "가격", "비용", "요금", "매출", "예산", "단가", "price", "amount", "cost"),
    "percent": ("비율", "비중", "률", "율", "%", "percent", "rate"),
    "quantity": ("면적", "수량", "중량", "용량", "면적", "size", "qty"),
    "id": ("id", "키", "key", "순번", "연번"),
}


@dataclass(frozen=True)
class Value:
    kind: str
    raw: str
    value: object | None = None
    note: str = ""
    flags: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.kind == "empty"

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


def strip_pad(raw: str) -> tuple[str, bool]:
    """앞뒤 공백·NBSP·제로폭 문자·전각 공백을 제거하고, 제거했는지 알려준다."""
    stripped = raw.strip()
    changed = stripped != raw
    trimmed = stripped.strip(PAD_CHARS)
    if trimmed != stripped:
        changed = True
        stripped = trimmed
    inner = raw.strip()
    # 값 중간에 섞인 제로폭 문자도 흔한 오염이다.
    if any(ch in inner for ch in "\u200b\u200c\u200d\ufeff"):
        cleaned = inner
        for ch in "\u200b\u200c\u200d\ufeff":
            cleaned = cleaned.replace(ch, "")
        stripped = cleaned.strip(PAD_CHARS)
        changed = True
    return stripped, changed


def to_ascii(text: str) -> tuple[str, bool]:
    if not any(ch in FULLWIDTH for ch in text):
        return text, False
    return "".join(FULLWIDTH.get(ch, ch) for ch in text), True


def header_hint(name: str) -> tuple[str, ...]:
    """열 이름에서 값의 성격을 짐작한다. 영문 약어(id, no.)는 단어 경계로만 본다.

    'SIDO_NM' 안의 'id'를 식별자로 읽으면 멀쩡한 인구 열에 앞자리 0 경고가 붙는다.
    """
    low = name.lower()
    found = []
    for kind, words in HEADER_HINTS.items():
        for word in words:
            if word.isascii():
                if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", low):
                    found.append(kind)
                    break
            elif word in low:
                found.append(kind)
                break
    return tuple(found)


MIN_YEAR, MAX_YEAR = 1900, 2100


def _plausible(y: int) -> bool:
    """125001 같은 6자리 숫자를 '1250년 1월'로 읽지 않기 위한 창."""
    return MIN_YEAR <= y <= MAX_YEAR


def _make_date(y: int, m: int, d: int, pattern: str, raw: str) -> Value | None:
    if y < 100:
        y += 2000
    if not _plausible(y):
        return None
    try:
        date = _dt.date(y, m, d)
    except ValueError:
        return Value("text", raw, raw, note="날짜 모양이지만 달력에 없는 날", flags=("invalid_date",))
    return Value("date", raw, date, note=pattern)


def _make_month(y: int, m: int, pattern: str, raw: str) -> Value | None:
    if not 1 <= m <= 12 or not _plausible(y):
        return None
    return Value("date", raw, _dt.date(y, m, 1), note=pattern + "(월 단위)", flags=("month_only",))


def parse_value(raw: str) -> Value:
    """칸 하나를 읽는다. 원문은 언제나 살아 있고, kind만 판정한다."""
    if raw is None:
        return Value("empty", "")
    original = raw
    text, had_pad = strip_pad(raw)
    if text == "":
        return Value("empty", original, None, flags=("pad",) if had_pad else ())

    text, had_fullwidth = to_ascii(text)
    flags: list[str] = []
    if had_pad:
        flags.append("pad")
    if had_fullwidth:
        flags.append("fullwidth")

    if _BOOL.match(text):
        truthy = text.upper() in ("Y", "YES", "TRUE", "예", "참")
        return Value("bool", original, truthy, flags=tuple(flags))

    # 회계식 음수 (1,234)
    accounting = _ACCOUNTING.match(text)
    if accounting:
        digits = text[1:-1]
        number = float(digits.replace(",", "")) * -1
        kind = "int" if "." not in digits else "float"
        return Value(kind, original, int(number) if kind == "int" else number,
                     note="괄호 음수", flags=tuple(flags + ["accounting"]))

    # 날짜/시각 — 시각 꼬리를 떼고 날짜 부분을 먼저 본다
    tail = _TIME_TAIL.match(text)
    head = tail.group(1) if tail else text
    for pattern, regex in _DATE_PATTERNS:
        m = regex.match(head)
        if m:
            value = _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), pattern, original)
            if value is None:
                continue
            if tail:
                hh, mm = int(tail.group(2)), int(tail.group(3))
                ss = int(tail.group(4) or 0)
                if hh > 23 or mm > 59 or ss > 59:
                    return Value("text", original, original, note="시각 범위를 벗어남", flags=tuple(flags))
                if isinstance(value.value, _dt.date):
                    return Value("datetime", original,
                                 _dt.datetime(value.value.year, value.value.month, value.value.day, hh, mm, ss),
                                 note=value.note + " HH:MM", flags=tuple(flags))
            return Value(value.kind, original, value.value, note=value.note,
                         flags=tuple(flags + list(value.flags)))
    for pattern, regex in _MONTH_PATTERNS:
        m = regex.match(head)
        if m and not tail:
            value = _make_month(int(m.group(1)), int(m.group(2)), pattern, original)
            if value:
                return Value(value.kind, original, value.value, note=value.note,
                             flags=tuple(flags + list(value.flags)))

    # 전화번호 — 숫자/구분자만 있고 9~13자리
    if _PHONE.match(text) and sum(ch.isdigit() for ch in text) >= 9:
        digits = "".join(ch for ch in text if ch.isdigit())
        return Value("phone", original, digits, note="+82" if text.startswith("+82") else "",
                     flags=tuple(flags))

    if _PERCENT.match(text):
        number = float(text.replace("%", "").replace(",", "").strip())
        return Value("percent", original, number, note="%", flags=tuple(flags + ["unit_in_cell"]))
    if _CURRENCY.match(text):
        number = re.sub(r"[^\d.\-]", "", text)
        unit = "".join(ch for ch in text if not (ch.isdigit() or ch in ".,-+ "))
        try:
            return Value("currency", original, float(number) if "." in number else int(number),
                         note=unit, flags=tuple(flags + ["unit_in_cell"]))
        except ValueError:
            pass
    if _QUANTITY.match(text):
        m = re.match(r"^([+-]?\d{1,3}(,\d{3})*(\.\d+)?)\s*(.+)$", text)
        if m:
            number_text = m.group(1).replace(",", "")
            unit = m.group(4).strip()
            number: float | int = float(number_text) if "." in number_text else int(number_text)
            return Value("quantity", original, number, note=unit,
                         flags=tuple(flags + ["unit_in_cell"]))

    # 앞자리 0 — 숫자로 바꾸면 사라지는 값
    if re.match(r"^0\d+$", text):
        return Value("code", original, text, note=f"{len(text)}자리",
                     flags=tuple(flags + ["leading_zero"]))
    if re.match(r"^[+-]?0\d+$", text):
        return Value("code", original, text, note=f"{len(text)}자리",
                     flags=tuple(flags + ["leading_zero"]))

    thousands = bool(_THOUSANDS.match(text))
    if thousands:
        digits = text.replace(",", "")
        if _FLOAT.match(digits):
            return Value("float", original, float(digits), note="천 단위 쉼표",
                         flags=tuple(flags + ["thousands"]))
        if _INT.match(digits):
            return Value("int", original, int(digits), note="천 단위 쉼표",
                         flags=tuple(flags + ["thousands"]))
    if _INT.match(text):
        return Value("int", original, int(text), flags=tuple(flags))
    if _FLOAT.match(text):
        return Value("float", original, float(text), flags=tuple(flags))
    if re.match(r"^\d+(\.\d+)?[eE][+-]?\d+$", text):
        return Value("float", original, float(text), note="지수 표기", flags=tuple(flags))

    return Value("text", original, text, flags=tuple(flags))


@dataclass
class ColumnStats:
    """칸 통계 — 칸 종류별 개수와, 규칙이 쓰는 관찰값만 모은다."""
    index: int
    name: str
    kinds: dict[str, int] = field(default_factory=dict)
    flags: dict[str, int] = field(default_factory=dict)
    date_patterns: dict[str, int] = field(default_factory=dict)
    units: dict[str, int] = field(default_factory=dict)
    widths: dict[int, int] = field(default_factory=dict)
    examples: dict[str, str] = field(default_factory=dict)      # kind -> 첫 예
    non_empty: int = 0
    total: int = 0
    numbers: list[float] = field(default_factory=list)
    distinct: set[str] = field(default_factory=set)

    def add(self, value: Value) -> None:
        self.total += 1
        self.kinds[value.kind] = self.kinds.get(value.kind, 0) + 1
        for flag in value.flags:
            self.flags[flag] = self.flags.get(flag, 0) + 1
        if value.is_empty:
            return
        self.non_empty += 1
        self.examples.setdefault(value.kind, value.raw)
        self.distinct.add(value.raw)
        if value.kind in ("date", "datetime") and value.note:
            pattern = value.note.split(" ")[0]
            self.date_patterns[pattern] = self.date_patterns.get(pattern, 0) + 1
        if value.kind == "quantity" and value.note:
            self.units[value.note] = self.units.get(value.note, 0) + 1
        if value.kind in ("int", "float", "currency", "percent", "quantity") and isinstance(value.value, (int, float)):
            self.numbers.append(float(value.value))
        if value.kind in ("code", "int") and isinstance(value.value, str):
            self.widths[len(value.value)] = self.widths.get(len(value.value), 0) + 1
        elif value.kind == "int" and isinstance(value.value, int):
            self.widths[len(str(abs(value.value)))] = self.widths.get(len(str(abs(value.value))), 0) + 1

    @property
    def kind(self) -> str:
        if not self.non_empty:
            return "empty"
        ranked = sorted(((k, v) for k, v in self.kinds.items() if k != "empty"), key=lambda kv: -kv[1])
        if not ranked:
            return "empty"
        top_kind, top_n = ranked[0]
        share = top_n / self.non_empty
        if share >= 0.9:
            return top_kind
        # 정수·실수·금액·수량이 섞인 것은 같은 숫자 계열로 본다
        numeric_kinds = ("int", "float", "currency", "percent", "quantity", "code")
        numeric = sum(self.kinds.get(k, 0) for k in numeric_kinds)
        if numeric / self.non_empty >= 0.9:
            for k in ("float", "quantity", "percent", "currency"):
                if self.kinds.get(k):
                    return k
            return "code" if self.kinds.get("code") and not self.kinds.get("int") else "int"
        return "mixed"

    @property
    def fill_rate(self) -> float:
        return self.non_empty / self.total if self.total else 0.0

    @property
    def dominant_share(self) -> float:
        if not self.non_empty:
            return 0.0
        return max(self.kinds.values()) / self.non_empty

    def summary(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "fill": round(self.fill_rate, 3),
            "distinct": len(self.distinct),
            "kinds": dict(sorted(self.kinds.items(), key=lambda kv: -kv[1])),
            "flags": dict(sorted(self.flags.items(), key=lambda kv: -kv[1])),
            "date_patterns": dict(self.date_patterns),
            "units": dict(self.units),
            "widths": dict(sorted(self.widths.items())),
            "numbers": (min(self.numbers), max(self.numbers)) if self.numbers else None,
            "examples": dict(self.examples),
        }
