"""Génère des données d'usage fictives pour le volet Fabric et Power BI.

Aucune donnée réelle : agences, conseillers et questions sont simulés. Le fichier
questions.csv contient volontairement des anomalies, corrigées ensuite par le notebook.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

GRAINE = 2026
NB_QUESTIONS = 5000
DEBUT = datetime(2026, 8, 1)
JOURS = 92
SORTIE = Path(__file__).resolve().parent / "raw"

AGENCES = [
    ("AG01", "Agence Anfa", "Casablanca", "Casablanca-Settat"),
    ("AG02", "Agence Maarif", "Casablanca", "Casablanca-Settat"),
    ("AG03", "Agence Hassan", "Rabat", "Rabat-Salé-Kénitra"),
    ("AG04", "Agence Agdal", "Rabat", "Rabat-Salé-Kénitra"),
    ("AG05", "Agence Guéliz", "Marrakech", "Marrakech-Safi"),
    ("AG06", "Agence Ville Nouvelle", "Fès", "Fès-Meknès"),
    ("AG07", "Agence Malabata", "Tanger", "Tanger-Tétouan-Al Hoceïma"),
    ("AG08", "Agence Centre", "Agadir", "Souss-Massa"),
]
THEMES = {
    "Remboursement anticipé": ("31-08", 22),
    "Offre préalable": ("31-08", 18),
    "Rétractation": ("31-08", 16),
    "Clauses abusives": ("31-08", 10),
    "Contrôle Bank Al-Maghrib": ("103-12", 12),
    "Banques participatives": ("103-12", 8),
    "Garantie des dépôts": ("103-12", 6),
    "Hors périmètre": ("aucune", 8),
}
HABILITATIONS = [
    ("conseiller.casablanca@exemple.ma", "Casablanca-Settat"),
    ("responsable.rabat@exemple.ma", "Rabat-Salé-Kénitra"),
]


def ecrire(nom: str, entetes: list[str], lignes: list[tuple]) -> None:
    with (SORTIE / nom).open("w", newline="", encoding="utf-8") as fichier:
        sortie = csv.writer(fichier)
        sortie.writerow(entetes)
        sortie.writerows(lignes)


def tirer_statut(alea: random.Random, theme: str) -> str:
    if theme == "Hors périmètre":
        return alea.choices(["refus", "escalade"], [85, 15])[0]
    return alea.choices(["reponse", "refus", "escalade"], [90, 4, 6])[0]


def tirer_feedback(alea: random.Random, statut: str) -> str:
    if alea.random() < 0.55:
        return ""
    return alea.choices(["utile", "pas_utile"], [85, 15] if statut == "reponse" else [45, 55])[0]


def question(alea: random.Random, rang: int, conseillers: list[str]) -> list:
    theme = alea.choices(list(THEMES), [p for _, p in THEMES.values()])[0]
    statut = tirer_statut(alea, theme)
    moment = DEBUT + timedelta(
        days=alea.randrange(JOURS), hours=alea.randint(8, 17), minutes=alea.randrange(60)
    )
    return [
        f"Q{rang:06d}",
        moment.strftime("%Y-%m-%d %H:%M:%S"),
        alea.choice(conseillers),
        theme,
        THEMES[theme][0],
        alea.choices(["fr", "ar"], [78, 22])[0],
        statut,
        int(alea.lognormvariate(8.05, 0.4)),
        alea.randint(2200, 3200),
        alea.randint(120, 320),
        tirer_feedback(alea, statut),
    ]


def ajouter_anomalies(alea: random.Random, lignes: list[list]) -> None:
    for ligne in alea.sample(lignes, 70):
        ligne[6] = f"  {ligne[6].upper()} "
    for ligne in alea.sample(lignes, 15):
        ligne[7] = -1
    for ligne in alea.sample(lignes, 10):
        ligne[2] = "C999"
    lignes.extend([list(ligne) for ligne in alea.sample(lignes, 50)])


def main() -> None:
    alea = random.Random(GRAINE)
    SORTIE.mkdir(exist_ok=True)
    conseillers = [
        (f"C{rang:03d}", f"Conseiller {rang:03d}", AGENCES[(rang - 1) % len(AGENCES)][0])
        for rang in range(1, 41)
    ]
    identifiants = [c[0] for c in conseillers]
    lignes = [question(alea, rang, identifiants) for rang in range(1, NB_QUESTIONS + 1)]
    ajouter_anomalies(alea, lignes)
    alea.shuffle(lignes)

    ecrire("agences.csv", ["agence_id", "agence", "ville", "region"], AGENCES)
    ecrire("conseillers.csv", ["conseiller_id", "conseiller", "agence_id"], conseillers)
    ecrire("habilitations.csv", ["email", "region"], HABILITATIONS)
    ecrire(
        "questions.csv",
        [
            "question_id", "horodatage", "conseiller_id", "theme", "loi", "langue", "statut",
            "latence_ms", "tokens_entree", "tokens_sortie", "feedback",
        ],
        lignes,
    )
    print(f"{len(lignes)} lignes écrites dans {SORTIE}")


if __name__ == "__main__":
    main()
