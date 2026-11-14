"""Accueil, connexion, et pages des blocs qui ne sont pas encore construits."""

from mahh.db import base
from mahh.droits import exiger_connexion
from mahh.presentation import jeton_cache, page
from mahh.reponse import Redirection
from mahh.securite import (
    cookie_jeton,
    cookie_session,
    cookie_session_vide,
    fermer_sessions,
    nouveau_jeton,
    ouvrir_session,
    url_sure,
    verifier_ou_factice,
)
from mahh.texte import echapper


def accueil(ctx):
    exiger_connexion(ctx)
    corps = """
    <h1>Application du ministère</h1>
    <p class="chapeau">Une seule application, quatre blocs. Deux sont en service dans ce socle.
    La collecte des ordures, le SEG et le SNAPE sont décrits et ne sont pas encore des écrans.
    La page d’instructions suit le circuit du ministre au chef de cabinet, au secrétaire général, puis aux directions.</p>
    <div class="cartes">
      <article class="carte">
        <p class="etat etat-ouvert">En service</p>
        <h2>Gestion documentaire</h2>
        <p>Dossiers et fichiers dans l’arbre des directions, avec des privilèges par groupe.</p>
        <a class="bouton" href="/directions">Ouvrir les directions</a>
      </article>
      <article class="carte">
        <p class="etat etat-ouvert">En service</p>
        <h2>Tableau de bord du BSD</h2>
        <p>Registre des projets, filtres et indicateurs. Le jeu chargé au départ est un exemple fictif.</p>
        <a class="bouton" href="/bsd">Ouvrir le tableau de bord</a>
      </article>
      <article class="carte">
        <p class="etat etat-ferme">Pas construit</p>
        <h2>Collecte des ordures</h2>
        <p>Abonnement, paiement, tournées et signalement. Le périmètre est écrit, l’écran n’existe pas.</p>
        <a class="bouton secondaire" href="/prevu/ordures">Lire le périmètre</a>
      </article>
      <article class="carte">
        <p class="etat etat-ferme">Pas construit</p>
        <h2>Eau, SEG et SNAPE</h2>
        <p>SEG en ville, SNAPE en zone rurale. Demande, abonnement et indicateurs : pas encore construits.</p>
        <a class="bouton secondaire" href="/prevu/eau">Lire le périmètre</a>
      </article>
    </div>
    """
    return page("Accueil", corps, ctx, actif="accueil")


def page_connexion(ctx, erreur=None, statut=200):
    if ctx.utilisateur is not None:
        return Redirection(url_sure(ctx.requete.get("suivant")))
    suivant = url_sure(ctx.requete.get("suivant") or ctx.formulaire.get("suivant") or "/")
    corps = (
        "<h1>Connexion</h1>"
        "<p>Accès réservé aux comptes créés par l’administrateur.</p>"
        '<form method="post" action="/connexion" class="formulaire">'
        + jeton_cache(ctx)
        + f'<input type="hidden" name="suivant" value="{echapper(suivant)}">'
        + '<label for="identifiant">Identifiant</label>'
        + '<input id="identifiant" name="identifiant" required autocomplete="username">'
        + '<label for="mot">Mot de passe</label>'
        + '<input id="mot" name="mot_de_passe" type="password" required autocomplete="current-password">'
        + '<button type="submit">Se connecter</button></form>'
    )
    return page("Connexion", corps, ctx, erreur=erreur, statut=statut)


def action_connexion(ctx):
    identifiant = ctx.formulaire.get("identifiant", "")
    mot = ctx.formulaire.get("mot_de_passe", "")
    with base() as conn:
        personne = conn.execute(
            "SELECT * FROM utilisateur WHERE lower(identifiant) = lower(?)",
            (identifiant.strip(),),
        ).fetchone()
        stocke = personne["mot_de_passe"] if personne else None
        if not verifier_ou_factice(mot, stocke) or personne is None or not personne["actif"]:
            return page_connexion(ctx, erreur="Identifiant ou mot de passe incorrect.", statut=401)
        jeton = ouvrir_session(conn, personne["id"])
    ctx.cookies.append(cookie_session(jeton))
    ctx.cookies.append(cookie_jeton(nouveau_jeton()))
    return Redirection(url_sure(ctx.formulaire.get("suivant") or "/"))


def action_deconnexion(ctx):
    if ctx.utilisateur is not None:
        with base() as conn:
            fermer_sessions(conn, ctx.utilisateur["id"])
    ctx.cookies.append(cookie_session_vide())
    ctx.cookies.append(cookie_jeton(nouveau_jeton()))
    return Redirection("/connexion")


def page_ordures(ctx):
    exiger_connexion(ctx)
    corps = """
    <h1>Collecte des ordures</h1>
    <p class="bandeau bandeau-vide">Ce module n’est pas construit dans ce socle.</p>
    <p>Le périmètre demandé, pour une suite, est le suivant.</p>
    <ul>
      <li>Abonnement en ligne et paiement.</li>
      <li>Relevé GPS de l’abonné à l’inscription.</li>
      <li>Rattachement au secteur : région, préfecture, sous-préfecture ou commune, quartier ou district, secteur ou village.</li>
      <li>Signalement « poubelle pleine » hors jour de collecte, avec des frais supplémentaires possibles selon la PME.</li>
      <li>PME gérées par les communes et le gouvernorat. Une PME peut couvrir plusieurs secteurs. Le sigle PME n’est pas développé dans la note.</li>
      <li>Points de collecte de l’ANASP, avec GPS.</li>
      <li>Agents qui se localisent pour la tournée.</li>
      <li>Jours, heures et contact communiqués à l’avance à l’abonné.</li>
      <li>Effectifs et trajets du jour suivis par la PME.</li>
    </ul>
    """
    return page("Collecte des ordures", corps, ctx, actif="accueil")


def page_eau(ctx):
    exiger_connexion(ctx)
    corps = """
    <h1>Eau : SEG et SNAPE</h1>
    <p class="bandeau bandeau-vide">Ce module n’est pas construit dans ce socle.</p>
    <p>SEG reste le sigle de la note, situé par le commanditaire sur la distribution d’eau en ville.
    Le SNAPE, Service national d’aménagement des points d’eau, est situé en zone rurale.
    Ces deux écrans métier n’existent pas encore. Aucun taux et aucun site ne sont affichés.</p>
    <p>Pour chacune, la suite demandée est : une demande en ligne, un abonnement en ligne,
    et un tableau de bord. Ce tableau comprend le taux d’abonnement et les sites d’approvisionnement,
    demandés en plus de la note, ainsi que les libellés déjà écrits pour SEG et pour SNAPE.</p>
    """
    return page("Eau", corps, ctx, actif="accueil")
