#!/usr/bin/env python3
"""(Re)gera output/coverage_summary.csv — cobertura de extração por órgão.

Por que é um derivador (e não uma célula). A cobertura é função PURA dos CSVs
já exportados: organs.csv (URLs dos PDFs de cada órgão) + deliveries.csv +
risks.csv (contagens por órgão). Não depende dos PDFs nem da rede — então segue
o padrão de build_variations.py / build_manifest.py (lê output/, --check no CI)
em vez de viver no pipeline do notebook. Reproduz o snapshot byte-a-byte.

Uma linha por órgão:
  pdf_diretivo / pdf_entregas       "sim"/"nao" — o órgão tem URL daquele documento
  entregas_extraidas / riscos_extraidos   contagem em deliveries / risks
  status_entregas:
    ok             extraiu entregas (n > 0)
    compartilhado  n == 0, mas o PDF de entregas é compartilhado (mesma URL) com
                   outro órgão que TEM dados — a entrega está sob o "dono"
    sem_dados      n == 0 e o PDF não rende dados a ninguém (provável escaneado)
  status_riscos:
    sem_pdf        o órgão não tem Documento Diretivo (sem URL)
    ok             extraiu riscos (n > 0)
    compartilhado  n == 0, PDF diretivo compartilhado com órgão que tem dados
    no_risk_table  n == 0, PDF próprio, mas sem tabela de risco reconhecida

Uso:
  python build_coverage.py            # (re)grava output/coverage_summary.csv
  python build_coverage.py --check    # falha se o commitado está defasado (CI)
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
ORGANS = os.path.join(OUTPUT_DIR, "organs.csv")
DELIVERIES = os.path.join(OUTPUT_DIR, "deliveries.csv")
RISKS = os.path.join(OUTPUT_DIR, "risks.csv")
COVERAGE = os.path.join(OUTPUT_DIR, "coverage_summary.csv")

COLUMNS = ["sigla", "grupo", "pdf_diretivo", "pdf_entregas",
           "entregas_extraidas", "riscos_extraidos",
           "status_entregas", "status_riscos"]


def _read(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _share_index(organs: list, url_field: str, counts: Counter) -> tuple:
    """Para cada URL: quantos órgãos a compartilham e se algum deles tem dados.

    'Compartilhado' = o PDF (mesma URL) é de >1 órgão e o dado foi extraído sob
    um deles (o dono). Se ninguém do grupo tem dados, não é compartilhamento
    útil — é PDF sem dados (sem_dados / no_risk_table).
    """
    sharers: "defaultdict[str, list]" = defaultdict(list)
    for o in organs:
        url = o.get(url_field) or ""
        if url:
            sharers[url].append(o.get("sigla", ""))
    n_sharers = {url: len(sigs) for url, sigs in sharers.items()}
    has_owner = {url: any(counts.get(s, 0) > 0 for s in sigs)
                 for url, sigs in sharers.items()}
    return n_sharers, has_owner


def build() -> list:
    organs = _read(ORGANS)
    n_del = Counter(r.get("orgao_sigla", "") for r in _read(DELIVERIES))
    n_risk = Counter(r.get("orgao_sigla", "") for r in _read(RISKS))
    n_shareE, ownerE = _share_index(organs, "url_entregas", n_del)
    n_shareD, ownerD = _share_index(organs, "url_diretivo", n_risk)

    rows = []
    for o in organs:
        sigla = o.get("sigla", "")
        url_e = o.get("url_entregas") or ""
        url_d = o.get("url_diretivo") or ""
        ne, nr = n_del.get(sigla, 0), n_risk.get(sigla, 0)

        if ne > 0:
            status_e = "ok"
        elif url_e and n_shareE.get(url_e, 0) > 1 and ownerE.get(url_e):
            status_e = "compartilhado"
        else:
            status_e = "sem_dados"

        if not url_d:
            status_r = "sem_pdf"
        elif nr > 0:
            status_r = "ok"
        elif n_shareD.get(url_d, 0) > 1 and ownerD.get(url_d):
            status_r = "compartilhado"
        else:
            status_r = "no_risk_table"

        rows.append({
            "sigla": sigla, "grupo": o.get("grupo", ""),
            "pdf_diretivo": "sim" if url_d else "nao",
            "pdf_entregas": "sim" if url_e else "nao",
            "entregas_extraidas": str(ne), "riscos_extraidos": str(nr),
            "status_entregas": status_e, "status_riscos": status_r,
        })
    rows.sort(key=lambda r: r["sigla"])
    return rows


def _serialize(rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def write(rows: list) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(COVERAGE, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(_serialize(rows))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera output/coverage_summary.csv.")
    ap.add_argument("--check", action="store_true",
                    help="Falha se output/coverage_summary.csv commitado está defasado.")
    args = ap.parse_args(argv)

    rows = build()
    content = _serialize(rows)
    if args.check:
        if not os.path.exists(COVERAGE):
            print("coverage_summary.csv ausente — rode `python build_coverage.py`.")
            return 1
        with open(COVERAGE, encoding="utf-8-sig") as fh:
            if fh.read() != content:
                print("output/coverage_summary.csv defasado vs output/ — "
                      "rode `python build_coverage.py`.")
                return 1
        print(f"OK — coverage_summary.csv em dia ({len(rows)} órgãos).")
        return 0

    write(rows)
    se = Counter(r["status_entregas"] for r in rows)
    sr = Counter(r["status_riscos"] for r in rows)
    print(f"coverage_summary.csv gravado — {len(rows)} órgãos.")
    print(f"  entregas: {dict(se)}")
    print(f"  riscos:   {dict(sr)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
