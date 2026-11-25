from shop.api import checkout


def test_checkout():
    assert checkout([("사과", 1000)]) == 1100.0
