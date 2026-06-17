"""Testes para os classificadores de tabela do cell 06b (PyMuPDF).

`classify_diretivo_table` e `classify_entregas_table` decidem o TIPO de cada
tabela extraída do PDF. Uma classificação errada silenciosamente corrompe
todos os números downstream (riscos atribuídos a órgãos errados, entregas
contadas no balde errado), então é a lógica de maior alavancagem de
qualidade de dados do pipeline.
"""


def _df(cells, columns, rows=None):
    """DataFrame helper. Sem `rows`, cria 1 linha placeholder.

    Nota: classify_entregas_table checa `df.empty`, e um DataFrame só-colunas
    é considerado vazio pelo pandas — por isso precisamos de ao menos 1 linha.
    """
    pd = cells["pd"]
    if rows is None:
        rows = [["x"] * len(columns)]
    return pd.DataFrame(rows, columns=columns)


# ---------------------- classify_diretivo_table ----------------------

def test_diretivo_risk_table_by_keywords(cells):
    cdt = cells["classify_diretivo_table"]
    df = _df(cells, ["ID do Risco", "Probabilidade", "Impacto", "Tratamento"])
    assert cdt(df) == "risk_table"


def test_diretivo_risk_table_risco_plus_tratamento(cells):
    # Regra: "risco" + "tratamento" + 3<=ncols<=8 → risk_table.
    cdt = cells["classify_diretivo_table"]
    df = _df(cells, ["Risco", "Descrição", "Tratamento"])
    assert cdt(df) == "risk_table"


def test_diretivo_organ_info(cells):
    cdt = cells["classify_diretivo_table"]
    df = _df(cells, ["Órgão", "Sigla", "CNPJ"])
    assert cdt(df) == "organ_info"


def test_diretivo_signature(cells):
    # >=2 sig_kw e ncols<=4 → signature.
    cdt = cells["classify_diretivo_table"]
    df = _df(cells, ["Nome", "Cargo", "Assinatura"])
    assert cdt(df) == "signature"


def test_diretivo_unknown(cells):
    cdt = cells["classify_diretivo_table"]
    assert cdt(_df(cells, ["A", "B"])) == "unknown"


def test_diretivo_none_returns_unknown(cells):
    assert cells["classify_diretivo_table"](None) == "unknown"


def test_diretivo_empty_columns_returns_unknown(cells):
    pd = cells["pd"]
    assert cells["classify_diretivo_table"](pd.DataFrame()) == "unknown"


def test_diretivo_risk_requires_column_count_bound(cells):
    # risk_hits>=2 mas ncols>8 → não classifica como risk_table.
    cdt = cells["classify_diretivo_table"]
    cols = ["Risco", "Probabilidade", "Impacto", "Tratamento",
            "C5", "C6", "C7", "C8", "C9"]
    assert cdt(_df(cells, cols)) != "risk_table"


def test_diretivo_uses_first_row_as_signal(cells):
    # Headers genéricos (Col0..) mas a 1a linha carrega os termos de risco.
    cdt = cells["classify_diretivo_table"]
    df = _df(cells, ["Col0", "Col1", "Col2", "Col3"],
             rows=[["ID do Risco", "Probabilidade", "Impacto", "Tratamento"]])
    assert cdt(df) == "risk_table"


# ---------------------- classify_entregas_table ----------------------

def test_entregas_canceladas_by_justificativa(cells):
    cet = cells["classify_entregas_table"]
    assert cet(_df(cells, ["Produto", "Justificativa"])) == "canceladas"


def test_entregas_concluidas_by_data_entrega(cells):
    cet = cells["classify_entregas_table"]
    assert cet(_df(cells, ["Produto", "Dt Entrega"])) == "concluidas"


def test_entregas_concluidas_by_pactuado_question(cells):
    cet = cells["classify_entregas_table"]
    assert cet(_df(cells, ["Produto", "Pactuado?"])) == "concluidas"


def test_entregas_pactuadas_by_data_pactuada(cells):
    cet = cells["classify_entregas_table"]
    assert cet(_df(cells, ["Produto", "Data Pactuada"])) == "pactuadas"


def test_entregas_pactuadas_area_responsavel(cells):
    cet = cells["classify_entregas_table"]
    df = _df(cells, ["Área Responsável", "Dt Pactuada"])
    assert cet(df) == "pactuadas"


def test_entregas_justificativa_takes_priority(cells):
    # "justificativa" é checado primeiro: vence mesmo com data entrega presente.
    cet = cells["classify_entregas_table"]
    df = _df(cells, ["Produto", "Justificativa", "Dt Entrega"])
    assert cet(df) == "canceladas"


def test_entregas_unknown(cells):
    cet = cells["classify_entregas_table"]
    assert cet(_df(cells, ["Foo", "Bar"])) == "unknown"


def test_entregas_empty_returns_unknown(cells):
    pd = cells["pd"]
    assert cells["classify_entregas_table"](pd.DataFrame()) == "unknown"


def test_entregas_none_returns_unknown(cells):
    assert cells["classify_entregas_table"](None) == "unknown"


# ---------------------- helpers ----------------------

def test_normalize_header_lowercases_and_strips_accents(cells):
    nh = cells["_normalize_header"]
    assert nh("Probabilidade") == "probabilidade"
    assert nh("Órgão") == "orgao"


def test_normalize_header_non_string_returns_empty(cells):
    assert cells["_normalize_header"](123) == ""
    assert cells["_normalize_header"](None) == ""


def test_is_risk_data_detects_scale_values(cells):
    pd = cells["pd"]
    ir = cells["_is_risk_data"]
    df = pd.DataFrame([["R1", "Provável", "Alto", "Mitigar"]])
    assert ir(df) is True


def test_is_risk_data_rejects_non_risk(cells):
    pd = cells["pd"]
    df = pd.DataFrame([["a", "b", "c", "d"]])
    assert cells["_is_risk_data"](df) is False


def test_is_risk_data_rejects_narrow_table(cells):
    pd = cells["pd"]
    # Menos de 4 colunas → não é tabela de risco.
    df = pd.DataFrame([["Provável", "Alto"]])
    assert cells["_is_risk_data"](df) is False


def test_is_risk_data_none_or_empty(cells):
    pd = cells["pd"]
    assert cells["_is_risk_data"](None) is False
    assert cells["_is_risk_data"](pd.DataFrame()) is False
