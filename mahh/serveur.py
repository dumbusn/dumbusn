"""Serveur HTTP du socle. Bibliothèque standard uniquement."""

import os
import re
import sys
import traceback
from datetime import date
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from mahh.accueil import (
    accueil,
    action_connexion,
    action_deconnexion,
    page_connexion,
    page_eau,
)
from mahh.ordures import (
    action_abonnement,
    action_chercher,
    action_passage,
    action_payer,
    action_signalement,
    action_suivi,
    page_abonnement,
    page_abonnes,
    page_fiche,
    page_module,
    page_pme,
    page_points,
    page_prevu,
)
from mahh.administration import (
    action_bsd,
    action_compte,
    action_desactiver,
    action_droit,
    action_groupe,
    action_membre,
    action_retirer,
    action_utilisateur,
    page_compte,
    page_groupe,
    page_groupes,
    page_utilisateurs,
)
from mahh.config import hote, port
from mahh.db import preparer
from mahh.instructions import action_instruction, action_sommation, page_instructions
from mahh.documents import (
    action_dossier,
    action_fichier,
    action_renommer,
    action_supprimer,
    page_directions,
    page_noeud,
    telecharger,
)
from mahh.presentation import lire_avis, page_message
from mahh.reponse import Html, Interdit, NonConnecte, Octets, Redirection
from mahh.securite import (
    cookie_jeton,
    jeton_cookie_acceptable,
    jeton_valide,
    nouveau_jeton,
    utilisateur_par_jeton,
)
from mahh.tableau import (
    action_modifier,
    action_piece,
    action_rattacher,
    action_saisie,
    action_supprimer_projet,
    page_bsd,
    page_modifier,
    page_projet,
    page_saisie,
    telecharger_piece,
)
from pathlib import Path


class Demande:
    def __init__(self):
        self.methode = "GET"
        self.chemin = "/"
        self.requete = {}
        self.formulaire = {}
        self.fichier = None
        self.utilisateur = None
        self.jeton = ""
        self.avis = None
        self.cookies = []
        self.aujourd_hui = date.today()


ROUTES = (
    ("GET", re.compile(r"^/$"), accueil),
    ("GET", re.compile(r"^/connexion$"), page_connexion),
    ("POST", re.compile(r"^/connexion$"), action_connexion),
    ("POST", re.compile(r"^/deconnexion$"), action_deconnexion),
    ("GET", re.compile(r"^/directions$"), page_directions),
    ("GET", re.compile(r"^/noeud/(\d+)$"), page_noeud),
    ("POST", re.compile(r"^/noeud/(\d+)/dossier$"), action_dossier),
    ("POST", re.compile(r"^/noeud/(\d+)/fichier$"), action_fichier),
    ("POST", re.compile(r"^/noeud/(\d+)/renommer$"), action_renommer),
    ("POST", re.compile(r"^/noeud/(\d+)/supprimer$"), action_supprimer),
    ("GET", re.compile(r"^/fichier/(\d+)$"), telecharger),
    ("GET", re.compile(r"^/groupes$"), page_groupes),
    ("POST", re.compile(r"^/groupes$"), action_groupe),
    ("GET", re.compile(r"^/groupes/(\d+)$"), page_groupe),
    ("POST", re.compile(r"^/groupes/(\d+)/membre$"), action_membre),
    ("POST", re.compile(r"^/groupes/(\d+)/retirer$"), action_retirer),
    ("POST", re.compile(r"^/groupes/(\d+)/droit$"), action_droit),
    ("POST", re.compile(r"^/groupes/(\d+)/bsd$"), action_bsd),
    ("GET", re.compile(r"^/utilisateurs$"), page_utilisateurs),
    ("POST", re.compile(r"^/utilisateurs$"), action_utilisateur),
    ("POST", re.compile(r"^/utilisateurs/(\d+)/desactiver$"), action_desactiver),
    ("GET", re.compile(r"^/compte$"), page_compte),
    ("POST", re.compile(r"^/compte$"), action_compte),
    ("GET", re.compile(r"^/bsd$"), page_bsd),
    ("GET", re.compile(r"^/bsd/saisie$"), page_saisie),
    ("POST", re.compile(r"^/bsd/saisie$"), action_saisie),
    ("GET", re.compile(r"^/bsd/projet/(\d+)$"), page_projet),
    ("POST", re.compile(r"^/bsd/projet/(\d+)/piece$"), action_piece),
    ("POST", re.compile(r"^/bsd/projet/(\d+)/rattacher$"), action_rattacher),
    ("GET", re.compile(r"^/piece/(\d+)$"), telecharger_piece),
    ("GET", re.compile(r"^/instructions$"), page_instructions),
    ("POST", re.compile(r"^/instructions$"), action_instruction),
    ("POST", re.compile(r"^/instructions/sommation$"), action_sommation),
    ("GET", re.compile(r"^/bsd/projet/(\d+)/modifier$"), page_modifier),
    ("POST", re.compile(r"^/bsd/projet/(\d+)/modifier$"), action_modifier),
    ("POST", re.compile(r"^/bsd/projet/(\d+)/supprimer$"), action_supprimer_projet),
    ("GET", re.compile(r"^/ordures$"), page_module),
    ("GET", re.compile(r"^/ordures/abonnement$"), page_abonnement),
    ("POST", re.compile(r"^/ordures/abonnement$"), action_abonnement),
    ("POST", re.compile(r"^/ordures/chercher$"), action_chercher),
    ("GET", re.compile(r"^/ordures/pme$"), page_pme),
    ("POST", re.compile(r"^/ordures/pme$"), action_suivi),
    ("GET", re.compile(r"^/ordures/points$"), page_points),
    ("GET", re.compile(r"^/ordures/abonnes$"), page_abonnes),
    ("GET", re.compile(r"^/ordures/a/([A-Za-z0-9-]+)$"), page_fiche),
    ("POST", re.compile(r"^/ordures/a/([A-Za-z0-9-]+)/payer$"), action_payer),
    ("POST", re.compile(r"^/ordures/a/([A-Za-z0-9-]+)/signalement$"), action_signalement),
    ("POST", re.compile(r"^/ordures/a/([A-Za-z0-9-]+)/passage$"), action_passage),
    ("GET", re.compile(r"^/prevu/ordures$"), page_prevu),
    ("GET", re.compile(r"^/prevu/eau$"), page_eau),
    ("GET", re.compile(r"^/statique/style\.css$"), None),
    ("GET", re.compile(r"^/favicon\.ico$"), None),
)


class Gestionnaire(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "SocleMAHH"

    def do_GET(self):
        self._traiter()

    def do_POST(self):
        self._traiter()

    def log_message(self, fmt, *args):
        if os.environ.get("MAHH_SILENCIEUX"):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _traiter(self):
        try:
            self._dispatch()
        except Exception:
            traceback.print_exc()
            corps = (
                "<!DOCTYPE html><html lang=\"fr\"><meta charset=\"utf-8\">"
                "<title>Erreur</title><h1>Erreur</h1>"
                "<p>L’application n’a pas pu traiter cette demande.</p></html>"
            )
            self._envoyer(Html(corps, 500), [])

    def _dispatch(self):
        analyse = urlparse(self.path)
        chemin = analyse.path
        ctx = Demande()
        ctx.methode = self.command
        ctx.chemin = chemin
        ctx.requete = {cle: valeurs[0] for cle, valeurs in parse_qs(analyse.query, keep_blank_values=True).items()}
        ctx.avis = lire_avis(ctx.requete.get("message"))
        cookies = _cookies(self.headers.get("Cookie"))
        jeton = cookies.get("mahh_jeton")
        if not jeton_cookie_acceptable(jeton):
            jeton = nouveau_jeton()
            ctx.cookies.append(cookie_jeton(jeton))
        ctx.jeton = jeton

        if chemin == "/statique/style.css" and self.command == "GET":
            fichier = Path(__file__).resolve().parent / "statique" / "style.css"
            self._envoyer(Octets(fichier.read_bytes(), "text/css; charset=utf-8"), ctx.cookies)
            return
        if chemin == "/favicon.ico" and self.command == "GET":
            self._envoyer(Octets(b"", "image/x-icon", statut=204), ctx.cookies)
            return

        if self.command == "POST":
            try:
                ctx.formulaire, ctx.fichier = _lire_corps(self)
            except ValueError:
                self._envoyer(
                    page_message(ctx, "Demande refusée", "Le formulaire n’a pas pu être lu.", 400),
                    ctx.cookies,
                )
                return
            if not jeton_valide(cookies.get("mahh_jeton"), ctx.formulaire.get("jeton")):
                self._envoyer(
                    page_message(
                        ctx,
                        "Formulaire expiré",
                        "Le formulaire a expiré. Rechargez la page et recommencez.",
                        403,
                    ),
                    ctx.cookies,
                )
                return

        from mahh.db import base

        with base() as conn:
            ctx.utilisateur = utilisateur_par_jeton(conn, cookies.get("mahh_session"))

        resultat = None
        try:
            for methode, motif, fonction in ROUTES:
                if methode != self.command or fonction is None:
                    continue
                trouve = motif.match(chemin)
                if trouve:
                    resultat = fonction(ctx, *trouve.groups())
                    break
            else:
                resultat = page_message(ctx, "Introuvable", "Cette page n’existe pas.", 404)
        except NonConnecte as exc:
            resultat = Redirection("/connexion?suivant=" + _chemin_suivant(exc.chemin))
        except Interdit as exc:
            resultat = page_message(ctx, "Accès refusé", exc.message, 403)
        self._envoyer(resultat, ctx.cookies)

    def _envoyer(self, resultat, cookies):
        if isinstance(resultat, Redirection):
            self.send_response(303)
            self.send_header("Location", resultat.url)
            self._entetes_communs(cookies)
            self.end_headers()
            return
        if isinstance(resultat, Octets):
            self.send_response(resultat.statut)
            self.send_header("Content-Type", resultat.type_mime)
            self.send_header("Content-Length", str(len(resultat.contenu)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if resultat.disposition:
                self.send_header("Content-Disposition", resultat.disposition)
            self._entetes_communs(cookies)
            self.end_headers()
            if resultat.contenu and self.command != "HEAD":
                self.wfile.write(resultat.contenu)
            return
        if not isinstance(resultat, Html):
            resultat = Html("<h1>Erreur</h1>", 500)
        donnees = resultat.corps.encode("utf-8")
        self.send_response(resultat.statut)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self._entetes_communs(cookies)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(donnees)

    def _entetes_communs(self, cookies):
        self.send_header("Cache-Control", "no-store")
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)


def _cookies(en_tete):
    pot = SimpleCookie()
    if en_tete:
        try:
            pot.load(en_tete)
        except CookieError:
            return {}
    return {cle: morsel.value for cle, morsel in pot.items()}


def _chemin_suivant(chemin):
    from urllib.parse import quote

    if not chemin.startswith("/") or chemin.startswith("//"):
        return "/"
    return quote(chemin, safe="/?=&")


def _lire_corps(handler):
    brut = handler.headers.get("Content-Length", "0")
    try:
        longueur = int(brut)
    except ValueError as exc:
        raise ValueError("longueur") from exc
    if longueur < 0 or longueur > 16 * 1024 * 1024:
        raise ValueError("taille")
    corps = handler.rfile.read(longueur) if longueur else b""
    type_contenu = handler.headers.get("Content-Type", "")
    if type_contenu.startswith("application/x-www-form-urlencoded"):
        couples = parse_qs(corps.decode("utf-8", errors="replace"), keep_blank_values=True)
        return {cle: valeurs[0] for cle, valeurs in couples.items()}, None
    if type_contenu.startswith("multipart/form-data"):
        return _multipart(type_contenu, corps)
    if longueur == 0:
        return {}, None
    raise ValueError("type")


def _multipart(type_contenu, corps):
    borne = _frontiere(type_contenu)
    if not borne:
        raise ValueError("frontiere")
    delimiteur = b"--" + borne.encode("utf-8")
    champs = {}
    fichier = None
    for morceau in corps.split(delimiteur):
        if morceau.startswith(b"\r\n"):
            morceau = morceau[2:]
        if morceau.endswith(b"\r\n"):
            morceau = morceau[:-2]
        if not morceau or morceau.startswith(b"--"):
            continue
        entete_brut, separation, contenu = morceau.partition(b"\r\n\r\n")
        if not separation:
            continue
        entete = entete_brut.decode("utf-8", errors="replace")
        disposition = ""
        for ligne in entete.split("\r\n"):
            if ligne.lower().startswith("content-disposition:"):
                disposition = ligne.split(":", 1)[1]
        nom = _parametre(disposition, "name")
        nom_fichier = _parametre(disposition, "filename")
        if not nom:
            continue
        if nom_fichier:
            fichier = (nom_fichier, contenu)
        else:
            champs[nom] = contenu.decode("utf-8", errors="replace")
    return champs, fichier


def _frontiere(type_contenu):
    marqueur = "boundary="
    index = type_contenu.lower().find(marqueur)
    if index < 0:
        return ""
    valeur = type_contenu[index + len(marqueur):].strip()
    if ";" in valeur:
        valeur = valeur.split(";", 1)[0].strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        valeur = valeur[1:-1]
    if not valeur or len(valeur) > 200:
        return ""
    return valeur


def _parametre(disposition, cle):
    if cle == "filename":
        for morceau in disposition.split(";"):
            morceau = morceau.strip()
            if morceau.lower().startswith("filename*="):
                valeur = morceau.split("=", 1)[1].strip()
                if "''" in valeur:
                    valeur = valeur.split("''", 1)[1]
                return unquote(valeur)
    prefixe = cle + "="
    for morceau in disposition.split(";"):
        morceau = morceau.strip()
        if morceau.lower().startswith(prefixe.lower()):
            valeur = morceau.split("=", 1)[1].strip()
            if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                valeur = valeur[1:-1]
            return valeur
    return ""


def nouveau_serveur():
    preparer()
    return ThreadingHTTPServer((hote(), port()), Gestionnaire)


def main():
    try:
        info = preparer()
    except SystemExit:
        raise
    serveur = ThreadingHTTPServer((hote(), port()), Gestionnaire)
    adresse, numero = serveur.server_address
    if info:
        print(f"Administrateur : {info['identifiant']}")
        if info.get("mot"):
            print(f"Mot de passe initial : {info['mot']}")
            print(f"Copie écrite dans : {info['fichier']}")
        else:
            print("Mot de passe : valeur de MAHH_ADMIN_MOT_DE_PASSE, non réaffichée.")
    print(f"Ouvrir http://{adresse}:{numero}/")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        serveur.server_close()
