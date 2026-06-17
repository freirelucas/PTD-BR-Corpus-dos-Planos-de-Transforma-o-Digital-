"""Testes do cell 05d (pdf_metadata): parsing da data de PDF e montagem das
linhas a partir dos PDFs no disco (owner pós-dedup, ord. por sigla/tipo)."""
from types import SimpleNamespace

import fitz


def test_parse_pdf_date(cells):
    parse = cells["_parse_pdf_date"]
    assert parse("D:20260429120000-03'00'") == "2026-04-29"
    assert parse("20251231") == "2025-12-31"
    assert parse("") == ""
    assert parse("D:2026") == ""        # curto demais
    assert parse("lixo") == ""


def test_build_pdf_metadata(cells, tmp_path):
    build = cells["build_pdf_metadata"]
    pdf = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"creationDate": "D:20260429120000",
                      "modDate": "D:20260430000000"})
    doc.save(str(pdf))
    doc.close()
    organs = [
        SimpleNamespace(sigla="AEB", pdf_path_diretivo=str(pdf),
                        pdf_path_entregas=str(pdf)),
        SimpleNamespace(sigla="ABIN", pdf_path_diretivo=None,
                        pdf_path_entregas=str(pdf)),
        SimpleNamespace(sigla="X", pdf_path_diretivo=None,
                        pdf_path_entregas=None),   # sem PDF -> nenhuma linha
    ]
    rows = build(organs)
    # ordenado por (sigla, tipo): ABIN/entregas, AEB/diretivo, AEB/entregas
    assert [(r["sigla"], r["tipo"]) for r in rows] == [
        ("ABIN", "entregas"), ("AEB", "diretivo"), ("AEB", "entregas")]
    r = rows[1]
    assert r["data_criacao_pdf"] == "2026-04-29"
    assert r["data_modificacao_pdf"] == "2026-04-30"
    assert r["vigencia"] == "" and r["tamanho_kb"] >= 1
    assert set(r) == {"sigla", "tipo", "data_criacao_pdf",
                      "data_modificacao_pdf", "vigencia", "tamanho_kb"}
