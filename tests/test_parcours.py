"""Parcours administrateur et contrôles du jeu d'exemple."""

import os
import re
import sys
import tempfile
import threading
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

os.environ["MAHH_DATA"] = tempfile.mkdtemp(prefix="mahh-test-")
os.environ["MAHH_ADMIN_MOT_DE_PASSE"] = "admin-socle-2026"
os.environ["MAHH_PORT"] = "0"
os.environ["MAHH_HOST"] = "127.0.0.1"
os.environ["MAHH_SILENCIEUX"] = "1"

from mahh.calculs import points_attention, synthese
from mahh.seed import projets_exemples
from mahh.config import hote as adresse_ecoute
from mahh.serveur import nouveau_serveur
from mahh.texte import fmt_pourcent


def verifie(condition, message):
    if not condition:
        raise SystemExit(message)


def indicateurs_exemples():
    resume = synthese(projets_exemples())
    verifie(resume["nombre"] == 18, "18 projets")
    verifie(resume["budget"] == Decimal("4590"), "budget 4590")
    verifie(resume["decaisse"].quantize(Decimal("0.01")) == Decimal("2103.05"), "décaissé")
    verifie(fmt_pourcent(resume["avancement"]) == "45,5\u00a0%", "avancement")
    verifie(fmt_pourcent(resume["decaissement"]) == "45,8\u00a0%", "décaissement")
    verifie(resume["en_cours"] == 12, "en cours")
    verifie(resume["retard"] == 3, "retard")
    verifie(resume["retard_ou_risque"] == 6, "retard ou risque")
    verifie(resume["termines"] == 3, "terminés")
    budgets = {ligne["statut"]: ligne["budget"] for ligne in resume["par_statut"]}
    verifie(budgets["Terminé"] == Decimal("245"), "budget terminé")
    verifie(budgets["Dans les délais"] == Decimal("2465"), "budget délais")
    verifie(budgets["À risque"] == Decimal("325"), "budget risque")
    verifie(budgets["En retard"] == Decimal("1060"), "budget retard")
    verifie(budgets["Suspendu"] == Decimal("110"), "budget suspendu")
    verifie(budgets["En préparation"] == Decimal("385"), "budget préparation")
    secteurs = {ligne["secteur"]: ligne for ligne in resume["par_secteur"]}
    verifie(secteurs["Assainissement"]["budget"] == Decimal("1155"), "budget assainissement")
    verifie(fmt_pourcent(secteurs["Assainissement"]["avancement"]) == "53,9\u00a0%", "avancement assainissement")
    verifie(fmt_pourcent(secteurs["Hydraulique"]["decaissement"]) == "40,5\u00a0%", "décaissement hydraulique")
    verifie(fmt_pourcent(secteurs["Hydrocarbures"]["avancement"]) == "44,8\u00a0%", "avancement hydrocarbures")
    ordre = [p["code"] for p in points_attention(projets_exemples())]
    verifie(
        ordre == ["HYC-03", "ASS-02", "HYD-03", "HYD-02", "HYC-04", "ASS-06"],
        "ordre des points d'attention " + str(ordre),
    )


class Client:
    def __init__(self, hote, numero):
        self.hote = hote
        self.numero = numero
        self.cookies = {}

    def appel(self, methode, chemin, formulaire=None, fichier=None, suivre=True):
        emplacements = []
        for _ in range(6):
            statut, en_tetes, corps = self._une_fois(methode, chemin, formulaire, fichier)
            self._cookies(en_tetes)
            if suivre and statut in (301, 302, 303, 307, 308):
                loc = en_tetes.get("Location")
                emplacements.append(loc)
                chemin = loc
                methode = "GET"
                formulaire = None
                fichier = None
                continue
            return statut, chemin, corps, emplacements
        raise SystemExit("trop de redirections")

    def _une_fois(self, methode, chemin, formulaire, fichier):
        conn = HTTPConnection(self.hote, self.numero, timeout=20)
        en_tetes = {}
        if self.cookies:
            en_tetes["Cookie"] = "; ".join(f"{cle}={valeur}" for cle, valeur in self.cookies.items())
        corps = None
        if fichier is not None:
            corps, type_contenu = fichier
            en_tetes["Content-Type"] = type_contenu
            en_tetes["Content-Length"] = str(len(corps))
        elif formulaire is not None:
            corps = urlencode(formulaire).encode("utf-8")
            en_tetes["Content-Type"] = "application/x-www-form-urlencoded"
            en_tetes["Content-Length"] = str(len(corps))
        conn.request(methode, chemin, body=corps, headers=en_tetes)
        reponse = conn.getresponse()
        contenu = reponse.read()
        conn.close()
        return reponse.status, reponse.headers, contenu.decode("utf-8", errors="replace")

    def _cookies(self, en_tetes):
        for brut in en_tetes.get_all("Set-Cookie") or []:
            nom, _, reste = brut.partition("=")
            valeur = reste.split(";", 1)[0]
            if "Max-Age=0" in brut:
                self.cookies.pop(nom, None)
            else:
                self.cookies[nom] = valeur


def jeton(html):
    trouve = re.search(r'name="jeton" value="([a-f0-9]+)"', html)
    verifie(trouve is not None, "jeton absent")
    return trouve.group(1)


def indiquer(html, cle):
    trouve = re.search(rf'data-indicateur="{cle}"[^>]*>([^<]+)', html)
    verifie(trouve is not None, f"indicateur {cle} absent")
    return trouve.group(1).strip()


def attribut(html, cle, nom):
    trouve = re.search(rf'data-indicateur="{cle}"[^>]*data-{nom}="([^"]*)"', html)
    if trouve is None:
        trouve = re.search(rf'data-{nom}="([^"]*)"[^>]*data-indicateur="{cle}"', html)
    verifie(trouve is not None, f"attribut {nom} de {cle} absent")
    return trouve.group(1)


def fichier_multipart(champs, nom_fichier, contenu):
    borne = "----SocleTest"
    morceaux = []
    for cle, valeur in champs.items():
        morceaux.append(
            f'--{borne}\r\nContent-Disposition: form-data; name="{cle}"\r\n\r\n{valeur}\r\n'.encode()
        )
    morceaux.append(
        (
            f'--{borne}\r\nContent-Disposition: form-data; name="fichier"; filename="{nom_fichier}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        + contenu
        + b"\r\n"
    )
    morceaux.append(f"--{borne}--\r\n".encode())
    return b"".join(morceaux), f"multipart/form-data; boundary={borne}"


def _nav(html):
    trouve = re.search(r'<nav class="navigation">(.*?)</nav>', html, re.S)
    return trouve.group(1) if trouve else ""


def _menu_contient(html, hrefs):
    nav = _nav(html)
    return all(f'href="{href}"' in nav for href in hrefs)


def parcours(hote, numero):
    admin = Client(hote, numero)
    anonyme = Client(hote, numero)
    statut, _, page, _ = anonyme.appel("GET", "/")
    verifie(statut == 200 and "<h1>Accueil</h1>" in page and "<nav" not in page, "accueil public sans session")
    verifie('data-rubrique="presentation"' in page and 'data-rubrique="actualite"' in page, "présentation et actualités")
    verifie('data-rubrique="communique"' in page and "Plan de mobilisation des parties prenantes" in page, "communiqués publics")
    verifie("République de Guinée" in page and "Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures" in page, "en-tête du ministère")
    verifie("Texte d’exemple" not in page and "exemple fictif" not in page, "plus de mention d’exemple")
    verifie("ne sont pas ceux" not in page and "ne sont pas celles" not in page, "bannière retirée")
    verifie("data-accueil=\"public\"" not in page, "bannière publique retirée")
    verifie('href="/connexion"' in page, "lien vers la connexion")
    verifie('href="/directions"' not in page and 'href="/bsd"' not in page and 'href="/ordures"' not in page, "pas de menu métier")
    verifie('href="/eau/seg"' not in page and 'href="/eau/snape"' not in page and 'href="/instructions"' not in page, "eau et instructions fermées")
    for ferme in ("/directions", "/bsd", "/instructions", "/ordures", "/eau", "/eau/seg", "/eau/snape"):
        statut, _, page, _ = anonyme.appel("GET", ferme)
        verifie(statut == 200 and "<h1>Connexion</h1>" in page and "<nav" not in page, f"{ferme} fermé sans session")
    statut, _, page, _ = anonyme.appel("GET", "/connexion")
    verifie(statut == 200 and "<h1>Connexion</h1>" in page, "écran de connexion seul")
    verifie("<nav" not in page, "pas de menu sur la connexion")
    verifie("Tableau de bord" not in page and "SEG" not in page and "SNAPE" not in page, "pas d’entrées métier")
    statut, chemin, page, _ = admin.appel("GET", "/connexion")
    verifie(statut == 200, f"connexion {statut}")
    statut, chemin, page, _ = admin.appel(
        "POST",
        "/connexion",
        {"identifiant": "admin", "mot_de_passe": "admin-socle-2026", "jeton": jeton(page), "suivant": "/"},
    )
    verifie(statut == 200 and "<h1>Accueil</h1>" in page, "accueil après connexion")
    verifie("Directions et dossiers" in page and "Tableau du BSD" in page, "blocs en service")
    verifie("Collecte des ordures" in page and ">SEG<" in page and ">SNAPE<" in page, "blocs eau séparés")
    verifie("Ouvrir les instructions" in page, "accès aux instructions depuis l’accueil")
    verifie("Les projets affichés sont des exemples" in page, "rappel exemples")
    verifie("Pas construit" not in page, "les quatre blocs sont en service")
    verifie('href="/ordures"' in page and "Ouvrir la collecte" in page, "accueil ouvre la collecte")
    verifie('href="/eau/seg"' in page and 'href="/eau/snape"' in page, "accueil ouvre SEG et SNAPE")
    verifie(_menu_contient(page, ("/directions", "/bsd", "/instructions", "/ordures", "/eau/seg", "/eau/snape")), "menu complet de la hiérarchie")
    _, _, ailleurs, _ = admin.appel("GET", "/bsd")
    verifie('class="nav nav-accueil"' in ailleurs, "accès accueil depuis le tableau")
    _, _, retour, _ = admin.appel("GET", "/")
    verifie("<h1>Accueil</h1>" in retour, "retour à l’accueil")

    statut, chemin, page, _ = admin.appel("GET", "/directions")
    verifie("Cellule informatique" not in page, "la cellule du classeur n'est pas une structure")
    verifie("Direction nationale" not in page, "les directions du classeur ne sont pas dans l'arbre")
    anasp = re.search(r'href="/noeud/(\d+)" data-nom="ANASP"', page)
    dga = re.search(r'href="/noeud/(\d+)" data-nom="DGA"', page)
    verifie(anasp and dga, "ANASP et DGA")
    statut, _, page, _ = admin.appel("GET", f"/noeud/{dga.group(1)}")
    verifie("n’est pas établi" in page, "DGA : sigle non établi")
    statut, _, page, _ = admin.appel("GET", f"/noeud/{anasp.group(1)}")
    verifie("Agence nationale d’assainissement et de la salubrité publique" in page, "ANASP développé")
    verifie(statut == 200, "page ANASP")
    verifie("<li>Organigramme</li>" not in page and "<li>Attribution</li>" not in page, "ces libellés ne sont plus des lignes")
    verifie('data-fonction="organigramme"' in page and 'data-fonction="attribution"' in page, "fonctions sur la direction")
    verifie('data-direction="ANASP"' in page and "Nombre de ZTT" in page, "menu ANASP et indicateurs")
    verifie("Libellés de la note, repris tels quels" not in page, "plus de liste brute")
    anasp_poste = re.search(r'data-poste="(\d+)" data-nom="ANASP"', page)
    verifie(anasp_poste is not None, "case ANASP")
    _, _, schema, _ = admin.appel(
        "POST",
        "/organigramme",
        {
            "nom": "Inspection",
            "intitule": "Contrôle interne",
            "parent_id": anasp_poste.group(1),
            "retour": "/directions",
            "jeton": jeton(page),
        },
    )
    verifie('data-nom="Inspection"' in schema and 'data-organigramme="1"' in schema, "case ajoutée au schéma")
    inspection = re.search(r'data-poste="(\d+)" data-nom="Inspection"', schema)
    _, _, schema, _ = admin.appel(
        "POST",
        f"/organigramme/{inspection.group(1)}",
        {
            "nom": "Inspection générale",
            "intitule": "Contrôle interne",
            "parent_id": anasp_poste.group(1),
            "retour": "/directions",
            "jeton": jeton(schema),
        },
    )
    verifie('data-nom="Inspection générale"' in schema, "case modifiée")
    _, _, schema, _ = admin.appel(
        "POST",
        "/attribution",
        {
            "noeud_id": anasp.group(1),
            "texte": "Veiller à la salubrité des communes",
            "retour": "/directions",
            "jeton": jeton(schema),
        },
    )
    verifie("Veiller à la salubrité des communes" in schema, "attribution ajoutée")
    attribution_id = re.search(r'data-attribution="(\d+)"', schema).group(1)
    _, _, schema, _ = admin.appel(
        "POST",
        f"/attribution/{attribution_id}",
        {
            "texte": "Organiser la salubrité des communes",
            "retour": "/directions",
            "jeton": jeton(schema),
        },
    )
    verifie("Organiser la salubrité des communes" in schema and "<details" in schema, "attribution modifiée dans le menu")

    statut, chemin, page, _ = admin.appel(
        "POST",
        f"/noeud/{anasp.group(1)}/dossier",
        {"nom": "Dossier ouvert", "jeton": jeton(page)},
    )
    verifie(statut == 200 and "Dossier ouvert" in page, "dossier créé")
    ouvert = re.search(r"/noeud/(\d+)", chemin).group(1)
    _, _, page_anasp, _ = admin.appel("GET", f"/noeud/{anasp.group(1)}")
    _, chemin_ferme, _, _ = admin.appel(
        "POST",
        f"/noeud/{anasp.group(1)}/dossier",
        {"nom": "Dossier fermé", "jeton": jeton(page_anasp)},
    )
    ferme = re.search(r"/noeud/(\d+)", chemin_ferme).group(1)

    statut, _, page, _ = admin.appel(
        "POST",
        f"/noeud/{anasp.group(1)}/supprimer",
        {"jeton": jeton(page_anasp)},
    )
    verifie(statut == 403, f"structure protégée {statut}")

    _, _, page, _ = admin.appel("GET", "/groupes")
    _, chemin, page, _ = admin.appel(
        "POST",
        "/groupes",
        {"nom": "Groupe documentation", "jeton": jeton(page)},
    )
    groupe = re.search(r"/groupes/(\d+)", chemin).group(1)
    verifie("Groupe documentation" in page, "groupe créé")

    _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
    admin.appel(
        "POST",
        "/utilisateurs",
        {
            "identifiant": "agent",
            "nom": "Agent de test",
            "mot_de_passe": "agent-socle-2026",
            "jeton": jeton(page_users),
        },
    )
    _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
    admin.appel(
        "POST",
        "/utilisateurs",
        {
            "identifiant": "visiteur",
            "nom": "Visiteur",
            "mot_de_passe": "visiteur-socle-2026",
            "jeton": jeton(page_users),
        },
    )
    _, _, page, _ = admin.appel("GET", f"/groupes/{groupe}")
    option = re.search(r'<option value="(\d+)" data-identifiant="agent">', page)
    verifie(option is not None, "agent dans la liste")
    admin.appel(
        "POST",
        f"/groupes/{groupe}/membre",
        {"utilisateur_id": option.group(1), "jeton": jeton(page)},
    )
    _, _, page, _ = admin.appel("GET", f"/groupes/{groupe}")
    admin.appel(
        "POST",
        f"/groupes/{groupe}/droit",
        {
            "noeud_id": ouvert,
            "creer": "on",
            "consulter": "on",
            "modifier": "on",
            "supprimer": "on",
            "jeton": jeton(page),
        },
    )
    _, _, page, _ = admin.appel("GET", f"/groupes/{groupe}")
    verifie(f'data-noeud="{ouvert}"' in page, "droit enregistré")
    verifie("créer" in page and "supprimer" in page, "les quatre privilèges s'affichent")
    admin.appel(
        "POST",
        f"/groupes/{groupe}/bsd",
        {"consulter_bsd": "on", "jeton": jeton(page)},
    )

    statut, _, refuse, _ = admin.appel(
        "POST",
        "/groupes",
        {"nom": "Sans jeton"},
        suivre=False,
    )
    verifie(statut == 403 and "expiré" in refuse, "jeton refusé")

    _, _, bsd, _ = admin.appel("GET", "/bsd")
    verifie("Ce ne sont pas les projets du ministère" in bsd, "bannière exemple")
    verifie("pas des chiffres officiels" in bsd, "chiffres non officiels")
    verifie(indiquer(bsd, "projets") == "18", "écran : 18 projets")
    verifie(indiquer(bsd, "en-cours") == "12", "écran : en cours")
    verifie(attribut(bsd, "budget", "montant") == "4590.00", "écran : budget")
    verifie(attribut(bsd, "decaisse", "montant") == "2103.05", "écran : décaissé")
    verifie(attribut(bsd, "avancement", "taux") == "45.5", "écran : avancement")
    verifie(attribut(bsd, "decaissement", "taux") == "45.8", "écran : décaissement")
    verifie('data-bandeau="exemple"' in bsd, "bandeau exemple")
    attention = re.search(r'data-attention>(.*?)</ol>', bsd, re.S).group(1)
    verifie(
        re.findall(r'data-code="([^"]+)"', attention)
        == ["HYC-03", "ASS-02", "HYD-03", "HYD-02", "HYC-04", "ASS-06"],
        "ordre à l'écran",
    )
    _, _, filtre, _ = admin.appel("GET", "/bsd?secteur=Hydraulique")
    verifie(indiquer(filtre, "projets") == "6", "filtre hydraulique")
    verifie("ASS-01" not in filtre, "filtre hydraulique sans assainissement")
    _, _, cellule, _ = admin.appel(
        "GET", "/bsd?direction=Cellule%20informatique%20et%20statistiques"
    )
    verifie(indiquer(cellule, "projets") == "1", "filtre direction")
    verifie("HYC-04" in cellule and "HYC-01" not in cellule, "seule la cellule")
    _, _, vide, _ = admin.appel("GET", "/bsd?secteur=Administration")
    verifie(indiquer(vide, "projets") == "0", "administration vide")
    verifie('data-bandeau="vide"' in vide, "filtre vide")

    _, _, saisie, _ = admin.appel("GET", "/bsd/saisie")
    _, chemin, fiche, _ = admin.appel(
        "POST",
        "/bsd/saisie",
        {
            "code": "TEST-01",
            "secteur": "Administration",
            "titre": "Projet saisi pour l'essai",
            "localisation": "Conakry",
            "statut": "En préparation",
            "budget": "10",
            "decaissement": "0",
            "avancement": "0",
            "debut": "2026-11-14",
            "echeance": "2027-11-14",
            "responsable": "BSD",
            "financement": "Budget national",
            "jalon": "Note de cadrage",
            "observations": "Saisie de test, hors du jeu d'exemple.",
            "jeton": jeton(saisie),
        },
    )
    verifie('data-genre="saisie"' in fiche, "la saisie n'est pas un exemple")
    projet_id = re.search(r"/bsd/projet/(\d+)", chemin).group(1)
    _, _, melange, _ = admin.appel("GET", "/bsd")
    verifie('data-bandeau="mixte"' in melange, "le total mélange exemple et saisie")
    _, _, saisie, _ = admin.appel("GET", f"/bsd/projet/{projet_id}")
    admin.appel(
        "POST",
        f"/bsd/projet/{projet_id}/supprimer",
        {"jeton": jeton(saisie)},
    )
    _, _, retour, _ = admin.appel("GET", "/bsd")
    verifie(indiquer(retour, "projets") == "18", "retour à 18 après suppression")

    parcours_ordures(admin, hote, numero)
    parcours_eau(admin, hote, numero)

    agent = Client(hote, numero)
    _, _, page, _ = agent.appel("GET", "/connexion")
    _, _, page, _ = agent.appel(
        "POST",
        "/connexion",
        {"identifiant": "agent", "mot_de_passe": "agent-socle-2026", "jeton": jeton(page)},
    )
    _, _, anasp_agent, _ = agent.appel("GET", f"/noeud/{anasp.group(1)}")
    verifie('data-dossier="Dossier ouvert"' in anasp_agent, "dossier visible")
    verifie("Dossier fermé" not in anasp_agent, "dossier fermé caché")
    statut, _, _, _ = agent.appel("GET", f"/noeud/{ferme}")
    verifie(statut == 403, "accès au dossier fermé refusé")
    _, _, dossier, _ = agent.appel("GET", f"/noeud/{ouvert}")
    verifie("creer consulter modifier supprimer" in dossier, "privilèges de l'agent")
    statut, _, _, _ = agent.appel("GET", "/groupes")
    verifie(statut == 403, "groupes réservés à l'administrateur")
    corps, type_contenu = fichier_multipart({"jeton": jeton(dossier)}, "note.txt", b"Piece de demonstration")
    statut, _, apres, _ = agent.appel("POST", f"/noeud/{ouvert}/fichier", fichier=(corps, type_contenu))
    verifie(statut == 200 and "note.txt" in apres, "fichier déposé")
    fichier_id = re.search(r'href="/fichier/(\d+)"', apres).group(1)
    statut, _, telecharge, _ = agent.appel("GET", f"/fichier/{fichier_id}")
    verifie(statut == 200 and telecharge == "Piece de demonstration", "téléchargement")
    _, _, accueil_agent, _ = agent.appel("GET", "/")
    verifie(_menu_contient(accueil_agent, ("/directions", "/bsd")), "menu de l’agent documentaire")
    verifie("/ordures" not in _nav(accueil_agent) and "/eau/seg" not in _nav(accueil_agent), "l’agent ne voit pas ordures ni SEG")
    verifie("/instructions" not in _nav(accueil_agent), "l’agent sans direction ne voit pas les instructions")
    _, _, bsd_agent, _ = agent.appel("GET", "/bsd")
    verifie(statut_ok(bsd_agent), "l'agent consulte le BSD")
    verifie("ASS-01" not in bsd_agent, "l'agent sans direction ne voit pas les projets")
    verifie(indiquer(bsd_agent, "projets") == "0", "registre vide pour l'agent")

    visiteur = Client(hote, numero)
    _, _, page, _ = visiteur.appel("GET", "/connexion")
    visiteur.appel(
        "POST",
        "/connexion",
        {"identifiant": "visiteur", "mot_de_passe": "visiteur-socle-2026", "jeton": jeton(page)},
    )
    statut, _, _, _ = visiteur.appel("GET", f"/fichier/{fichier_id}")
    verifie(statut == 403, "téléchargement refusé sans droit")
    _, _, accueil_visiteur, _ = visiteur.appel("GET", "/")
    verifie(
        "/directions" not in _nav(accueil_visiteur)
        and "/bsd" not in _nav(accueil_visiteur)
        and "/ordures" not in _nav(accueil_visiteur)
        and "/eau/" not in _nav(accueil_visiteur)
        and "/instructions" not in _nav(accueil_visiteur),
        "le visiteur n’a pas de menu métier",
    )
    verifie('href="/compte"' in _nav(accueil_visiteur) and 'href="/"' in _nav(accueil_visiteur), "accueil et compte seuls")
    verifie('data-bloc="ordures"' not in accueil_visiteur and 'data-bloc="bsd"' not in accueil_visiteur, "pas de cartes")
    statut, _, page, _ = visiteur.appel("GET", "/bsd")
    verifie(statut == 403, "BSD refusé sans privilège")
    statut, _, _, _ = visiteur.appel("GET", "/ordures")
    verifie(statut == 403, "ordures refusées sans privilège")
    statut, _, _, _ = visiteur.appel("GET", "/eau/seg")
    verifie(statut == 403, "SEG refusé sans privilège")
    statut, _, _, _ = visiteur.appel("GET", "/instructions")
    verifie(statut == 403, "instructions refusées sans direction")
    _, _, anasp_visiteur, _ = visiteur.appel("GET", f"/noeud/{anasp.group(1)}")
    verifie("Dossier ouvert" not in anasp_visiteur, "le visiteur ne voit pas le dossier")

    _, _, css, _ = admin.appel("GET", "/statique/style.css")
    verifie(".tricolore" in css, "feuille de style")

    _, _, registre, _ = admin.appel("GET", "/bsd")
    verifie("Un clic sur le code ouvre" in registre, "le code ouvre le dossier")
    lien = re.search(r'href="(/bsd/projet/\d+)">ASS-01', registre)
    verifie(lien is not None, "code cliquable")
    _, _, dossier, _ = admin.appel("GET", lien.group(1))
    verifie("Notes" in dossier and "Rapports" in dossier, "notes et rapports")
    verifie("Classement des documents physiques" in dossier, "classement physique")
    _, _, dossier, _ = admin.appel(
        "POST",
        lien.group(1) + "/piece",
        {
            "genre": "note",
            "titre": "Note de suivi",
            "texte": "Texte de la note de test.",
            "cote": "",
            "emplacement": "",
            "jeton": jeton(dossier),
        },
    )
    verifie("Note de suivi" in dossier and "Texte de la note de test." in dossier, "note ajoutée")

    _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
    admin.appel(
        "POST",
        "/utilisateurs",
        {
            "identifiant": "bsd",
            "nom": "Bureau de stratégie",
            "mot_de_passe": "bsd-socle-2026",
            "fonction": "bsd",
            "jeton": jeton(page_users),
        },
    )
    bsd_compte = Client(hote, numero)
    _, _, page, _ = bsd_compte.appel("GET", "/connexion")
    bsd_compte.appel(
        "POST",
        "/connexion",
        {"identifiant": "bsd", "mot_de_passe": "bsd-socle-2026", "jeton": jeton(page)},
    )
    _, _, bsd_vue, _ = bsd_compte.appel("GET", "/bsd")
    verifie(indiquer(bsd_vue, "projets") == "18", "le BSD voit tous les projets")
    verifie("ASS-01" in bsd_vue, "le BSD voit ASS-01")

    _, _, directions, _ = admin.appel("GET", "/directions")
    dga = re.search(r'/noeud/(\d+)" data-nom="DGA"', directions).group(1)
    _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
    admin.appel(
        "POST",
        "/utilisateurs",
        {
            "identifiant": "anasp",
            "nom": "Direction ANASP",
            "mot_de_passe": "anasp-socle-2026",
            "structure_id": anasp.group(1),
            "jeton": jeton(page_users),
        },
    )
    _, _, saisie, _ = admin.appel("GET", "/bsd/saisie")
    _, chemin, _, _ = admin.appel(
        "POST",
        "/bsd/saisie",
        {
            "code": "TEST-02",
            "secteur": "Assainissement",
            "titre": "Projet rattaché à l'ANASP",
            "localisation": "Conakry",
            "statut": "En retard",
            "budget": "4",
            "decaissement": "10",
            "avancement": "10",
            "debut": "2026-01-01",
            "echeance": "2026-06-01",
            "responsable": "ANASP",
            "financement": "Budget national",
            "jalon": "Rapport",
            "observations": "Rattachement explicite pour l'essai.",
            "structure_id": anasp.group(1),
            "jeton": jeton(saisie),
        },
    )
    projet_anasp = re.search(r"/bsd/projet/(\d+)", chemin).group(1)

    direction = Client(hote, numero)
    _, _, page, _ = direction.appel("GET", "/connexion")
    direction.appel(
        "POST",
        "/connexion",
        {"identifiant": "anasp", "mot_de_passe": "anasp-socle-2026", "jeton": jeton(page)},
    )
    _, _, accueil_direction, _ = direction.appel("GET", "/")
    verifie(_menu_contient(accueil_direction, ("/directions", "/bsd", "/instructions", "/ordures")), "menu ANASP")
    verifie("/eau/seg" not in _nav(accueil_direction) and "/eau/snape" not in _nav(accueil_direction), "ANASP sans SEG ni SNAPE")
    verifie('data-bloc="seg"' not in accueil_direction and 'data-bloc="snape"' not in accueil_direction, "cartes eau cachées")
    _, _, vue, _ = direction.appel("GET", "/bsd")
    verifie("TEST-02" in vue and "ASS-01" not in vue, "la direction ne voit que son projet")
    verifie(indiquer(vue, "projets") == "1", "un seul projet pour la direction")
    _, _, ses_directions, _ = direction.appel("GET", "/directions")
    verifie('data-nom="ANASP"' in ses_directions, "sa structure")
    verifie('data-nom="DGA"' not in ses_directions and 'data-nom="SEG"' not in ses_directions, "pas les autres")
    verifie("Organiser la salubrité des communes" in ses_directions, "son menu d’attributions")
    verifie("Inspection générale" in ses_directions, "la case ajoutée sous sa direction")
    verifie("Construire l’organigramme" not in ses_directions, "l’outil reste à l’administrateur")
    _, _, compte, _ = direction.appel("GET", "/compte")
    statut, _, _, _ = direction.appel(
        "POST",
        "/organigramme",
        {"nom": "Case refusée", "retour": "/directions", "jeton": jeton(compte)},
        suivre=False,
    )
    verifie(statut == 403, "une direction ne construit pas l’organigramme")
    statut, _, _, _ = direction.appel("GET", lien.group(1))
    verifie(statut == 403, "projet d'exemple refusé à la direction")

    _, _, ecran, _ = admin.appel("GET", "/instructions")
    verifie('data-echelon="ministre"' in ecran and 'data-echelon="chef_cabinet"' in ecran, "circuit")
    verifie('data-echelon="secretaire_general"' in ecran and 'data-echelon="directions"' in ecran, "circuit complet")
    verifie("Sommer d’avancer" in ecran, "sommation depuis la page")
    _, _, ecran, _ = admin.appel(
        "POST",
        "/instructions",
        {
            "echelon": "ministre",
            "texte": "Note du ministre pour le cabinet de test.",
            "jeton": jeton(ecran),
        },
    )
    verifie("Note du ministre pour le cabinet de test." in ecran, "instruction publiée")
    _, _, ecran, _ = admin.appel("GET", "/instructions")
    admin.appel(
        "POST",
        "/instructions/sommation",
        {
            "structure_id": anasp.group(1),
            "projet_id": projet_anasp,
            "texte": "Avancer le dossier de test ANASP.",
            "jeton": jeton(ecran),
        },
    )
    _, _, ecran, _ = admin.appel("GET", "/instructions")
    admin.appel(
        "POST",
        "/instructions/sommation",
        {
            "structure_id": dga,
            "texte": "Sommation adressée à la DGA seule.",
            "jeton": jeton(ecran),
        },
    )
    _, _, vue_direction, _ = direction.appel("GET", "/instructions")
    verifie("Avancer le dossier de test ANASP." in vue_direction, "sommation reçue")
    verifie("Sommation adressée à la DGA seule." not in vue_direction, "sommation des autres cachée")
    verifie("Note du ministre pour le cabinet de test." not in vue_direction, "instruction du cabinet cachée")
    verifie('data-retard="TEST-02"' in vue_direction, "retard de la direction")
    statut, _, _, _ = direction.appel(
        "POST",
        "/instructions/sommation",
        {"structure_id": anasp.group(1), "texte": "Une direction ne somme pas.", "jeton": jeton(vue_direction)},
    )
    verifie(statut == 403, "la direction ne somme pas")
    parcours_vitrine(admin, direction, hote, numero)


def parcours_vitrine(admin, direction, hote, numero):
    _, _, utilisateurs, _ = admin.appel("GET", "/utilisateurs")
    verifie('value="communication"' in utilisateurs, "l’administrateur peut accorder le rôle")
    admin.appel(
        "POST",
        "/utilisateurs",
        {
            "identifiant": "cellule",
            "nom": "Cellule de communication",
            "mot_de_passe": "cellule-page-2026",
            "fonction": "communication",
            "jeton": jeton(utilisateurs),
        },
    )
    cellule = Client(hote, numero)
    _, _, formulaire, _ = cellule.appel("GET", "/connexion")
    _, _, accueil_cellule, _ = cellule.appel(
        "POST",
        "/connexion",
        {"identifiant": "cellule", "mot_de_passe": "cellule-page-2026", "jeton": jeton(formulaire)},
    )
    verifie('href="/communication"' in _nav(accueil_cellule), "la cellule voit la communication")
    verifie("/ordures" not in _nav(accueil_cellule) and "/eau/seg" not in _nav(accueil_cellule), "la cellule n’a pas le menu métier")
    _, _, edition, _ = cellule.appel("GET", "/communication")
    bloc = re.search(
        r'data-bloc="(\d+)" data-genre="communique"',
        edition,
    )
    verifie(bloc is not None, "un communiqué est éditable")
    _, _, apres, _ = cellule.appel(
        "POST",
        f"/communication/{bloc.group(1)}",
        {
            "titre": "Avis modifié par la cellule",
            "publie_le": "2026-11-12",
            "texte": "Communiqué réécrit par la cellule de communication. Texte fictif.",
            "jeton": jeton(edition),
        },
    )
    verifie("Avis modifié par la cellule" in apres, "la cellule a modifié le communiqué")
    anonyme = Client(hote, numero)
    _, _, public, _ = anonyme.appel("GET", "/")
    verifie("Avis modifié par la cellule" in public, "le communiqué modifié est public")
    verifie("<nav" not in public, "le visiteur ne voit toujours pas le menu")
    statut, _, refuse, _ = direction.appel("GET", "/communication")
    verifie(statut == 403, "une direction n’ouvre pas la communication")
    _, _, accueil_direction, _ = direction.appel("GET", "/")
    statut, _, _, _ = direction.appel(
        "POST",
        f"/communication/{bloc.group(1)}",
        {
            "titre": "Une direction ne réécrit pas",
            "publie_le": "2026-11-12",
            "texte": "Tentative refusée.",
            "jeton": jeton(accueil_direction),
        },
        suivre=False,
    )
    verifie(statut == 403, "une direction ne modifie pas le communiqué")


def parcours_ordures(admin, hote, numero):
    public = Client(hote, numero)
    statut, _, _, _ = public.appel("GET", "/ordures", suivre=False)
    verifie(statut in (302, 303), "ordures fermé sans session")
    statut, _, _, _ = public.appel("GET", "/ordures/abonnement", suivre=False)
    verifie(statut in (302, 303), "abonnement fermé sans session")
    _, _, page, _ = admin.appel("GET", "/ordures")
    verifie("<h1>Collecte des ordures</h1>" in page, "module ordures pour l’ANASP et la hiérarchie")
    verifie("ne sont pas ceux du ministère" in page, "bannière exemple ordures")
    verifie("S’abonner" in page, "abonnement en ligne")
    _, _, formulaire, _ = admin.appel("GET", "/ordures/abonnement")
    option = re.search(r'<option value="(\d+)">([^<]*Secteur A)</option>', formulaire)
    verifie(option is not None, "chaîne de rattachement")
    verifie("Région exemple" in option.group(2) and "Préfecture exemple" in option.group(2), "région et préfecture")
    verifie("Commune exemple" in option.group(2) and "Quartier Nord" in option.group(2), "commune et quartier")
    _, chemin, fiche, _ = admin.appel(
        "POST",
        "/ordures/abonnement",
        {
            "nom": "Fatou Diallo",
            "telephone": "622 00 00 13",
            "secteur_id": option.group(1),
            "latitude": "9,641500",
            "longitude": "-13.578500",
            "jeton": jeton(formulaire),
        },
    )
    verifie("/ordures/a/ORD-" in chemin, "référence d’abonnement")
    verifie("9.641500" in fiche and "-13.578500" in fiche, "GPS enregistré")
    verifie("Sous-préfecture ou commune" in fiche and "Secteur ou village" in fiche, "maillage affiché")
    verifie("mardi" in fiche and "620 00 00 01" in fiche, "jours et contact communiqués")
    verifie('data-paye="0"' in fiche, "paiement encore ouvert")
    reference = chemin.rstrip("/").split("/")[-1].split("?")[0]
    _, _, fiche, _ = admin.appel(
        "POST",
        f"/ordures/a/{reference}/payer",
        {"jeton": jeton(fiche)},
    )
    verifie('data-paye="1"' in fiche, "paiement enregistré")
    _, _, fiche, _ = admin.appel(
        "POST",
        f"/ordures/a/{reference}/signalement",
        {"jeton": jeton(fiche)},
    )
    verifie("poubelle pleine" in fiche.lower() or "Poubelle pleine" in fiche or "data-hors-jour" in fiche, "signalement")
    verifie('data-hors-jour="' in fiche, "hors jour indiqué")
    _, _, exemple, _ = admin.appel("GET", "/ordures/a/ORD-EX-01")
    verifie('data-genre="exemple"' in exemple and "Aïssatou Bah" in exemple, "exemple et agent")
    statut, _, _, _ = public.appel("GET", "/ordures/pme", suivre=False)
    verifie(statut in (302, 303), "le suivi PME demande un compte")

    _, _, pme, _ = admin.appel("GET", "/ordures/pme")
    verifie('data-pme="PME Alpha"' in pme and 'data-gestion="commune"' in pme, "PME de commune")
    verifie('data-pme="PME Bêta"' in pme and 'data-gestion="gouvernorat"' in pme, "PME du gouvernorat")
    verifie("Secteur A" in pme and "Secteur B" in pme, "plusieurs secteurs pour une PME")
    verifie("Effectif du jour" in pme and "Secteur A, puis Secteur B" in pme, "effectif et trajet")
    _, _, points, _ = admin.appel("GET", "/ordures/points")
    verifie("Point ANASP Nord" in points and 'data-exemple="1"' in points, "point ANASP avec pastille")
    verifie("9.641200" in points, "GPS du point")
    _, _, fiche, _ = admin.appel("GET", f"/ordures/a/{reference}")
    _, _, fiche, _ = admin.appel(
        "POST",
        f"/ordures/a/{reference}/passage",
        {
            "agent": "Mamadou Camara",
            "latitude": "9.641510",
            "longitude": "-13.578510",
            "heure": "8 h 05",
            "jeton": jeton(fiche),
        },
    )
    verifie("Mamadou Camara" in fiche and "9.641510" in fiche, "agent localisé chez l’abonné")


def parcours_eau(admin, hote, numero):
    public = Client(hote, numero)
    statut, _, _, _ = public.appel("GET", "/eau", suivre=False)
    verifie(statut in (302, 303), "eau fermé sans session")
    statut, _, _, _ = public.appel("GET", "/eau/demande", suivre=False)
    verifie(statut in (302, 303), "demande d’eau fermée sans session")
    _, _, page, _ = admin.appel("GET", "/eau")
    verifie("SEG" in page and "SNAPE" in page, "module eau pour la hiérarchie")
    verifie("ne sont pas ceux du ministère" in page, "bannière exemple eau")
    _, _, seg, _ = admin.appel("GET", "/eau/seg")
    verifie('data-abonnes="5"' in seg and 'data-taux-abonnement="33.3"' in seg, "taux d’abonnement SEG")
    verifie('data-sites="3"' in seg and 'data-villes="2"' in seg, "sites et villes")
    verifie('data-desserte="53.3"' in seg, "taux de desserte")
    verifie('data-facturation="80.0"' in seg and 'data-recouvrement="62.5"' in seg, "facturation et recouvrement")
    verifie('data-produit="1000"' in seg and 'data-distribue="800"' in seg, "volumes")
    verifie('data-ville="Ville Alpha"' in seg and 'data-ville="Ville Bêta"' in seg, "liste des villes")
    verifie("Nombre d’abonné" in seg and "Taux de desserte urbain" in seg, "libellés SEG de la note")
    _, _, snape, _ = admin.appel("GET", "/eau/snape")
    verifie('data-villages="2"' in snape and 'data-points="3"' in snape, "villages et points")
    verifie('data-village="Village Nord"' in snape and 'data-couverte="250"' in snape, "population couverte")
    verifie('data-forages="2"' in snape and "realisés" in snape, "points realisés, graphie de la note")
    statut, _, _, _ = public.appel("GET", "/eau/seg", suivre=False)
    verifie(statut in (302, 303), "le tableau SEG demande un compte")

    _, _, directions, _ = admin.appel("GET", "/directions")
    seg_id = re.search(r'/noeud/(\d+)" data-nom="SEG"', directions).group(1)
    snape_id = re.search(r'/noeud/(\d+)" data-nom="SNAPE"', directions).group(1)
    anasp_id = re.search(r'/noeud/(\d+)" data-nom="ANASP"', directions).group(1)
    _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
    jeton_users = jeton(page_users)
    for ident, mot, extra in (
        ("segville", "seg-eau-2026", {"structure_id": seg_id}),
        ("snaperural", "snape-eau-2026", {"structure_id": snape_id}),
        ("anaspvue", "anasp-eau-2026", {"structure_id": anasp_id}),
        ("bsdeau", "bsd-eau-2026xx", {"fonction": "bsd"}),
    ):
        champs = {
            "identifiant": ident,
            "nom": ident,
            "mot_de_passe": mot,
            "jeton": jeton_users,
        }
        champs.update(extra)
        admin.appel("POST", "/utilisateurs", champs)
        _, _, page_users, _ = admin.appel("GET", "/utilisateurs")
        jeton_users = jeton(page_users)

    def compte(ident, mot):
        client = Client(hote, numero)
        _, _, formulaire, _ = client.appel("GET", "/connexion")
        client.appel(
            "POST",
            "/connexion",
            {"identifiant": ident, "mot_de_passe": mot, "jeton": jeton(formulaire)},
        )
        return client

    seg_compte = compte("segville", "seg-eau-2026")
    _, _, accueil_seg, _ = seg_compte.appel("GET", "/")
    verifie(_menu_contient(accueil_seg, ("/directions", "/bsd", "/instructions", "/eau/seg")), "menu du SEG")
    verifie("/ordures" not in _nav(accueil_seg) and "/eau/snape" not in _nav(accueil_seg), "SEG sans ordures ni SNAPE")
    statut, _, _, _ = seg_compte.appel("GET", "/ordures")
    verifie(statut == 403, "le SEG ne voit pas la collecte")
    statut, _, page, _ = seg_compte.appel("GET", "/eau/seg")
    verifie(statut == 200 and "Ville Alpha" in page, "le SEG voit son tableau")
    statut, _, _, _ = seg_compte.appel("GET", "/eau/snape")
    verifie(statut == 403, "le SEG ne voit pas le SNAPE")
    snape_compte = compte("snaperural", "snape-eau-2026")
    _, _, accueil_snape, _ = snape_compte.appel("GET", "/")
    verifie("/eau/snape" in _nav(accueil_snape) and "/eau/seg" not in _nav(accueil_snape), "menu du SNAPE")
    verifie("/ordures" not in _nav(accueil_snape), "SNAPE sans ordures")
    statut, _, page, _ = snape_compte.appel("GET", "/eau/snape")
    verifie(statut == 200 and "Village Nord" in page, "le SNAPE voit son tableau")
    statut, _, _, _ = snape_compte.appel("GET", "/eau/seg")
    verifie(statut == 403, "le SNAPE ne voit pas le SEG")
    autre = compte("anaspvue", "anasp-eau-2026")
    _, _, accueil_anasp, _ = autre.appel("GET", "/")
    verifie("/ordures" in _nav(accueil_anasp) and "/eau/seg" not in _nav(accueil_anasp), "menu ANASP sans SEG")
    statut, _, _, _ = autre.appel("GET", "/eau/seg")
    verifie(statut == 403, "une autre direction ne voit pas le SEG")
    bsd = compte("bsdeau", "bsd-eau-2026xx")
    _, _, accueil_bsd, _ = bsd.appel("GET", "/")
    verifie(
        _menu_contient(accueil_bsd, ("/directions", "/bsd", "/instructions", "/ordures", "/eau/seg", "/eau/snape")),
        "le BSD voit tout le menu",
    )
    statut_seg, _, _, _ = bsd.appel("GET", "/eau/seg")
    statut_snape, _, _, _ = bsd.appel("GET", "/eau/snape")
    verifie(statut_seg == 200 and statut_snape == 200, "le BSD voit les deux tableaux")

    _, _, formulaire, _ = admin.appel("GET", "/eau/demande")
    lieu = re.search(r'<option value="(\d+)">Ville Alpha</option>', formulaire)
    verifie(lieu is not None, "ville SEG proposée")
    _, chemin, fiche, _ = admin.appel(
        "POST",
        "/eau/demande",
        {
            "nom": "Kadiatou Sylla",
            "telephone": "624 00 00 14",
            "lieu_id": lieu.group(1),
            "latitude": "9,652000",
            "longitude": "-13.572000",
            "jeton": jeton(formulaire),
        },
    )
    verifie("/eau/d/EAU-" in chemin and "Ville Alpha" in fiche and "9.652000" in fiche, "demande SEG")
    reference = chemin.rstrip("/").split("/")[-1].split("?")[0]
    _, chemin, fiche, _ = admin.appel(
        "POST",
        f"/eau/d/{reference}/abonner",
        {"jeton": jeton(fiche)},
    )
    verifie("/eau/a/EAU-" in chemin and 'data-paye="0"' in fiche, "abonnement ouvert")
    reference_abonnement = chemin.rstrip("/").split("/")[-1].split("?")[0]
    _, _, fiche, _ = admin.appel(
        "POST",
        f"/eau/a/{reference_abonnement}/payer",
        {"jeton": jeton(fiche)},
    )
    verifie('data-paye="1"' in fiche, "paiement de l’eau enregistré")
    _, _, seg, _ = admin.appel("GET", "/eau/seg")
    verifie('data-abonnes="6"' in seg and 'data-taux-abonnement="40.0"' in seg, "le taux suit le nouvel abonné")
    statut, _, _, _ = snape_compte.appel("GET", f"/eau/a/{reference_abonnement}")
    verifie(statut == 403, "le SNAPE ne voit pas l’abonné du SEG")


def statut_ok(page):
    return "Tableau de bord du BSD" in page


def vitrine_remplace_lexemple():
    import sqlite3

    from mahh.db import SCHEMA, migrer, semer_vitrine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrer(conn)
    conn.execute(
        """
        INSERT INTO bloc_public (genre, titre, texte, publie_le, ordre, exemple, cree_le, modifie_le)
        VALUES ('communique', 'Communiqué de démonstration', 'Texte d’exemple.', '2026-11-10', 1, 1, 'x', 'x')
        """
    )
    conn.execute(
        """
        INSERT INTO bloc_public (genre, titre, texte, publie_le, ordre, exemple, cree_le, modifie_le)
        VALUES ('actualite', 'Note de la cellule', 'Texte conservé par la cellule.', '2026-11-11', 1, 0, 'x', 'x')
        """
    )
    semer_vitrine(conn)
    demo = conn.execute(
        "SELECT titre, texte, exemple FROM bloc_public WHERE genre = 'communique'"
    ).fetchone()
    verifie(demo["exemple"] == 0, "l’ancien communiqué n’est plus un exemple")
    verifie("démonstration" not in demo["titre"] and "Texte d’exemple" not in demo["texte"], "le texte d’exemple est remplacé")
    garde = conn.execute(
        "SELECT texte FROM bloc_public WHERE titre = 'Note de la cellule'"
    ).fetchone()
    verifie(garde["texte"] == "Texte conservé par la cellule.", "la cellule conserve son texte")
    css = (RACINE / "mahh" / "statique" / "style.css").read_text(encoding="utf-8")
    verifie(".marque" in css and "text-align: center" in css, "l’en-tête est centré")


def main():
    indicateurs_exemples()
    vitrine_remplace_lexemple()
    verifie(adresse_ecoute() == "127.0.0.1", "le test reste sur la boucle locale")
    os.environ.pop("MAHH_HOST")
    verifie(adresse_ecoute() == "0.0.0.0", "écoute par défaut sur toutes les interfaces")
    os.environ["MAHH_HOST"] = "127.0.0.1"
    serveur = nouveau_serveur()
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    hote, numero = serveur.server_address
    try:
        parcours(hote, numero)
    finally:
        serveur.shutdown()
        serveur.server_close()
    print("Parcours vérifié.")


if __name__ == "__main__":
    main()
