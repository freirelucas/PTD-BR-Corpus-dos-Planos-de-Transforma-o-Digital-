# PTD-corpus — Planos de Transformação Digital (Gov.br)

Coleta, extração, padronização e exportação dos **Planos de Transformação
Digital (PTDs)** dos órgãos federais brasileiros — entregas pactuadas e riscos de
gestão — a partir dos PDFs oficiais do gov.br.

**Fonte:** [gov.br/governodigital — Planos de Transformação Digital](https://www.gov.br/governodigital/pt-br/estrategias-e-governanca-digital/planos-de-transformacao-digital)

**Pipeline:**
1. Scraping da lista de órgãos signatários e URLs dos PDFs
2. Download dos PDFs (Documento Diretivo + Anexo de Entregas)
3. Extração de tabelas (PyMuPDF `find_tables()`)
4. Padronização de vocabulário
5. Exportação CSV/JSON + relatório de erros
6. Validação com checksums + bundle de publicação
