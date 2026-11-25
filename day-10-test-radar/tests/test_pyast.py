"""Python 파일 읽기 — 모듈 이름, import, 심볼, 최상위 실행 줄, 문자열 참조."""

from __future__ import annotations

import pytest

from test_radar import pyast

SOURCE = '''"""모듈 설명."""

import os
import os.path as osp
from collections import OrderedDict
from . import sibling
from ..pkg import thing as other
from shop.cart import Cart, empty_cart
from .sub import *

TAX_RATE = 0.1
__all__ = ["Cart", "helper"]


def helper(a, b=1, *args, c: int = 2, **kwargs):
    """도움."""
    value = "shop.cart.Cart"
    return a + b


async def fetch(url):
    return url


class Cart:
    limit = 10

    def add(self, name):
        return name

    class Inner:
        pass


def _private():
    pass
'''


@pytest.fixture()
def module():
    return pyast.parse_module("shop/core.py", SOURCE, "shop.core", ".")


@pytest.mark.parametrize("path,expected", [
    ("shop/cart.py", "shop.cart"),
    ("shop/__init__.py", "shop"),
    ("src/shop/cart.py", "shop.cart"),
    ("lib/shop/cart.py", "shop.cart"),
    ("top.py", "top"),
    ("a/b/c.py", "a.b.c"),
    ("tests/test_cart.py", "tests.test_cart"),
])
def test_module_name(path: str, expected: str) -> None:
    assert pyast.module_name(path, ".", path.endswith("__init__.py")) == expected


def test_imports_recorded(module) -> None:
    names = [ref.module for ref in module.imports]
    assert "os" in names
    assert "shop.cart" in names
    assert "sub" in names


def test_relative_import_level(module) -> None:
    relative = [ref for ref in module.imports if ref.level]
    assert {ref.level for ref in relative} == {1, 2}


def test_from_import_names(module) -> None:
    cart = [ref for ref in module.imports if ref.module == "shop.cart"][0]
    assert cart.names == ("Cart", "empty_cart")


def test_star_import(module) -> None:
    sub = [ref for ref in module.imports if ref.module == "sub"][0]
    assert sub.is_star is True
    assert sub.names == ()


def test_import_line_numbers_ordered(module) -> None:
    numbers = [ref.lineno for ref in module.imports]
    assert numbers == sorted(numbers)


def test_symbol_kinds(module) -> None:
    kinds = {symbol.qualname: symbol.kind for symbol in module.symbols}
    assert kinds["helper"] == "function"
    assert kinds["fetch"] == "function"
    assert kinds["Cart"] == "class"
    assert kinds["Cart.add"] == "method"
    assert kinds["Cart.Inner"] == "class"
    assert kinds["TAX_RATE"] == "constant"


def test_symbol_end_lines(module) -> None:
    helper = module.symbol("helper")
    assert helper.end_lineno > helper.lineno
    cart = module.symbol("Cart")
    inner = module.symbol("Cart.Inner")
    assert cart.lineno < inner.lineno <= cart.end_lineno


def test_signature_text(module) -> None:
    helper = module.symbol("helper")
    assert helper.signature.startswith("(a, b=1")
    assert "*args" in helper.signature
    assert "**kwargs" in helper.signature


def test_params_tuple(module) -> None:
    assert module.symbol("helper").params == ("a", "b", "args", "c", "kwargs")


def test_public_flags(module) -> None:
    assert module.symbol("Cart").is_public
    assert module.symbol("_private").is_public is False
    assert module.symbol("Cart.add").is_public is True


def test_parent_links(module) -> None:
    assert module.symbol("Cart.add").parent == "Cart"
    assert module.symbol("Cart.Inner").parent == "Cart"


def test_module_docstring_not_top_level_code(module) -> None:
    assert 1 not in module.top_level_lines


def test_constant_is_top_level_code(module) -> None:
    assert 12 in module.top_level_lines


def test_strings_only_dotted() -> None:
    module = pyast.parse_module("x.py", 'A = "shop.cart.Cart"\nB = "short"\nC = "a::b"\n', "x", ".")
    assert "shop.cart.Cart" in module.strings
    assert "a::b" in module.strings
    assert "short" not in module.strings


def test_exports(module) -> None:
    assert module.exports == ("Cart", "helper")


def test_exports_absent() -> None:
    module = pyast.parse_module("x.py", "def f():\n    pass\n", "x", ".")
    assert module.exports == ()


def test_parse_error_recorded() -> None:
    module = pyast.parse_module("bad.py", "def broken(:\n", "bad", ".")
    assert module.parse_error
    assert "SyntaxError" in module.parse_error


def test_parse_error_keeps_name() -> None:
    module = pyast.parse_module("bad.py", "class (: pass\n", "bad", ".")
    assert module.name == "bad"
    assert module.symbols == []


def test_dynamic_import_flag() -> None:
    module = pyast.parse_module("x.py", "import importlib\nimportlib.import_module('m')\n", "x", ".")
    assert module.dynamic_import is True


def test_dunder_import_flag() -> None:
    module = pyast.parse_module("x.py", "m = __import__('shop')\n", "x", ".")
    assert module.dynamic_import is True


def test_no_dynamic_import() -> None:
    module = pyast.parse_module("x.py", "import os\n", "x", ".")
    assert module.dynamic_import is False


def test_lines_counted() -> None:
    module = pyast.parse_module("x.py", "a\nb\nc\n", "x", ".")
    assert module.lines == 3


def test_empty_source() -> None:
    module = pyast.parse_module("x.py", "", "x", ".")
    assert module.symbols == []
    assert module.parse_error == ""


def test_package_flag() -> None:
    module = pyast.parse_module("shop/__init__.py", "", "shop", ".")
    assert module.is_package is True


def test_decorators_captured() -> None:
    module = pyast.parse_module(
        "x.py", "import pytest\n@pytest.mark.skip(reason='x')\ndef test_a():\n    pass\n", "x", ".")
    symbol = module.symbol("test_a")
    assert any("skip" in dec for dec in symbol.decorators)


def test_symbol_at() -> None:
    module = pyast.parse_module("x.py", "def f():\n    a = 1\n    return a\n\ndef g():\n    pass\n", "x", ".")
    assert module.symbol_at(2).name == "f"
    assert module.symbol_at(6).name == "g"


def test_symbol_at_outside() -> None:
    module = pyast.parse_module("x.py", "X = 1\n\ndef f():\n    pass\n", "x", ".")
    assert module.symbol_at(2) is None


def test_class_level_constant_is_symbol() -> None:
    module = pyast.parse_module("x.py", "class C:\n    LIMIT = 3\n", "x", ".")
    assert module.symbol("LIMIT") is not None


def test_annotated_constant() -> None:
    module = pyast.parse_module("x.py", "MAX: int = 10\n", "x", ".")
    assert module.symbol("MAX").kind == "constant"


def test_async_function_signature() -> None:
    module = pyast.parse_module("x.py", "async def run(x, *, y=2):\n    pass\n", "x", ".")
    assert module.symbol("run").params == ("x", "y")


def test_find_defs_in_text() -> None:
    text = " def foo(a):\n-class Bar:\n+def baz():\n"
    assert pyast.find_defs_in_text(text) == ["foo", "Bar", "baz"]


def test_find_defs_async() -> None:
    assert pyast.find_defs_in_text("-async def go(x):") == ["go"]


def test_find_defs_empty() -> None:
    assert pyast.find_defs_in_text("x = 1\n") == []


def test_parse_file(tmp_path) -> None:
    path = tmp_path / "pkg"
    path.mkdir()
    (path / "__init__.py").write_text("", encoding="utf-8")
    (path / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    module = pyast.parse_file("pkg/mod.py", tmp_path)
    assert module.name == "pkg.mod"
    assert module.symbol("f") is not None


def test_parse_file_non_utf8(tmp_path) -> None:
    (tmp_path / "cp.py").write_text("# 한글\n", encoding="cp949")
    module = pyast.parse_file("cp.py", tmp_path)
    assert module.parse_error == ""


def test_import_refs_sorted_by_line(module) -> None:
    lines = [ref.lineno for ref in module.imports]
    assert lines == sorted(lines)
