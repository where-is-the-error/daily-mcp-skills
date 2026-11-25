from shop.cart import Cart, empty_cart


def test_add(cart):
    assert cart.add("사과", 1000) == 1


def test_total():
    cart = Cart()
    cart.add("사과", 1000)
    assert cart.total() == 1100.0


def test_empty():
    assert empty_cart().items == []
