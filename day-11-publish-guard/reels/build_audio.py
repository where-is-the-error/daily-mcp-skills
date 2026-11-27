#!/usr/bin/env python3
"""Day 11 릴스 사운드 — 21.5초, 120 BPM, 직접 합성.

    python3 reels/build_audio.py            # reels-day11-audio.wav (loudnorm -14 LUFS / -1.5 dBTP)
    python3 reels/build_audio.py --raw      # 정규화 전 원본

외부 음원은 쓰지 않는다. 마지막에 ffmpeg loudnorm 한 번으로 이 영상이 검사하는 기준에 맞춘다.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000
DUR = 21.5
N = int(SR * DUR)
BPM = 120.0
BEAT = 60.0 / BPM
BAR = BEAT * 4

CUTS = (1.5, 4.5, 8.0, 11.5, 15.5, 19.0)

rng = np.random.default_rng(11)


def buf(seconds: float = DUR) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float64)


def add(dst: np.ndarray, src: np.ndarray, at: float, gain: float = 1.0) -> None:
    start = int(at * SR)
    if start >= len(dst):
        return
    end = min(len(dst), start + len(src))
    if end > start:
        dst[start:end] += src[: end - start] * gain


def env_exp(n: int, tau: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.exp(-t / tau)


def kick(dur: float = 0.42, f0: float = 150.0, f1: float = 48.0) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    freq = f1 + (f0 - f1) * np.exp(-t / 0.045)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * env_exp(n, 0.11) * 0.95


def hat(dur: float = 0.06) -> np.ndarray:
    n = int(SR * dur)
    noise = rng.standard_normal(n)
    noise = np.diff(noise, prepend=0.0)  # 위쪽으로 치우친 고역
    return noise * env_exp(n, 0.018) * 0.22


def clap(dur: float = 0.20) -> np.ndarray:
    n = int(SR * dur)
    noise = rng.standard_normal(n)
    shaped = np.diff(noise, prepend=0.0) * 0.6
    env = env_exp(n, 0.05)
    for offset in (0.0, 0.012, 0.024):
        start = int(offset * SR)
        env[start:] *= 1.0
    return shaped * env * 0.35


def tone(freq: float, dur: float, harmonics: tuple[float, ...] = (1.0, 0.5, 0.25)) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for index, weight in enumerate(harmonics, start=1):
        out += weight * np.sin(2 * np.pi * freq * index * t)
    return out


def bass(freq: float, dur: float) -> np.ndarray:
    n = int(SR * dur)
    body = tone(freq, dur, (1.0, 0.35, 0.12))
    env = np.minimum(1.0, np.arange(n) / (0.008 * SR)) * env_exp(n, 0.22)
    return np.tanh(body * env * 0.9)


def pad(freqs: tuple[float, ...], dur: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for freq in freqs:
        for detune in (-0.6, 0.0, 0.6):
            out += np.sin(2 * np.pi * (freq + detune) * t + rng.uniform(0, 6.28))
    attack = np.minimum(1.0, np.arange(n) / (0.35 * SR))
    release = np.minimum(1.0, (n - np.arange(n)) / (0.25 * SR))
    return out / (len(freqs) * 3) * attack * release * 0.5


def tick(freq: float = 2400.0) -> np.ndarray:
    n = int(SR * 0.05)
    return np.sin(2 * np.pi * freq * np.arange(n) / SR) * env_exp(n, 0.008) * 0.18


def whoosh(dur: float = 0.55) -> np.ndarray:
    n = int(SR * dur)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.ones(12) / 12, mode="same")
    ramp = np.linspace(0, 1, n) ** 2.2
    fall = np.linspace(1, 0, n) ** 0.8
    return noise * ramp * fall * 0.30


def riser(dur: float = 1.2) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    freq = 180 * (2 ** (3.0 * t / dur))
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sweep = np.sin(phase) * 0.25
    noise = rng.standard_normal(n) * np.linspace(0.02, 0.22, n)
    return (sweep + noise) * np.linspace(0.2, 1.0, n) ** 1.6


def impact() -> np.ndarray:
    n = int(SR * 1.2)
    t = np.arange(n) / SR
    freq = 70 * np.exp(-t / 0.25) + 38
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * env_exp(n, 0.32) * 0.85


def chime(freq: float, dur: float = 1.2) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, weight in ((1.0, 1.0), (2.01, 0.5), (3.02, 0.28), (4.9, 0.12)):
        out += weight * np.sin(2 * np.pi * freq * ratio * t)
    return out * env_exp(n, 0.42) * 0.20


def build() -> np.ndarray:
    mix = np.zeros((N, 2))

    # 코드 진행: Am - F - C - G (2마디씩)
    roots = [55.0, 43.65, 65.41, 49.0]
    chords = [
        (220.0, 261.63, 329.63),
        (174.61, 220.0, 261.63),
        (261.63, 329.63, 392.0),
        (196.0, 246.94, 293.66),
    ]
    melody = [440.0, 392.0, 329.63, 293.66, 392.0, 440.0, 523.25, 392.0]

    bars = int(np.ceil(DUR / BAR))
    for bar in range(bars):
        start = bar * BAR
        section = 0 if bar < 1 else (1 if bar < 3 else (2 if bar < 4 else (3 if bar < 6 else (4 if bar < 8 else 5))))
        root = roots[(bar // 2) % 4]
        chord = chords[(bar // 2) % 4]

        heavy = section in (1, 2, 3)
        soft = section in (0, 4, 5)

        if start < DUR:
            add(mix[:, 0], pad(chord, min(BAR * 1.05, DUR - start)), start, 0.55)
            add(mix[:, 1], pad(chord, min(BAR * 1.05, DUR - start)), start, 0.55)

        beat_count = 4
        for beat in range(beat_count):
            at = start + beat * BEAT
            if at >= DUR:
                break
            if section == 4 and beat % 2 == 1:
                continue
            gain = 0.9 if heavy else 0.55
            add(mix[:, 0], kick(), at, gain)
            add(mix[:, 1], kick(), at, gain)
            if heavy and beat in (1, 3):
                add(mix[:, 0], clap(), at, 0.8)
                add(mix[:, 1], clap(), at + 0.004, 0.8)
            for half in (0.0, 0.5):
                hat_at = at + half * BEAT
                if hat_at < DUR and (section >= 2):
                    pan = 0.42 if half == 0 else 0.58
                    add(mix[:, 0], hat(), hat_at, pan)
                    add(mix[:, 1], hat(), hat_at, 1.0 - pan)

        if section in (1, 2, 3):
            for eighth in range(8):
                at = start + eighth * BEAT / 2
                if at >= DUR:
                    break
                note = root * (2 if eighth in (3, 6) else 1)
                add(mix[:, 0], bass(note, 0.22), at, 0.42)
                add(mix[:, 1], bass(note, 0.22), at, 0.42)

        if section == 0 and start < 1.5:
            add(mix[:, 0], chime(880.0, 0.9), start + 0.05, 0.5)
            add(mix[:, 1], chime(880.0, 0.9), start + 0.06, 0.5)

    # 장면 전환 — 틱과 훅
    for at in CUTS:
        add(mix[:, 0], tick(), at - 0.02, 1.0)
        add(mix[:, 1], tick(2600.0), at - 0.02, 1.0)
        add(mix[:, 0], whoosh(), at - 0.35, 0.9)
        add(mix[:, 1], whoosh(), at - 0.33, 0.9)

    # 11.5초 고치기 시작 — 라이저와 임팩트
    add(mix[:, 0], riser(1.15), 10.35, 0.55)
    add(mix[:, 1], riser(1.15), 10.35, 0.55)
    add(mix[:, 0], impact(), 11.5, 0.9)
    add(mix[:, 1], impact(), 11.5, 0.9)

    # 19.0초 루프 — 첫 화면과 같은 말이니 같은 종소리로 돌아간다
    add(mix[:, 0], chime(880.0, 1.4), 19.0, 1.0)
    add(mix[:, 1], chime(880.0, 1.4), 19.02, 1.0)
    add(mix[:, 0], chime(659.25, 1.2), 19.5, 0.6)
    add(mix[:, 1], chime(659.25, 1.2), 19.52, 0.6)

    # 아주 옅은 멜로디 — 8분음표마다
    for index in range(int(DUR / (BEAT / 2))):
        at = index * BEAT / 2
        if 4.0 <= at < 11.3:
            note = melody[index % len(melody)]
            add(mix[:, 0], tone(note * 2, 0.18, (1.0, 0.2)) * env_exp(int(0.18 * SR), 0.05) * 0.05, at, 1.0)
            add(mix[:, 1], tone(note * 2, 0.18, (1.0, 0.2)) * env_exp(int(0.18 * SR), 0.05) * 0.05, at + 0.006, 1.0)

    # 스테레오 폭 — 아주 살짝
    mix[:, 1] = 0.97 * mix[:, 1] + 0.03 * mix[:, 0]
    peak = float(np.max(np.abs(mix))) or 1.0
    return mix / peak * 0.72


def write_wav(path: Path, stereo: np.ndarray) -> None:
    data = np.clip(stereo, -1.0, 1.0)
    left = (data[:, 0] * 32767).astype("<i2")
    right = (data[:, 1] * 32767).astype("<i2")
    interleaved = np.empty(len(left) * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(interleaved.tobytes())


def find_ffmpeg() -> str:
    for candidate in ("ffmpeg", str(Path.home() / ".local/bin/ffmpeg"), "/workspace/.local/bin/ffmpeg-static"):
        found = shutil.which(candidate) if "/" not in candidate else candidate
        if found and Path(found).exists():
            return found
    raise SystemExit("ffmpeg을 찾을 수 없습니다.")


def measure(path: Path) -> dict[str, float]:
    ffmpeg = find_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    import re

    def grab(pattern: str) -> float:
        match = re.search(pattern, result.stderr)
        return float(match.group(1)) if match else float("nan")

    return {
        "lufs": grab(r"Integrated loudness:\s*\n\s*I:\s*(-?\d+(?:\.\d+)?)"),
        "peak": grab(r"True peak:\s*\n\s*Peak:\s*(-?\+?\d+(?:\.\d+)?)"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", action="store_true", help="loudnorm 없이 원본만")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day11-audio.wav"))
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    raw = here / "audio-raw.wav"
    write_wav(raw, build())
    before = measure(raw)

    if args.raw:
        target = Path(args.out)
        shutil.copyfile(raw, target)
    else:
        ffmpeg = find_ffmpeg()
        target = Path(args.out)
        # 1단계: 실제 값을 재고, 2단계: 그 값으로 선형 정규화한다 (한 번에 하면 목표에서 벗어난다)
        probe = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(raw),
                "-af",
                "loudnorm=I=-14:TP=-2.8:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        import json
        import re

        match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe.stderr, re.DOTALL)
        if not match:
            raise SystemExit("loudnorm 1단계 측정 실패")
        measured = json.loads(match.group(0))
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(raw),
                "-af",
                (
                    "loudnorm=I=-14:TP=-2.8:LRA=11"
                    f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
                    f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
                    f":offset={measured['target_offset']}:linear=true"
                ),
                "-ar",
                str(SR),
                "-ac",
                "2",
                str(target),
            ],
            check=True,
        )
    after = measure(target)
    print(f"raw   : {before['lufs']:.1f} LUFS · {before['peak']:+.1f} dBTP")
    print(f"final : {after['lufs']:.1f} LUFS · {after['peak']:+.1f} dBTP")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
