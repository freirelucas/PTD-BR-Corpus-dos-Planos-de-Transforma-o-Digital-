# ============================================================
# CÉLULA 7 — Extração de Tabelas de Risco (PyMuPDF find_tables)
# ============================================================
# Inclui: merge multi-página, recuperação header-as-data,
# resolução de referências numéricas de ações.

_HEADER_LITERALS_RISK = {
    "risco", "probabilidade", "impacto", "tratamento",
    "acoes", "ações", "ação",
    "probabilidade de ocorrencia", "probabilidade de ocorrência",
    "nivel de impacto", "nível de impacto",
    "id risco", "id do risco", "id",
}


def _is_header_literal(value: str) -> bool:
    """True se valor é texto literal de header (capturado como dado)."""
    if not value:
        return False
    norm = strip_accents(normalize_text(value).lower().strip())
    return norm in _HEADER_LITERALS_RISK


def _try_swap_prob_impacto(prob_raw: str, imp_raw: str,
                           prob_m: Tuple[str, float],
                           imp_m: Tuple[str, float]) -> Optional[Tuple[str, str, Tuple[str, float], Tuple[str, float]]]:
    """Detecta column-shift prob↔impacto e retorna valores corrigidos.

    Aciona se ambos casam mal nas escalas esperadas E casam bem se invertidos.
    Conservador: requer score >= 0.85 nas escalas invertidas.

    Retorna (prob_corrigido, imp_corrigido, prob_m_corrigido, imp_m_corrigido)
    ou None se não houver evidência clara de shift.
    """
    if not prob_raw or not imp_raw:
        return None
    if prob_m[1] >= 0.70 and imp_m[1] >= 0.70:
        return None  # ambos casam onde esperado — não precisa swap
    alt_prob_in_imp = fuzzy_match_scale(prob_raw, IMPACTO_SCALE)
    alt_imp_in_prob = fuzzy_match_scale(imp_raw, PROBABILIDADE_SCALE)
    if alt_prob_in_imp[1] >= 0.85 and alt_imp_in_prob[1] >= 0.85:
        # Swap evidente: prob_raw é valor de impacto, imp_raw é valor de prob
        return (imp_raw, prob_raw, alt_imp_in_prob, alt_prob_in_imp)
    return None


def _map_risk_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    canonical = {"risco":None,"probabilidade":None,"impacto":None,"tratamento":None,"acoes":None}
    keyword_map = {
        "risco": ["risco","evento","descricao do risco","descricao"],
        "probabilidade": ["probabilidade","probabilidade de ocorrer","prob","classificacao de probabilidade"],
        "impacto": ["impacto","severidade","classificacao de impacto"],
        "tratamento": ["opcao de tratamento","tratamento","resposta","tipo de tratamento","estrategia"],
        "acoes": ["acoes de tratamento","descrever acoes","acoes","acao","medidas","plano de acao"],
    }
    headers = {str(c): _normalize_header(str(c)) for c in df.columns}
    cols_list = [str(c) for c in df.columns]

    # ID column ("ID do risco", "Nº", etc) deve ser excluído do match para "risco"
    id_cols = {c for c, n in headers.items() if n in (
        "id do risco", "id risco", "id", "n", "no", "num", "numero", "codigo", "cod"
    ) or n.startswith("id ")}

    for canon_key, keywords in keyword_map.items():
        best_col, best_score = None, 0.0
        for col_name, col_norm in headers.items():
            if canon_key == "risco" and col_name in id_cols:
                continue
            for kw in keywords:
                if kw in col_norm:
                    score = max(len(kw)/max(len(col_norm),1), 0.85)
                    if score > best_score: best_score, best_col = score, col_name
            if best_col is None:
                for kw in keywords:
                    ratio = difflib.SequenceMatcher(None, col_norm, strip_accents(kw)).ratio()
                    if ratio > best_score and ratio >= 0.65: best_score, best_col = ratio, col_name
        canonical[canon_key] = best_col

    # Fallback posicional: quando o cabeçalho do PDF é genérico (Col0/Col2)
    # ou fragmentado, usa a posição padrão do template SGD (5 colunas).
    # Aplica somente se a coluna posicional estiver livre — não sobrescreve
    # mapeamentos por keyword.
    fallback_pos = {"risco": 0, "probabilidade": 1, "impacto": 2, "tratamento": 3, "acoes": 4}
    used_cols = {v for v in canonical.values() if v is not None}
    # Detecta offset por id_risco quando ncols >= 6 e a primeira coluna parece ID
    has_id_col = bool(id_cols) and cols_list[0] in id_cols
    offset = 1 if (len(cols_list) >= 6 and (
        has_id_col or _normalize_header(cols_list[0]) == "col0"
    )) else 0
    for field, pos in fallback_pos.items():
        if canonical[field] is None and pos + offset < len(cols_list):
            cand = cols_list[pos + offset]
            if cand not in used_cols and cand not in id_cols:
                canonical[field] = cand
                used_cols.add(cand)
    return canonical


def extract_risk_table(pdf_path: str, sigla: str) -> Tuple[List[RiskEntry], List[ProcessingError]]:
    entries: List[RiskEntry] = []
    errors: List[ProcessingError] = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        errors.append(ProcessingError(orgao_sigla=sigla, document_type="diretivo",
            stage="extraction", error_type="pdf_open_failed", error_message=str(exc)))
        return entries, errors

    # Extrair lista de ações de tratamento
    full_text = "\n".join(p.get_text() for p in doc)
    action_list = _extract_action_list(full_text)

    risk_ncols = None
    col_order = None

    for page in doc:
        tabs = page.find_tables()
        if not tabs.tables:
            continue
        for table in tabs.tables:
            try:
                df = table.to_pandas()
            except Exception:
                continue
            if df is None or df.shape[1] < 4:
                continue

            df = _consolidate_multiline_cells(df)

            has_header = classify_diretivo_table(df) == "risk_table"
            data_as_header = _cols_are_data(df)
            is_continuation = (risk_ncols and df.shape[1] == risk_ncols
                               and not has_header and _is_risk_data(df))
            is_orphan = (not has_header and not data_as_header and not is_continuation
                         and _is_orphan_risk_data(df))

            if not has_header and not data_as_header and not is_continuation and not is_orphan:
                continue

            if has_header:
                col_map = _map_risk_columns(df)
                if col_map["risco"] is None and len(df.columns) > 0:
                    col_map["risco"] = str(df.columns[0])
                col_order = list(col_map.keys())
                risk_ncols = len(df.columns)

                if len(df) > 0 and _is_subheader_row(df.iloc[0]):
                    df = df.iloc[1:].reset_index(drop=True)
                if len(df) == 0:
                    continue

            elif data_as_header:
                risk_ncols = len(df.columns)
                if col_order is None:
                    col_order = ["risco", "probabilidade", "impacto", "tratamento", "acoes"]
                    if df.shape[1] >= 6:
                        col_order = ["id_risco"] + col_order

                # Recuperar primeiro risco do header
                vals = [normalize_text(str(c)) for c in df.columns]
                vals = ["" if v.lower() in ("nan", "none") else v for v in vals]
                if vals[0] and not _is_subheader_row(vals):
                    prob_raw = vals[1] if len(vals) > 1 else ""
                    imp_raw = vals[2] if len(vals) > 2 else ""
                    trat_raw = vals[3] if len(vals) > 3 else ""
                    acoes_raw = vals[4] if len(vals) > 4 else ""
                    prob_m = fuzzy_match_scale(prob_raw, PROBABILIDADE_SCALE)
                    imp_m = fuzzy_match_scale(imp_raw, IMPACTO_SCALE)
                    trat_m = fuzzy_match_scale(trat_raw, TRATAMENTO_OPTIONS)
                    entries.append(RiskEntry(
                        orgao_sigla=sigla, risco_texto=vals[0],
                        probabilidade_original=prob_raw,
                        probabilidade_normalizada=prob_m[0] if prob_m[1] >= 0.70 else "",
                        impacto_original=imp_raw,
                        impacto_normalizado=imp_m[0] if imp_m[1] >= 0.70 else "",
                        tratamento_original=trat_raw,
                        tratamento_normalizado=trat_m[0] if trat_m[1] >= 0.70 else "",
                        acoes_tratamento=_resolve_action_refs(acoes_raw, action_list),
                        extraction_confidence="medium",
                        needs_review=True,
                        review_reason="recuperado de header de coluna",
                    ))

            elif is_continuation and col_order:
                if len(df) > 0 and _is_subheader_row(df.iloc[0]):
                    df = df.iloc[1:].reset_index(drop=True)

            elif is_orphan:
                risk_ncols = len(df.columns)
                if col_order is None:
                    col_order = ["risco", "probabilidade", "impacto", "tratamento", "acoes"]
                    if df.shape[1] >= 6:
                        col_order = ["id_risco"] + col_order
                if len(df) > 0 and _is_subheader_row(df.iloc[0]):
                    df = df.iloc[1:].reset_index(drop=True)
                if len(df) == 0:
                    continue

            if col_order is None:
                continue

            mapped_count = sum(1 for k in col_order if k in (col_map if has_header else {}))
            if has_header:
                active_map = col_map
            else:
                # Mapeamento posicional. Detecta offset de id_risco quando a
                # tabela tem 1 coluna a mais que o col_order esperado e a 1ª
                # coluna parece um identificador curto (single char/num).
                cols_list = [str(c) for c in df.columns]
                offset = 0
                if len(cols_list) > len(col_order) and len(df) > 0:
                    first_vals = [str(df.iloc[r, 0]).strip() for r in range(min(3, len(df)))]
                    if all(len(v) <= 3 and v.lower() not in ("nan","none","") for v in first_vals if v):
                        offset = 1
                active_map = {f: cols_list[i + offset]
                              for i, f in enumerate(col_order)
                              if i + offset < len(cols_list)}

            for _, row in df.iterrows():
                if _is_subheader_row(row):
                    continue

                def _get(field):
                    col = active_map.get(field)
                    if col and col in row.index:
                        v = normalize_text(str(row[col]))
                        return "" if v.lower() in ("nan", "none") else v
                    return ""

                risco = _get("risco")
                prob = _get("probabilidade")
                imp = _get("impacto")
                trat = _get("tratamento")
                acoes = _get("acoes")

                if not risco and not prob and not imp:
                    continue

                # FIX ESTRUTURAL 1 — Header capturado como dado: skip row inteira.
                # Acontece em PDFs onde find_tables pega header repetido em
                # página seguinte como primeira linha de dados (CENSIPAM, MJSP).
                if (_is_header_literal(risco) or _is_header_literal(prob)
                        or _is_header_literal(imp) or _is_header_literal(trat)):
                    continue

                prob_m = fuzzy_match_scale(prob, PROBABILIDADE_SCALE)
                imp_m = fuzzy_match_scale(imp, IMPACTO_SCALE)

                # FIX ESTRUTURAL 2 — Swap automático prob↔impacto.
                # Detecta column-shift simétrico (CADE: "Médio"/"1-Alto" em
                # prob, valor de prob em impacto). Conservador: só swap se
                # ambos casam >=0.85 nas escalas INVERTIDAS.
                swap_result = _try_swap_prob_impacto(prob, imp, prob_m, imp_m)
                swap_applied = False
                if swap_result:
                    prob, imp, prob_m, imp_m = swap_result
                    swap_applied = True

                trat_m = fuzzy_match_scale(trat, TRATAMENTO_OPTIONS)
                acoes_resolved = _resolve_action_refs(acoes, action_list)

                review_reasons = []
                if swap_applied:
                    review_reasons.append("swap automático prob↔impacto (column-shift corrigido)")
                if prob and prob_m[1] < 0.70: review_reasons.append(f"probabilidade: '{prob[:40]}'")
                if imp and imp_m[1] < 0.70: review_reasons.append(f"impacto: '{imp[:40]}'")
                if not risco: review_reasons.append("risco vazio")
                # FIX ESTRUTURAL 3 — Column bleed em impacto/tratamento.
                # Sinaliza vazamento sem corrigir (não dá pra recuperar dado
                # original sem reprocessar PDF). Threshold: >100 chars E sem
                # match canônico.
                if imp and len(imp) > 100 and imp_m[1] < 0.70:
                    review_reasons.append(f"impacto: bleed de coluna ({len(imp)} chars)")
                if trat and len(trat) > 100 and trat_m[1] < 0.70:
                    review_reasons.append(f"tratamento: bleed de coluna ({len(trat)} chars)")

                confidence = ("high" if not review_reasons else
                              "medium" if len(review_reasons) <= 1 else "low")

                entries.append(RiskEntry(
                    orgao_sigla=sigla, risco_texto=risco,
                    probabilidade_original=prob,
                    probabilidade_normalizada=prob_m[0] if prob_m[1] >= 0.70 else "",
                    impacto_original=imp,
                    impacto_normalizado=imp_m[0] if imp_m[1] >= 0.70 else "",
                    tratamento_original=trat,
                    tratamento_normalizado=trat_m[0] if trat_m[1] >= 0.70 else "",
                    acoes_tratamento=acoes_resolved,
                    extraction_confidence=confidence,
                    needs_review=len(review_reasons) > 0,
                    review_reason="; ".join(review_reasons) if review_reasons else None,
                ))

    doc.close()
    if not entries:
        errors.append(ProcessingError(orgao_sigla=sigla, document_type="diretivo",
            stage="extraction", error_type="no_risk_table",
            error_message=f"Nenhuma tabela de risco encontrada em {os.path.basename(pdf_path)}"))

    return entries, errors


# --------------- Extração em lote -----------------------------

def extract_all_risks() -> None:
    global all_risks, all_errors

    # Fingerprint do estado upstream (lista de siglas com PDF diretivo após dedup).
    # Se 05c_dedup.py rodar e zerar paths, o fingerprint muda e o cache é
    # invalidado automaticamente, evitando regressões silenciosas.
    fp = state_fingerprint(sorted((o.sigla, bool(o.pdf_path_diretivo)) for o in all_organs))

    cached = load_checkpoint("risks_raw", expected_fingerprint=fp)
    if cached is not None and len(cached[0]) > 0:
        cached_risks, cached_errors, processed_siglas = cached
        all_risks.extend(cached_risks)
        all_errors.extend(cached_errors)
        print(f"  Retomando: {len(cached_risks)} riscos de {len(processed_siglas)} órgãos")
    else:
        cached_risks, cached_errors, processed_siglas = [], [], set()

    organs_with_pdf = [o for o in all_organs if o.pdf_path_diretivo]
    pending = [o for o in organs_with_pdf if o.sigla not in processed_siglas]

    if not pending:
        print("  Todos os órgãos já processados (checkpoint).")
        return

    print(f"  Processando: {len(pending)} órgãos pendentes")

    pdf_results_cache: Dict[str, Tuple[List[RiskEntry], List[ProcessingError], str]] = {}
    batch_risks, batch_errors = [], []
    count = 0

    for organ in tqdm(pending, desc="Extraindo riscos"):
        sigla = organ.sigla
        pdf_path = organ.pdf_path_diretivo

        if not os.path.isfile(pdf_path):
            batch_errors.append(ProcessingError(orgao_sigla=sigla, document_type="diretivo",
                stage="extraction", error_type="file_not_found",
                error_message=f"PDF não encontrado: {pdf_path}"))
            processed_siglas.add(sigla)
            count += 1
            continue

        real_path = os.path.realpath(pdf_path)
        if real_path in pdf_results_cache:
            owner = pdf_results_cache[real_path][2]
            processed_siglas.add(sigla)
            logger.info(f"[{sigla}] PDF compartilhado com {owner} — sem duplicação")
        else:
            entries, errs = extract_risk_table(pdf_path, sigla)
            pdf_results_cache[real_path] = (entries, errs, sigla)
            batch_risks.extend(entries)
            all_risks.extend(entries)
            batch_errors.extend(errs)
            all_errors.extend(errs)
            processed_siglas.add(sigla)
            if entries:
                logger.info(f"[{sigla}] {len(entries)} riscos extraídos")

        count += 1
        if count % 10 == 0:
            save_checkpoint((cached_risks + batch_risks, cached_errors + batch_errors, processed_siglas), "risks_raw", fingerprint=fp)

    save_checkpoint((cached_risks + batch_risks, cached_errors + batch_errors, processed_siglas), "risks_raw", fingerprint=fp)
    print(f"  Extração de riscos concluída.")


# --------------- Execução -------------------------------------
extract_all_risks()


# --------------- Auditoria pós-extração (Categoria A) ---------
# Detecta padrões anômalos comuns na extração tabular e marca needs_review
# com motivo explícito. Não descarta entry — preserva audit trail.
#
# Padrões detectados:
#   (a) Header capturado como dado (valor == nome literal do campo)
#   (b) Fragmento de hifenização (texto < 5 chars OU começa/termina com "-"
#       sem letra ao lado)
#   (c) Bleed de coluna em campo de escala (texto > 30 chars em
#       prob/imp/trat, que deveria ser categoria curta)
#   (d) Column-shift detectável (valor canoniza melhor em outra escala)

_HEADER_LITERALS = {
    "probabilidade", "impacto", "tratamento", "risco",
    "probabilidade de ocorrencia", "probabilidade de ocorrência",
    "nivel de impacto", "nível de impacto",
}
_SCALE_MAX_LEN = 30  # categorias de escala raramente passam de 25 chars


def _is_header_capture(value: str) -> bool:
    """Valor literal igual ao nome do campo."""
    if not value:
        return False
    norm = strip_accents(normalize_text(value).lower().strip())
    return norm in _HEADER_LITERALS


def _is_fragment(value: str) -> bool:
    """Texto fragmentado por hifenização ou quebra de página.

    Detecção CONSERVADORA — só pega padrões inequívocos pra evitar
    falsos positivos em valores válidos curtos ("raro", "alto", "3").

    Padrões:
    1. Termina com hífen sem palavra-seguinte (resto da hifenização perdido)
       Ex: "de de Ocor-", "Probabilidade-"
    2. Começa com hífen + lowercase (sufixo isolado)
       Ex: "-rência", "-bilidade"
    3. Repetição imediata de palavra curta (artefato OCR)
       Ex: "de de Ocor-", "do do" — palavras de 2-3 chars duplicadas seguidas
    """
    if not value:
        return False
    s = value.strip()
    # (1) hífen final solitário
    if s.endswith("-") and len(s) > 1 and not s[-2].isspace():
        return True
    # (2) hífen inicial + lowercase
    if re.match(r"^-[a-záéíóúâêôãõç]", s):
        return True
    # (3) repetição imediata de palavra curta
    if re.search(r"\b(\w{1,3})\s+\1\b", s.lower()):
        return True
    return False


def _is_column_bleed(value: str, scale: list) -> bool:
    """Texto longo demais pra ser categoria de escala (provável bleed)."""
    if not value:
        return False
    if len(value) <= _SCALE_MAX_LEN:
        return False
    # Verifica que não casa com nenhum canônico via fuzzy (se casasse alto,
    # talvez fosse só prolixo mas correto)
    _, score = fuzzy_match(value, scale, threshold=0.85)
    return score < 0.70


def _detect_column_shift(value: str, expected_scale: list, other_scales: list) -> Optional[str]:
    """Se valor casa em outra escala melhor que na esperada → column-shift.

    Retorna nome da escala onde casaria, ou None.
    """
    if not value:
        return None
    _, expected_score = fuzzy_match(value, expected_scale, threshold=0.85)
    if expected_score >= 0.85:
        return None  # casa onde deveria
    for other_name, other_scale in other_scales:
        _, other_score = fuzzy_match(value, other_scale, threshold=0.85)
        if other_score >= 0.85 and other_score > expected_score + 0.10:
            return other_name
    return None


def _audit_risk_entries(entries: List[RiskEntry]) -> Dict[str, int]:
    """Marca needs_review por padrão anômalo. Retorna contagem por categoria."""
    stats = Counter()
    field_specs = [
        ("probabilidade_original", PROBABILIDADE_SCALE, "probabilidade",
         [("impacto", IMPACTO_SCALE)]),
        ("impacto_original", IMPACTO_SCALE, "impacto",
         [("probabilidade", PROBABILIDADE_SCALE)]),
        # Simetria: detecta tratamento que na verdade é valor de outra escala
        # (column-shift). Seguro — _detect_column_shift retorna cedo quando o
        # valor já casa bem em TRATAMENTO_OPTIONS.
        ("tratamento_original", TRATAMENTO_OPTIONS, "tratamento",
         [("probabilidade", PROBABILIDADE_SCALE), ("impacto", IMPACTO_SCALE)]),
    ]
    for e in entries:
        reasons = []
        for attr, scale, label, others in field_specs:
            val = getattr(e, attr, "") or ""
            if not val:
                continue
            if _is_header_capture(val):
                reasons.append(f"{label}: header capturado ('{val[:30]}')")
                stats["header_captured"] += 1
                continue
            if _is_fragment(val):
                reasons.append(f"{label}: fragmento ('{val[:30]}')")
                stats["fragment"] += 1
                continue
            if _is_column_bleed(val, scale):
                reasons.append(f"{label}: bleed de coluna ({len(val)} chars)")
                stats["column_bleed"] += 1
                continue
            shift = _detect_column_shift(val, scale, others)
            if shift:
                reasons.append(f"{label}: column-shift (casa em '{shift}')")
                stats["column_shift"] += 1
        if reasons:
            e.needs_review = True
            existing = (e.review_reason or "").strip()
            new = "; ".join(reasons)
            e.review_reason = f"{existing}; {new}".strip("; ") if existing else new
            e.extraction_confidence = "low"
    return dict(stats)


_audit_stats = _audit_risk_entries(all_risks)
if _audit_stats:
    print("\n--- Auditoria de extração (Categoria A) ---")
    for k, v in sorted(_audit_stats.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<20s} {v:>4d}")
    print(f"  TOTAL marcado needs_review por extração: {sum(_audit_stats.values())}")


organs_with_risks = set(r.orgao_sigla for r in all_risks)
organs_without_risks = set(o.sigla for o in all_organs if o.pdf_path_diretivo) - organs_with_risks
risk_errors = [e for e in all_errors if e.document_type == "diretivo" and e.stage == "extraction"]

print(f"\n{'='*60}")
print(f"RESUMO — Extração de Riscos")
print(f"{'='*60}")
print(f"  Total de riscos extraídos: {len(all_risks)}")
print(f"  Órgãos com tabela de risco: {len(organs_with_risks)}")
print(f"  Órgãos sem tabela de risco: {len(organs_without_risks)}")
if organs_without_risks:
    print(f"    → {', '.join(sorted(organs_without_risks))}")
print(f"  Erros de extração: {len(risk_errors)}")
n_with_acoes = sum(1 for r in all_risks if r.acoes_tratamento and r.acoes_tratamento.strip())
print(f"  Riscos com ações de tratamento: {n_with_acoes}")
