"""계획과 보고서 — 명령 조립, 조각 나누기, 문장 형식."""

from __future__ import annotations

import pytest

from conftest import SHOP, make_diff, repo_with
from test_radar import diffparse, report, risk as risk_module
from test_radar.plan import build as build_plan
from test_radar.plan import estimated_total
from test_radar.select import build as build_set


def setup_change(path: str = "shop/pricing.py", old: str = "", new: str = ""):
    old = old or SHOP[path]
    new = new or SHOP[path].replace("0.1", "0.2")
    repo = repo_with(**{path.replace("/", "__"): new})
    change_set = build_set(repo, diffparse.parse(make_diff(path, old, new)))
    return change_set, build_plan(change_set, shards=2)


def test_plan_has_commands() -> None:
    _, plan = setup_change()
    assert plan.commands


def test_python_command_shape() -> None:
    change_set, plan = setup_change()
    command = plan.commands[0]["command"]
    assert command.startswith("python -m pytest ")
    assert "tests/" in command


def test_shards_split() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 2\n"}
    for number in range(6):
        files[f"tests/test_{number}.py"] = "from pkg.core import f\n\ndef test_f():\n    assert f() == 2\n"
    from test_radar.graph import load_sources
    repo = load_sources(files)
    change_set = build_set(repo, diffparse.parse(make_diff("pkg/core.py", "def f():\n    return 1\n",
                                                          "def f():\n    return 2\n")))
    plan = build_plan(change_set, shards=3)
    assert len({command["label"] for command in plan.commands}) == 3


def test_single_shard() -> None:
    change_set, _ = setup_change()
    one = build_plan(change_set, shards=1)
    labels = [command["label"] for command in one.commands]
    assert "python 필수" in labels
    assert len([label for label in labels if label.endswith("필수")]) == 1


def test_shards_clamped() -> None:
    change_set, _ = setup_change()
    assert len(build_plan(change_set, shards=99).commands) <= 8


def test_zero_shards_becomes_one() -> None:
    change_set, _ = setup_change()
    plan = build_plan(change_set, shards=0)
    assert len(plan.commands) >= 1


def test_estimate_grows_with_items() -> None:
    change_set, plan = setup_change()
    small = build_plan(change_set, shards=1, per_item_ms=10).commands[0]["est_seconds"]
    large = build_plan(change_set, shards=1, per_item_ms=100).commands[0]["est_seconds"]
    assert large > small


def test_assumed_fields() -> None:
    _, plan = setup_change()
    assert plan.assumed["per_item_ms"] == 50
    assert "모델" in plan.assumed["note"]


def test_fallback_command() -> None:
    _, plan = setup_change()
    assert plan.fallback["command"] == "python -m pytest"
    assert plan.fallback["items"] >= 1


def test_fallback_not_triggered() -> None:
    _, plan = setup_change()
    assert plan.fallback["triggered"] is False


def test_fallback_triggered_by_config() -> None:
    repo = repo_with(**{"tests__conftest.py": SHOP["tests/conftest.py"] + "\n# x\n"})
    change_set = build_set(repo, diffparse.parse(make_diff(
        "tests/conftest.py", SHOP["tests/conftest.py"], SHOP["tests/conftest.py"] + "\n# x\n")))
    plan = build_plan(change_set, shards=2)
    assert plan.fallback["triggered"] is True
    assert plan.fallback["reasons"]


def test_max_per_shard_note() -> None:
    change_set, _ = setup_change()
    plan = build_plan(change_set, shards=2, max_per_shard=0)
    assert all("조각" in command["note"] or "먼저" in command["note"] or "근거" in command["note"]
               for command in plan.commands)


def test_estimated_total() -> None:
    _, plan = setup_change()
    assert estimated_total(plan) == round(sum(command["est_seconds"] for command in plan.commands), 2)


def test_javascript_command() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({
        "web/lib/money.js": "export function total(c){ return 1; }\n",
        "web/app.js": "import { total } from './lib/money.js';\n\nexport function render(c){ return total(c); }\n",
        "web/__tests__/app.test.js": "import { render } from '../app.js';\n\ntest('x', () => {});\n",
    })
    change_set = build_set(repo, diffparse.parse(make_diff(
        "web/lib/money.js", "export function total(c){ return 1; }\n",
        "export function total(c){ return 2; }\n")))
    plan = build_plan(change_set, shards=1)
    commands = [command["command"] for command in plan.commands]
    assert any(command.startswith("npx jest") for command in commands)


def test_empty_plan() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({"pkg/__init__.py": "", "pkg/a.py": "def f():\n    return 2\n",
                         "tests/test_other.py": "def test_x():\n    assert True\n"})
    change_set = build_set(repo, diffparse.parse(make_diff("pkg/a.py", "def f():\n    return 1\n",
                                                           "def f():\n    return 2\n")))
    plan = build_plan(change_set)
    assert plan.commands == []


# ------------------------------------------------------------------ 보고서
def test_report_has_sections() -> None:
    change_set, plan = setup_change()
    risks = risk_module.check(change_set)
    text = report.impact_report(change_set, risks, plan)
    for needle in ("test-radar", "선택:", "테스트 근거 없는 변경", "위험 규칙", "계획:", "판정하지 않음"):
        assert needle in text


def test_report_verdict_line() -> None:
    change_set, plan = setup_change()
    text = report.impact_report(change_set, risk_module.check(change_set), plan)
    assert "판정:" in text


def test_change_lines() -> None:
    change_set, _ = setup_change()
    text = report.change_lines(change_set)
    assert "shop/pricing.py" in text
    assert "바뀐 심볼" in text


def test_change_lines_with_hunks() -> None:
    change_set, _ = setup_change()
    text = report.change_lines(change_set, include_hunks=True)
    assert "@@" in text
    assert "+" in text


def test_change_lines_signature() -> None:
    old = SHOP["shop/pricing.py"]
    new = old.replace("def total_for(items):", "def total_for(items, rate=TAX_RATE):")
    repo = repo_with(**{"shop__pricing.py": new})
    change_set = build_set(repo, diffparse.parse(make_diff("shop/pricing.py", old, new)))
    text = report.change_lines(change_set)
    assert "인자 변경" in text


def test_tests_lines() -> None:
    change_set, _ = setup_change()
    text = report.tests_lines(change_set)
    assert "tests/test_pricing.py" in text
    assert "L1" in text


def test_tests_lines_empty() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({"pkg/a.py": "def f():\n    return 2\n"})
    change_set = build_set(repo, diffparse.parse(make_diff("pkg/a.py", "def f():\n    return 1\n",
                                                           "def f():\n    return 2\n")))
    assert "선택된 테스트 없음" in report.tests_lines(change_set)


def test_tests_lines_limit() -> None:
    change_set, _ = setup_change()
    assert "더" in report.tests_lines(change_set, limit=1) or len(change_set.selections) <= 1


def test_plan_lines() -> None:
    change_set, plan = setup_change()
    text = "\n".join(report.plan_lines(plan, change_set))
    assert "전체 실행:" in text


def test_gap_lines_none() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({"pkg/__init__.py": "", "pkg/a.py": "def f():\n    return 2\n",
                         "tests/test_a.py": "from pkg.a import f\n\ndef test_f():\n    assert f() == 2\n"})
    change_set = build_set(repo, diffparse.parse(make_diff("pkg/a.py", "def f():\n    return 1\n",
                                                           "def f():\n    return 2\n")))
    assert "없음" in report.gap_lines(change_set)[0]


def test_risk_lines_empty() -> None:
    assert "해당 없음" in report.risk_lines([])[0]


def test_summary_has_parse_warning() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({"bad.py": "def (:\n"})
    change_set = build_set(repo, diffparse.parse(make_diff("bad.py", "", "def (:\n", status="added")))
    assert any("파싱 실패" in line for line in report.summary_lines(change_set))


def test_limits_text() -> None:
    text = "\n".join(report.limits_lines())
    assert "판정하지 않음" in text and "커버리지" in text
