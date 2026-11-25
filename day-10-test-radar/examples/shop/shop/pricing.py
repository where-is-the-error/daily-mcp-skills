"""가격."""

TAX_RATE = 0.1


def total_for(items):
    subtotal = sum(price for _, price in items)
    return round(subtotal * (1 + TAX_RATE), 2)


def _discount(price, percent):
    return price * (1 - percent / 100)
