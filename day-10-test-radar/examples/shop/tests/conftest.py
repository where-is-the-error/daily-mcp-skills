import pytest


@pytest.fixture
def cart():
    from shop.cart import Cart
    return Cart()
