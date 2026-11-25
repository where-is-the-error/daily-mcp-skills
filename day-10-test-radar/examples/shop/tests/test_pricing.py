import pytest

from shop.pricing import total_for


@pytest.mark.parametrize("items,expected", [([], 0.0), ([("a", 100)], 110.0)])
def test_total_for(items, expected):
    assert total_for(items) == expected


@pytest.mark.skip(reason="아직")
def test_discount():
    assert False
