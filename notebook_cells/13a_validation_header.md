## Célula 13 — Relatório de Validação do Ciclo

Exporta um único JSON (`output/validation_report.json`) consolidando todas as métricas que precisam ser auditadas após cada run do pipeline. Útil para:

- **Validação pós-mudança**: comparar antes/depois ao introduzir aliases (Camada 1.5), corrigir extração tabular (Categoria A) ou refatorar utilitários.
- **Auditoria entre máquinas**: confirmar que um run no Colab produziu o mesmo resultado que rodaria localmente (checksums dos CSVs).
- **Histórico de regressões**: arquivar o JSON após cada run significativo cria uma série temporal de saúde do pipeline.

O JSON contém: contagens, taxas de canonização, top-20 residuais por campo, status dos thresholds de qualidade e MD5 dos outputs principais.
