#!/usr/bin/env python3
"""Smoke test do notebook PTD — verificação leve de saúde do pipeline.

NÃO roda a extração de verdade (que baixa PDFs do gov.br e leva minutos).
Confirma, em camadas, que o notebook está íntegro e carregável:

  offline (padrão):
    1. py_compile de todas as cells (sintaxe)
    2. ptd_scraper.ipynb é JSON/nbformat válido
    3. as dependências de requirements.txt importam
    4. todas as cells carregam suas definições na ordem do notebook
       (full-exec 01/02/03; filtro AST no resto, descartando a execução de
        pipeline que exigiria rede/PDFs)

  --live (opcional, requer rede):
    5. conectividade com o portal SGD + scrape_organ_listing() ao vivo,
       reportando nº de órgãos vs baseline (~91). Não falha por rede indisponível.

Uso:
  python smoke_test.py            # offline
  python smoke_test.py --live     # offline + scraper ao vivo
Exit ≠ 0 se qualquer checagem offline falhar.
"""
from __future__ import annotations

import argparse
import ast
import glob
import os
import py_compile
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
CELLS_DIR = os.path.join(REPO_ROOT, "notebook_cells")
NOTEBOOK = os.path.join(REPO_ROOT, "ptd_scraper.ipynb")

# Reaproveita o loader AST-filtered já usado pelos testes (DRY).
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
import conftest  # noqa: E402

# Cells determinísticas → exec completo; o resto → só definições.
_FULL = {"01_setup.py", "02_config.py", "03_utils.py"}
_REQUIREMENTS = {
    "pymupdf": "fitz", "beautifulsoup4": "bs4", "requests": "requests",
    "tqdm": "tqdm", "pandas": "pandas",
}
# pypdf é importado lazy dentro do pipeline → opcional para carga.
_OPTIONAL = {"pypdf": "pypdf"}
_KEY_SYMBOLS = ["safe_request", "scrape_organ_listing", "extract_risk_table",
                "standardize_deliveries", "standardize_risks",
                "classify_diretivo_table"]


def _ok(msg):
    print(f"  OK   {msg}")


def _fail(msg):
    print(f"  FAIL {msg}")


def check_syntax() -> bool:
    print("[1] Sintaxe das cells")
    bad = []
    for path in sorted(glob.glob(os.path.join(CELLS_DIR, "*.py"))):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            bad.append(f"{os.path.basename(path)}: {e}")
    if bad:
        for b in bad:
            _fail(b)
        return False
    _ok(f"{len(glob.glob(os.path.join(CELLS_DIR, '*.py')))} cells compilam")
    return True


def check_notebook() -> bool:
    print("[2] ptd_scraper.ipynb válido")
    try:
        try:
            import nbformat
            nb = nbformat.read(NOTEBOOK, as_version=4)
            nbformat.validate(nb)
            _ok(f"nbformat válido — {len(nb.cells)} cells")
        except ImportError:
            import json
            with open(NOTEBOOK, encoding="utf-8") as fh:
                d = json.load(fh)
            _ok(f"JSON válido — {len(d['cells'])} cells (nbformat ausente)")
        return True
    except Exception as e:
        _fail(f"notebook inválido: {e}")
        return False


def check_deps() -> bool:
    print("[3] Dependências de runtime")
    import importlib
    missing = []
    for pkg, mod in _REQUIREMENTS.items():
        try:
            importlib.import_module(mod)
        except Exception as e:
            missing.append(f"{pkg} ({mod}): {type(e).__name__}")
    for pkg, mod in _OPTIONAL.items():
        try:
            importlib.import_module(mod)
            _ok(f"{pkg} (opcional) disponível")
        except Exception as e:
            print(f"  WARN {pkg} (opcional, import lazy no pipeline): {type(e).__name__}")
    if missing:
        for m in missing:
            _fail(m)
        return False
    _ok(f"{len(_REQUIREMENTS)} deps obrigatórias importam")
    return True


def check_load() -> bool:
    print("[4] Carga das definições do pipeline (ordem do notebook)")
    ns = conftest._base_namespace()
    cells = sorted(glob.glob(os.path.join(CELLS_DIR, "*.py")))
    failed = []
    for path in cells:
        name = os.path.basename(path)
        try:
            src = open(path, encoding="utf-8").read()
            code = (compile(src, path, "exec") if name in _FULL
                    else conftest._defs_only_source(src, path))
            exec(code, ns)
        except Exception as e:
            failed.append((name, repr(e)))
            traceback.print_exc()
    if failed:
        for n, e in failed:
            _fail(f"{n}: {e}")
        return False
    missing = [k for k in _KEY_SYMBOLS if k not in ns]
    if missing:
        _fail(f"símbolos ausentes no namespace: {missing}")
        return False
    _ok(f"{len(cells)} cells carregadas; símbolos-chave presentes")
    return True


def check_live() -> bool:
    print("[5] Scraper ao vivo (--live)")
    ns = conftest._load_cells()
    url = ns.get("BASE_URL")
    try:
        import requests
        r = requests.get(url, timeout=15, headers={"User-Agent": "PTD-smoke"})
        _ok(f"portal SGD acessível: HTTP {r.status_code}, {len(r.content)} bytes")
    except Exception as e:
        print(f"  WARN rede indisponível neste ambiente: {type(e).__name__} "
              f"(checagem ao vivo pulada, não-fatal)")
        return True
    try:
        organs = ns["scrape_organ_listing"](url)
        n = len(organs)
        baseline_ok = 70 <= n <= 130
        _ok(f"scrape_organ_listing: {n} órgãos "
            f"({'dentro do baseline ~91' if baseline_ok else 'FORA do baseline'})")
        if not baseline_ok:
            print("  WARN nº de órgãos fora do esperado — possível mudança no portal")
    except Exception as e:
        _fail(f"scraper quebrou contra o HTML atual: {e}")
        return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="Inclui probe de conectividade + scraper ao vivo.")
    args = ap.parse_args(argv)

    print("=== SMOKE TEST — PTD ===")
    results = [check_syntax(), check_notebook(), check_deps(), check_load()]
    if args.live:
        check_live()  # informativo, não entra no veredito offline

    ok = all(results)
    print(f"\n{'✓ SMOKE OK' if ok else '✗ SMOKE FALHOU'} "
          f"({sum(results)}/{len(results)} checagens offline)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
