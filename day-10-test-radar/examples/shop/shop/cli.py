"""CLI."""

from shop.api import checkout


def main(argv=None):
    return checkout([("사과", 1000)])


if __name__ == "__main__":
    print(main())
