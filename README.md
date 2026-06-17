# PTD-corpus — Corpus dos Planos de Transformação Digital

Pipeline para coleta, extração, padronização e exportação do corpus dos
**Planos de Transformação Digital (PTDs)** dos órgãos federais brasileiros,
publicados no portal [gov.br](https://www.gov.br/governodigital/pt-br/estrategias-e-governanca-digital/planos-de-transformacao-digital).

> **Spin-off sem analytics.** Este repositório é a fatia de *engenharia do
> corpus* do projeto PTD: scraping → extração → padronização → exportação →
> harmonização → metadados de dados abertos. **Sem** a camada de análise
> (estatísticas, figuras, dashboard interativo, insumos da nota técnica). O
> porquê, o que foi mantido/removido e como continuar estão em
> [`HANDOUT.md`](HANDOUT.md).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/freirelucas/ptd-br-corpus-dos-planos-de-transforma-o-digital-/blob/main/ptd_scraper.ipynb)

## O que o corpus contém

91 órgãos federais signatários (decreto 12.198/2024). Para cada órgão são
extraídos dois documentos do portal:

- **Anexo de Entregas** — tabela de produtos pactuados com a SGD/MGI, classificados por eixo da EFGD 2024-2027
- **Documento Diretivo** — tabela de gestão de riscos com probabilidade, impacto e ações de tratamento

Resultado consolidado (snapshot herdado do projeto PTD, `data_execucao=2026-05-12`):

| Métrica | Valor |
|---|---|
| Órgãos signatários | 91 |
| Entregas pactuadas | **4.574** |
| Riscos identificados | **619** |
| Cobertura entregas | 79/91 órgãos (57 próprios + 22 compartilhados) |
| Cobertura riscos | 76/91 órgãos (51 próprios + 25 compartilhados) |
| PDFs com falha de extração (provavelmente escaneados) | 10 |

Sete grupos ministeriais publicam um único PDF para múltiplos órgãos
(MD/MEC/MF/MMA/MT/MIDR/MDA). O pipeline detecta isso por **hash MD5** e registra
os dados uma única vez sob a sigla alfabeticamente menor; os demais membros são
marcados como `compartilhado` na cobertura.

## Saídas

| Arquivo | Descrição |
|---------|-----------|
| `output/deliveries.csv` / `.json` | Entregas pactuadas, concluídas e canceladas |
| `output/risks.csv` / `.json` | Riscos identificados nos Documentos Diretivos |
| `output/organs.csv` | Lista de órgãos com URLs dos PDFs |
| `output/coverage_summary.csv` | Cobertura de extração por órgão (status por documento), gerada por `build_coverage.py` |
| `output/error_report.csv` | Erros de processamento por órgão e estágio |
| `output/pdf_metadata.csv` | Metadados dos PDFs (datas, tamanhos) |
| `output/validation_report.json` | Contagens, taxas de canonização e checksums MD5 dos artefatos |
| `output/manifest.json` | Manifesto da execução: commit do pipeline, contagens de PDFs e hash SHA-256 dos artefatos exportados |
| `output/datapackage.json` | Descritor [Frictionless Data Package](https://specs.frictionlessdata.io/) (Table Schema dos CSVs) |
| `output/metadata/` | Metadados em padrões abertos: schema.org/Dataset, DCAT-AP, SKOS, JSON Schema, PROV-O, payload CKAN |
| `output/harmonized/` | Corpus harmonizado: colunas `*_normalizado` estritamente canônicas + datapackage com enums estritos + relatório auditável |
| `output/variations.csv` | Catálogo **tipado** das divergências texto autoral × catálogo (`alias`/`aproximado`/`imputado`/`residual`), gerado por `build_variations.py` |
| `output/PTD-corpus.xlsx` | Pasta de trabalho Excel multi-aba (entregas/riscos/órgãos/cobertura + LEIA-ME + dicionário), pronta para uso no Excel/LibreOffice em qualquer locale, gerada por `build_xlsx.py` |

Os descritores de dados abertos são gerados por [`build_metadata.py`](build_metadata.py);
o `manifest.json` por [`build_manifest.py`](build_manifest.py); a versão
harmonizada do corpus por [`build_corpus.py`](build_corpus.py); a cobertura por
órgão por [`build_coverage.py`](build_coverage.py); a pasta Excel pronta para
uso por [`build_xlsx.py`](build_xlsx.py). Documentação e
linhagem em [`METADATA.md`](METADATA.md).

Cada campo categórico guarda `_original` (texto autoral) + `_normalizado`
(catálogo, p/ analytics) + `_method`/`_score` (como o autoral foi encaixado). O
atrito entre os dois — onde o texto dos órgãos não coube no vocabulário — é
consolidado e **tipado** em `output/variations.csv` (`build_variations.py`); a
contagem por linha está nas colunas `needs_review` e agregada em
`validation_report.json`.

Para baixar **só o corpus** (CSVs canônicos), `make corpus-zip` empacota
`corpus_<snapshot>.zip` — pacote Frictionless autocontido:
`deliveries`/`risks`/`organs` canônicos + `datapackage.json` +
`harmonization_report.json` + `manifest.json` (proveniência).

## Como usar

**Princípio do projeto — transparência e reprodutibilidade científicas.**
Há uma única fonte de código (`notebook_cells/*.py`); o notebook Colab é
**gerado** dela por `build_notebook.py`, e o CI bloqueia qualquer divergência
(`notebook-consistency.yml`). Todo artefato publicado é derivável da fonte: os
CSVs pelo pipeline, os descritores por `build_manifest.py` /
`build_metadata.py` / `build_corpus.py`, e o `validation_report.json` registra
checksums de tudo.

### Google Colab

Clique no badge **Open in Colab** acima e execute as células sequencialmente. O
ambiente detecta o Colab automaticamente e instala as dependências. Os PDFs são
persistidos no Google Drive (`MyDrive/PTD_Scraper/`) para reutilização entre
execuções.

### Execução local

```bash
git clone https://github.com/freirelucas/ptd-br-corpus-dos-planos-de-transforma-o-digital-.git
cd REPO
pip install -r requirements.txt
jupyter notebook ptd_scraper.ipynb
```

Para rodar o pipeline inteiro sem Jupyter (headless, mesmo fluxo do workflow mensal):

```bash
python run_pipeline.py          # executa as células em sequência; gate de qualidade no fim
python run_pipeline.py --sync   # idem + substitui output/ do repo e regenera derivados
```

Os PDFs ficam em `ptd_output/pdfs/{diretivo,entregas}/` e os outputs em `ptd_output/output/`.

### Atualizar os dados

Dados entram na `main` por **pull request — nunca por push direto**. O PR de
dados passa pelos mesmos checks que qualquer mudança de código (pytest,
consistência do notebook, checksums em dia).

**Via canônica — CI mensal.** O workflow
[`monthly-refresh.yml`](.github/workflows/monthly-refresh.yml) roda
`run_pipeline.py --sync` todo dia 2 do mês num runner do GitHub e abre o PR
`data-refresh/YYYY-MM` com `output/` — apenas se os CSVs sem timestamp mudaram
de fato. Configure o secret `DATA_REFRESH_PAT` (fine-grained PAT com Contents +
Pull requests RW) para os checks rodarem automaticamente no PR.

**Via local (headless)** — mesma execução, na sua máquina:

```bash
python run_pipeline.py --sync               # pipeline + output/ prontos
git checkout -b data-refresh/AAAA-MM
git add output/
git commit -m "data: refresh output/ — run AAAA-MM-DD"
git push -u origin data-refresh/AAAA-MM     # e abrir PR para main
```

## Pipeline

O notebook executa as etapas sequenciais de engenharia do corpus:

1. **Setup** — Detecta ambiente (Colab/local), instala dependências
2. **Configuração** — Vocabulários canônicos, ORGAN_GROUPS, dataclasses
3. **Utilitários** — Rede, normalização, fuzzy matching
4. **Scraping** — Coleta lista de órgãos e URLs dos PDFs no gov.br
5. **Download** — Baixa PDFs com resume automático (skip se já existe)
6. **Dedup MD5** — Identifica PDFs compartilhados entre órgãos do mesmo grupo ministerial e elege um "owner" alfabético
7. **Extração** — Configura PyMuPDF `find_tables()` e detectores auxiliares
8. **Riscos** — Extrai tabelas de risco com merge multi-página, header-as-data, tabelas órfãs e consolidação multi-linha
9. **Entregas** — Extrai tabelas de entregas com mapeamento posicional para multi-página
10. **Padronização** — Normaliza vocabulário com fuzzy match contra produtos canônicos + legados
11. **Exportação** — Gera CSVs e JSONs estruturados
12. **Validação** — `validation_report.json` (contagens, taxas, checksums) + bundle de publicação

O pipeline tem **checkpoint/resume**: se interrompido, retoma do último checkpoint salvo.

## Estrutura do projeto

```
PTD-corpus/
  ptd_scraper.ipynb            # Notebook principal (gerado a partir de notebook_cells/)
  build_notebook.py            # Monta o notebook a partir das células
  build_manifest.py            # (re)gera output/manifest.json (derivador standalone)
  build_metadata.py            # (re)gera descritores de dados abertos
  build_corpus.py              # (re)gera o corpus harmonizado
  build_variations.py          # (re)gera variations.csv (catálogo tipado de divergências)
  build_coverage.py            # (re)gera coverage_summary.csv (cobertura por órgão)
  build_xlsx.py                # (re)gera PTD-corpus.xlsx (pasta Excel pronta p/ uso)
  run_pipeline.py              # Executa o pipeline headless (CI/local)
  notebook_cells/              # Células individuais (.py e .md)
  output/                      # Dados extraídos e descritores
  tests/                       # pytest (helpers puros das células + derivadores)
  HANDOUT.md                   # Origem do spin-off, o que foi mantido/removido, próximos passos
  DECISIONS.md                 # Histórico de decisões técnicas e bugs corrigidos
  METADATA.md                  # Linhagem dos metadados de dados abertos
  requirements.txt             # Dependências Python
```

## Desenvolvimento

As células do notebook ficam em `notebook_cells/` como arquivos `.py` e `.md`
individuais. Após editar, reconstrua o notebook:

```bash
python build_notebook.py        # ou: make build
```

O CI (`.github/workflows/notebook-consistency.yml`) valida em todo push/PR que
`ptd_scraper.ipynb` reflete `notebook_cells/` e bloqueia merge em caso de drift.

### Metadados e corpus harmonizado

Os derivados de `output/` não exigem rodar o pipeline:

```bash
make manifest   # output/manifest.json                         (build_manifest.py)
make metadata   # output/datapackage.json + output/metadata/   (build_metadata.py)
make corpus     # output/harmonized/                            (build_corpus.py)
make variations # output/variations.csv                        (build_variations.py)
make coverage   # output/coverage_summary.csv                  (build_coverage.py)
make xlsx       # output/PTD-corpus.xlsx                        (build_xlsx.py)
```

Todos têm modo `--check` (usado no `pytest`) que falha se os artefatos
commitados estão defasados. Detalhes em [`METADATA.md`](METADATA.md).

## Citação

DIREITO, Denise; SILVA, Lucas; QUEIROZ, Sérgio. *Corpus dos Planos de Transformação Digital: extração, padronização e análise dos PTDs de 91 órgãos federais brasileiros*. Brasília: Ipea, 2026. (Nota Técnica).

## Licença

Este projeto está licenciado sob a [Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE).
