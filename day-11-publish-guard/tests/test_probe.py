"""ffprobe·ffmpeg 읽기 — 파서와 실패 경로. 실제 영상은 test_cli 에서 만든다."""

from __future__ import annotations

import json

import pytest

from publish_guard import probe
from publish_guard.probe import (
    ProbeError,
    Tools,
    find_tools,
    head_tail_silence,
    parse_ebur128,
    parse_ffprobe,
    parse_silencedetect,
)

FFPROBE_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "profile": "High",
            "width": 1080,
            "height": 1920,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1",
            "r_frame_rate": "30/1",
            "bit_rate": "364030",
        },
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000"},
    ],
    "format": {
        "duration": "21.500000",
        "size": "1556523",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "filename": "reels.mp4",
    },
}

EBUR128 = """
[Parsed_ebur128_0 @ 0x1] t: 21.4  TARGET:-23 LUFS  M:-13.0 S:-14.0  I: -11.7 LUFS  LRA: 1.6 LU  FTPK: -0.2 -0.2 dBFS

  Integrated loudness:
    I:         -11.7 LUFS
    Threshold: -21.8 LUFS

  Loudness range:
    LRA:         1.6 LU
    Threshold: -31.6 LUFS
    LRA low:   -12.3 LUFS
    LRA high:  -10.7 LUFS

  True peak:
    Peak:       -0.2 dBFS
"""

SILENCE = """
[silencedetect @ 0x1] silence_start: 0
[silencedetect @ 0x1] silence_end: 0.42 | silence_duration: 0.42
[silencedetect @ 0x1] silence_start: 20.9
[silencedetect @ 0x1] silence_end: 21.5 | silence_duration: 0.6
"""


class TestParseFFprobe:
    def test_core_values(self):
        facts = parse_ffprobe(FFPROBE_JSON, path="reels.mp4")
        assert facts.path == "reels.mp4"
        assert facts.duration_s == 21.5
        assert facts.width == 1080
        assert facts.height == 1920
        assert facts.fps == 30.0
        assert facts.video_codec == "h264"
        assert facts.video_profile == "High"
        assert facts.pix_fmt == "yuv420p"
        assert facts.video_bitrate_kbps == 364
        assert facts.audio_codec == "aac"
        assert facts.audio_channels == 2
        assert facts.audio_sample_rate == 48000
        assert facts.size_bytes == 1556523

    def test_fps_fraction(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["streams"][0]["avg_frame_rate"] = "30000/1001"
        assert parse_ffprobe(data).fps == pytest.approx(29.97, abs=0.01)

    def test_fps_falls_back_to_r_frame_rate(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["streams"][0]["avg_frame_rate"] = "0/0"
        assert parse_ffprobe(data).fps == 30.0

    def test_no_video_raises(self):
        data = {"streams": [{"codec_type": "audio", "codec_name": "aac"}], "format": {}}
        with pytest.raises(ProbeError, match="영상 스트림"):
            parse_ffprobe(data)

    def test_no_audio(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["streams"] = [data["streams"][0]]
        facts = parse_ffprobe(data)
        assert facts.has_audio is False
        assert facts.audio_channels is None

    def test_rotation_side_data(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["streams"][0]["side_data_list"] = [{"rotation": -90}]
        assert parse_ffprobe(data).rotation == -90

    def test_rotation_tag(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["streams"][0]["tags"] = {"rotate": "90"}
        assert parse_ffprobe(data).rotation == 90

    def test_missing_bitrate_is_none(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        del data["streams"][0]["bit_rate"]
        assert parse_ffprobe(data).video_bitrate_kbps is None

    def test_duration_from_video_stream(self):
        data = json.loads(json.dumps(FFPROBE_JSON))
        data["format"] = {}
        data["streams"][0]["duration"] = "10.0"
        assert parse_ffprobe(data).duration_s == 10.0


class TestParseEbur128:
    def test_values(self):
        out = parse_ebur128(EBUR128)
        assert out["integrated_lufs"] == -11.7
        assert out["lra_lu"] == 1.6
        assert out["true_peak_dbtp"] == -0.2

    def test_positive_peak(self):
        assert parse_ebur128("  True peak:\n    Peak:       +2.8 dBFS\n")["true_peak_dbtp"] == 2.8

    def test_silence_is_minus_inf(self):
        assert parse_ebur128("  Integrated loudness:\n    I:         -inf LUFS\n")["integrated_lufs"] == float("-inf")

    def test_missing_returns_none(self):
        out = parse_ebur128("nothing here")
        assert out["integrated_lufs"] is None
        assert out["true_peak_dbtp"] is None

    def test_summary_preferred_over_progress_line(self):
        text = (
            "[Parsed] t: 1.0 I: -70.0 LUFS\n"
            "  Integrated loudness:\n    I:         -14.1 LUFS\n"
        )
        assert parse_ebur128(text)["integrated_lufs"] == -14.1


class TestSilence:
    def test_parse(self):
        intervals = parse_silencedetect(SILENCE, 21.5)
        assert intervals == [(0.0, 0.42), (20.9, 21.5)]

    def test_open_ended_uses_duration(self):
        intervals = parse_silencedetect("silence_start: 18.0", 21.5)
        assert intervals == [(18.0, 21.5)]

    def test_head_tail(self):
        head, tail = head_tail_silence(parse_silencedetect(SILENCE, 21.5), 21.5)
        assert head == 0.42
        assert tail == 0.6

    def test_none(self):
        assert head_tail_silence([], 21.5) == (0.0, 0.0)

    def test_middle_silence_not_counted(self):
        head, tail = head_tail_silence([(5.0, 7.0)], 21.5)
        assert (head, tail) == (0.0, 0.0)


class TestTools:
    def test_env_override(self, monkeypatch, tmp_path):
        binary = tmp_path / "ffprobe"
        binary.write_text("#!/bin/sh\n")
        monkeypatch.setenv("PUBLISH_GUARD_FFPROBE", str(binary))
        assert find_tools().ffprobe == str(binary)

    def test_missing_tools(self, monkeypatch):
        monkeypatch.setattr(probe, "find_tools", lambda: Tools(None, None))
        with pytest.raises(ProbeError, match="ffprobe"):
            probe.probe_json("/tmp/x.mp4")
        with pytest.raises(ProbeError, match="ffmpeg"):
            probe.measure_loudness("/tmp/x.mp4")
        with pytest.raises(ProbeError, match="ffmpeg"):
            probe.measure_silence("/tmp/x.mp4", 10)

    def test_missing_file(self):
        with pytest.raises(ProbeError, match="파일이 없습니다"):
            probe.probe_json("/definitely/not/here.mp4")

    def test_directory(self, tmp_path):
        with pytest.raises(ProbeError, match="디렉터리"):
            probe.probe_json(tmp_path)

    def test_run_timeout(self, monkeypatch):
        import subprocess

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

        monkeypatch.setattr(probe.subprocess, "run", boom)
        with pytest.raises(ProbeError, match="시간 초과"):
            probe._run(["ffprobe"])

    def test_run_failure(self, monkeypatch):
        import subprocess

        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr(probe.subprocess, "run", lambda *a, **k: Result())
        with pytest.raises(ProbeError, match="실패"):
            probe._run(["ffprobe"])
