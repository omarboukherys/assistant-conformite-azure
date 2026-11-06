"""Vérifie la traduction des questions en arabe, sans appel à Azure."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rechercher import requete_de_recherche  # noqa: E402


class FauxClient:
    def __init__(self, *reponses):
        self.appels = []
        self.reponses = list(reponses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.creer))

    def creer(self, **options):
        self.appels.append(options)
        message = SimpleNamespace(content=self.reponses.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


QUESTION_ARABE = "ما هو أجل التراجع؟"


def test_question_francaise_sans_appel_au_modele():
    client = FauxClient()
    assert requete_de_recherche("Quel est le délai ?", client) == "Quel est le délai ?"
    assert client.appels == []


def test_question_arabe_traduite(monkeypatch):
    monkeypatch.setenv("AZURE_CHAT_DEPLOYMENT", "gpt-5.4-mini")
    client = FauxClient("  Quel est le délai de rétractation ?\n")
    assert requete_de_recherche(QUESTION_ARABE, client) == "Quel est le délai de rétractation ?"
    assert client.appels[0]["model"] == "gpt-5.4-mini"
    assert client.appels[0]["messages"][-1]["content"] == QUESTION_ARABE


def test_reformulation_en_arabe_refusee_puis_nouvel_essai(monkeypatch):
    monkeypatch.setenv("AZURE_CHAT_DEPLOYMENT", "gpt-5.4-mini")
    client = FauxClient("ما هو الأجل؟", "Quel est le délai ?")
    assert requete_de_recherche(QUESTION_ARABE, client) == "Quel est le délai ?"
    assert len(client.appels) == 2


def test_echec_de_traduction_garde_la_question(monkeypatch, capsys):
    monkeypatch.setenv("AZURE_CHAT_DEPLOYMENT", "gpt-5.4-mini")
    client = FauxClient("ما هو الأجل؟", "ما هو الأجل؟")
    assert requete_de_recherche(QUESTION_ARABE, client) == QUESTION_ARABE
    assert "traduction impossible" in capsys.readouterr().out
