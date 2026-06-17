"""Testes para build_metadata.py — gerador de metadados em padrões abertos.

Cobre (a) os conversores do modelo de campo para Table Schema e JSON Schema,
(b) os builders de cada artefato, (c) a injeção idempotente do schema.org no
index.html e (d) a consistência dos artefatos commitados (mesmo guard da CI).
"""
import json

import pytest

import build_metadata as bm


# ---------------------- conversores do modelo de campo ----------------------

def test_to_frictionless_field_basic():
    fld = bm.f("sigla", "string", "Sigla", "desc", required=True)
    out = bm.to_frictionless_field(fld)
    assert out["name"] == "sigla"
    assert out["type"] == "string"
    assert out["constraints"]["required"] is True


def test_to_frictionless_field_enum_and_bounds():
    fld = bm.f("s", "number", "S", "d", enum=None, minimum=0.0, maximum=1.0)
    out = bm.to_frictionless_field(fld)
    assert out["constraints"]["minimum"] == 0.0
    assert out["constraints"]["maximum"] == 1.0


def test_to_frictionless_field_uri_format():
    fld = bm.f("u", "string", "U", "d", fmt="uri")
    assert bm.to_frictionless_field(fld)["format"] == "uri"


def test_to_jsonschema_prop_nullable_for_optional():
    fld = bm.f("x", "string", "X", "d")  # não-obrigatório
    prop = bm.to_jsonschema_prop(fld)
    assert prop["type"] == ["string", "null"]


def test_to_jsonschema_prop_required_not_nullable():
    fld = bm.f("x", "string", "X", "d", required=True)
    assert bm.to_jsonschema_prop(fld)["type"] == "string"


def test_to_jsonschema_prop_enum_allows_null_when_optional():
    fld = bm.f("m", "string", "M", "d", enum=["a", "b"])
    prop = bm.to_jsonschema_prop(fld)
    assert "a" in prop["enum"] and None in prop["enum"]


# ---------------------- field specs / invariantes ----------------------

def test_score_fields_are_bounded_0_1():
    score = bm._score("produto_score", "Score")
    assert score["minimum"] == 0.0 and score["maximum"] == 1.0


def test_method_fields_use_methods_enum():
    m = bm._method("produto_method", "Método")
    assert m["enum"] == bm.METHODS


def test_orgao_sigla_is_foreign_key_in_risks_and_deliveries():
    for res in ("risks", "deliveries"):
        fks = bm.RESOURCES[res]["foreignKeys"]
        assert ("orgao_sigla", "organs", "sigla") in fks


def test_organs_primary_key_is_sigla():
    assert bm.RESOURCES["organs"]["primaryKey"] == "sigla"


def test_risk_scale_fields_have_no_hard_enum():
    # Por design: linhas needs_review podem carregar texto bruto (column-bleed).
    fields = {x["name"]: x for x in bm.RISKS_FIELDS}
    for name in ("probabilidade_normalizada", "impacto_normalizado",
                 "tratamento_normalizado"):
        assert fields[name]["enum"] is None
        # ...mas a escala canônica fica documentada na descrição.
    assert "raro" in fields["probabilidade_normalizada"]["description"]


def test_eixo_field_keeps_hard_enum():
    fields = {x["name"]: x for x in bm.DELIVERIES_FIELDS}
    assert fields["eixo_normalizado"]["enum"] == bm.EIXOS


# ---------------------- builders ----------------------

@pytest.fixture(scope="module")
def citation():
    return bm.load_citation()


@pytest.fixture(scope="module")
def manifest():
    return bm.load_manifest()


def test_authors_parsed(citation):
    names = [a["name"] for a in bm._authors(citation)]
    assert any("Silva" in n for n in names)


def test_datapackage_has_resources_with_schema(citation, manifest):
    dp = bm.build_datapackage(citation, manifest)
    names = {r["name"] for r in dp["resources"]}
    assert {"organs", "risks", "deliveries"} <= names
    risks = next(r for r in dp["resources"] if r["name"] == "risks")
    assert risks["schema"]["foreignKeys"][0]["reference"]["resource"] == "organs"


def test_datapackage_created_is_datetime(citation, manifest):
    dp = bm.build_datapackage(citation, manifest)
    # Frictionless exige RFC3339 datetime, não date-only.
    assert "T" in dp["created"]


def test_datapackage_resource_carries_sha256(citation, manifest):
    dp = bm.build_datapackage(citation, manifest)
    risks = next(r for r in dp["resources"] if r["name"] == "risks")
    assert risks["hash"].startswith("sha256:")


def test_schema_org_has_vcge_theme(citation, manifest):
    so = bm.build_schema_org(citation, manifest)
    assert so["@type"] == "Dataset"
    ids = {t["@id"] for t in so["about"]}
    assert "http://vocab.e.gov.br/id/governo#administracao" in ids


def test_schema_org_no_duplicate_status_key(citation, manifest):
    # Regressão: 'creativeWorkStatus' estava duplicado.
    so = bm.build_schema_org(citation, manifest)
    assert so["creativeWorkStatus"] == "Versão preliminar"


def test_dcat_distribution_has_checksum(citation, manifest):
    dcat = bm.build_dcat(citation, manifest)
    dists = dcat["dcat:distribution"]
    assert any("spdx:checksum" in d for d in dists)


def test_dcat_theme_uses_vcge(citation, manifest):
    dcat = bm.build_dcat(citation, manifest)
    assert all(t["@id"].startswith("http://vocab.e.gov.br") for t in dcat["dcat:theme"])


def test_skos_concepts_have_preflabel():
    vocab = bm.read_vocabulary()
    skos = bm.build_skos(vocab)
    concepts = [n for n in skos["@graph"] if n.get("@type") == "skos:Concept"]
    assert len(concepts) >= 20  # 5 eixos + 14 escalas + produtos
    assert all("skos:prefLabel" in c for c in concepts)


def test_skos_ordinal_scales_have_notation():
    vocab = bm.read_vocabulary()
    skos = bm.build_skos(vocab)
    prob = [n for n in skos["@graph"]
            if n.get("@type") == "skos:Concept" and "probabilidade" in n["@id"]]
    # Escala ordinal → skos:notation posicional 1..5.
    notations = sorted(c["skos:notation"] for c in prob)
    assert notations == [1, 2, 3, 4, 5]


def test_skos_collects_altlabels_from_variants():
    vocab = bm.read_vocabulary()
    skos = bm.build_skos(vocab)
    # Algum conceito deve ter altLabel (variantes capturadas dos PDFs).
    has_alt = any("skos:altLabel" in n for n in skos["@graph"]
                  if n.get("@type") == "skos:Concept")
    assert has_alt


def test_json_schema_targets_grouped_structure():
    schemas = bm.build_json_schemas()
    risks = schemas["risks"]
    assert risks["required"] == ["metadata", "data"]
    entry = risks["properties"]["data"]["additionalProperties"]["items"]
    assert "orgao_sigla" in entry["properties"]
    assert entry["additionalProperties"] is False


def test_prov_links_outputs_to_activity(citation, manifest):
    prov = bm.build_prov(citation, manifest)
    entities = [n for n in prov["@graph"] if n.get("@type") == "prov:Entity"
                and "wasGeneratedBy" in str(n)]
    assert entities


def test_ckan_package_uses_cc_by(citation, manifest):
    pkg = bm.build_ckan_package(citation, manifest)
    assert pkg["license_id"] == "cc-by"
    assert pkg["resources"]


# ---------------------- injeção schema.org ----------------------

def test_inject_schema_org_first_time():
    html = "<html><head>\n<title>x</title>\n</head><body></body></html>"
    out = bm.inject_schema_org(html, {"@type": "Dataset", "name": "T"})
    assert bm.BEGIN_MARK in out and bm.END_MARK in out
    assert out.count("application/ld+json") == 1


def test_inject_schema_org_idempotent():
    html = "<html><head>\n</head></html>"
    once = bm.inject_schema_org(html, {"@type": "Dataset", "name": "A"})
    twice = bm.inject_schema_org(once, {"@type": "Dataset", "name": "B"})
    assert twice.count("application/ld+json") == 1
    assert '"name": "B"' in twice and '"name": "A"' not in twice


# ---------------------- validação contra os padrões ----------------------

def test_datapackage_validates_with_frictionless():
    """O datapackage + dados conformam ao spec Frictionless (Table Schema)."""
    frictionless = pytest.importorskip("frictionless")
    import warnings
    warnings.simplefilter("ignore")
    report = frictionless.Package(bm.os.path.join(bm.OUTPUT_DIR, "datapackage.json")).validate()
    assert report.valid, report.flatten(["fieldName", "type", "note"])[:10]


@pytest.mark.parametrize("name", ["risks", "deliveries"])
def test_json_outputs_validate_against_schema(name):
    """risks.json / deliveries.json conformam ao JSON Schema gerado."""
    jsonschema = pytest.importorskip("jsonschema")
    with open(bm.os.path.join(bm.SCHEMAS_DIR, f"{name}.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    with open(bm.os.path.join(bm.OUTPUT_DIR, f"{name}.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    jsonschema.validate(data, schema)  # levanta ValidationError se inválido


# ---------------------- consistência (mesmo guard da CI) ----------------------

def test_committed_artifacts_are_in_sync():
    """Os artefatos no repo devem refletir build_metadata.py (rode-o se falhar)."""
    stale = bm.check(bm.generate())
    assert stale == [], f"Artefatos defasados: {stale}"
