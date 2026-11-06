"""Contrôles du découpage, sans appel à Azure."""

import json
import re
from pathlib import Path

import pytest

CHUNKS = Path(__file__).resolve().parent.parent / "data" / "chunks.jsonl"


@pytest.fixture(scope="module")
def chunks():
    with CHUNKS.open(encoding="utf-8") as fichier:
        return [json.loads(ligne) for ligne in fichier]


def contenu(chunks, code, numero):
    return "\n".join(
        c["contenu"]
        for c in chunks
        if c["code_texte"] == code and c["numero_article"] == numero
    )


@pytest.mark.parametrize("code, total", [("31-08", 206), ("103-12", 196)])
def test_chaque_article_de_loi_est_present(chunks, code, total):
    numeros = {
        c["numero_article"] for c in chunks if c["code_texte"] == code and c["numero_article"]
    }
    assert numeros == set(range(1, total + 1))


def test_identifiants_uniques_et_valides_pour_ai_search(chunks):
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[A-Za-z0-9_\-=]+", i) for i in ids)


def test_article_du_decret_non_confondu_avec_la_loi(chunks):
    # L'article 23 du décret parle du mode d'emploi, pas l'article 23 de la loi.
    assert "mode d'emploi" not in contenu(chunks, "31-08", 23)
    assert "mode d'emploi" in contenu(chunks, "decret-2-12-503", 23)


def test_aucune_note_dans_le_texte_des_lois(chunks):
    lois = [c for c in chunks if c["type_source"] == "loi"]
    assert not [c["id"] for c in lois if "n° 2-12-503" in c["contenu"]]
    assert not [c["id"] for c in lois if "Bulletin Officiel n°" in c["contenu"]]


def test_appels_de_note_retires(chunks):
    assert not [c["id"] for c in chunks if re.search(r"réglementaire\s?\d", c["contenu"])]


def test_aucun_intitule_dans_le_contenu(chunks):
    motif = re.compile(r"^(TITRE\s|Chapitre\s|Section\s\d|Article\s\d+\s*$)", re.M)
    assert not [c["id"] for c in chunks if motif.search(c["contenu"])]


def test_decret_relie_aux_articles_de_la_loi(chunks):
    article_33 = next(c for c in chunks if c["id"] == "decret-2-12-503_art-33_p1")
    assert {"Article 79", "Article 83", "Article 104"} <= set(article_33["articles_loi_lies"])


def test_contenu_juridique_de_reference(chunks):
    assert "rembourser par anticipation" in contenu(chunks, "31-08", 103)
    assert "sept jours" in contenu(chunks, "31-08", 85)
    assert "3.000 Dirhams" in contenu(chunks, "decret-2-12-503", 28)


def test_taille_maximale_respectee(chunks):
    assert max(len(c["contenu"]) for c in chunks) <= 2400


def test_contexte_ajoute_au_texte_vectorise(chunks):
    chunk = next(c for c in chunks if c["id"] == "31-08_art-103_p1")
    assert "Remboursement anticipé" in chunk["texte_a_vectoriser"]
    assert "Article 103" in chunk["texte_a_vectoriser"]
