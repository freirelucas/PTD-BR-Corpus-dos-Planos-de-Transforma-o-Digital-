# PTD-corpus — Planos de Transformação Digital (Gov.br)

Notebook de **engenharia do corpus** dos Planos de Transformação Digital dos
órgãos federais brasileiros: coleta, extração, padronização e exportação.

Spin-off do projeto PTD **sem a camada de analytics** (estatísticas, figuras,
dashboard, insumos da nota técnica) — ver `HANDOUT.md`.

**Fonte:** [gov.br/governodigital - Planos de Transformação Digital](https://www.gov.br/governodigital/pt-br/estrategias-e-governanca-digital/planos-de-transformacao-digital)

**Pipeline:**
1. Scraping da lista de órgãos signatários e URLs dos PDFs
2. Download dos PDFs (Documento Diretivo + Anexo de Entregas)
3. Extração de tabelas (PyMuPDF `find_tables()`)
4. Padronização de vocabulário
5. Exportação CSV/JSON + relatório de erros
6. Validação com checksums + bundle de publicação
