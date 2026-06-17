#!/usr/bin/env python3
"""Harmoniza o corpus PTD e empacota um conjunto coerente de dados abertos.

Motivação: o corpus passou por muitas transformações (scraping → extração →
normalização → canonização). Restaram, nas colunas `*_normalizado`, alguns
valores NÃO canônicos — artefatos de column-bleed que vazaram texto bruto
(ex.: `de de Ocor-`, listas de ações inteiras) e compostos (`transferir;
transferir`). Este script produz uma VISÃO HARMONIZADA do corpus em que essas
colunas ficam estritamente canônicas, de forma reversível e auditável:

  - O valor cru permanece em `*_original` (intacto).
  - Cada célula alterada é registrada em harmonization_report.json.
  - Linhas com bleed que escaparam ao `needs_review` são re-sinalizadas.

Saídas (em output/harmonized/):
  - organs.csv / risks.csv / deliveries.csv   versão harmonizada (mesmo schema)
  - harmonization_report.json                 toda alteração, com motivo + contagens
  - datapackage.json                          Frictionless com enums ESTRITOS
                                              (validável porque os dados agora conformam)
  - README.md                                 explica a linhagem e o pacote

Uso:
  python build_corpus.py            # (re)gera output/harmonized/
  python build_corpus.py --check    # falha se a versão commitada está defasada
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys

import build_metadata as bm

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
HARM_DIR = os.path.join(OUTPUT_DIR, "harmonized")

# Colunas normalizadas com vocabulário canônico fechado e a escala correspondente.
# produto_normalizado fica de fora do enum (55 produtos + 'Outros'); é checado
# contra o conjunto canônico para harmonização mas não recebe enum no schema.
CANONICAL = {
    "probabilidade_normalizada": bm.PROBABILIDADE,
    "impacto_normalizado": bm.IMPACTO,
    "tratamento_normalizado": bm.TRATAMENTO,
    "eixo_normalizado": bm.EIXOS,
}
SPLIT_RE = re.compile(r"[;|]")


def _is_blank(v):
    return v is None or str(v).strip() == "" or str(v).strip().lower() == "nan"


def harmonize_cell(value, allowed):
    """Harmoniza um valor de coluna normalizada contra `allowed` (set canônico).

    Retorna (valor_harmonizado, motivo|None). motivo None = sem alteração.
      - canônico exato            → mantém
      - vazio                     → mantém vazio
      - composto de canônicos     → dedup; 1 token → token; vários → branco + 'multiplos_valores'
      - qualquer outra coisa      → branco + 'column_bleed'
    """
    if _is_blank(value):
        return "", None
    v = str(value).strip()
    if v in allowed:
        return v, None
    tokens = [t.strip() for t in SPLIT_RE.split(v) if t.strip()]
    if tokens and all(t in allowed for t in tokens):
        uniq = list(dict.fromkeys(tokens))
        if len(uniq) == 1:
            return uniq[0], "deduplicado"
        return "", "multiplos_valores"
    return "", "column_bleed"


def _read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def _write_rows(fieldnames, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def harmonize_table(name, id_field="orgao_sigla"):
    """Harmoniza um CSV. Retorna (fieldnames, rows, changes)."""
    fieldnames, rows = _read_rows(os.path.join(OUTPUT_DIR, f"{name}.csv"))
    cols = [c for c in CANONICAL if c in fieldnames]
    changes = []
    for idx, row in enumerate(rows):
        flagged_reasons = []
        for col in cols:
            new, reason = harmonize_cell(row.get(col), CANONICAL[col])
            if reason is not None and new != (row.get(col) or "").strip():
                changes.append({
                    "row": idx,
                    "orgao": row.get(id_field, ""),
                    "campo": col,
                    "original_normalizado": row.get(col, ""),
                    "harmonizado": new,
                    "motivo": reason,
                })
                row[col] = new
                if reason in ("column_bleed", "multiplos_valores"):
                    flagged_reasons.append(f"{col}:{reason}")
        # Harmoniza o flag de revisão: toda célula branqueada por bleed/múltiplos
        # é anotada em review_reason (auditoria) e a linha vai para needs_review.
        if flagged_reasons and "needs_review" in fieldnames:
            row["needs_review"] = "True"
            extra = "harmonizacao(" + ",".join(flagged_reasons) + ")"
            row["review_reason"] = (
                (row.get("review_reason") or "").strip() + "; " + extra
            ).lstrip("; ")
    return fieldnames, rows, changes


# ---------------------------------------------------------------------------
# Datapackage harmonizado: enums ESTRITOS (os dados agora conformam).
# ---------------------------------------------------------------------------
def _strict_fields(base_fields):
    """Copia os campos do build_metadata injetando enum canônico nas escalas."""
    out = []
    for fld in base_fields:
        fld = dict(fld)
        if fld["name"] in CANONICAL:
            fld["enum"] = list(CANONICAL[fld["name"]])
        out.append(fld)
    return out


def build_harmonized_datapackage(citation, sha_by_file):
    specs = {
        "organs": (bm.ORGANS_FIELDS, "sigla", []),
        "risks": (_strict_fields(bm.RISKS_FIELDS), None,
                  [("orgao_sigla", "organs", "sigla")]),
        "deliveries": (_strict_fields(bm.DELIVERIES_FIELDS), None,
                       [("orgao_sigla", "organs", "sigla")]),
    }
    resources = []
    for name, (fields, pk, fks) in specs.items():
        schema = {"fields": [bm.to_frictionless_field(x) for x in fields]}
        if pk:
            schema["primaryKey"] = pk
        if fks:
            schema["foreignKeys"] = [
                {"fields": fk[0], "reference": {"resource": fk[1], "fields": fk[2]}}
                for fk in fks
            ]
        res = {"name": name, "path": f"{name}.csv", "format": "csv",
               "mediatype": "text/csv", "encoding": "utf-8", "schema": schema}
        if sha_by_file.get(name):
            res["hash"] = f"sha256:{sha_by_file[name]}"
        resources.append(res)
    created = str(citation.get("date-released", "")).strip()
    if len(created) == 10:
        created = f"{created}T00:00:00Z"
    return {
        "name": "ptd-corpus-harmonizado",
        "title": str(citation.get("title", "PTD")) + " — visão harmonizada",
        "description": ("Visão harmonizada do corpus PTD: as colunas *_normalizado "
                        "contêm apenas valores canônicos (ou vazio). Valores crus "
                        "preservados em *_original; alterações em harmonization_report.json."),
        "version": str(citation.get("version", "")),
        "created": created,
        "homepage": citation.get("url", bm.BASE),
        "licenses": [{"name": "CC-BY-4.0",
                      "title": "Creative Commons Attribution 4.0 International",
                      "path": "https://creativecommons.org/licenses/by/4.0/"}],
        "sources": [{"title": "Corpus PTD (output/ não harmonizado)",
                     "path": f"{bm.BASE}/output/datapackage.json"}],
        "resources": resources,
    }


HARM_README = """# Corpus PTD — visão harmonizada

Gerado por [`build_corpus.py`](../../build_corpus.py) a partir de `output/*.csv`.

## O que muda em relação a `output/`

As colunas `*_normalizado` (probabilidade, impacto, tratamento, eixo) contêm
**apenas valores canônicos ou vazio**. Valores não canônicos remanescentes —
artefatos de *column-bleed* e compostos — são removidos da coluna normalizada,
mas:

- o valor cru permanece intacto em `*_original`;
- toda alteração está em [`harmonization_report.json`](harmonization_report.json)
  (órgão, campo, valor original, motivo);
- linhas cujo bleed havia escapado ao `needs_review` são re-sinalizadas.

Nada é perdido — a harmonização é **reversível** via `*_original` + report.

## Linhagem (cadeia de transformações)

```
PTDs (PDF, portal SGD/MGI)
  → scraping de URLs (cell 04b)
  → download + dedup MD5 (05b/05c)
  → extração tabular PyMuPDF (06b/07b/08b)
  → normalização + canonização vs. escalas/produtos SGD (09b)
  → export CSV/JSON (10b) ........................ output/
  → descritores de dados abertos (build_metadata.py) ... output/datapackage.json, metadata/
  → HARMONIZAÇÃO (build_corpus.py) ............... output/harmonized/   ← você está aqui
```

## Contrato estrito

`datapackage.json` aqui usa enums **estritos** nas escalas canônicas — algo que
o datapackage de `output/` não pode fazer, porque os dados crus ainda carregam
valores em revisão. Validar:

```bash
pip install frictionless
frictionless validate output/harmonized/datapackage.json
```
"""


def _sha256(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate():
    """Constrói os artefatos harmonizados em memória. Retorna {rel_path: conteúdo}."""
    citation = bm.load_citation()

    tables = {}
    all_changes = {}
    for name in ("organs", "risks", "deliveries"):
        fieldnames, rows, changes = harmonize_table(name)
        tables[name] = _write_rows(fieldnames, rows)
        all_changes[name] = changes

    sha_by_file = {name: _sha256(content) for name, content in tables.items()}

    # Relatório de harmonização (auditável).
    by_reason = {}
    for name, changes in all_changes.items():
        for c in changes:
            by_reason[c["motivo"]] = by_reason.get(c["motivo"], 0) + 1
    report = {
        "gerado_de": "output/*.csv",
        "total_alteracoes": sum(len(c) for c in all_changes.values()),
        "por_motivo": by_reason,
        "por_tabela": {k: len(v) for k, v in all_changes.items()},
        "alteracoes": all_changes,
    }

    artifacts = {f"output/harmonized/{n}.csv": c for n, c in tables.items()}
    artifacts["output/harmonized/harmonization_report.json"] = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    artifacts["output/harmonized/datapackage.json"] = (
        json.dumps(build_harmonized_datapackage(citation, sha_by_file),
                   ensure_ascii=False, indent=2) + "\n")
    artifacts["output/harmonized/README.md"] = HARM_README
    return artifacts


def write(artifacts):
    os.makedirs(HARM_DIR, exist_ok=True)
    for rel, content in artifacts.items():
        path = os.path.join(REPO_ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def check(artifacts):
    stale = []
    for rel, content in artifacts.items():
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            stale.append(rel)
            continue
        with open(path, encoding="utf-8") as fh:
            if fh.read() != content:
                stale.append(rel)
    return stale


def bundle_zip(artifacts, out_path=None):
    """Empacota SÓ o corpus num zip distribuível e autocontido.

    Conteúdo: os artefatos de `output/harmonized/` (datapackage.json +
    deliveries/risks/organs.csv + harmonization_report.json + README.md) mais
    `manifest.json` para proveniência (commit do pipeline + data do snapshot),
    sob a pasta `ptd-corpus-<snapshot>/`. É o dataset citável, sem o restante de
    `output/` (dashboard, figuras, fila de revisão, estatísticas).

    Determinístico: os timestamps das entradas são fixados na data do snapshot,
    então o mesmo snapshot produz o mesmo zip (bit-exact).
    """
    import zipfile

    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    manifest_raw = None
    snapshot = "snapshot"
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest_raw = fh.read()
        snapshot = json.loads(manifest_raw).get("data_execucao") or snapshot

    members = {os.path.basename(rel): content for rel, content in artifacts.items()}
    if manifest_raw is not None:
        members["manifest.json"] = manifest_raw

    try:
        y, m, d = (int(x) for x in snapshot.split("-")[:3])
        date_time = (y, m, d, 0, 0, 0)
    except ValueError:
        date_time = (1980, 1, 1, 0, 0, 0)

    top = f"ptd-corpus-{snapshot}"
    if out_path is None:
        out_path = os.path.join(REPO_ROOT, f"corpus_{snapshot}.zip")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members):
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, members[name])
    return out_path, sorted(members)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="Falha se output/harmonized/ commitado está defasado.")
    ap.add_argument("--zip", action="store_true",
                    help="Empacota só o corpus (harmonized/ + manifest.json) "
                         "em corpus_<snapshot>.zip, sem o resto de output/.")
    args = ap.parse_args(argv)

    artifacts = generate()
    if args.zip:
        out_path, members = bundle_zip(artifacts)
        print(f"Corpus empacotado: {out_path}")
        for name in members:
            print(f"  - {name}")
        return 0
    if args.check:
        stale = check(artifacts)
        if stale:
            print("Corpus harmonizado defasado (rode `python build_corpus.py`):")
            for s in stale:
                print(f"  - {s}")
            return 1
        print(f"OK — {len(artifacts)} artefatos harmonizados em dia.")
        return 0

    write(artifacts)
    rep = json.loads(artifacts["output/harmonized/harmonization_report.json"])
    print(f"Harmonização concluída: {rep['total_alteracoes']} células alteradas "
          f"{rep['por_motivo']}")
    for rel in artifacts:
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
