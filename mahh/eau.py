"""Eau : SEG en ville, SNAPE en zone rurale. Le jeu de départ est un exemple."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from secrets import token_hex

from mahh.db import base
from mahh.droits import exiger_connexion, peut_voir_reseau, peut_voir_seg, peut_voir_snape
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import attribut_pourcent, echapper, fmt_nombre, fmt_pourcent
from mahh.validation import ligne

BANDEAU = (
    "Jeu d’exemple. Ces villes, villages, sites, forages et abonnés ne sont pas ceux du ministère. "
    "Aucun de ces chiffres n’est officiel. SEG reste le sigle de la note. "
    "SNAPE, Service national d’aménagement des points d’eau, est le développement indiqué par le commanditaire."
)


def page_module(ctx):
    exiger_connexion(ctx)
    with base() as conn:
        voit_seg = peut_voir_seg(conn, ctx.utilisateur)
        voit_snape = peut_voir_snape(conn, ctx.utilisateur)
    if not voit_seg and not voit_snape:
        raise Interdit("Cette structure ne voit que ce qui la concerne.")
    tableaux = []
    if voit_seg:
        tableaux.append('<a class="bouton" href="/eau/seg">Tableau du SEG</a>')
    if voit_snape:
        tableaux.append('<a class="bouton secondaire" href="/eau/snape">Tableau du SNAPE</a>')
    corps = (
        _fil()
        + "<h1>Eau : SEG et SNAPE</h1>"
        + _bandeau()
        + "<p class=\"chapeau\">SEG : distribution d’eau en ville. SNAPE : forages en zone rurale. "
        "Seuls les réseaux ouverts à votre compte sont affichés.</p>"
        + '<p><a class="bouton" href="/eau/demande">Déposer une demande</a></p>'
        + "<p>" + " ".join(tableaux) + "</p>"
    )
    actif = "seg" if voit_seg and not voit_snape else "snape" if voit_snape and not voit_seg else "eau"
    return page("Eau", corps, ctx, actif=actif)


def page_demande(ctx, erreur=None, valeurs=None):
    exiger_connexion(ctx)
    valeurs = valeurs or {}
    with base() as conn:
        if not peut_voir_seg(conn, ctx.utilisateur) and not peut_voir_snape(conn, ctx.utilisateur):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        options = _options_lieux(conn, ctx.utilisateur, valeurs.get("lieu_id"))
        voit_seg = peut_voir_seg(conn, ctx.utilisateur)
        voit_snape = peut_voir_snape(conn, ctx.utilisateur)
        actif = "seg" if voit_seg and not voit_snape else "snape" if voit_snape and not voit_seg else "eau"
    corps = (
        _fil()
        + "<h1>Demande d’eau</h1>"
        + _bandeau()
        + "<p>Une ville relève du SEG. Un village relève du SNAPE. "
        "Le relevé GPS est saisi : latitude et longitude.</p>"
        + '<form method="post" action="/eau/demande" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="nom">Nom</label>'
        + f'<input id="nom" name="nom" required maxlength="80" value="{echapper(valeurs.get("nom", ""))}">'
        + '<label for="telephone">Téléphone</label>'
        + f'<input id="telephone" name="telephone" required maxlength="20" value="{echapper(valeurs.get("telephone", ""))}">'
        + '<label for="lieu">Ville ou village</label>'
        + f'<select id="lieu" name="lieu_id" required>{options}</select>'
        + '<label for="latitude">Latitude</label>'
        + f'<input id="latitude" name="latitude" required inputmode="decimal" value="{echapper(valeurs.get("latitude", ""))}">'
        + '<label for="longitude">Longitude</label>'
        + f'<input id="longitude" name="longitude" required inputmode="decimal" value="{echapper(valeurs.get("longitude", ""))}">'
        + '<button type="submit">Enregistrer la demande</button></form>'
    )
    return page("Demande d’eau", corps, ctx, actif=actif, erreur=erreur)


def action_demande(ctx):
    exiger_connexion(ctx)
    try:
        nom = ligne(ctx.formulaire.get("nom"), 2, 80, "Nom")
        telephone = _telephone(ctx.formulaire.get("telephone"))
        latitude = _coordonnee(ctx.formulaire.get("latitude"), "-90", "90", "Latitude")
        longitude = _coordonnee(ctx.formulaire.get("longitude"), "-180", "180", "Longitude")
        lieu_id = int(ctx.formulaire.get("lieu_id") or "0")
    except (ValeurRefusee, ValueError) as exc:
        message = exc.message if isinstance(exc, ValeurRefusee) else "Le lieu n’est pas reconnu."
        return page_demande(ctx, erreur=message, valeurs=ctx.formulaire)
    with base() as conn:
        lieu = conn.execute("SELECT * FROM eau_lieu WHERE id = ?", (lieu_id,)).fetchone()
        if lieu is None:
            return page_demande(ctx, erreur="Le lieu n’est pas reconnu.", valeurs=ctx.formulaire)
        if not peut_voir_reseau(conn, ctx.utilisateur, lieu["reseau"]):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        reference = "EAU-" + token_hex(3).upper()
        conn.execute(
            """
            INSERT INTO eau_demande (
                reference, reseau, lieu_id, nom, telephone, latitude, longitude, etat, exemple, cree_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'recue', 0, ?)
            """,
            (reference, lieu["reseau"], lieu_id, nom, telephone, latitude, longitude, maintenant()),
        )
    return Redirection(f"/eau/d/{reference}?message=demande-eau-creee")


def page_demande_fiche(ctx, reference, erreur=None):
    exiger_connexion(ctx)
    with base() as conn:
        demande = _demande(conn, reference)
        if demande is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if not _peut_voir(ctx, conn, demande["reseau"]):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        lieu = conn.execute("SELECT * FROM eau_lieu WHERE id = ?", (demande["lieu_id"],)).fetchone()
        abonnement = conn.execute(
            "SELECT reference FROM eau_abonnement WHERE demande_id = ?",
            (demande["id"],),
        ).fetchone()
    corps = (
        _fil()
        + _pastille(demande["exemple"])
        + f'<h1>{echapper(demande["reference"])}</h1>'
        + _bandeau()
        + _identite(demande, lieu)
        + _suite_abonnement(ctx, demande, abonnement)
    )
    return page(demande["reference"], corps, ctx, actif=demande["reseau"], erreur=erreur)


def action_abonner(ctx, reference):
    exiger_connexion(ctx)
    with base() as conn:
        demande = _demande(conn, reference)
        if demande is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if not _peut_voir(ctx, conn, demande["reseau"]):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        existant = conn.execute(
            "SELECT reference FROM eau_abonnement WHERE demande_id = ?",
            (demande["id"],),
        ).fetchone()
        if existant:
            return Redirection(f"/eau/a/{existant['reference']}")
        reference_abonnement = "EAU-" + token_hex(3).upper()
        conn.execute(
            """
            INSERT INTO eau_abonnement (
                reference, demande_id, reseau, lieu_id, nom, telephone, latitude, longitude,
                paye, exemple, cree_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                reference_abonnement, demande["id"], demande["reseau"], demande["lieu_id"],
                demande["nom"], demande["telephone"], demande["latitude"], demande["longitude"],
                maintenant(),
            ),
        )
        conn.execute("UPDATE eau_demande SET etat = 'abonne' WHERE id = ?", (demande["id"],))
    return Redirection(f"/eau/a/{reference_abonnement}?message=abonnement-eau-cree")


def page_abonnement(ctx, reference, erreur=None):
    exiger_connexion(ctx)
    with base() as conn:
        abonnement = _abonnement(conn, reference)
        if abonnement is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if not _peut_lire_fiche(ctx, conn, abonnement["reseau"]):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        lieu = conn.execute("SELECT * FROM eau_lieu WHERE id = ?", (abonnement["lieu_id"],)).fetchone()
    corps = (
        _fil()
        + _pastille(abonnement["exemple"])
        + f'<h1>{echapper(abonnement["reference"])}</h1>'
        + _bandeau()
        + _identite(abonnement, lieu)
        + _paiement(ctx, abonnement)
    )
    return page(abonnement["reference"], corps, ctx, actif=abonnement["reseau"], erreur=erreur)


def action_payer(ctx, reference):
    exiger_connexion(ctx)
    with base() as conn:
        abonnement = _abonnement(conn, reference)
        if abonnement is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if not _peut_lire_fiche(ctx, conn, abonnement["reseau"]):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
        conn.execute("UPDATE eau_abonnement SET paye = 1 WHERE id = ?", (abonnement["id"],))
    return Redirection(f"/eau/a/{reference}?message=paiement-eau-enregistre")


def page_seg(ctx):
    with base() as conn:
        _exiger_reseau(ctx, conn, "seg")
        corps = _tableau_seg(conn)
    return page("Tableau du SEG", corps, ctx, actif="seg")


def page_snape(ctx):
    with base() as conn:
        _exiger_reseau(ctx, conn, "snape")
        corps = _tableau_snape(conn)
    return page("Tableau du SNAPE", corps, ctx, actif="snape")


def page_prevu(ctx):
    exiger_connexion(ctx)
    with base() as conn:
        if not peut_voir_seg(conn, ctx.utilisateur) and not peut_voir_snape(conn, ctx.utilisateur):
            raise Interdit("Cette structure ne voit que ce qui la concerne.")
    return Redirection("/eau")


def _tableau_seg(conn):
    lieux = conn.execute("SELECT * FROM eau_lieu WHERE reseau = 'seg' ORDER BY nom").fetchall()
    sites = conn.execute(
        """
        SELECT s.*, l.nom AS ville FROM eau_site s
        JOIN eau_lieu l ON l.id = s.lieu_id
        WHERE l.reseau = 'seg' ORDER BY s.nom
        """
    ).fetchall()
    abonnes = conn.execute(
        "SELECT COUNT(*) AS n FROM eau_abonnement WHERE reseau = 'seg' AND paye = 1"
    ).fetchone()["n"]
    population = sum(lieu["population"] for lieu in lieux)
    desservie = sum(lieu["population_couverte"] for lieu in lieux)
    situation = conn.execute("SELECT * FROM eau_situation WHERE reseau = 'seg'").fetchone()
    taux_abonnement = _taux(abonnes, population)
    taux_desserte = _taux(desservie, population)
    taux_facturation = None
    taux_recouvrement = None
    produit = distribue = None
    if situation:
        produit = situation["volume_produit"]
        distribue = situation["volume_distribue"]
        taux_facturation = _taux(situation["montant_facture"], situation["montant_du"])
        taux_recouvrement = _taux(situation["montant_recouvre"], situation["montant_facture"])
    villes = [lieu["nom"] for lieu in lieux if lieu["population_couverte"]]
    indicateurs = (
        f'<section class="indicateurs" data-abonnes="{abonnes}" '
        f'data-taux-abonnement="{attribut_pourcent(taux_abonnement)}" '
        f'data-sites="{len(sites)}" data-villes="{len(villes)}" '
        f'data-desserte="{attribut_pourcent(taux_desserte)}" '
        f'data-facturation="{attribut_pourcent(taux_facturation)}" '
        f'data-recouvrement="{attribut_pourcent(taux_recouvrement)}" '
        f'data-produit="{echapper(produit or "")}" data-distribue="{echapper(distribue or "")}">'
        + _carte("Nombre d’abonné", str(abonnes))
        + _carte("Taux d’abonnement", fmt_pourcent(taux_abonnement))
        + _carte("Nombre de sites d’approvisionnement", str(len(sites)))
        + _carte("Nombre de ville couverte", str(len(villes)))
        + _carte("Taux de desserte urbain", fmt_pourcent(taux_desserte))
        + _carte("Taux de facturation", fmt_pourcent(taux_facturation))
        + _carte("Taux de recouvrement", fmt_pourcent(taux_recouvrement))
        + _carte("Volume d’eau produit (m³)", fmt_nombre(produit) if produit else "—")
        + _carte("Volume d’eau distribué (m³)", fmt_nombre(distribue) if distribue else "—")
        + "</section>"
    )
    liste = "".join(f'<li data-ville="{echapper(nom)}">{echapper(nom)}</li>' for nom in villes)
    points = "".join(
        f'<li data-site="{echapper(site["nom"])}">{echapper(site["nom"])} — {echapper(site["ville"])} — '
        f'GPS {echapper(site["latitude"])}, {echapper(site["longitude"])}</li>'
        for site in sites
    )
    return (
        _fil()
        + "<h1>Tableau du SEG</h1>"
        + _bandeau()
        + "<p>Distribution d’eau en ville. L’organigramme et les attributions se règlent dans Directions.</p>"
        + "<p class=\"aide\">Taux d’abonnement et nombre de sites d’approvisionnement : demandés par le commanditaire, "
        "absents de la note. Taux d’abonnement = abonnés payants / population des villes. "
        "Taux de desserte urbain = population desservie déclarée / population des villes. "
        "Taux de facturation = montant facturé / montant dû. "
        "Taux de recouvrement = montant recouvré / montant facturé. "
        "La note ne donne pas ces formules. Les volumes et les montants viennent de la situation d’exemple, "
        "pas d’une somme abonné par abonné.</p>"
        + indicateurs
        + "<h2>La liste des villes couvertes</h2><ul>" + liste + "</ul>"
        + "<h2>Sites d’approvisionnement</h2><ul>" + points + "</ul>"
    )


def _tableau_snape(conn):
    lieux = conn.execute("SELECT * FROM eau_lieu WHERE reseau = 'snape' ORDER BY nom").fetchall()
    items = []
    total_points = 0
    for lieu in lieux:
        points = conn.execute(
            "SELECT * FROM eau_site WHERE lieu_id = ? ORDER BY nom",
            (lieu["id"],),
        ).fetchall()
        total_points += len(points)
        forages = "".join(
            f'<li>{echapper(point["nom"])} — GPS {echapper(point["latitude"])}, {echapper(point["longitude"])}</li>'
            for point in points
        )
        items.append(
            f'<article class="carte" data-village="{echapper(lieu["nom"])}" '
            f'data-couverte="{lieu["population_couverte"]}" data-forages="{len(points)}">'
            f'<h2>{echapper(lieu["nom"])}</h2>'
            f'<p>Nombre de population couverte par village : {lieu["population_couverte"]}</p>'
            f'<p>Nombre de points d’eau realisés par village : {len(points)}</p>'
            f"<ul>{forages}</ul></article>"
        )
    return (
        _fil()
        + "<h1>Tableau du SNAPE</h1>"
        + _bandeau()
        + "<p>Forages en zone rurale. L’organigramme et les attributions se règlent dans Directions.</p>"
        + f'<p data-villages="{len(lieux)}" data-points="{total_points}">'
        + f"Nombre de villages couvert : {len(lieux)}. "
        + f"Points d’eau realisés : {total_points}.</p>"
        + "".join(items)
    )


def _fil():
    return '<p class="fil"><a href="/">Accueil</a> · <a href="/eau">Eau</a></p>'


def _bandeau():
    return f'<p class="bandeau bandeau-exemple" data-bandeau="exemple">{echapper(BANDEAU)}</p>'


def _pastille(exemple):
    if exemple:
        return '<p class="badge-exemple" data-genre="exemple">exemple fictif</p>'
    return '<p class="badge-saisie" data-genre="saisie">saisie</p>'


def _options_lieux(conn, utilisateur, choisi):
    options = ['<option value="">Choisir</option>']
    reseaux = []
    if peut_voir_reseau(conn, utilisateur, "seg"):
        reseaux.append(("seg", "Villes, SEG"))
    if peut_voir_reseau(conn, utilisateur, "snape"):
        reseaux.append(("snape", "Villages, SNAPE"))
    for reseau, libelle in reseaux:
        lignes = conn.execute(
            "SELECT id, nom FROM eau_lieu WHERE reseau = ? ORDER BY nom",
            (reseau,),
        ).fetchall()
        bloc = [f'<optgroup label="{libelle}">']
        for ligne_lieu in lignes:
            sel = " selected" if str(ligne_lieu["id"]) == str(choisi or "") else ""
            bloc.append(
                f'<option value="{int(ligne_lieu["id"])}"{sel}>{echapper(ligne_lieu["nom"])}</option>'
            )
        bloc.append("</optgroup>")
        options.append("".join(bloc))
    return "".join(options)


def _identite(personne, lieu):
    reseau = "SEG, ville" if personne["reseau"] == "seg" else "SNAPE, zone rurale"
    return (
        "<dl>"
        f'<dt>Nom</dt><dd>{echapper(personne["nom"])}</dd>'
        f'<dt>Téléphone</dt><dd>{echapper(personne["telephone"])}</dd>'
        f'<dt>Réseau</dt><dd>{reseau}</dd>'
        f'<dt>Lieu</dt><dd data-lieu="{echapper(lieu["nom"])}">{echapper(lieu["nom"])}</dd>'
        f'<dt>Relevé GPS</dt><dd>{echapper(personne["latitude"])}, {echapper(personne["longitude"])}</dd>'
        "</dl>"
    )


def _suite_abonnement(ctx, demande, abonnement):
    if abonnement:
        return (
            f'<p>Abonnement : <a href="/eau/a/{echapper(abonnement["reference"])}">'
            f'{echapper(abonnement["reference"])}</a></p>'
        )
    return (
        f'<form method="post" action="/eau/d/{echapper(demande["reference"])}/abonner" class="formulaire">'
        + jeton_cache(ctx)
        + '<button type="submit">Prendre l’abonnement</button></form>'
    )


def _paiement(ctx, abonnement):
    if abonnement["paye"]:
        return '<p data-paye="1">Paiement enregistré. La personne compte parmi les abonnés.</p>'
    return (
        '<p data-paye="0">Paiement non enregistré. Ce n’est pas un paiement bancaire.</p>'
        + f'<form method="post" action="/eau/a/{echapper(abonnement["reference"])}/payer" class="formulaire">'
        + jeton_cache(ctx)
        + '<button type="submit">Enregistrer le paiement</button></form>'
    )


def _carte(libelle, valeur):
    return (
        '<article class="carte-chiffre">'
        f'<p class="libelle">{echapper(libelle)}</p>'
        f'<p class="valeur">{echapper(valeur)}</p></article>'
    )


def _taux(numerateur, denominateur):
    if denominateur in (None, 0, "0", ""):
        return None
    return Decimal(str(numerateur)) / Decimal(str(denominateur))


def _demande(conn, reference):
    return conn.execute(
        "SELECT * FROM eau_demande WHERE reference = ?",
        (reference.strip().upper(),),
    ).fetchone()


def _abonnement(conn, reference):
    return conn.execute(
        "SELECT * FROM eau_abonnement WHERE reference = ?",
        (reference.strip().upper(),),
    ).fetchone()


def _exiger_reseau(ctx, conn, reseau):
    exiger_connexion(ctx)
    if not _peut_voir(ctx, conn, reseau):
        raise Interdit("Cette structure ne voit que ce qui la concerne.")


def _peut_voir(ctx, conn, reseau):
    return peut_voir_reseau(conn, ctx.utilisateur, reseau)


def _peut_lire_fiche(ctx, conn, reseau):
    return _peut_voir(ctx, conn, reseau)


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
    if nombre < Decimal(minimum) or nombre > Decimal(maximum):
        raise ValeurRefusee(f"Le champ « {libelle} » est hors limites.")
    return format(nombre.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")
