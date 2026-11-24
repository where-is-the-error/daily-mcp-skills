"""바이트 → 글자.

공공데이터포털·행정기관에서 받은 CSV는 UTF-8이 아닌 경우가 흔하다. 엑셀에서 'CSV(쉼표로
분리)'로 저장하면 CP949가 되고, 그 파일을 UTF-8로 읽으면 한글이 깨지거나 첫 줄에서
UnicodeDecodeError가 난다. 여기서는 후보 인코딩을 **엄격 모드로** 모두 시도하고, 실제로
디코딩된 글자의 모양(한글·ASCII·제어문자 비율)으로 점수를 매겨 고른다.

    python -c "from sheet_guard.decode import decode_bytes; print(decode_bytes(open('a.csv','rb').read()))"
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 후보 순서는 '먼저 성공하면 유리한' 순서가 아니라 점수로 정한다. 순서는 동점일 때만 쓴다.
CANDIDATES = ("utf-8-sig", "utf-8", "cp949", "euc-kr", "utf-16", "utf-16-le", "utf-16-be", "latin-1")

BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig", "UTF-8 BOM"),
    (b"\xff\xfe\x00\x00", "utf-32-le", "UTF-32 LE BOM"),
    (b"\x00\x00\xfe\xff", "utf-32-be", "UTF-32 BE BOM"),
    (b"\xff\xfe", "utf-16-le", "UTF-16 LE BOM"),
    (b"\xfe\xff", "utf-16-be", "UTF-16 BE BOM"),
)

# 제어문자(탭·줄바꿈 제외)는 인코딩을 잘못 고른 강한 신호다.
_CONTROL_OK = {"\t", "\n", "\r", "\f", "\v"}


@dataclass
class Decoded:
    text: str
    encoding: str
    confidence: float
    bom: str | None = None
    candidates: list[tuple[str, float]] = field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        if self.encoding.startswith("cp949") or self.encoding.startswith("euc-kr"):
            return "CP949(EUC-KR 계열)"
        return self.encoding.upper()

    @property
    def is_utf8(self) -> bool:
        return self.encoding in ("utf-8", "utf-8-sig")


def _char_score(text: str) -> float:
    """글자 모양 점수 — 높을수록 '이 인코딩으로 읽은 결과가 말이 된다'."""
    if not text:
        return 0.0
    total = 0
    hangul = 0
    ascii_print = 0
    control = 0
    weird = 0
    for ch in text:
        total += 1
        code = ord(ch)
        if ch in _CONTROL_OK:
            continue
        if code < 0x20 or code == 0x7F:
            control += 1
        elif 0xAC00 <= code <= 0xD7A3 or 0x3131 <= code <= 0x318E:
            hangul += 1
        elif 0x20 <= code <= 0x7E:
            ascii_print += 1
        elif ch in "·…—–‘’“”《》〈〉、。":
            ascii_print += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            weird += 0.25          # 한자·가나는 정상일 수 있지만 흔치는 않다
        elif code == 0xFFFD:
            weird += 3
        elif 0x1100 <= code <= 0x11FF:
            weird += 1.5           # 조합 전 자모 — CP949로 UTF-8을 읽었을 때 자주 나온다
        else:
            weird += 0.6
    score = (hangul * 1.4 + ascii_print) / total - (control * 4 + weird * 2) / total
    return score


def _decode_one(data: bytes, encoding: str) -> str | None:
    if encoding.startswith("utf-16") and len(data) % 2:
        return None                # 홀수 길이는 UTF-16일 수 없다
    try:
        text = data.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return None
    # UTF-16/32로 읽었는데 NUL이 많다는 건 대개 오판이다(ASCII 파일을 UTF-16으로 읽은 경우).
    if encoding.startswith("utf-16") and text.count("\x00") > len(text) * 0.05:
        return None
    return text


def decode_bytes(data: bytes, candidates: tuple[str, ...] = CANDIDATES) -> Decoded:
    """후보를 모두 시도하고 점수로 고른다. 실패하면 latin-1(무손실)로 표기한다."""
    if not data:
        return Decoded(text="", encoding="utf-8", confidence=1.0, note="빈 파일")

    bom_label = None
    bom_encoding = None
    for mark, enc, label in BOMS:
        if data.startswith(mark):
            bom_label, bom_encoding = label, enc
            break

    scored: list[tuple[str, float, str]] = []
    for enc in candidates:
        text = _decode_one(data, enc)
        if text is None:
            continue
        # UTF-8이 성공했다면 다른 인코딩으로 '우연히' 성공한 것보다 우선한다.
        # BOM이 없는데 utf-8-sig로 읽는 것은 같은 결과라 UTF-8을 앞세운다.
        if enc == "utf-8":
            bonus = 0.15
        elif enc == "utf-8-sig":
            bonus = 0.15 if data.startswith(b"\xef\xbb\xbf") else 0.10
        else:
            bonus = 0.0
        scored.append((enc, _char_score(text) + bonus, text))

    if not scored:
        text = data.decode("latin-1", errors="replace")
        return Decoded(text=text, encoding="latin-1", confidence=0.2,
                       bom=bom_label,
                       note="어떤 후보로도 엄격 디코딩이 실패해 latin-1로 읽었습니다. 글자가 깨졌을 수 있습니다.")

    scored.sort(key=lambda item: item[1], reverse=True)
    best_enc, best_score, best_text = scored[0]
    second = scored[1][1] if len(scored) > 1 else best_score - 1.0

    # CP949와 EUC-KR은 같은 글자를 내놓는 경우가 대부분이다 — 다른 인코딩과의 차이만 본다.
    family = {"cp949", "euc-kr"}
    rivals = [score for enc, score, text_ in scored[1:]
              if text_ != best_text and not (best_enc in family and enc in family)]
    second = max(rivals) if rivals else best_score - 0.6

    # BOM이 있으면 그 인코딩을 존중한다(내용 점수가 근소하게 달라도 사용자의 표시가 우선).
    if bom_encoding and bom_encoding in {s[0] for s in scored}:
        for enc, score, text in scored:
            if enc == bom_encoding:
                best_enc, best_score, best_text = enc, score, text
                break

    best_text = best_text.lstrip("\ufeff")

    margin = max(0.0, best_score - second)
    confidence = round(min(0.99, 0.55 + margin * 0.6), 2)
    if len(scored) == 1:
        confidence = 0.9
    # BOM은 사용자가 이미 인코딩을 말해 준 것과 같다.
    if bom_label and best_enc.replace("-", "_").split("_")[0] == bom_encoding.split("-")[0]:
        confidence = max(confidence, 0.95)
    # CP949와 EUC-KR은 같은 계열이라, 둘 사이의 차이는 '한글을 못 읽는' 위험이 아니다.
    if best_enc in ("cp949", "euc-kr"):
        confidence = max(confidence, 0.75)

    note = ""
    if not best_enc.startswith("utf"):
        note = "UTF-8이 아니어서 %s로 읽었습니다. 엑셀에서 다시 저장할 때 'CSV UTF-8'을 고르면 다음부터 안 깨집니다." % best_enc.upper()
    if bom_label:
        note = (note + " " if note else "") + f"{bom_label}이 붙어 있어 첫 칸 이름에서 제거했습니다."

    return Decoded(
        text=best_text,
        encoding=best_enc,
        confidence=confidence,
        bom=bom_label,
        candidates=[(enc, round(score, 3)) for enc, score, _ in scored],
        note=note,
    )


def line_ending_report(text: str) -> dict:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    kinds = [name for name, n in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if n]
    return {"crlf": crlf, "lf": lf, "cr": cr, "mixed": len(kinds) > 1, "kinds": kinds}
