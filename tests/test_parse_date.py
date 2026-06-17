"""Testes de parse_date (notebook_cells/03_utils.py)."""


def test_parse_date_empty(cells):
    assert cells["parse_date"]("") is None
    assert cells["parse_date"](None) is None


def test_parse_date_iso_full(cells):
    # ISO YYYY-MM-DD passa direto (regex retorna o próprio match)
    assert cells["parse_date"]("2025-12-31") == "2025-12-31"


def test_parse_date_dd_mm_yyyy(cells):
    assert cells["parse_date"]("31/12/2025") == "2025-12-31"


def test_parse_date_mm_yyyy(cells):
    assert cells["parse_date"]("12/2025") == "2025-12"


def test_parse_date_mes_yyyy(cells):
    pd_fn = cells["parse_date"]
    assert pd_fn("jun/25") == "2025-06"
    assert pd_fn("jan/2026") == "2026-01"
    assert pd_fn("dez/2024") == "2024-12"


def test_parse_date_fallback_returns_original(cells):
    # Texto não-parseável retorna o original normalizado
    assert cells["parse_date"]("texto qualquer") == "texto qualquer"


def test_parse_date_strips_whitespace(cells):
    assert cells["parse_date"]("  31/12/2025  ") == "2025-12-31"
