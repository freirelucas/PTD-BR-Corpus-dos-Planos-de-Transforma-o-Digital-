#!/usr/bin/env python3
"""(Re)gera output/manifest.json a partir de output/ + git — derivador standalone.

No projeto PTD original (com analytics) o manifest era escrito DENTRO da célula
do dashboard (11cb_dashboard_data.py), acoplado ao cálculo das estatísticas.
Neste spin-off sem analytics ele vira um derivador independente, no mesmo padrão
de build_metadata.py / build_corpus.py: lê o que já está em output/, sem rodar o
pipeline nem acessar a rede. build_metadata.py consome este manifest
(data_execucao, pipeline_commit e o mapa outputs[].sha256) para montar os
descritores DCAT / PROV / CKAN.

Campos:
  pipeline_commit   git HEAD do repositório; se indisponível (ex.: árvore sem
                    git), preserva o valor do manifest existente.
  data_execucao     preservado do manifest existente; senão, UTC de hoje. É a
                    data do snapshot dos dados — só muda num run novo do pipeline.
  pdfs_*            baixados/diretivo/entregas são recontados de
                    output/pdf_metadata.csv; com_texto_extraido /
                    escaneados_pendentes / dedup_owners / compartilhados são
                    telemetria do run que extraiu os PDFs (não derivável dos
                    CSVs commitados) e portanto preservados do manifest anterior.
  outputs           {arquivo: {linhas, bytes, sha256}} dos arquivos de primeiro
                    nível em output/, exceto data.js, manifest.json e os
                    derivados (datapackage.json, variations.csv, PTD-corpus.xlsx
                    — fora para não criar ciclo de hash) e subdiretórios
                    (metadata/, harmonized/).

Uso:
  python build_manifest.py            # (re)grava output/manifest.json
  python build_manifest.py --check    # falha se o commitado está defasado (CI)

`--check` ignora pipeline_commit e data_execucao (mudam de forma independente
dos dados) e confere o invariante que importa: os hashes em outputs[] batem com
os arquivos, e as contagens de PDF batem com pdf_metadata.csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
MANIFEST = os.path.join(OUTPUT_DIR, "manifest.json")
PDF_METADATA = os.path.join(OUTPUT_DIR, "pdf_metadata.csv")

# Arquivos de primeiro nível que NÃO entram em outputs[]:
#   data.js          artefato de dashboard (não existe no spin-off)
#   manifest.json    auto-referência
#   datapackage.json derivado por build_metadata.py (evita ciclo de hash)
#   variations.csv   derivado por build_variations.py (idem)
#   PTD-corpus.xlsx  derivado por build_xlsx.py (conveniência binária; fora do
#                    grafo de proveniência, que é sobre os CSVs canônicos)
_OUTPUTS_EXCLUDE = {"data.js", "manifest.json", "datapackage.json",
                    "variations.csv", "PTD-corpus.xlsx"}

# Telemetria de PDFs preservada do manifest anterior (não derivável dos CSVs).
_PRESERVED_PDF_FIELDS = (
    "pdfs_com_texto_extraido",
    "pdfs_escaneados_pendentes",
    "pdfs_dedup_owners",
    "pdfs_compartilhados",
)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: str) -> int:
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


def _git_head() -> str:
    try:
        r = subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _load_prev() -> dict:
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def _pdf_counts() -> dict:
    """Conta PDFs por tipo a partir de output/pdf_metadata.csv (se existir)."""
    if not os.path.exists(PDF_METADATA):
        return {}
    diretivo = entregas = total = 0
    with open(PDF_METADATA, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            tipo = (row.get("tipo") or "").strip().lower()
            if tipo == "diretivo":
                diretivo += 1
            elif tipo == "entregas":
                entregas += 1
    return {"pdfs_baixados": total,
            "pdfs_diretivo": diretivo,
            "pdfs_entregas": entregas}


def _outputs_map() -> "OrderedDict[str, dict]":
    out: "OrderedDict[str, dict]" = OrderedDict()
    if not os.path.isdir(OUTPUT_DIR):
        return out
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if not os.path.isfile(fpath) or fname in _OUTPUTS_EXCLUDE:
            continue
        out[fname] = {"linhas": _line_count(fpath),
                      "bytes": os.path.getsize(fpath),
                      "sha256": _sha256(fpath)}
    return out


def build() -> "OrderedDict[str, object]":
    prev = _load_prev()
    m: "OrderedDict[str, object]" = OrderedDict()
    m["pipeline_commit"] = _git_head() or prev.get("pipeline_commit", "")
    m["data_execucao"] = prev.get("data_execucao") or \
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m.update(_pdf_counts())
    for k in _PRESERVED_PDF_FIELDS:
        if k in prev:
            m[k] = prev[k]
    m["outputs"] = _outputs_map()
    return m


def _serialize(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def _comparable(manifest: dict) -> dict:
    """Manifest sem os campos que mudam fora do controle dos dados."""
    m = dict(manifest)
    m.pop("pipeline_commit", None)
    m.pop("data_execucao", None)
    return m


def write(manifest: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(_serialize(manifest))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera output/manifest.json.")
    ap.add_argument("--check", action="store_true",
                    help="Falha se output/manifest.json commitado está defasado.")
    args = ap.parse_args(argv)

    manifest = build()
    if args.check:
        if not os.path.exists(MANIFEST):
            print("manifest.json ausente — rode `python build_manifest.py`.")
            return 1
        with open(MANIFEST, encoding="utf-8") as fh:
            committed = json.load(fh)
        if _comparable(committed) != _comparable(manifest):
            print("output/manifest.json defasado vs output/ — "
                  "rode `python build_manifest.py`.")
            return 1
        print(f"OK — manifest.json em dia ({len(manifest['outputs'])} "
              f"arquivos em outputs).")
        return 0

    write(manifest)
    commit = str(manifest["pipeline_commit"])[:7] or "(sem git)"
    print(f"manifest.json gravado — {len(manifest['outputs'])} arquivos em "
          f"outputs, commit={commit}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
