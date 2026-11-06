"""Paramètres communs et clients Azure, avec une authentification Entra ID sans clé."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import AzureCliCredential, CredentialUnavailableError, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv
from openai import APIStatusError, AuthenticationError, OpenAI, PermissionDeniedError

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

DIMENSIONS = 1536  # taille des vecteurs de text-embedding-3-small
PORTEE_FOUNDRY = "https://ai.azure.com/.default"
FICHIERS_PDF = {
    "31-08": "loi-31-08-protection-consommateur.pdf",
    "103-12": "loi-103-12-etablissements-credit.pdf",
    "decret-2-12-503": "loi-31-08-protection-consommateur.pdf",  # reproduit dans ses notes
}


def variable(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        sys.exit(f"Variable manquante : {nom}. Copie .env.example vers .env.")
    return valeur


def identifiants() -> AzureCliCredential:
    return AzureCliCredential(tenant_id=variable("AZURE_TENANT_ID"))


def client_index() -> SearchIndexClient:
    return SearchIndexClient(variable("AZURE_SEARCH_ENDPOINT"), identifiants())


def client_recherche() -> SearchClient:
    return SearchClient(
        variable("AZURE_SEARCH_ENDPOINT"), variable("AZURE_SEARCH_INDEX"), identifiants()
    )


def client_openai() -> OpenAI:
    return OpenAI(
        base_url=variable("AZURE_OPENAI_ENDPOINT"),
        api_key=get_bearer_token_provider(identifiants(), PORTEE_FOUNDRY),
    )


def vectoriser(openai_client: OpenAI, textes: list[str]) -> list[list[float]]:
    reponse = openai_client.embeddings.create(
        model=variable("AZURE_EMBEDDING_DEPLOYMENT"), input=textes
    )
    return [element.embedding for element in sorted(reponse.data, key=lambda e: e.index)]


def executer(action) -> None:
    """Lance une action et traduit les erreurs d'accès les plus probables."""
    try:
        action()
    except (CredentialUnavailableError, ClientAuthenticationError) as erreur:
        sys.exit(
            "Connexion Azure impossible. Lance : "
            f"az login --tenant {variable('AZURE_TENANT_ID')} --use-device-code\n{erreur}"
        )
    except HttpResponseError as erreur:
        if erreur.status_code in (401, 403):
            sys.exit(
                "AI Search refuse l'accès. Vérifie que Keys est sur Both et que ton compte "
                "omar@ a les rôles Search Service Contributor et Search Index Data Contributor. "
                f"Un rôle peut mettre 5 à 10 minutes à s'appliquer.\n{erreur.message}"
            )
        raise
    except (AuthenticationError, PermissionDeniedError) as erreur:
        sys.exit(
            "Foundry refuse l'accès. Vérifie que ton compte omar@ a le rôle Foundry User "
            f"(ancien nom : Azure AI User) sur assistant-conformite-resource.\n{erreur}"
        )
    except APIStatusError as erreur:
        sys.exit(f"Erreur Foundry {erreur.status_code} : {erreur.message}")
