# ============================================================
# CÉLULA 5d — Metadados dos PDFs (datas, tamanho)
# ============================================================
# Após o dedup (5c), cada PDF único sobrevive sob seu "owner" (a sigla
# alfabeticamente menor; os não-owners ficam com pdf_path=None). Esta célula
# registra, por PDF presente no disco, as datas de criação/modificação lidas do
# próprio arquivo (via PyMuPDF) e o tamanho em KB -> output/pdf_metadata.csv.
#
# Consumido por build_manifest.py (contagens de PDF) e exigido pelo bundle de
# publicação (13c). Uma linha por PDF único (tantas quantas URLs distintas).
import fitz


def _parse_pdf_date(raw: str) -> str:
    """Data de PDF (ex.: "D:20260429120000-03'00'") -> "YYYY-MM-DD". "" se ausente."""
    if not raw:
        return ""
    s = raw[2:] if raw.startswith("D:") else raw
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s[:8].isdigit() else ""


def _pdf_file_meta(path: str) -> dict:
    """Datas (lidas do PDF) + tamanho_kb (do disco). Datas vazias se ilegíveis."""
    cre = mod = ""
    try:
        with fitz.open(path) as doc:
            meta = doc.metadata or {}
        cre = _parse_pdf_date(meta.get("creationDate", ""))
        mod = _parse_pdf_date(meta.get("modDate", ""))
    except Exception:
        pass   # PDF sem metadados / corrompido: datas vazias, tamanho ainda conta
    return {"data_criacao_pdf": cre, "data_modificacao_pdf": mod,
            "tamanho_kb": round(os.path.getsize(path) / 1024)}


def build_pdf_metadata(organs: "List[OrganInfo]") -> "List[dict]":
    """Uma linha por PDF presente no disco (owner pós-dedup), ord. por (sigla, tipo)."""
    rows = []
    for o in organs:
        for tipo, path in (("diretivo", o.pdf_path_diretivo),
                           ("entregas", o.pdf_path_entregas)):
            if path and os.path.exists(path):
                rows.append({"sigla": o.sigla, "tipo": tipo,
                             **_pdf_file_meta(path), "vigencia": ""})
    rows.sort(key=lambda r: (r["sigla"], r["tipo"]))
    return rows


# ---- Execução ----
PDF_METADATA_COLS = ["sigla", "tipo", "data_criacao_pdf", "data_modificacao_pdf",
                     "vigencia", "tamanho_kb"]
if all_organs:
    _pdf_meta_rows = build_pdf_metadata(all_organs)
    _pm_path = os.path.join(DIRS["output"], "pdf_metadata.csv")
    pd.DataFrame(_pdf_meta_rows, columns=PDF_METADATA_COLS).to_csv(
        _pm_path, index=False, encoding="utf-8-sig")
    print(f"pdf_metadata.csv gravado — {len(_pdf_meta_rows)} PDFs únicos.")
else:
    print("Nenhum órgão — pdf_metadata.csv não gerado.")
