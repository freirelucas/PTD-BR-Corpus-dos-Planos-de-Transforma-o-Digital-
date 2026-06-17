"""Testes para os helpers puros do cell 07b (extração/auditoria de risco)."""


# ---------------------- _is_header_literal ----------------------

def test_is_header_literal_true(cells):
    ihl = cells["_is_header_literal"]
    assert ihl("Probabilidade") is True
    assert ihl("Impacto") is True
    assert ihl("Ações") is True  # strip_accents → "acoes"


def test_is_header_literal_false(cells):
    ihl = cells["_is_header_literal"]
    assert ihl("A transformação digital não gerar resultado") is False
    assert ihl("") is False
    assert ihl(None) is False


# ---------------------- _try_swap_prob_impacto ----------------------

def test_swap_detects_inverted_columns(cells):
    swap = cells["_try_swap_prob_impacto"]
    # prob_raw é valor de impacto, imp_raw é valor de probabilidade, ambos
    # casam mal nas escalas esperadas.
    res = swap("Alto", "Raro", ("", 0.3), ("", 0.3))
    assert res is not None
    prob_corr, imp_corr, _, _ = res
    assert prob_corr == "Raro" and imp_corr == "Alto"


def test_swap_no_swap_when_both_match(cells):
    swap = cells["_try_swap_prob_impacto"]
    assert swap("Raro", "Alto", ("raro", 0.95), ("alto", 0.95)) is None


def test_swap_none_on_empty(cells):
    swap = cells["_try_swap_prob_impacto"]
    assert swap("", "Alto", ("", 0.3), ("", 0.3)) is None


# ---------------------- _map_risk_columns ----------------------

def test_map_risk_columns_named(cells):
    pd = cells["pd"]
    df = pd.DataFrame(columns=["ID do risco", "Risco", "Probabilidade",
                               "Impacto", "Tratamento", "Ações"])
    m = cells["_map_risk_columns"](df)
    assert m["risco"] == "Risco"
    assert m["probabilidade"] == "Probabilidade"
    assert m["impacto"] == "Impacto"
    assert m["tratamento"] == "Tratamento"
    # ID não deve ser mapeado como "risco".
    assert m["risco"] != "ID do risco"


def test_map_risk_columns_positional_fallback(cells):
    pd = cells["pd"]
    df = pd.DataFrame(columns=["Col0", "Col1", "Col2", "Col3", "Col4"])
    m = cells["_map_risk_columns"](df)
    # Sem headers reconhecíveis → fallback posicional do template SGD.
    assert m["risco"] == "Col0"
    assert m["acoes"] == "Col4"


# ---------------------- _is_header_capture / _is_fragment ----------------------

def test_is_header_capture_uses_literal_set(cells):
    ihc = cells["_is_header_capture"]
    member = next(iter(cells["_HEADER_LITERALS"]))
    assert ihc(member) is True
    assert ihc("uma frase de dado real qualquer") is False


def test_is_fragment(cells):
    isf = cells["_is_fragment"]
    assert isf("Probabilidade-") is True       # hífen final solitário
    assert isf("-rência") is True              # sufixo isolado
    assert isf("de de Ocor-") is True          # repetição + hífen
    assert isf("raro") is False
    assert isf("") is False


# ---------------------- _is_column_bleed / _detect_column_shift ----------------------

def test_is_column_bleed_long_text(cells):
    icb = cells["_is_column_bleed"]
    scale = cells["TRATAMENTO_OPTIONS"]
    longtext = ("Desenvolver planos de contingência detalhados para lidar com "
                "falhas ou interrupções nos serviços prestados aos cidadãos")
    assert icb(longtext, scale) is True
    assert icb("mitigar", scale) is False


def test_detect_column_shift(cells):
    dcs = cells["_detect_column_shift"]
    PROB = cells["PROBABILIDADE_SCALE"]
    IMP = cells["IMPACTO_SCALE"]
    # "alto" é valor de impacto colocado na coluna de probabilidade.
    assert dcs("alto", PROB, [("impacto", IMP)]) == "impacto"
    # valor que casa na própria escala → sem shift.
    assert dcs("raro", PROB, [("impacto", IMP)]) is None


# ---------------------- _audit_risk_entries ----------------------

def test_audit_flags_column_bleed(cells):
    RiskEntry = cells["RiskEntry"]
    bleed = ("Implementar controles de acesso rigorosos, limitando o acesso a "
             "dados apenas a usuários autorizados e auditando periodicamente")
    e = RiskEntry(orgao_sigla="X", risco_texto="r", probabilidade_original="raro",
                  impacto_original="alto", tratamento_original=bleed)
    stats = cells["_audit_risk_entries"]([e])
    assert e.needs_review is True
    assert sum(stats.values()) >= 1


def test_audit_clean_entry_not_flagged(cells):
    RiskEntry = cells["RiskEntry"]
    e = RiskEntry(orgao_sigla="X", risco_texto="r", probabilidade_original="raro",
                  impacto_original="alto", tratamento_original="mitigar")
    cells["_audit_risk_entries"]([e])
    assert e.needs_review is False
