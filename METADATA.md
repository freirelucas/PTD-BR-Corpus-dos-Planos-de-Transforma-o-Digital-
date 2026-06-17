# Metadados em padrões de dados abertos

O corpus PTD é publicado com um conjunto de descritores em padrões abertos,
gerados de forma reprodutível por [`build_metadata.py`](build_metadata.py) a
partir de fontes únicas da verdade (sem duplicação manual):

| Fonte | Fornece |
|---|---|
| `CITATION.cff` | autoria, licença, versão, keywords, resumo |
| `output/manifest.json` | proveniência: commit do pipeline, data, `sha256` e bytes por arquivo |
| `output/*.csv` | nomes de coluna (schema) |
| `output/vocabulary_mapping.csv` | rótulos canônicos (`prefLabel`) + variantes (`altLabel`) |

Regenerar: `make metadata` (ou `python build_metadata.py`).
Verificar se os artefatos commitados estão em dia: `python build_metadata.py --check`.

## Artefatos gerados

| Arquivo | Padrão | Para quê |
|---|---|---|
| `output/datapackage.json` | **Frictionless Data Package** + Table Schema | Torna os CSVs auto-descritivos (tipos, enums, `primaryKey`, `foreignKeys`) e validáveis com `frictionless validate`. |
| `output/metadata/schema_org_dataset.jsonld` | **schema.org/Dataset** (JSON-LD) | Descoberta pública (Google Dataset Search). |
| `output/metadata/dcat.jsonld` | **DCAT-AP** + tema **VCGE** | Interoperabilidade com o ecossistema gov.br / dados.gov.br. |
| `output/metadata/vocabulary.skos.jsonld` | **SKOS** ConceptScheme | Publica as escalas e produtos canônicos como vocabulário reusável/linkável. |
| `output/metadata/schemas/{risks,deliveries}.schema.json` | **JSON Schema** (2020-12) | Contrato dos `.json` aninhados, validável em CI. |
| `output/metadata/prov.jsonld` | **W3C PROV-O** | Linhagem: PTDs do portal SGD → pipeline → outputs (com `sha256`). |
| `output/metadata/ckan_package.json` | payload **CKAN** | Corpo pronto para publicação no dados.gov.br (ver abaixo). |

### Chaves e integridade referencial

O Table Schema declara `organs.sigla` como `primaryKey` e
`risks.orgao_sigla` / `deliveries.orgao_sigla` como `foreignKeys` para
`organs.sigla` — `frictionless validate` checa a integridade referencial
entre os recursos.

### Vocabulário canônico (SKOS)

`vocabulary.skos.jsonld` expõe cinco `ConceptScheme` (eixos, produtos,
probabilidade, impacto, tratamento). Cada termo canônico vira `skos:prefLabel`
e as variantes capturadas dos PDFs viram `skos:altLabel`. As escalas ordinais
(probabilidade, impacto) recebem `skos:notation` posicional (1…5).

## Validação em CI

A validação roda dentro do `pytest` (workflow `tests.yml`), sem etapa
separada:

- `test_committed_artifacts_are_in_sync` — equivale a `--check`: falha se os
  descritores commitados divergem do gerador.
- `test_datapackage_validates_with_frictionless` — valida o Data Package + dados.
- `test_json_outputs_validate_against_schema` — valida `risks.json`/`deliveries.json`.

## Nota de qualidade: o que a validação revelou

Aplicar enums canônicos via Table Schema **expôs 43 valores** não canônicos
vazados para `*_normalizado` em riscos — artefatos de *column-bleed* (fragmentos
como `de de Ocor-`, `1-Alto`, listas de ações inteiras) e compostos
(`transferir; transferir`). Distribuição: 6 em probabilidade, 15 em impacto,
22 em tratamento.

Achado relevante: probabilidade e impacto já estavam todos `needs_review=True`,
**mas 17 dos 22 de `tratamento_normalizado` haviam escapado ao `needs_review`** —
uma lacuna da fila de revisão que só apareceu sob a validação por enum.

Por isso, no datapackage de `output/`, os campos de escala de risco
(`probabilidade_normalizada`, `impacto_normalizado`, `tratamento_normalizado`)
documentam a escala canônica na descrição **sem** enum rígido. Os campos limpos
(`eixo_normalizado`, `tabela_tipo`, `*_method`, `extraction_confidence`) mantêm
enum rígido. O contrato estritamente canônico é cumprido pela **versão
harmonizada** (abaixo).

## Corpus harmonizado (`output/harmonized/`)

Gerado por [`build_corpus.py`](build_corpus.py) (`make corpus`) a partir de
`output/*.csv`. Produz uma visão em que as colunas `*_normalizado` são
**estritamente canônicas** — resolvendo os 43 valores acima de forma reversível:

| Motivo | Ação na coluna normalizada | Nº |
|---|---|---|
| `column_bleed` | branqueada (valor cru fica em `*_original`) | 38 |
| `multiplos_valores` (ex. `mitigar; transferir`) | branqueada + anotada | 4 |
| `deduplicado` (ex. `transferir; transferir`) | colapsada para o token único | 1 |

Garantias:
- **Reversível** — o valor cru permanece em `*_original`; toda alteração está em
  `harmonization_report.json` (órgão, campo, valor original, motivo).
- **Re-sinalização** — linhas branqueadas por bleed/múltiplos recebem
  `needs_review=True` e uma anotação `harmonizacao(...)` em `review_reason`,
  fechando a lacuna de `tratamento`.
- **Contrato estrito** — `output/harmonized/datapackage.json` usa enums
  **estritos** e passa em `frictionless validate` (o de `output/` não passaria).

### Linhagem (cadeia de transformações)

```
PTDs (PDF, portal SGD/MGI)
  → scraping (04b) → download+dedup (05b/05c) → extração PyMuPDF (06b/07b/08b)
  → normalização+canonização SGD (09b) → export CSV/JSON (10b) ......... output/
  → descritores de dados abertos (build_metadata.py) .... output/datapackage.json, metadata/
  → harmonização estrita (build_corpus.py) .............. output/harmonized/
  → cobertura por órgão (build_coverage.py) ............ output/coverage_summary.csv
  → catálogo de variações (build_variations.py) ........ output/variations.csv
  → pasta Excel pronta p/ uso (build_xlsx.py) .......... output/PTD-corpus.xlsx
```

A mesma linhagem está formalizada em `output/metadata/prov.jsonld` (PROV-O).

## Publicar no dados.gov.br (CKAN)

`output/metadata/ckan_package.json` é o corpo de uma requisição
`package_create` da API CKAN. A publicação **não** é automatizada aqui — exige
credenciais e autorização institucional. Quando autorizado:

1. Ajustar `owner_org` para o slug real da organização no portal.
2. Confirmar os termos VCGE em `extras.tema_vcge`.
3. `POST {PORTAL}/api/3/action/package_create` com header `Authorization: <API_KEY>`
   e o JSON como corpo.

Referências: [Frictionless Data](https://specs.frictionlessdata.io/) ·
[schema.org/Dataset](https://schema.org/Dataset) ·
[DCAT-AP](https://semiceu.github.io/DCAT-AP/releases/3.0.0/) ·
[VCGE](http://vocab.e.gov.br/) ·
[SKOS](https://www.w3.org/TR/skos-reference/) ·
[PROV-O](https://www.w3.org/TR/prov-o/) ·
[JSON Schema](https://json-schema.org/).
