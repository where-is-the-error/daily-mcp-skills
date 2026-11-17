from __future__ import annotations

from repo_context import outline


def test_python_outline_uses_ast() -> None:
    source = (
        '"""모듈."""\n\n\nclass A:\n    """클래스."""\n\n    def method(self):\n        pass\n\n\n'
        "async def fetch(x):\n    pass\n"
    )
    symbols = outline.outline(source, "sample.py")
    assert [s.name for s in symbols] == ["A", "A.method", "fetch"]
    assert symbols[0].kind == "class"
    assert symbols[1].line == 7
    assert symbols[0].note == "클래스."


def test_python_syntax_error_falls_back_without_raising() -> None:
    symbols = outline.outline("def broken(:\n", "broken.py")
    assert isinstance(symbols, list)


def test_typescript_outline() -> None:
    source = (
        "export class Store {}\n"
        "export function greet(name: string) {}\n"
        "export const shout = (x: string) => x;\n"
        "export interface Config {}\n"
    )
    kinds = {s.name: s.kind for s in outline.outline(source, "web.ts")}
    assert kinds["Store"] == "class"
    assert kinds["greet"] == "function"
    assert kinds["shout"] == "arrow"
    assert kinds["Config"] == "interface"


def test_go_and_rust_outline() -> None:
    go = "func main() {}\nfunc (s *Server) Start() {}\ntype User struct {}\n"
    assert {s.name for s in outline.outline(go, "main.go")} == {"main", "Start", "User"}
    rust = "pub struct App;\npub async fn run() {}\nimpl App {}\n"
    assert {s.name for s in outline.outline(rust, "lib.rs")} >= {"App", "run"}


def test_unsupported_extension_returns_empty() -> None:
    assert outline.outline("hello", "notes.txt") == []


def test_render_symbols_marks_truncation() -> None:
    symbols = [outline.Symbol("def", f"f{i}", i + 1) for i in range(5)]
    rendered = outline.render_symbols(symbols, limit=3)
    assert rendered[0].startswith("- def `f0` (L1)")
    assert "2개 더" in rendered[-1]
