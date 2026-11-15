"""Accueil, connexion, et pages des blocs qui ne sont pas encore construits."""

from mahh.db import base
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
        entree = (
            '<p><a class="bouton" href="/connexion">Se connecter</a></p>'
            "<p>Après la connexion, cette page reste la première.</p>"
        )
    else:
        entree = ""
    corps = entree + """
    <h1>Accueil</h1>
    <p class="chapeau">Première page après la connexion. Quatre blocs, puis la page d’instructions.</p>
    <p class="bandeau bandeau-exemple" data-accueil="exemples">Les projets affichés sont des exemples fictifs.
    Ce ne sont pas les projets du ministère, et les totaux ne sont pas des chiffres officiels.</p>
    <h2>Les quatre blocs</h2>
    <div class="cartes">
      <article class="carte" data-bloc="directions">
        <p class="etat etat-ouvert">En service</p>
        <h2>Directions et dossiers</h2>
        <p>Dossiers et fichiers de toutes les directions, dans l’arbre de la note.</p>
        <a class="bouton" href="/directions">Ouvrir les directions</a>
      </article>
      <article class="carte" data-bloc="bsd">
        <p class="etat etat-ouvert">En service</p>
        <h2>Tableau du BSD</h2>
        <p>Suivi des projets. Le code d’un projet ouvre son dossier.</p>
        <a class="bouton" href="/bsd">Ouvrir le tableau de bord</a>
      </article>
      <article class="carte" data-bloc="ordures">
        <p class="etat etat-ouvert">En service</p>
        <h2>Collecte des ordures</h2>
        <p>Abonnement, paiement, tournées et signalement. Le jeu chargé au départ est un exemple fictif.</p>
        <a class="bouton" href="/ordures">Ouvrir la collecte</a>
      </article>
      <article class="carte" data-bloc="eau">
        <p class="etat etat-ouvert">En service</p>
        <h2>SEG et SNAPE</h2>
        <p>SEG en ville, SNAPE en zone rurale. Demande, abonnement et tableaux. Le jeu chargé est un exemple fictif.</p>
        <a class="bouton" href="/eau">Ouvrir l’eau</a>
      </article>
    </div>
    <h2>Instructions</h2>
    <article class="carte" data-bloc="instructions">
      <p>Page destinée aux écrans du ministère : du ministre au chef de cabinet,
      au secrétaire général, puis aux directions et services.</p>
      <a class="bouton" href="/instructions">Ouvrir les instructions</a>
    </article>
    """
    return page("Accueil", corps, ctx, actif="accueil")


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

