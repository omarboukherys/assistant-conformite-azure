"""Interroge l'index en recherche hybride : mots-clés et vecteurs combinés.

Usage : python scripts/rechercher.py "Un client peut-il rembourser son crédit par anticipation ?"
"""

from __future__ import annotations

import argparse
import re

from azure.search.documents.models import VectorizedQuery

from config import client_openai, client_recherche, executer, variable, vectoriser

CHAMPS = ["id", "title", "content", "article", "code_texte", "page_debut", "partie", "parties_total"]
VOISINS = 30
RE_ARABE = re.compile(r"[\u0600-\u06FF]")
TENTATIVES_TRADUCTION = 2
CONSIGNE_TRADUCTION = (
    "Tu es traducteur juridique de l'arabe vers le français. Tu reçois une question en arabe. "
    "Renvoie uniquement sa traduction en français, avec le vocabulaire du droit marocain. "
    "Ne réponds pas à la question, ne la reformule pas en arabe et n'écris aucun caractère arabe. "
    "Conserve les rôles juridiques : المقترض signifie emprunteur et المقرض signifie prêteur."
)
EXEMPLE_QUESTION = "هل يحق للمستهلك التراجع عن الشراء عن بعد؟"
EXEMPLE_TRADUCTION = "Le consommateur a-t-il le droit de se rétracter d'un achat à distance ?"


def requete_de_recherche(question: str, openai_client) -> str:
    """Les lois sont en français : une question en arabe est d'abord traduite."""
    if not RE_ARABE.search(question):
        return question
    for _ in range(TENTATIVES_TRADUCTION):
        reponse = openai_client.chat.completions.create(
            model=variable("AZURE_CHAT_DEPLOYMENT"),
            messages=[
                {"role": "system", "content": CONSIGNE_TRADUCTION},
                {"role": "user", "content": EXEMPLE_QUESTION},
                {"role": "assistant", "content": EXEMPLE_TRADUCTION},
                {"role": "user", "content": question},
            ],
        )
        traduction = reponse.choices[0].message.content.strip()
        if traduction and not RE_ARABE.search(traduction):
            return traduction
    print("Attention : traduction impossible, recherche avec la question d'origine.")
    return question


def rechercher(question: str, top: int = 5, recherche=None, openai_client=None) -> list[dict]:
    recherche = recherche or client_recherche()
    openai_client = openai_client or client_openai()
    vecteur = vectoriser(openai_client, [question])[0]
    resultats = recherche.search(
        search_text=question,
        vector_queries=[
            VectorizedQuery(vector=vecteur, k_nearest_neighbors=VOISINS, fields="content_vector")
        ],
        select=CHAMPS,
        top=top,
    )
    return [dict(resultat) for resultat in resultats]


def afficher(question: str, top: int) -> None:
    openai_client = client_openai()
    requete = requete_de_recherche(question, openai_client)
    if requete != question:
        print(f"Requête traduite : {requete}\n")
    for rang, resultat in enumerate(rechercher(requete, top, None, openai_client), 1):
        extrait = " ".join(resultat["content"].split())[:220]
        print(f"{rang}. {resultat['title']} (p. {resultat['page_debut']})\n   {extrait}…\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    executer(lambda: afficher(args.question, args.top))


if __name__ == "__main__":
    main()
