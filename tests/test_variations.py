"""Testes do derivador build_variations.py (catálogo tipado de divergências).

Cobre a lógica de tipagem (classify), a coleta a partir das colunas
_original/_normalizado/_method e a paridade do variations.csv commitado (CI)."""
import build_variations as bv


def test_classify_tipos():
    # encaixe limpo não vira variação
    assert bv.classify("Evolução do Serviço", "Evolução do Serviço", "exact") == "exato"
    assert bv.classify("Integr. base", "Integração à base de dados", "alias") == "alias"
    # texto autoral próximo do catálogo
    assert bv.classify("oEvolução do Serviço", "Evolução do Serviço", "fuzzy_high") == "aproximado"
    # eixo ausente, inferido de outro campo
    assert bv.classify("", "Segurança e Privacidade", "unmatched") == "imputado"
    # autoral fora do catálogo
    assert bv.classify("1-Alto", "1-Alto", "unmatched") == "residual"
    # 'Outros' é sempre residual, não importa o método
    assert bv.classify("sOutros", "Outros", "fuzzy_high") == "residual"


def test_collect_ignora_exato_e_tipa_resto():
    rows = [
        {"orgao_sigla": "A", "produto_original": "X", "produto_normalizado": "X",
         "produto_method": "exact", "produto_score": "1.0",
         "eixo_original": "", "eixo_normalizado": "Segurança e Privacidade",
         "eixo_method": "unmatched", "eixo_score": "0.0"},
    ]
    out = bv._collect(rows, "delivery", ("produto", "eixo"))
    # produto exato sai; eixo imputado entra
    assert len(out) == 1
    v = out[0]
    assert v["field"] == "eixo" and v["variation_type"] == "imputado"
    assert v["entry_type"] == "delivery" and v["orgao_sigla"] == "A"


def test_serialize_roundtrip_estavel():
    variations = bv.build()
    once = bv._serialize(variations)
    twice = bv._serialize(bv.build())
    assert once == twice
    assert once.startswith("orgao_sigla,entry_type,field,")


def test_variations_commitado_em_dia():
    """O variations.csv do repo bate com build_variations (mesmo guard da CI)."""
    assert bv.main(["--check"]) == 0
