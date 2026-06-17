"""Carrega notebook_cells/*.py num namespace compartilhado para testes.

Os cells assumem o namespace global do Jupyter — para testá-los como Python
puro, carregamos via exec() num dict dummy e expomos os símbolos pela fixture
`cells`.

Dois modos de carregamento:

* **full** — exec do cell inteiro. Usado em 02_config/03_utils, que são
  puramente declarativos (dataclasses, constantes, funções; os únicos side
  effects são prints e caches lazy, todos toleráveis).

* **defs** — para cells de pipeline (04b, 06b, 08b, 09b, ...) que, além de
  definir funções, EXECUTAM o pipeline no nível de módulo
  (`all_organs = scrape_organ_listing(BASE_URL)` dispara HTTP real,
  `extract_all_deliveries()` lê PDFs do disco). Filtramos o AST para manter
  apenas imports, defs/classes e constantes literais — descartando chamadas,
  ifs, loops e prints de topo de módulo. Assim as funções ficam disponíveis
  para teste sem rodar o pipeline.
"""
import ast
import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELLS_DIR = os.path.join(REPO_ROOT, "notebook_cells")

# Permite `import build_metadata` (script no topo do repo) a partir dos testes.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Cells carregados por inteiro (declarativos, exec seguro).
_FULL_CELLS = ("02_config.py", "03_utils.py")

# Cells de pipeline: só defs + constantes literais (ver docstring do módulo).
# Adicione aqui conforme novos testes precisarem de funções de outros cells.
_DEFS_CELLS = (
    "04b_scraping.py",
    "06b_docling_setup.py",
    "07b_extract_risks.py",
    "08b_extract_deliveries.py",
    "09b_standardization.py",
    "10b_export.py",
)


def _is_literal_value(node: ast.AST) -> bool:
    """True se o valor de um Assign é um literal puro (sem Call/Name/etc.).

    Mantemos constantes como `_MONTH_MAP = {...}` e `_SCALE_MAX_LEN = 40`, mas
    rejeitamos assignments que executam pipeline (`all_organs = scrape(...)`,
    `eixo_counter = Counter(...)`), que dependem de dados de runtime inexistentes
    no contexto de teste.
    """
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Call, ast.Name, ast.Attribute,
                            ast.comprehension, ast.Subscript)):
            return False
    return True


def _defs_only_source(code: str, filename: str) -> str:
    """Reescreve o source mantendo só imports, defs/classes e constantes literais."""
    tree = ast.parse(code, filename)
    kept = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            kept.append(stmt)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            if stmt.value is not None and _is_literal_value(stmt.value):
                kept.append(stmt)
        # demais nós (Expr/print, If, For, While, With) são descartados
    tree.body = kept
    return compile(tree, filename, "exec")


def _base_namespace() -> dict:
    """Imports que as cells assumem disponíveis no namespace do Jupyter."""
    import re, unicodedata, difflib, os as _os, time, pickle, json, logging
    from typing import Optional, List, Tuple, Dict, Any
    from dataclasses import dataclass, field, asdict
    from datetime import datetime
    import requests, pandas as pd
    from bs4 import BeautifulSoup
    from tqdm.auto import tqdm

    return {
        "re": re, "unicodedata": unicodedata, "difflib": difflib, "os": _os,
        "time": time, "pickle": pickle, "json": json, "logging": logging,
        "Optional": Optional, "List": List, "Tuple": Tuple, "Dict": Dict, "Any": Any,
        "dataclass": dataclass, "field": field, "asdict": asdict,
        "datetime": datetime, "requests": requests, "pd": pd,
        "BeautifulSoup": BeautifulSoup, "tqdm": tqdm,
        # DIRS stub — cells referenciam em paths de checkpoint/output, não nos
        # caminhos cobertos pelos testes.
        "DIRS": {"checkpoints": "/tmp", "output": "/tmp"},
    }


def _load_cells() -> dict:
    """Carrega cells declarativos (full) + cells de pipeline (defs-only)."""
    ns = _base_namespace()

    for fname in _FULL_CELLS:
        path = os.path.join(CELLS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            exec(compile(f.read(), path, "exec"), ns)

    for fname in _DEFS_CELLS:
        path = os.path.join(CELLS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            exec(_defs_only_source(f.read(), path), ns)

    return ns


@pytest.fixture(scope="session")
def cells():
    """Namespace com 02_config + 03_utils + defs dos cells de pipeline.

    Uso típico:
        def test_x(cells):
            assert cells["normalize_text"]("foo") == "foo"
    """
    return _load_cells()
