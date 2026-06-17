"""Testes para os helpers puros do cell 10b (export)."""
import os


def _delivery(cells, sigla, produto):
    DeliveryEntry = cells["DeliveryEntry"]
    return DeliveryEntry(orgao_sigla=sigla, tabela_tipo="pactuada",
                         servico_acao="x", produto_original=produto,
                         produto_normalizado=produto, eixo_original="",
                         eixo_normalizado="")


# ---------------------- _build_nested_json ----------------------

def test_build_nested_json_groups_by_key(cells):
    entries = [_delivery(cells, "ABIN", "P1"), _delivery(cells, "ABIN", "P2"),
               _delivery(cells, "AEB", "P3")]
    out = cells["_build_nested_json"](entries, "orgao_sigla")
    assert set(out["data"].keys()) == {"ABIN", "AEB"}
    assert len(out["data"]["ABIN"]) == 2
    assert out["metadata"]["total"] == 3


def test_build_nested_json_metadata_extra(cells):
    out = cells["_build_nested_json"]([_delivery(cells, "ABIN", "P1")],
                                      "orgao_sigla", {"fonte": "teste"})
    assert out["metadata"]["fonte"] == "teste"


def test_build_nested_json_empty(cells):
    out = cells["_build_nested_json"]([], "orgao_sigla")
    assert out["data"] == {} and out["metadata"]["total"] == 0


# ---------------------- _sorted_stable ----------------------

def test_sorted_stable_orders_by_key(cells):
    entries = [_delivery(cells, "C", "p"), _delivery(cells, "A", "p"),
               _delivery(cells, "B", "p")]
    out = cells["_sorted_stable"](entries, "orgao_sigla")
    assert [e.orgao_sigla for e in out] == ["A", "B", "C"]


def test_sorted_stable_multi_key_stable(cells):
    entries = [_delivery(cells, "A", "z"), _delivery(cells, "A", "a"),
               _delivery(cells, "B", "m")]
    out = cells["_sorted_stable"](entries, "orgao_sigla", "produto_normalizado")
    assert [(e.orgao_sigla, e.produto_normalizado) for e in out] == [
        ("A", "a"), ("A", "z"), ("B", "m")]


# ---------------------- _file_size_str ----------------------

def test_file_size_str_bytes(cells, tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * 512)
    s = cells["_file_size_str"](str(p))
    assert "B" in s  # alguma unidade de tamanho


def test_file_size_str_kb(cells, tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * 4096)
    s = cells["_file_size_str"](str(p))
    assert "KB" in s or "KiB" in s or "K" in s
