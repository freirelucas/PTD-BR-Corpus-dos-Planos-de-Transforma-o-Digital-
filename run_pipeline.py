#!/usr/bin/env python3
"""Executa o pipeline PTD fora do Jupyter (CI/headless).

Reproduz o notebook: exec sequencial de notebook_cells/*.py num namespace
compartilhado — a mesma semântica que o Jupyter dá às células. Saídas em
./ptd_output/ (mesmo layout do 01_setup local).

Com --sync, substitui output/ do repo pelo resultado do run e regenera os
derivados (build_metadata.py → datapackage/metadata;
build_corpus.py → harmonized/; build_xlsx.py → PTD-corpus.xlsx),
deixando a árvore pronta para commit.

Exit codes: 0 ok | 1 falha de pipeline ou gate | 2 portal SGD inacessível.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
import traceback

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
CELLS_DIR = os.path.join(REPO_ROOT, "notebook_cells")
RUN_OUTPUT = os.path.join(REPO_ROOT, "ptd_output", "output")
REPO_OUTPUT = os.path.join(REPO_ROOT, "output")

# Headless ANTES de qualquer import feito pelas células.
os.environ.setdefault("MPLBACKEND", "Agg")   # headless: sem display (defensivo)
os.environ.setdefault("TQDM_DISABLE", "1")   # tqdm>=4.66 honra TQDM_*

# Preflight após 03: BASE_URL/HTTP_HEADERS já estão no namespace e nenhuma
# célula tocou a rede ainda (04b é a primeira a fazer scraping).
PREFLIGHT_AFTER = "03_utils.py"

# QUALITY_THRESHOLDS (02_config) tem só TETOS + ratios mínimos — um portal
# devolvendo metade do corpus passaria neles. Pisos ≈75-80% do baseline
# 2026-05 (91 órgãos / 4574 entregas / 619 riscos).
FLOORS = {"orgaos": 80, "entregas": 3500, "riscos": 450}


def preflight(ns: dict) -> None:
    """HEAD no portal SGD; aborta com exit 2 (e mensagem clara) se inacessível."""
    import requests
    url = ns["BASE_URL"]
    exc_msg = ""
    try:
        resp = requests.head(url, headers=ns["HTTP_HEADERS"],
                             timeout=30, allow_redirects=True)
        code = resp.status_code
    except requests.RequestException as exc:
        code, exc_msg = None, f"{type(exc).__name__}: {exc}"
    if code is None or code >= 400:
        print("PREFLIGHT FALHOU: portal SGD inacessível "
              f"({exc_msg if code is None else f'HTTP {code}'}) — {url}")
        print("Causas prováveis: bloqueio do IP do runner pelo gov.br ou "
              "indisponibilidade do portal.")
        print("Fallback: fluxo manual via Colab (README §Publicar os dados).")
        sys.exit(2)
    print(f"PREFLIGHT ok: HTTP {code} em {url}")


def run_cells(skip_preflight: bool) -> None:
    ns: dict = {"__name__": "__main__"}
    for path in sorted(glob.glob(os.path.join(CELLS_DIR, "*.py"))):
        name = os.path.basename(path)
        t0 = time.time()
        print(f"\n{'=' * 70}\n=== CELL {name}\n{'=' * 70}", flush=True)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            exec(compile(src, path, "exec"), ns)
        except SystemExit:
            raise
        except BaseException:
            traceback.print_exc()
            print(f"\nFALHA na cell {name} — abortando.", flush=True)
            sys.exit(1)
        print(f"--- {name} ok em {time.time() - t0:.1f}s", flush=True)
        if name == PREFLIGHT_AFTER and not skip_preflight:
            preflight(ns)


def quality_gate() -> dict:
    """Gate final sobre validation_report.json (gerado pela célula 13b)."""
    path = os.path.join(RUN_OUTPUT, "validation_report.json")
    if not os.path.exists(path):
        print("GATE: validation_report.json ausente — 13b não rodou.")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)

    problems = []
    counts = report.get("counts", {})
    for key, floor in FLOORS.items():
        if counts.get(key, 0) < floor:
            problems.append(f"counts.{key}={counts.get(key)} < piso {floor}")
    if not report.get("all_thresholds_passed"):
        for name, t in report.get("thresholds", {}).items():
            if not t.get("passed"):
                problems.append(f"threshold {name}: actual={t['actual']} "
                                f"limite={t['limit']}")
    if problems:
        print("GATE DE QUALIDADE FALHOU:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    cz = report["canonization"]
    print("\nGATE OK — resumo do run:")
    print(f"  órgãos={counts['orgaos']}  entregas={counts['entregas']}  "
          f"riscos={counts['riscos']}  erros={counts['errors']}")
    print(f"  canonização: prob={cz['probabilidade']['rate']:.1%}  "
          f"imp={cz['impacto']['rate']:.1%}  trat={cz['tratamento']['rate']:.1%}")
    return report


def sync_repo() -> None:
    """ptd_output/output → output/ do repo + regeneração dos derivados.

    Delete-then-copy: converge o repo para a verdade do run, removendo
    artefatos órfãos de runs antigos (o Drive acumula; o repo não deve).
    """
    print("\nSYNC: substituindo output/ do repo pelo run novo…")
    for entry in os.listdir(REPO_OUTPUT):
        p = os.path.join(REPO_OUTPUT, entry)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    shutil.copytree(RUN_OUTPUT, REPO_OUTPUT, dirs_exist_ok=True)

    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import build_corpus
    import build_manifest
    import build_metadata
    import build_variations
    import build_xlsx
    if (build_manifest.main([]) != 0 or build_metadata.main([]) != 0
            or build_corpus.main([]) != 0 or build_variations.main([]) != 0
            or build_xlsx.main([]) != 0):
        print("SYNC: regeneração de manifest/metadados/corpus/variações/xlsx falhou.")
        sys.exit(1)
    print("SYNC ok: output/ pronto para commit.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Pipeline PTD headless (ver docstring do módulo).")
    ap.add_argument("--sync", action="store_true",
                    help="Após o run, sincroniza output/ do repo e regenera "
                         "datapackage/metadata/harmonized + PTD-corpus.xlsx.")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="Não testa o portal SGD antes do scraping.")
    args = ap.parse_args(argv)

    os.chdir(REPO_ROOT)   # 01_setup deriva BASE_DIR de os.getcwd()
    t0 = time.time()
    run_cells(args.skip_preflight)
    quality_gate()
    if args.sync:
        sync_repo()
    print(f"\nPIPELINE OK em {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
