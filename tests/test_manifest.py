"""Testes do derivador standalone build_manifest.py.

Cobre: (a) o mapa outputs[] hasheia os arquivos de primeiro nível e exclui
data.js / manifest.json / datapackage.json e subdiretórios; (b) as contagens de
PDF saem de pdf_metadata.csv; (c) build() preserva data_execucao/telemetria do
manifest anterior; (d) o manifest commitado no repo está em dia (mesmo guard
da CI)."""
import json

import build_manifest as bm


def _write(path, content="x\n"):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def test_outputs_exclui_derivados_e_subdirs(tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "metadata").mkdir(parents=True)
    for f in ("risks.csv", "deliveries.json", "data.js",
              "manifest.json", "datapackage.json"):
        _write(out / f)
    _write(out / "metadata" / "dcat.jsonld", "{}")
    monkeypatch.setattr(bm, "OUTPUT_DIR", str(out))

    outputs = bm._outputs_map()
    assert set(outputs) == {"risks.csv", "deliveries.json"}
    for meta in outputs.values():
        assert set(meta) == {"linhas", "bytes", "sha256"}
        assert len(meta["sha256"]) == 64


def test_pdf_counts(tmp_path, monkeypatch):
    csv_path = tmp_path / "pdf_metadata.csv"
    _write(csv_path,
           "sigla,tipo,tamanho_kb\nA,diretivo,1\nA,entregas,2\nB,diretivo,3\n")
    monkeypatch.setattr(bm, "PDF_METADATA", str(csv_path))
    assert bm._pdf_counts() == {"pdfs_baixados": 3,
                                "pdfs_diretivo": 2, "pdfs_entregas": 1}


def test_build_preserva_data_execucao_e_telemetria(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    _write(out / "risks.csv")
    prev = {"pipeline_commit": "deadbeef", "data_execucao": "2026-05-12",
            "pdfs_escaneados_pendentes": 10, "outputs": {}}
    _write(out / "manifest.json", json.dumps(prev))
    monkeypatch.setattr(bm, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(bm, "MANIFEST", str(out / "manifest.json"))
    monkeypatch.setattr(bm, "PDF_METADATA", str(out / "pdf_metadata.csv"))
    monkeypatch.setattr(bm, "_git_head", lambda: "")

    m = bm.build()
    assert m["data_execucao"] == "2026-05-12"
    assert m["pipeline_commit"] == "deadbeef"   # fallback p/ prev quando sem git
    assert m["pdfs_escaneados_pendentes"] == 10
    assert "risks.csv" in m["outputs"]


def test_manifest_commitado_em_dia():
    """O manifest do repo bate com build_manifest (ignora commit/data)."""
    assert bm.main(["--check"]) == 0
