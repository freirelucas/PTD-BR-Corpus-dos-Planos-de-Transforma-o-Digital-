# ============================================================
# CÉLULA 8 — Extração de Tabelas de Entregas (PyMuPDF find_tables)
# ============================================================
# Abordagem híbrida: find_tables() para tabelas multi-página,
# fallback texto para PDFs sem estrutura tabelar.
# Captura produto "Outros" literalmente.

def _id_col(col_name: str) -> Optional[str]:
    c = _normalize_header(str(col_name))
    cs = c.strip()
    # Match exato ANTES dos substring matches — "Situação" colide com "ação" via
    # `"acao" in c` se for substring; checar status primeiro evita falso positivo.
    if cs == "status" or cs == "situacao" or cs == "situação": return "status"
    if cs == "pactuado" or cs == "pactuado?" or cs == "entregue" or cs == "entregue?": return "pactuado"
    if cs == "justificativa" or ("motivo" in c and "cancel" in c): return "justificativa"
    if "servico" in c or "acao" in c: return "servico"
    if cs in ("produto", "produto ptd", "entrega"): return "produto"
    if "eixo" in c: return "eixo"
    if "dtpactuada" in c.replace(" ","") or "data pactuada" in c or "prazo" in c: return "data_pactuada"
    if "dtentrega" in c.replace(" ","") or "data entrega" in c or "data conclusao" in c: return "data_entrega"
    return None


def _is_outros(text: str) -> bool:
    return normalize_text(text).lower().strip() in ("outros", "outro", "outros -", "outros –")


def _classify_tabela_tipo(col_map: dict, row_status: Optional[str] = None) -> str:
    """Classifica tabela como pactuada/concluida/cancelada por estrutura.

    Estratégia (defensiva, exige sinais combinados pra reduzir falso positivo):
    1. `row_status` (valor por linha de coluna 'status'/'situação') vence se vier
       um termo claro: "concluído", "cancelado", "pactuada", "em andamento".
    2. Concluida: precisa de `data_entrega` OU `pactuado` (qualquer um — colunas
       inéditas no template de pactuadas).
    3. Cancelada: precisa de `justificativa` E não pode ter `data_entrega`
       (cancelada não tem data de entrega, mas pactuada pode ter coluna
       "Justificativa" pra explicar produto "Outros").
    4. Default: "pactuada" — comportamento histórico, todos os PTDs em main.

    Especulativo: o template SGD para ciclos completos não está documentado.
    Após Colab run, se aparecerem entries com tabela_tipo != pactuada,
    inspecionar os PDFs de origem pra confirmar e ajustar.
    """
    if row_status:
        s = normalize_text(str(row_status)).lower().strip()
        if "conclu" in s or s in ("sim", "entregue", "finalizada"): return "concluida"
        if "cancel" in s or s in ("nao", "não"): return "cancelada"
        if "pactuada" in s or s == "em andamento": return "pactuada"
    if "data_entrega" in col_map or "pactuado" in col_map: return "concluida"
    if "justificativa" in col_map and "data_entrega" not in col_map and "pactuado" not in col_map:
        return "cancelada"
    return "pactuada"


_HEADER_LITERALS_DELIVERY = {
    "servico", "serviço", "servico/acao", "servico/ação", "ação", "acao",
    "produto", "produto ptd", "eixo", "data pactuada", "data entrega",
    "area responsavel", "área responsável", "id", "id entrega",
}


def _is_header_literal_delivery(value: str) -> bool:
    """True se valor é texto literal de header (capturado como dado em row)."""
    if not value:
        return False
    norm = strip_accents(normalize_text(value).lower().strip())
    return norm in _HEADER_LITERALS_DELIVERY


def _extract_deliveries_tables(pdf_path: str, sigla: str) -> List[DeliveryEntry]:
    """Extrai entregas via find_tables() com matching de produtos."""
    entries = []
    doc = fitz.open(pdf_path)
    col_map = None

    for page in doc:
        tabs = page.find_tables()
        for table in tabs.tables:
            try:
                df = table.to_pandas()
            except Exception:
                continue
            if df is None or df.empty or df.shape[1] < 3:
                continue

            # Tentar mapear colunas
            nm = {}
            for ci, col in enumerate(df.columns):
                role = _id_col(str(col))
                if role and role not in nm:
                    nm[role] = str(col)
            if "produto" in nm or ("servico" in nm and len(nm) >= 2):
                col_map = nm
            elif col_map and df.shape[1] == len(col_map):
                # Continuação multi-página: mesma estrutura, headers são dados
                # Recuperar primeira linha (que virou header de coluna)
                header_vals = [normalize_text(str(c)) for c in df.columns]
                prod_in_header = fuzzy_match_produto(header_vals[1] if len(header_vals)>1 else "")
                is_out_header = _is_outros(header_vals[1] if len(header_vals)>1 else "")
                if (prod_in_header[1] >= 0.85 or is_out_header) and header_vals[0].lower() not in ("nan","none",""):
                    # Header é dado — criar entrada e processar normalmente
                    p = prod_in_header[0] if prod_in_header[1] >= 0.85 else "Outros"
                    e = PRODUTO_TO_EIXO.get(p, "")
                    if not e and len(header_vals) > 2:
                        em = fuzzy_match_eixo(header_vals[2])
                        if em[1] >= 0.80: e = em[0]
                    entries.append(DeliveryEntry(
                        orgao_sigla=sigla, servico_acao=header_vals[0][:250],
                        produto_original=header_vals[1][:250] if len(header_vals)>1 else "",
                        produto_normalizado=p, eixo_original=header_vals[2][:100] if len(header_vals)>2 else "",
                        eixo_normalizado=e,
                        data_pactuada=parse_date(header_vals[4]) if len(header_vals)>4 and header_vals[4] else None,
                        extraction_confidence="medium", needs_review=True,
                        review_reason="recuperado de header multi-página",
                    ))
                # Usar col_map posicional existente para o restante das linhas

            if not col_map and len(df) > 0:
                for ci, val in enumerate(df.iloc[0]):
                    role = _id_col(str(val))
                    if role:
                        if col_map is None:
                            col_map = {}
                        if role not in col_map:
                            col_map[role] = str(df.columns[ci])
                if col_map:
                    df = df.iloc[1:].reset_index(drop=True)

            if not col_map:
                for _, row in df.iterrows():
                    for val in row:
                        pm = fuzzy_match_produto(str(val))
                        if pm[1] >= 0.85 or _is_outros(str(val)):
                            ci2 = list(row).index(val)
                            col_map = {"produto": str(df.columns[ci2])}
                            if ci2 > 0: col_map["servico"] = str(df.columns[ci2-1])
                            if ci2+1 < len(df.columns): col_map["eixo"] = str(df.columns[ci2+1])
                            break
                    if col_map:
                        break

            if not col_map:
                continue

            # Construir mapa posicional para tabelas de continuação
            # onde os nomes de coluna são dados, não headers
            pos_map = None
            if col_map:
                test_col = col_map.get("produto", "")
                if test_col and test_col not in df.columns:
                    # Nomes mudaram (continuação) — mapear por posição
                    # Estrutura padrão: 0=servico, 1=produto, 2=eixo, 3=area, 4=data_pactuada
                    pos_map = {"servico": 0, "produto": 1, "eixo": 2}
                    if df.shape[1] >= 5: pos_map["data_pactuada"] = 4
                    elif df.shape[1] >= 4: pos_map["data_pactuada"] = 3

            for _, row in df.iterrows():
                prod_raw = ""
                if pos_map and "produto" in pos_map:
                    prod_raw = normalize_text(str(row.iloc[pos_map["produto"]]))
                elif "produto" in col_map:
                    prod_raw = normalize_text(str(row.get(col_map["produto"], "")))
                if not prod_raw or prod_raw.lower() in ("nan", "none", "produto", "produto ptd"):
                    for val in row:
                        pm = fuzzy_match_produto(str(val))
                        if pm[1] >= 0.85 or _is_outros(str(val)):
                            prod_raw = normalize_text(str(val))
                            break
                if not prod_raw or prod_raw.lower() in ("nan", "none"):
                    continue

                # FIX ESTRUTURAL — header capturado em produto: skip row.
                # Acontece em PDFs onde find_tables pega header repetido em
                # nova página como linha de dados.
                if _is_header_literal_delivery(prod_raw):
                    continue

                pm = fuzzy_match_produto(prod_raw)
                is_out = _is_outros(prod_raw)
                if pm[1] < 0.85 and not is_out:
                    continue

                serv = ""
                if pos_map and "servico" in pos_map:
                    serv = normalize_text(str(row.iloc[pos_map["servico"]]))
                elif "servico" in col_map:
                    serv = normalize_text(str(row.get(col_map["servico"], "")))
                if serv.lower() in ("nan", "none", "servico/acao", "servico", "serviço /ação"): serv = ""

                eixo_raw = ""
                if pos_map and "eixo" in pos_map:
                    eixo_raw = normalize_text(str(row.iloc[pos_map["eixo"]]))
                elif "eixo" in col_map:
                    eixo_raw = normalize_text(str(row.get(col_map["eixo"], "")))
                if eixo_raw.lower() in ("nan", "none", "eixo"): eixo_raw = ""

                prod_norm = pm[0] if pm[1] >= 0.85 else "Outros"
                eixo_norm = PRODUTO_TO_EIXO.get(prod_norm, "")
                if not eixo_norm:
                    eixo_match = fuzzy_match_eixo(eixo_raw)
                    if eixo_match[1] >= 0.80:
                        eixo_norm = eixo_match[0]

                # Datas: pactuada e entrega são agora separadas em col_map.
                # Para retrocompat, "data" antiga vira "data_pactuada".
                def _read_field(name):
                    if pos_map and name in pos_map:
                        return normalize_text(str(row.iloc[pos_map[name]]))
                    if name in col_map:
                        return normalize_text(str(row.get(col_map[name], "")))
                    return ""

                def _clean(v):
                    return "" if v.lower() in ("nan", "none", "dtpactuada", "dtentrega") else v

                data_pact = _clean(_read_field("data_pactuada"))
                data_entr = _clean(_read_field("data_entrega"))
                pactuado_val = _clean(_read_field("pactuado"))
                justif_val = _clean(_read_field("justificativa"))
                status_val = _clean(_read_field("status"))

                tipo = _classify_tabela_tipo(col_map, status_val or None)

                entries.append(DeliveryEntry(
                    orgao_sigla=sigla,
                    tabela_tipo=tipo,
                    servico_acao=serv[:250],
                    produto_original=prod_raw[:250],
                    produto_normalizado=prod_norm,
                    eixo_original=eixo_raw,
                    eixo_normalizado=eixo_norm,
                    data_pactuada=parse_date(data_pact) if data_pact else None,
                    data_entrega=parse_date(data_entr) if data_entr else None,
                    pactuado=pactuado_val or None,
                    justificativa=justif_val[:500] if justif_val else None,
                    extraction_confidence="high" if pm[1] >= 0.95 else ("medium" if pm[1] >= 0.85 else "low"),
                    needs_review=pm[1] < 0.95 or is_out,
                    review_reason="produto Outros" if is_out else (f"fuzzy={pm[1]:.2f}" if pm[1] < 0.95 else None),
                ))

    doc.close()
    return entries


def _extract_deliveries_text(pdf_path: str, sigla: str) -> List[DeliveryEntry]:
    """Fallback: extrai entregas por matching de produto no texto linha-a-linha."""
    entries = []
    doc = fitz.open(pdf_path)

    for page in doc:
        lines = [l.strip() for l in page.get_text().split('\n') if l.strip()]
        for i, line in enumerate(lines):
            pm = fuzzy_match_produto(line)
            is_out = _is_outros(line)
            if pm[1] < 0.85 and not is_out:
                continue

            serv = ""
            if i > 0:
                prev = lines[i-1]
                if (fuzzy_match_produto(prev)[1] < 0.80 and
                    fuzzy_match_eixo(prev)[1] < 0.80 and len(prev) > 5 and
                    not re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", prev.lower())):
                    serv = prev[:250]

            prod_norm = pm[0] if pm[1] >= 0.85 else "Outros"
            eixo_norm = PRODUTO_TO_EIXO.get(prod_norm, "")
            if not eixo_norm and i+1 < len(lines):
                em = fuzzy_match_eixo(lines[i+1])
                if em[1] >= 0.80:
                    eixo_norm = em[0]

            data = ""
            for j in range(i+1, min(i+5, len(lines))):
                if re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[\-/]\d{2,4}$", lines[j].lower()):
                    data = lines[j]; break
                if re.match(r"^\d{2}/\d{2,4}$", lines[j]):
                    data = lines[j]; break

            entries.append(DeliveryEntry(
                orgao_sigla=sigla,
                servico_acao=serv,
                produto_original=line[:250],
                produto_normalizado=prod_norm,
                eixo_original="",
                eixo_normalizado=eixo_norm,
                data_pactuada=parse_date(data) if data else None,
                extraction_confidence="high" if pm[1] >= 0.95 else ("medium" if pm[1] >= 0.85 else "low"),
                needs_review=pm[1] < 0.95 or is_out,
                review_reason="produto Outros" if is_out else None,
            ))

    doc.close()
    return entries


# --------------- Extração em lote (híbrida) -------------------

def extract_all_deliveries() -> None:
    global all_deliveries, all_errors

    # Fingerprint do estado upstream (siglas com PDF entregas após dedup MD5).
    # Invalida o cache automaticamente quando 05c_dedup zera paths.
    fp = state_fingerprint(sorted((o.sigla, bool(o.pdf_path_entregas)) for o in all_organs))

    cached = load_checkpoint("deliveries_raw", expected_fingerprint=fp)
    if cached is not None and len(cached[0]) > 0:
        cached_del, cached_errors, processed_siglas = cached
        all_deliveries.extend(cached_del)
        all_errors.extend(cached_errors)
        print(f"  Retomando: {len(cached_del)} entregas de {len(processed_siglas)} órgãos")
    else:
        cached_del, cached_errors, processed_siglas = [], [], set()

    organs_with_pdf = [o for o in all_organs if o.pdf_path_entregas]
    pending = [o for o in organs_with_pdf if o.sigla not in processed_siglas]

    if not pending:
        print("  Todos os órgãos já processados (checkpoint).")
        return

    print(f"  Processando: {len(pending)} órgãos pendentes")

    pdf_results_cache: Dict[str, Tuple[List[DeliveryEntry], str]] = {}
    batch_del, batch_errors = [], []
    count = 0

    for organ in tqdm(pending, desc="Extraindo entregas"):
        sigla = organ.sigla
        pdf_path = organ.pdf_path_entregas

        if not os.path.isfile(pdf_path):
            batch_errors.append(ProcessingError(orgao_sigla=sigla, document_type="entregas",
                stage="extraction", error_type="file_not_found",
                error_message=f"PDF não encontrado: {pdf_path}"))
            processed_siglas.add(sigla)
            count += 1
            continue

        real_path = os.path.realpath(pdf_path)
        if real_path in pdf_results_cache:
            owner = pdf_results_cache[real_path][1]
            processed_siglas.add(sigla)
            logger.info(f"[{sigla}] PDF compartilhado com {owner} — sem duplicação")
        else:
            # Híbrido: find_tables primeiro, fallback texto
            ft_entries = _extract_deliveries_tables(pdf_path, sigla)
            tx_entries = _extract_deliveries_text(pdf_path, sigla)
            best = ft_entries if len(ft_entries) >= len(tx_entries) else tx_entries

            pdf_results_cache[real_path] = (best, sigla)
            batch_del.extend(best)
            all_deliveries.extend(best)
            processed_siglas.add(sigla)

            if best:
                logger.info(f"[{sigla}] {len(best)} entregas extraídas")

        count += 1
        if count % 10 == 0:
            save_checkpoint((cached_del + batch_del, cached_errors + batch_errors, processed_siglas), "deliveries_raw", fingerprint=fp)

    save_checkpoint((cached_del + batch_del, cached_errors + batch_errors, processed_siglas), "deliveries_raw", fingerprint=fp)
    print(f"  Extração de entregas concluída.")


# --------------- Execução -------------------------------------
extract_all_deliveries()

organs_with_del = set(d.orgao_sigla for d in all_deliveries)
del_errors = [e for e in all_errors if e.document_type == "entregas" and e.stage == "extraction"]

print(f"\n{'='*60}")
print(f"RESUMO — Extração de Entregas")
print(f"{'='*60}")
print(f"  Total de entregas extraídas: {len(all_deliveries)}")
print(f"  Órgãos com entregas: {len(organs_with_del)}")
print(f"  Erros de extração: {len(del_errors)}")

tipo_counts = {}
for d in all_deliveries:
    t = d.tabela_tipo or "pactuada"
    tipo_counts[t] = tipo_counts.get(t, 0) + 1
print(f"  Por tipo: {tipo_counts}")

n_outros = sum(1 for d in all_deliveries if d.produto_normalizado == "Outros")
print(f"  Produto 'Outros': {n_outros}")
