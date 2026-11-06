"""Découpe les lois 31-08 et 103-12 article par article.

Pourquoi ne pas utiliser l'indexeur Azure ni un découpage à taille fixe :
- l'indexeur du niveau Free tronque chaque document à environ 32 000 caractères,
  alors que chaque loi en compte plus de 140 000 ;
- la loi 31-08 reproduit des articles du décret n° 2-12-503 en notes de bas de page.
  Ils portent leurs propres numéros (« Article 23 : »), et un découpage naïf les
  confondrait avec les articles de la loi. Une citation juridique serait alors fausse.

Le script sépare donc le corps du texte et les notes grâce au filet de séparation
du PDF, puis repère les titres d'articles par leur police (gras, centré).

Usage : python scripts/decouper_lois.py [--pdf-dir data/pdf] [--sortie data/chunks.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber

TEXTES = {
    "31-08": {
        "fichier": "loi-31-08-protection-consommateur.pdf",
        "reference": "Loi n° 31-08",
        "intitule": "Loi n° 31-08 édictant des mesures de protection du consommateur",
        "nb_articles": 206,
    },
    "103-12": {
        "fichier": "loi-103-12-etablissements-credit.pdf",
        "reference": "Loi n° 103-12",
        "intitule": "Loi n° 103-12 relative aux établissements de crédit et organismes assimilés",
        "nb_articles": 196,
    },
}
DECRET = {
    "code": "decret-2-12-503",
    "reference": "Décret n° 2-12-503",
    "intitule": (
        "Décret n° 2-12-503 du 11 septembre 2013 pris pour l'application de "
        "certaines dispositions de la loi n° 31-08"
    ),
}

TAILLE_MAX = 2200
RECOUVREMENT = 250
TAILLE_APPEL_NOTE = 9.0
TAILLE_MIN_INTITULE = 15.0  # le corps du texte est en 14 ; certains titres ne sont pas en gras
# Le PDF contient des coquilles d'origine, comme « Article 3l » avec un L à la place du 1.
RE_ARTICLE = re.compile(r"^Article\s+(premier|1er|\d[\dlI]*)\s*$", re.I)
RE_ARTICLE_DECRET = re.compile(r"^Article\s*(\d+)\s*:?\s*$")
RE_NOTE = re.compile(r"^(\d{1,2})\s*-\s*\S")
RE_RENVOI_DECRET = re.compile(r"Voir\s+(?:les\s+)?articles?\s+(.*?)\s+du\s+décret", re.I)
RE_STRUCTURE = re.compile(r"^(TITRE|Chapitre|Section|Sous-section)\b", re.I)
RE_DEBUT_LOI = re.compile(r"^LOI\s+N°", re.I)
RE_PUCE = re.compile(r"^[\-–—•\uf0b7\uf02d\uf0a7]\s*")
RE_ITEM = re.compile(r"^(\d{1,2}[.)]|[A-Z][.)]|[a-z]\))\s")


@dataclass
class Ligne:
    page: int
    haut: float
    x0: float
    texte: str
    gras: bool
    taille: float

    @property
    def intitule(self) -> bool:
        return self.gras or self.taille >= TAILLE_MIN_INTITULE


@dataclass
class Article:
    numero: int | None
    libelle: str
    page_debut: int
    page_fin: int
    titre: str = ""
    chapitre: str = ""
    section: str = ""
    lignes: list[Ligne] = field(default_factory=list)


@dataclass
class Chunk:
    id: str
    type_source: str
    code_texte: str
    reference: str
    intitule: str
    article: str
    numero_article: int | None
    titre: str
    chapitre: str
    section: str
    page_debut: int
    page_fin: int
    partie: int
    parties_total: int
    articles_loi_lies: list[str]
    contenu: str
    texte_a_vectoriser: str


def nettoyer(texte: str) -> str:
    return re.sub(r"\s+", " ", texte.replace(" ", " ")).strip()


def est_gras(chars: list[dict]) -> bool:
    utiles = [c for c in chars if c["text"].strip()]
    return bool(utiles) and sum("Bold" in c["fontname"] for c in utiles) / len(utiles) > 0.8


def filet_de_notes(page) -> float | None:
    """Renvoie l'ordonnée du filet qui sépare le corps des notes, s'il existe."""
    filets = [r for r in page.rects if r["bottom"] - r["top"] < 3 and r["x1"] - r["x0"] > 100]
    return min((r["top"] for r in filets), default=None)


def lire_page(page, numero: int) -> tuple[list[Ligne], list[Ligne], list[tuple[int, float, int]]]:
    """Sépare une page en lignes de corps, lignes de notes et appels de note."""
    page = page.dedupe_chars(tolerance=2, extra_attrs=())  # titres dessinés deux fois
    filet = filet_de_notes(page)
    limite = filet if filet is not None else page.height

    def garde_corps(obj: dict) -> bool:
        if obj.get("object_type") != "char":
            return True
        return (
            obj["top"] < limite
            and "Calibri" not in obj["fontname"]
            and round(obj["size"], 1) != TAILLE_APPEL_NOTE
        )

    def garde_notes(obj: dict) -> bool:
        if obj.get("object_type") != "char":
            return True
        return obj["top"] > limite and "Calibri" not in obj["fontname"]

    def lignes_de(vue) -> list[Ligne]:
        resultat = []
        for ligne in vue.extract_text_lines(return_chars=True, x_tolerance=1.5):
            chars = ligne["chars"]
            texte = nettoyer(ligne["text"])
            if not texte or re.fullmatch(r"-\s*\d+\s*-", texte):
                continue
            tailles = [c["size"] for c in chars if c["text"].strip()]
            resultat.append(
                Ligne(
                    page=numero,
                    haut=ligne["top"],
                    x0=ligne["x0"],
                    texte=texte,
                    gras=est_gras(chars),
                    taille=max(tailles, default=0),
                )
            )
        return resultat

    corps = lignes_de(page.filter(garde_corps))
    notes = lignes_de(page.filter(garde_notes)) if filet is not None else []

    appels = []
    bruts = sorted(
        (
            c
            for c in page.chars
            if round(c["size"], 1) == TAILLE_APPEL_NOTE
            and c["top"] < limite
            and c["text"].isdigit()
        ),
        key=lambda c: (round(c["top"]), c["x0"]),
    )
    courant, dernier = "", None
    for c in bruts:
        if dernier is not None and (abs(c["top"] - dernier["top"]) > 1 or c["x0"] - dernier["x1"] > 2):
            appels.append((numero, dernier["top"], int(courant)))
            courant = ""
        courant += c["text"]
        dernier = c
    if courant:
        appels.append((numero, dernier["top"], int(courant)))
    return corps, notes, appels


def lire_pdf(chemin: Path) -> tuple[list[Ligne], list[Ligne], list[tuple[int, float, int]]]:
    corps, notes, appels = [], [], []
    with pdfplumber.open(chemin) as pdf:
        for numero, page in enumerate(pdf.pages, 1):
            c, n, a = lire_page(page, numero)
            corps += c
            notes += n
            appels += a
    return corps, notes, appels


def numero_article(libelle: str) -> int:
    valeur = RE_ARTICLE.match(libelle).group(1).lower()
    return 1 if valeur in ("premier", "1er") else int(valeur.replace("l", "1").replace("i", "1"))


def structurer(corps: list[Ligne], attendus: int) -> list[Article]:
    """Regroupe les lignes en articles et note leur place dans la loi."""
    debut = next(i for i, l in enumerate(corps) if RE_DEBUT_LOI.match(l.texte) and l.intitule)
    articles: list[Article] = []
    actuel: Article | None = None
    contexte = {"titre": "", "chapitre": "", "section": ""}
    dernier_niveau: str | None = None
    i = debut

    while i < len(corps):
        ligne = corps[i]
        i += 1

        if ligne.intitule and RE_STRUCTURE.match(ligne.texte):
            niveau = ligne.texte.split()[0].lower().split("-")[0]
            niveau = {"sous": "section"}.get(niveau, niveau)
            contexte[niveau] = ligne.texte
            if niveau == "titre":
                contexte["chapitre"] = contexte["section"] = ""
            elif niveau == "chapitre":
                contexte["section"] = ""
            dernier_niveau = niveau
            continue

        if ligne.intitule and RE_ARTICLE.match(ligne.texte):
            numero = numero_article(ligne.texte)
            libelle = "Article premier" if numero == 1 else f"Article {numero}"
            actuel = Article(numero, libelle, ligne.page, ligne.page, **contexte)
            articles.append(actuel)
            dernier_niveau = None
            continue

        if ligne.intitule and dernier_niveau:
            # Suite d'un intitulé de titre, de chapitre ou de section sur plusieurs lignes.
            contexte[dernier_niveau] = f"{contexte[dernier_niveau]} {ligne.texte}"
            continue

        if ligne.intitule and ligne.texte.upper().startswith("PREAMBULE"):
            actuel = Article(None, "Préambule", ligne.page, ligne.page)
            articles.append(actuel)
            continue

        if actuel is not None:
            actuel.lignes.append(ligne)
            actuel.page_fin = ligne.page

    numeros = [a.numero for a in articles if a.numero is not None]
    if numeros != list(range(1, attendus + 1)):
        manquants = sorted(set(range(1, attendus + 1)) - set(numeros))
        raise ValueError(f"Articles inattendus : {len(numeros)} trouvés, manquants {manquants}")
    return articles


def paragraphes(lignes: list[Ligne]) -> list[str]:
    """Reconstitue les paragraphes à partir des retraits de première ligne."""
    if not lignes:
        return []
    marge = min(l.x0 for l in lignes)
    blocs: list[str] = []
    x_puce: float | None = None
    for ligne in lignes:
        retrait = ligne.x0 - marge
        puce = bool(RE_PUCE.match(ligne.texte) or RE_ITEM.match(ligne.texte))
        texte = RE_PUCE.sub("- ", ligne.texte)
        suite_de_puce = x_puce is not None and not puce and ligne.x0 > x_puce + 2
        if puce:
            x_puce = ligne.x0
        elif not suite_de_puce:
            x_puce = None
        if not blocs or puce or (retrait > 8 and not suite_de_puce):
            blocs.append(texte)
        elif blocs[-1].endswith("-") and not blocs[-1].endswith(" -"):
            blocs[-1] += texte
        else:
            blocs[-1] += f" {texte}"
    return blocs


def decouper(blocs: list[str]) -> list[str]:
    """Garde un article entier si possible, sinon coupe entre deux paragraphes."""
    texte = "\n".join(blocs)
    if len(texte) <= TAILLE_MAX:
        return [texte] if texte else []

    morceaux: list[str] = []
    courant: list[str] = []
    for bloc in blocs:
        if courant and len("\n".join(courant)) + len(bloc) + 1 > TAILLE_MAX:
            morceaux.append("\n".join(courant))
            reprise: list[str] = []
            for precedent in reversed(courant):
                if sum(map(len, reprise)) + len(precedent) > RECOUVREMENT:
                    break
                reprise.insert(0, precedent)
            courant = reprise
        courant.append(bloc)
    if courant:
        morceaux.append("\n".join(courant))
    return morceaux


def creer_chunks(
    *,
    code: str,
    type_source: str,
    reference: str,
    intitule: str,
    article: str,
    numero: int | None,
    blocs: list[str],
    pages: tuple[int, int],
    titre: str = "",
    chapitre: str = "",
    section: str = "",
    liens: list[str] | None = None,
) -> list[Chunk]:
    morceaux = decouper(blocs)
    cle = "preambule" if numero is None else f"art-{numero}"
    chemin = " > ".join(x for x in (intitule, titre, chapitre, section, article) if x)
    resultat = []
    for rang, contenu in enumerate(morceaux, 1):
        resultat.append(
            Chunk(
                id=f"{code}_{cle}_p{rang}",
                type_source=type_source,
                code_texte=code,
                reference=reference,
                intitule=intitule,
                article=article,
                numero_article=numero,
                titre=titre,
                chapitre=chapitre,
                section=section,
                page_debut=pages[0],
                page_fin=pages[1],
                partie=rang,
                parties_total=len(morceaux),
                articles_loi_lies=liens or [],
                contenu=contenu,
                texte_a_vectoriser=f"{chemin}\n{contenu}",
            )
        )
    return resultat


def article_de_l_appel(articles: list[Article], page: int, haut: float) -> Article | None:
    """Trouve l'article de la loi dans lequel se trouve un appel de note."""
    for article in articles:
        if not article.lignes:
            continue
        premiere, derniere = article.lignes[0], article.lignes[-1]
        apres_debut = (page, haut + 3) >= (premiere.page, premiere.haut)
        avant_fin = (page, haut - 3) <= (derniere.page, derniere.haut)
        if apres_debut and avant_fin:
            return article
    return None


def fin_de_citation(blocs: list[str]) -> list[str]:
    """Retire les renvois placés après le guillemet fermant de l'article cité."""
    texte = "\n".join(blocs)
    fin = texte.rfind("»")
    return texte[: fin + 1].split("\n") if fin != -1 else blocs


def extraire_decret(
    notes: list[Ligne], appels: list[tuple[int, float, int]], articles: list[Article]
) -> list[Chunk]:
    """Isole les articles du décret reproduits dans les notes de la loi 31-08."""
    lien_par_note: dict[int, list[str]] = {}
    for page, haut, note in appels:
        article = article_de_l_appel(articles, page, haut)
        if article:
            lien_par_note.setdefault(note, []).append(article.libelle)

    renvois: dict[int, set[str]] = {}
    note_courante = None
    actuel: dict | None = None
    decret: list[dict] = []
    for ligne in notes:
        renvoi = RE_NOTE.match(ligne.texte)
        if renvoi:
            note_courante = int(renvoi.group(1))
            actuel = None
            cible = RE_RENVOI_DECRET.search(ligne.texte)
            if cible:
                numeros = [int(n) for n in re.findall(r"\d+", cible.group(1))]
                if " à " in cible.group(1) and len(numeros) >= 2:
                    numeros = [numeros[0], *range(numeros[-2], numeros[-1] + 1)]
                for n in numeros:
                    renvois.setdefault(n, set()).update(lien_par_note.get(note_courante, []))
            continue
        en_tete = RE_ARTICLE_DECRET.match(ligne.texte)
        if en_tete and ligne.gras:
            numero = int(en_tete.group(1))
            actuel = {"numero": numero, "lignes": [], "page_debut": ligne.page, "page_fin": ligne.page}
            decret.append(actuel)
            continue
        if actuel is not None:
            actuel["lignes"].append(ligne)
            actuel["page_fin"] = ligne.page

    chunks: list[Chunk] = []
    for bloc in decret:
        numero = bloc["numero"]
        blocs = fin_de_citation(paragraphes(bloc["lignes"]))
        liens = sorted(renvois.get(numero, set()), key=lambda a: int(re.sub(r"\D", "", a) or 1))
        chunks += creer_chunks(
            code=DECRET["code"],
            type_source="decret",
            reference=DECRET["reference"],
            intitule=DECRET["intitule"],
            article=f"Article {numero} du décret",
            numero=numero,
            blocs=blocs,
            pages=(bloc["page_debut"], bloc["page_fin"]),
            liens=liens,
        )
    return chunks


def construire(dossier_pdf: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for code, texte in TEXTES.items():
        corps, notes, appels = lire_pdf(dossier_pdf / texte["fichier"])
        articles = structurer(corps, texte["nb_articles"])
        for article in articles:
            chunks += creer_chunks(
                code=code,
                type_source="loi",
                reference=texte["reference"],
                intitule=texte["intitule"],
                article=article.libelle,
                numero=article.numero,
                blocs=paragraphes(article.lignes),
                pages=(article.page_debut, article.page_fin),
                titre=article.titre,
                chapitre=article.chapitre,
                section=article.section,
            )
        if code == "31-08":
            chunks += extraire_decret(notes, appels, articles)
    return chunks


def main() -> None:
    racine = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, default=racine / "data" / "pdf")
    parser.add_argument("--sortie", type=Path, default=racine / "data" / "chunks.jsonl")
    args = parser.parse_args()

    chunks = construire(args.pdf_dir)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    with args.sortie.open("w", encoding="utf-8") as fichier:
        for chunk in chunks:
            fichier.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

    for code in [*TEXTES, DECRET["code"]]:
        sous_ensemble = [c for c in chunks if c.code_texte == code]
        distincts = {c.numero_article for c in sous_ensemble if c.numero_article}
        print(f"{code}: {len(distincts)} articles, {len(sous_ensemble)} morceaux")
    print(f"Écrit : {args.sortie} ({len(chunks)} morceaux)")


if __name__ == "__main__":
    main()
