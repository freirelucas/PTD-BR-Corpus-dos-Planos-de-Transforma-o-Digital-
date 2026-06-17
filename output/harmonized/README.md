# Corpus PTD — visão harmonizada

Gerado por [`build_corpus.py`](../../build_corpus.py) a partir de `output/*.csv`.

## O que muda em relação a `output/`

As colunas `*_normalizado` (probabilidade, impacto, tratamento, eixo) contêm
**apenas valores canônicos ou vazio**. Valores não canônicos remanescentes —
artefatos de *column-bleed* e compostos — são removidos da coluna normalizada,
mas:

- o valor cru permanece intacto em `*_original`;
- toda alteração está em [`harmonization_report.json`](harmonization_report.json)
  (órgão, campo, valor original, motivo);
- linhas cujo bleed havia escapado ao `needs_review` são re-sinalizadas.

Nada é perdido — a harmonização é **reversível** via `*_original` + report.

## Linhagem (cadeia de transformações)

```
PTDs (PDF, portal SGD/MGI)
  → scraping de URLs (cell 04b)
  → download + dedup MD5 (05b/05c)
  → extração tabular PyMuPDF (06b/07b/08b)
  → normalização + canonização vs. escalas/produtos SGD (09b)
  → export CSV/JSON (10b) ........................ output/
  → descritores de dados abertos (build_metadata.py) ... output/datapackage.json, metadata/
  → HARMONIZAÇÃO (build_corpus.py) ............... output/harmonized/   ← você está aqui
```

## Contrato estrito

`datapackage.json` aqui usa enums **estritos** nas escalas canônicas — algo que
o datapackage de `output/` não pode fazer, porque os dados crus ainda carregam
valores em revisão. Validar:

```bash
pip install frictionless
frictionless validate output/harmonized/datapackage.json
```
