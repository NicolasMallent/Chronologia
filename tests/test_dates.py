from datetime import date

import pytest

from chronologia.dates import DateParseError, PartialDate, Precision, parse_date


@pytest.mark.parametrize(
    "text, value, precision",
    [
        ("18700904", date(1870, 9, 4), Precision.DAY),
        ("187009", date(1870, 9, 1), Precision.MONTH),
        ("1870", date(1870, 1, 1), Precision.YEAR),
        ("04/09/1870", date(1870, 9, 4), Precision.DAY),
        ("09/1870", date(1870, 9, 1), Precision.MONTH),
        ("19720400", date(1972, 4, 1), Precision.MONTH),
        ("19720000", date(1972, 1, 1), Precision.YEAR),
        (" 1861 ", date(1861, 1, 1), Precision.YEAR),
    ],
)
def test_formats_acceptes(text, value, precision):
    assert parse_date(text) == PartialDate(value, precision)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "18700",
        "1870093",
        "2023-01-01",
        "31/02/2020",
        "20231301",
        "19733112",
        "00000000",
        "0000",
    ],
)
def test_formats_refuses(text):
    with pytest.raises(DateParseError):
        parse_date(text)


@pytest.mark.parametrize("text", ["18700904", "187009", "1870"])
def test_aller_retour_csv(text):
    assert parse_date(text).to_csv() == text


def test_format_francais_reecrit_en_compact():
    assert parse_date("04/09/1870").to_csv() == "18700904"


@pytest.mark.parametrize("text", ["18700904", "187009", "1870", "04/09/1870"])
def test_affichage_se_relit_a_l_identique(text):
    parsed = parse_date(text)
    assert parse_date(parsed.to_display()) == parsed
