"""Testes de normalize_text e strip_accents (notebook_cells/03_utils.py)."""


def test_normalize_text_empty(cells):
    assert cells["normalize_text"]("") == ""
    assert cells["normalize_text"](None) == ""


def test_normalize_text_basic(cells):
    assert cells["normalize_text"]("hello world") == "hello world"


def test_normalize_text_strips_whitespace(cells):
    assert cells["normalize_text"]("  hello  ") == "hello"


def test_normalize_text_collapses_multiple_spaces(cells):
    assert cells["normalize_text"]("hello    world") == "hello world"


def test_normalize_text_collapses_tabs_and_newlines(cells):
    assert cells["normalize_text"]("hello\t\n world") == "hello world"


def test_normalize_text_strips_enum_prefix_paren(cells):
    assert cells["normalize_text"]("A) Evitar") == "Evitar"
    assert cells["normalize_text"]("B) Reduzir ou mitigar") == "Reduzir ou mitigar"


def test_normalize_text_strips_enum_prefix_number(cells):
    assert cells["normalize_text"]("1) Pouco provável") == "Pouco provável"
    assert cells["normalize_text"]("12) Item") == "Item"


def test_normalize_text_strips_enum_prefix_roman(cells):
    assert cells["normalize_text"]("II. Probabilidade") == "Probabilidade"
    assert cells["normalize_text"]("iv) opção") == "opção"


def test_normalize_text_no_enum_prefix_for_long_word(cells):
    # Mais de 3 chars antes do delimitador não deve casar — "abcd) X" preserva
    assert cells["normalize_text"]("abcd) X") == "abcd) X"


def test_normalize_text_idempotent(cells):
    nt = cells["normalize_text"]
    once = nt("  A)  Reduzir  ")
    twice = nt(once)
    assert once == twice == "Reduzir"


def test_normalize_text_preserves_accents(cells):
    assert cells["normalize_text"]("Probabilidade") == "Probabilidade"


def test_strip_accents_portuguese(cells):
    sa = cells["strip_accents"]
    assert sa("Integração") == "Integracao"
    assert sa("ação") == "acao"
    assert sa("muito provável") == "muito provavel"


def test_strip_accents_case_preserved(cells):
    assert cells["strip_accents"]("MAÇÃ") == "MACA"


def test_strip_accents_no_op_for_ascii(cells):
    assert cells["strip_accents"]("hello") == "hello"
