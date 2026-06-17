# ============================================================
# CÉLULA 13 — Exporta validation_report.json
# ============================================================
import json, hashlib
from collections import Counter
from datetime import datetime, timezone

def _md5_file(path: str) -> str:
    if not os.path.exists(path):
        return ""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _topn(values, n=20):
    return [{"value": v, "count": c} for v, c in Counter(values).most_common(n)]

# --- Contagens básicas ---
n_entregas = len(all_deliveries) if all_deliveries else 0
n_riscos = len(all_risks) if all_risks else 0
n_orgaos = len(all_organs) if all_organs else 0

# --- Taxas de canonização e residuais ---
prob_ok = imp_ok = trat_ok = 0
nc_prob_vals, nc_imp_vals, nc_trat_vals = [], [], []
if all_risks:
    for r in all_risks:
        if r.probabilidade_normalizada in PROBABILIDADE_SCALE:
            prob_ok += 1
        elif r.probabilidade_original:
            nc_prob_vals.append(r.probabilidade_original)
        if r.impacto_normalizado in IMPACTO_SCALE:
            imp_ok += 1
        elif r.impacto_original:
            nc_imp_vals.append(r.impacto_original)
        trat_canonical = (r.tratamento_normalizado and
                          all(t.strip() in TRATAMENTO_OPTIONS
                              for t in r.tratamento_normalizado.split(";") if t.strip()))
        if trat_canonical:
            trat_ok += 1
        elif r.tratamento_original:
            nc_trat_vals.append(r.tratamento_original)

prob_rate = prob_ok / n_riscos if n_riscos else 0.0
imp_rate = imp_ok / n_riscos if n_riscos else 0.0
trat_rate = trat_ok / n_riscos if n_riscos else 0.0

# --- Threshold checks ---
thresholds = {
    "max_entregas": {
        "limit": QUALITY_THRESHOLDS["max_entregas"],
        "actual": n_entregas,
        "passed": n_entregas <= QUALITY_THRESHOLDS["max_entregas"],
    },
    "max_riscos": {
        "limit": QUALITY_THRESHOLDS["max_riscos"],
        "actual": n_riscos,
        "passed": n_riscos <= QUALITY_THRESHOLDS["max_riscos"],
    },
    "min_prob_canonica_ratio": {
        "limit": QUALITY_THRESHOLDS["min_prob_canonica_ratio"],
        "actual": round(prob_rate, 4),
        "passed": prob_rate >= QUALITY_THRESHOLDS["min_prob_canonica_ratio"],
    },
    "min_imp_canonica_ratio": {
        "limit": QUALITY_THRESHOLDS["min_imp_canonica_ratio"],
        "actual": round(imp_rate, 4),
        "passed": imp_rate >= QUALITY_THRESHOLDS["min_imp_canonica_ratio"],
    },
    "min_trat_canonica_ratio": {
        "limit": QUALITY_THRESHOLDS["min_trat_canonica_ratio"],
        "actual": round(trat_rate, 4),
        "passed": trat_rate >= QUALITY_THRESHOLDS["min_trat_canonica_ratio"],
    },
}

# --- Needs-review ---
n_review_del = sum(1 for d in all_deliveries if d.needs_review) if all_deliveries else 0
n_review_risk = sum(1 for r in all_risks if r.needs_review) if all_risks else 0

# --- Distribuições normalizadas (para detectar shifts) ---
dist_prob = Counter(r.probabilidade_normalizada for r in all_risks) if all_risks else {}
dist_imp = Counter(r.impacto_normalizado for r in all_risks) if all_risks else {}
dist_trat = Counter(r.tratamento_normalizado for r in all_risks) if all_risks else {}

# --- Checksums dos outputs ---
out = DIRS["output"]
checksums = {
    name: _md5_file(os.path.join(out, name))
    for name in ["risks.csv", "deliveries.csv", "organs.csv",
                 "risks.json", "deliveries.json", "error_report.csv"]
}

# --- Pipeline fingerprints (um por checkpoint, gravados por save_checkpoint) ---
fingerprints = {}
ckpt_dir = DIRS.get("checkpoints", "")
if ckpt_dir and os.path.isdir(ckpt_dir):
    for fname in sorted(os.listdir(ckpt_dir)):
        if fname.endswith(".fingerprint"):
            try:
                with open(os.path.join(ckpt_dir, fname), encoding="utf-8") as f:
                    fingerprints[fname[:-len(".fingerprint")]] = f.read().strip()
            except Exception:
                pass

report = {
    "schema_version": 1,
    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "counts": {
        "orgaos": n_orgaos,
        "entregas": n_entregas,
        "riscos": n_riscos,
        "errors": len(all_errors) if all_errors else 0,
        "needs_review_entregas": n_review_del,
        "needs_review_riscos": n_review_risk,
    },
    "canonization": {
        "probabilidade": {"ok": prob_ok, "total": n_riscos, "rate": round(prob_rate, 4)},
        "impacto":       {"ok": imp_ok,  "total": n_riscos, "rate": round(imp_rate, 4)},
        "tratamento":    {"ok": trat_ok, "total": n_riscos, "rate": round(trat_rate, 4)},
    },
    "non_canonical_top20": {
        "probabilidade": _topn(nc_prob_vals),
        "impacto":       _topn(nc_imp_vals),
        "tratamento":    _topn(nc_trat_vals),
    },
    "distributions_normalized": {
        "probabilidade": dict(dist_prob),
        "impacto":       dict(dist_imp),
        "tratamento":    dict(dist_trat),
    },
    "thresholds": thresholds,
    "all_thresholds_passed": all(t["passed"] for t in thresholds.values()),
    "output_checksums_md5": checksums,
    "checkpoint_fingerprints": fingerprints,
}

report_path = os.path.join(out, "validation_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("=" * 60)
print("RELATÓRIO DE VALIDAÇÃO")
print("=" * 60)
print(f"  Arquivo: {report_path}")
print(f"  Entregas: {n_entregas}  |  Riscos: {n_riscos}  |  Órgãos: {n_orgaos}")
print(f"  Canonização: prob={prob_rate:.1%} imp={imp_rate:.1%} trat={trat_rate:.1%}")
print(f"  Residuais: prob={len(set(nc_prob_vals))} imp={len(set(nc_imp_vals))} trat={len(set(nc_trat_vals))} valores únicos")
print(f"  Thresholds: {'✓ todos passaram' if report['all_thresholds_passed'] else '✗ FALHA — ver thresholds[*].passed'}")
print(f"  MD5 risks.csv: {checksums.get('risks.csv', '')[:12]}...")
print("=" * 60)
print("Baixe validation_report.json para auditoria local.")
