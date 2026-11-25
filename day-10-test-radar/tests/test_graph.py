"""저장소 그래프 — import 해석, 역방향 간선, 테스트 수집."""

from __future__ import annotations

import pytest

from conftest import SHOP
from test_radar.graph import load, load_sources
from test_radar.types import Module


def test_shop_summary(repo) -> None:
    info = repo.summary()
    assert info["tests"] == 5
    assert info["test_items"] > 0
    assert info["python"] > 0


def test_module_names(repo) -> None:
    assert repo.module("shop/cart.py").name == "shop.cart"
    assert repo.module("shop/__init__.py").name == "shop"


def test_absolute_import_resolved(repo) -> None:
    cart = repo.module("shop/cart.py")
    assert "shop/pricing.py" in cart.resolved


def test_imported_symbols_recorded(repo) -> None:
    cart = repo.module("shop/cart.py")
    assert "total_for" in cart.imported_symbols["shop/pricing.py"]


def test_package_reexport(repo) -> None:
    init = repo.module("shop/__init__.py")
    assert "shop/cart.py" in init.resolved


def test_reverse_edge(repo) -> None:
    assert "shop/cart.py" in repo.importers_of("shop/pricing.py")
    assert "shop/api.py" in repo.importers_of("shop/cart.py")


def test_fan_in_excludes_tests(repo) -> None:
    fan = repo.fan_in("shop/cart.py")
    assert fan >= 2                      # pricing? no — api, __init__
    assert all(not repo.is_test(path) for path in repo.importers_of("shop/cart.py", include_tests=False))


def test_transitive_importers(repo) -> None:
    found = repo.transitive_importers("shop/pricing.py", depth=2)
    assert found["shop/cart.py"] == 1
    assert found["shop/api.py"] == 2


def test_transitive_depth_limit(repo) -> None:
    found = repo.transitive_importers("shop/pricing.py", depth=1)
    assert "shop/api.py" not in found


def test_transitive_importers_include_tests(repo) -> None:
    found = repo.transitive_importers("shop/pricing.py", depth=3)
    assert "tests/test_cart.py" in found


def test_package_of(repo) -> None:
    assert repo.package_of("shop/cart.py") == "shop"
    assert repo.package_of("top.py") == "."


def test_is_test(repo) -> None:
    assert repo.is_test("tests/test_cart.py")
    assert not repo.is_test("shop/cart.py")


def test_test_items_collected(repo) -> None:
    test = repo.test("tests/test_cart.py")
    assert {item.name for item in test.items} == {"test_add", "test_total", "test_empty"}


def test_test_item_metadata(repo) -> None:
    test = repo.test("tests/test_pricing.py")
    by_name = {item.name: item for item in test.items}
    assert by_name["test_total_for"].parametrized is True
    assert by_name["test_discount"].skip is True


def test_conftest_flagged(repo) -> None:
    assert repo.test("tests/conftest.py").is_conftest is True


def test_test_file_imports(repo) -> None:
    test = repo.test("tests/test_cart.py")
    assert "shop/cart.py" in test.resolved
    assert "empty_cart" in test.imported_symbols["shop/cart.py"]


def test_test_weight(repo) -> None:
    assert repo.test("tests/test_cart.py").weight() == 3


def test_total_items(repo) -> None:
    assert repo.total_items() >= 6


def test_js_test_discovered(repo) -> None:
    test = repo.test("web/__tests__/render.test.js")
    assert test is not None
    assert {item.name for item in test.items} == {"renders a cart", "renders empty"}


def test_js_import_resolution(repo) -> None:
    module = repo.module("web/__tests__/render.test.js")
    assert "web/app.js" in module.resolved


def test_js_nested_import(repo) -> None:
    app = repo.module("web/app.js")
    assert "web/lib/money.js" in app.resolved


def test_js_import_names(repo) -> None:
    app = repo.module("web/app.js")
    assert "total" in app.imported_symbols["web/lib/money.js"]


def test_hidden_imports(repo) -> None:
    assert "pytest" in repo.hidden


def test_load_sources_ignores_unknown_suffix() -> None:
    repo = load_sources({"README.md": "# hi", "a.py": "x = 1\n"})
    assert list(repo.modules) == ["a.py"]


def test_src_layout_resolution() -> None:
    repo = load_sources({
        "src/pkg/__init__.py": "",
        "src/pkg/a.py": "def f():\n    return 1\n",
        "tests/test_a.py": "from pkg.a import f\n\ndef test_f():\n    assert f() == 1\n",
    })
    assert "src/pkg/a.py" in repo.module("tests/test_a.py").resolved


def test_relative_import_resolution() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "VALUE = 1\n",
        "pkg/b.py": "from .a import VALUE\n",
    })
    assert "pkg/a.py" in repo.module("pkg/b.py").resolved


def test_subpackage_relative() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/mod.py": "X = 1\n",
        "pkg/user.py": "from .sub.mod import X\n",
    })
    assert "pkg/sub/mod.py" in repo.module("pkg/user.py").resolved


def test_from_import_submodule() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/extra.py": "Y = 2\n",
        "pkg/user.py": "from pkg import extra\n",
    })
    assert "pkg/extra.py" in repo.module("pkg/user.py").resolved


def test_unresolved_from_import_submodule() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/user.py": "from pkg import missing\n",
    })
    assert "pkg/missing.py" not in repo.module("pkg/user.py").resolved


def test_star_import_marks_wildcard() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "A = 1\n",
        "pkg/b.py": "from pkg.a import *\n",
    })
    assert "*" in repo.module("pkg/b.py").imported_symbols["pkg/a.py"]


def test_parse_error_counted() -> None:
    repo = load_sources({"bad.py": "def (:\n", "ok.py": "x=1\n"})
    assert repo.summary()["parse_errors"] == 1


def test_load_from_disk(tmp_path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "core.py").write_text("CONST = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text(
        "from pkg.core import CONST\n\ndef test_c():\n    assert CONST == 1\n", encoding="utf-8")
    repo = load(tmp_path)
    assert repo.module("pkg/core.py") is not None
    assert repo.test("tests/test_core.py") is not None
    assert "pkg/core.py" in repo.test("tests/test_core.py").resolved


def test_load_skips_node_modules(tmp_path) -> None:
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "index.js").write_text("require('./y')", encoding="utf-8")
    (tmp_path / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    repo = load(tmp_path)
    assert "app.js" in repo.modules
    assert not any(path.startswith("node_modules") for path in repo.modules)


def test_load_missing_root(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "없는디렉터리")


def test_load_include_filter(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "y.py").write_text("y=1\n", encoding="utf-8")
    repo = load(tmp_path, include=["a"])
    assert "a/x.py" in repo.modules
    assert "b/y.py" not in repo.modules


def test_duplicate_import_single_edge() -> None:
    repo = load_sources({
        "pkg/__init__.py": "",
        "pkg/a.py": "A=1\n",
        "pkg/b.py": "from pkg.a import A\nfrom pkg import a\n",
    })
    assert "pkg/a.py" in repo.module("pkg/b.py").resolved


def test_module_type() -> None:
    assert isinstance(Module(path="x.py", name="x"), Module)


def test_js_index_resolution() -> None:
    repo = load_sources({
        "web/lib/index.js": "export const x = 1;\n",
        "web/app.js": "import { x } from './lib';\n",
    })
    assert "web/lib/index.js" in repo.module("web/app.js").resolved


def test_alias_resolution() -> None:
    repo = load_sources({
        "src/util/date.js": "export const d = 1;\n",
        "src/app.js": "import { d } from '@/util/date';\n",
    })
    assert "src/util/date.js" in repo.module("src/app.js").resolved


def test_no_self_edge() -> None:
    repo = load_sources({"a.py": "import a\n"})
    assert repo.importers_of("a.py") == set()


def test_summary_keys(repo) -> None:
    info = repo.summary()
    for key in ("root", "modules", "files", "tests", "test_items", "python", "javascript"):
        assert key in info


def test_shop_files_present(repo) -> None:
    for path in SHOP:
        assert path in repo.modules
