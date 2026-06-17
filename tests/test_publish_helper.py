"""Testes da célula 13c (bundle de publicação): zip recursivo de output/ e
validação dos artefatos essenciais.

Spin-off sem analytics: a lista de essenciais não inclui data.js,
statistics_summary.json, review_data.json nem nota_tecnica_insumos.md.
manifest.json e coverage_summary.csv saíram da lista — são derivados
pós-pipeline (build_manifest.py / build_coverage.py), não saídas das células."""
import os
import zipfile

import pytest

CELL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "notebook_cells", "13c_publish_helper.py")

ESSENCIAIS = [
    "validation_report.json",
    "pdf_metadata.csv", "risks.csv", "risks.json",
    "deliveries.csv", "deliveries.json", "organs.csv", "error_report.csv",
    "vocabulary_mapping.csv",
]


def _exec_13c(out_dir):
    """Full-exec da célula com DIRS apontando para um output/ sintético."""
    ns = {"DIRS": {"output": str(out_dir)}}
    with open(CELL_PATH, encoding="utf-8") as f:
        exec(compile(f.read(), CELL_PATH, "exec"), ns)
    return ns


def _make_output(tmp_path):
    out = tmp_path / "output"
    (out / "metadata").mkdir(parents=True)
    (out / "harmonized").mkdir()
    for fname in ESSENCIAIS:
        (out / fname).write_text("conteudo", encoding="utf-8")
    (out / "metadata" / "dcat.jsonld").write_text("{}", encoding="utf-8")
    (out / "harmonized" / "risks.csv").write_text("a,b\n", encoding="utf-8")
    return out


def test_13c_zip_recursivo_completo(tmp_path):
    out = _make_output(tmp_path)
    _exec_13c(out)
    zips = list(tmp_path.glob("output_*.zip"))
    assert len(zips) == 1
    names = zipfile.ZipFile(zips[0]).namelist()
    assert "output/risks.csv" in names
    assert "output/pdf_metadata.csv" in names
    assert "output/metadata/dcat.jsonld" in names
    assert "output/harmonized/risks.csv" in names
    # todos os arcnames sob output/ (sem path traversal)
    assert all(n.startswith("output/") and ".." not in n for n in names)
    assert len(names) == len(ESSENCIAIS) + 2


def test_13c_falha_com_essencial_ausente(tmp_path):
    out = _make_output(tmp_path)
    os.remove(out / "risks.csv")
    os.remove(out / "vocabulary_mapping.csv")
    with pytest.raises(RuntimeError) as exc:
        _exec_13c(out)
    assert "risks.csv" in str(exc.value)
    assert "vocabulary_mapping.csv" in str(exc.value)
    assert not list(tmp_path.glob("output_*.zip"))   # nada zipado
