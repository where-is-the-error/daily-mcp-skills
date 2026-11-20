"""검사·집계·출력 — 점수 규칙, 사이트 묶음, 고치기 순서."""

from __future__ import annotations

import json

import pytest

from a11y_lens.audit import (
    LIMITS,
    audit_page,
    audit_site,
    grade_of,
    load_document,
    page_payload,
    payload_json,
    render_page,
    render_plan,
    render_site,
    score_of,
)
from a11y_lens.rules import Violation, rule_by_id


def test_audit_inline_html(bad_page) -> None:
    audit = audit_page(bad_page)
    assert audit.path == "(inline html)"
    assert audit.title == "로그인"
    assert audit.violations


def test_audit_file_path_named(tmp_path) -> None:
    path = tmp_path / "p.html"
    path.write_text("<html lang='ko'><head><title>t</title></head><body><main>x</main></body></html>", encoding="utf-8")
    audit = audit_page(str(path))
    assert audit.path == str(path)
    assert audit.violations == []
    assert audit.score == 100


def test_audit_relative_path_with_base_dir(tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "p.html").write_text("<html><body><main>x</main></body></html>", encoding="utf-8")
    audit = audit_page("sub/p.html", base_dir=tmp_path)
    assert audit.path.endswith("p.html")


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_document("없는파일.html")


def test_empty_source_raises() -> None:
    with pytest.raises(ValueError):
        load_document("   ")


def test_unknown_rule_raises(bad_page) -> None:
    with pytest.raises(ValueError):
        audit_page(bad_page, rule_ids=["nope"])


def test_rule_filter_limits_violations(bad_page) -> None:
    audit = audit_page(bad_page, rule_ids=["image-alt"])
    assert {v.rule.id for v in audit.violations} == {"image-alt"}


def test_file_url_is_accepted(tmp_path) -> None:
    path = tmp_path / "u.html"
    path.write_text("<p>x</p>", encoding="utf-8")
    assert load_document(f"file://{path}").first("p") is not None


def test_audit_counts_by_impact(bad_page) -> None:
    audit = audit_page(bad_page)
    counts = audit.counts()
    assert sum(counts.values()) == len(audit.violations)
    assert counts["critical"] >= 1


def test_audit_by_rule_groups(bad_page) -> None:
    audit = audit_page(bad_page)
    grouped = audit.by_rule()
    assert set(grouped) == {v.rule.id for v in audit.violations}


def test_rules_hit_preserves_first_seen_order(bad_page) -> None:
    audit = audit_page(bad_page)
    assert audit.rules_hit()[0] == audit.violations[0].rule.id


def test_worst_impact(bad_page, good_page) -> None:
    assert audit_page(bad_page).worst == "critical"
    assert audit_page(good_page).worst == "none"


def test_score_drops_once_per_rule() -> None:
    serious = rule_by_id("html-lang")
    many = [
        Violation(rule=serious, selector="x", line=1, snippet="", message="", fingerprint=f"f{i}")
        for i in range(10)
    ]
    assert score_of(many)[0] == 100 - 12


def test_score_sums_distinct_rules() -> None:
    html = (
        '<html lang="ko"><head><title>t</title></head>'
        '<body><main><img src="a.png"><div tabindex="3">x</div></main></body></html>'
    )
    audit = audit_page(html)
    assert set(audit.rules_hit()) == {"image-alt", "tabindex-positive"}
    assert audit.score == 100 - 25 - 4


def test_score_never_negative() -> None:
    html = (
        '<html><body><img src="a.png"><button></button><a href="/x"></a>'
        '<input placeholder="p"><table><tr><td>1</td><td>2</td></tr></table></body></html>'
    )
    assert score_of(audit_page(html).violations)[0] == 0


@pytest.mark.parametrize(
    "score,grade",
    [(100, "양호"), (90, "양호"), (89, "주의"), (70, "주의"), (69, "위험"), (40, "위험"), (39, "심각"), (0, "심각")],
)
def test_grade_boundaries(score, grade) -> None:
    assert grade_of(score) == grade


def test_render_page_has_score_counts_and_limits(bad_page) -> None:
    text = render_page(audit_page(bad_page))
    assert "점수" in text
    assert "치명" in text
    assert LIMITS in text


def test_render_page_clean_message(good_page) -> None:
    text = render_page(audit_page(good_page))
    assert "정적으로 판정 가능한 위반은 없습니다" in text


def test_render_page_can_hide_fixes(bad_page) -> None:
    assert "고치기:" in render_page(audit_page(bad_page))
    assert "고치기:" not in render_page(audit_page(bad_page), show_fix=False)


def test_render_page_trims_repeats_and_says_how_many() -> None:
    html = "<html><body>" + "".join(f'<img src="{i}.png">' for i in range(6)) + "</body></html>"
    audit = audit_page(html)
    text = render_page(audit, max_per_rule=2)
    assert "생략된 반복" in text
    assert "image-alt 4건" in text


def test_render_page_shows_line_and_selector(bad_page) -> None:
    text = render_page(audit_page(bad_page))
    assert "L" in text
    assert "`" in text


def test_payload_json_is_valid(bad_page) -> None:
    audit = audit_page(bad_page)
    data = json.loads(payload_json(audit))
    assert data["path"] == "(inline html)"
    assert data["violations"][0]["wcag"].count(".") == 2
    assert "fingerprint" in data["violations"][0]


def test_page_payload_matches_audit(bad_page) -> None:
    audit = audit_page(bad_page)
    payload = page_payload(audit)
    assert payload["score"] == audit.score
    assert len(payload["violations"]) == len(audit.violations)


def test_plan_orders_by_impact() -> None:
    html = (
        '<html lang="ko"><head><title>t</title></head>'
        '<body><main><h1>가</h1><h4>나</h4><img src="a.png"></main></body></html>'
    )
    text = render_plan(audit_page(html))
    assert text.index("이미지에 대체텍스트") < text.index("제목 단계를 건너뛰었습니다")


def test_plan_limits_steps(bad_page) -> None:
    audit = audit_page(bad_page)
    text = render_plan(audit, max_steps=1)
    assert text.count("**1.") == 1
    assert "규칙" in text.splitlines()[-3]


def test_plan_clean_page(good_page) -> None:
    text = render_plan(audit_page(good_page))
    assert "고치기 순서" in text


# ---------------------------------------------------------------- 사이트
def test_site_audit_collects_pages(site) -> None:
    result = audit_site(site)
    assert len(result.pages) == 3
    assert {page.path for page in result.pages} == {"index.html", "about.html", "sub/deep.html"}


def test_site_audit_groups_repeats_across_pages(site) -> None:
    result = audit_site(site)
    image_groups = [g for g in result.groups if g.rule.id == "image-alt"]
    assert image_groups
    assert max(len(g.pages) for g in image_groups) >= 2


def test_site_audit_counts_total(site) -> None:
    result = audit_site(site)
    assert result.total_violations() == sum(len(page.violations) for page in result.pages)
    assert result.counts()["critical"] >= 3


def test_site_audit_scores(site) -> None:
    result = audit_site(site)
    assert len(result.scores()) == 3
    assert min(result.scores()) < 100


def test_site_audit_respects_max_pages(site) -> None:
    result = audit_site(site, max_pages=2)
    assert len(result.pages) == 2
    assert result.skipped


def test_site_audit_glob_pattern(site) -> None:
    result = audit_site(site, pattern="**/deep.html")
    assert [page.path for page in result.pages] == ["sub/deep.html"]


def test_site_audit_not_a_directory(tmp_path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        audit_site(target)


def test_site_audit_empty_directory(tmp_path) -> None:
    result = audit_site(tmp_path)
    assert result.pages == []
    assert "페이지 **0쪽**" in render_site(result)


def test_render_site_has_table_and_lowest_pages(site) -> None:
    text = render_site(audit_site(site))
    assert "| 위반 패턴 |" in text
    assert "쪽별 점수" in text
    assert LIMITS in text


def test_render_site_limits_groups(site) -> None:
    text = render_site(audit_site(site), max_groups=1)
    assert "패턴" in text and "더 |" in text


def test_site_payload_json(site) -> None:
    data = json.loads(json.dumps(audit_site(site).to_dict(), ensure_ascii=False))
    assert len(data["pages"]) == 3
    assert data["groups"][0]["fingerprint"].startswith("fp_")


def test_site_group_prefers_worst_impact(site) -> None:
    result = audit_site(site)
    ranks = [{"critical": 0, "serious": 1, "moderate": 2}[g.impact] for g in result.groups]
    assert ranks == sorted(ranks)


def test_broken_file_is_skipped_with_reason(tmp_path) -> None:
    (tmp_path / "bad.html").write_bytes(b"\xff\xfe\x00bad")
    (tmp_path / "ok.html").write_text("<html><body><main>x</main></body></html>", encoding="utf-8")
    result = audit_site(tmp_path)
    assert any(page.path == "ok.html" for page in result.pages)
