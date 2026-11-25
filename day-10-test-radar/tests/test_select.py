"""선택 — 어떤 근거로 어떤 테스트를 고르는가."""

from __future__ import annotations

import pytest

from conftest import SHOP, make_diff, repo_with
from test_radar import diffparse
from test_radar.select import build


def build_set(repo, text: str):
    return build(repo, diffparse.parse(text))


def diff_for(path: str, old: str | None = None, new: str | None = None) -> str:
    old = SHOP[path] if old is None else old
    new = SHOP[path] if new is None else new
    return make_diff(path, old, new)


# ------------------------------------------------------------------ 직접
def test_direct_import_selected(repo) -> None:
    text = diff_for("shop/pricing.py",
                    SHOP["shop/pricing.py"].replace("0.1", "0.12"),
                    SHOP["shop/pricing.py"].replace("0.1", "0.12"))
    change_set = build_set(repo, text)
    assert "tests/test_pricing.py" in change_set.selections


def test_direct_reason_names_symbol(repo) -> None:
    new = SHOP["shop/pricing.py"].replace("round(subtotal * (1 + TAX_RATE), 2)",
                                          "return subtotal")
    change_set = build_set(repo, make_diff("shop/pricing.py", SHOP["shop/pricing.py"], new))
    sel = change_set.selections["tests/test_pricing.py"]
    assert sel.level == 1
    assert "total_for" in sel.reason


def test_direct_module_reason(repo) -> None:
    new = SHOP["shop/cart.py"] + "\n\n# 주석\n"
    change_set = build_set(repo, make_diff("shop/cart.py", SHOP["shop/cart.py"], new))
    sel = change_set.selections["tests/test_cart.py"]
    assert "직접 import" in sel.reason


def test_star_import_reason(repo) -> None:
    repo = repo
    text = make_diff("shop/pricing.py", SHOP["shop/pricing.py"],
                     SHOP["shop/pricing.py"].replace("0.1", "0.2"))
    change_set = build_set(repo, text)
    assert change_set.selections["tests/test_pricing.py"].level == 1


def test_symbol_string_reference(repo) -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "app/__init__.py": "",
        "app/jobs.py": "def run():\n    return 1\n",
        "tests/test_jobs.py": (
            "def test_run(monkeypatch):\n"
            "    monkeypatch.setattr('app.jobs.run', lambda: 2)\n"
            "    assert True\n"
        ),
    })
    change_set = build(small, diffparse.parse(
        make_diff("app/jobs.py", "def run():\n    return 1\n", "def run():\n    return 2\n")))
    sel = change_set.selections["tests/test_jobs.py"]
    assert sel.level == 1
    assert "문자열" in sel.reason


# ---------------------------------------------------------------- 전이
def test_transitive_level(repo) -> None:
    change_set = build_set(repo, diff_for(
        "shop/pricing.py",
        SHOP["shop/pricing.py"],
        SHOP["shop/pricing.py"].replace("0.1", "0.15")))
    sel = change_set.selections["tests/test_cart.py"]
    assert sel.level == 2
    assert "전이" in sel.reason


def test_distance_three_not_selected_by_default() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/base.py": "def f():\n    return 1\n",
        "pkg/mid.py": "from pkg.base import f\n\ndef g():\n    return f()\n",
        "pkg/top.py": "from pkg.mid import g\n\ndef h():\n    return g()\n",
        "tests/test_top.py": "from pkg.top import h\n\ndef test_h():\n    assert h() == 1\n",
    })
    diff = diffparse.parse(make_diff("pkg/base.py", "def f():\n    return 1\n", "def f():\n    return 2\n"))
    assert "tests/test_top.py" not in build(small, diff).selections
    deeper = build(small, diff, depth=3)
    assert deeper.selections["tests/test_top.py"].level == 3
    assert deeper.selections["tests/test_top.py"].mandatory is False


def test_distance_two_selected() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/base.py": "def f():\n    return 1\n",
        "pkg/mid.py": "from pkg.base import f\n\ndef g():\n    return f()\n",
        "tests/test_mid.py": "from pkg.mid import g\n\ndef test_g():\n    assert g() == 1\n",
    })
    change_set = build(small, diffparse.parse(
        make_diff("pkg/base.py", "def f():\n    return 1\n", "def f():\n    return 2\n")))
    assert change_set.selections["tests/test_mid.py"].level == 2


def test_same_directory_is_optional(repo) -> None:
    change_set = build_set(repo, diff_for(
        "shop/cart.py", SHOP["shop/cart.py"], SHOP["shop/cart.py"] + "\n# c\n"))
    # tests 디렉터리는 shop 과 다르므로 같은 디렉터리 선택 없음
    assert all(sel.level != 3 for sel in change_set.selections.values())


def test_same_package_optional() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "def f():\n    return 3\n",
        "pkg/test_local.py": "def test_x():\n    assert True\n",
    })
    change_set = build(small, diffparse.parse(
        make_diff("pkg/a.py", "def f():\n    return 1\n", "def f():\n    return 3\n")))
    sel = change_set.selections["pkg/test_local.py"]
    assert sel.level == 3
    assert sel.mandatory is False


# ---------------------------------------------------------------- 테스트 자체
def test_changed_test_selected(repo) -> None:
    old = SHOP["tests/test_cart.py"]
    change_set = build_set(repo, make_diff("tests/test_cart.py", old, old + "\n# 손봄\n"))
    sel = change_set.selections["tests/test_cart.py"]
    assert sel.level == 0
    assert "테스트 파일" in sel.reason


def test_conftest_selects_directory(repo) -> None:
    old = SHOP["tests/conftest.py"]
    change_set = build_set(repo, make_diff("tests/conftest.py", old, old + "\n# fixture\n"))
    assert change_set.selections["tests/test_cart.py"].level == 0
    assert "fixture" in change_set.selections["tests/test_cart.py"].reason
    assert "tests/conftest.py" not in change_set.selections


def test_root_conftest_selects_all() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "conftest.py": "import pytest\n",
        "tests/test_a.py": "def test_a():\n    assert True\n",
        "other/test_b.py": "def test_b():\n    assert True\n",
    })
    change_set = build(small, diffparse.parse(make_diff("conftest.py", "import pytest\n", "import pytest\nimport os\n")))
    assert change_set.selections["tests/test_a.py"].level == 0
    assert change_set.selections["other/test_b.py"].level == 0


def test_deleted_test_file(repo) -> None:
    old = SHOP["tests/test_unrelated.py"]
    change_set = build_set(repo, make_diff("tests/test_unrelated.py", old, "", status="deleted"))
    assert "tests/test_unrelated.py" in change_set.selections


def test_deleted_module_tests_selected(repo) -> None:
    text = "diff --git a/shop/pricing.py b/shop/pricing.py\ndeleted file mode 100644\n--- a/shop/pricing.py\n+++ /dev/null\n@@ -1,15 +0,0 @@\n-TAX_RATE = 0.1\n"
    change_set = build_set(repo, text)
    assert "tests/test_cart.py" in change_set.selections


# ------------------------------------------------------------------ 구멍
def test_new_file_without_test_gap(repo) -> None:
    change_set = build_set(repo, make_diff("shop/newmod.py", "",
                                           "def thing():\n    return 1\n", status="added"))
    kinds = {gap["kind"] for gap in change_set.gaps}
    assert "new-module" in kinds


def test_changed_file_without_test_gap(repo) -> None:
    new = SHOP["shop/pricing.py"] + "\n\ndef extra():\n    return 1\n"
    change_set = build_set(repo, make_diff("shop/pricing.py", SHOP["shop/pricing.py"], new))
    assert all(gap["path"] != "shop/pricing.py" for gap in change_set.gaps if gap["kind"] == "no-test")


def test_unreferenced_symbol_gap() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "def used():\n    return 1\n\ndef unused():\n    return 2\n",
        "tests/test_a.py": "from pkg.a import used\n\ndef test_used():\n    assert used() == 1\n",
    })
    new = "def used():\n    return 1\n\ndef unused():\n    return 3\n"
    change_set = build(small, diffparse.parse(make_diff("pkg/a.py",
                                                        "def used():\n    return 1\n\ndef unused():\n    return 2\n", new)))
    symbols = {gap.get("symbol") for gap in change_set.gaps if gap["kind"] == "unreferenced-symbol"}
    assert "unused" in symbols


def test_no_gap_when_symbol_referenced() -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "def used():\n    return 1\n",
        "tests/test_a.py": "from pkg.a import used\n\ndef test_used():\n    assert used() == 1\n",
    })
    change_set = build(small, diffparse.parse(make_diff("pkg/a.py", "def used():\n    return 1\n",
                                                        "def used():\n    return 7\n")))
    assert change_set.gaps == []


# ---------------------------------------------------------------- 폴백
def test_fallback_on_test_config(repo) -> None:
    new = SHOP["tests/conftest.py"] + "\n# 추가\n"
    change_set = build_set(repo, make_diff("tests/conftest.py", SHOP["tests/conftest.py"], new))
    assert any("테스트 실행 방식" in reason or "conftest" in reason for reason in change_set.fallback)


def test_fallback_on_parse_error(repo) -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "def f(:\n    return 1\n",
        "tests/test_a.py": "from pkg.a import f\n\ndef test_f():\n    assert f() == 1\n",
    })
    change_set = build(small, diffparse.parse(make_diff(
        "pkg/a.py", "def f():\n    return 1\n", "def f(:\n    return 1\n")))
    assert any("파싱" in reason for reason in change_set.fallback)


def test_fallback_on_dynamic_import(repo) -> None:
    from test_radar.graph import load_sources
    small = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "import importlib\n\ndef load(name):\n    return importlib.import_module(name + '1')\n",
        "tests/test_a.py": "from pkg.a import load\n\ndef test_load():\n    assert load\n",
    })
    change_set = build(small, diffparse.parse(make_diff(
        "pkg/a.py", "import importlib\n\ndef load(name):\n    return importlib.import_module(name)\n",
        "import importlib\n\ndef load(name):\n    return importlib.import_module(name + '1')\n")))
    assert any("동적" in reason for reason in change_set.fallback)


def test_fallback_when_no_tests() -> None:
    from test_radar.graph import load_sources
    repo = load_sources({"pkg/a.py": "def f():\n    return 1\n"})
    change_set = build(repo, diffparse.parse(make_diff("pkg/a.py", "def f():\n    return 1\n",
                                                       "def f():\n    return 2\n")))
    assert any("테스트 파일을" in reason for reason in change_set.fallback)


def test_fallback_when_broad() -> None:
    from test_radar.graph import load_sources
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 1\n"}
    for number in range(12):
        files[f"tests/test_{number}.py"] = (
            "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n")
    repo = load_sources(files)
    change_set = build(repo, diffparse.parse(make_diff("pkg/core.py", "def f():\n    return 1\n",
                                                       "def f():\n    return 3\n")))
    assert any("전체의" in reason for reason in change_set.fallback)


def test_no_fallback_narrow(repo) -> None:
    from test_radar.graph import load_sources
    files = {"pkg/__init__.py": "", "pkg/core.py": "def f():\n    return 1\n",
             "pkg/other.py": "def g():\n    return 2\n"}
    for number in range(12):
        files[f"tests/test_{number}.py"] = (
            "from pkg.core import f\n\ndef test_f():\n    assert f() == 1\n")
    files["tests/test_other.py"] = "from pkg.other import g\n\ndef test_g():\n    assert g() == 2\n"
    repo = load_sources(files)
    change_set = build(repo, diffparse.parse(make_diff("pkg/other.py", "def g():\n    return 2\n",
                                                       "def g():\n    return 3\n")))
    assert change_set.fallback == []


# ------------------------------------------------------------------ 숫자
def test_share(repo) -> None:
    change_set = build_set(repo, diff_for("shop/pricing.py"))
    assert 0 < change_set.share() <= 1


def test_selected_items(repo) -> None:
    change_set = build_set(repo, diff_for("shop/pricing.py"))
    assert change_set.selected_items() >= 1


def test_mandatory_only_paths(repo) -> None:
    change_set = build_set(repo, diff_for("shop/pricing.py"))
    assert all(change_set.selections[path].mandatory for path in change_set.selected_paths(True))


def test_untested_file_has_no_selection(repo) -> None:
    old = SHOP["shop/cli.py"]
    change_set = build_set(repo, make_diff("shop/cli.py", old, old + "\n# 손봄\n"))
    assert change_set.selections == {}


def test_binary_note(repo) -> None:
    text = "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"
    change_set = build_set(repo, text)
    assert any("바이너리" in note for note in change_set.notes)


def test_mode_only_note(repo) -> None:
    text = "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
    change_set = build_set(repo, text)
    assert any("실행 권한" in note for note in change_set.notes)


# ------------------------------------------------------------------ 뷰
def test_symbols_touched(repo) -> None:
    old = SHOP["shop/pricing.py"]
    new = old.replace("return round(subtotal * (1 + TAX_RATE), 2)",
                      "return round(subtotal * (1 + TAX_RATE), 3)")
    change_set = build_set(repo, make_diff("shop/pricing.py", old, new))
    view = change_set.views[0]
    assert [symbol.name for symbol in view.symbols] == ["total_for"]


def test_removed_defs(repo) -> None:
    old = SHOP["shop/pricing.py"]
    new = old.replace("def _discount(price, percent):\n    return price * (1 - percent / 100)\n", "")
    change_set = build_set(repo, make_diff("shop/pricing.py", old, new))
    assert "_discount" in change_set.views[0].removed_defs


def test_signature_changes() -> None:
    old = SHOP["shop/pricing.py"]
    new = old.replace("def total_for(items):", "def total_for(items, rate=TAX_RATE):")
    after = repo_with(**{"shop__pricing.py": new})
    change_set = build(after, diffparse.parse(make_diff("shop/pricing.py", old, new)))
    assert change_set.views[0].signature_changes
    name, before, after = change_set.views[0].signature_changes[0]
    assert name == "total_for"
    assert "items" in before and "rate" in after


def test_view_module_name(repo) -> None:
    change_set = build_set(repo, diff_for("shop/pricing.py"))
    assert change_set.views[0].module_name == "shop.pricing"


def test_ref_default_empty(repo) -> None:
    assert build_set(repo, diff_for("shop/pricing.py")).ref == ""


def test_selection_upgrades(repo) -> None:
    """여러 파일이 같은 테스트를 가리키면 더 강한 근거를 남긴다."""
    old = SHOP["shop/cart.py"]
    new = old + "\n# c\n"
    text = make_diff("shop/cart.py", old, new) + make_diff("shop/pricing.py", SHOP["shop/pricing.py"],
                                                           SHOP["shop/pricing.py"].replace("0.1", "0.2"))
    change_set = build_set(repo, text)
    assert change_set.selections["tests/test_cart.py"].level <= 2
