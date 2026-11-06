"""Crée l'index hybride AI Search et y envoie les articles vectorisés.

Le script peut être relancé sans risque : l'index est mis à jour et les documents
sont remplacés par leur identifiant. Avec --recreer, l'index est d'abord supprimé.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchIndex,
    VectorSearch,
    VectorSearchProfile,
)

from config import (
    DIMENSIONS,
    FICHIERS_PDF,
    RACINE,
    client_index,
    client_openai,
    client_recherche,
    executer,
    variable,
    vectoriser,
)

ANALYSEUR = "fr.microsoft"
PROFIL_VECTEUR = "profil-hnsw"
TAILLE_LOT_VECTEURS = 64
TAILLE_LOT_ENVOI = 100


def champ_filtre(nom: str, type_champ: str = "Edm.String", **options) -> SearchField:
    return SearchField(name=nom, type=type_champ, filterable=True, retrievable=True, **options)


def champ_texte(nom: str) -> SearchField:
    return SearchField(
        name=nom, type="Edm.String", searchable=True, retrievable=True, analyzer_name=ANALYSEUR
    )


def definir_index(nom: str) -> SearchIndex:
    # content, title et url sont les champs lus par l'outil Azure AI Search des agents Foundry.
    champs = [
        SearchField(name="id", type="Edm.String", key=True, filterable=True, retrievable=True),
        champ_texte("title"),
        champ_texte("content"),
        champ_texte("structure"),
        SearchField(name="url", type="Edm.String", retrievable=True),
        champ_filtre("type_source"),
        champ_filtre("code_texte"),
        champ_filtre("reference"),
        champ_filtre("article"),
        champ_filtre("numero_article", "Edm.Int32", sortable=True),
        champ_filtre("page_debut", "Edm.Int32"),
        champ_filtre("page_fin", "Edm.Int32"),
        champ_filtre("partie", "Edm.Int32"),
        champ_filtre("parties_total", "Edm.Int32"),
        champ_filtre("articles_loi_lies", "Collection(Edm.String)"),
        SearchField(
            name="content_vector",
            type="Collection(Edm.Single)",
            searchable=True,
            retrievable=False,
            stored=False,
            vector_search_dimensions=DIMENSIONS,
            vector_search_profile_name=PROFIL_VECTEUR,
        ),
    ]
    recherche_vectorielle = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name=PROFIL_VECTEUR, algorithm_configuration_name="hnsw")],
    )
    return SearchIndex(name=nom, fields=champs, vector_search=recherche_vectorielle)


def titre_citation(chunk: dict) -> str:
    return f"{chunk['reference']}, {chunk['article'].removesuffix(' du décret')}"


def vers_document(chunk: dict, vecteur: list[float], base_url: str) -> dict:
    return {
        "id": chunk["id"],
        "title": titre_citation(chunk),
        "content": chunk["contenu"],
        "structure": " > ".join(
            x for x in (chunk["titre"], chunk["chapitre"], chunk["section"]) if x
        ),
        "url": f"{base_url.rstrip('/')}/{FICHIERS_PDF[chunk['code_texte']]}#page={chunk['page_debut']}",
        "type_source": chunk["type_source"],
        "code_texte": chunk["code_texte"],
        "reference": chunk["reference"],
        "article": chunk["article"],
        "numero_article": chunk["numero_article"],
        "page_debut": chunk["page_debut"],
        "page_fin": chunk["page_fin"],
        "partie": chunk["partie"],
        "parties_total": chunk["parties_total"],
        "articles_loi_lies": chunk["articles_loi_lies"],
        "content_vector": vecteur,
    }


def lots(elements: list, taille: int):
    for debut in range(0, len(elements), taille):
        yield elements[debut : debut + taille]


def lire_chunks(chemin: Path) -> list[dict]:
    with chemin.open(encoding="utf-8") as fichier:
        return [json.loads(ligne) for ligne in fichier if ligne.strip()]


def indexer(chemin: Path, recreer: bool) -> None:
    nom_index = variable("AZURE_SEARCH_INDEX")
    base_url = variable("AZURE_BLOB_BASE_URL")
    chunks = lire_chunks(chemin)

    administration = client_index()
    if recreer:
        try:
            administration.delete_index(nom_index)
        except ResourceNotFoundError:
            pass
    administration.create_or_update_index(definir_index(nom_index))
    print(f"Index prêt : {nom_index}")

    openai_client = client_openai()
    documents = []
    for lot in lots(chunks, TAILLE_LOT_VECTEURS):
        vecteurs = vectoriser(openai_client, [c["texte_a_vectoriser"] for c in lot])
        documents += [vers_document(c, v, base_url) for c, v in zip(lot, vecteurs)]
        print(f"Vecteurs : {len(documents)}/{len(chunks)}")

    recherche = client_recherche()
    envoyes = 0
    for lot in lots(documents, TAILLE_LOT_ENVOI):
        resultats = recherche.upload_documents(lot)
        echecs = [r.key for r in resultats if not r.succeeded]
        if echecs:
            raise SystemExit(f"Documents refusés : {echecs[:5]}")
        envoyes += len(resultats)
        print(f"Envoyés : {envoyes}/{len(documents)}")
    print(f"Terminé : {envoyes} documents dans {nom_index}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunks", type=Path, default=RACINE / "data" / "chunks.jsonl")
    parser.add_argument("--recreer", action="store_true", help="supprime l'index avant de le créer")
    args = parser.parse_args()
    executer(lambda: indexer(args.chunks, args.recreer))


if __name__ == "__main__":
    main()
