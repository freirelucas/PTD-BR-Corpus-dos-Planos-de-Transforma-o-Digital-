"""Testes de classify_match (notebook_cells/03_utils.py).

Este módulo é o mais importante do test suite — `classify_match` teve um
bug em PR #9 (corrigido em PR #11) onde as keys do alias_map não eram
normalizadas antes de comparar, causando misclassificação silenciosa
de entries de PRODUTO_ALIASES / EIXO_ALIASES (case+accent preservados)
como `fuzzy_high` em vez de `alias`.

Os testes abaixo cobrem ambos os casos (keys normalizadas vs preservadas)
e teriam falhado imediatamente com o bug.
"""


def test_classify_match_exact(cells):
    cm = cells["classify_match"]
    assert cm("any", 1.0, None) == "exact"
    assert cm("any", 0.9995, None) == "exact"
    assert cm("any", 0.999, None) == "exact"


def test_classify_match_unmatched_zero(cells):
    cm = cells["classify_match"]
    assert cm("any", 0.0, None) == "unmatched"
    assert cm("any", -0.1, None) == "unmatched"


def test_classify_match_unmatched_empty(cells):
    cm = cells["classify_match"]
    assert cm("", 0.95, None) == "unmatched"


def test_classify_match_fuzzy_high(cells):
    cm = cells["classify_match"]
    assert cm("xyz", 0.90, None) == "fuzzy_high"
    assert cm("xyz", 0.85, None) == "fuzzy_high"


def test_classify_match_fuzzy_low(cells):
    cm = cells["classify_match"]
    assert cm("xyz", 0.84, None) == "fuzzy_low"
    assert cm("xyz", 0.70, None) == "fuzzy_low"


def test_classify_match_unmatched_below_threshold(cells):
    cm = cells["classify_match"]
    assert cm("xyz", 0.69, None) == "unmatched"
    assert cm("xyz", 0.50, None) == "unmatched"


def test_classify_match_alias_scale_normalized_keys(cells):
    """PROBABILIDADE_ALIASES tem keys já normalizadas ('pouca', 'baixa').

    Cenário comum: score=0.95 retornado por fuzzy_match_scale alias path,
    com 'Pouca' como original (case+accent). Deve classificar como 'alias'.
    """
    cm = cells["classify_match"]
    prob_aliases = cells["PROBABILIDADE_ALIASES"]
    assert cm("Pouca", 0.95, prob_aliases) == "alias"
    assert cm("Baixa", 0.95, prob_aliases) == "alias"
    assert cm("MUITO ALTA", 0.95, prob_aliases) == "alias"


def test_classify_match_alias_produto_preserved_keys(cells):
    """PRODUTO_ALIASES tem keys com case+accent preservados.

    ESTE É O TESTE QUE PEGARIA O BUG do PR #9 corrigido em PR #11:
    keys como 'Integração ao Login Único Gov.Br' não eram normalizadas
    antes da comparação, fazendo `norm in alias_map` retornar False
    silenciosamente.
    """
    cm = cells["classify_match"]
    produto_aliases = cells["PRODUTO_ALIASES"]
    # "Integração ao Login Único Gov.Br" é uma key de PRODUTO_ALIASES.
    # Quando essa string é o `original`, deve classificar como 'alias'.
    assert cm("Integração ao Login Único Gov.Br", 1.0, produto_aliases) == "exact"  # 1.0 vence
    assert cm("Integração ao Login Único Gov.Br", 0.98, produto_aliases) == "alias"
    assert cm("integracao ao login unico gov.br", 0.98, produto_aliases) == "alias"
    # "Integração ao Login Unico" (sem acento no Unico) é outra key
    assert cm("Integração ao Login Unico", 0.98, produto_aliases) == "alias"


def test_classify_match_alias_eixo_preserved_keys(cells):
    """EIXO_ALIASES também tem keys preservadas."""
    cm = cells["classify_match"]
    eixo_aliases = cells["EIXO_ALIASES"]
    # "Transformação Digital de Serviços Públicos" é key de EIXO_ALIASES
    assert cm("Transformação Digital de Serviços Públicos", 0.95, eixo_aliases) == "alias"


def test_classify_match_alias_takes_priority_over_fuzzy_high(cells):
    """Quando original casa em alias_map E score é fuzzy_high range,
    classifica como 'alias' (não fuzzy_high)."""
    cm = cells["classify_match"]
    produto_aliases = cells["PRODUTO_ALIASES"]
    # Sem o bug fix: cairia em fuzzy_high. Com fix: alias.
    assert cm("Integração ao Login Único Gov.Br", 0.90, produto_aliases) == "alias"


def test_classify_match_not_in_alias_map_falls_back(cells):
    """Original não presente em alias_map cai no score-based fallback."""
    cm = cells["classify_match"]
    produto_aliases = cells["PRODUTO_ALIASES"]
    # "xyz totalmente desconhecido" não está em PRODUTO_ALIASES
    assert cm("xyz totalmente desconhecido", 0.90, produto_aliases) == "fuzzy_high"
    assert cm("xyz totalmente desconhecido", 0.75, produto_aliases) == "fuzzy_low"


def test_classify_match_caches_normalized_keys(cells):
    """O cache _ALIAS_KEY_NORM_CACHE evita re-normalização."""
    cache = cells["_ALIAS_KEY_NORM_CACHE"]
    produto_aliases = cells["PRODUTO_ALIASES"]
    cells["classify_match"]("Pouca", 0.95, produto_aliases)
    assert id(produto_aliases) in cache
    # As keys normalizadas estão lá, em forma strip_accents lowercase
    normalized = cache[id(produto_aliases)]
    assert "integracao ao login unico gov.br" in normalized


def test_classify_match_custom_cuts(cells):
    """fuzzy_high_cut e fuzzy_low_cut customizáveis."""
    cm = cells["classify_match"]
    # Sem alias map, só score
    assert cm("x", 0.90, None, fuzzy_high_cut=0.95, fuzzy_low_cut=0.80) == "fuzzy_low"
    assert cm("x", 0.96, None, fuzzy_high_cut=0.95, fuzzy_low_cut=0.80) == "fuzzy_high"
    assert cm("x", 0.79, None, fuzzy_high_cut=0.95, fuzzy_low_cut=0.80) == "unmatched"
