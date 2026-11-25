# examples/shop — 예제 저장소 (13파일)

`test-radar` 를 바로 돌려 보기 위한 작은 상점 코드입니다. 실제로 pytest 로 돌아갑니다.

```text
shop/
  __init__.py     Cart 를 다시 내보냄
  cart.py         Cart (add · total) · empty_cart
  pricing.py      TAX_RATE · total_for · _discount
  api.py          checkout
  cli.py          main + if __name__ == "__main__"
tests/
  conftest.py     cart fixture
  test_cart.py    test_add · test_total · test_empty
  test_api.py     test_checkout
  test_pricing.py test_total_for(parametrize) · test_discount(skip)
  test_unrelated.py test_nothing
web/
  app.js          render → lib/money.js
  lib/money.js    total
  __tests__/render.test.js  test · it.skip
```

## 세금 한 줄만 바꿔 보기

`shop.patch` 는 `TAX_RATE = 0.1` → `0.12` 한 줄짜리 diff 입니다.

```bash
python -m test_radar.cli scan examples/shop --diff examples/shop.patch
```

```text
선택: 2파일 · 5/9항목 (56%)
   ● tests/test_pricing.py  L1 직접  바뀐 모듈을 직접 import
   ◐ tests/test_cart.py  L2 전이  2단계 전이 import
위험 규칙: 참고 1 — 모듈 최상위 실행 코드 (import 하는 순간 실행되는 줄 1개 변경)
판정: 선택 실행
```

`test_api.py` 는 `shop.api` 를 import 하고, `shop.api` 는 `shop.cart` 를 import 합니다.
`shop.cart` 는 `shop.pricing` 을 import 하므로 3단계 — 기본 `depth=2` 로는 선택되지 않습니다.
conftest 를 건드리면 그 디렉터리 테스트가 L0 으로 전부 선택되고,
`fixture-changed`(`주의`) · `test-config-changed`(`치명`) 규칙이 붙어 `판정: 전체 실행` 이 됩니다.


예제는 실제 pytest 로 돌아갑니다 — `7 passed, 1 skipped`:

```bash
cd examples/shop && python -m pytest -q
```
