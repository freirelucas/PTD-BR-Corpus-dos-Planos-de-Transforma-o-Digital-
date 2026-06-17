# HANDOUT — PTD-corpus (spin-off sem analytics)

Este pacote é a **semente de um novo repositório**: a fatia de *engenharia do
corpus* do projeto PTD, sem a camada de analytics. Foi gerado
automaticamente a partir do repositório PTD original por
`tools/make_spinoff.py` — a proveniência exata (commit-fonte e data) está em
`SPINOFF_PROVENANCE.txt`, na raiz deste pacote.

Leia este documento inteiro antes de começar. Ele cobre: por que o spin-off
existe, o que foi mantido e removido, a única mudança de arquitetura não-trivial,
como rodar e validar, o setup do novo repositório e o que ainda falta validar.

---

## 1. Por que separar

O PTD tem duas camadas com maturidades diferentes:

- **Corpus (sólido):** scraping, download, dedup MD5, extração de tabelas,
  padronização de vocabulário, exportação CSV/JSON, harmonização e metadados de
  dados abertos. Os totais e a distribuição de entregas eram reprodutíveis e
  estáveis entre runs.
- **Analytics (instável):** estatísticas, figuras, dashboard interativo e os
  insumos numéricos da nota técnica. O balanço de consistência do projeto
  mostrou que era exatamente aqui que os números divergiam entre execuções
  (taxas de canonização de risco, taxa de padronização, zona crítica,
  severidade), em boa parte porque a "fonte autoritativa" da NT não tinha
  gerador versionado.

Este spin-off isola a camada sólida num repositório próprio, mais leve e fácil
de manter, sem `index.html`, figuras, `data.js` nem os insumos da NT.

> "Analytics" aqui é **análise de dados** (estatísticas/visualização), não
> *web analytics*. O dashboard original não tinha nenhum rastreador (Google
> Analytics, Plausible, etc.).

---

## 2. O que foi mantido e o que saiu

### Mantido (engenharia do corpus)

| Componente | Arquivos |
|---|---|
| Pipeline de coleta/extração/padronização | `notebook_cells/00`→`10*` |
| Validação + bundle de publicação | `notebook_cells/13*` |
| Notebook gerado + builder | `ptd_scraper.ipynb`, `build_notebook.py` |
| Pipeline headless | `run_pipeline.py` |
| Manifesto (proveniência) | **`build_manifest.py`** (novo — ver §3) |
| Catálogo tipado de variações | **`build_variations.py`** (novo — ver §3.5) |
| Descritores de dados abertos | `build_metadata.py` (DCAT/PROV/CKAN/SKOS/schema.org/JSON Schema) |
| Corpus harmonizado | `build_corpus.py` |
| Dados do corpus | `output/*.csv|json`, `output/harmonized/`, `output/metadata/` |
| Testes | `tests/` (helpers puros das células + derivadores) |
| CI | `tests.yml`, `notebook-consistency.yml`, `monthly-refresh.yml` |

### Removido (analytics)

| O que | Onde estava |
|---|---|
| Estatísticas + figuras | `notebook_cells/11a`, `11b_statistics.py`, `output/figures/`, `output/statistics_summary.json` |
| Dashboard interativo | `index.html`, `notebook_cells/11ca`/`11cb_dashboard_data.py`, `output/data.js` |
| Resumo de revisão p/ dashboard | `notebook_cells/11cc`/`11cd_review_queue.py`, `output/review_data.json` |
| Insumos da nota técnica | `notebook_cells/11e_nt_insumos.py`, `output/nota_tecnica_insumos.md` |
| Fila de revisão + curadoria | `notebook_cells/12*_iteration`, exportação de `review_queue.csv` no `10b`, `output/review_queue.csv`, `tests/test_iteration.py` |
| Testes de analytics/curadoria | `tests/test_nt_insumos.py`, `tests/test_parse_year_month.py`, `tests/test_iteration.py` |
| Documentos da NT/auditoria | `BALANCO_CONSISTENCIA.md`, `NOTA_TECNICA.md`, `NT_CORRECOES.md` |
| Dependências de figuras | `matplotlib`, `seaborn` (de `requirements.txt`) |

> **A fila de revisão (worklist) saiu, mas o sinal foi preservado e melhorado.**
> A `review_queue.csv` era um dump binário de `needs_review` que misturava
> fenômenos distintos. Em vez dela, o corpus mantém — por linha — as colunas
> `<campo>_original` / `_normalizado` / `_method` / `_score` (o atrito entre
> texto autoral e catálogo, no detalhe) e ganha **`build_variations.py`**, que
> deriva `output/variations.csv`: um catálogo TIPADO das divergências
> (`alias` / `aproximado` / `imputado` / `residual`). Ver §3.5. Saíram só a
> célula de curadoria `12*` e o resumo que alimentava o dashboard
> (`11cd`/`review_data.json`).

---

## 3. A única mudança de arquitetura não-trivial: `build_manifest.py`

99% do corte foi mecânico: as células de analytics (`11*`) rodam **depois** das
do corpus (`00`→`10`) e compartilham só o namespace do notebook; as células do
corpus nunca leem variáveis das de analytics. Remover as de analytics não pode
quebrar a extração.

A exceção é o **`manifest.json`** — artefato de *proveniência do corpus* que
`build_metadata.py` consome (DCAT/PROV/CKAN usam `data_execucao`,
`pipeline_commit` e `outputs[].sha256`). No projeto original ele era escrito
**dentro da célula do dashboard** (`11cb`), entrelaçado com as estatísticas.
Remover o dashboard deixaria o pipeline sem manifesto.

Solução: extrair um derivador **standalone** `build_manifest.py`, no mesmo
padrão de `build_metadata.py` / `build_corpus.py` — lê `output/` + git, sem rede,
com `--check` para o CI. Em comparação ao original:

- `outputs[]` é recomputado de `output/` (exclui `data.js`, `manifest.json` e
  `datapackage.json`) → no spin-off fica limpo automaticamente;
- `pdfs_baixados/diretivo/entregas` são recontados de `pdf_metadata.csv`;
- `data_execucao` e a telemetria de PDFs que não sai dos CSVs
  (`com_texto_extraido`, `escaneados_pendentes`, `dedup_owners`,
  `compartilhados`) são **preservados** do manifest anterior — a telemetria só
  muda num run novo do pipeline;
- `--check` ignora `pipeline_commit`/`data_execucao` (mudam de forma
  independente dos dados) e confere o invariante real: os hashes batem com os
  arquivos.

`run_pipeline.py --sync` chama `build_manifest` **antes** de `build_metadata`
(os descritores leem o manifest). Há teste em `tests/test_manifest.py`.

Demais ajustes (mecânicos): `build_metadata.py` não injeta mais o bloco
schema.org no `index.html` (a função `inject_schema_org` continua no módulo
porque é testada como helper puro, mas não é mais chamada em `generate()`);
`13b` tirou `statistics_summary.json` da lista de checksums; `13c` tirou os
4 artefatos de analytics de `EXPECTED_OUTPUTS`; `conftest.py` tirou `11cb`/`11e`
de `_DEFS_CELLS`; `smoke_test.py` tirou matplotlib/seaborn das deps obrigatórias;
`monthly-refresh.yml` tirou `index.html` do `add-paths` do PR.

---

## 3.5. needs_review = atrito texto autoral × catálogo (dois fatores)

`needs_review` **não é "lixo a validar"**: é, em boa parte, o texto autoral dos
órgãos que não coube no vocabulário controlado. Medido no snapshot, porém, ele
mistura fenômenos distintos — e essa é a nuance que muda o tratamento:

| Tipo | O que é | Quanto (snapshot) | É autoral "espremido"? |
|---|---|---|---|
| `imputado` | eixo vazio no original → inferido do produto (cross-validation) | 2.276 entregas | **não** — dado AUSENTE, inferido |
| `aproximado` | produto fuzzy_high (autoral ≈ catálogo) | 531 entregas | em parte (variação real **+** ruído de PDF: `sOutros`, `oEvolução`…) |
| `residual` | produto 'Outros' | 148 entregas | **sim** — o órgão usou categoria própria |
| `residual` | escala de risco fora do padrão SGD (`1-Alto`, `Médio`…) | prob 15 · imp 18 · trat 35 | **sim** |

Conclusão da veracidade: a tese está **certa para `aproximado` + `residual`**
(o atrito real autoral×catálogo, ~700 entregas + os residuais de risco), mas o
**grosso do `needs_review` é `imputado`** (eixo ausente preenchido) — fenômeno
diferente. O flag binário antigo confundia os três.

Impacto no conceito do código: **os dois fatores já convivem no nível da linha**
— `_normalizado` (catálogo → analytics agregada) + `_original`/`_method`/`_score`
(autoral → caracterização do desvio). `build_variations.py` só consolida e
**tipa** esse atrito, sem descartar nenhum dos dois. É derivado (offline,
`--check` no CI) e não toca o pipeline — fácil de clonar e refinar. Próximos
passos naturais (seus, no clone): separar ruído de extração de variação autoral
dentro de `aproximado` (ex.: detectar caractere colado), e cruzar `residual` com
órgão/eixo para ver *quem* mais escapa do catálogo.

---

## 4. Como rodar e validar (offline, sem o portal)

O corpus já vem extraído em `output/` — não é preciso rodar o pipeline para usar
os dados. Tudo que **não** depende de rede pode ser validado de imediato:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python build_notebook.py            # gera ptd_scraper.ipynb das células
python build_manifest.py            # gera output/manifest.json
python build_metadata.py            # gera datapackage.json + metadata/
python build_corpus.py              # gera harmonized/
python build_variations.py          # gera variations.csv (catálogo de divergências)
python -m pytest -q tests/          # suíte (helpers puros + derivadores --check)
python smoke_test.py                # sintaxe/deps/carga das células
```

O **pipeline completo** (`run_pipeline.py`) precisa do portal SGD/MGI
(gov.br). Ele tem preflight: se o portal estiver inacessível (ex.: bloqueio do
IP do runner), sai com código 2 e mensagem clara — o fallback é rodar no Colab.

---

## 5. Setup do novo repositório

1. **Crie o repositório** no GitHub e descompacte este pacote na raiz:
   ```bash
   unzip ptd-corpus-handout.zip
   cd ptd-corpus
   git init && git add -A && git commit -m "chore: bootstrap PTD-corpus (spin-off sem analytics)"
   git remote add origin https://github.com/OWNER/REPO.git
   git push -u origin main
   ```
2. **Troque `OWNER/REPO`** em `README.md` (clone + badge do Colab). Procure por
   `OWNER/REPO` no projeto:
   ```bash
   grep -rn "OWNER/REPO" .
   ```
3. **GitHub Pages:** o spin-off não tem dashboard. Deixe Pages desligado (ou
   sirva só os dados de `output/` se quiser links diretos aos CSVs).
4. **Refresh mensal (opcional):** para os PRs de `monthly-refresh.yml` rodarem o
   CI sozinhos, crie o secret `DATA_REFRESH_PAT` (fine-grained PAT: Contents RW
   + Pull requests RW). Sem ele, feche/reabra o PR para disparar os checks.
5. **Rode a validação offline da §4** e confirme a suíte verde antes do primeiro
   push.

---

## 6. O que ainda falta validar / decidir

1. **Primeiro run ao vivo do pipeline.** O portal gov.br costuma bloquear IPs de
   runner; este pacote foi montado num ambiente **sem acesso ao portal**, então
   o fim-a-fim (scraping → extração) **não** foi exercido aqui. Rode uma vez
   (local ou Colab) para confirmar. Num run novo, `build_manifest.py` passa a
   recontar `pdfs_baixados/diretivo/entregas` de `pdf_metadata.csv`; se quiser
   também a telemetria de dedup/scan fresca (`dedup_owners`, `compartilhados`,
   `escaneados_pendentes`, `com_texto_extraido`), porte esse cálculo de
   `11cb` (original) para uma célula do corpus ou para `build_manifest.py` — hoje
   ela é **preservada** do snapshot, não recalculada.
2. **`METADATA.md`** pode citar `index.html`/dashboard em passagens da linhagem.
   Revise e ajuste o texto (não afeta código).
3. **`CITATION.cff`** mantém o título/autores da nota técnica do corpus. Ajuste
   se o spin-off for citado de forma diferente.
4. **Tabela de números no `README.md`** reflete o snapshot herdado
   (`data_execucao=2026-05-12`). Atualize quando rodar um refresh.

---

## 7. Reproduzir / regenerar este pacote

O gerador vive no repositório PTD original em `tools/make_spinoff.py`. Para
regenerar a semente quando o corpus mudar lá:

```bash
python tools/make_spinoff.py        # reescreve a árvore + zip do spin-off
```

Os arquivos-fonte do spin-off (templates não-mecânicos: este HANDOUT, o
`README`, `build_manifest.py`, os testes novos, `Makefile`, `requirements`,
`00_title.md`) ficam versionados em `spinoff/` no repositório PTD; o gerador
copia a lista do corpus, aplica as edições mecânicas e sobrepõe esses templates.
