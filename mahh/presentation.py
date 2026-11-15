"""Habillage HTML commun. Les textes affichés passent par echapper."""

from mahh.reponse import Html
from mahh.texte import echapper

AVIS = {
    "dossier-cree": "Le dossier a été créé.",
    "fichier-ajoute": "Le fichier a été ajouté.",
    "renomme": "Le nom a été modifié.",
    "supprime": "La suppression est faite.",
    "groupe-cree": "Le groupe a été créé.",
    "membre-ajoute": "La personne a été ajoutée au groupe.",
    "membre-retire": "La personne a été retirée du groupe.",
    "droit-enregistre": "Les privilèges du groupe ont été enregistrés.",
    "bsd-enregistre": "Le privilège du tableau de bord a été enregistré.",
    "utilisateur-cree": (
        "Le compte a été créé. Transmettez le mot de passe par un canal sûr, "
        "puis demandez à la personne de le changer."
    ),
    "utilisateur-desactive": "Le compte a été désactivé.",
    "mot-de-passe-change": "Le mot de passe a été changé. Connectez-vous à nouveau.",
    "projet-cree": "Le projet a été ajouté au registre. Il n’est pas marqué exemple.",
    "projet-modifie": "Le projet a été modifié.",
    "projet-supprime": "Le projet a été retiré du registre.",
    "projet-rattache": "Le rattachement a été enregistré.",
    "piece-ajoutee": "L’élément a été ajouté au dossier du projet.",
    "instruction-creee": "L’instruction a été publiée.",
    "sommation-creee": "La direction a été sommée d’avancer.",
    "abonnement-cree": "L’abonnement est enregistré. Le paiement ne l’est pas encore.",
    "paiement-enregistre": "Le paiement a été enregistré.",
    "signalement-enregistre": "Le signalement « poubelle pleine » a été enregistré.",
    "passage-enregistre": "La position de l’agent a été enregistrée.",
    "suivi-enregistre": "Le suivi du jour a été enregistré.",
    "demande-eau-creee": "La demande d’eau est enregistrée.",
    "abonnement-eau-cree": "L’abonnement d’eau est ouvert. Le paiement ne l’est pas encore.",
    "paiement-eau-enregistre": "Le paiement de l’abonnement d’eau a été enregistré.",
    "bloc-cree": "Le bloc a été publié sur la page publique.",
    "bloc-modifie": "Le bloc a été modifié.",
    "bloc-retire": "Le bloc a été retiré de la page publique.",
}


def lire_avis(code):
    if not code:
        return None
    return AVIS.get(code)


def jeton_cache(ctx):
    return f'<input type="hidden" name="jeton" value="{echapper(ctx.jeton)}">'


def page(titre, corps, ctx, actif=None, erreur=None, statut=200):
    utilisateur = ctx.utilisateur
    if utilisateur is None:
        navigation = ""
        if ctx.chemin == "/connexion":
            session = ""
        else:
            session = (
                '<div class="session">'
                '<a class="bouton" href="/connexion">Se connecter</a>'
                "</div>"
            )
    else:
        from mahh.db import base
        from mahh.droits import entrees_menu

        with base() as conn:
            liens = entrees_menu(conn, utilisateur)
        elements = []
        for href, libelle, cle in liens:
            classe = " nav-accueil" if cle == "accueil" else ""
            if cle == actif:
                classe += " actif"
            elements.append(
                f'<a class="nav{classe}" href="{href}">{echapper(libelle)}</a>'
            )
        navigation = '<nav class="navigation">' + "".join(elements) + "</nav>"
        session = (
            '<div class="session">'
            f'<p>{echapper(utilisateur["nom"])}</p>'
            f'<form method="post" action="/deconnexion">{jeton_cache(ctx)}'
            '<button type="submit" class="secondaire">Se déconnecter</button>'
            "</form></div>"
        )
    bandeau = ""
    if erreur:
        bandeau += f'<p class="alerte" role="alert">{echapper(erreur)}</p>'
    if ctx.avis and not erreur:
        bandeau += f'<p class="avis" role="status">{echapper(ctx.avis)}</p>'
    document = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{echapper(titre)} — Ministère</title>
  <link rel="stylesheet" href="/statique/style.css">
</head>
<body>
  <div class="tricolore" aria-hidden="true"><i></i><i></i><i></i></div>
  <header class="entete">
    <div class="marque">
      <p class="pays">République de Guinée</p>
      <p class="ministere"><a href="/">Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures</a></p>
    </div>
    {navigation}
    {session}
  </header>
  <main>
    {bandeau}
    {corps}
  </main>
  <footer>
    <p>Socle local. Les projets marqués « exemple » sont fictifs et ne sont pas ceux du ministère.</p>
  </footer>
</body>
</html>"""
    return Html(document, statut)


def page_message(ctx, titre, message, statut):
    corps = f"<h1>{echapper(titre)}</h1><p>{echapper(message)}</p>"
    return page(titre, corps, ctx, statut=statut)
