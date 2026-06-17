#!/usr/bin/env python3
"""(Re)gera output/variations.csv — catálogo TIPADO das divergências entre o
texto autoral dos PTDs e o vocabulário controlado (o "catálogo").

Por que existe. Cada campo categórico do corpus já guarda quatro colunas:

  <campo>_original     o que o órgão escreveu (texto autoral)
  <campo>_normalizado  o valor canônico do catálogo (para agregação/análise)
  <campo>_method       como o autoral foi encaixado: exact|alias|fuzzy_high|unmatched
  <campo>_score        distância do encaixe (1.0 = idêntico)

Ou seja: o corpus já une os dois fatores — catálogo (p/ análise agregada) e
texto autoral (p/ entender a variação) — no nível da linha. O que faltava era
uma visão consolidada e TIPADA do *atrito* entre os dois. Este derivador a
produz a partir das colunas existentes, sem rodar o pipeline nem acessar a rede
(mesmo padrão de build_manifest.py / build_metadata.py / build_corpus.py).

Não é uma fila de revisão / worklist a "consertar": é um retrato das
características do corpus. Tipos (variation_type):

  alias        sinônimo conhecido mapeado ao catálogo (encaixe limpo)
  aproximado   fuzzy_high — texto autoral próximo, não idêntico (ver score);
               inclui tanto variação autoral real quanto ruído de extração
               (ex.: caractere colado de PDF) que casou de volta
  imputado     campo vazio no original, inferido de outro campo (ex.: eixo via
               cross-validation a partir do produto) — dado AUSENTE, não autoral
  residual     autoral fora do catálogo: produto 'Outros', escala de risco
               não-canônica (method=unmatched) — a divergência mais forte

Linhas method=exact (sem divergência) NÃO entram no catálogo de variações.

Uso:
  python build_variations.py            # (re)grava output/variations.csv
  python build_variations.py --check    # falha se o commitado está defasado (CI)
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import Counter, OrderedDict

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
DELIVERIES = os.path.join(OUTPUT_DIR, "deliveries.csv")
RISKS = os.path.join(OUTPUT_DIR, "risks.csv")
VARIATIONS = os.path.join(OUTPUT_DIR, "variations.csv")

# (entry_type, [campos categóricos]) — cada campo tem _original/_normalizado/
# _method/_score em seu CSV.
DELIVERY_FIELDS = ("produto", "eixo")
RISK_FIELDS = ("probabilidade", "impacto", "tratamento")

COLUMNS = ["orgao_sigla", "entry_type", "field",
           "original", "normalizado", "method", "score", "variation_type"]


def classify(original: str, normalizado: str, method: str) -> str:
    """Tipa a divergência a partir de (original, normalizado, method)."""
    o = (original or "").strip()
    nz = (normalizado or "").strip()
    # 'Outros' é o catch-all do catálogo: caiu nele = residual, não importa como.
    if nz.lower() == "outros":
        return "residual"
    if method == "exact":
        return "exato"
    if method == "alias":
        return "alias"
    if method == "fuzzy_high":
        return "aproximado"
    if method == "unmatched":
        # original vazio + normalizado preenchido = inferido de outro campo.
        return "imputado" if (not o and nz) else "residual"
    # método ausente/desconhecido: trata pelo conteúdo.
    if not o and nz:
        return "imputado"
    return "exato" if o == nz else "residual"


def _read(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _collect(rows: list, entry_type: str, fields: tuple) -> list:
    out = []
    for r in rows:
        sigla = r.get("orgao_sigla", "")
        for field in fields:
            original = r.get(f"{field}_original", "")
            normalizado = r.get(f"{field}_normalizado", r.get(f"{field}_normalizada", ""))
            method = r.get(f"{field}_method", "")
            score = r.get(f"{field}_score", "")
            vtype = classify(original, normalizado, method)
            if vtype == "exato":
                continue
            out.append({
                "orgao_sigla": sigla,
                "entry_type": entry_type,
                "field": field,
                "original": original,
                "normalizado": normalizado,
                "method": method,
                "score": score,
                "variation_type": vtype,
            })
    return out


def build() -> list:
    variations = (_collect(_read(DELIVERIES), "delivery", DELIVERY_FIELDS)
                  + _collect(_read(RISKS), "risk", RISK_FIELDS))
    variations.sort(key=lambda v: (v["entry_type"], v["field"],
                                   v["variation_type"], v["orgao_sigla"],
                                   v["original"]))
    return variations


def _serialize(variations: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(variations)
    return buf.getvalue()


def summary(variations: list) -> "OrderedDict[tuple, int]":
    c = Counter((v["field"], v["variation_type"]) for v in variations)
    return OrderedDict(sorted(c.items()))


def write(variations: list) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(VARIATIONS, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(_serialize(variations))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera output/variations.csv.")
    ap.add_argument("--check", action="store_true",
                    help="Falha se output/variations.csv commitado está defasado.")
    args = ap.parse_args(argv)

    variations = build()
    content = _serialize(variations)
    if args.check:
        if not os.path.exists(VARIATIONS):
            print("variations.csv ausente — rode `python build_variations.py`.")
            return 1
        with open(VARIATIONS, encoding="utf-8-sig") as fh:
            if fh.read() != content:
                print("output/variations.csv defasado — rode `python build_variations.py`.")
                return 1
        print(f"OK — variations.csv em dia ({len(variations)} variações).")
        return 0

    write(variations)
    print(f"variations.csv gravado — {len(variations)} variações:")
    for (field, vtype), n in summary(variations).items():
        print(f"  {field:>14s} · {vtype:<11s} {n:>5d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
