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
os.environ["MAHH_HOTE"] = "127.0.0.1"
os.environ["MAHH_SILENCIEUX"] = "1"

from mahh.calculs import points_attention, synthese
from mahh.seed import projets_exemples
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


def parcours(hote, numero):
    admin = Client(hote, numero)
    statut, chemin, page, _ = admin.appel("GET", "/connexion")
    verifie(statut == 200, f"connexion {statut}")
    statut, chemin, page, _ = admin.appel(
        "POST",
        "/connexion",
        {"identifiant": "admin", "mot_de_passe": "admin-socle-2026", "jeton": jeton(page), "suivant": "/"},
    )
    verifie(statut == 200 and "Application du ministère" in page, "accueil après connexion")
    verifie(page.count("Pas construit") == 2, "deux blocs non construits")

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

    _, _, ordures, _ = admin.appel("GET", "/prevu/ordures")
    verifie("n’est pas construit" in ordures and "poubelle pleine" in ordures, "ordures")
    verifie("sous-préfecture" in ordures, "maillage ordures")
    _, _, eau, _ = admin.appel("GET", "/prevu/eau")
    verifie("n’est pas construit" in eau and "taux d’abonnement" in eau, "eau")
    verifie("sites d’approvisionnement" in eau and "en ville" in eau, "SEG ville")

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
    statut, _, page, _ = visiteur.appel("GET", "/bsd")
    verifie(statut == 403, "BSD refusé sans privilège")
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
    _, _, vue, _ = direction.appel("GET", "/bsd")
    verifie("TEST-02" in vue and "ASS-01" not in vue, "la direction ne voit que son projet")
    verifie(indiquer(vue, "projets") == "1", "un seul projet pour la direction")
    _, _, ses_directions, _ = direction.appel("GET", "/directions")
    verifie('data-nom="ANASP"' in ses_directions, "sa structure")
    verifie('data-nom="DGA"' not in ses_directions and 'data-nom="SEG"' not in ses_directions, "pas les autres")
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


def statut_ok(page):
    return "Tableau de bord du BSD" in page


def main():
    indicateurs_exemples()
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
