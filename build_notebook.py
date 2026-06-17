#!/usr/bin/env python3
"""Assembles notebook_cells/*.py and *.md into ptd_scraper.ipynb."""
import json, glob, re, os

def make_cell(cell_type, source_text):
    lines = source_text.split('\n')
    src = [l + '\n' for l in lines[:-1]] + [lines[-1]] if lines else []
    cell = {"cell_type": cell_type, "metadata": {}, "source": src}
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell

cells_dir = os.path.join(os.path.dirname(__file__), "notebook_cells")
files = sorted(glob.glob(os.path.join(cells_dir, "*")))

cells = []
for fpath in files:
    if not os.path.isfile(fpath):
        continue   # ignora diretórios como __pycache__
    fname = os.path.basename(fpath)
    # Pattern: NN_name.py  or  NN_name.md  or NNx_name.py (e.g. 01a_)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read().rstrip('\n')
    if fname.endswith(".md"):
        cells.append(make_cell("markdown", content))
    elif fname.endswith(".py"):
        cells.append(make_cell("code", content))

notebook = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": [], "name": "PTD Scraper Gov.br", "toc_visible": True},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"}
    },
    "cells": cells
}

out_path = os.path.join(os.path.dirname(__file__), "ptd_scraper.ipynb")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"Notebook criado com {len(cells)} células em {out_path}")
