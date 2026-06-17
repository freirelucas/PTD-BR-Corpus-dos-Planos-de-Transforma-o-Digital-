"""Testes do derivador build_xlsx.py (pasta de trabalho Excel do corpus).

Cobre: estrutura/ordem das abas, integridade (linhas e colunas batem com os
CSVs canônicos), número preservado como número (resolve a armadilha decimal
pt-BR), o dicionário derivado do datapackage.json e a paridade do
PTD-corpus.xlsx commitado (mesmo guard --check da CI)."""
import os

import pandas as pd

import build_xlsx as bx

OUTPUT = bx.OUTPUT_DIR


def test_abas_estrutura_e_contagens(tmp_path):
    dest = tmp_path / "out.xlsx"
    bx.write(str(dest))
    xf = pd.ExcelFile(dest)
    assert xf.sheet_names == ["LEIA-ME", "entregas", "riscos", "órgãos",
                              "cobertura", "dicionário"]
    # cada aba de dados tem as mesmas dimensões do CSV de origem
    for csv, aba, _ in bx.SHEETS:
        src = pd.read_csv(os.path.join(OUTPUT, csv), encoding="utf-8-sig")
        assert xf.parse(aba).shape == src.shape, f"{aba} difere de {csv}"


def test_numero_e_numero(tmp_path):
    """Score de produto vira número (não texto) — o ganho central sobre o CSV."""
    dest = tmp_path / "out.xlsx"
    bx.write(str(dest))
    ent = pd.read_excel(dest, sheet_name="entregas")
    assert pd.api.types.is_numeric_dtype(ent["produto_score"])


def test_dicionario_vem_do_datapackage(tmp_path):
    dest = tmp_path / "out.xlsx"
    bx.write(str(dest))
    dic = pd.read_excel(dest, sheet_name="dicionário")
    assert list(dic.columns) == ["planilha", "coluna", "tipo", "descrição"]
    # datapackage presente no repo → ao menos uma descrição não-vazia
    assert dic["descrição"].fillna("").str.len().sum() > 0


def test_xlsx_commitado_em_dia():
    """O PTD-corpus.xlsx do repo bate com build_xlsx (mesmo guard da CI)."""
    assert bx.main(["--check"]) == 0
