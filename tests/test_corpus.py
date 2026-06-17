"""Testes para build_corpus.py — harmonização do corpus.

Cobre a regra célula-a-célula (`harmonize_cell`), a harmonização de tabela
(incluindo a re-sinalização de `needs_review`), o datapackage estrito e a
consistência dos artefatos commitados.
"""
import csv
import io
import json

import pytest

import build_corpus as bc
import build_metadata as bm


# ---------------------- harmonize_cell ----------------------

def test_cell_keeps_canonical():
    assert bc.harmonize_cell("raro", bm.PROBABILIDADE) == ("raro", None)


def test_cell_blank_stays_blank():
    for v in ("", "  ", None, "nan"):
        assert bc.harmonize_cell(v, bm.TRATAMENTO) == ("", None)


def test_cell_dedup_compound_single_token():
    assert bc.harmonize_cell("transferir; transferir", bm.TRATAMENTO) == ("transferir", "deduplicado")


def test_cell_multiple_distinct_canonical_blanked():
    out, reason = bc.harmonize_cell("mitigar; transferir", bm.TRATAMENTO)
    assert out == "" and reason == "multiplos_valores"


def test_cell_column_bleed_blanked():
    out, reason = bc.harmonize_cell("- Sensibilização para apoio da alta administração", bm.TRATAMENTO)
    assert out == "" and reason == "column_bleed"


def test_cell_bleed_in_probability_scale():
    out, reason = bc.harmonize_cell("de de Ocor-", bm.PROBABILIDADE)
    assert out == "" and reason == "column_bleed"


# ---------------------- harmonize_table ----------------------

def test_harmonize_table_risks_changes_recorded():
    fieldnames, rows, changes = bc.harmonize_table("risks")
    assert changes, "esperava alterações nos riscos"
    # Todo change tem os campos de auditoria.
    for c in changes[:5]:
        assert {"orgao", "campo", "original_normalizado", "harmonizado", "motivo"} <= set(c)


def test_harmonize_table_blanks_are_canonical_or_empty():
    fieldnames, rows, _ = bc.harmonize_table("risks")
    allowed = {c: set(v) | {""} for c, v in bc.CANONICAL.items()}
    for row in rows:
        for col, ok in allowed.items():
            if col in fieldnames:
                assert (row[col] or "").strip() in ok


def test_harmonize_bleed_rows_get_needs_review():
    fieldnames, rows, changes = bc.harmonize_table("risks")
    bleed_rows = {c["row"] for c in changes if c["motivo"] in ("column_bleed", "multiplos_valores")}
    for i in bleed_rows:
        assert str(rows[i]["needs_review"]).strip().lower() == "true"
        assert "harmonizacao(" in rows[i]["review_reason"]


def test_harmonize_preserves_original_column():
    # O valor cru deve continuar em *_original mesmo após branquear o normalizado.
    fieldnames, rows, changes = bc.harmonize_table("risks")
    c = next(x for x in changes if x["campo"] == "tratamento_normalizado"
             and x["motivo"] == "column_bleed")
    assert rows[c["row"]]["tratamento_original"].strip() != ""


def test_organs_unchanged():
    _, _, changes = bc.harmonize_table("organs")
    assert changes == []


# ---------------------- datapackage estrito ----------------------

def test_strict_fields_inject_enum():
    strict = bc._strict_fields(bm.RISKS_FIELDS)
    by_name = {f["name"]: f for f in strict}
    assert by_name["probabilidade_normalizada"]["enum"] == bm.PROBABILIDADE
    assert by_name["tratamento_normalizado"]["enum"] == bm.TRATAMENTO


def test_harmonized_datapackage_validates_strictly():
    frictionless = pytest.importorskip("frictionless")
    import warnings
    warnings.simplefilter("ignore")
    # Garante que os CSVs harmonizados em disco refletem o gerador.
    bc.write(bc.generate())
    report = frictionless.Package(
        bm.os.path.join(bc.HARM_DIR, "datapackage.json")).validate()
    assert report.valid, report.flatten(["fieldName", "type", "note"])[:10]


# ---------------------- report + consistência ----------------------

def test_report_totals_match_changes():
    arts = bc.generate()
    report = json.loads(arts["output/harmonized/harmonization_report.json"])
    soma = sum(report["por_tabela"].values())
    assert report["total_alteracoes"] == soma == sum(report["por_motivo"].values())


def test_committed_harmonized_in_sync():
    """output/harmonized/ deve refletir build_corpus.py."""
    stale = bc.check(bc.generate())
    assert stale == [], f"Harmonizado defasado: {stale}"


# ---------------------- bundle_zip (make corpus-zip) ----------------------

def test_bundle_zip_conteudo_e_determinismo(tmp_path):
    import os
    import zipfile
    arts = bc.generate()
    z1 = tmp_path / "a.zip"
    out, members = bc.bundle_zip(arts, out_path=str(z1))
    assert out == str(z1)

    names = zipfile.ZipFile(z1).namelist()
    # tudo sob uma única pasta ptd-corpus-<snapshot>/, sem caminhos crus de output/
    assert names and all(n.startswith("ptd-corpus-") and "/" in n for n in names)
    base = {n.split("/", 1)[1] for n in names}
    # o corpus e o descritor — não data.js, figures, statistics, review_queue…
    assert {"deliveries.csv", "risks.csv", "organs.csv", "datapackage.json"} <= base
    assert "data.js" not in base and "statistics_summary.json" not in base
    # manifest.json entra se existir no output/ do repo (proveniência)
    if os.path.exists(os.path.join(bc.OUTPUT_DIR, "manifest.json")):
        assert "manifest.json" in base

    # determinístico: regerar produz bytes idênticos (timestamps fixos)
    z2 = tmp_path / "b.zip"
    bc.bundle_zip(arts, out_path=str(z2))
    assert z1.read_bytes() == z2.read_bytes()
