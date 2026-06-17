"""Testes para os helpers de scraping (cell 04b).

`_classify_pdf_link` decide se um link é o documento diretivo ou o anexo de
entregas; `_extract_siglas_from_header` extrai siglas de órgão de um cabeçalho
de seção. São lógica pura de string/regex — o tipo de coisa que quebra
silenciosamente quando o portal muda a nomenclatura.
"""


# ---------------------- _classify_pdf_link ----------------------

def test_classify_link_diretivo(cells):
    cl = cells["_classify_pdf_link"]
    assert cl("Documento Diretivo") == "diretivo"
    assert cl("DIRETIVO") == "diretivo"


def test_classify_link_entregas(cells):
    cl = cells["_classify_pdf_link"]
    assert cl("Anexo de Entregas") == "entregas"
    assert cl("Entregas") == "entregas"


def test_classify_link_accent_insensitive(cells):
    # "Transformação" e afins não importam aqui, mas a normalização tira acento.
    cl = cells["_classify_pdf_link"]
    assert cl("Diretivo") == "diretivo"


def test_classify_link_unrelated_returns_none(cells):
    cl = cells["_classify_pdf_link"]
    assert cl("Página inicial") is None
    assert cl("") is None


# ---------------------- _extract_siglas_from_header ----------------------

def test_extract_siglas_single(cells):
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital CVM:") == ["CVM"]


def test_extract_siglas_trailing_dash(cells):
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital CVM -") == ["CVM"]


def test_extract_siglas_multiple(cells):
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital SUSEP / ANTAQ:") == ["SUSEP", "ANTAQ"]


def test_extract_siglas_strips_parenthetical_suffix(cells):
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital ANATEL (NOVO):") == ["ANATEL"]


def test_extract_siglas_allows_hyphen(cells):
    # Siglas com hífen como SG-PR são válidas.
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital SG-PR:") == ["SG-PR"]


def test_extract_siglas_rejects_lowercase_noise(cells):
    # Texto não-sigla (lowercase) é filtrado pela regex de uppercase.
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital alguma coisa minúscula") == []


def test_extract_siglas_empty_after_prefix(cells):
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital") == []


def test_extract_siglas_too_long_rejected(cells):
    # Limite de 2-14 chars: nome por extenso não vira sigla.
    es = cells["_extract_siglas_from_header"]
    assert es("Plano de Transformação Digital MINISTERIODAECONOMIAEFAZENDA:") == []
