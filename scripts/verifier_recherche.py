"""Mesure le rappel à 5 sur des questions dont l'article attendu a été vérifié dans la loi.

Les PDF sont en français : les questions en arabe sont traduites avant la recherche.
Un résultat compte comme réussi si un article attendu figure dans les 5 premiers documents.
"""

from __future__ import annotations

import json

from config import RACINE, client_openai, client_recherche, executer
from rechercher import rechercher, requete_de_recherche

JEU_DE_TEST = RACINE / "data" / "questions_reference.json"
TOP = 5


def verifier() -> None:
    with JEU_DE_TEST.open(encoding="utf-8") as fichier:
        questions = json.load(fichier)

    recherche, openai_client = client_recherche(), client_openai()
    bilan: dict[str, list[bool]] = {}
    for cas in questions:
        requete = requete_de_recherche(cas["question"], openai_client)
        documents = rechercher(requete, TOP, recherche, openai_client)
        trouves = [f"{d['code_texte']}:{d['article']}" for d in documents]
        reussi = any(cible in trouves for cible in cas["attendus"])
        bilan.setdefault(cas["langue"], []).append(reussi)
        print(f"[{'OK ' if reussi else 'NON'}] {cas['langue']} | {cas['question']}")
        if requete != cas["question"]:
            print(f"      requête : {requete}")
        if not reussi:
            print(f"      attendu : {cas['attendus']}\n      obtenu  : {trouves}")

    print()
    for langue, resultats in bilan.items():
        print(f"Rappel@{TOP} {langue} : {sum(resultats)}/{len(resultats)}")


def main() -> None:
    executer(verifier)


if __name__ == "__main__":
    main()
