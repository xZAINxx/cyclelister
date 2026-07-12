from app.services.catalog import normalize_part_number


def test_uppercases():
    assert normalize_part_number("3g2-83312-00") == "3G28331200"


def test_strips_spaces_and_dashes():
    assert normalize_part_number(" 17210-KA4-000 ") == "17210KA4000"


def test_strips_all_punctuation():
    assert normalize_part_number("13780/43400.a") == "1378043400A"


def test_empty_and_junk():
    assert normalize_part_number("") == ""
    assert normalize_part_number("---") == ""


def test_already_normalized_is_stable():
    assert normalize_part_number("11060A1086") == "11060A1086"
