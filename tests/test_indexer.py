"""Vérifie le schéma et les documents envoyés, sans appel à Azure."""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from indexer import definir_index, lots, titre_citation, vers_document  # noqa: E402

JEU = RACINE / "data" / "questions_reference.json"
CHUNKS = RACINE / "data" / "chunks.jsonl"


def lire_chunks():
    with CHUNKS.open(encoding="utf-8") as fichier:
        return [json.loads(ligne) for ligne in fichier]


def test_schema_compatible_avec_l_outil_des_agents():
    champs = {c.name: c for c in definir_index("test").fields}
    assert champs["id"].key
    assert champs["content"].searchable and champs["content"].retrievable
    assert champs["title"].retrievable and champs["url"].retrievable
    assert champs["content_vector"].vector_search_dimensions == 1536


def test_document_complet_et_lien_vers_la_bonne_page():
    chunk = next(c for c in lire_chunks() if c["id"] == "31-08_art-103_p1")
    document = vers_document(chunk, [0.0] * 1536, "https://exemple/lois/")
    assert document["title"] == "Loi n° 31-08, Article 103"
    assert document["url"] == "https://exemple/lois/loi-31-08-protection-consommateur.pdf#page=41"
    noms = {c.name for c in definir_index("test").fields}
    assert set(document) == noms


def test_citation_du_decret():
    chunk = next(c for c in lire_chunks() if c["id"] == "decret-2-12-503_art-28_p1")
    assert titre_citation(chunk) == "Décret n° 2-12-503, Article 28"


def test_decoupage_en_lots():
    assert [len(l) for l in lots(list(range(250)), 100)] == [100, 100, 50]


def test_articles_attendus_existent_dans_les_chunks():
    connus = {f"{c['code_texte']}:{c['article']}" for c in lire_chunks()}
    with JEU.open(encoding="utf-8") as fichier:
        questions = json.load(fichier)
    assert {q["langue"] for q in questions} == {"fr", "ar"}
    for cas in questions:
        assert set(cas["attendus"]) <= connus
