from invoice.utils import clean_int, normalize_digits


def test_persian_digits():
    assert normalize_digits("۱۲۳۴۵") == "12345"


def test_arabic_digits():
    assert normalize_digits("٦٧٨٩") == "6789"


def test_comma_separated():
    assert clean_int("1,669,510") == 1669510


def test_arabic_comma():
    assert clean_int("۱،۶۶۹،۵۱۰ تومان") == 1669510


def test_dot_grouped():
    assert clean_int("1.669.510") == 1669510


def test_decimal_small():
    assert clean_int("0.590") == 590


def test_zwnj_in_number():
    assert clean_int("13570\u200c") == 13570


def test_garbage():
    assert clean_int("n/a") == 0
    assert clean_int(None) == 0
