"""Collecte des ordures. Les lignes exemple restent fictives. PME n’est pas développé."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from secrets import token_hex

from mahh.db import base
from mahh.droits import exiger_connexion, peut_voir_ordures
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import echapper
from mahh.validation import ligne

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
GENRES = {
    "region": "Région",
    "prefecture": "Préfecture",
    "sous_prefecture": "Sous-préfecture ou commune",
    "quartier": "Quartier ou district",
    "secteur": "Secteur ou village",
}
GESTIONS = {"commune": "Commune", "gouvernorat": "Gouvernorat"}
MONTANT_ABONNEMENT = "50000"
BANDEAU = (
    "Jeu d’exemple. Ces lieux, ces PME, ces points et ces abonnés ne sont pas ceux du ministère. "
    "Aucun de ces chiffres n’est officiel. PME reste un sigle : la note ne le développe pas."
)


def _garder(ctx):
    exiger_connexion(ctx)
    with base() as conn:
        if not peut_voir_ordures(conn, ctx.utilisateur):
            raise Interdit("La collecte concerne l’ANASP, la hiérarchie et le BSD.")


def page_module(ctx):
    _garder(ctx)
    with base() as conn:
        nombre = conn.execute("SELECT COUNT(*) AS n FROM abonnement").fetchone()["n"]
        exemples = conn.execute(
            "SELECT COUNT(*) AS n FROM abonnement WHERE exemple = 1"
        ).fetchone()["n"]
    suite = ""
    if ctx.utilisateur is not None:
        suite = (
            "<h2>Suivi</h2>"
            '<p><a class="bouton" href="/ordures/pme">PME, effectifs et trajets</a> '
            '<a class="bouton secondaire" href="/ordures/points">Points de collecte ANASP</a> '
            '<a class="bouton secondaire" href="/ordures/abonnes">Abonnés</a></p>'
        )
    corps = (
        _fil()
        + "<h1>Collecte des ordures</h1>"
        + _bandeau()
        + "<p class=\"chapeau\">Abonnement de la population, paiement, tournée et signalement "
        "« poubelle pleine ». Les jours, les heures et le contact sont communiqués à l’abonné "
        "dès l’inscription.</p>"
        + f'<p data-abonnes="{nombre}" data-exemples="{exemples}">{nombre} abonnement'
        + ("s" if nombre != 1 else "")
        + f", dont {exemples} marqué" + ("s" if exemples != 1 else "") + " exemple.</p>"
        + '<p><a class="bouton" href="/ordures/abonnement">S’abonner</a></p>'
        + _recherche(ctx)
        + suite
    )
    return page("Collecte des ordures", corps, ctx, actif="ordures")


def page_abonnement(ctx, erreur=None, valeurs=None):
    _garder(ctx)
    valeurs = valeurs or {}
    with base() as conn:
        options = _options_secteurs(conn, valeurs.get("secteur_id"))
    corps = (
        _fil()
        + "<h1>Abonnement</h1>"
        + _bandeau()
        + "<p>L’abonné indique son rattachement, du plus large au plus fin, et le relevé GPS "
        "de l’inscription : latitude et longitude. Le montant est enregistré dans l’application. "
        "Ce n’est pas un paiement bancaire.</p>"
        + f"<p>Montant de l’abonnement : {echapper(_fmt_gnf(MONTANT_ABONNEMENT))}.</p>"
        + '<form method="post" action="/ordures/abonnement" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="nom">Nom</label>'
        + f'<input id="nom" name="nom" required maxlength="80" value="{echapper(valeurs.get("nom", ""))}">'
        + '<label for="telephone">Téléphone</label>'
        + f'<input id="telephone" name="telephone" required maxlength="20" value="{echapper(valeurs.get("telephone", ""))}">'
        + '<label for="secteur">Rattachement</label>'
        + f'<select id="secteur" name="secteur_id" required>{options}</select>'
        + '<p class="aide">Chaque ligne suit l’ordre : région, préfecture, sous-préfecture ou commune, '
        "quartier ou district, secteur ou village.</p>"
        + '<label for="latitude">Latitude</label>'
        + f'<input id="latitude" name="latitude" required inputmode="decimal" value="{echapper(valeurs.get("latitude", ""))}">'
        + '<label for="longitude">Longitude</label>'
        + f'<input id="longitude" name="longitude" required inputmode="decimal" value="{echapper(valeurs.get("longitude", ""))}">'
        + '<button type="submit">Enregistrer l’abonnement</button></form>'
    )
    return page("Abonnement", corps, ctx, actif="ordures", erreur=erreur)


def action_abonnement(ctx):
    _garder(ctx)
    try:
        nom = ligne(ctx.formulaire.get("nom"), 2, 80, "Nom")
        telephone = _telephone(ctx.formulaire.get("telephone"))
        latitude = _coordonnee(ctx.formulaire.get("latitude"), Decimal("-90"), Decimal("90"), "Latitude")
        longitude = _coordonnee(ctx.formulaire.get("longitude"), Decimal("-180"), Decimal("180"), "Longitude")
        secteur_id = int(ctx.formulaire.get("secteur_id") or "0")
    except (ValeurRefusee, ValueError) as exc:
        message = exc.message if isinstance(exc, ValeurRefusee) else "Le rattachement n’est pas reconnu."
        return page_abonnement(ctx, erreur=message, valeurs=ctx.formulaire)
    with base() as conn:
        secteur = conn.execute(
            "SELECT id FROM maille WHERE id = ? AND genre = 'secteur'",
            (secteur_id,),
        ).fetchone()
        if secteur is None:
            return page_abonnement(ctx, erreur="Le rattachement n’est pas reconnu.", valeurs=ctx.formulaire)
        pme = conn.execute(
            """
            SELECT pme_id FROM pme_secteur WHERE secteur_id = ? ORDER BY pme_id LIMIT 1
            """,
            (secteur_id,),
        ).fetchone()
        reference = "ORD-" + token_hex(3).upper()
        conn.execute(
            """
            INSERT INTO abonnement (
                reference, nom, telephone, secteur_id, latitude, longitude, pme_id,
                montant_gnf, paye, exemple, cree_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                reference, nom, telephone, secteur_id, latitude, longitude,
                pme["pme_id"] if pme else None, MONTANT_ABONNEMENT, maintenant(),
            ),
        )
    return Redirection(f"/ordures/a/{reference}?message=abonnement-cree")


def page_fiche(ctx, reference, erreur=None):
    _garder(ctx)
    with base() as conn:
        abonne = _abonne(conn, reference)
        if abonne is None:
            return page("Introuvable", "<h1>Introuvable</h1><p>Cette référence n’est pas au registre.</p>", ctx, statut=404)
        chaine = _chaine(conn, abonne["secteur_id"])
        pme = None
        if abonne["pme_id"]:
            pme = conn.execute("SELECT * FROM pme WHERE id = ?", (abonne["pme_id"],)).fetchone()
        passages = conn.execute(
            "SELECT * FROM passage WHERE abonnement_id = ? ORDER BY id DESC",
            (abonne["id"],),
        ).fetchall()
        signalements = conn.execute(
            "SELECT * FROM signalement WHERE abonnement_id = ? ORDER BY id DESC",
            (abonne["id"],),
        ).fetchall()
    hors = _hors_jour(pme, ctx.aujourd_hui)
    corps = (
        _fil()
        + f'<p class="badge-{"exemple" if abonne["exemple"] else "saisie"}" data-genre="{"exemple" if abonne["exemple"] else "saisie"}">'
        + ("exemple fictif" if abonne["exemple"] else "saisie")
        + "</p>"
        + f'<h1>{echapper(abonne["reference"])}</h1>'
        + _bandeau()
        + "<h2>Abonné</h2>"
        + _liste([
            ("Nom", abonne["nom"]),
            ("Téléphone", abonne["telephone"]),
            ("Relevé GPS", f'{abonne["latitude"]}, {abonne["longitude"]}'),
        ])
        + "<h2>Rattachement</h2>"
        + _liste([(GENRES[m["genre"]], m["nom"]) for m in chaine])
        + "<h2>Communiqué à l’avance</h2>"
        + _communique(pme)
        + "<h2>Paiement</h2>"
        + _paiement(ctx, abonne)
        + "<h2>Localisation des agents</h2>"
        + _passages(ctx, abonne, passages)
        + "<h2>Poubelle pleine</h2>"
        + _signalements(ctx, abonne, pme, hors, signalements)
    )
    return page(abonne["reference"], corps, ctx, actif="ordures", erreur=erreur)


def action_payer(ctx, reference):
    _garder(ctx)
    with base() as conn:
        abonne = _abonne(conn, reference)
        if abonne is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conn.execute("UPDATE abonnement SET paye = 1 WHERE id = ?", (abonne["id"],))
    return Redirection(f"/ordures/a/{reference}?message=paiement-enregistre")


def action_signalement(ctx, reference):
    _garder(ctx)
    with base() as conn:
        abonne = _abonne(conn, reference)
        if abonne is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        pme = None
        if abonne["pme_id"]:
            pme = conn.execute("SELECT * FROM pme WHERE id = ?", (abonne["pme_id"],)).fetchone()
        hors = _hors_jour(pme, ctx.aujourd_hui)
        frais = pme["frais_hors_jour"] if hors and pme else "0"
        conn.execute(
            """
            INSERT INTO signalement (abonnement_id, jour, hors_jour, frais_gnf, exemple, cree_le)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (abonne["id"], ctx.aujourd_hui.isoformat(), 1 if hors else 0, frais, maintenant()),
        )
    return Redirection(f"/ordures/a/{reference}?message=signalement-enregistre")


def action_passage(ctx, reference):
    _garder(ctx)
    try:
        agent = ligne(ctx.formulaire.get("agent"), 2, 80, "Agent")
        latitude = _coordonnee(ctx.formulaire.get("latitude"), Decimal("-90"), Decimal("90"), "Latitude")
        longitude = _coordonnee(ctx.formulaire.get("longitude"), Decimal("-180"), Decimal("180"), "Longitude")
        heure = ligne(ctx.formulaire.get("heure"), 3, 20, "Heure")
    except ValeurRefusee as exc:
        return page_fiche(ctx, reference, erreur=exc.message)
    with base() as conn:
        abonne = _abonne(conn, reference)
        if abonne is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conn.execute(
            """
            INSERT INTO passage (abonnement_id, agent, latitude, longitude, jour, heure, exemple)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (abonne["id"], agent, latitude, longitude, ctx.aujourd_hui.isoformat(), heure),
        )
    return Redirection(f"/ordures/a/{reference}?message=passage-enregistre")


def action_chercher(ctx):
    _garder(ctx)
    reference = (ctx.formulaire.get("reference") or "").strip().upper()
    if not reference:
        return page_module(ctx)
    return Redirection(f"/ordures/a/{reference}")


def page_pme(ctx, erreur=None):
    _garder(ctx)
    jour = ctx.aujourd_hui.isoformat()
    with base() as conn:
        pmes = conn.execute("SELECT * FROM pme ORDER BY nom").fetchall()
        blocs = []
        for pme in pmes:
            secteurs = conn.execute(
                """
                SELECT m.id FROM pme_secteur ps
                JOIN maille m ON m.id = ps.secteur_id
                WHERE ps.pme_id = ?
                ORDER BY m.nom
                """,
                (pme["id"],),
            ).fetchall()
            libelles = []
            for secteur in secteurs:
                noms = " — ".join(m["nom"] for m in _chaine(conn, secteur["id"]))
                libelles.append(noms)
            effectifs = conn.execute(
                "SELECT nombre, exemple FROM effectif WHERE pme_id = ? AND jour = ?",
                (pme["id"], jour),
            ).fetchall()
            trajets = conn.execute(
                "SELECT libelle, exemple FROM trajet WHERE pme_id = ? AND jour = ?",
                (pme["id"], jour),
            ).fetchall()
            blocs.append(_carte_pme(pme, libelles, effectifs, trajets))
        corps = (
            _fil()
            + "<h1>PME, effectifs et trajets</h1>"
            + _bandeau()
            + "<p>Les PME sont gérées par les communes ou par le gouvernorat. "
            "Une PME peut couvrir plusieurs secteurs ou quartiers. "
            f"Effectifs et trajets du {echapper(_jour_long(ctx.aujourd_hui))}.</p>"
            + "".join(blocs)
            + _forme_suivi(ctx, pmes)
        )
    return page("PME", corps, ctx, actif="ordures", erreur=erreur)


def action_suivi(ctx):
    _garder(ctx)
    try:
        pme_id = int(ctx.formulaire.get("pme_id") or "0")
        genre = ctx.formulaire.get("genre") or ""
    except ValueError:
        return page_pme(ctx, erreur="La PME n’est pas reconnue.")
    with base() as conn:
        pme = conn.execute("SELECT id FROM pme WHERE id = ?", (pme_id,)).fetchone()
        if pme is None:
            return page_pme(ctx, erreur="La PME n’est pas reconnue.")
        jour = ctx.aujourd_hui.isoformat()
        if genre == "effectif":
            try:
                nombre = int(ctx.formulaire.get("nombre") or "")
            except ValueError:
                return page_pme(ctx, erreur="L’effectif est un nombre entier.")
            if nombre < 0 or nombre > 500:
                return page_pme(ctx, erreur="L’effectif doit être compris entre 0 et 500.")
            conn.execute(
                "INSERT INTO effectif (pme_id, jour, nombre, exemple) VALUES (?, ?, ?, 0)",
                (pme_id, jour, nombre),
            )
        elif genre == "trajet":
            try:
                libelle = ligne(ctx.formulaire.get("libelle"), 2, 200, "Trajet")
            except ValeurRefusee as exc:
                return page_pme(ctx, erreur=exc.message)
            conn.execute(
                "INSERT INTO trajet (pme_id, jour, libelle, exemple) VALUES (?, ?, ?, 0)",
                (pme_id, jour, libelle),
            )
        else:
            return page_pme(ctx, erreur="Le suivi demandé n’est pas reconnu.")
    return Redirection("/ordures/pme?message=suivi-enregistre")


def page_points(ctx):
    _garder(ctx)
    with base() as conn:
        points = conn.execute("SELECT * FROM point_collecte ORDER BY nom").fetchall()
        lignes = []
        for point in points:
            chaine = " — ".join(m["nom"] for m in _chaine(conn, point["secteur_id"]))
            pastille = "exemple" if point["exemple"] else "saisie"
            lignes.append(
                f'<tr data-point="{echapper(point["nom"])}" data-exemple="{point["exemple"]}">'
                f'<td>{echapper(point["nom"])}</td>'
                f'<td>{echapper(point["latitude"])}, {echapper(point["longitude"])}</td>'
                f"<td>{echapper(chaine)}</td>"
                f"<td>{pastille}</td></tr>"
            )
    corps = (
        _fil()
        + "<h1>Points de collecte ANASP</h1>"
        + _bandeau()
        + "<p>Points de l’Agence nationale d’assainissement et de la salubrité publique, avec GPS. "
        "Ce développement du sigle vient du commanditaire, pas de la note.</p>"
        + "<table><caption>Points</caption><thead><tr>"
        "<th>Point</th><th>GPS</th><th>Rattachement</th><th></th></tr></thead><tbody>"
        + "".join(lignes)
        + "</tbody></table>"
    )
    return page("Points ANASP", corps, ctx, actif="ordures")


def page_abonnes(ctx):
    _garder(ctx)
    with base() as conn:
        lignes = conn.execute(
            "SELECT reference, nom, paye, exemple FROM abonnement ORDER BY reference"
        ).fetchall()
    items = []
    for ligne_abonne in lignes:
        etat = "payé" if ligne_abonne["paye"] else "non payé"
        pastille = "exemple" if ligne_abonne["exemple"] else "saisie"
        items.append(
            f'<li data-reference="{echapper(ligne_abonne["reference"])}">'
            f'<a href="/ordures/a/{echapper(ligne_abonne["reference"])}">{echapper(ligne_abonne["reference"])}</a> '
            f'{echapper(ligne_abonne["nom"])} — {etat} — {pastille}</li>'
        )
    corps = (
        _fil()
        + "<h1>Abonnés</h1>"
        + _bandeau()
        + "<ul>" + "".join(items) + "</ul>"
    )
    return page("Abonnés", corps, ctx, actif="ordures")


def page_prevu(ctx):
    _garder(ctx)
    return Redirection("/ordures")


def _fil():
    return '<p class="fil"><a href="/">Accueil</a> · <a href="/ordures">Collecte des ordures</a></p>'


def _bandeau():
    return f'<p class="bandeau bandeau-exemple" data-bandeau="exemple">{echapper(BANDEAU)}</p>'


def _recherche(ctx):
    return (
        "<h2>Déjà abonné</h2>"
        '<form method="post" action="/ordures/chercher" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="reference">Référence</label>'
        + '<input id="reference" name="reference" required maxlength="20">'
        + '<button type="submit">Ouvrir l’abonnement</button></form>'
    )


def _abonne(conn, reference):
    return conn.execute(
        "SELECT * FROM abonnement WHERE reference = ?",
        (reference.strip().upper(),),
    ).fetchone()


def _chaine(conn, maille_id):
    morceaux = []
    courant = maille_id
    vus = set()
    while courant and courant not in vus:
        vus.add(courant)
        ligne = conn.execute("SELECT * FROM maille WHERE id = ?", (courant,)).fetchone()
        if ligne is None:
            break
        morceaux.append(ligne)
        courant = ligne["parent_id"]
    morceaux.reverse()
    return morceaux


def _options_secteurs(conn, choisi):
    secteurs = conn.execute(
        "SELECT id FROM maille WHERE genre = 'secteur' ORDER BY nom"
    ).fetchall()
    options = ['<option value="">Choisir</option>']
    for secteur in secteurs:
        chaine = _chaine(conn, secteur["id"])
        texte = " — ".join(m["nom"] for m in chaine)
        sel = " selected" if str(secteur["id"]) == str(choisi or "") else ""
        options.append(f'<option value="{int(secteur["id"])}"{sel}>{echapper(texte)}</option>')
    return "".join(options)


def _liste(couples):
    return "<dl>" + "".join(
        f"<dt>{echapper(libelle)}</dt><dd>{echapper(valeur)}</dd>" for libelle, valeur in couples
    ) + "</dl>"


def _communique(pme):
    if pme is None:
        return "<p>Aucune PME n’est encore rattachée à ce secteur. Les jours ne sont pas communiqués.</p>"
    return _liste([
        ("PME", pme["nom"]),
        ("Gestion", GESTIONS.get(pme["gestion"], pme["gestion"])),
        ("Jour de collecte", pme["jour_collecte"]),
        ("Heures", pme["heure_collecte"]),
        ("Contact", pme["contact"]),
    ])


def _paiement(ctx, abonne):
    montant = _fmt_gnf(abonne["montant_gnf"])
    if abonne["paye"]:
        return f'<p data-paye="1">Paiement enregistré : {echapper(montant)}.</p>'
    return (
        f'<p data-paye="0">Paiement non enregistré. Montant : {echapper(montant)}.</p>'
        + f'<form method="post" action="/ordures/a/{echapper(abonne["reference"])}/payer" class="formulaire">'
        + jeton_cache(ctx)
        + '<button type="submit">Enregistrer le paiement</button></form>'
    )


def _passages(ctx, abonne, passages):
    if passages:
        items = []
        for passage in passages:
            pastille = "exemple" if passage["exemple"] else "saisie"
            items.append(
                f"<li>{echapper(passage['agent'])} — {echapper(passage['jour'])} {echapper(passage['heure'])} — "
                f"GPS {echapper(passage['latitude'])}, {echapper(passage['longitude'])} — {pastille}</li>"
            )
        liste = "<ul>" + "".join(items) + "</ul>"
    else:
        liste = "<p>Aucun agent ne s’est encore localisé pour cet abonné.</p>"
    if ctx.utilisateur is None:
        return liste + "<p class=\"aide\">La position de l’agent est enregistrée par un compte du ministère.</p>"
    return (
        liste
        + "<h3>Enregistrer une position</h3>"
        + f'<form method="post" action="/ordures/a/{echapper(abonne["reference"])}/passage" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="agent">Agent</label><input id="agent" name="agent" required maxlength="80">'
        + '<label for="latitude-agent">Latitude</label><input id="latitude-agent" name="latitude" required inputmode="decimal">'
        + '<label for="longitude-agent">Longitude</label><input id="longitude-agent" name="longitude" required inputmode="decimal">'
        + '<label for="heure">Heure</label><input id="heure" name="heure" required maxlength="20" placeholder="7 h 30">'
        + '<button type="submit">Localiser l’agent chez l’abonné</button></form>'
    )


def _signalements(ctx, abonne, pme, hors, signalements):
    if pme is None:
        intro = "<p>Sans PME, les frais hors jour ne sont pas déterminés.</p>"
    elif hors:
        intro = (
            f'<p data-hors-jour="1">Aujourd’hui n’est pas le jour de collecte ({echapper(pme["jour_collecte"])}). '
            f'La PME peut appliquer des frais supplémentaires : {echapper(_fmt_gnf(pme["frais_hors_jour"]))}.</p>'
        )
    else:
        intro = (
            f'<p data-hors-jour="0">Aujourd’hui est le jour de collecte ({echapper(pme["jour_collecte"])}). '
            "Aucun frais supplémentaire n’est ajouté.</p>"
        )
    items = []
    for signalement in signalements:
        frais = _fmt_gnf(signalement["frais_gnf"]) if int(signalement["frais_gnf"]) else "aucun frais"
        pastille = "exemple" if signalement["exemple"] else "saisie"
        items.append(
            f"<li>{echapper(signalement['jour'])} — {frais} — {pastille}</li>"
        )
    liste = "<ul>" + "".join(items) + "</ul>" if items else "<p>Aucun signalement.</p>"
    return (
        intro
        + liste
        + f'<form method="post" action="/ordures/a/{echapper(abonne["reference"])}/signalement" class="formulaire">'
        + jeton_cache(ctx)
        + '<button type="submit">Signaler une poubelle pleine</button></form>'
    )


def _carte_pme(pme, libelles, effectifs, trajets):
    pastille = "exemple" if pme["exemple"] else "saisie"
    effectif = ", ".join(
        f'{ligne["nombre"]} ({"exemple" if ligne["exemple"] else "saisie"})' for ligne in effectifs
    ) or "aucun effectif saisi pour ce jour"
    trajet = "".join(
        f'<li>{echapper(ligne["libelle"])} ({"exemple" if ligne["exemple"] else "saisie"})</li>'
        for ligne in trajets
    ) or "<li>Aucun trajet saisi pour ce jour.</li>"
    return (
        f'<article class="carte" data-pme="{echapper(pme["nom"])}" data-gestion="{echapper(pme["gestion"])}">'
        f"<h2>{echapper(pme['nom'])}</h2>"
        f"<p>{echapper(GESTIONS.get(pme['gestion'], pme['gestion']))} — {pastille}</p>"
        f"<p>Contact {echapper(pme['contact'])}. Collecte le {echapper(pme['jour_collecte'])}, "
        f"{echapper(pme['heure_collecte'])}. Frais hors jour : {echapper(_fmt_gnf(pme['frais_hors_jour']))}.</p>"
        f"<p>Secteurs ou quartiers : {echapper(' ; '.join(libelles))}</p>"
        f"<p>Effectif du jour : {echapper(effectif)}</p>"
        f"<ul>{trajet}</ul></article>"
    )


def _forme_suivi(ctx, pmes):
    options = "".join(
        f'<option value="{int(pme["id"])}">{echapper(pme["nom"])}</option>' for pme in pmes
    )
    return (
        "<h2>Ajouter au suivi du jour</h2>"
        '<form method="post" action="/ordures/pme" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="pme-suivi">PME</label>'
        + f'<select id="pme-suivi" name="pme_id" required>{options}</select>'
        + '<label for="genre-suivi">Sorte</label>'
        + '<select id="genre-suivi" name="genre" required>'
        + '<option value="effectif">Effectif</option><option value="trajet">Trajet</option></select>'
        + '<label for="nombre">Effectif</label><input id="nombre" name="nombre" inputmode="numeric">'
        + '<label for="libelle">Trajet</label><input id="libelle" name="libelle" maxlength="200">'
        + '<button type="submit">Enregistrer le suivi</button></form>'
    )


def _hors_jour(pme, aujourd_hui):
    if pme is None:
        return False
    return JOURS[aujourd_hui.weekday()] != pme["jour_collecte"]


def _jour_long(jour):
    return f"{JOURS[jour.weekday()]} {jour.isoformat()}"


def _fmt_gnf(valeur):
    texte = f"{int(valeur):,}".replace(",", "\u00a0")
    return f"{texte}\u00a0GNF"


def _telephone(valeur):
    texte = ligne(valeur, 8, 20, "Téléphone")
    if any(caractere not in "0123456789 +-" for caractere in texte):
        raise ValeurRefusee("Le téléphone ne contient que des chiffres, des espaces, + ou -.")
    return texte


def _coordonnee(valeur, minimum, maximum, libelle):
    texte = "" if valeur is None else str(valeur).strip().replace(",", ".")
    try:
        nombre = Decimal(texte)
    except InvalidOperation as exc:
        raise ValeurRefusee(f"Le champ « {libelle} » n’est pas un nombre.") from exc
    if nombre < minimum or nombre > maximum:
        raise ValeurRefusee(f"Le champ « {libelle} » est hors limites.")
    return format(nombre.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")
