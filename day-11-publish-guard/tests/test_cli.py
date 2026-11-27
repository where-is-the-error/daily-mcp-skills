"""명령줄 — 종료 코드와 출력 형식. 실제 ffmpeg 로 만든 4초 영상을 쓴다."""

from __future__ import annotations

import json

import pytest

from conftest import CAPTION_BAD, CAPTION_GOOD
from publish_guard.cli import main


def _write(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestMediaCommand:
    def test_json(self, tiny_video, capsys):
        assert main(["media", tiny_video, "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["width"] == 1080
        assert data["height"] == 1920
        assert data["duration_s"] == pytest.approx(4.0, abs=0.2)

    def test_text(self, tiny_video, capsys):
        assert main(["media", tiny_video]) == 0
        out = capsys.readouterr().out
        assert "1080×1920 (세로)" in out

    def test_missing_file(self, capsys):
        assert main(["media", "/definitely/not/here.mp4"]) == 1
        assert "파일이 없습니다" in capsys.readouterr().err


class TestCheckCommand:
    def test_hold_on_bad_caption(self, tiny_video, tmp_path, capsys):
        caption = _write(tmp_path, "bad.md", CAPTION_BAD)
        assert main(["check", tiny_video, "--caption", caption]) == 2
        out = capsys.readouterr().out
        assert "판정: 보류" in out
        assert "ffmpeg -i" in out

    def test_pass_without_measure(self, tiny_video, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["check", tiny_video, "--caption", caption, "--no-measure"]) == 0
        out = capsys.readouterr().out
        assert "판정: 통과" in out

    def test_json_and_save(self, tiny_video, tmp_path, capsys):
        caption = _write(tmp_path, "bad.md", CAPTION_BAD)
        save = tmp_path / "report.json"
        assert main(["check", tiny_video, "--caption", caption, "--json", "--save", str(save)]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["verdict"] == "hold"
        saved = json.loads(save.read_text(encoding="utf-8"))
        assert saved["score"] == payload["score"]

    def test_caption_only(self, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["check", "--caption", caption]) == 0
        assert "캡션만" in capsys.readouterr().out

    def test_boxes_file(self, tiny_video, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        boxes = _write(tmp_path, "boxes.json", '[{"label":"훅","x":0,"y":300,"w":900,"h":180}]')
        assert main(["check", tiny_video, "--caption", caption, "--boxes", boxes]) == 2
        assert "상단에 걸린 문구" in capsys.readouterr().out

    def test_platform_filter(self, tiny_video, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["check", tiny_video, "--caption", caption, "--platforms", "tiktok", "--no-measure"]) == 0
        out = capsys.readouterr().out
        assert "YouTube Shorts" not in out

    def test_requires_input(self):
        with pytest.raises(SystemExit):
            main(["check"])

    def test_keyword(self, tmp_path, capsys):
        caption = _write(tmp_path, "c.md", "피크 -0.2 dBTP면 깨진다 #ffmpeg")
        assert main(["caption", caption, "--keyword", "오디오"]) == 3
        assert "keyword-missing" in capsys.readouterr().out


class TestCaptionCommand:
    def test_clean(self, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["caption", caption]) == 0
        out = capsys.readouterr().out
        assert "캡션:" in out
        assert "걸린 것 없음" in out

    def test_json(self, tmp_path, capsys):
        caption = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["caption", caption, "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["caption"]["hashtags"] == ["ffmpeg", "릴스", "영상편집"]

    def test_hold_keeps_facts_in_output(self, tmp_path, capsys):
        caption = _write(tmp_path, "bad.md", CAPTION_BAD)
        assert main(["caption", caption]) == 3
        assert "tell-not-x-but-y" in capsys.readouterr().out


class TestCompareCommand:
    def test_compare(self, tmp_path, capsys):
        before = tmp_path / "before.json"
        after = tmp_path / "after.json"
        caption = _write(tmp_path, "bad.md", CAPTION_BAD)
        assert main(["check", "--caption", caption, "--json", "--save", str(before)]) == 2
        capsys.readouterr()
        good = _write(tmp_path, "good.md", CAPTION_GOOD)
        assert main(["check", "--caption", good, "--json", "--save", str(after)]) == 0
        capsys.readouterr()
        assert main(["compare", str(before), str(after)]) == 0
        out = capsys.readouterr().out
        assert "→" in out
        assert "사실 보존" in out


class TestRulesCommand:
    def test_text(self, capsys):
        assert main(["rules"]) == 0
        out = capsys.readouterr().out
        assert "규칙" in out
        assert "true-peak-over" in out

    def test_json(self, capsys):
        assert main(["rules", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert any(row["id"] == "tell-not-x-but-y" for row in data)

    def test_one(self, capsys):
        assert main(["rules", "true-peak-over"]) == 0
        assert "트루피크" in capsys.readouterr().out

    def test_unknown(self, capsys):
        assert main(["rules", "nope"]) == 1


class TestUsage:
    def test_no_command(self, capsys):
        assert main([]) == 1
        assert "usage" in capsys.readouterr().out.lower()

    def test_bad_platform(self, tmp_path, capsys):
        caption = _write(tmp_path, "c.md", CAPTION_GOOD)
        assert main(["caption", caption, "--platforms", "myspace"]) == 1
        assert "모르는 플랫폼" in capsys.readouterr().err
