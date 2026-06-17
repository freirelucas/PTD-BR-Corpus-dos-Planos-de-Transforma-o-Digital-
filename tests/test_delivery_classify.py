"""Testes para a classificação de colunas/tabelas de entregas (cell 08b).

`_id_col` mapeia um nome de coluna do PDF para um campo canônico; `_classify_tabela_tipo`
decide se a tabela é pactuada/concluida/cancelada. Ambos têm armadilhas de
substring documentadas no código (ex: "Situação" colidindo com "ação").
"""


# ---------------------- _id_col ----------------------

def test_id_col_status_exact_before_substring(cells):
    # "Situação" deve virar 'status', NÃO 'servico' via substring "ação".
    idc = cells["_id_col"]
    assert idc("Situação") == "status"
    assert idc("Status") == "status"


def test_id_col_pactuado_variants(cells):
    idc = cells["_id_col"]
    assert idc("Pactuado?") == "pactuado"
    assert idc("Entregue?") == "pactuado"


def test_id_col_justificativa(cells):
    idc = cells["_id_col"]
    assert idc("Justificativa") == "justificativa"
    assert idc("Motivo do Cancelamento") == "justificativa"


def test_id_col_servico(cells):
    idc = cells["_id_col"]
    assert idc("Serviço/Ação") == "servico"


def test_id_col_produto(cells):
    idc = cells["_id_col"]
    assert idc("Produto") == "produto"
    assert idc("Produto PTD") == "produto"
    assert idc("Entrega") == "produto"


def test_id_col_eixo(cells):
    assert cells["_id_col"]("Eixo") == "eixo"


def test_id_col_data_pactuada(cells):
    idc = cells["_id_col"]
    assert idc("Dt Pactuada") == "data_pactuada"
    assert idc("Data Pactuada") == "data_pactuada"
    assert idc("Prazo") == "data_pactuada"


def test_id_col_data_entrega(cells):
    idc = cells["_id_col"]
    assert idc("Dt Entrega") == "data_entrega"
    assert idc("Data Conclusão") == "data_entrega"


def test_id_col_unknown_returns_none(cells):
    assert cells["_id_col"]("Coluna Aleatória") is None


# ---------------------- _classify_tabela_tipo ----------------------

def test_classify_tipo_default_pactuada(cells):
    # Sem sinais → comportamento histórico "pactuada".
    assert cells["_classify_tabela_tipo"]({}) == "pactuada"


def test_classify_tipo_row_status_concluida(cells):
    ct = cells["_classify_tabela_tipo"]
    assert ct({}, "Concluído") == "concluida"
    assert ct({}, "Sim") == "concluida"


def test_classify_tipo_row_status_cancelada(cells):
    ct = cells["_classify_tabela_tipo"]
    assert ct({}, "Cancelado") == "cancelada"
    assert ct({}, "Não") == "cancelada"


def test_classify_tipo_row_status_pactuada(cells):
    ct = cells["_classify_tabela_tipo"]
    assert ct({}, "Em andamento") == "pactuada"


def test_classify_tipo_concluida_by_columns(cells):
    ct = cells["_classify_tabela_tipo"]
    assert ct({"data_entrega": "x"}) == "concluida"
    assert ct({"pactuado": "x"}) == "concluida"


def test_classify_tipo_cancelada_by_justificativa_without_entrega(cells):
    ct = cells["_classify_tabela_tipo"]
    assert ct({"justificativa": "x"}) == "cancelada"


def test_classify_tipo_justificativa_with_entrega_is_concluida(cells):
    # Pactuada/concluida pode ter coluna "Justificativa" para produto "Outros":
    # se também há data_entrega, NÃO é cancelada.
    ct = cells["_classify_tabela_tipo"]
    assert ct({"justificativa": "x", "data_entrega": "y"}) == "concluida"


def test_classify_tipo_status_wins_over_columns(cells):
    # row_status claro vence a heurística de colunas.
    ct = cells["_classify_tabela_tipo"]
    assert ct({"data_entrega": "x"}, "Cancelado") == "cancelada"


# ---------------------- _is_outros / _is_header_literal_delivery ----------------------

def test_is_outros(cells):
    io = cells["_is_outros"]
    assert io("Outros") is True
    assert io("outro") is True
    assert io("Outros -") is True
    assert io("Produto Real") is False


def test_is_header_literal_delivery(cells):
    ihl = cells["_is_header_literal_delivery"]
    assert ihl("Produto") is True
    assert ihl("Área Responsável") is True
    assert ihl("Data Pactuada") is True
    assert ihl("valor de dado real") is False


def test_is_header_literal_delivery_empty(cells):
    assert cells["_is_header_literal_delivery"]("") is False
    assert cells["_is_header_literal_delivery"](None) is False
