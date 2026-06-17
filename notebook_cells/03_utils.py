# ============================================================
# CÉLULA 3 — Funções Utilitárias
# ============================================================

# --------------- Rede com retry -----------------------------
def safe_request(url: str, max_retries: int = MAX_RETRIES,
                 delay: float = REQUEST_DELAY,
                 timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    """GET com retry exponencial e rate-limiting."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(delay)
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 503 and attempt < max_retries:
                wait = delay * (2 ** attempt)
                print(f"  503 em {url} — retry {attempt}/{max_retries} em {wait:.0f}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            if attempt < max_retries:
                wait = delay * (2 ** attempt)
                print(f"  Erro ({exc}) — retry {attempt}/{max_retries} em {wait:.0f}s")
                time.sleep(wait)
            else:
                print(f"  FALHA definitiva: {url} — {exc}")
                return None
    return None

# --------------- Normalização de texto ----------------------
# Prefixo enumerativo de listas: "A) ", "1) ", "i) ", "II. ", "a- " etc.
# Stripa o marcador para que aliases (e.g., "reduzir ou mitigar") casem
# mesmo quando o PDF do órgão prefixa com letra/número (e.g. CADE: "B) Reduzir...").
_ENUM_PREFIX = re.compile(r"^[A-Za-z0-9]{1,3}\s*[\)\.\-]\s+")

def normalize_text(text: str) -> str:
    """Normaliza unicode, whitespace e caixa para comparação."""
    if not text:
        return ""
    text = str(text)
    # Strip Unicode Cf (Format): ZWSP, ZWJ, soft hyphen, BOM, word joiner,
    # variation selectors, etc. Esses chars vêm de extração PyMuPDF de PDFs
    # com kerning custom e quebram fuzzy_match silenciosamente — strings
    # visualmente idênticas comparam como diferentes, devolvendo ~0.98 via
    # SequenceMatcher em vez de exact match 1.0.
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _ENUM_PREFIX.sub("", text)
    return text

def strip_accents(text: str) -> str:
    """Remove acentos para matching fuzzy."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

# --------------- Matching fuzzy de vocabulário --------------
def fuzzy_match(original: str, candidates: list,
                threshold: float = 0.85) -> Tuple[str, float]:
    """Retorna (melhor_candidato, score). Score 0 se abaixo do threshold."""
    if not original or not candidates:
        return ("", 0.0)
    norm = normalize_text(original).lower()
    norm_stripped = strip_accents(norm)
    # Tentativa exata (case-insensitive, accent-insensitive)
    for c in candidates:
        c_norm = normalize_text(c).lower()
        if norm == c_norm or norm_stripped == strip_accents(c_norm):
            return (c, 1.0)
    # Fuzzy
    best, best_score = "", 0.0
    for c in candidates:
        c_norm = normalize_text(c).lower()
        score = difflib.SequenceMatcher(None, norm_stripped,
                                        strip_accents(c_norm)).ratio()
        if score > best_score:
            best, best_score = c, score
    if best_score >= threshold:
        return (best, best_score)
    return (best, best_score)   # retorna melhor mesmo abaixo do threshold

def fuzzy_match_produto(original: str) -> Tuple[str, float]:
    """Match produto com: aliases determinísticos → canônicos+legados → fuzzy."""
    if not original:
        return ("", 0.0)
    norm = normalize_text(original)
    # Camada 0: alias determinístico (variações conhecidas)
    for alias_key, canonical_val in PRODUTO_ALIASES.items():
        if normalize_text(alias_key).lower() == norm.lower():
            return (canonical_val, 1.0)
        if strip_accents(normalize_text(alias_key).lower()) == strip_accents(norm.lower()):
            return (canonical_val, 0.98)
    # Camada 1+: match fuzzy contra lista completa (canônicos + legados)
    return fuzzy_match(original, ALL_PRODUTOS, threshold=0.80)

def fuzzy_match_eixo(original: str) -> Tuple[str, float]:
    """Match eixo com: aliases legados → canônicos → fuzzy."""
    if not original:
        return ("", 0.0)
    norm = normalize_text(original)
    # Camada 0: alias legado (eixos EGD 2020-2022 → EFGD 2024)
    for alias_key, canonical_val in EIXO_ALIASES.items():
        if normalize_text(alias_key).lower() == norm.lower():
            return (canonical_val, 0.95)
        if strip_accents(normalize_text(alias_key).lower()) == strip_accents(norm.lower()):
            return (canonical_val, 0.93)
    return fuzzy_match(original, CANONICAL_EIXOS, threshold=0.80)

def classify_match(original: str, score: float, alias_map: Optional[dict] = None,
                   fuzzy_high_cut: float = 0.85, fuzzy_low_cut: float = 0.70) -> str:
    """Classifica o resultado de um fuzzy_match em 5 buckets fixos.

    Sempre retorna um dos 5 valores; nunca cresce em cardinalidade.
    Usado para popular RiskEntry.*_method e DeliveryEntry.*_method.

    `alias_map` pode ter keys de duas formas:
    - normalizadas (lowercase + sem accent) — caso de PROBABILIDADE_ALIASES,
      IMPACTO_ALIASES, TRATAMENTO_ALIASES.
    - preservando case+accent — caso de PRODUTO_ALIASES, EIXO_ALIASES.

    Para detectar 'alias' nos dois casos, normaliza-se cada key também.
    Cacheia o set normalizado por id(alias_map) para amortizar custo entre
    chamadas (alias_maps são módulo-level, vivem o run inteiro).
    """
    if not original or score <= 0.0:
        return "unmatched"
    if score >= 0.999:
        return "exact"
    if alias_map:
        norm = strip_accents(normalize_text(original).lower().strip())
        cache_key = id(alias_map)
        if cache_key not in _ALIAS_KEY_NORM_CACHE:
            _ALIAS_KEY_NORM_CACHE[cache_key] = {
                strip_accents(normalize_text(k).lower().strip()) for k in alias_map
            }
        if norm in _ALIAS_KEY_NORM_CACHE[cache_key]:
            return "alias"
    if score >= fuzzy_high_cut:
        return "fuzzy_high"
    if score >= fuzzy_low_cut:
        return "fuzzy_low"
    return "unmatched"


# Cache de keys normalizadas dos alias_maps. Populado lazily em classify_match.
# As keys do dict são id(alias_map); values são set[str] de keys normalizadas.
_ALIAS_KEY_NORM_CACHE: Dict[int, set] = {}


def fuzzy_match_scale(original: str, scale: list) -> Tuple[str, float]:
    """Canoniza valores de escala (probabilidade/impacto/tratamento) com
    suporte a escalas alternativas usadas por alguns órgãos (ANTAQ 3-pontos,
    SUSEP numérica, CADE mista). Aliases têm prioridade sobre fuzzy match."""
    if not original:
        return ("", 0.0)
    norm = strip_accents(normalize_text(original).lower().strip())
    if scale is PROBABILIDADE_SCALE and norm in PROBABILIDADE_ALIASES:
        return (PROBABILIDADE_ALIASES[norm], 0.95)
    if scale is IMPACTO_SCALE and norm in IMPACTO_ALIASES:
        return (IMPACTO_ALIASES[norm], 0.95)
    if scale is TRATAMENTO_OPTIONS and norm in TRATAMENTO_ALIASES:
        return (TRATAMENTO_ALIASES[norm], 0.95)
    return fuzzy_match(original, scale, threshold=0.70)

# --------------- Parse de datas variadas --------------------
_DATE_PATTERNS = [
    (r"(\d{2})/(\d{2})/(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
    (r"(\d{2})/(\d{4})",          lambda m: f"{m.group(2)}-{m.group(1)}"),
    (r"(\d{4})-(\d{2})-(\d{2})",  lambda m: m.group(0)),
]
_MONTH_MAP = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04",
    "mai": "05", "jun": "06", "jul": "07", "ago": "08",
    "set": "09", "out": "10", "nov": "11", "dez": "12",
}

def parse_date(text: str) -> Optional[str]:
    """Converte formatos variados para YYYY-MM ou YYYY-MM-DD."""
    if not text:
        return None
    text = normalize_text(text).strip()
    for pat, fmt in _DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            return fmt(m)
    # Formato "jun/25", "mar/2026"
    m = re.match(r"([a-záéíóú]{3})[\./\-](\d{2,4})", text.lower())
    if m:
        month = _MONTH_MAP.get(m.group(1)[:3])
        year = m.group(2)
        if len(year) == 2:
            year = "20" + year
        if month:
            return f"{year}-{month}"
    return text   # retorna original se não parsear

# --------------- Checkpoint / Resume ------------------------
# Fingerprint sidecar: detecta quando o estado upstream mudou (ex: 05c_dedup.py
# zerou pdf_path de N órgãos) e invalida automaticamente o pickle, em vez de
# carregar dados estagnados que não refletem o pipeline atual.

def state_fingerprint(state: Any) -> str:
    """SHA-1 truncado de uma representação estável de `state`. Use uma estrutura
    pequena e ordenada (ex: lista de tuplas) para que o fingerprint seja
    determinístico entre runs."""
    import hashlib
    payload = repr(state).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]

def save_checkpoint(data: Any, name: str, fingerprint: Optional[str] = None) -> None:
    pkl_path = os.path.join(DIRS["checkpoints"], f"{name}.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump(data, f)
    if fingerprint:
        fp_path = os.path.join(DIRS["checkpoints"], f"{name}.fingerprint")
        with open(fp_path, "w") as f:
            f.write(fingerprint)
    print(f"  Checkpoint salvo: {name}" + (f" [fp={fingerprint}]" if fingerprint else ""))

def load_checkpoint(name: str, expected_fingerprint: Optional[str] = None) -> Optional[Any]:
    pkl_path = os.path.join(DIRS["checkpoints"], f"{name}.pkl")
    fp_path = os.path.join(DIRS["checkpoints"], f"{name}.fingerprint")
    if not os.path.exists(pkl_path):
        return None
    if expected_fingerprint is not None:
        actual = ""
        if os.path.exists(fp_path):
            with open(fp_path) as f:
                actual = f.read().strip()
        if actual != expected_fingerprint:
            print(f"  Checkpoint {name}: fingerprint divergente "
                  f"({actual or 'ausente'} != {expected_fingerprint}) — invalidando")
            try:
                os.remove(pkl_path)
                if os.path.exists(fp_path):
                    os.remove(fp_path)
            except OSError:
                pass
            return None
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
    print(f"  Checkpoint carregado: {name}")
    return data

# --------------- Logging ------------------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ptd_scraper")

print("Funções utilitárias carregadas.")