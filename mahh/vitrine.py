"""Page publique : présentation, actualités, communiqués. La cellule de communication les modifie."""

from datetime import date

from mahh.db import base
from mahh.droits import exiger_connexion, peut_gerer_vitrine
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import echapper, fmt_date
from mahh.validation import bloc, ligne

GENRES = (
    ("presentation", "Présentation"),
    ("actualite", "Actualité"),
    ("communique", "Communiqué"),
)
LIBELLES = dict(GENRES)


def rendu_public(ctx):
    with base() as conn:
        blocs = _blocs(conn)
    entree = ""
    if ctx.utilisateur is None:
        entree = '<p><a class="bouton" href="/connexion">Se connecter à l’espace de travail</a></p>'
    elif peut_gerer_vitrine(ctx.utilisateur):
        entree = '<p><a class="bouton" href="/communication">Modifier la page publique</a></p>'
    return (
        "<h1>Accueil</h1>"
        + '<p class="chapeau">Présentation, actualités et communiqués du ministère.</p>'
        + entree
        + _rubrique("presentation", "Présentation", blocs)
        + _rubrique("actualite", "Actualités", blocs)
        + _rubrique("communique", "Communiqués", blocs)
    )


def page_edition(ctx, erreur=None):
    _exiger(ctx)
    with base() as conn:
        blocs = _blocs(conn)
    parties = [
        "<h1>Communication</h1>",
        "<p class=\"chapeau\">La cellule de communication crée, modifie et retire les blocs "
        "de la page publique. Une direction ne gère pas cette page.</p>",
        '<p><a href="/">Voir la page publique</a></p>',
    ]
    for genre, libelle in GENRES:
        cartes = []
        for bloc_public in blocs:
            if bloc_public["genre"] != genre:
                continue
            cartes.append(_forme_bloc(ctx, bloc_public))
        parties.append(
            f'<section data-rubrique="{genre}"><h2>{echapper(libelle)}</h2>{"".join(cartes)}</section>'
        )
    parties.append(_forme_creation(ctx))
    return page("Communication", "".join(parties), ctx, actif="communication", erreur=erreur)


def action_creer(ctx):
    _exiger(ctx)
    try:
        genre, titre, texte, publie_le = _saisie(ctx.formulaire, creation=True)
    except ValeurRefusee as exc:
        return page_edition(ctx, erreur=exc.message)
    with base() as conn:
        ordre = conn.execute(
            "SELECT COALESCE(MAX(ordre), 0) + 1 AS n FROM bloc_public WHERE genre = ?",
            (genre,),
        ).fetchone()["n"]
        conn.execute(
            """
            INSERT INTO bloc_public (genre, titre, texte, publie_le, ordre, exemple, cree_le, modifie_le)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (genre, titre, texte, publie_le, ordre, maintenant(), maintenant()),
        )
    return Redirection("/communication?message=bloc-cree")


def action_modifier(ctx, bloc_id):
    _exiger(ctx)
    try:
        _, titre, texte, publie_le = _saisie(ctx.formulaire, creation=False)
    except ValeurRefusee as exc:
        return page_edition(ctx, erreur=exc.message)
    with base() as conn:
        actuel = _un(conn, bloc_id)
        if actuel is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conn.execute(
            """
            UPDATE bloc_public
            SET titre = ?, texte = ?, publie_le = ?, exemple = 0, modifie_le = ?
            WHERE id = ?
            """,
            (titre, texte, publie_le, maintenant(), actuel["id"]),
        )
    return Redirection("/communication?message=bloc-modifie")


def action_retirer(ctx, bloc_id):
    _exiger(ctx)
    with base() as conn:
        actuel = _un(conn, bloc_id)
        if actuel is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conn.execute("DELETE FROM bloc_public WHERE id = ?", (actuel["id"],))
    return Redirection("/communication?message=bloc-retire")


def _exiger(ctx):
    exiger_connexion(ctx)
    if not peut_gerer_vitrine(ctx.utilisateur):
        raise Interdit("La page publique est rédigée par la cellule de communication. Une direction ne la modifie pas.")


def _blocs(conn):
    return conn.execute(
        """
        SELECT * FROM bloc_public
        ORDER BY
            CASE genre WHEN 'presentation' THEN 0 WHEN 'actualite' THEN 1 ELSE 2 END,
            publie_le DESC,
            ordre,
            id
        """
    ).fetchall()


def _un(conn, bloc_id):
    try:
        identifiant = int(bloc_id)
    except (TypeError, ValueError):
        return None
    return conn.execute("SELECT * FROM bloc_public WHERE id = ?", (identifiant,)).fetchone()


def _rubrique(genre, titre, blocs):
    articles = []
    for bloc_public in blocs:
        if bloc_public["genre"] != genre:
            continue
        articles.append(
            f'<article class="publication" data-bloc="{int(bloc_public["id"])}" data-genre="{genre}">'
            f'<p class="meta">{echapper(fmt_date(bloc_public["publie_le"]))}</p>'
            f'<h3>{echapper(bloc_public["titre"])}</h3>'
            f'<p>{echapper(bloc_public["texte"])}</p>'
            "</article>"
        )
    if not articles:
        articles.append("<p>Aucun texte publié. La cellule de communication le rédige.</p>")
    return f'<section class="rubrique" data-rubrique="{genre}"><h2>{echapper(titre)}</h2>{"".join(articles)}</section>'


def _forme_bloc(ctx, bloc_public):
    identifiant = int(bloc_public["id"])
    return (
        f'<form method="post" action="/communication/{identifiant}" class="formulaire" '
        f'data-bloc="{identifiant}" data-genre="{echapper(bloc_public["genre"])}">'
        + jeton_cache(ctx)
        + f'<p class="meta">{echapper(LIBELLES[bloc_public["genre"]])}</p>'
        + '<label for="titre-' + str(identifiant) + '">Titre</label>'
        + f'<input id="titre-{identifiant}" name="titre" required maxlength="160" value="{echapper(bloc_public["titre"])}">'
        + '<label for="date-' + str(identifiant) + '">Date</label>'
        + f'<input id="date-{identifiant}" name="publie_le" type="date" required value="{echapper(bloc_public["publie_le"])}">'
        + '<label for="texte-' + str(identifiant) + '">Texte</label>'
        + f'<textarea id="texte-{identifiant}" name="texte" required maxlength="4000">{echapper(bloc_public["texte"])}</textarea>'
        + '<button type="submit">Enregistrer</button></form>'
        + f'<form method="post" action="/communication/{identifiant}/retirer" class="formulaire">'
        + jeton_cache(ctx)
        + '<button type="submit" class="secondaire">Retirer</button></form>'
    )


def _forme_creation(ctx):
    options = "".join(
        f'<option value="{cle}">{echapper(libelle)}</option>' for cle, libelle in GENRES
    )
    return (
        "<h2>Nouveau bloc</h2>"
        '<form method="post" action="/communication" class="formulaire" data-creation="1">'
        + jeton_cache(ctx)
        + '<label for="genre">Rubrique</label>'
        + f'<select id="genre" name="genre" required>{options}</select>'
        + '<label for="titre-nouveau">Titre</label>'
        + '<input id="titre-nouveau" name="titre" required maxlength="160">'
        + '<label for="date-nouveau">Date</label>'
        + '<input id="date-nouveau" name="publie_le" type="date" required>'
        + '<label for="texte-nouveau">Texte</label>'
        + '<textarea id="texte-nouveau" name="texte" required maxlength="4000"></textarea>'
        + '<button type="submit">Publier</button></form>'
    )


def _saisie(formulaire, creation):
    genre = (formulaire.get("genre") or "").strip()
    if creation and genre not in LIBELLES:
        raise ValeurRefusee("La rubrique n’est pas reconnue.")
    titre = ligne(formulaire.get("titre"), 2, 160, "Titre")
    texte = bloc(formulaire.get("texte"), 2, 4000, "Texte")
    publie_le = ligne(formulaire.get("publie_le"), 10, 10, "Date")
    try:
        date.fromisoformat(publie_le)
    except ValueError as exc:
        raise ValeurRefusee("La date n’est pas reconnue.") from exc
    return genre, titre, texte, publie_le
