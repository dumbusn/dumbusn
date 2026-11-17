"""Découpage officiel des dix régions. Chargé tel quel, sans localité inventée."""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CLASSEUR = Path(__file__).resolve().parent / "referentiel" / "Decoupage_Guinee_10_regions_uniformise.xlsx"
GENRES = (
    ("region", "Région"),
    ("prefecture", "Préfecture"),
    ("sous_prefecture", "Sous-préfecture ou commune"),
    ("quartier", "Quartier ou district"),
    ("secteur", "Secteur ou village"),
)
PARENT = {
    "prefecture": "region",
    "sous_prefecture": "prefecture",
    "quartier": "sous_prefecture",
    "secteur": "quartier",
}
_LIBELLES = dict(GENRES)


def semer_decoupage(conn):
    if conn.execute("SELECT 1 FROM maille WHERE code != '' LIMIT 1").fetchone():
        return
    if not CLASSEUR.is_file():
        return
    feuilles = _lire(CLASSEUR)
    regions = _inserer(conn, feuilles["Regions"], "region", None, {})
    prefectures = _inserer(conn, feuilles["Prefectures"], "prefecture", "code_region", regions)
    communes = _inserer(conn, feuilles["Communes_SousPref"], "sous_prefecture", "code_prefecture", prefectures)
    quartiers = _inserer(conn, feuilles["Quartiers_Districts"], "quartier", "code_commune", communes)
    _inserer(conn, feuilles["Secteurs_Villages"], "secteur", "code_quartier_district", quartiers)


def _inserer(conn, lignes, genre, cle_parent, parents):
    identifiants = {}
    lot = []
    for ligne in lignes:
        code = (ligne.get("code") or "").strip()
        nom = (ligne.get("nom") or "").strip()
        if not code or not nom:
            continue
        parent_id = None
        if cle_parent:
            parent_id = parents.get((ligne.get(cle_parent) or "").strip())
            if parent_id is None:
                continue
        detail = (ligne.get("niveau") or "").strip()
        lot.append((parent_id, genre, nom, code, detail))
    conn.executemany(
        """
        INSERT INTO maille (parent_id, genre, nom, code, detail, exemple)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        lot,
    )
    for ligne in conn.execute(
        "SELECT id, code FROM maille WHERE genre = ? AND code != ''",
        (genre,),
    ):
        identifiants[ligne["code"]] = ligne["id"]
    return identifiants


def _lire(chemin):
    noms = {
        "Regions": ("code", "nom"),
        "Prefectures": ("code", "code_region", "nom"),
        "Communes_SousPref": ("code", "code_prefecture", "code_region", "nom", "niveau"),
        "Quartiers_Districts": ("code", "code_commune", "code_prefecture", "code_region", "nom"),
        "Secteurs_Villages": (
            "code", "code_quartier_district", "code_commune", "code_prefecture", "code_region", "nom",
        ),
    }
    with zipfile.ZipFile(chemin) as archive:
        classeur = ET.fromstring(archive.read("xl/workbook.xml"))
        feuilles = []
        for feuille in classeur.findall("m:sheets/m:sheet", NS):
            feuilles.append(feuille.attrib["name"])
        resultat = {}
        for index, nom in enumerate(feuilles, start=1):
            if nom not in noms:
                continue
            colonnes = noms[nom]
            racine = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            lignes = []
            for ligne in racine.findall("m:sheetData/m:row", NS):
                valeurs = {}
                for cellule in ligne.findall("m:c", NS):
                    reference = cellule.attrib.get("r", "")
                    colonne = "".join(caractere for caractere in reference if caractere.isalpha())
                    valeurs[colonne] = _texte(cellule)
                if not any(valeurs.values()):
                    continue
                enregistrement = {}
                for position, cle in enumerate(colonnes):
                    lettre = chr(ord("A") + position)
                    enregistrement[cle] = valeurs.get(lettre, "")
                lignes.append(enregistrement)
            if lignes and lignes[0].get("code") == "code":
                lignes = lignes[1:]
            resultat[nom] = lignes
    return resultat


def _texte(cellule):
    valeur = cellule.find("m:v", NS)
    if valeur is not None and valeur.text:
        return valeur.text
    inline = cellule.find("m:is", NS)
    if inline is None:
        return ""
    return "".join(
        (noeud.text or "")
        for noeud in inline.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
    )


def selection(conn, requete):
    """Choix validé, du plus large au plus fin. Un niveau incohérent est ignoré."""
    choisi = {}
    for genre, _libelle in GENRES:
        brut = (requete.get(genre) or "").strip()
        if not brut:
            break
        try:
            identifiant = int(brut)
        except ValueError:
            break
        ligne = conn.execute(
            "SELECT id, genre, parent_id FROM maille WHERE id = ?",
            (identifiant,),
        ).fetchone()
        parent = PARENT.get(genre)
        if ligne is None or ligne["genre"] != genre:
            break
        if parent and ligne["parent_id"] != choisi.get(parent):
            break
        choisi[genre] = ligne["id"]
    return choisi


def ancre(choisi):
    for genre, _libelle in reversed(GENRES):
        if genre in choisi:
            return choisi[genre]
    return None


def options(conn, genre, parent_id):
    if genre == "region":
        return conn.execute(
            "SELECT id, nom, detail FROM maille WHERE genre = 'region' ORDER BY nom"
        ).fetchall()
    if parent_id is None:
        return []
    return conn.execute(
        """
        SELECT id, nom, detail FROM maille
        WHERE genre = ? AND parent_id = ?
        ORDER BY nom
        """,
        (genre, parent_id),
    ).fetchall()


def libelle_maille(ligne):
    if ligne["detail"]:
        return f'{ligne["nom"]} ({ligne["detail"]})'
    return ligne["nom"]


def sous_requete(ancre_id):
    if ancre_id is None:
        return "SELECT id FROM maille", ()
    return (
        """
        WITH RECURSIVE sous(id) AS (
            SELECT id FROM maille WHERE id = ?
            UNION ALL
            SELECT m.id FROM maille m JOIN sous s ON m.parent_id = s.id
        )
        SELECT id FROM sous
        """,
        (ancre_id,),
    )
