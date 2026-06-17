# ============================================================
# CÉLULA 1 — Setup & Instalação
# ============================================================
# Detecta ambiente (Google Colab ou local) e instala dependências.
# Execute esta célula primeiro.

import os, sys

# --- Detecção de ambiente ---
try:
    from google.colab import drive
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

# --- Instalação de pacotes (apenas no Colab; local usa requirements.txt) ---
# IMPORTANTE: manter alinhado com requirements.txt na raiz do repo.
if IN_COLAB:
    get_ipython().system('pip install -q pymupdf pypdf beautifulsoup4 requests tqdm pandas')

# --- Google Drive (persistência de PDFs e outputs no Colab) ---
USE_DRIVE = IN_COLAB

if USE_DRIVE:
    drive.mount('/content/drive')
    BASE_DIR = "/content/drive/MyDrive/PTD_Scraper"
else:
    BASE_DIR = os.path.join(os.getcwd(), "ptd_output")

DIRS = {
    "pdfs_diretivo":  os.path.join(BASE_DIR, "pdfs", "diretivo"),
    "pdfs_entregas":  os.path.join(BASE_DIR, "pdfs", "entregas"),
    "output":         os.path.join(BASE_DIR, "output"),
    "checkpoints":    os.path.join(BASE_DIR, "checkpoints"),
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

print(f"Ambiente: {'Google Colab' if IN_COLAB else 'Local'}")
print(f"Diretório base: {BASE_DIR}")
print("Estrutura criada:", list(DIRS.keys()))