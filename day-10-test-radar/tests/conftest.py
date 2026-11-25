"""테스트 공용 — 디스크 없이 만드는 작은 상점 저장소와 diff 조립기."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_radar.graph import Repo, load_sources  # noqa: E402

SHOP: dict[str, str] = {
    "shop/__init__.py": '"""상점."""\n\nfrom shop.cart import Cart\n\n__all__ = ["Cart"]\n',
    "shop/cart.py": (
        '"""장바구니."""\n'
        "\n"
        "from shop.pricing import total_for\n"
        "\n"
        "\n"
        "class Cart:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "\n"
        "    def add(self, name, price):\n"
        "        self.items.append((name, price))\n"
        "        return len(self.items)\n"
        "\n"
        "    def total(self):\n"
        "        return total_for(self.items)\n"
        "\n"
        "\n"
        "def empty_cart():\n"
        "    return Cart()\n"
    ),
    "shop/pricing.py": (
        '"""가격."""\n'
        "\n"
        "TAX_RATE = 0.1\n"
        "\n"
        "\n"
        "def total_for(items):\n"
        "    subtotal = sum(price for _, price in items)\n"
        "    return round(subtotal * (1 + TAX_RATE), 2)\n"
        "\n"
        "\n"
        "def _discount(price, percent):\n"
        "    return price * (1 - percent / 100)\n"
    ),
    "shop/api.py": (
        '"""HTTP 진입점."""\n'
        "\n"
        "from shop.cart import Cart\n"
        "\n"
        "\n"
        "def checkout(names_prices):\n"
        "    cart = Cart()\n"
        "    for name, price in names_prices:\n"
        "        cart.add(name, price)\n"
        "    return cart.total()\n"
    ),
    "shop/cli.py": (
        '"""CLI."""\n'
        "\n"
        "from shop.api import checkout\n"
        "\n"
        "\n"
        "def main(argv=None):\n"
        "    return checkout([(\"사과\", 1000)])\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    print(main())\n"
    ),
    "tests/conftest.py": (
        "import pytest\n"
        "\n"
        "\n"
        "@pytest.fixture\n"
        "def cart():\n"
        "    from shop.cart import Cart\n"
        "    return Cart()\n"
    ),
    "tests/test_cart.py": (
        "from shop.cart import Cart, empty_cart\n"
        "\n"
        "\n"
        "def test_add(cart):\n"
        "    assert cart.add(\"사과\", 1000) == 1\n"
        "\n"
        "\n"
        "def test_total():\n"
        "    cart = Cart()\n"
        "    cart.add(\"사과\", 1000)\n"
        "    assert cart.total() == 1100.0\n"
        "\n"
        "\n"
        "def test_empty():\n"
        "    assert empty_cart().items == []\n"
    ),
    "tests/test_api.py": (
        "from shop.api import checkout\n"
        "\n"
        "\n"
        "def test_checkout():\n"
        "    assert checkout([(\"사과\", 1000)]) == 1100.0\n"
    ),
    "tests/test_pricing.py": (
        "import pytest\n"
        "\n"
        "from shop.pricing import total_for\n"
        "\n"
        "\n"
        "@pytest.mark.parametrize(\"items,expected\", [([], 0.0), ([(\"a\", 100)], 110.0)])\n"
        "def test_total_for(items, expected):\n"
        "    assert total_for(items) == expected\n"
        "\n"
        "\n"
        "@pytest.mark.skip(reason=\"아직\")\n"
        "def test_discount():\n"
        "    assert False\n"
    ),
    "tests/test_unrelated.py": (
        "def test_nothing():\n"
        "    assert True\n"
    ),
    "web/app.js": (
        "import { total } from '../shop/../web/lib/money.js';\n"
        "\n"
        "export function render(cart) {\n"
        "  return total(cart);\n"
        "}\n"
    ),
    "web/lib/money.js": (
        "export function total(cart) {\n"
        "  return cart.items.length;\n"
        "}\n"
    ),
    "web/__tests__/render.test.js": (
        "import { render } from '../app.js';\n"
        "\n"
        "test('renders a cart', () => {\n"
        "  expect(render({ items: [] })).toBe(0);\n"
        "});\n"
        "\n"
        "it.skip('renders empty', () => {});\n"
    ),
}


@pytest.fixture()
def repo() -> Repo:
    return load_sources(dict(SHOP))


def repo_with(**overrides: str) -> Repo:
    """바뀐 뒤의 작업 트리를 흉내 낸다 — diff 는 '옛 것 → 새 것'으로 준다."""
    files = dict(SHOP)
    files.update({key.replace("__", "/"): value for key, value in overrides.items()})
    return load_sources(files)


def make_diff(path: str, old: str, new: str, status: str = "modified",
              old_path: str = "", context: int = 3) -> str:
    """두 텍스트로 git 스타일 unified diff 를 만든다(테스트 전용)."""
    header = [f"diff --git a/{old_path or path} b/{path}"]
    if status == "added":
        header.append("new file mode 100644")
        header.append("--- /dev/null")
        header.append(f"+++ b/{path}")
        old_lines: list[str] = []
    elif status == "deleted":
        header.append("deleted file mode 100644")
        header.append(f"--- a/{path}")
        header.append("+++ /dev/null")
        old_lines = old.splitlines()
    elif status == "renamed":
        header.append(f"similarity index 100%")
        header.append(f"rename from {old_path or path}")
        header.append(f"rename to {path}")
        old_lines = old.splitlines()
    else:
        header.append("index 1111111..2222222 100644")
        header.append(f"--- a/{old_path or path}")
        header.append(f"+++ b/{path}")
        old_lines = old.splitlines()
    new_lines = [] if status == "deleted" else new.splitlines()
    body = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="",
            tofile="",
            n=context,
            lineterm="",
        )
    )
    if body:
        # difflib 은 첫 두 줄이 ---/+++ 이므로 hunk 부터만 쓴다
        start = 0
        for index, line in enumerate(body):
            if line.startswith("@@"):
                start = index
                break
        body = body[start:]
    lines = header + body
    return "\n".join(lines) + "\n"
