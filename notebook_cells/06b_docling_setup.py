# ============================================================
# CÉLULA 6 — Configuração do Extrator de Tabelas (PyMuPDF)
# ============================================================

import fitz  # PyMuPDF

# --------------- Classificação de tabelas diretivo ------------

def _normalize_header(text: str) -> str:
    if not isinstance(text, str): return ""
    t = normalize_text(text).lower()
    t = t.replace("- ", "").replace("-\n", "")
    return strip_accents(t)


def classify_diretivo_table(df: pd.DataFrame) -> str:
    if df is None or len(df.columns) == 0: return "unknown"
    ncols = len(df.columns)
    headers = [_normalize_header(str(c)) for c in df.columns]
    first_row = [_normalize_header(str(v)) for v in df.iloc[0]] if len(df) > 0 else []
    combined = " ".join(headers + first_row)

    risk_kw = ["risco", "probabilidade", "impacto", "tratamento", "ocorrer"]
    risk_alt = ["evento", "classificacao", "severidade", "resposta", "acao", "acoes",
                "id do risco", "descricao do risco", "opcao de tratamento"]
    risk_hits = sum(1 for kw in risk_kw if kw in combined)
    risk_alt_hits = sum(1 for kw in risk_alt if kw in combined)

    if risk_hits >= 2 and 3 <= ncols <= 8: return "risk_table"
    if risk_hits >= 1 and risk_alt_hits >= 1 and 3 <= ncols <= 8: return "risk_table"
    if "risco" in combined and "tratamento" in combined and 3 <= ncols <= 8: return "risk_table"

    info_kw = ["orgao", "ministerio", "secretaria", "sigla", "cnpj", "responsavel",
               "gestor", "dirigente", "titular", "instituicao", "vinculacao"]
    if sum(1 for kw in info_kw if kw in combined) >= 2: return "organ_info"

    sig_kw = ["assinatura", "assinado", "data", "nome", "cargo", "cpf"]
    if sum(1 for kw in sig_kw if kw in combined) >= 2 and ncols <= 4: return "signature"

    return "unknown"


def classify_entregas_table(df: pd.DataFrame) -> str:
    if df is None or df.empty: return "unknown"
    headers = [_normalize_header(str(c)) for c in df.columns]
    first_row = [_normalize_header(str(v)) for v in df.iloc[0]] if len(df) > 0 else []
    combined = " ".join(headers + first_row)
    compact = combined.replace(" ", "")

    if "justificativa" in combined: return "canceladas"
    if "dtentrega" in compact or "data entrega" in combined or "data de entrega" in combined: return "concluidas"
    if "pactuado?" in combined or "pactuado ?" in combined: return "concluidas"
    if ("area" in combined and "responsavel" in combined) and "dtpactuada" in compact: return "pactuadas"
    if "dtpactuada" in compact or "data pactuada" in combined: return "pactuadas"
    return "unknown"


def _cols_are_data(df: pd.DataFrame) -> bool:
    """Detecta se find_tables interpretou o 1o risco como header de coluna."""
    if df.shape[1] < 4: return False
    col0 = _normalize_header(str(df.columns[0]))
    if len(col0) < 10 or col0.startswith("risco") or col0.startswith("col") or col0 == "nan":
        return False
    col1 = _normalize_header(str(df.columns[1]))
    scale_vals = ["raro", "pouco provavel", "provavel", "muito provavel", "praticamente certo",
                  "baixo", "medio", "alto", "muito alto", "baixa", "media", "alta"]
    return any(sv in col1 for sv in scale_vals)


def _is_risk_data(df: pd.DataFrame) -> bool:
    """Verifica se uma tabela contém valores de escala de risco (continuação)."""
    if df is None or df.empty or df.shape[1] < 4: return False
    all_text = strip_accents(" ".join(str(v).lower() for v in df.values.flatten()))
    scale_vals = ["raro", "pouco provavel", "provavel", "muito provavel", "praticamente certo",
                  "muito baixo", "baixo", "medio", "alto", "muito alto",
                  "mitigar", "eliminar", "transferir", "aceitar", "baixa", "media", "alta"]
    return sum(1 for sv in scale_vals if sv in all_text) >= 2


def _is_subheader_row(row) -> bool:
    text = strip_accents(" ".join(str(v) for v in row).lower())
    return any(kw in text for kw in ["certo]", "certo ]", "ocorrer", "muito alto]",
               "muito alto ]", "tratamento do risco", "escolher entre"])


def _consolidate_multiline_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Consolida tabelas onde cada risco ocupa múltiplas linhas porque o
    PDF usa células com texto quebrado em várias linhas internas.

    Heurística: se col0 (ID do risco) está populado em <40% das linhas e
    há ao menos 3 IDs distintos, agrupa as linhas entre IDs concatenando
    os textos de cada coluna.
    """
    if df is None or df.empty or df.shape[1] < 4:
        return df

    n = len(df)

    def _is_id(v):
        s = str(v).strip()
        return bool(s) and s.lower() not in ("nan", "none")

    id_idx = [i for i in range(n) if _is_id(df.iloc[i, 0])]
    if len(id_idx) < 3 or len(id_idx) >= 0.4 * n:
        return df

    # Cria blocos: [start : next_id_row]. start é a linha do ID exceto
    # quando a linha imediatamente anterior contém texto em col1 sem ID
    # (caso comum em PDFs onde a primeira linha do risco aparece visualmente
    # acima do ID quando há quebra de página/coluna).
    def _has_text(v):
        s = str(v).strip()
        return bool(s) and s.lower() not in ("nan", "none")

    blocks = []
    prev_end = 0
    for k, id_pos in enumerate(id_idx):
        start = id_pos
        if (start > prev_end and not _is_id(df.iloc[start - 1, 0])
                and _has_text(df.iloc[start - 1, 1])):
            start -= 1
        end = id_idx[k + 1] if k + 1 < len(id_idx) else n
        blocks.append((start, end))
        prev_end = end

    consolidated_rows = []
    for start, end in blocks:
        merged = []
        for ci in range(df.shape[1]):
            parts = []
            for ri in range(start, end):
                v = str(df.iloc[ri, ci]).strip()
                if v and v.lower() not in ("nan", "none"):
                    parts.append(v)
            # Preserva semântica de bullets: se algum chunk começa com "-"
            # ou contém ";", junta com " | " (mais legível downstream).
            # Caso simples (texto contínuo): mantém join com espaço.
            has_bullets = any(p.lstrip().startswith(("-", "•", "*")) for p in parts)
            has_semicolons = any(";" in p for p in parts) and len(parts) > 1
            sep = " | " if (has_bullets or has_semicolons) else " "
            merged.append(sep.join(parts))
        consolidated_rows.append(merged)

    return pd.DataFrame(consolidated_rows, columns=df.columns)


def _is_orphan_risk_data(df: pd.DataFrame) -> bool:
    """Detecta tabela cujo conteúdo é dado de risco mas find_tables não
    associou a um cabeçalho identificável (retornou Col0/Col1/... ou
    fragmentos do template como headers). Permite processar tabelas que
    não foram precedidas por uma tabela com cabeçalho válido (caso em
    que is_continuation não dispara por falta de risk_ncols)."""
    if df is None or df.empty or df.shape[1] < 4 or df.shape[1] > 8:
        return False
    if not _is_risk_data(df):
        return False
    headers_norm = [_normalize_header(str(c)) for c in df.columns]
    n_generic = sum(1 for h in headers_norm
                    if (h.startswith("col") and len(h) <= 5)
                    or any(kw in h for kw in ["escolher entre", "certo]", "certo ]",
                                              "muito alto]", "muito alto ]", "ocorrer"]))
    return n_generic >= max(2, len(headers_norm) // 2)


def _extract_action_list(doc_text: str) -> dict:
    """Extrai lista 'Referencial para ações de tratamento do risco'."""
    actions = {}
    for pat in [r"[Rr]eferencial\s+para\s+a[çc][õo]es\s+de\s+tratamento",
                r"[Aa][çc][õo]es\s+de\s+tratamento\s+do\s+risco\s*:"]:
        m = re.search(pat, doc_text)
        if m:
            for line in doc_text[m.end():].split('\n'):
                line = line.strip()
                am = re.match(r"^(\d{1,2})\s*[\.\-\)]\s*(.+)", line)
                if am:
                    actions[am.group(1)] = am.group(2).strip()
                elif actions and not line[0:1].isdigit() and len(actions) > 3:
                    break
            if actions: return actions
    return actions


def _resolve_action_refs(acoes_text: str, action_list: dict) -> str:
    """Resolve referências numéricas ('1, 2, 9') para texto completo."""
    if not acoes_text or not action_list: return acoes_text
    refs = re.findall(r'\d+', acoes_text)
    if not refs: return acoes_text
    tokens = re.split(r'[,;\s]+', acoes_text.strip())
    num_tokens = sum(1 for t in tokens if re.match(r'^\d+$', t.strip()))
    if num_tokens / max(len(tokens), 1) < 0.5: return acoes_text
    resolved = [f"{ref}. {action_list[ref]}" for ref in refs if ref in action_list]
    return " | ".join(resolved) if resolved else acoes_text


print("PyMuPDF configurado.")
print("Classificadores de tabelas e funções de extração carregados.")
print(f"Produtos no vocabulário: {len(ALL_PRODUTOS)}")
