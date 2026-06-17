# ============================================================
# CÉLULA 10 — Exportação de Dados
# ============================================================
from datetime import datetime
from dataclasses import asdict


def _file_size_str(path: str) -> str:
    """Retorna tamanho do arquivo em formato legível."""
    size = os.path.getsize(path)
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def _build_nested_json(entries: list, key_field: str, metadata_extra: dict = None) -> dict:
    """Agrupa entradas por key_field em um JSON com metadata.

    `entries` deve vir ordenado pelo chamador para que `grouped` resulte
    determinístico (Python 3.7+ preserva ordem de inserção em dict).
    """
    grouped = {}
    for entry in entries:
        d = asdict(entry)
        key = d.get(key_field, "UNKNOWN")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(d)

    metadata = {
        "exported_at": datetime.now().isoformat(),
        "total": len(entries),
        "groups": len(grouped),
    }
    if metadata_extra:
        metadata.update(metadata_extra)

    return {"metadata": metadata, "data": grouped}


def _sorted_stable(entries: list, *keys):
    """Ordena por tuplas de chaves, tolerando None (vira string vazia).

    Usa sort estável (Timsort) para preservar a ordem upstream entre
    registros equivalentes.
    """
    def _key(e):
        d = asdict(e) if hasattr(e, "__dataclass_fields__") else e
        return tuple((d.get(k) or "") for k in keys)
    return sorted(entries, key=_key)


export_log = []  # (filename, rows, size_str)

# Ordenação estável aplicada in-place para garantir reprodutibilidade
# bit-a-bit dos CSVs/JSONs entre runs (sem depender da ordem upstream).
all_deliveries = _sorted_stable(
    all_deliveries, "orgao_sigla", "eixo_normalizado",
    "produto_normalizado", "servico_acao",
)
all_risks = _sorted_stable(all_risks, "orgao_sigla", "risco_texto")
all_organs = _sorted_stable(all_organs, "sigla")
all_errors = _sorted_stable(all_errors, "orgao_sigla", "document_type", "stage")

# ---- 1. Entregas: CSV e JSON ----
if all_deliveries:
    df_del = pd.DataFrame([asdict(e) for e in all_deliveries])

    csv_path = os.path.join(DIRS["output"], "deliveries.csv")
    df_del.to_csv(csv_path, index=False, encoding="utf-8-sig")
    export_log.append(("deliveries.csv", len(df_del), _file_size_str(csv_path)))

    json_path = os.path.join(DIRS["output"], "deliveries.json")
    nested = _build_nested_json(all_deliveries, "orgao_sigla")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(nested, f, ensure_ascii=False, indent=2)
    export_log.append(("deliveries.json", len(all_deliveries), _file_size_str(json_path)))
else:
    print("Nenhuma entrega para exportar.")

# ---- 2. Riscos: CSV e JSON ----
if all_risks:
    df_risk = pd.DataFrame([asdict(e) for e in all_risks])

    csv_path = os.path.join(DIRS["output"], "risks.csv")
    df_risk.to_csv(csv_path, index=False, encoding="utf-8-sig")
    export_log.append(("risks.csv", len(df_risk), _file_size_str(csv_path)))

    json_path = os.path.join(DIRS["output"], "risks.json")
    nested = _build_nested_json(all_risks, "orgao_sigla")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(nested, f, ensure_ascii=False, indent=2)
    export_log.append(("risks.json", len(all_risks), _file_size_str(json_path)))
else:
    print("Nenhum risco para exportar.")

# ---- 3. Órgãos: CSV ----
if all_organs:
    df_org = pd.DataFrame([asdict(o) for o in all_organs])

    csv_path = os.path.join(DIRS["output"], "organs.csv")
    df_org.to_csv(csv_path, index=False, encoding="utf-8-sig")
    export_log.append(("organs.csv", len(df_org), _file_size_str(csv_path)))
else:
    print("Nenhum órgão para exportar.")

# ---- 4. Relatório de erros: CSV ----
if all_errors:
    df_err = pd.DataFrame([asdict(e) for e in all_errors])

    csv_path = os.path.join(DIRS["output"], "error_report.csv")
    df_err.to_csv(csv_path, index=False, encoding="utf-8-sig")
    export_log.append(("error_report.csv", len(df_err), _file_size_str(csv_path)))
else:
    print("Nenhum erro registrado para exportar.")

# ---- 5. Mapeamento de vocabulário: CSV ----
vocab_rows = []

# Produto mappings
for m in vocab_report.get("produto_mappings", []):
    vocab_rows.append({
        "type": "produto",
        "original": m["original"],
        "normalized": m["normalized"],
        "score": m["score"],
        "count": m["count"],
    })

# Eixo mappings
for m in vocab_report.get("eixo_mappings", []):
    vocab_rows.append({
        "type": "eixo",
        "original": m["original"],
        "normalized": m["normalized"],
        "score": m["score"],
        "count": m["count"],
    })

# Risk field mappings
for field_key in ["probabilidade_mappings", "impacto_mappings", "tratamento_mappings"]:
    field_type = field_key.replace("_mappings", "")
    for m in risk_report.get(field_key, []):
        vocab_rows.append({
            "type": field_type,
            "original": m["original"],
            "normalized": m["normalized"],
            "score": m["score"],
            "count": m["count"],
        })

# Sempre grava o arquivo (mesmo vazio com header) para alinhar com o
# README e tornar a ausência de mapeamentos uma sentinela explícita.
csv_path = os.path.join(DIRS["output"], "vocabulary_mapping.csv")
vocab_cols = ["type", "original", "normalized", "score", "count"]
df_vocab = pd.DataFrame(vocab_rows, columns=vocab_cols)
if not df_vocab.empty:
    df_vocab = df_vocab.sort_values(
        ["type", "original"], kind="mergesort"
    ).reset_index(drop=True)
df_vocab.to_csv(csv_path, index=False, encoding="utf-8-sig")
export_log.append(("vocabulary_mapping.csv", len(df_vocab), _file_size_str(csv_path)))
if df_vocab.empty:
    print("vocabulary_mapping.csv gravado vazio (nenhum mapeamento aplicado).")

# ---- Resumo de exportação ----
print("\n" + "=" * 60)
print("RESUMO DA EXPORTAÇÃO")
print("=" * 60)
print(f"Diretório de saída: {DIRS['output']}\n")
print(f"{'Arquivo':<30s} {'Registros':>10s} {'Tamanho':>10s}")
print("-" * 52)
for fname, rows, size in export_log:
    print(f"{fname:<30s} {rows:>10,d} {size:>10s}")
print("-" * 52)
total_files = len(export_log)
total_rows = sum(r for _, r, _ in export_log)
print(f"{'TOTAL':<30s} {total_rows:>10,d}   ({total_files} arquivos)")
print("=" * 60)
