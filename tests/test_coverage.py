"""Testes do derivador build_coverage.py (cobertura de extração por órgão).

Cobre a regra-chave de status (compartilhado exige um 'dono' com dados no grupo
que divide a URL; senão é sem_dados / no_risk_table), a distribuição do snapshot
e a paridade do coverage_summary.csv commitado (mesmo guard --check da CI)."""
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


def test_build_reproduz_distribuicao_do_snapshot():
    rows = bc.build()
    assert len(rows) == 91
    se = Counter(r["status_entregas"] for r in rows)
    sr = Counter(r["status_riscos"] for r in rows)
    assert se == {"ok": 57, "compartilhado": 22, "sem_dados": 12}
    assert sr == {"ok": 51, "compartilhado": 25, "no_risk_table": 10, "sem_pdf": 5}
    assert rows == sorted(rows, key=lambda r: r["sigla"])   # ordenado por sigla


def test_serialize_estavel_e_header():
    once = bc._serialize(bc.build())
    assert once == bc._serialize(bc.build())
    assert once.startswith("sigla,grupo,pdf_diretivo,pdf_entregas,")


def test_coverage_commitado_em_dia():
    """O coverage_summary.csv do repo bate com build_coverage (guard da CI)."""
    assert bc.main(["--check"]) == 0
