from invoice.extract import parse_lines
from invoice.utils import clean_int


def test_basic_table():
    text = (
        "لیمو شیرین | 0/590 | 1 | 23000 | 13570\n"
        "خیار شمال | 0/760 | - | 12600 | 9576\n"
        "TOTAL: 1669510\n"
    )
    inv = parse_lines(text)
    assert len(inv.items) == 2
    assert inv.items[0].name == "لیمو شیرین"
    assert clean_int(inv.grand_total) == 1669510


def test_markdown_strip():
    text = "| لیمو | 1 | 23000 | 13570 |\n"
    inv = parse_lines(text)
    assert inv.items[0].name == "لیمو"


def test_missing_total_derives_from_rows():
    text = "a | 1 | 10 | 100\nb | 1 | 10 | 200\n"
    inv = parse_lines(text)
    assert clean_int(inv.grand_total) == 300


def test_header_skipped():
    text = "نام کالا | وزن | تعداد | فی | جمع\nx | 1 | 1 | 10 | 10\n"
    inv = parse_lines(text)
    assert len(inv.items) == 1
