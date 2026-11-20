"""기준선 저장·비교 — '고쳤다'를 숫자로 확인한다."""

from __future__ import annotations

import json

import pytest

from a11y_lens import store
from a11y_lens.audit import audit_page, audit_site

PAGE_BEFORE = """<html lang="ko"><head><title>t</title></head>
<body><main><h1>가</h1><img src="a.png"><img src="b.png"><button></button></main></body></html>
"""

PAGE_AFTER = """<html lang="ko"><head><title>t</title></head>
<body><main><h1>가</h1><img src="a.png" alt="그림"><button>저장</button></main></body></html>
"""

PAGE_REGRESSED = """<html lang="ko"><head><title>t</title></head>
<body><main><h1>가</h1><button></button><iframe src="x"></iframe></main></body></html>
"""


def test_home_uses_env(lens_home) -> None:
    assert store.home() == lens_home


def test_resolve_strips_paths(lens_home) -> None:
    path = store.resolve("../../etc/passwd")
    assert path.parent == lens_home
    assert ".." not in path.name


def test_resolve_keeps_korean_names(lens_home) -> None:
    assert store.resolve("로그인페이지").name == "로그인페이지.json"


def test_resolve_default_name(lens_home) -> None:
    assert store.resolve("").name == "baseline.json"


def test_resolve_strips_json_suffix(lens_home) -> None:
    assert store.resolve("site.json").name == "site.json"


def test_save_and_load_roundtrip(lens_home) -> None:
    audit = audit_page(PAGE_BEFORE)
    path = store.save("page", audit)
    data = store.load("page")
    assert path.exists()
    assert data["tool"] == "a11y-lens"
    assert data["count"] == len(audit.violations)
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == data["count"]


def test_load_missing_raises(lens_home) -> None:
    with pytest.raises(FileNotFoundError):
        store.load("없음")


def test_compare_reports_resolved_and_remaining(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    result = store.compare(before, audit_page(PAGE_AFTER))
    assert result["resolved"]
    assert result["ok"] is True
    assert result["current_count"] < result["baseline_count"]


def test_compare_detects_new_violations(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    result = store.compare(before, audit_page(PAGE_REGRESSED))
    assert result["new"]
    assert result["ok"] is False
    assert any(item["rule"] == "iframe-title" for item in result["new"])


def test_compare_same_page_is_all_remaining(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    result = store.compare(before, audit_page(PAGE_BEFORE))
    assert result["new"] == []
    assert result["resolved"] == []
    assert len(result["remaining"]) == result["baseline_count"]


def test_same_template_violations_share_one_fingerprint(lens_home) -> None:
    before = audit_page(PAGE_BEFORE)
    fps = [v.fingerprint for v in before.violations if v.rule.id == "image-alt"]
    assert len(fps) == 2 and len(set(fps)) == 1
    result = store.compare({"violations": store.flatten(before)}, audit_page(PAGE_AFTER))
    assert result["current_count"] == 0
    assert len(result["resolved"]) == 3


def test_render_compare_mentions_counts(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    text = store.render_compare(store.compare(before, audit_page(PAGE_AFTER)), before, title="p.html")
    assert "기준선" in text
    assert "없어짐" in text
    assert "새로 생김" in text


def test_render_compare_flags_regression(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    text = store.render_compare(store.compare(before, audit_page(PAGE_REGRESSED)), before)
    assert "새로 생긴 위반이 있습니다" in text


def test_render_compare_success(lens_home) -> None:
    store.save("page", audit_page(PAGE_BEFORE))
    before = store.load("page")
    text = store.render_compare(store.compare(before, audit_page(PAGE_AFTER)), before)
    assert "✅" in text


def test_save_site_audit(site, lens_home) -> None:
    path = store.save("site", audit_site(site))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["count"] >= 3
    assert all("file" in item for item in data["violations"])


def test_flatten_includes_page_path_for_site(site) -> None:
    items = store.flatten(audit_site(site))
    assert {item["file"] for item in items} >= {"index.html", "about.html"}


def test_compare_against_site(site, lens_home) -> None:
    store.save("site", audit_site(site))
    result = store.compare(store.load("site"), audit_site(site))
    assert result["new"] == []
    assert result["ok"] is True
