"""스택 트레이스 — 어디서 터졌는지.

언어마다 프레임 순서가 반대다. Python 은 바깥 → 안쪽으로 쌓이고(마지막이 터진 곳),
Java·Node 는 안쪽 → 바깥쪽이다(첫 줄이 터진 곳). 이 차이를 무시하고 '첫 프레임'을
쓰면 Python 로그에서는 항상 `main` 이 범인이 된다.

그래서 언어를 먼저 알아보고, 언어별로 '가장 안쪽 프레임'을 고른다.
모르는 형식이면 위치를 비우고 그 사실을 남긴다 — 추측해서 채우지 않는다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .signature import Cluster
from .types import LogFile, Record

PY_FRAME = re.compile(r'File\s"(?P<file>[^"]+)",\s*line\s+(?P<line>\d+)(?:,\s*in\s+(?P<func>\S+))?')
JAVA_FRAME = re.compile(r"^\s*at\s+(?P<cls>[\w$.]+)\.(?P<method>[\w$<>]+)\((?P<src>[^)]*)\)")
NODE_FRAME = re.compile(r"^\s*at\s+(?P<func>[^()]+?)\s+\((?P<file>[^:()]+):(?P<line>\d+):(?P<col>\d+)\)")
NODE_BARE = re.compile(r"^\s*at\s+(?P<file>[^:()]+):(?P<line>\d+):(?P<col>\d+)")
GO_FRAME = re.compile(r"^(?P<func>[\w.$*/\[\]]+)\((?P<args>[^)]*)\)$")
GO_FILE = re.compile(r"^\t(?P<file>[^\s:]+):(?P<line>\d+)")
EXC_WORD = re.compile(r"\b(?P<type>[A-Za-z_$][\w.$]*(?:Exception|Error|Throwable|Fault))\b")
CAUSE = re.compile(r"^\s*(?:Caused by:\s*)?(?P<rest>.*)$")


@dataclass(slots=True)
class TraceInfo:
    language: str = "unknown"
    exception: str = ""
    top_frame: str = ""
    frames: list[str] = field(default_factory=list)
    causes: int = 1
    deepest: str = ""

    @property
    def known(self) -> bool:
        return self.language != "unknown"


def detect_language(lines: list[str]) -> str:
    text = "\n".join(lines[:40])
    if "Traceback (most recent call last)" in text or re.search(r'File\s"[^"]+",\s*line\s+\d+', text):
        return "python"
    if re.search(r"^\s*at\s+[\w$.]+\.[\w$<>]+\(", text, re.M):
        return "java"
    if re.search(r"^\s*at\s+.+\([^:()]+:\d+:\d+\)", text, re.M) or re.search(r"^\s*at\s+[^:()]+:\d+:\d+", text, re.M):
        return "node"
    if text.lstrip().startswith("panic:") or re.search(r"^goroutine\s+\d+\s+\[", text, re.M):
        return "go"
    if text.lstrip().startswith("Exception in thread"):
        return "java"
    return "unknown"


def analyze_trace(lines: list[str]) -> TraceInfo:
    if not lines:
        return TraceInfo()
    language = detect_language(lines)
    info = TraceInfo(language=language)

    if language == "python":
        frames = []
        for line in lines:
            m = PY_FRAME.search(line)
            if m:
                func = m.group("func") or "?"
                frames.append(f"{func} ({_basename(m.group('file'))}:{m.group('line')})")
        info.frames = frames
        info.top_frame = frames[-1] if frames else ""
        candidates = [line.strip() for line in lines
                      if line.strip() and not PY_FRAME.search(line)
                      and not line.strip().startswith(("Traceback", "During handling",
                                                       "The above exception"))]
        info.exception = candidates[-1] if candidates else ""
        info.causes = 1
        for line in lines:
            if "direct cause of the following exception" in line or "During handling of the above" in line:
                info.causes += 1
        info.deepest = info.exception

    elif language in ("java", "node"):
        frames = []
        exception = ""
        for line in lines:
            m = JAVA_FRAME.match(line)
            if m:
                src = m.group("src")
                frames.append(f"{m.group('cls')}.{m.group('method')}({src})")
                continue
            m = NODE_FRAME.match(line) or NODE_BARE.match(line)
            if m:
                file = _basename(m.group("file"))
                func = m.groupdict().get("func") or "<anonymous>"
                frames.append(f"{func.strip()} ({file}:{m.group('line')})")
                continue
            if not exception:
                word = EXC_WORD.search(line)
                if word and not line.strip().startswith(("at ", "Caused by")):
                    exception = line.strip()
        info.frames = frames
        info.top_frame = frames[0] if frames else ""
        causes = [line for line in lines if line.strip().startswith("Caused by:")]
        info.causes = 1 + len(causes)
        info.exception = exception
        if causes:
            info.deepest = causes[-1].strip().replace("Caused by: ", "", 1)
        else:
            info.deepest = exception

    elif language == "go":
        frames = []
        for index, line in enumerate(lines):
            m = GO_FRAME.match(line.strip())
            if m and "(" not in m.group("func"):
                nxt = lines[index + 1] if index + 1 < len(lines) else ""
                g = GO_FILE.match(nxt)
                location = f"{_basename(g.group('file'))}:{g.group('line')}" if g else ""
                frames.append(f"{m.group('func')} ({location})" if location else m.group("func"))
        info.frames = frames
        info.top_frame = frames[0] if frames else ""
        panic = next((line for line in lines if line.startswith("panic:")), "")
        info.exception = panic.replace("panic: ", "", 1)
        info.deepest = info.exception

    else:
        # 모르는 형식: 위치를 비워 두고, 첫 줄만 예외 후보로 남긴다.
        info.exception = lines[0].strip()
        info.top_frame = ""

    return info


def _basename(path: str) -> str:
    cleaned = path.strip()
    for sep in ("/", "\\"):
        if sep in cleaned:
            cleaned = cleaned.rsplit(sep, 1)[-1]
    return cleaned[:60]


def exception_head(record: Record) -> str:
    """서명에 보탤 예외 머리 — 메시지가 'Unhandled exception' 뿐일 때 구분자 노릇."""
    if not record.trace:
        return ""
    info = analyze_trace(record.trace)
    text = info.exception
    if not text:
        return ""
    if len(text) > 120:
        text = text[:119] + "…"
    return text


@dataclass(slots=True)
class StackGroup:
    signature: str
    template: str
    count: int
    language: str
    exception: str
    top_frame: str
    causes: int
    distinct_stacks: int
    location: str = ""
    prints: set[str] = field(default_factory=set)


@dataclass(slots=True)
class StackReport:
    traced: int = 0
    untraced_errors: int = 0
    groups: list[StackGroup] = field(default_factory=list)
    top_frames: Counter = field(default_factory=Counter)
    languages: Counter = field(default_factory=Counter)

    @property
    def trace_ratio(self) -> float:
        return 0.0


def stack_report(log: LogFile, clusters: list[Cluster] | None = None) -> StackReport:
    from .signature import cluster as cluster_log
    clusters = clusters or cluster_log(log)
    by_sig: dict[str, Cluster] = {c.signature: c for c in clusters}

    groups: dict[str, StackGroup] = {}
    top_frames: Counter = Counter()
    languages: Counter = Counter()
    traced = 0

    for record in log.records:
        if not record.trace:
            continue
        if not any(line.strip() for line in record.trace):
            continue
        traced += 1
        info = analyze_trace(record.trace)
        languages[info.language] += 1
        if info.top_frame:
            location = info.top_frame.split("(")[-1].rstrip(")") if "(" in info.top_frame else info.top_frame
            top_frames[location] += 1

        from .signature import record_signature
        sig = record_signature(record)
        group = groups.get(sig)
        if group is None:
            group = StackGroup(signature=sig, template=by_sig[sig].template if sig in by_sig else record.snippet(100),
                               count=0, language=info.language, exception=info.exception,
                               top_frame=info.top_frame, causes=info.causes, distinct_stacks=0)
            groups[sig] = group
        group.count += 1
        group.causes = max(group.causes, info.causes)
        if info.top_frame and not group.location:
            group.location = info.top_frame
        if info.language != "unknown" and group.language == "unknown":
            group.language = info.language
        if info.exception and not group.exception:
            group.exception = info.exception
        # 같은 서명 안에 몇 가지 스택이 섞였는지 (프레임 목록 전체의 지문)
        fingerprint = "|".join(info.frames[:6])
        if fingerprint:
            group.prints.add(fingerprint)
        group.distinct_stacks = max(1, len(group.prints))

    errors = log.error_records()
    untraced = sum(1 for record in errors if not record.trace)
    ordered = sorted(groups.values(), key=lambda g: -g.count)
    return StackReport(traced=traced, untraced_errors=untraced, groups=ordered,
                       top_frames=top_frames, languages=languages)
