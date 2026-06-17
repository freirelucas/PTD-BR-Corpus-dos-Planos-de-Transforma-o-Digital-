# ============================================================
# CÉLULA 4 — Scraping: Lista de Órgãos e URLs dos PDFs
# ============================================================

def _classify_pdf_link(anchor_text: str) -> Optional[str]:
    """Classifica um link de PDF como 'diretivo' ou 'entregas' pelo texto da âncora."""
    text = normalize_text(anchor_text).lower()
    text_no_accents = strip_accents(text)

    diretivo_kw = ["diretivo", "documento diretivo"]
    if any(kw in text_no_accents for kw in diretivo_kw):
        return "diretivo"

    entregas_kw = ["entregas", "anexo de entregas", "anexo entregas"]
    if any(kw in text_no_accents for kw in entregas_kw):
        return "entregas"

    return None


def _extract_siglas_from_header(header_text: str) -> List[str]:
    """
    Extrai siglas de um cabeçalho como:
      'Plano de Transformação Digital SIGLA:'
      'Plano de Transformação Digital SIGLA1 / SIGLA2 / SIGLA3:'
      'Plano de Transformação Digital CVM -'
    """
    text = normalize_text(header_text)

    # Remove o prefixo "Plano de Transformação Digital"
    prefix_pattern = re.compile(
        r"Plano\s+de\s+Transforma[çc][ãa]o\s+Digital\s*", re.IGNORECASE
    )
    text = prefix_pattern.sub("", text).strip()

    # Remove trailing : ou -
    text = re.sub(r"[\s:–\-]+$", "", text).strip()

    if not text:
        return []

    # Divide por " / " para múltiplas siglas
    parts = [p.strip() for p in re.split(r"\s*/\s*", text) if p.strip()]

    # Filtra: siglas são uppercase (permitem hífen para SG-PR), 2-14 chars
    siglas = []
    for p in parts:
        # Limpa possíveis sufixos ("(NOVO)")
        p = re.sub(r"\s*\(.*?\)\s*", "", p).strip()
        if re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\-]{1,14}$", p):
            siglas.append(p)

    return siglas


def scrape_organ_listing(url: str) -> List[OrganInfo]:
    """
    Faz o scraping da página gov.br para extrair órgãos e links de PDFs.

    Estrutura real da página:
      Cada órgão é um <td> contendo:
        <strong>Plano de Transformação Digital SIGLA:</strong>
        <a href="...diretivo.pdf">Documento Diretivo</a> /
        <a href="...entregas.pdf">Anexo de Entregas</a>
    """
    resp = safe_request(url)
    if resp is None:
        raise RuntimeError(f"Não foi possível acessar {url}")

    soup = BeautifulSoup(resp.content, "html.parser")

    # Encontrar todos os <strong> que contêm "Plano de Transformação Digital"
    organ_data: Dict[str, Dict[str, Optional[str]]] = {}
    seen_sigla_sets = set()  # evitar duplicatas

    for strong_tag in soup.find_all(["strong", "b"]):
        raw_text = strong_tag.get_text(separator=" ", strip=True)
        if "transformação digital" not in raw_text.lower() and "transformacao digital" not in raw_text.lower():
            continue

        siglas = _extract_siglas_from_header(raw_text)
        if not siglas:
            continue

        # Evitar processar duplicatas do mesmo grupo
        sigla_key = tuple(sorted(siglas))
        if sigla_key in seen_sigla_sets:
            continue
        seen_sigla_sets.add(sigla_key)

        # Encontrar links PDF no mesmo container (td, p, div, etc.)
        container = strong_tag.parent
        if container is None:
            continue

        pdf_links_in_container = []
        for a_tag in container.find_all("a", href=True):
            href = a_tag["href"]
            if not href.lower().endswith(".pdf"):
                continue
            if "ptds-vigentes/" not in href and "planos-de-transformacao-digital" not in href:
                continue
            anchor_text = a_tag.get_text(separator=" ", strip=True)
            doc_type = _classify_pdf_link(anchor_text)

            # Fallback: classificar pelo nome do arquivo
            if doc_type is None:
                fname = href.rsplit("/", 1)[-1].lower()
                if "diretivo" in fname or "diretiv" in fname:
                    doc_type = "diretivo"
                elif "entregas" in fname or "anexo" in fname:
                    doc_type = "entregas"
                else:
                    doc_type = "unknown"

            # Converter URL relativa para absoluta
            if href.startswith("/"):
                href = "https://www.gov.br" + href

            pdf_links_in_container.append((href, doc_type))

        # Atribuir URLs por tipo
        url_diretivo = None
        url_entregas = None
        for href, doc_type in pdf_links_in_container:
            if doc_type == "diretivo" and url_diretivo is None:
                url_diretivo = href
            elif doc_type == "entregas" and url_entregas is None:
                url_entregas = href
            elif doc_type == "unknown":
                if url_diretivo is None:
                    url_diretivo = href
                elif url_entregas is None:
                    url_entregas = href

        # Registrar para todas as siglas neste header
        for sigla in siglas:
            if sigla not in organ_data:
                organ_data[sigla] = {
                    "nome": raw_text,
                    "url_diretivo": url_diretivo,
                    "url_entregas": url_entregas,
                }

    logger.info(f"Scraping direto: {len(organ_data)} siglas encontradas")

    # Expandir grupos: membros herdam PDFs do cabeça se não tiverem próprios
    expanded = dict(organ_data)
    for head_sigla, members in ORGAN_GROUPS.items():
        if head_sigla in organ_data:
            head_info = organ_data[head_sigla]
            for member in members:
                if member == head_sigla:
                    continue
                if member not in expanded:
                    expanded[member] = {
                        "nome": head_info["nome"],
                        "url_diretivo": head_info["url_diretivo"],
                        "url_entregas": head_info["url_entregas"],
                    }
                else:
                    if expanded[member]["url_diretivo"] is None:
                        expanded[member]["url_diretivo"] = head_info["url_diretivo"]
                    if expanded[member]["url_entregas"] is None:
                        expanded[member]["url_entregas"] = head_info["url_entregas"]

    # Construir lista final
    organs: List[OrganInfo] = []
    for sigla in sorted(expanded.keys()):
        info = expanded[sigla]
        grupo = MEMBER_TO_GROUP.get(sigla)
        organs.append(OrganInfo(
            sigla=sigla,
            nome_completo=info["nome"],
            grupo=grupo,
            url_diretivo=info.get("url_diretivo"),
            url_entregas=info.get("url_entregas"),
        ))

    return organs


# ---- Execução (sempre faz scraping fresco — leva ~3s) ----
print("Fazendo scraping da página principal...")
all_organs = scrape_organ_listing(BASE_URL)

# ---- Validação e Resumo ----
_n_total = len(all_organs)
_n_diretivo = sum(1 for o in all_organs if o.url_diretivo)
_n_entregas = sum(1 for o in all_organs if o.url_entregas)
_n_ambos = sum(1 for o in all_organs if o.url_diretivo and o.url_entregas)
_n_nenhum = sum(1 for o in all_organs if not o.url_diretivo and not o.url_entregas)
_n_grupos = sum(1 for o in all_organs if o.grupo is not None)

print(f"\n{'='*50}")
print(f"Total de órgãos encontrados: {_n_total}")
if _n_total < 80 or _n_total > 110:
    print(f"  ⚠ ATENÇÃO: esperados ~91 órgãos, encontrados {_n_total}")
else:
    print(f"  ✓ Contagem dentro do esperado (~91)")
print(f"  Com Documento Diretivo:    {_n_diretivo}")
print(f"  Com Anexo de Entregas:     {_n_entregas}")
print(f"  Com ambos:                 {_n_ambos}")
print(f"  Sem nenhum PDF:            {_n_nenhum}")
print(f"  Membros de grupo:          {_n_grupos}")
print(f"{'='*50}")

if _n_nenhum > 0:
    print("\nÓrgãos SEM nenhum PDF:")
    for o in all_organs:
        if not o.url_diretivo and not o.url_entregas:
            print(f"  - {o.sigla}")

print("\nAmostra (primeiros 10):")
for o in all_organs[:10]:
    print(f"  {o.sigla:12s} | dir={'Sim' if o.url_diretivo else '---'} "
          f"| ent={'Sim' if o.url_entregas else '---'} "
          f"| grupo={o.grupo or '—'}")