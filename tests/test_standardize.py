"""Testes para a canonização do cell 09b (standardize_risks / standardize_deliveries).

Inclui os testes de REGRESSÃO da lacuna de `tratamento`: valores compostos
(ex.: "mitigar; transferir") que casavam bem em cada parte e por isso escapavam
ao `needs_review`. O fix em 09b sinaliza compostos sem alterar o valor normalizado.
"""
import pytest


def _risk(cells, prob="raro", imp="alto", trat="mitigar"):
    RiskEntry = cells["RiskEntry"]
    return RiskEntry(orgao_sigla="X", risco_texto="evento de risco",
                     probabilidade_original=prob, impacto_original=imp,
                     tratamento_original=trat)


def _delivery(cells, produto="Evolução do Serviço",
              eixo="Serviços Digitais e Melhoria da Qualidade"):
    DeliveryEntry = cells["DeliveryEntry"]
    return DeliveryEntry(orgao_sigla="X", tabela_tipo="pactuada",
                         servico_acao="ação", produto_original=produto,
                         eixo_original=eixo)


# ---------------------- standardize_risks: caso limpo ----------------------

def test_standardize_risks_clean_canonical(cells):
    e = _risk(cells, "raro", "alto", "mitigar")
    cells["standardize_risks"]([e])
    assert e.probabilidade_normalizada == "raro"
    assert e.impacto_normalizado == "alto"
    assert e.tratamento_normalizado == "mitigar"
    assert e.needs_review is False


def test_standardize_risks_returns_entries_and_report(cells):
    out = cells["standardize_risks"]([_risk(cells)])
    entries, report = out
    assert isinstance(entries, list) and isinstance(report, dict)
    assert "tratamento_mappings" in report


def test_standardize_risks_low_score_flags_review(cells):
    # Valor sem casamento na escala → needs_review.
    e = _risk(cells, prob="xpto sem sentido nenhum aqui", imp="alto", trat="mitigar")
    cells["standardize_risks"]([e])
    assert e.needs_review is True


# ---------------------- standardize_risks: REGRESSÃO frente B ----------------------

COMPOUNDS = [
    "mitigar; transferir",      # composto exato
    "Mitigar/Transferir",       # composto via "/"
    "Mitigar/Tra nsferir",      # composto com ruído de extração
    "transferir; transferir",   # duplicado
    "Transferir/ Compartilhar",  # parte fora da escala mas fuzzy-casada
]


@pytest.mark.parametrize("trat", COMPOUNDS)
def test_tratamento_composto_dispara_review(cells, trat):
    """Regressão: compostos antes escapavam (needs_review=False)."""
    e = _risk(cells, trat=trat)
    cells["standardize_risks"]([e])
    assert e.needs_review is True
    assert "composto" in (e.review_reason or "").lower() or "múltiplo" in (e.review_reason or "").lower()


@pytest.mark.parametrize("trat", COMPOUNDS)
def test_tratamento_composto_nao_altera_normalizado(cells, trat):
    """O fix sinaliza, mas NÃO muda tratamento_normalizado (preserva canonização)."""
    e = _risk(cells, trat=trat)
    before_method = None
    cells["standardize_risks"]([e])
    # Continua sendo um join "; " de tokens (não foi branqueado nem reescrito).
    assert "; " in e.tratamento_normalizado


@pytest.mark.parametrize("trat", ["mitigar", "Transferir", "Aceitar", "eliminar"])
def test_tratamento_canonico_unico_nao_dispara_review(cells, trat):
    """Tratamento canônico único permanece sem revisão (sem falso positivo)."""
    e = _risk(cells, trat=trat)
    cells["standardize_risks"]([e])
    assert e.needs_review is False
    assert e.tratamento_normalizado in cells["TRATAMENTO_OPTIONS"]


def test_review_reason_implies_needs_review(cells):
    """Fix geral: qualquer review_reason registrado implica needs_review=True."""
    e = _risk(cells, trat="mitigar; aceitar")
    cells["standardize_risks"]([e])
    assert e.review_reason and e.needs_review is True


# ---------------------- standardize_deliveries ----------------------

def test_standardize_deliveries_canonical(cells):
    e = _delivery(cells)
    out = cells["standardize_deliveries"]([e])
    entries, report = out
    assert e.produto_normalizado  # casou para algum produto canônico
    assert e.eixo_normalizado in cells["CANONICAL_EIXOS"]
    assert isinstance(report, dict)


def test_standardize_deliveries_unmatched(cells):
    # Produto fora do vocabulário SGD → marcado UNMATCHED (e sinalizado p/ revisão).
    e = _delivery(cells, produto="Algo totalmente fora do vocabulário SGD")
    cells["standardize_deliveries"]([e])
    assert e.produto_normalizado == "UNMATCHED"
    assert e.needs_review is True
