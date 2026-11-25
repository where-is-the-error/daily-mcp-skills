"""규칙 — 각 규칙이 실제로 무엇을 잡고 무엇을 안 잡는지."""

from __future__ import annotations

import pytest

from conftest import SHOP, make_diff, repo_with
from test_radar import diffparse, risk
from test_radar.select import build


def analyze(files: dict[str, str], path: str, old: str, new: str, status: str = "modified"):
    from test_radar.graph import load_sources
    repo = load_sources(files)
    change_set = build(repo, diffparse.parse(make_diff(path, old, new, status=status)))
    return change_set, risk.check(change_set)


def rules_of(risks) -> list[str]:
    return [item.rule for item in risks]


BASE = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def f():\n    return 1\n",
    "tests/test_core.py": "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n",
}


def test_catalog_size() -> None:
    assert len(risk.catalog()) == 23


def test_catalog_filter() -> None:
    rows = risk.catalog("dynamic-import")
    assert len(rows) == 1 and rows[0]["rule"] == "dynamic-import"


def test_catalog_unknown() -> None:
    assert risk.catalog("nope") == []


def test_catalog_fields() -> None:
    row = risk.catalog("test-weakened")[0]
    assert set(row) == {"rule", "severity", "title", "doc"}


def test_counts() -> None:
    risks = [risk.Risk("a", "치명", "t", "d"), risk.Risk("b", "참고", "t", "d")]
    tally = risk.counts(risks)
    assert tally["치명"] == 1 and tally["참고"] == 1 and tally["심각"] == 0


def test_verdict_fatal() -> None:
    assert risk.verdict([risk.Risk("a", "치명", "t", "d")], []) == "전체 실행"


def test_verdict_fallback() -> None:
    assert risk.verdict([], ["이유"]) == "전체 실행"


def test_verdict_serious() -> None:
    assert risk.verdict([risk.Risk("a", "심각", "t", "d")], []) == "선택 실행 + 심각 항목 확인"


def test_verdict_clean() -> None:
    assert risk.verdict([], []) == "선택 실행"


def test_risk_sorted_by_severity() -> None:
    risks = [risk.Risk("z", "참고", "t", "d"), risk.Risk("a", "치명", "t", "d")]
    order = [item.severity for item in sorted(risks, key=lambda r: risk.SEVERITIES.index(r.severity))]
    assert order == ["치명", "참고"]


# ------------------------------------------------------------- 개별 규칙
def test_test_config_changed() -> None:
    _, risks = analyze({**BASE, "conftest.py": "import pytest\n"},
                       "conftest.py", "import pytest\n", "import pytest\nimport os\n")
    assert "test-config-changed" in rules_of(risks)


def test_fixture_changed() -> None:
    _, risks = analyze({"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 1\n",
                        "tests/conftest.py": "import pytest\n",
                        "tests/test_core.py": "def test_x():\n    assert True\n"},
                       "tests/conftest.py", "import pytest\n", "import pytest\nimport os\n")
    assert "fixture-changed" in rules_of(risks)


def test_unparseable() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({**BASE, "pkg/core.py": "def f(:\n    return 1\n"})
    change_set = build(repo, diffparse.parse(make_diff("pkg/core.py", "def f():\n    return 1\n", "def f(:\n")))
    assert "unparseable-change" in rules_of(risk.check(change_set))


def test_dynamic_import() -> None:
    files = {**BASE, "pkg/core.py": "import importlib\n\ndef f():\n    return importlib.import_module('x')\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n",
                       "import importlib\n\ndef f():\n    return importlib.import_module('x')\n")
    assert "dynamic-import" in rules_of(risks)


def test_no_test_reaches() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 2\n",
             "tests/test_other.py": "def test_x():\n    assert True\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "no-test-reaches" in rules_of(risks)


def test_deleted_module_still_imported() -> None:
    files = {"pkg/__init__.py": "", "pkg/user.py": "from pkg.gone import f\n",
             "tests/test_user.py": "def test_x():\n    assert True\n"}
    _, risks = analyze(files, "pkg/gone.py", "def f():\n    return 1\n", "", status="deleted")
    assert "deleted-module-still-imported" in rules_of(risks)


def test_renamed_stale_import() -> None:
    files = {"pkg/__init__.py": "", "pkg/user.py": "from pkg.old import f\n",
             "pkg/new.py": "def f():\n    return 1\n",
             "tests/test_user.py": "def test_x():\n    assert True\n"}
    from test_radar.graph import load_sources
    repo = load_sources(files)
    diff = diffparse.parse(
        "diff --git a/pkg/old.py b/pkg/new.py\nsimilarity index 100%\n"
        "rename from pkg/old.py\nrename to pkg/new.py\n")
    change_set = build(repo, diff)
    assert "renamed-module-stale-import" in rules_of(risk.check(change_set))


def test_public_symbol_removed() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def g():\n    return 2\n",
             "pkg/user.py": "from pkg.core import f\n",
             "tests/test_core.py": "def test_x():\n    assert True\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n\ndef g():\n    return 2\n",
                       "def g():\n    return 2\n")
    assert "public-symbol-removed" in rules_of(risks)


def test_signature_changed() -> None:
    files = {**BASE, "pkg/core.py": "def f(x=1):\n    return x\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n", "def f(x=1):\n    return x\n")
    assert "signature-changed" in rules_of(risks)


def test_public_symbol_no_test() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def used():\n    return 1\n\ndef unused():\n    return 3\n",
             "tests/test_core.py": "from pkg.core import used\n\ndef test_u():\n    assert used() == 1\n"}
    _, risks = analyze(files, "pkg/core.py",
                       "def used():\n    return 1\n\ndef unused():\n    return 2\n",
                       "def used():\n    return 1\n\ndef unused():\n    return 3\n")
    assert "public-symbol-no-test" in rules_of(risks)


def test_high_fan_in() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 2\n"}
    for number in range(6):
        files[f"pkg/user{number}.py"] = "from pkg.core import f\n"
    files["tests/test_user0.py"] = "from pkg.user0 import *\n\ndef test_x():\n    assert True\n"
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "high-fan-in" in rules_of(risks)


def test_test_weakened_assert_removed() -> None:
    files = {**BASE, "tests/test_core.py": "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n"}
    _, risks = analyze(files, "tests/test_core.py",
                       "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n",
                       "from pkg.core import f\n\ndef test_f():\n    f()\n")
    assert "test-weakened" in rules_of(risks)


def test_test_weakened_skip_added() -> None:
    files = {**BASE, "tests/test_core.py": "import pytest\n\n@pytest.mark.skip\ndef test_f():\n    pass\n"}
    _, risks = analyze(files, "tests/test_core.py",
                       "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n",
                       "import pytest\n\n@pytest.mark.skip\ndef test_f():\n    pass\n")
    assert "test-weakened" in rules_of(risks)


def test_test_deleted() -> None:
    _, risks = analyze({"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 1\n"},
                       "tests/test_core.py", "from pkg.core import f\n", "", status="deleted")
    assert "test-deleted" in rules_of(risks)


def test_new_file_no_test() -> None:
    _, risks = analyze({**BASE, "pkg/extra.py": "def extra():\n    return 1\n"},
                       "pkg/extra.py", "", "def extra():\n    return 1\n", status="added")
    assert "new-file-no-test" in rules_of(risks)


def test_module_level_code() -> None:
    files = {**BASE, "pkg/core.py": "import os\n\nVALUE = os.environ.get('X', '1')\n\ndef f():\n    return 1\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n",
                       "import os\n\nVALUE = os.environ.get('X', '1')\n\ndef f():\n    return 1\n")
    found = rules_of(risks)
    assert "module-level-code" in found
    assert "env-or-network" in found


def test_entrypoint_changed() -> None:
    files = {"pkg/__init__.py": "", "pkg/cli.py": "def main():\n    return 2\n",
             "tests/test_cli.py": "def test_x():\n    assert True\n"}
    _, risks = analyze(files, "pkg/cli.py", "def main():\n    return 1\n", "def main():\n    return 2\n")
    assert "entrypoint-changed" in rules_of(risks)


def test_broad_except() -> None:
    files = {**BASE, "pkg/core.py": "def f():\n    try:\n        return 1\n    except:\n        pass\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n",
                       "def f():\n    try:\n        return 1\n    except:\n        pass\n")
    assert "broad-except" in rules_of(risks)


def test_nondeterminism() -> None:
    files = {**BASE, "pkg/core.py": "import time\n\ndef f():\n    time.sleep(1)\n    return 1\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n",
                       "import time\n\ndef f():\n    time.sleep(1)\n    return 1\n")
    assert "nondeterminism" in rules_of(risks)


def test_broad_test() -> None:
    files = {"pkg/__init__.py": ""}
    imports = ["from pkg.core import f"]
    for number in range(9):
        files[f"pkg/m{number}.py"] = f"X{number} = 1\n"
        imports.append(f"from pkg.m{number} import X{number}")
    files["pkg/core.py"] = "def f():\n    return 2\n"
    files["tests/test_broad.py"] = "\n".join(imports) + "\n\ndef test_x():\n    assert True\n"
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "broad-test" in rules_of(risks)


def test_constant_condition() -> None:
    files = {**BASE, "pkg/core.py": "def f():\n    if True:\n        return 1\n    return 2\n"}
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n",
                       "def f():\n    if True:\n        return 1\n    return 2\n")
    assert "constant-condition" in rules_of(risks)


def test_no_tests_in_repo() -> None:
    _, risks = analyze({"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 2\n"},
                       "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "no-tests-in-repo" in rules_of(risks)


def test_selection_too_broad() -> None:
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 2\n"}
    for number in range(12):
        files[f"tests/test_{number}.py"] = "from pkg.core import f\n\ndef test_f():\n    assert f() == 2\n"
    _, risks = analyze(files, "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "selection-too-broad" in rules_of(risks)


def test_clean_change_has_no_fatal() -> None:
    _, risks = analyze({**BASE}, "pkg/core.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
    assert "치명" not in [item.severity for item in risks]


def test_fatal_first() -> None:
    files = {**BASE, "pkg/core.py": "def f():\n    return 2\n", "conftest.py": "import pytest\nimport os\n"}
    _, risks = analyze(files, "conftest.py", "import pytest\n", "import pytest\nimport os\n")
    assert risks[0].severity == "치명"


def test_each_risk_has_fields() -> None:
    _, risks = analyze({**BASE, "pkg/cli.py": "def main():\n    return 2\n"},
                       "pkg/cli.py", "def main():\n    return 1\n", "def main():\n    return 2\n")
    for item in risks:
        assert item.rule and item.severity in risk.SEVERITIES and item.title and item.detail


def test_rule_survives_missing_module() -> None:
    """파일이 저장소에 없어도(삭제 등) 규칙이 죽지 않는다."""
    from test_radar.graph import load_sources
    repo = load_sources({"pkg/__init__.py": "", "tests/test_a.py": "def test_x():\n    assert True\n"})
    change_set = build(repo, diffparse.parse(make_diff("pkg/gone.py", "x = 1\n", "", status="deleted")))
    assert isinstance(risk.check(change_set), list)


def test_shop_conftest_fatal() -> None:
    repo = repo_with()
    change_set = build(repo, diffparse.parse(make_diff(
        "tests/conftest.py", SHOP["tests/conftest.py"], SHOP["tests/conftest.py"] + "\n# x\n")))
    risks = risk.check(change_set)
    assert "fixture-changed" in rules_of(risks)
