# ============================================================
# CÉLULA 5 — Download dos PDFs
# ============================================================

PDF_MAGIC_BYTES = b"%PDF"
MIN_SUSPICIOUS_SIZE = 10 * 1024   # 10 KB
MIN_VALID_SIZE = 1000             # 1 KB (skip threshold para resume)


def _download_single_pdf(url: str, dest_path: str, sigla: str,
                         doc_type: str) -> Optional[ProcessingError]:
    """
    Baixa um único PDF. Retorna ProcessingError em caso de falha, None se OK.
    Pula o download se o arquivo já existe com tamanho > MIN_VALID_SIZE.
    """
    # Resume: pula se já existe e parece válido
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > MIN_VALID_SIZE:
        return None

    resp = safe_request(url)
    if resp is None:
        return ProcessingError(
            orgao_sigla=sigla,
            document_type=doc_type,
            stage="download",
            error_type="request_failed",
            error_message=f"Falha ao baixar após {MAX_RETRIES} tentativas",
            url=url,
        )

    content = resp.content

    # Verifica magic bytes
    if not content[:4].startswith(PDF_MAGIC_BYTES):
        return ProcessingError(
            orgao_sigla=sigla,
            document_type=doc_type,
            stage="download",
            error_type="invalid_pdf",
            error_message=f"Arquivo não começa com %PDF (magic bytes: {content[:8]!r})",
            url=url,
        )

    # Salva o arquivo
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(content)

    # Alerta para arquivos suspeitamente pequenos
    file_size = len(content)
    if file_size < MIN_SUSPICIOUS_SIZE:
        logger.warning(f"  {sigla}/{doc_type}: arquivo pequeno ({file_size:,} bytes) — pode estar corrompido")

    return None


def download_all_pdfs(organs: List[OrganInfo]) -> List[ProcessingError]:
    """
    Baixa todos os PDFs (diretivo + entregas) dos órgãos.
    Atualiza organ.pdf_path_diretivo e organ.pdf_path_entregas.
    Retorna lista de erros.
    """
    errors: List[ProcessingError] = []
    downloaded_urls: Dict[str, str] = {}   # url → caminho local (evita re-download)

    # Contagem total de downloads potenciais
    total_downloads = sum(
        (1 if o.url_diretivo else 0) + (1 if o.url_entregas else 0)
        for o in organs
    )

    pbar = tqdm(total=total_downloads, desc="Baixando PDFs", unit="pdf")

    for organ in organs:
        for doc_type, url_attr, path_attr, target_dir in [
            ("diretivo", "url_diretivo", "pdf_path_diretivo", DIRS["pdfs_diretivo"]),
            ("entregas", "url_entregas", "pdf_path_entregas", DIRS["pdfs_entregas"]),
        ]:
            url = getattr(organ, url_attr)
            if url is None:
                continue

            filename = f"{organ.sigla}_{doc_type}.pdf"
            dest_path = os.path.join(target_dir, filename)

            # Se outro órgão do mesmo grupo já baixou este URL, reutiliza
            if url in downloaded_urls:
                existing_path = downloaded_urls[url]
                if os.path.exists(existing_path):
                    # Copia ou cria link — usamos cópia para robustez
                    if not os.path.exists(dest_path):
                        import shutil
                        shutil.copy2(existing_path, dest_path)
                    setattr(organ, path_attr, dest_path)
                    pbar.update(1)
                    continue

            err = _download_single_pdf(url, dest_path, organ.sigla, doc_type)
            if err is not None:
                errors.append(err)
            else:
                setattr(organ, path_attr, dest_path)
                downloaded_urls[url] = dest_path

            pbar.update(1)

    pbar.close()
    return errors


# ---- Execução ----
# Download já faz skip automático de PDFs existentes (resume embutido no _download_single_pdf)
if all_organs:
    print(f"Iniciando download de PDFs para {len(all_organs)} órgãos...")
    print("(PDFs já baixados serão reutilizados automaticamente)")
    download_errors = download_all_pdfs(all_organs)
    all_errors.extend(download_errors)
else:
    print("ERRO: Nenhum órgão encontrado. Verifique a célula de scraping.")
    download_errors = []

# ---- Resumo ----
_n_dir_ok = sum(1 for o in all_organs if o.pdf_path_diretivo and os.path.exists(o.pdf_path_diretivo))
_n_ent_ok = sum(1 for o in all_organs if o.pdf_path_entregas and os.path.exists(o.pdf_path_entregas))

_total_size = 0
_suspicious: List[str] = []
for o in all_organs:
    for p in [o.pdf_path_diretivo, o.pdf_path_entregas]:
        if p and os.path.exists(p):
            sz = os.path.getsize(p)
            _total_size += sz
            if sz < MIN_SUSPICIOUS_SIZE:
                _suspicious.append(f"{o.sigla}: {os.path.basename(p)} ({sz:,} bytes)")

print(f"\n{'='*50}")
print(f"Download concluído")
print(f"  Documento Diretivo OK:    {_n_dir_ok}")
print(f"  Anexo de Entregas OK:     {_n_ent_ok}")
print(f"  Erros de download:        {len(download_errors)}")
print(f"  Tamanho total:            {_total_size / (1024*1024):.1f} MB")
print(f"{'='*50}")

if _suspicious:
    print(f"\nArquivos suspeitamente pequenos (<{MIN_SUSPICIOUS_SIZE//1024} KB):")
    for s in _suspicious:
        print(f"  - {s}")

if download_errors:
    print(f"\nErros de download:")
    for e in download_errors:
        print(f"  - {e.orgao_sigla}/{e.document_type}: {e.error_type} — {e.error_message}")