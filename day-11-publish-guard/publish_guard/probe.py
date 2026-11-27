"""ffprobe·ffmpeg 읽기 — 잰 값만 가져온다. 파일을 고치지 않고, 아무것도 업로드하지 않는다.

도구는 PATH·환경변수·알려진 경로 순서로 찾는다. 없으면 '없다'고 실패한다 — 추측하지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import MediaFacts

SILENCE_MIN_S = 0.3
SILENCE_THRESHOLD_DB = -45


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tools:
    ffprobe: str | None
    ffmpeg: str | None
    version: str = ""


def _candidate(name: str, env: str) -> str | None:
    value = os.environ.get(env)
    if value and Path(value).exists():
        return value
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    for path in (
        home / ".local/bin" / name,
        home / ".local/bin" / f"{name}-static",
        Path("/workspace/.local/bin") / f"{name}-static",
        Path("/workspace/.local/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/opt/homebrew/bin") / name,
    ):
        if path.exists():
            return str(path)
    return None


def find_tools() -> Tools:
    ffprobe = _candidate("ffprobe", "PUBLISH_GUARD_FFPROBE")
    ffmpeg = _candidate("ffmpeg", "PUBLISH_GUARD_FFMPEG")
    version = ""
    for tool in (ffprobe, ffmpeg):
        if not tool:
            continue
        try:
            out = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=10, check=False).stdout
            first = out.splitlines()[0] if out else ""
            version = " · ".join(filter(None, [version, first.split(" Copyright")[0].strip()]))
        except Exception:
            continue
    return Tools(ffprobe=ffprobe, ffmpeg=ffmpeg, version=version)


def _run(command: list[str], timeout: int = 120) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"{Path(command[0]).name} 시간 초과 ({timeout}s)") from exc
    except OSError as exc:
        raise ProbeError(f"{command[0]} 실행 실패: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-4:]
        raise ProbeError(f"{Path(command[0]).name} 실패 (exit {result.returncode}): {' / '.join(tail)}")
    return result.stdout


def _fraction(value: str | None) -> float | None:
    if not value:
        return None
    if "/" in value:
        num, _, den = value.partition("/")
        try:
            return float(num) / float(den) if float(den) else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _rotation(stream: dict[str, Any]) -> int:
    for item in stream.get("side_data_list", []) or []:
        if "rotation" in item:
            try:
                return int(float(item["rotation"]))
            except (TypeError, ValueError):
                pass
    tags = stream.get("tags", {}) or {}
    try:
        return int(float(tags.get("rotate", 0)))
    except (TypeError, ValueError):
        return 0


def parse_ffprobe(data: dict[str, Any], path: str = "") -> MediaFacts:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProbeError("영상 스트림이 없습니다")
    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    fps = _fraction(video.get("avg_frame_rate")) or _fraction(video.get("r_frame_rate"))
    return MediaFacts(
        path=path or str(fmt.get("filename", "")),
        container=str(fmt.get("format_name", "")),
        duration_s=round(duration, 3),
        width=_int(video.get("width")) or 0,
        height=_int(video.get("height")) or 0,
        fps=round(fps, 3) if fps else None,
        video_codec=video.get("codec_name"),
        video_profile=video.get("profile"),
        pix_fmt=video.get("pix_fmt"),
        video_bitrate_kbps=(_int(video.get("bit_rate")) or 0) // 1000 or None,
        audio_codec=(audio or {}).get("codec_name"),
        audio_channels=_int((audio or {}).get("channels")),
        audio_sample_rate=_int((audio or {}).get("sample_rate")),
        size_bytes=_int(fmt.get("size")) or 0,
        rotation=_rotation(video),
        probed_with="ffprobe",
    )


def parse_ebur128(text: str) -> dict[str, float | None]:
    """ffmpeg ebur128 요약에서 통합 음량·진폭 범위·트루피크를 읽는다."""
    out: dict[str, float | None] = {"integrated_lufs": None, "lra_lu": None, "true_peak_dbtp": None}

    def number(pattern: str) -> float | None:
        match = re.search(pattern, text)
        if not match:
            return None
        raw = match.group(1)
        if "inf" in raw.lower():
            return float("-inf")
        try:
            return float(raw)
        except ValueError:
            return None

    integrated = number(r"Integrated loudness:\s*\n\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS")
    if integrated is None:
        integrated = number(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS")
    lra = number(r"\bLRA:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LU")
    peak = number(r"\bPeak:\s*(-?(?:\d+(?:\.\d+)?|inf|\+?\d+(?:\.\d+)?))\s*dBFS")
    out["integrated_lufs"] = integrated
    out["lra_lu"] = lra
    out["true_peak_dbtp"] = peak
    return out


def parse_silencedetect(text: str, duration: float) -> list[tuple[float, float]]:
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*(-?\d+(?:\.\d+)?)", text)]
    ends: list[float] = []
    for match in re.finditer(r"silence_end:\s*(-?\d+(?:\.\d+)?)", text):
        ends.append(float(match.group(1)))
    intervals: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration
        intervals.append((max(0.0, start), min(duration, end)))
    return intervals


def head_tail_silence(intervals: list[tuple[float, float]], duration: float) -> tuple[float, float]:
    head = 0.0
    tail = 0.0
    for start, end in intervals:
        if start <= 0.05:
            head = max(head, end - max(0.0, start))
        if abs(end - duration) <= 0.06:
            tail = max(tail, end - start)
    return round(head, 3), round(tail, 3)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def probe_json(path: str | Path) -> dict[str, Any]:
    tools = find_tools()
    if not tools.ffprobe:
        raise ProbeError("ffprobe 를 찾지 못했습니다 — PATH 에 두거나 PUBLISH_GUARD_FFPROBE 로 지정하세요")
    target = Path(path).expanduser()
    if not target.exists():
        raise ProbeError(f"파일이 없습니다: {target}")
    if target.is_dir():
        raise ProbeError(f"디렉터리입니다: {target}")
    out = _run(
        [
            tools.ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(target),
        ]
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe JSON 을 읽지 못했습니다: {exc}") from exc


def measure_loudness(path: str | Path, timeout: int = 300) -> dict[str, float | None]:
    tools = find_tools()
    if not tools.ffmpeg:
        raise ProbeError("ffmpeg 를 찾지 못했습니다 — PATH 에 두거나 PUBLISH_GUARD_FFMPEG 로 지정하세요")
    result = subprocess.run(
        [tools.ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"ffmpeg ebur128 실패: {result.stderr.strip().splitlines()[-1:]}")
    return parse_ebur128(result.stderr)


def measure_silence(path: str | Path, duration: float, timeout: int = 300) -> tuple[float, float]:
    tools = find_tools()
    if not tools.ffmpeg:
        raise ProbeError("ffmpeg 를 찾지 못했습니다")
    result = subprocess.run(
        [
            tools.ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_S}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        return 0.0, 0.0
    intervals = parse_silencedetect(result.stderr, duration)
    return head_tail_silence(intervals, duration)


def probe(path: str | Path, measure_audio: bool = True) -> MediaFacts:
    data = probe_json(path)
    facts = parse_ffprobe(data, path=str(Path(path).expanduser()))
    tools = find_tools()
    facts = MediaFacts(**{**facts.__dict__, "probed_with": tools.version or tools.ffprobe or "ffprobe", "measured_at": _now()})
    if measure_audio and facts.has_audio:
        loud = measure_loudness(path)
        head, tail = measure_silence(path, facts.duration_s)
        facts = MediaFacts(
            **{
                **facts.__dict__,
                "loudness_lufs": None if loud["integrated_lufs"] is None else round(loud["integrated_lufs"], 1),
                "loudness_range_lu": None if loud["lra_lu"] is None else round(loud["lra_lu"], 1),
                "true_peak_dbtp": None if loud["true_peak_dbtp"] is None else round(loud["true_peak_dbtp"], 1),
                "head_silence_s": head,
                "tail_silence_s": tail,
            }
        )
    return facts
