"""Testes de fuzzy_match, fuzzy_match_produto, fuzzy_match_eixo, fuzzy_match_scale."""


def test_fuzzy_match_exact(cells):
    fm = cells["fuzzy_match"]
    result, score = fm("hello", ["hello", "world"])
    assert result == "hello"
    assert score == 1.0


def test_fuzzy_match_case_insensitive(cells):
    fm = cells["fuzzy_match"]
    result, score = fm("HELLO", ["hello"])
    assert score == 1.0


def test_fuzzy_match_accent_insensitive(cells):
    fm = cells["fuzzy_match"]
    # "Integracao" sem acento deve achar "Integração" com score 1.0
    result, score = fm("integracao", ["Integração"])
    assert result == "Integração"
    assert score == 1.0


def test_fuzzy_match_fuzzy_high(cells):
    fm = cells["fuzzy_match"]
    # truncamento de 1 char → score alto mas <1
    result, score = fm("Integração ao Login Únic", ["Integração ao Login Único"])
    assert result == "Integração ao Login Único"
    assert 0.85 <= score < 1.0


def test_fuzzy_match_below_threshold_returns_best(cells):
    fm = cells["fuzzy_match"]
    # Não atinge threshold mas retorna o melhor candidato
    result, score = fm("xyz", ["abc", "def"])
    assert score < 0.85
    # Best e score são retornados


def test_fuzzy_match_empty_inputs(cells):
    fm = cells["fuzzy_match"]
    assert fm("", ["a"]) == ("", 0.0)
    assert fm("a", []) == ("", 0.0)


def test_fuzzy_match_produto_alias_exact(cells):
    fmp = cells["fuzzy_match_produto"]
    # Alias key exata → score 1.0
    result, score = fmp("Integração ao Login Único Gov.Br")
    assert result == "Integração ao Login Único"
    assert score == 1.0


def test_fuzzy_match_produto_alias_accent_insensitive(cells):
    fmp = cells["fuzzy_match_produto"]
    # "Integração ao Login Unico" (sem acento no Unico) — key de alias
    result, score = fmp("Integração ao Login Unico")
    assert result == "Integração ao Login Único"


def test_fuzzy_match_produto_canonical_returns_self(cells):
    fmp = cells["fuzzy_match_produto"]
    # Texto idêntico ao canônico — fuzzy_match retorna 1.0 via exact path
    result, score = fmp("Integração ao Login Único")
    assert result == "Integração ao Login Único"
    assert score >= 0.95  # 1.0 via exact, ou 0.98 via alias accent-insensitive


def test_fuzzy_match_produto_unknown(cells):
    fmp = cells["fuzzy_match_produto"]
    result, score = fmp("texto completamente diferente xyz")
    assert score < 0.70


def test_fuzzy_match_scale_alias_normalized(cells):
    fms = cells["fuzzy_match_scale"]
    prob_scale = cells["PROBABILIDADE_SCALE"]
    # "Pouca" está em PROBABILIDADE_ALIASES (key lowercase no-accent)
    result, score = fms("Pouca", prob_scale)
    assert result == "pouco provável"
    assert score == 0.95


def test_fuzzy_match_scale_susep_numeric(cells):
    fms = cells["fuzzy_match_scale"]
    prob_scale = cells["PROBABILIDADE_SCALE"]
    # SUSEP usa "1"-"5" mapeados via PROBABILIDADE_ALIASES
    result, _ = fms("1", prob_scale)
    assert result == "raro"
    result, _ = fms("5", prob_scale)
    assert result == "praticamente certo"


def test_fuzzy_match_scale_antaq_three_points(cells):
    fms = cells["fuzzy_match_scale"]
    prob_scale = cells["PROBABILIDADE_SCALE"]
    # ANTAQ "baixa" mapeia para "pouco provável"
    result, _ = fms("baixa", prob_scale)
    assert result == "pouco provável"


def test_fuzzy_match_scale_exact_canonical(cells):
    fms = cells["fuzzy_match_scale"]
    prob_scale = cells["PROBABILIDADE_SCALE"]
    # Termo já canônico vem com score 1.0 via fuzzy_match (depois do alias check)
    result, score = fms("raro", prob_scale)
    assert result == "raro"
    assert score == 1.0


def test_fuzzy_match_eixo_canonical(cells):
    fme = cells["fuzzy_match_eixo"]
    result, score = fme("Serviços Digitais e Melhoria da Qualidade")
    assert result == "Serviços Digitais e Melhoria da Qualidade"
    assert score >= 0.95


def test_fuzzy_match_eixo_legacy_alias(cells):
    fme = cells["fuzzy_match_eixo"]
    # EGD 2020-2022 → EFGD 2024
    result, score = fme("Transformação Digital de Serviços Públicos")
    assert result == "Serviços Digitais e Melhoria da Qualidade"
