"""Accueil, connexion, et pages des blocs qui ne sont pas encore construits."""

from mahh.db import base
from mahh.droits import (
    peut_voir_bsd,
    peut_voir_directions,
    peut_voir_instructions,
    peut_voir_ordures,
    peut_voir_seg,
    peut_voir_snape,
)
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
    if ctx.utilisateur is None:
        from mahh.site_public import accueil_public

        return page("Accueil", accueil_public(ctx), ctx, actif="accueil")
    cartes = []
    instructions = False
    if ctx.utilisateur is not None:
        with base() as conn:
            cartes = _cartes(conn, ctx.utilisateur)
            instructions = peut_voir_instructions(ctx.utilisateur)
    blocs = ""
    if cartes:
        blocs = (
            "<h2>Entrées ouvertes à votre compte</h2>"
            f'<div class="cartes">{"".join(cartes)}</div>'
        )
    bloc_instructions = ""
    if instructions:
        bloc_instructions = """
    <h2>Instructions</h2>
    <article class="carte" data-bloc="instructions">
      <p>Page destinée aux écrans du ministère : du ministre au chef de cabinet,
      au secrétaire général, puis aux directions et services.</p>
      <a class="bouton" href="/instructions">Ouvrir les instructions</a>
    </article>
    """
    espace = f"""
    <h1>Accueil</h1>
    <h2>Espace de travail</h2>
    <p class="chapeau">Seules les entrées de votre compte sont affichées.</p>
    {blocs}
    {bloc_instructions}
    """
    return page("Accueil", espace, ctx, actif="accueil")


def _cartes(conn, utilisateur):
    cartes = []
    if peut_voir_directions(conn, utilisateur):
        cartes.append(
            """
      <article class="carte" data-bloc="directions">
        <p class="etat etat-ouvert">En service</p>
        <h2>Directions et dossiers</h2>
        <p>Dossiers et fichiers ouverts à votre compte, dans l’arbre de la note.</p>
        <a class="bouton" href="/directions">Ouvrir les directions</a>
      </article>
            """
        )
    if peut_voir_bsd(conn, utilisateur):
        cartes.append(
            """
      <article class="carte" data-bloc="bsd">
        <p class="etat etat-ouvert">En service</p>
        <h2>Tableau du BSD</h2>
        <p>Suivi des projets qui vous concernent. Le code d’un projet ouvre son dossier.</p>
        <a class="bouton" href="/bsd">Ouvrir le tableau de bord</a>
      </article>
            """
        )
    if peut_voir_ordures(conn, utilisateur):
        cartes.append(
            """
      <article class="carte" data-bloc="ordures">
        <p class="etat etat-ouvert">En service</p>
        <h2>Collecte des ordures</h2>
        <p>Abonnement, paiement, tournées et signalement. L’ANASP y enregistre les localités, les PME et les abonnés.</p>
        <a class="bouton" href="/ordures">Ouvrir la collecte</a>
      </article>
            """
        )
    if peut_voir_seg(conn, utilisateur):
        cartes.append(
            """
      <article class="carte" data-bloc="seg">
        <p class="etat etat-ouvert">En service</p>
        <h2>SEG</h2>
        <p>Distribution d’eau en ville. Le SEG y indique les villes, les sites et les abonnements.</p>
        <a class="bouton" href="/eau/seg">Ouvrir le SEG</a>
      </article>
            """
        )
    if peut_voir_snape(conn, utilisateur):
        cartes.append(
            """
      <article class="carte" data-bloc="snape">
        <p class="etat etat-ouvert">En service</p>
        <h2>SNAPE</h2>
        <p>Forages en zone rurale. Le SNAPE y indique les villages, la population couverte et les points d’eau.</p>
        <a class="bouton" href="/eau/snape">Ouvrir le SNAPE</a>
      </article>
            """
        )
    return cartes


def page_connexion(ctx, erreur=None, statut=200):
    if ctx.utilisateur is not None:
        return Redirection("/")
    suivant = url_sure(ctx.requete.get("suivant") or ctx.formulaire.get("suivant") or "/")
    corps = (
        "<h1>Connexion</h1>"
        "<p>Accès réservé aux comptes créés par l’administrateur. "
        "Après la connexion, la première page est l’accueil.</p>"
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
    return Redirection("/")


def action_deconnexion(ctx):
    if ctx.utilisateur is not None:
        with base() as conn:
            fermer_sessions(conn, ctx.utilisateur["id"])
    ctx.cookies.append(cookie_session_vide())
    ctx.cookies.append(cookie_jeton(nouveau_jeton()))
    return Redirection("/connexion")

