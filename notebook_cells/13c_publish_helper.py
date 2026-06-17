# ============================================================
# CÉLULA 13c — Empacota output/ para publicação no main
# ============================================================
# Após executar o pipeline, gera um único `output_TIMESTAMP.zip` em
# DIRS["output"]/.. com o conteúdo COMPLETO de output/ (recursivo,
# incluindo quaisquer extras presentes).
#
# Por que isso existe:
# - Colab executa o pipeline e escreve em MyDrive/PTD_Scraper/output/.
# - O caminho CANÔNICO de publicação é o CI (monthly-refresh.yml), que roda
#   o mesmo pipeline e abre PR revisado. Este bundle é o FALLBACK para runs
#   Colab (sem ambiente local, ou gov.br bloqueando IPs de runner) — e
#   também o artefato de transparência: o run inteiro num zip auditável.
# - Dados entram na main por PR, nunca por push direto: commit parcial ou
#   inconsistente é bloqueado pelo CI (notebook-consistency.yml + pytest).
# ============================================================

import os
import zipfile
from datetime import datetime

out_dir = DIRS["output"]
zip_name = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
zip_path = os.path.join(os.path.dirname(out_dir), zip_name)

# Núcleo obrigatório: o que as CÉLULAS sempre geram no top-level de output/.
# Fora da lista (derivados pós-pipeline, gerados por build_*.py — ver README):
#   - manifest.json (build_manifest.py), coverage_summary.csv (build_coverage.py)
#   - datapackage.json, metadata/, harmonized/, variations.csv, PTD-corpus.xlsx
#     (build_metadata / build_corpus / build_variations / build_xlsx)
EXPECTED_OUTPUTS = [
    "validation_report.json",
    "pdf_metadata.csv",
    "risks.csv",
    "risks.json",
    "deliveries.csv",
    "deliveries.json",
    "organs.csv",
    "error_report.csv",
    "vocabulary_mapping.csv",
]

_missing = [f for f in EXPECTED_OUTPUTS
            if not os.path.exists(os.path.join(out_dir, f))]
if _missing:
    raise RuntimeError(
        f"Pipeline incompleto — {len(_missing)} artefato(s) essenciais "
        f"ausentes em output/: {', '.join(_missing)}. Execute as células "
        f"anteriores (04b→13b) antes de publicar.")

# Zip recursivo de TODO o output/. Arcnames sempre sob 'output/' por
# construção (relpath ancorado em out_dir) — sem path traversal.
_entries = []
for _root, _dirs, _files in os.walk(out_dir):
    _dirs.sort()
    for _fname in sorted(_files):
        _fpath = os.path.join(_root, _fname)
        _arc = os.path.join("output", os.path.relpath(_fpath, out_dir))
        _entries.append((_fpath, _arc))

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for _fpath, _arc in _entries:
        zf.write(_fpath, arcname=_arc)

print("=" * 60)
print("BUNDLE DE PUBLICAÇÃO")
print("=" * 60)
print(f"  Arquivo: {zip_path}")
print(f"  Conteúdo: {len(_entries)} arquivos (output/ completo)")
for _fpath, _arc in _entries:
    print(f"    {_arc:<48s} {os.path.getsize(_fpath) / 1024:>8.1f} KB")
print("\nPara publicar (fallback — o caminho canônico é o CI mensal, que abre PR sozinho):")
print("  1. Baixe o zip pelo painel de Files do Colab (ou aguarde o download automático)")
print("  2. No seu clone local do repo PTD:")
print(f"       unzip -o {zip_name} && \\")
print("       python build_coverage.py && python build_manifest.py && python build_metadata.py && \\")
print("       python build_corpus.py && python build_variations.py && python build_xlsx.py && \\")
print("       git checkout -b data-refresh/$(date +%Y-%m) && \\")
print("       git add output/ && \\")
print("       git commit -m 'data: refresh output/ — Colab run' && \\")
print("       git push -u origin data-refresh/$(date +%Y-%m)")
print("  3. Abra o PR para main — o CI valida o refresh (testes, checksums,")
print("     derivados); Pages reflete ~1 min após o merge")
print("=" * 60)

# Em ambiente Colab, oferece o download programático.
try:
    from google.colab import files as _gc_files
    print("\nIniciando download automático do bundle…")
    _gc_files.download(zip_path)
except ImportError:
    pass  # headless/local — o zip fica em disco
