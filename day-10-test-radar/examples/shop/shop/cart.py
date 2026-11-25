"""장바구니."""

from shop.pricing import total_for


class Cart:
    def __init__(self):
        self.items = []

    def add(self, name, price):
        self.items.append((name, price))
        return len(self.items)

    def total(self):
        return total_for(self.items)


def empty_cart():
    return Cart()
