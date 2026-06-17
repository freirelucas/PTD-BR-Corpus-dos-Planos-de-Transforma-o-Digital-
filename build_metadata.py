#!/usr/bin/env python3
"""Gera artefatos de metadados em padrões abertos a partir de output/.

Produz, de forma reprodutível, descritores que tornam o corpus PTD
auto-descritivo, validável e descobrível — sem alterar o formato dos dados:

  - output/datapackage.json                         Frictionless Data Package + Table Schema
  - output/metadata/schema_org_dataset.jsonld       schema.org/Dataset (Google Dataset Search)
  - output/metadata/dcat.jsonld                      DCAT-AP + tema VCGE (dados.gov.br)
  - output/metadata/vocabulary.skos.jsonld           SKOS ConceptScheme (escalas/produtos canônicos)
  - output/metadata/schemas/*.schema.json            JSON Schema (contrato dos *.json)
  - output/metadata/prov.jsonld                      W3C PROV-O (linhagem do pipeline)
  - output/metadata/ckan_package.json                payload p/ publicação no dados.gov.br (CKAN)

Fontes da verdade (DRY — nada é hardcoded em duplicidade):
  - CITATION.cff          autoria, licença, versão, keywords, abstract
  - output/manifest.json  proveniência: commit, data, sha256 e bytes por arquivo
  - output/*.csv          nomes de coluna (schema)
  - output/vocabulary_mapping.csv  rótulos canônicos (prefLabel) + variantes (altLabel)

Uso:
  python build_metadata.py            # gera os artefatos em output/
  python build_metadata.py --check    # falha se artefatos commitados estão defasados
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import OrderedDict

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
META_DIR = os.path.join(OUTPUT_DIR, "metadata")
SCHEMAS_DIR = os.path.join(META_DIR, "schemas")
CITATION = os.path.join(REPO_ROOT, "CITATION.cff")
MANIFEST = os.path.join(OUTPUT_DIR, "manifest.json")

# Base de URI estável para os recursos/vocabulário publicados via GitHub Pages.
BASE = "https://freirelucas.github.io/PTD"
PORTAL_SGD = ("https://www.gov.br/governodigital/pt-br/estrategias-e-governanca-digital/"
              "planos-de-transformacao-digital")

# --- Vocabulário canônico (definido pela SGD; escalas são ORDINAIS) ----------
# Mantido aqui como fonte autoritativa da ordem; os rótulos/variantes vêm de
# vocabulary_mapping.csv. Espelha notebook_cells/02_config.py.
EIXOS = [
    "Serviços Digitais e Melhoria da Qualidade",
    "Unificação de Canais Digitais",
    "Governança e Gestão de Dados",
    "Segurança e Privacidade",
    "Projetos Especiais",
]
PROBABILIDADE = ["raro", "pouco provável", "provável", "muito provável", "praticamente certo"]
IMPACTO = ["muito baixo", "baixo", "médio", "alto", "muito alto"]
TRATAMENTO = ["mitigar", "eliminar", "transferir", "aceitar"]
METHODS = ["exact", "alias", "fuzzy_high", "fuzzy_low", "unmatched"]
CONFIDENCE = ["high", "medium", "low"]
TABELA_TIPO = ["pactuada", "concluida", "cancelada"]

# Temas VCGE (Vocabulário Controlado do Governo Eletrônico) — URIs reais.
VCGE = "http://vocab.e.gov.br/id/governo"
VCGE_THEMES = [
    (f"{VCGE}#administracao", "Administração"),
    (f"{VCGE}#servicos-publicos", "Serviços Públicos"),
    (f"{VCGE}#pesquisa-e-desenvolvimento", "Pesquisa e Desenvolvimento"),
]


# =============================================================================
# Modelo de campo: declarado uma vez, derivado para Table Schema E JSON Schema.
# =============================================================================
def f(name, type, title, desc, *, required=False, enum=None,
      fmt=None, minimum=None, maximum=None):
    return dict(name=name, type=type, title=title, description=desc,
                required=required, enum=enum, format=fmt,
                minimum=minimum, maximum=maximum)


def _score(name, title):
    return f(name, "number", title, "Confiança 0–1 do casamento contra o vocabulário canônico.",
             minimum=0.0, maximum=1.0)


def _method(name, title):
    return f(name, "string", title, "Estratégia de casamento aplicada.", enum=METHODS)


# Campos compartilhados por linha (CSV) e por entry (JSON), na mesma ordem.
ORGANS_FIELDS = [
    f("sigla", "string", "Sigla", "Sigla do órgão signatário (chave primária).", required=True),
    f("nome_completo", "string", "Nome completo", "Título do PTD / nome do órgão."),
    f("grupo", "string", "Grupo", "Grupo de órgãos que compartilham um mesmo PTD, se houver."),
    f("url_diretivo", "string", "URL do documento diretivo", "URL do PDF diretivo no portal SGD.", fmt="uri"),
    f("url_entregas", "string", "URL do anexo de entregas", "URL do PDF de entregas no portal SGD.", fmt="uri"),
    f("pdf_path_diretivo", "string", "Caminho local (diretivo)", "Caminho do PDF diretivo baixado."),
    f("pdf_path_entregas", "string", "Caminho local (entregas)", "Caminho do PDF de entregas baixado."),
]

RISKS_FIELDS = [
    f("orgao_sigla", "string", "Órgão", "Sigla do órgão (chave estrangeira → organs.sigla).", required=True),
    f("risco_texto", "string", "Descrição do risco", "Texto do evento de risco extraído da tabela diretiva."),
    f("probabilidade_original", "string", "Probabilidade (original)", "Valor de probabilidade como extraído do PDF."),
    # Sem enum rígido: linhas com needs_review=True podem carregar texto bruto
    # não corrigido (column-bleed). A escala canônica é documentada aqui e
    # publicada como SKOS; o contrato vale para o subconjunto needs_review=False.
    f("probabilidade_normalizada", "string", "Probabilidade (canônica)",
      "Probabilidade na escala ordinal SGD: " + " < ".join(PROBABILIDADE)
      + ". Linhas com needs_review=True podem conter texto não canônico."),
    _score("probabilidade_score", "Score da probabilidade"),
    _method("probabilidade_method", "Método (probabilidade)"),
    f("impacto_original", "string", "Impacto (original)", "Valor de impacto como extraído do PDF."),
    f("impacto_normalizado", "string", "Impacto (canônico)",
      "Impacto na escala ordinal SGD: " + " < ".join(IMPACTO)
      + ". Linhas com needs_review=True podem conter texto não canônico."),
    _score("impacto_score", "Score do impacto"),
    _method("impacto_method", "Método (impacto)"),
    f("tratamento_original", "string", "Tratamento (original)", "Opção de tratamento como extraída do PDF."),
    f("tratamento_normalizado", "string", "Tratamento (canônico)",
      "Opção de tratamento canônica (" + ", ".join(TRATAMENTO)
      + "). Linhas com needs_review=True podem conter texto não canônico."),
    _score("tratamento_score", "Score do tratamento"),
    _method("tratamento_method", "Método (tratamento)"),
    f("acoes_tratamento", "string", "Ações de tratamento", "Ações de tratamento (texto livre ou referências resolvidas)."),
    f("extraction_confidence", "string", "Confiança da extração", "Confiança qualitativa da linha.", enum=CONFIDENCE),
    f("needs_review", "boolean", "Requer revisão", "Sinaliza linha para a fila de revisão humana."),
    f("review_reason", "string", "Motivo da revisão", "Razão pela qual a linha foi sinalizada."),
]

DELIVERIES_FIELDS = [
    f("orgao_sigla", "string", "Órgão", "Sigla do órgão (chave estrangeira → organs.sigla).", required=True),
    f("tabela_tipo", "string", "Tipo de tabela", "Origem estrutural da entrega.", enum=TABELA_TIPO),
    f("servico_acao", "string", "Serviço/Ação", "Serviço ou ação associada à entrega."),
    f("produto_original", "string", "Produto (original)", "Produto como extraído do PDF."),
    f("produto_normalizado", "string", "Produto (canônico)", "Produto canônico SGD, ou 'Outros'.", enum=None),
    _score("produto_score", "Score do produto"),
    _method("produto_method", "Método (produto)"),
    f("eixo_original", "string", "Eixo (original)", "Eixo como extraído do PDF."),
    f("eixo_normalizado", "string", "Eixo (canônico)", "Eixo canônico da EFGD.", enum=EIXOS),
    _score("eixo_score", "Score do eixo"),
    _method("eixo_method", "Método (eixo)"),
    f("area_responsavel", "string", "Área responsável", "Área/unidade responsável pela entrega."),
    f("data_pactuada", "string", "Data pactuada", "Prazo pactuado (formato heterogêneo; ver _parse_year_month)."),
    f("data_entrega", "string", "Data de entrega", "Data de conclusão, quando disponível."),
    f("pactuado", "string", "Pactuado", "Marcador de pactuação, quando presente no template."),
    f("justificativa", "string", "Justificativa", "Justificativa (cancelamento ou produto 'Outros')."),
    f("extraction_confidence", "string", "Confiança da extração", "Confiança qualitativa da linha.", enum=CONFIDENCE),
    f("needs_review", "boolean", "Requer revisão", "Sinaliza linha para a fila de revisão humana."),
    f("review_reason", "string", "Motivo da revisão", "Razão pela qual a linha foi sinalizada."),
]

# Recurso → (caminho relativo, título, descrição, campos, chave primária, FKs)
RESOURCES = OrderedDict([
    ("organs", dict(path="organs.csv", title="Órgãos signatários",
                    desc="Um registro por órgão signatário de PTD, com URLs dos PDFs de origem.",
                    fields=ORGANS_FIELDS, primaryKey="sigla", foreignKeys=[])),
    ("risks", dict(path="risks.csv", title="Riscos (tabelas diretivas)",
                   desc="Riscos de gestão extraídos das tabelas diretivas, normalizados contra as escalas SGD.",
                   fields=RISKS_FIELDS, primaryKey=None,
                   foreignKeys=[("orgao_sigla", "organs", "sigla")])),
    ("deliveries", dict(path="deliveries.csv", title="Entregas pactuadas",
                        desc="Entregas pactuadas/concluídas extraídas dos anexos, com produto e eixo canônicos.",
                        fields=DELIVERIES_FIELDS, primaryKey=None,
                        foreignKeys=[("orgao_sigla", "organs", "sigla")])),
])

# Recursos tabulares auxiliares (schema leve, derivado do header do CSV).
AUX_CSV = ["coverage_summary.csv", "pdf_metadata.csv", "vocabulary_mapping.csv", "error_report.csv"]


# =============================================================================
# Conversores do modelo de campo
# =============================================================================
def to_frictionless_field(fld):
    out = {"name": fld["name"], "type": fld["type"],
           "title": fld["title"], "description": fld["description"]}
    if fld.get("format"):
        out["format"] = fld["format"]
    constraints = {}
    if fld.get("required"):
        constraints["required"] = True
    if fld.get("enum"):
        constraints["enum"] = list(fld["enum"])
    if fld.get("minimum") is not None:
        constraints["minimum"] = fld["minimum"]
    if fld.get("maximum") is not None:
        constraints["maximum"] = fld["maximum"]
    if constraints:
        out["constraints"] = constraints
    return out


def to_jsonschema_prop(fld):
    jstype = {"string": "string", "number": "number", "boolean": "boolean",
              "integer": "integer"}[fld["type"]]
    # Campos não-obrigatórios podem vir nulos no JSON aninhado.
    prop = {"type": [jstype, "null"] if not fld.get("required") else jstype,
            "title": fld["title"], "description": fld["description"]}
    if fld.get("enum"):
        prop["enum"] = list(fld["enum"]) + ([None] if not fld.get("required") else [])
    if fld.get("minimum") is not None:
        prop["minimum"] = fld["minimum"]
    if fld.get("maximum") is not None:
        prop["maximum"] = fld["maximum"]
    if fld.get("format") == "uri":
        prop["format"] = "uri"
    return prop


# =============================================================================
# Leitura das fontes da verdade
# =============================================================================
def load_citation(path=CITATION):
    """Lê CITATION.cff. Usa PyYAML se disponível; senão um parser mínimo."""
    try:
        import yaml
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception:  # pragma: no cover - fallback defensivo
        return _minimal_cff(path)


def _minimal_cff(path):  # pragma: no cover
    data, authors = {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(("title:", "abstract:", "license:", "version:",
                                "url:", "date-released:")):
                k, _, v = line.partition(":")
                data[k.strip()] = v.strip().strip('"').strip()
    data.setdefault("authors", authors)
    return data


def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def csv_header(filename):
    with open(os.path.join(OUTPUT_DIR, filename), encoding="utf-8-sig") as fh:
        return next(csv.reader(fh))


def read_vocabulary(path=os.path.join(OUTPUT_DIR, "vocabulary_mapping.csv")):
    """Agrupa vocabulary_mapping.csv por (type, normalized) → {variantes, count}."""
    grouped = OrderedDict()
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            norm = (row.get("normalized") or "").strip()
            typ = (row.get("type") or "").strip()
            orig = (row.get("original") or "").strip()
            if not norm or not typ:
                continue
            key = (typ, norm)
            entry = grouped.setdefault(key, {"variants": set(), "count": 0})
            if orig and orig != norm:
                entry["variants"].add(orig)
            try:
                entry["count"] += int(float(row.get("count") or 0))
            except ValueError:
                pass
    return grouped


def _authors(citation):
    out = []
    for a in citation.get("authors", []) or []:
        given, family = a.get("given-names", ""), a.get("family-names", "")
        name = " ".join(p for p in (given, family) if p).strip()
        if name:
            out.append({"name": name, "affiliation": a.get("affiliation", "")})
    return out


# =============================================================================
# Builders
# =============================================================================
def build_datapackage(citation, manifest):
    def resource(name, meta):
        rel = meta["path"]
        m = manifest.get("outputs", {}).get(rel, {})
        schema = {"fields": [to_frictionless_field(x) for x in meta["fields"]]}
        if meta.get("primaryKey"):
            schema["primaryKey"] = meta["primaryKey"]
        if meta.get("foreignKeys"):
            schema["foreignKeys"] = [
                {"fields": fk[0],
                 "reference": {"resource": fk[1], "fields": fk[2]}}
                for fk in meta["foreignKeys"]
            ]
        res = {"name": name, "path": rel, "title": meta["title"],
               "description": meta["desc"], "format": "csv",
               "mediatype": "text/csv", "encoding": "utf-8", "schema": schema}
        if m.get("bytes"):
            res["bytes"] = m["bytes"]
        if m.get("sha256"):
            res["hash"] = f"sha256:{m['sha256']}"
        return res

    # Frictionless exige `created` em datetime RFC3339; data-only não basta.
    created = str(citation.get("date-released", "")).strip()
    if len(created) == 10:  # 'YYYY-MM-DD'
        created = f"{created}T00:00:00Z"

    resources = [resource(n, m) for n, m in RESOURCES.items()]
    # Recursos auxiliares: schema raso (apenas nomes de coluna).
    for fn in AUX_CSV:
        m = manifest.get("outputs", {}).get(fn, {})
        try:
            header = csv_header(fn)
        except FileNotFoundError:
            continue
        res = {"name": fn.replace(".csv", ""), "path": fn,
               "format": "csv", "mediatype": "text/csv", "encoding": "utf-8",
               "schema": {"fields": [{"name": h, "type": "string"} for h in header]}}
        if m.get("bytes"):
            res["bytes"] = m["bytes"]
        if m.get("sha256"):
            res["hash"] = f"sha256:{m['sha256']}"
        resources.append(res)

    return {
        "name": "ptd-corpus",
        "title": citation.get("title", "PTD — Corpus"),
        "description": " ".join(str(citation.get("abstract", "")).split()),
        "version": str(citation.get("version", "")),
        "created": created,
        "homepage": citation.get("url", BASE),
        "licenses": [{
            "name": "CC-BY-4.0",
            "title": "Creative Commons Attribution 4.0 International",
            "path": "https://creativecommons.org/licenses/by/4.0/",
        }],
        "keywords": citation.get("keywords", []),
        "contributors": [{"title": a["name"], "organization": a["affiliation"],
                          "role": "author"} for a in _authors(citation)],
        "sources": [{"title": "Portal SGD/MGI — Planos de Transformação Digital",
                     "path": PORTAL_SGD}],
        "resources": resources,
    }


def build_schema_org(citation, manifest):
    distribution = []
    for rel, m in manifest.get("outputs", {}).items():
        if not rel.endswith((".csv", ".json")):
            continue
        fmt = "text/csv" if rel.endswith(".csv") else "application/json"
        dist = {"@type": "DataDownload", "encodingFormat": fmt,
                "contentUrl": f"{BASE}/output/{rel}"}
        if m.get("sha256"):
            dist["sha256"] = m["sha256"]
        distribution.append(dist)

    return {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "name": citation.get("title", "PTD — Corpus"),
        "description": " ".join(str(citation.get("abstract", "")).split()),
        "url": citation.get("url", BASE),
        "sameAs": citation.get("repository-code", ""),
        "version": str(citation.get("version", "")),
        "datePublished": str(citation.get("date-released", "")),
        "inLanguage": "pt-BR",
        "isAccessibleForFree": True,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "keywords": citation.get("keywords", []),
        "creator": [{"@type": "Person", "name": a["name"],
                     "affiliation": {"@type": "Organization", "name": a["affiliation"]}}
                    for a in _authors(citation)],
        "publisher": {"@type": "Organization",
                      "name": "Instituto de Pesquisa Econômica Aplicada (Ipea)"},
        "creativeWorkStatus": "Versão preliminar",
        "about": [{"@type": "Thing", "name": label, "@id": uri}
                  for uri, label in VCGE_THEMES],
        "isBasedOn": PORTAL_SGD,
        "distribution": distribution,
    }


def build_dcat(citation, manifest):
    distributions = []
    for rel, m in manifest.get("outputs", {}).items():
        if not rel.endswith((".csv", ".json")):
            continue
        fmt = "CSV" if rel.endswith(".csv") else "JSON"
        media = "text/csv" if rel.endswith(".csv") else "application/json"
        d = {"@type": "dcat:Distribution",
             "dcat:downloadURL": {"@id": f"{BASE}/output/{rel}"},
             "dcat:mediaType": media, "dct:format": fmt,
             "dct:license": {"@id": "https://creativecommons.org/licenses/by/4.0/"}}
        if m.get("sha256"):
            d["spdx:checksum"] = {"@type": "spdx:Checksum",
                                  "spdx:algorithm": "spdx:checksumAlgorithm_sha256",
                                  "spdx:checksumValue": m["sha256"]}
        distributions.append(d)

    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "foaf": "http://xmlns.com/foaf/0.1/",
            "spdx": "http://spdx.org/rdf/terms#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
        },
        "@type": "dcat:Dataset",
        "@id": citation.get("url", BASE),
        "dct:title": citation.get("title", "PTD — Corpus"),
        "dct:description": " ".join(str(citation.get("abstract", "")).split()),
        "dct:issued": str(citation.get("date-released", "")),
        "dct:modified": manifest.get("data_execucao", ""),
        "dcat:version": str(citation.get("version", "")),
        "dct:language": "pt-BR",
        "dct:accrualPeriodicity": "http://purl.org/cld/freq/irregular",
        "dct:license": {"@id": "https://creativecommons.org/licenses/by/4.0/"},
        "dcat:keyword": citation.get("keywords", []),
        "dcat:theme": [{"@id": uri, "skos:prefLabel": label} for uri, label in VCGE_THEMES],
        "dct:publisher": {"@type": "foaf:Organization",
                          "foaf:name": "Instituto de Pesquisa Econômica Aplicada (Ipea)"},
        "dct:creator": [{"@type": "foaf:Person", "foaf:name": a["name"]}
                        for a in _authors(citation)],
        "dct:provenance": {
            "@type": "dct:ProvenanceStatement",
            "rdfs:label": (f"Extraído automaticamente dos PTDs publicados no portal SGD/MGI "
                           f"via pipeline PyMuPDF (commit {manifest.get('pipeline_commit','')[:10]}), "
                           f"execução de {manifest.get('data_execucao','')}."),
        },
        "dct:source": {"@id": PORTAL_SGD},
        "dcat:distribution": distributions,
    }


def build_skos(vocab):
    scheme_id = f"{BASE}/vocab"
    type_meta = {
        "eixo": ("Eixos da EFGD", EIXOS),
        "produto": ("Produtos canônicos SGD", None),
        "probabilidade": ("Escala de probabilidade", PROBABILIDADE),
        "impacto": ("Escala de impacto", IMPACTO),
        "tratamento": ("Opções de tratamento de risco", TRATAMENTO),
    }
    concepts = []
    schemes = []
    for typ, (label, order) in type_meta.items():
        sid = f"{scheme_id}/{typ}"
        schemes.append({"@id": sid, "@type": "skos:ConceptScheme",
                        "skos:prefLabel": {"@language": "pt", "@value": label}})
        # Coleta termos canônicos deste tipo, na ordem definida quando ordinal.
        terms = OrderedDict()
        for (t, norm), info in vocab.items():
            if t == typ:
                terms.setdefault(norm, info)
        ordered = order if order else sorted(terms)
        # Garante presença mesmo de canônicos sem variantes registradas.
        for norm in ordered:
            terms.setdefault(norm, {"variants": set(), "count": 0})
        for idx, norm in enumerate([n for n in ordered if n in terms]):
            info = terms[norm]
            slug = norm.lower().replace(" ", "-").replace("/", "-")
            concept = {
                "@id": f"{sid}#{slug}",
                "@type": "skos:Concept",
                "skos:inScheme": {"@id": sid},
                "skos:prefLabel": {"@language": "pt", "@value": norm},
            }
            if order:  # escala ordinal → notação posicional
                concept["skos:notation"] = idx + 1
            alts = sorted(info["variants"])
            if alts:
                concept["skos:altLabel"] = [{"@language": "pt", "@value": a} for a in alts]
            concepts.append(concept)

    return {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@graph": [
            {"@id": scheme_id, "@type": "skos:ConceptScheme",
             "skos:prefLabel": {"@language": "pt",
                                "@value": "Vocabulário canônico do corpus PTD"},
             "dct:license": {"@id": "https://creativecommons.org/licenses/by/4.0/"},
             "skos:hasTopConcept": [{"@id": s["@id"]} for s in schemes]},
            *schemes,
            *concepts,
        ],
    }


def _json_schema_for(name, meta):
    """JSON Schema (draft 2020-12) p/ um arquivo {metadata, data:{grupo:[entry]}}."""
    props = {fld["name"]: to_jsonschema_prop(fld) for fld in meta["fields"]}
    required = [fld["name"] for fld in meta["fields"] if fld.get("required")]
    entry = {"type": "object", "properties": props, "required": required,
             "additionalProperties": False}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE}/output/metadata/schemas/{name}.schema.json",
        "title": f"PTD — {meta['title']}",
        "description": meta["desc"],
        "type": "object",
        "required": ["metadata", "data"],
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "exported_at": {"type": "string"},
                    "total": {"type": "integer", "minimum": 0},
                    "groups": {"type": "integer", "minimum": 0},
                },
                "required": ["total"],
            },
            "data": {
                "type": "object",
                "description": "Entries agrupadas por sigla de órgão.",
                "additionalProperties": {"type": "array", "items": entry},
            },
        },
    }


def build_json_schemas():
    return {
        "risks": _json_schema_for("risks", RESOURCES["risks"]),
        "deliveries": _json_schema_for("deliveries", RESOURCES["deliveries"]),
    }


def build_prov(citation, manifest):
    pipeline = {"@id": f"{BASE}#pipeline",
                "@type": "prov:SoftwareAgent",
                "prov:label": "Pipeline de extração PTD (PyMuPDF)",
                "rdfs:seeAlso": {"@id": citation.get("repository-code", BASE)}}
    portal = {"@id": PORTAL_SGD, "@type": "prov:Entity",
              "prov:label": "PTDs publicados no portal SGD/MGI"}
    activity = {
        "@id": f"{BASE}#execucao-{manifest.get('data_execucao','')}",
        "@type": "prov:Activity",
        "prov:label": "Extração, padronização e exportação do corpus",
        "prov:endedAtTime": manifest.get("data_execucao", ""),
        "prov:wasAssociatedWith": {"@id": f"{BASE}#pipeline"},
        "prov:used": {"@id": PORTAL_SGD},
        "ptd:commit": manifest.get("pipeline_commit", ""),
    }
    entities = []
    for rel, m in manifest.get("outputs", {}).items():
        e = {"@id": f"{BASE}/output/{rel}", "@type": "prov:Entity",
             "prov:label": rel,
             "prov:wasGeneratedBy": {"@id": activity["@id"]},
             "prov:wasDerivedFrom": {"@id": PORTAL_SGD}}
        if m.get("sha256"):
            e["ptd:sha256"] = m["sha256"]
        entities.append(e)
    return {
        "@context": {
            "prov": "http://www.w3.org/ns/prov#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "ptd": f"{BASE}#",
        },
        "@graph": [pipeline, portal, activity, *entities],
    }


def build_ckan_package(citation, manifest):
    """Payload para POST em package_create do CKAN (dados.gov.br).

    NÃO publica — apenas materializa o corpo da requisição. A publicação exige
    credenciais e autorização institucional (ver METADATA.md).
    """
    resources = []
    for rel, m in manifest.get("outputs", {}).items():
        if not rel.endswith((".csv", ".json")):
            continue
        resources.append({
            "name": rel,
            "url": f"{BASE}/output/{rel}",
            "format": "CSV" if rel.endswith(".csv") else "JSON",
            "mimetype": "text/csv" if rel.endswith(".csv") else "application/json",
            "hash": f"sha256:{m['sha256']}" if m.get("sha256") else "",
            "size": m.get("bytes", 0),
        })
    return {
        "name": "corpus-ptd-planos-transformacao-digital",
        "title": citation.get("title", "PTD — Corpus"),
        "notes": " ".join(str(citation.get("abstract", "")).split()),
        "owner_org": "ipea",  # ajustar para o slug real da organização no portal
        "license_id": "cc-by",
        "url": citation.get("url", BASE),
        "version": str(citation.get("version", "")),
        "tags": [{"name": k} for k in citation.get("keywords", [])],
        "extras": [
            {"key": "tema_vcge", "value": "; ".join(l for _, l in VCGE_THEMES)},
            {"key": "fonte", "value": PORTAL_SGD},
            {"key": "pipeline_commit", "value": manifest.get("pipeline_commit", "")},
            {"key": "data_execucao", "value": manifest.get("data_execucao", "")},
            {"key": "frequencia_atualizacao", "value": "irregular"},
        ],
        "resources": resources,
    }


# =============================================================================
# index.html: injeção idempotente do bloco schema.org
# =============================================================================
BEGIN_MARK = "<!-- BEGIN schema.org JSON-LD (gerado por build_metadata.py) -->"
END_MARK = "<!-- END schema.org JSON-LD -->"


def inject_schema_org(html, schema_org):
    # Bloco sem indentação à esquerda → re-injeção estável (idempotente).
    block = (f"{BEGIN_MARK}\n"
             f'<script type="application/ld+json">\n'
             f"{json.dumps(schema_org, ensure_ascii=False, indent=2)}\n"
             f"</script>\n"
             f"{END_MARK}")
    if BEGIN_MARK in html and END_MARK in html:
        # Recorta da quebra de linha que precede BEGIN até o fim de END,
        # descartando a indentação antiga (que senão cresceria a cada rodada).
        start = html.rfind("\n", 0, html.index(BEGIN_MARK)) + 1
        end = html.index(END_MARK) + len(END_MARK)
        return html[:start] + block + html[end:]
    # Primeira injeção: imediatamente antes de </head>.
    return html.replace("</head>", block + "\n</head>", 1)


# =============================================================================
# Escrita / consistência
# =============================================================================
def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def generate():
    """Constrói todos os artefatos em memória. Retorna {caminho_relativo: conteúdo}."""
    citation = load_citation()
    manifest = load_manifest()
    vocab = read_vocabulary()

    artifacts = {
        "output/datapackage.json": _dump(build_datapackage(citation, manifest)),
        "output/metadata/schema_org_dataset.jsonld": _dump(build_schema_org(citation, manifest)),
        "output/metadata/dcat.jsonld": _dump(build_dcat(citation, manifest)),
        "output/metadata/vocabulary.skos.jsonld": _dump(build_skos(vocab)),
        "output/metadata/prov.jsonld": _dump(build_prov(citation, manifest)),
        "output/metadata/ckan_package.json": _dump(build_ckan_package(citation, manifest)),
    }
    for name, schema in build_json_schemas().items():
        artifacts[f"output/metadata/schemas/{name}.schema.json"] = _dump(schema)

    return artifacts


def write(artifacts):
    os.makedirs(SCHEMAS_DIR, exist_ok=True)
    for rel, content in artifacts.items():
        path = os.path.join(REPO_ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def check(artifacts):
    """Retorna lista de caminhos defasados (conteúdo difere do commitado)."""
    stale = []
    for rel, content in artifacts.items():
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            stale.append(rel)
            continue
        with open(path, encoding="utf-8") as fh:
            if fh.read() != content:
                stale.append(rel)
    return stale


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="Falha se os artefatos commitados estão defasados.")
    args = ap.parse_args(argv)

    artifacts = generate()
    if args.check:
        stale = check(artifacts)
        if stale:
            print("Artefatos de metadados defasados (rode `python build_metadata.py`):")
            for s in stale:
                print(f"  - {s}")
            return 1
        print(f"OK — {len(artifacts)} artefatos de metadados em dia.")
        return 0

    write(artifacts)
    print(f"Gerados {len(artifacts)} artefatos de metadados:")
    for rel in artifacts:
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
