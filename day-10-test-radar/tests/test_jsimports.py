"""JS/TS 읽기 — import·require·export·테스트 선언."""

from __future__ import annotations

import pytest

from test_radar import jsimports

SOURCE = """import React from 'react';
import { total, sum } from './money.js';
import * as helpers from "../lib/helpers";
import './side-effect.css';
export { a, b } from './letters.js';

const { readFile } = require('node:fs');
const path = require('path');

export function render(cart) {
  return total(cart);
}

export class View {
  draw() {}
}

export const mount = (node) => node;

export default function App() {}
"""


@pytest.fixture()
def module():
    return jsimports.parse_module("web/app.jsx", SOURCE)


def test_js_suffix_detection() -> None:
    assert jsimports.is_js("a.js") and jsimports.is_js("a.tsx") and jsimports.is_js("a.mjs")
    assert not jsimports.is_js("a.py") and not jsimports.is_js("a.json")


def test_import_specifiers(module) -> None:
    specifiers = [ref.module for ref in module.imports]
    assert "react" in specifiers
    assert "./money.js" in specifiers
    assert "../lib/helpers" in specifiers
    assert "./side-effect.css" in specifiers
    assert "./letters.js" in specifiers


def test_import_names(module) -> None:
    money = [ref for ref in module.imports if ref.module == "./money.js"][0]
    assert money.names == ("total", "sum")


def test_require_destructuring(module) -> None:
    fs = [ref for ref in module.imports if ref.module == "node:fs"][0]
    assert fs.names == ("readFile",)


def test_default_require(module) -> None:
    assert any(ref.module == "path" for ref in module.imports)


def test_import_line_numbers(module) -> None:
    numbers = [ref.lineno for ref in module.imports]
    assert numbers == sorted(numbers)
    assert numbers[0] == 1


def test_no_duplicate_refs() -> None:
    module = jsimports.parse_module("x.js", "const a = require('./m');\nrequire('./m');\n")
    assert len([ref for ref in module.imports if ref.module == "./m"]) == 2  # 줄이 다르면 각각


def test_dynamic_require_flag() -> None:
    module = jsimports.parse_module("x.js", "const name = './m'; require(name);\n")
    assert module.dynamic_import is True


def test_dynamic_import_flag() -> None:
    module = jsimports.parse_module("x.js", "async function go(n){ return import(n); }\n")
    assert module.dynamic_import is True


def test_static_only_not_dynamic() -> None:
    module = jsimports.parse_module("x.js", "import a from './a';\n")
    assert module.dynamic_import is False


def test_function_symbols(module) -> None:
    names = {symbol.name for symbol in module.symbols}
    assert {"render", "View", "mount", "App"} <= names


def test_symbol_kinds(module) -> None:
    kinds = {symbol.name: symbol.kind for symbol in module.symbols}
    assert kinds["render"] == "function"
    assert kinds["View"] == "class"


def test_export_declarations(module) -> None:
    assert {"render", "View", "mount", "App"} <= set(module.exports)


def test_export_list(module) -> None:
    assert {"a", "b"} <= set(module.exports)


def test_language_and_name(module) -> None:
    assert module.language == "javascript"
    assert module.name == "web/app.jsx"


def test_lines_counted(module) -> None:
    assert module.lines == SOURCE.count("\n")


@pytest.mark.parametrize("source,expected", [
    ("test('a', () => {});", ["a"]),
    ("it('b', function () {});", ["b"]),
    ("describe('group', () => {});", ["group"]),
    ("test.skip('c', () => {});", ["c"]),
    ("xit('d', () => {});", ["d"]),
    ("specify(`e`, () => {});", ["e"]),
])
def test_test_items(source: str, expected: list[str]) -> None:
    items = jsimports.test_items("a.test.js", source)
    assert [item.name for item in items] == expected


def test_skip_flag() -> None:
    items = jsimports.test_items("a.test.js", "test.skip('c', () => {});\ntest.todo('d');\n")
    assert all(item.skip for item in items)


def test_no_skip_flag() -> None:
    items = jsimports.test_items("a.test.js", "test('ok', () => {});\n")
    assert items[0].skip is False


def test_test_item_line_numbers() -> None:
    items = jsimports.test_items("a.test.js", "\n\ntest('x', () => {});\n")
    assert items[0].lineno == 3


def test_test_item_path() -> None:
    items = jsimports.test_items("web/__tests__/a.test.js", "test('x', () => {});")
    assert items[0].path == "web/__tests__/a.test.js"


def test_describe_nested_not_split() -> None:
    source = "describe('outer', () => {\n  test('inner', () => {});\n});\n"
    names = [item.name for item in jsimports.test_items("a.test.js", source)]
    assert names == ["outer", "inner"]


def test_empty_source() -> None:
    module = jsimports.parse_module("x.js", "")
    assert module.imports == [] and module.symbols == []
