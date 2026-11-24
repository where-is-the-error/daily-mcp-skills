from __future__ import annotations

from pathlib import Path

import pytest

from sheet_guard.table import build_from_text

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
RAW = EXAMPLES / "raw_population.csv"
XLSX = EXAMPLES / "merged_population.xlsx"


@pytest.fixture()
def raw_path() -> Path:
    return RAW


@pytest.fixture()
def xlsx_path() -> Path:
    return XLSX


@pytest.fixture()
def raw_table():
    from sheet_guard.table import load_table

    return load_table(RAW)


@pytest.fixture()
def simple_table():
    text = (
        "이름,나이,가입일\n"
        "김철수,31,2024-01-05\n"
        "이영희,28,2024-02-11\n"
        "박민수,45,2024-03-02\n"
    )
    return build_from_text(text, source="mem:simple")


def make(text: str, source: str = "mem:test"):
    return build_from_text(text, source=source)
