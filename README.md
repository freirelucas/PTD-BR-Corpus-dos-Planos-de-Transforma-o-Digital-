# PTD-corpus — Planos de Transformação Digital dos órgãos federais

Dados estruturados dos **Planos de Transformação Digital (PTDs)** de **93 órgãos
federais brasileiros** — as **entregas** pactuadas com a SGD/MGI e os **riscos**
de gestão — extraídos automaticamente dos PDFs oficiais publicados no
[gov.br](https://www.gov.br/governodigital/pt-br/estrategias-e-governanca-digital/planos-de-transformacao-digital),
entregues em **CSV, JSON e Excel** com metadados em padrões de dados abertos.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/freirelucas/ptd-br-corpus-dos-planos-de-transforma-o-digital-/blob/main/ptd_scraper.ipynb) &nbsp; [![Baixar corpus em Excel](https://img.shields.io/badge/⬇%20Baixar-Corpus%20em%20Excel%20.xlsx-1D6F42?style=for-the-badge&logo=microsoftexcel&logoColor=white)](https://github.com/freirelucas/PTD-BR-Corpus-dos-Planos-de-Transforma-o-Digital-/raw/main/output/PTD-corpus.xlsx)

> 📊 **Baixe o corpus pronto em Excel:** [`PTD-corpus.xlsx`](https://github.com/freirelucas/PTD-BR-Corpus-dos-Planos-de-Transforma-o-Digital-/raw/main/output/PTD-corpus.xlsx) (516 KB) — abas **entregas · riscos · órgãos · cobertura** + LEIA-ME e dicionário. Abre direto no Excel/LibreOffice em qualquer idioma (acentos e números corretos, sem mexer em delimitador). 93 órgãos, snapshot 2026-06-17.

## Os dados

Para cada órgão, dois documentos do portal viram tabelas:

- **Anexo de Entregas** — produtos pactuados com a SGD/MGI, classificados por eixo da EFGD 2024-2027.
- **Documento Diretivo** — gestão de riscos com probabilidade, impacto e ações de tratamento.

| Métrica | Valor |
|---|---|
| Órgãos signatários | 93 |
| Entregas pactuadas | **4.999** |
| Riscos identificados | **662** |
| Cobertura entregas | 81/93 órgãos (59 próprios + 22 compartilhados) |
| Cobertura riscos | 81/93 órgãos (54 próprios + 27 compartilhados) |
| Diretivos sem tabela de risco extraível (provavelmente escaneados) | 10 |

Sete grupos ministeriais publicam um único PDF para vários órgãos
(MD/MEC/MF/MMA/MT/MIDR/MDA). O pipeline detecta isso por **hash MD5**, registra os
dados uma única vez sob a sigla alfabeticamente menor e marca os demais membros
como `compartilhado` na cobertura.

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `output/deliveries.csv` / `.json` | Entregas pactuadas, concluídas e canceladas |
| `output/risks.csv` / `.json` | Riscos dos Documentos Diretivos |
| `output/organs.csv` | Órgãos e URLs dos PDFs |
| `output/coverage_summary.csv` | Cobertura de extração por órgão (status por documento) |
| `output/pdf_metadata.csv` | Metadados dos PDFs (datas, tamanhos) |
| `output/error_report.csv` | Erros de processamento por órgão e estágio |
| `output/PTD-corpus.xlsx` | Pasta Excel multi-aba pronta para uso (entregas/riscos/órgãos/cobertura + LEIA-ME + dicionário) |
| `output/harmonized/` | Corpus harmonizado: colunas `*_normalizado` estritamente canônicas + datapackage com enums estritos |
| `output/variations.csv` | Catálogo tipado das divergências texto autoral × catálogo (`alias`/`aproximado`/`imputado`/`residual`) |
| `output/datapackage.json` | Descritor [Frictionless Data Package](https://specs.frictionlessdata.io/) (Table Schema dos CSVs) |
| `output/metadata/` | Metadados abertos: schema.org/Dataset, DCAT-AP, SKOS, JSON Schema, PROV-O, payload CKAN |
| `output/manifest.json` · `validation_report.json` | Proveniência: contagens, taxas de canonização e checksums (MD5/SHA-256) de cada artefato |

Cada campo categórico guarda três versões: `_original` (texto do órgão),
`_normalizado` (rótulo canônico do catálogo da SGD) e `_method`/`_score` (como um
foi encaixado no outro). Onde o texto autoral não coube no vocabulário, o atrito é
consolidado e tipado em `output/variations.csv`; a contagem por linha está em
`needs_review` e agregada em `validation_report.json`.

## Como usar os dados

- **Excel / LibreOffice** — baixe [`PTD-corpus.xlsx`](https://github.com/freirelucas/PTD-BR-Corpus-dos-Planos-de-Transforma-o-Digital-/raw/main/output/PTD-corpus.xlsx). Quatro abas + dicionário; abre em qualquer locale.
- **CSV / JSON** — arquivos em `output/`. Exemplo:
  ```python
  import pandas as pd
  entregas = pd.read_csv("output/deliveries.csv")
  riscos   = pd.read_csv("output/risks.csv")
  ```
- **Frictionless** — `output/datapackage.json` descreve o schema de todos os CSVs (validável com `frictionless validate`).
- **Corpus canônico** — `output/harmonized/` traz só as colunas normalizadas, com enums estritos. Para empacotar apenas os CSVs canônicos: `make corpus-zip` gera `corpus_<snapshot>.zip` autocontido (dados + `datapackage.json` + proveniência).

Todo artefato publicado tem checksum em `manifest.json` / `validation_report.json`,
então dá para verificar que os dados não mudaram desde a extração.

## O que o código faz

O pipeline lê o portal do gov.br e produz as tabelas acima, em etapas:

1. **Scraping** — lista de órgãos signatários e URLs dos PDFs.
2. **Download** — baixa os PDFs (Documento Diretivo + Anexo de Entregas), com resume.
3. **Dedup MD5** — detecta PDFs compartilhados entre órgãos de um mesmo grupo ministerial.
4. **Extração** — tabelas via PyMuPDF `find_tables()`, com merge multi-página, tabelas órfãs e consolidação multi-linha.
5. **Padronização** — normaliza o vocabulário (escalas e produtos canônicos da SGD) por fuzzy match, preservando o texto autoral.
6. **Exportação** — CSV/JSON + corpus harmonizado + descritores de dados abertos.
7. **Validação** — `validation_report.json` (contagens, taxas, checksums) e gate de qualidade.

O pipeline tem **checkpoint/resume**: se interrompido, retoma do último checkpoint salvo.

### Rodar

**Google Colab** — clique no badge **Open in Colab** e execute as células em
ordem; o ambiente instala as dependências e persiste os PDFs no Drive
(`MyDrive/PTD_Scraper/`) para reuso entre execuções.

**Local:**

```bash
git clone https://github.com/freirelucas/ptd-br-corpus-dos-planos-de-transforma-o-digital-.git
cd ptd-br-corpus-dos-planos-de-transforma-o-digital-
pip install -r requirements.txt
python run_pipeline.py          # pipeline headless; gate de qualidade no fim
python run_pipeline.py --sync   # idem + regenera output/ e derivados
```

Os PDFs ficam em `ptd_output/pdfs/{diretivo,entregas}/` e os outputs em `ptd_output/output/`.

### Atualizar os dados

Os dados entram na `main` por **pull request**, com os mesmos checks de código
(pytest, consistência do notebook, checksums em dia).

- **Automático** — o workflow [`monthly-refresh.yml`](.github/workflows/monthly-refresh.yml)
  roda `run_pipeline.py --sync` todo dia 2 e abre o PR `data-refresh/AAAA-MM`
  apenas se os dados mudaram (requer o secret `DATA_REFRESH_PAT`).
- **Manual:**
  ```bash
  python run_pipeline.py --sync
  git checkout -b data-refresh/AAAA-MM
  git add output/ && git commit -m "data: refresh output/ — AAAA-MM-DD"
  git push -u origin data-refresh/AAAA-MM   # abrir PR para main
  ```

## Fonte, licença e citação

- **Fonte:** portal gov.br / SGD-MGI. Snapshot `data_execucao=2026-06-17`.
- **Licença:** [Creative Commons Attribution 4.0 (CC BY 4.0)](LICENSE).
- **Como citar:** DIREITO, Denise; SILVA, Lucas; QUEIROZ, Sérgio. *Corpus dos
  Planos de Transformação Digital: extração, padronização e análise dos PTDs de 93
  órgãos federais brasileiros*. Brasília: Ipea, 2026. (Nota Técnica). Metadados de
  citação em [`CITATION.cff`](CITATION.cff).

## Desenvolvimento

A fonte do notebook são os arquivos em `notebook_cells/` (`.py`/`.md`); o
`ptd_scraper.ipynb` é **gerado** deles por `build_notebook.py`, e o CI bloqueia
qualquer divergência. Os derivados de `output/` não exigem rodar o pipeline:

```bash
python build_notebook.py   # reconstrói o notebook após editar as células
make manifest metadata corpus variations coverage xlsx   # regenera os derivados
```

Cada derivador tem modo `--check` (rodado no `pytest`) que falha se o artefato
commitado está defasado. Linhagem dos metadados em [`METADATA.md`](METADATA.md).
