"""Testes do derivador build_coverage.py (cobertura de extração por órgão).

Cobre a regra-chave de status (compartilhado exige um 'dono' com dados no grupo
que divide a URL; senão é sem_dados / no_risk_table), invariantes que valem em
QUALQUER snapshot (sem fixar contagens — o corpus cresce) e a paridade do
coverage_summary.csv commitado (mesmo guard --check da CI)."""
import csv
import os
from collections import Counter

import build_coverage as bc


def test_share_index_exige_dono_com_dados():
    organs = [{"sigla": "A", "url_entregas": "u1"},
              {"sigla": "B", "url_entregas": "u1"},
              {"sigla": "C", "url_entregas": "u2"},
              {"sigla": "D", "url_entregas": "u2"}]
    n_share, has_owner = bc._share_index(organs, "url_entregas", Counter({"A": 3}))
    assert n_share == {"u1": 2, "u2": 2}
    # u1: A tem dados -> há dono; u2: ninguém do par tem dados -> não há dono
    assert has_owner == {"u1": True, "u2": False}


def test_build_invariantes():
    """Invariantes independentes de contagem — valem com 91, 93, 100… órgãos."""
    rows = bc.build()
    with open(os.path.join(bc.OUTPUT_DIR, "organs.csv"), encoding="utf-8-sig") as fh:
        n_orgaos = sum(1 for _ in csv.DictReader(fh))
    assert len(rows) == n_orgaos                     # uma linha por órgão
    assert rows == sorted(rows, key=lambda r: r["sigla"])
    assert all(r["status_entregas"] in {"ok", "compartilhado", "sem_dados"}
               for r in rows)
    assert all(r["status_riscos"] in {"ok", "compartilhado", "no_risk_table",
                                      "sem_pdf"} for r in rows)
    # contagens batem com o groupby de deliveries / risks
    n_del = Counter(r["orgao_sigla"] for r in bc._read(bc.DELIVERIES))
    n_risk = Counter(r["orgao_sigla"] for r in bc._read(bc.RISKS))
    for r in rows:
        assert int(r["entregas_extraidas"]) == n_del.get(r["sigla"], 0)
        assert int(r["riscos_extraidos"]) == n_risk.get(r["sigla"], 0)
        # sem PDF diretivo => sem_pdf; com dados => ok (coerência status×contagem)
        if r["pdf_diretivo"] == "nao":
            assert r["status_riscos"] == "sem_pdf"
        if int(r["entregas_extraidas"]) > 0:
            assert r["status_entregas"] == "ok"


def test_serialize_estavel_e_header():
    once = bc._serialize(bc.build())
    assert once == bc._serialize(bc.build())
    assert once.startswith("sigla,grupo,pdf_diretivo,pdf_entregas,")


def test_coverage_commitado_em_dia():
    """O coverage_summary.csv do repo bate com build_coverage (guard da CI)."""
    assert bc.main(["--check"]) == 0
