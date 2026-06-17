# ============================================================
# CÉLULA 5b — Dedup por hash MD5 (PDFs compartilhados)
# ============================================================
# Órgãos que pertencem a um grupo ministerial (ORGAN_GROUPS) frequentemente
# compartilham um único PDF publicado pelo ministério. O scraping baixa uma
# cópia para cada sigla membro, mas o conteúdo é idêntico. Sem dedup, a
# extração processaria o mesmo conteúdo N vezes, gerando duplicatas.
#
# Estratégia: para cada hash MD5 distinto, manter como "owner" a sigla
# alfabeticamente menor. As demais ficam com path=None — a extração as
# ignora. A cobertura é expandida via MEMBER_TO_GROUP, marcando os
# membros não-owner como "compartilhado".
import hashlib
from collections import defaultdict


def _md5(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dedupe_by_hash(organs: List[OrganInfo], path_attr: str) -> int:
    """Para cada hash duplicado, zera path em todos exceto o sigla
    alfabético menor. Retorna número de cópias zeradas."""
    by_hash: Dict[str, List[OrganInfo]] = defaultdict(list)
    for o in organs:
        p = getattr(o, path_attr, None)
        h = _md5(p)
        if h:
            by_hash[h].append(o)
    n_dropped = 0
    for h, members in by_hash.items():
        if len(members) <= 1:
            continue
        members.sort(key=lambda o: o.sigla)
        for o in members[1:]:
            setattr(o, path_attr, None)
            n_dropped += 1
    return n_dropped


_n_dir = dedupe_by_hash(all_organs, "pdf_path_diretivo")
_n_ent = dedupe_by_hash(all_organs, "pdf_path_entregas")

print(f"\n{'='*50}")
print(f"Dedup por hash MD5")
print(f"  PDFs diretivo descartados (cópias):  {_n_dir}")
print(f"  PDFs entregas descartados (cópias):  {_n_ent}")
print(f"  Owners únicos diretivo: {sum(1 for o in all_organs if o.pdf_path_diretivo)}")
print(f"  Owners únicos entregas: {sum(1 for o in all_organs if o.pdf_path_entregas)}")
print(f"{'='*50}")
