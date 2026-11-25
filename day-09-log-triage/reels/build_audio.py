#!/usr/bin/env python3
"""Day 09 릴스 사운드트랙 — 21.5초 / 120 BPM / 48kHz 스테레오.

    python3 reels/build_audio.py              # wav + 파형 PNG
    python3 reels/build_audio.py --report     # 구간별 레벨 표

구성
    0.00 ~ 3.00   훅: 경고 사이렌 + 글리치 + 서브 드론 + 라이저, 2.94~3.00 무음 갭
    3.00          드롭: 서브 붐 + 브라암 + 임팩트 (삐에로가 로그를 폅니다)
    3.00 ~ 21.50  테크/로파이 그루브 9마디 (120 BPM, 1마디 2.0초)
    씬 컷 5.0 / 9.0 / 14.5 / 18.0 마다 whoosh + 임팩트 + 차임
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 48000
DUR = 21.5
N = int(round(SR * DUR))

DROP = 3.00          # 음악 시작 = 씬 2 진입
BPM = 120.0
BEAT = 60.0 / BPM    # 0.5 s
BAR = 4 * BEAT       # 2.0 s
BARS = 10            # 3.0 ~ 21.5 (마지막 마디는 잘린다)

CUTS = [5.0, 9.0, 14.5, 18.0]
SCENES = [
    ("hook", 0.0, 3.0),
    ("reveal", 3.0, 5.0),
    ("merge", 5.0, 9.0),
    ("demo", 9.0, 14.5),
    ("doc", 14.5, 18.0),
    ("cta", 18.0, 21.5),
]

rng = np.random.default_rng(20261125)


# --------------------------------------------------------------------- utilities
def secs(seconds: float) -> int:
    return int(round(seconds * SR))


def time_array(n: int) -> np.ndarray:
    return np.arange(n) / SR


def fft_filter(x: np.ndarray, lo: float | None = None, hi: float | None = None,
               order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth-magnitude filter (numpy only)."""
    n = len(x)
    if n == 0:
        return x
    nfft = 1 << max(1, (n - 1).bit_length())
    spec = np.fft.rfft(x, nfft)
    freq = np.fft.rfftfreq(nfft, 1.0 / SR)
    gain = np.ones_like(freq)
    if hi:
        gain *= 1.0 / np.sqrt(1.0 + (freq / hi) ** (2 * order))
    if lo:
        gain *= 1.0 / np.sqrt(1.0 + (lo / np.maximum(freq, 1e-9)) ** (2 * order))
    return np.fft.irfft(spec * gain, nfft)[:n]


def fft_convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    nfft = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[:n]


def midi(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def peak_normalize(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return x * (peak / m) if m > 0 else x


# ------------------------------------------------------------------- instruments
def kick(dur: float = 0.5, f0: float = 168.0, f1: float = 55.0, tau: float = 0.095) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    freq = f1 + (f0 - f1) * np.exp(-t / 0.017)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / tau)
    click = fft_filter(rng.standard_normal(n), lo=1900, hi=7000) * np.exp(-t / 0.005) * 0.34
    click *= np.clip(t / 0.0022, 0, 1) ** 0.8
    return peak_normalize(np.tanh(1.35 * (body + click)), 1.0)


def clap(dur: float = 0.28) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    noise = fft_filter(rng.standard_normal(n), lo=900, hi=7500)
    env = np.zeros(n)
    for at, amp in ((0.000, 0.55), (0.010, 0.75), (0.022, 1.0)):
        env += amp * np.exp(-np.clip(t - at, 0, None) / 0.048) * (t >= at)
    env *= np.clip(t / 0.0008, 0, 1)
    tone = (np.sin(2 * np.pi * 196 * t) + 0.5 * np.sin(2 * np.pi * 345 * t)) * np.exp(-t / 0.040)
    return peak_normalize(noise * env * 0.95 + 0.30 * tone, 1.0)


def hat(dur: float = 0.10, tau: float = 0.026) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = fft_filter(rng.standard_normal(n), lo=7500, hi=15500) * np.exp(-t / tau)
    s *= np.clip(t / 0.0008, 0, 1)
    return peak_normalize(s, 1.0)


def shaker(dur: float = 0.08) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = fft_filter(rng.standard_normal(n), lo=4200, hi=9500)
    s *= (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.028)
    return peak_normalize(s, 1.0)


def bass_note(freq: float, dur: float) -> np.ndarray:
    n = secs(dur + 0.14)
    t = time_array(n)
    s = np.zeros(n)
    for h in range(1, 10):
        f = freq * h
        if f > 2600:
            break
        s += np.sin(2 * np.pi * f * t + 0.4 * h) / (h ** 1.5)
    env = (1 - np.exp(-t / 0.005)) * np.exp(-t / (dur * 0.9 + 0.05))
    env *= np.clip((dur + 0.14 - t) / 0.05, 0.0, 1.0)
    return peak_normalize(np.tanh(1.8 * s) * env, 1.0)


def ep_note(freq: float, dur: float, detune_cents: float = 0.0) -> np.ndarray:
    """Rhodes-ish FM electric piano."""
    f = freq * 2.0 ** (detune_cents / 1200.0)
    n = secs(dur + 0.5)
    t = time_array(n)
    index = 1.2 * np.exp(-t / 0.10)
    s = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * 2.0 * t))
    s += 0.16 * np.sin(2 * np.pi * f * 3.98 * t + 0.6) * np.exp(-t / 0.05)
    s += 0.08 * np.sin(2 * np.pi * f * 6.1 * t + 1.1) * np.exp(-t / 0.03)
    env = (1 - np.exp(-t / 0.007)) * np.exp(-t / (dur * 0.8 + 0.22))
    trem = 1.0 + 0.05 * np.sin(2 * np.pi * 4.2 * t)
    return peak_normalize(s * env * trem, 1.0)


def pluck(freq: float, dur: float = 0.28) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = np.sin(2 * np.pi * freq * t) + 0.32 * np.sin(2 * np.pi * freq * 2 * t + 0.3)
    s += 0.15 * np.sin(2 * np.pi * freq * 3 * t + 0.9)
    env = (1 - np.exp(-t / 0.003)) * np.exp(-t / (dur * 0.26))
    return peak_normalize(fft_filter(s * env, hi=5600), 1.0)


def bell_note(freq: float, dur: float = 0.7) -> np.ndarray:
    """Circus music-box timbre for the 삐에로 motif."""
    n = secs(dur)
    t = time_array(n)
    s = np.zeros(n)
    for ratio, amp, dec in ((1.0, 1.0, 1.0), (2.0, 0.35, 0.6), (3.01, 0.22, 0.4), (4.2, 0.12, 0.25)):
        s += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / (dur * 0.35 * dec))
    s *= (1 - np.exp(-t / 0.0015))
    return peak_normalize(s, 1.0)


def pad_chord(freqs: list[float], dur: float) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = np.zeros(n)
    for f in freqs:
        for det in (-0.11, 0.0, 0.13):
            ff = f * 2.0 ** (det / 12.0)
            for h in range(1, 7):
                s += np.sin(2 * np.pi * ff * h * t + 0.7 * h * det) / (h ** 1.9)
    s = fft_filter(s, hi=1600, order=2)
    lfo = 1.0 + 0.10 * np.sin(2 * np.pi * 0.28 * t)
    env = np.clip(t / 0.5, 0, 1) ** 1.4 * np.clip((dur - t) / 0.4, 0, 1) ** 1.2
    return peak_normalize(s * env * lfo, 1.0)


def chime(freq: float, dur: float = 1.6) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = np.zeros(n)
    for ratio, amp, dec in ((1.0, 1.0, 1.0), (2.0, 0.42, 0.55), (2.76, 0.33, 0.42),
                            (5.4, 0.17, 0.24), (8.93, 0.08, 0.14)):
        s += amp * np.sin(2 * np.pi * freq * ratio * t + 0.2 * ratio) * np.exp(-t / (dur * 0.55 * dec))
    return peak_normalize(s * (1 - np.exp(-t / 0.002)), 1.0)


def pop(freq: float = 700.0) -> np.ndarray:
    n = secs(0.13)
    t = time_array(n)
    f = freq * (1.0 + 1.7 * (1 - np.exp(-t / 0.011)))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.032)
    s += 0.28 * fft_filter(rng.standard_normal(n), lo=2600, hi=8200) * np.exp(-t / 0.007)
    return peak_normalize(s * (1 - np.exp(-t / 0.0015)), 1.0)


def whoosh(dur: float = 1.0) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    noise = rng.standard_normal(n)
    low = fft_filter(noise, 350, 1100)
    mid = fft_filter(noise, 1100, 3400)
    high = fft_filter(noise, 3200, 7800)

    def bell(center: float, width: float) -> np.ndarray:
        return np.exp(-0.5 * (((t / dur) - center) / width) ** 2)

    s = 0.45 * low * bell(0.45, 0.30) + 0.80 * mid * bell(0.70, 0.22) + 1.05 * high * bell(0.90, 0.13)
    s *= (t / dur) ** 2.2
    s[-secs(0.004):] *= np.linspace(1, 0, secs(0.004))
    return peak_normalize(s, 1.0)


def impact() -> np.ndarray:
    n = secs(0.5)
    t = time_array(n)
    click = fft_filter(rng.standard_normal(n), lo=1100, hi=5500) * np.exp(-t / 0.013)
    click *= np.sin(np.clip(t / 0.0026, 0, 1) * np.pi / 2) ** 2 * 0.55
    body = np.sin(2 * np.pi * np.cumsum(62 + 120 * np.exp(-t / 0.025)) / SR) * np.exp(-t / 0.11)
    air = fft_filter(rng.standard_normal(n), lo=5000, hi=13000) * np.exp(-t / 0.04) * 0.45
    air *= np.clip(t / 0.002, 0, 1)
    return peak_normalize(np.tanh(1.4 * (click + body + air)), 1.0)


def riser(dur: float = 0.9) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    f = 220.0 * (1.0 + 5.2 * (t / dur) ** 2.2)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    tone += 0.35 * np.sin(2 * np.pi * np.cumsum(f * 2.0) / SR)
    env = (t / dur) ** 3.0
    tail = secs(0.005)
    env[-tail:] *= np.linspace(1, 0, tail) ** 1.5   # 꼬리 클릭 방지
    return peak_normalize(tone * env, 1.0)


def noise_riser(dur: float = 0.8) -> np.ndarray:
    """Rising band-passed noise — the '숨을 참는' build before the drop."""
    n = secs(dur)
    t = time_array(n)
    x = rng.standard_normal(n)
    out = np.zeros(n)
    steps = 12
    for i in range(steps):
        a, b = i / steps, (i + 1) / steps
        lo = 300 * (2 ** (i * 0.45))
        hi = lo * 4.0
        seg = fft_filter(x, lo=lo, hi=hi)
        win = np.zeros(n)
        ia, ib = secs(a * dur), secs(b * dur)
        win[ia:ib] = 1.0
        out += seg * win * (0.35 + 0.65 * b)
    env = (t / dur) ** 2.6
    out *= env
    out[: secs(0.01)] *= np.linspace(0, 1, secs(0.01))
    return peak_normalize(out, 1.0)


def sub_boom(dur: float = 1.6) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    f = 44 + 70 * np.exp(-t / 0.055)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR)
    s += 0.25 * np.sin(2 * np.pi * np.cumsum(f * 2.0) / SR)
    env = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.42)
    s = np.tanh(1.9 * s * env)
    s[-secs(0.08):] *= np.linspace(1, 0, secs(0.08))
    return peak_normalize(s, 1.0)


def braam(dur: float = 1.4) -> np.ndarray:
    """Trailer-style detuned saw stack that lands with the drop."""
    n = secs(dur)
    t = time_array(n)
    s = np.zeros(n)
    for f in (55.0, 55.4, 82.5, 110.8):
        for h in range(1, 12):
            if f * h > 3000:
                break
            s += np.sin(2 * np.pi * f * h * t + 0.35 * h) / (h ** 1.35)
    env = (1 - np.exp(-t / 0.012)) * np.exp(-t / 0.45)
    s = fft_filter(s, hi=2400, order=3) * env
    return peak_normalize(np.tanh(1.6 * s), 1.0)


def alarm(freq: float, dur: float = 0.16) -> np.ndarray:
    """Harsh two-tone warning beep (square-ish, band-limited)."""
    n = secs(dur)
    t = time_array(n)
    s = np.sign(np.sin(2 * np.pi * freq * t)) * 0.55
    s += np.sin(2 * np.pi * freq * t) * 0.45
    s = fft_filter(s, lo=300, hi=5200, order=3)
    env = np.clip(t / 0.004, 0, 1) * np.clip((dur - t) / 0.02, 0, 1)
    return peak_normalize(s * env, 1.0)


def glitch_burst(dur: float = 0.14) -> np.ndarray:
    """Bit-crushed gated noise."""
    n = secs(dur)
    t = time_array(n)
    x = rng.standard_normal(n)
    gate = (np.sin(2 * np.pi * (55 + 40 * t / dur) * t) > 0.1).astype(float)
    x = x * gate
    x = np.round(x * 6.0) / 6.0                      # bit crush
    x = fft_filter(x, lo=250, hi=9000, order=2)
    x *= np.clip(t / 0.002, 0, 1) * np.clip((dur - t) / 0.01, 0, 1)
    return peak_normalize(x, 1.0)


def thump(dur: float = 0.45) -> np.ndarray:
    n = secs(dur)
    t = time_array(n)
    s = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t / 0.03)) / SR) * np.exp(-t / 0.10)
    s *= np.clip(t / 0.0015, 0, 1)
    return peak_normalize(np.tanh(1.4 * s), 1.0)


def key_tick() -> np.ndarray:
    n = secs(0.035)
    t = time_array(n)
    s = fft_filter(rng.standard_normal(n), lo=2000, hi=6500) * np.exp(-t / 0.006)
    s += 0.4 * np.sin(2 * np.pi * 2600 * t) * np.exp(-t / 0.004)
    s *= np.clip(t / 0.0008, 0, 1)
    return peak_normalize(s, 1.0)


# ------------------------------------------------------------------- arrangement
# 4마디 루프: Am9 – Fmaj7 – Cmaj7 – G6
PROG = [
    (45, [57, 60, 64, 67]),
    (41, [53, 57, 60, 64]),
    (48, [52, 55, 59, 64]),
    (43, [55, 59, 62, 67]),
]

STEM_NAMES = ("kick", "clap", "hat", "shaker", "bass", "ep_l", "ep_r",
              "pad_l", "pad_r", "arp", "fx", "tick", "hook")


def bar_start(bar: int) -> float:
    return DROP + bar * BAR


def main_theme() -> dict[str, np.ndarray]:
    stems: dict[str, np.ndarray] = {k: np.zeros(N) for k in STEM_NAMES}

    def put(stem: str, start: float, sig: np.ndarray, gain: float = 1.0) -> None:
        i = secs(start)
        if i >= N or i < 0:
            return
        n = min(len(sig), N - i)
        if n > 0:
            stems[stem][i:i + n] += sig[:n] * gain

    kick_hit = kick()
    clap_hit = clap()
    hat_c = hat()
    hat_o = hat(dur=0.24, tau=0.070)
    shake = shaker()
    key = key_tick()

    # ================================================================ HOOK (0~3.0)
    # 서브 드론 + 저역 럼블
    n = secs(3.0)
    t = time_array(n)
    drone = np.sin(2 * np.pi * 41.2 * t) * 0.55 + np.sin(2 * np.pi * 61.7 * t) * 0.30
    drone *= np.clip(t / 0.02, 0, 1) * np.exp(-t / 6.0) * (1 + 0.25 * np.sin(2 * np.pi * 5.5 * t))
    put("hook", 0.0, peak_normalize(drone, 1.0), 0.52)
    rumble = fft_filter(rng.standard_normal(n), lo=28, hi=110) * np.clip(t / 0.01, 0, 1)
    put("hook", 0.0, peak_normalize(rumble, 1.0), 0.16)

    # 경고음 — 빨라지는 사이렌
    for at, f, g in ((0.08, 1320, 0.26), (0.42, 1392, 0.27), (0.78, 1472, 0.28),
                     (1.10, 1568, 0.30), (1.42, 1568, 0.31), (1.72, 1760, 0.32),
                     (2.02, 1760, 0.33), (2.34, 1976, 0.34), (2.62, 2093, 0.35)):
        put("hook", at, alarm(f, 0.13), g)

    # 글리치
    for at, g in ((0.0, 0.30), (0.55, 0.18), (1.05, 0.18), (1.60, 0.20),
                  (2.10, 0.24), (2.72, 0.28)):
        put("hook", at, glitch_burst(0.12), g)

    # 심장 박동 (느리게 → 빨라지게)
    for at, g in ((0.0, 0.5), (0.92, 0.6), (1.62, 0.55), (2.22, 0.5), (2.56, 0.45)):
        put("hook", at, thump(), g)

    # 라이저 + 노이즈 스웰 (2.95에 끊기고 0.05초 무음 갭 → 드롭)
    put("hook", 1.15, noise_riser(1.05), 0.24)
    put("hook", 1.95, riser(0.98), 0.16)

    # ================================================================ DROP (3.0)
    put("fx", DROP, sub_boom(1.8), 0.62)
    put("fx", DROP, braam(1.5), 0.34)
    put("fx", DROP, impact(), 0.34)

    # 삐에로 시그니처 — 반음계 상승 벨 모티프 (A C# E A)
    for i, note in enumerate((81, 85, 88, 93)):
        put("fx", DROP + 0.02 + i * 0.11, bell_note(midi(note), 0.65), 0.20)

    # ================================================================ GROOVE
    # drums: 3.0~21.0 풀 그루브 (bar 0~8), 마지막 마디는 축소
    for bar in range(0, 9):
        t0 = bar_start(bar)
        # kick — four on the floor
        for beat in range(4):
            put("kick", t0 + beat * BEAT, kick_hit, 0.92 if beat % 2 == 0 else 0.84)
        # clap — 2, 4박
        put("clap", t0 + 1 * BEAT, clap_hit, 0.80)
        put("clap", t0 + 3 * BEAT, clap_hit, 0.86)
        # hats — 8분 + 오프비트 오픈햇
        for step in range(8):
            at = t0 + step * BEAT / 2
            if step % 2 == 1:
                put("hat", at, hat_o, 0.24)
            else:
                put("hat", at, hat_c, 0.55 if step % 4 == 0 else 0.42)
        # shaker 16분
        for step in range(4, 16):
            put("shaker", t0 + step * BEAT / 4, shake, 0.15)
        if bar in (1, 3, 5, 6):
            # 스네어 필 (마디 끝)
            for i in range(3):
                put("clap", t0 + 3.5 * BEAT + i * BEAT / 6, clap_hit, 0.10 + 0.05 * i)

    # 작은 드롭 직전 브레이크 (17.5 씬 전) — 마지막 1/4박 비움은 위 루프에서 자동

    # bass — 8분 오프비트 + 옥타브 점프
    for bar in range(0, 9):
        t0 = bar_start(bar)
        root, _ = PROG[bar % 4]
        pat = [(0.0, 0.24, 1.00), (0.75, 0.20, 0.62), (1.0, 0.24, 0.86),
               (1.75, 0.20, 0.58), (2.0, 0.24, 0.92), (2.75, 0.20, 0.60),
               (3.0, 0.22, 0.80), (3.5, 0.18, 0.52)]
        for beat, dur, g in pat:
            note = root + (12 if beat in (1.75, 3.5) else 0)
            put("bass", t0 + beat * BEAT, bass_note(midi(note), dur), 0.34 * g)

    # chords — Rhodes, 좌우 디튠
    for bar in range(0, 10):
        _, voicing = PROG[bar % 4]
        t0 = bar_start(bar)
        level = 0.30 if bar >= 1 else 0.36
        for note in voicing:
            f = midi(note)
            put("ep_l", t0, ep_note(f, 1.75, detune_cents=-5.0), level / len(voicing) * 2.0)
            put("ep_r", t0, ep_note(f, 1.75, detune_cents=+5.0), level / len(voicing) * 2.0)
        if bar % 2 == 1:                       # 2.5박 컴핑
            for note in voicing[:3]:
                f = midi(note + 12)
                put("ep_l", t0 + 2.5 * BEAT, ep_note(f, 0.5, -4.0), 0.050)
                put("ep_r", t0 + 2.5 * BEAT, ep_note(f, 0.5, +4.0), 0.050)

    # pad — 2마디 단위
    for bar in range(0, BARS, 2):
        _, voicing = PROG[bar % 4]
        freqs = [midi(n + 12) for n in voicing[:3]]
        dur = min(BAR * 2, DUR - bar_start(bar)) - 0.05
        if dur <= 0.2:
            continue
        pad = pad_chord(freqs, dur)
        put("pad_l", bar_start(bar), pad, 0.115)
        put("pad_r", bar_start(bar), np.roll(pad, secs(0.011)), 0.115)

    # arp — 테크한 16분 플럭 (2마디 이후)
    pattern = [0, 2, 1, 3, 2, 0, 3, 1]
    for bar in range(1, 9):
        _, voicing = PROG[bar % 4]
        for step in range(8):
            note = voicing[pattern[(step + bar) % 8]] + (12 if step % 4 == 3 else 0)
            put("arp", bar_start(bar) + step * BEAT / 2, pluck(midi(note), 0.24),
                0.145 if step % 2 == 0 else 0.095)

    # ================================================================ 씬 컷 FX
    for i, at in enumerate(CUTS):
        put("fx", at - 0.98, whoosh(1.0), 0.42)
        put("fx", at - 0.85, noise_riser(0.80) if i != 0 else np.zeros(secs(0.8)), 0.0)
        put("fx", at - 0.80, riser(0.78), 0.085)
        put("fx", at + 0.004, impact(), 0.24)
        put("fx", at + 0.012, chime((659.25, 880.0, 1046.5, 1318.5)[i]), 0.185)

    # ================================================================ 텍스트 팝
    pops = [
        (0.08, 520, 0.20), (0.22, 640, 0.16), (0.36, 760, 0.20),
        (1.52, 900, 0.24), (1.66, 1040, 0.18),
        (3.62, 620, 0.18), (4.62, 720, 0.16), (5.42, 980, 0.24), (6.30, 1080, 0.14),
        (7.56, 700, 0.18), (7.78, 780, 0.16), (8.00, 860, 0.18), (8.22, 960, 0.22),
        (13.60, 560, 0.16), (14.20, 640, 0.15), (14.80, 720, 0.16), (15.70, 880, 0.20),
        (17.56, 620, 0.20), (17.78, 760, 0.16), (18.30, 940, 0.18),
    ]
    for at, f, g in pops:
        put("fx", at, pop(f), g)

    # 터미널 타이핑 (10.1 ~ 10.95)
    tt = 10.10
    i = 0
    while tt < 10.92:
        put("tick", tt, key, 0.52 if i % 2 == 0 else 0.34)
        tt += 0.046 + (0.014 if i % 6 == 0 else 0.0)
        i += 1

    # 보안 행 체크 사운드
    for at in (14.22, 14.82, 15.42):
        put("fx", at + 0.12, bell_note(midi(93), 0.5), 0.09)

    return stems


def tilt(x: np.ndarray, high_db: float = 4.0, high_fc: float = 3000.0,
         low_db: float = -1.5, low_fc: float = 90.0) -> np.ndarray:
    """Gentle shelves: lift presence, trim sub — keeps it audible on a phone speaker."""
    n = len(x)
    nfft = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1.0 / SR)
    high = 10 ** (high_db / 20.0)
    low = 10 ** (low_db / 20.0)
    gain = (1 + (high - 1) * (f ** 2 / (f ** 2 + high_fc ** 2))) * \
           (1 + (low - 1) * (low_fc ** 2 / (f ** 2 + low_fc ** 2)))
    return np.fft.irfft(spec * gain, nfft)[:n]


def stereofy(pairs: list[tuple[float, np.ndarray, float]]) -> tuple[np.ndarray, np.ndarray]:
    left, right = np.zeros(N), np.zeros(N)
    for pan, sig, gain in pairs:
        angle = (pan + 1.0) * np.pi / 4.0
        gl, gr = np.cos(angle) * gain, np.sin(angle) * gain
        n = min(len(sig), N)
        left[:n] += sig[:n] * gl
        right[:n] += sig[:n] * gr
    return left, right


def assemble(stems: dict[str, np.ndarray]) -> np.ndarray:
    ep = 0.5 * (stems["ep_l"] + stems["ep_r"])
    pad = 0.5 * (stems["pad_l"] + stems["pad_r"])

    drum_l, drum_r = stereofy([
        (0.00, stems["kick"], 1.0),
        (0.02, stems["clap"], 1.0),
        (-0.22, stems["hat"], 1.0),
        (0.30, stems["shaker"], 1.0),
    ])
    music_l, music_r = stereofy([
        (0.00, stems["bass"], 1.0),
        (-0.30, stems["ep_l"], 1.0),
        (0.30, stems["ep_r"], 1.0),
        (-0.45, stems["pad_l"], 1.0),
        (0.45, stems["pad_r"], 1.0),
        (0.12, stems["arp"], 1.0),
        (0.00, stems["fx"], 1.0),
        (0.00, stems["tick"], 1.0),
        (0.00, stems["hook"], 1.0),
    ])

    # reverb send: 화성 + FX
    send = 0.40 * ep + 0.55 * pad + 0.50 * stems["arp"] + 0.45 * stems["fx"]
    ir_len = secs(0.7)
    ir_t = time_array(ir_len)
    ir_l = fft_filter(rng.standard_normal(ir_len) * np.exp(-ir_t / 0.21), lo=300, hi=5200)
    ir_r = fft_filter(rng.standard_normal(ir_len) * np.exp(-ir_t / 0.21), lo=300, hi=5200)
    ir_l = peak_normalize(ir_l) * 0.055
    ir_r = peak_normalize(ir_r) * 0.055
    wet_l = np.concatenate([np.zeros(secs(0.012)), fft_convolve(send, ir_l)])[:N]
    wet_r = np.concatenate([np.zeros(secs(0.012)), fft_convolve(send, ir_r)])[:N]

    # kick sidechain — 음악 버스만
    duck = np.ones(N)
    idx = np.flatnonzero(stems["kick"] > 0.3)
    if len(idx):
        starts = idx[np.concatenate([[True], np.diff(idx) > secs(0.09)])]
        tt = time_array(secs(0.40))
        shape = 1.0 - 0.36 * np.exp(-tt / 0.095)
        for s0 in starts:
            n = min(len(shape), N - s0)
            if n > 0:
                duck[s0:s0 + n] = np.minimum(duck[s0:s0 + n], shape[:n])

    music_l = music_l * duck + wet_l
    music_r = music_r * duck + wet_r

    mix_l, mix_r = drum_l + music_l, drum_r + music_r

    mix_l = tilt(fft_filter(mix_l, lo=32, order=2), high_db=7.5, high_fc=2800.0, low_db=-3.0)
    mix_r = tilt(fft_filter(mix_r, lo=32, order=2), high_db=7.5, high_fc=2800.0, low_db=-3.0)

    stereo = np.stack([mix_l, mix_r], axis=1)
    stereo = np.tanh(stereo * 1.20) / np.tanh(1.20)      # bus glue

    t = time_array(N)
    env = np.ones(N)
    env *= np.clip(t / 0.02, 0, 1) ** 1.0                # 첫 샘플 클릭 방지
    # 1.44~1.50 무음 갭 (드롭 전 숨 고르기)
    fade_out_start, gap_start, gap_end = 1.400, 1.437, 1.500
    m1 = (t >= fade_out_start) & (t < gap_start)
    env[m1] = np.cos((t[m1] - fade_out_start) / (gap_start - fade_out_start) * np.pi / 2)
    env[(t >= gap_start) & (t < gap_end)] = 0.0
    # 아웃트로 페이드
    env *= np.clip((DUR - t) / 1.2, 0, 1) ** 1.4
    stereo *= env[:, None]
    # 드롭 직후 5ms 어택 램프 (0에서 시작하므로 클릭 없음)
    d0 = secs(DROP)
    ramp = secs(0.004)
    stereo[d0:d0 + ramp] *= np.linspace(0, 1, ramp)[:, None]

    peak = float(np.max(np.abs(stereo)))
    target = 10 ** (-3.0 / 20)                            # -3.0 dBFS (AAC 오버슈트 여유)
    stereo *= target / peak
    return stereo


def audit(stereo: np.ndarray) -> dict[str, float]:
    mono = stereo.mean(axis=1)
    peak = 20 * np.log10(np.max(np.abs(stereo)) + 1e-12)
    rms = 20 * np.log10(np.sqrt(np.mean(mono ** 2)) + 1e-12)
    clipped = int(np.sum(np.abs(stereo) >= 1.0))
    max_jump = float(np.max(np.abs(np.diff(mono))))
    return {"peak_db": peak, "rms_db": rms, "clipped_samples": clipped,
            "max_step_db": 20 * np.log10(max_jump + 1e-12)}


def report(stereo: np.ndarray) -> None:
    from PIL import Image, ImageDraw

    mono = stereo.mean(axis=1)
    info = audit(stereo)
    print(f"peak {info['peak_db']:.2f} dBFS · rms {info['rms_db']:.2f} dBFS · "
          f"clipped {info['clipped_samples']} · max sample step {info['max_step_db']:.2f} dBFS")
    for name, start, end in SCENES:
        seg = mono[secs(start):secs(end)]
        seg_rms = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)
        seg_peak = 20 * np.log10(np.max(np.abs(seg)) + 1e-12)
        print(f"  {name:<7} {start:>5.1f}-{end:>5.1f}s  rms {seg_rms:7.2f}  peak {seg_peak:7.2f}")

    W, H = 1100, 620
    img = Image.new("RGB", (W, H), (10, 14, 20))
    draw = ImageDraw.Draw(img)
    mid = H // 2
    step = max(1, N // (W * 2))
    amp = np.abs(stereo[: W * step]).reshape(-1, step).max(axis=1)[:W]
    for x, a in enumerate(amp):
        h = int(a * (H / 2 - 8))
        draw.line([(x, mid - h), (x, mid + h)], fill=(57, 211, 83))
    for at in [s[1] for s in SCENES[1:]]:
        x = int(at / DUR * (W - 1))
        draw.line([(x, 0), (x, H)], fill=(88, 166, 255))
    out = Path(__file__).resolve().parent.parent / "reels-day09-audio-waveform.png"
    img.save(out)
    print(out)


def write_wav24(path: Path, stereo: np.ndarray) -> None:
    data = np.clip(stereo, -1.0, 1.0)
    ints = np.round(data * (2 ** 23 - 1)).astype(np.int32)
    raw = ints.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(SR)
        handle.writeframes(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    out = Path(args.out) if args.out else here.parent / "reels-day09-audio.wav"

    stems = main_theme()
    stereo = assemble(stems)
    write_wav24(out, stereo)
    print(out)
    report(stereo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
