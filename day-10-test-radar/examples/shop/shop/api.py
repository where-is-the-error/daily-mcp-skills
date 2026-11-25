"""HTTP 진입점."""

from shop.cart import Cart


def checkout(names_prices):
    cart = Cart()
    for name, price in names_prices:
        cart.add(name, price)
    return cart.total()
