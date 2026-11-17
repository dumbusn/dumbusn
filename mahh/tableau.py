"""Tableau de bord du BSD."""

from pathlib import Path
from secrets import token_hex
from urllib.parse import quote, urlencode

from mahh.calculs import (
    FINANCEMENTS_EXEMPLE,
    SECTEURS,
    STATUTS,
    budget_decaisse,
    jours_restants,
    points_attention,
    synthese,
)
from mahh.config import repertoire_fichiers
from mahh.db import base
from mahh.documents import MESSAGE_TAILLE, TAILLE_MAX, _chemin_stockage, _nom_fichier, suffixe_stockage
from mahh.droits import (
    est_hierarchie,
    exiger_admin,
    exiger_bsd,
    exiger_connexion,
    peut_tenir_projet,
    peut_voir_projet,
)
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Octets, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import (
    attribut_decimal,
    attribut_pourcent,
    classe_barre,
    echapper,
    fmt_date,
    fmt_nombre,
    fmt_pourcent,
    pourcent_saisi,
)
from mahh.validation import bloc, ligne
from mahh.validation import projet as lire_projet

ORDRE_SQL = "ORDER BY secteur, code"


def page_bsd(ctx):
    secteur = ctx.requete.get("secteur", "")
    direction = ctx.requete.get("direction", "")
    statut = ctx.requete.get("statut", "")
    with base() as conn:
        exiger_bsd(ctx, conn)
        visibles = _filtrer(conn, ctx.utilisateur, "", "", "")
        responsables = sorted({ligne["responsable"] for ligne in visibles})
        if direction and direction not in responsables:
            responsables.append(direction)
        projets = _filtrer(conn, ctx.utilisateur, secteur, direction, statut)
        resume = synthese(projets, secteur_demande=secteur or None)
        attention = points_attention(projets)
        corps = _corps(ctx, resume, projets, attention, responsables, secteur, direction, statut)
    return page("Tableau de bord", corps, ctx, actif="bsd")


def page_projet(ctx, projet_id, erreur=None):
    with base() as conn:
        exiger_bsd(ctx, conn)
        projet = conn.execute("SELECT * FROM projet WHERE id = ?", (int(projet_id),)).fetchone()
        if projet is None:
            return page("Introuvable", "<h1>Introuvable</h1><p>Ce projet n’est pas au registre.</p>", ctx, statut=404)
        if not peut_voir_projet(ctx.utilisateur, projet):
            raise Interdit("Ce projet ne concerne pas votre direction.")
        pieces = conn.execute(
            "SELECT * FROM piece WHERE projet_id = ? ORDER BY cree_le, id",
            (projet["id"],),
        ).fetchall()
        structures = _structures(conn) if est_hierarchie(ctx.utilisateur) else []
        rattachee = None
        if projet["structure_id"]:
            rattachee = conn.execute(
                "SELECT nom FROM noeud WHERE id = ?", (projet["structure_id"],)
            ).fetchone()
        corps = _fiche(ctx, projet, pieces, structures, rattachee)
    return page(projet["code"], corps, ctx, actif="bsd", erreur=erreur)


def page_saisie(ctx, valeurs=None, erreur=None, projet_id=None):
    exiger_admin(ctx)
    valeurs = valeurs or {}
    with base() as conn:
        structures = _structures(conn)
    titre = "Modifier le projet" if projet_id else "Saisir un projet"
    corps = f"<h1>{titre}</h1>" + _formulaire(ctx, valeurs, projet_id, structures)
    if projet_id:
        corps += (
            f'<form method="post" action="/bsd/projet/{int(projet_id)}/supprimer" class="formulaire">'
            f"{jeton_cache(ctx)}"
            '<button type="submit" class="danger">Retirer du registre</button></form>'
        )
    return page(titre, corps, ctx, actif="bsd", erreur=erreur)


def page_modifier(ctx, projet_id, erreur=None, valeurs=None):
    exiger_admin(ctx)
    with base() as conn:
        projet = conn.execute("SELECT * FROM projet WHERE id = ?", (int(projet_id),)).fetchone()
    if projet is None:
        return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
    if valeurs is None:
        valeurs = _valeurs_projet(projet)
    return page_saisie(ctx, valeurs=valeurs, erreur=erreur, projet_id=int(projet_id))


def action_saisie(ctx):
    exiger_admin(ctx)
    try:
        donnees = lire_projet(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_saisie(ctx, valeurs=ctx.formulaire, erreur=exc.message)
    with base() as conn:
        if conn.execute("SELECT id FROM projet WHERE code = ?", (donnees["code"],)).fetchone():
            return page_saisie(ctx, valeurs=ctx.formulaire, erreur="Cet identifiant est déjà utilisé.")
        try:
            structure_id = _structure_formulaire(conn, ctx.formulaire)
        except ValeurRefusee as exc:
            return page_saisie(ctx, valeurs=ctx.formulaire, erreur=exc.message)
        quand = maintenant()
        curseur = conn.execute(
            """
            INSERT INTO projet (
                code, secteur, titre, localisation, statut, budget_mds, decaissement,
                avancement, debut, echeance, responsable, financement, jalon,
                observations, exemple, structure_id, cree_le, modifie_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                donnees["code"], donnees["secteur"], donnees["titre"], donnees["localisation"],
                donnees["statut"], donnees["budget_mds"], donnees["decaissement"],
                donnees["avancement"], donnees["debut"], donnees["echeance"],
                donnees["responsable"], donnees["financement"], donnees["jalon"],
                donnees["observations"], structure_id, quand, quand,
            ),
        )
        nouveau = curseur.lastrowid
    return Redirection(f"/bsd/projet/{nouveau}?message=projet-cree")


def action_modifier(ctx, projet_id):
    exiger_admin(ctx)
    try:
        donnees = lire_projet(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_modifier(ctx, projet_id, erreur=exc.message, valeurs=ctx.formulaire)
    with base() as conn:
        actuel = conn.execute("SELECT * FROM projet WHERE id = ?", (int(projet_id),)).fetchone()
        if actuel is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conflit = conn.execute(
            "SELECT id FROM projet WHERE code = ? AND id != ?",
            (donnees["code"], actuel["id"]),
        ).fetchone()
        if conflit:
            return page_modifier(
                ctx, projet_id, erreur="Cet identifiant est déjà utilisé.", valeurs=ctx.formulaire
            )
        try:
            structure_id = _structure_formulaire(conn, ctx.formulaire)
        except ValeurRefusee as exc:
            return page_modifier(ctx, projet_id, erreur=exc.message, valeurs=ctx.formulaire)
        conn.execute(
            """
            UPDATE projet SET
                code = ?, secteur = ?, titre = ?, localisation = ?, statut = ?,
                budget_mds = ?, decaissement = ?, avancement = ?, debut = ?, echeance = ?,
                responsable = ?, financement = ?, jalon = ?, observations = ?,
                structure_id = ?, modifie_le = ?
            WHERE id = ?
            """,
            (
                donnees["code"], donnees["secteur"], donnees["titre"], donnees["localisation"],
                donnees["statut"], donnees["budget_mds"], donnees["decaissement"],
                donnees["avancement"], donnees["debut"], donnees["echeance"],
                donnees["responsable"], donnees["financement"], donnees["jalon"],
                donnees["observations"], structure_id, maintenant(), actuel["id"],
            ),
        )
    return Redirection(f"/bsd/projet/{int(projet_id)}?message=projet-modifie")


def action_supprimer_projet(ctx, projet_id):
    exiger_admin(ctx)
    with base() as conn:
        pieces = conn.execute(
            "SELECT nom_stockage FROM piece WHERE projet_id = ? AND nom_stockage IS NOT NULL",
            (int(projet_id),),
        ).fetchall()
        for piece in pieces:
            chemin = _chemin_stockage(piece["nom_stockage"])
            if chemin is not None and chemin.exists():
                chemin.unlink()
        conn.execute("DELETE FROM projet WHERE id = ?", (int(projet_id),))
    return Redirection("/bsd?message=projet-supprime")


def action_rattacher(ctx, projet_id):
    exiger_connexion(ctx)
    if not est_hierarchie(ctx.utilisateur):
        raise Interdit("Le rattachement d’un projet est réservé à la hiérarchie.")
    with base() as conn:
        projet = conn.execute("SELECT * FROM projet WHERE id = ?", (int(projet_id),)).fetchone()
        if projet is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        try:
            structure_id = _structure_formulaire(conn, ctx.formulaire)
        except ValeurRefusee as exc:
            return page_projet(ctx, projet_id, erreur=exc.message)
        conn.execute(
            "UPDATE projet SET structure_id = ?, modifie_le = ? WHERE id = ?",
            (structure_id, maintenant(), projet["id"]),
        )
    return Redirection(f"/bsd/projet/{int(projet_id)}?message=projet-rattache")


def action_piece(ctx, projet_id):
    exiger_connexion(ctx)
    with base() as conn:
        projet = conn.execute("SELECT * FROM projet WHERE id = ?", (int(projet_id),)).fetchone()
        if projet is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if not peut_tenir_projet(ctx.utilisateur, projet):
            raise Interdit("Ce projet ne concerne pas votre direction.")
        try:
            genre, titre, texte, cote, emplacement = _lire_piece(ctx.formulaire)
        except ValeurRefusee as exc:
            return page_projet(ctx, projet_id, erreur=exc.message)
        fichier = ctx.fichier
        if fichier is not None and not fichier[0]:
            fichier = None
        stockage = None
        nom_fichier = None
        if genre == "rapport" and fichier is None:
            return page_projet(ctx, projet_id, erreur="Un rapport se dépose avec un fichier.")
        if fichier is not None:
            try:
                nom_fichier = _nom_fichier(fichier[0])
            except ValeurRefusee as exc:
                return page_projet(ctx, projet_id, erreur=exc.message)
            if not fichier[1]:
                return page_projet(ctx, projet_id, erreur="Le fichier est vide.")
            if len(fichier[1]) > TAILLE_MAX:
                return page_projet(ctx, projet_id, erreur=MESSAGE_TAILLE)
            stockage = token_hex(16) + suffixe_stockage(nom_fichier)
        conn.execute(
            """
            INSERT INTO piece (
                projet_id, genre, titre, texte, cote, emplacement,
                nom_stockage, nom_fichier, cree_par, cree_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                projet["id"], genre, titre, texte, cote, emplacement,
                stockage, nom_fichier, ctx.utilisateur["id"], maintenant(),
            ),
        )
    if stockage is not None:
        (repertoire_fichiers() / stockage).write_bytes(fichier[1])
    return Redirection(f"/bsd/projet/{int(projet_id)}?message=piece-ajoutee")


def telecharger_piece(ctx, piece_id):
    exiger_connexion(ctx)
    with base() as conn:
        piece = conn.execute("SELECT * FROM piece WHERE id = ?", (int(piece_id),)).fetchone()
        if piece is None or not piece["nom_stockage"]:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        projet = conn.execute("SELECT * FROM projet WHERE id = ?", (piece["projet_id"],)).fetchone()
        if projet is None or not peut_voir_projet(ctx.utilisateur, projet):
            raise Interdit("Ce projet ne concerne pas votre direction.")
        chemin = _chemin_stockage(piece["nom_stockage"])
        if chemin is None or not chemin.exists():
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        contenu = chemin.read_bytes()
        nom = piece["nom_fichier"] or "piece"
    disposition = "attachment; filename*=UTF-8''" + quote(nom)
    return Octets(contenu, "application/octet-stream", disposition=disposition)


def _filtrer(conn, utilisateur, secteur, direction, statut):
    requete = "SELECT * FROM projet WHERE 1 = 1"
    params = []
    if est_hierarchie(utilisateur):
        pass
    elif utilisateur["structure_id"]:
        requete += " AND structure_id = ?"
        params.append(utilisateur["structure_id"])
    else:
        requete += " AND 0 = 1"
    if secteur:
        requete += " AND secteur = ?"
        params.append(secteur)
    if direction:
        requete += " AND responsable = ?"
        params.append(direction)
    if statut:
        requete += " AND statut = ?"
        params.append(statut)
    requete += " " + ORDRE_SQL
    return conn.execute(requete, params).fetchall()


def _corps(ctx, resume, projets, attention, responsables, secteur, direction, statut):
    filtres = _filtres(responsables, secteur, direction, statut)
    if resume["nombre"] == 0:
        if secteur or direction or statut:
            texte = "Aucun projet ne correspond à ce filtre."
        else:
            texte = (
                "Aucun projet enregistré. Le BSD saisit le code, le secteur, le budget, "
                "l’avancement et la direction responsable."
            )
        bandeau = f'<p class="vide" data-bandeau="vide">{texte}</p>'
        indicateur = (
            '<section class="indicateurs" id="indicateurs">'
            + _carte("projets", "Projets suivis", "0")
            + "</section>"
        )
        secteurs = ""
        statuts = ""
        attentions = "<h2>Points d’attention</h2><p>Aucun projet en retard ou à risque.</p>"
    else:
        bandeau = ""
        indicateur = _indicateurs(ctx, resume)
        secteurs = _tableau_secteurs(resume["par_secteur"])
        statuts = _tableau_statuts(resume["par_statut"])
        attentions = _liste_attention(ctx, attention)
    registre = _registre(projets, ctx)
    saisie = ""
    if ctx.utilisateur["administrateur"]:
        saisie = '<p><a class="bouton" href="/bsd/saisie">Saisir un projet</a></p>'
    parametres = {
        cle: valeur
        for cle, valeur in (("secteur", secteur), ("direction", direction), ("statut", statut))
        if valeur
    }
    lien = "/bsd/export.csv"
    if parametres:
        lien += "?" + urlencode(parametres)
    export = f'<p><a class="bouton secondaire" href="{echapper(lien)}">Exporter le registre (CSV)</a></p>'
    note = (
        "<p class=\"note\">« En cours d’exécution » regroupe les projets dans les délais, "
        "à risque ou en retard. Suspendu et en préparation n’y entrent pas. "
        "Les moyennes sont pondérées par le budget. "
        f"Les jours restants sont calculés au {echapper(fmt_date(ctx.aujourd_hui.isoformat()))}. "
        "Un clic sur le code ouvre le dossier du projet : notes, rapports et classement des documents physiques.</p>"
    )
    if est_hierarchie(ctx.utilisateur):
        portee = (
            "<p class=\"note\">Vous voyez tous les projets. "
            "Les structures n’ont pas à vous remonter l’information.</p>"
        )
    elif ctx.utilisateur["structure_id"]:
        portee = (
            "<p class=\"note\">Registre limité à votre direction ou service. "
            "La hiérarchie voit l’ensemble.</p>"
        )
    else:
        portee = (
            "<p class=\"note\">Ce compte n’a pas l’accès complet et n’est rattaché à aucune direction. "
            "Le registre est vide.</p>"
        )
    return (
        "<h1>Tableau de bord du BSD</h1>"
        '<p class="chapeau">Bureau de stratégie et de développement. '
        "Suivi des projets des directions.</p>"
        + bandeau + note + portee + filtres + saisie + export + indicateur + secteurs + statuts + attentions + registre
    )


def _filtres(responsables, secteur, direction, statut):
    def option(valeur, libelle, choisi):
        sel = " selected" if valeur == choisi else ""
        return f'<option value="{echapper(valeur)}"{sel}>{echapper(libelle)}</option>'

    secteurs = ['<option value="">Tous les domaines</option>']
    for nom in SECTEURS:
        secteurs.append(option(nom, nom, secteur))
    directions = ['<option value="">Toutes les directions responsables</option>']
    for nom in responsables:
        directions.append(option(nom, nom, direction))
    statuts = ['<option value="">Tous les statuts</option>']
    for nom in STATUTS:
        statuts.append(option(nom, nom, statut))
    return (
        '<form method="get" action="/bsd" class="filtres">'
        '<label for="secteur">Secteur</label>'
        f'<select id="secteur" name="secteur">{"".join(secteurs)}</select>'
        '<label for="direction">Direction responsable</label>'
        f'<select id="direction" name="direction">{"".join(directions)}</select>'
        '<label for="statut">Statut</label>'
        f'<select id="statut" name="statut">{"".join(statuts)}</select>'
        '<button type="submit">Filtrer</button>'
        '<a href="/bsd">Effacer le filtre</a></form>'
    )


def _carte(cle, libelle, visible, **attrs):
    extra = "".join(f' data-{nom}="{echapper(valeur)}"' for nom, valeur in attrs.items())
    return (
        '<article class="carte-chiffre">'
        f'<p class="libelle">{echapper(libelle)}</p>'
        f'<p class="valeur" data-indicateur="{echapper(cle)}"{extra}>{echapper(visible)}</p>'
        "</article>"
    )


def _indicateurs(ctx, resume):
    del ctx
    cartes = [
        _carte("projets", "Projets suivis", str(resume["nombre"])),
        _carte("en-cours", "En cours d’exécution", str(resume["en_cours"])),
        _carte("termines", "Projets terminés", str(resume["termines"])),
        _carte("budget", "Budget total (Mds GNF)", fmt_nombre(resume["budget"]), montant=attribut_decimal(resume["budget"])),
        _carte("decaisse", "Budget décaissé (Mds GNF)", fmt_nombre(resume["decaisse"]), montant=attribut_decimal(resume["decaisse"])),
        _carte("avancement", "Avancement physique", fmt_pourcent(resume["avancement"]), taux=attribut_pourcent(resume["avancement"])),
        _carte("decaissement", "Taux de décaissement", fmt_pourcent(resume["decaissement"]), taux=attribut_pourcent(resume["decaissement"])),
        _carte("retard-ou-risque", "En retard ou à risque", str(resume["retard_ou_risque"])),
        _carte("retard", "Dont en retard", str(resume["retard"])),
    ]
    return '<section class="indicateurs" id="indicateurs">' + "".join(cartes) + "</section>"


def _tableau_secteurs(lignes):
    corps = []
    for ligne in lignes:
        part = None
        corps.append(
            f'<tr data-secteur="{echapper(ligne["secteur"])}" data-nombre="{ligne["nombre"]}" '
            f'data-budget="{attribut_decimal(ligne["budget"])}">'
            f'<td>{echapper(ligne["secteur"])}</td>'
            f'<td>{ligne["nombre"]}</td>'
            f'<td>{echapper(fmt_nombre(ligne["budget"]))}</td>'
            f'<td>{echapper(fmt_pourcent(ligne["avancement"]))}</td>'
            f'<td>{echapper(fmt_pourcent(ligne["decaissement"]))}</td>'
            f'<td><span class="barre" aria-hidden="true"><i class="{classe_barre(ligne["avancement"])}"></i></span></td>'
            "</tr>"
        )
        del part
    return (
        "<h2>Situation par secteur</h2>"
        '<div class="defilement"><table><caption>Budget, avancement et décaissement</caption>'
        "<thead><tr><th>Secteur</th><th>Projets</th><th>Budget (Mds GNF)</th>"
        "<th>Avancement</th><th>Décaissement</th><th>Avancement</th></tr></thead><tbody>"
        + "".join(corps) + "</tbody></table></div>"
    )


def _tableau_statuts(lignes):
    corps = []
    for ligne in lignes:
        corps.append(
            f'<tr data-statut="{echapper(ligne["statut"])}" data-nombre="{ligne["nombre"]}" '
            f'data-budget="{attribut_decimal(ligne["budget"])}">'
            f'<td>{_pastille(ligne["statut"])}</td>'
            f'<td>{ligne["nombre"]}</td>'
            f'<td>{echapper(fmt_nombre(ligne["budget"]))}</td>'
            f'<td>{echapper(fmt_pourcent(ligne["part"]))}</td></tr>'
        )
    return (
        "<h2>Répartition par statut</h2>"
        "<table><caption>Nombre et budget selon le statut</caption><thead><tr>"
        "<th>Statut</th><th>Projets</th><th>Budget (Mds GNF)</th><th>Part du budget</th>"
        "</tr></thead><tbody>" + "".join(corps) + "</tbody></table>"
    )


def _liste_attention(ctx, lignes):
    if not lignes:
        return "<h2>Points d’attention</h2><p>Aucun projet en retard ou à risque dans ce filtre.</p>"
    items = []
    for projet in lignes:
        jours = jours_restants(projet, ctx.aujourd_hui)
        items.append(
            f'<li data-code="{echapper(projet["code"])}" data-echeance="{echapper(projet["echeance"])}">'
            f'<a href="/bsd/projet/{int(projet["id"])}">{echapper(projet["code"])}</a> '
            f'{echapper(projet["titre"])} {_pastille(projet["statut"])} '
            f'<span>{echapper(_texte_jours(jours))}</span></li>'
        )
    return (
        "<h2>Points d’attention</h2>"
        "<p>Retards d’abord, puis projets à risque, par échéance. "
        "Le projet suspendu n’y figure pas.</p>"
        f'<ol class="attention" data-attention>{"".join(items)}</ol>'
    )


def _registre(projets, ctx):
    del ctx
    lignes = []
    for projet in projets:
        lignes.append(
            f'<tr data-code="{echapper(projet["code"])}">'
            f'<td><a href="/bsd/projet/{int(projet["id"])}">{echapper(projet["code"])}</a></td>'
            f'<td>{echapper(projet["secteur"])}</td>'
            f'<td>{echapper(projet["titre"])}</td>'
            f'<td>{echapper(projet["localisation"])}</td>'
            f'<td>{_pastille(projet["statut"])}</td>'
            f'<td>{echapper(fmt_nombre(projet["budget_mds"]))}</td>'
            f'<td>{echapper(fmt_pourcent(projet["decaissement"]))}</td>'
            f'<td>{echapper(fmt_pourcent(projet["avancement"]))}</td>'
            f'<td>{echapper(fmt_date(projet["debut"]))}</td>'
            f'<td>{echapper(fmt_date(projet["echeance"]))}</td>'
            f'<td>{echapper(projet["responsable"])}</td>'
            "</tr>"
        )
    vide = "" if lignes else '<tr><td colspan="11">Aucun projet enregistré.</td></tr>'
    return (
        "<h2>Registre</h2>"
        '<div class="defilement"><table class="registre"><caption>Registre des projets</caption><thead><tr>'
        "<th>Identifiant</th><th>Secteur</th><th>Projet</th><th>Localisation</th><th>Statut</th>"
        "<th>Budget</th><th>Décaissement</th><th>Avancement</th><th>Début</th><th>Échéance</th>"
        "<th>Direction responsable</th></tr></thead><tbody>"
        + ("".join(lignes) or vide) + "</tbody></table></div>"
    )


def _fiche(ctx, projet, pieces, structures, rattachee):
    jours = jours_restants(projet, ctx.aujourd_hui)
    decaisse = budget_decaisse(projet)
    champs = [
        ("Identifiant", projet["code"]),
        ("Secteur", projet["secteur"]),
        ("Projet", projet["titre"]),
        ("Localisation", projet["localisation"]),
        ("Statut", projet["statut"]),
        ("Budget (Mds GNF)", fmt_nombre(projet["budget_mds"])),
        ("Décaissement", fmt_pourcent(projet["decaissement"])),
        ("Budget décaissé (Mds GNF)", fmt_nombre(decaisse)),
        ("Avancement physique", fmt_pourcent(projet["avancement"])),
        ("Début", fmt_date(projet["debut"])),
        ("Échéance", fmt_date(projet["echeance"])),
        ("Jours restants", _texte_jours(jours)),
        ("Direction responsable", projet["responsable"]),
        ("Structure de rattachement", rattachee["nom"] if rattachee else "Aucune"),
        ("Source de financement", projet["financement"]),
        ("Prochain jalon", projet["jalon"]),
        ("Observations", projet["observations"]),
    ]
    lignes = "".join(
        f"<dt>{echapper(libelle)}</dt><dd>{echapper(valeur)}</dd>" for libelle, valeur in champs
    )
    actions = ""
    if ctx.utilisateur["administrateur"]:
        actions = f'<p><a class="bouton" href="/bsd/projet/{int(projet["id"])}/modifier">Modifier</a></p>'
    return (
        '<p class="fil"><a href="/bsd">Tableau de bord</a></p>'
        f'<h1>{echapper(projet["code"])}</h1>'
        f"<dl>{lignes}</dl>{actions}"
        + _rattachement(ctx, projet, structures)
        + _elements(ctx, projet, pieces)
    )


def _rattachement(ctx, projet, structures):
    if not est_hierarchie(ctx.utilisateur):
        return ""
    options = ['<option value="">Aucune structure</option>']
    for structure in structures:
        sel = " selected" if projet["structure_id"] == structure["id"] else ""
        options.append(
            f'<option value="{int(structure["id"])}"{sel}>{echapper(structure["nom"])}</option>'
        )
    return (
        "<h2>Rattachement</h2>"
        "<p class=\"aide\">Le rattachement à une direction ou à un service est un choix explicite.</p>"
        f'<form method="post" action="/bsd/projet/{int(projet["id"])}/rattacher" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="structure-rattachement">Direction ou service</label>'
        + f'<select id="structure-rattachement" name="structure_id">{"".join(options)}</select>'
        + '<button type="submit">Rattacher</button></form>'
    )


def _elements(ctx, projet, pieces):
    blocs = [
        _liste_pieces(pieces, "note", "Notes"),
        _liste_pieces(pieces, "rapport", "Rapports"),
        _liste_pieces(pieces, "physique", "Classement des documents physiques"),
    ]
    if not peut_tenir_projet(ctx.utilisateur, projet):
        return "".join(blocs)
    return "".join(blocs) + (
        "<h2>Ajouter un élément</h2>"
        f'<form method="post" action="/bsd/projet/{int(projet["id"])}/piece" '
        'class="formulaire" enctype="multipart/form-data">'
        + jeton_cache(ctx)
        + '<label for="genre-piece">Sorte</label>'
        + '<select id="genre-piece" name="genre" required>'
        + '<option value="note">Note</option>'
        + '<option value="rapport">Rapport</option>'
        + '<option value="physique">Document physique</option>'
        + "</select>"
        + '<label for="titre-piece">Intitulé</label>'
        + '<input id="titre-piece" name="titre" required maxlength="200">'
        + '<label for="texte-piece">Texte</label>'
        + '<textarea id="texte-piece" name="texte" maxlength="4000"></textarea>'
        + '<label for="cote-piece">Cote</label>'
        + '<input id="cote-piece" name="cote" maxlength="80">'
        + '<label for="emplacement-piece">Emplacement</label>'
        + '<input id="emplacement-piece" name="emplacement" maxlength="200">'
        + '<label for="fichier-piece">Fichier</label>'
        + '<input id="fichier-piece" name="fichier" type="file">'
        + "<p class=\"aide\">Une note a un texte. Un rapport a un fichier. "
        "Un document physique a une cote et un emplacement : le papier n’est pas prétendu numérisé.</p>"
        + '<button type="submit">Ajouter au dossier</button></form>'
    )


def _liste_pieces(pieces, genre, titre):
    lignes = []
    for piece in pieces:
        if piece["genre"] != genre:
            continue
        detail = []
        if piece["texte"]:
            detail.append(f"<p>{echapper(piece['texte'])}</p>")
        if piece["cote"]:
            detail.append(f"<p>Cote : {echapper(piece['cote'])}</p>")
        if piece["emplacement"]:
            detail.append(f"<p>Emplacement : {echapper(piece['emplacement'])}</p>")
        if piece["nom_fichier"]:
            detail.append(
                f'<p><a href="/piece/{int(piece["id"])}">{echapper(piece["nom_fichier"])}</a></p>'
            )
        lignes.append(f"<li><strong>{echapper(piece['titre'])}</strong>{''.join(detail)}</li>")
    vide = "<p>Aucun élément.</p>" if not lignes else ""
    return (
        f"<h2>{echapper(titre)}</h2>"
        + vide
        + (f"<ul class=\"pieces\" data-genre-piece=\"{genre}\">{''.join(lignes)}</ul>" if lignes else "")
    )


def _formulaire(ctx, valeurs, projet_id, structures):
    def champ(nom):
        return echapper(valeurs.get(nom, "") or "")

    action = f"/bsd/projet/{int(projet_id)}/modifier" if projet_id else "/bsd/saisie"
    options_secteur = []
    for nom in SECTEURS:
        sel = " selected" if valeurs.get("secteur") == nom else ""
        options_secteur.append(f'<option value="{echapper(nom)}"{sel}>{echapper(nom)}</option>')
    options_statut = []
    for nom in STATUTS:
        sel = " selected" if valeurs.get("statut") == nom else ""
        options_statut.append(f'<option value="{echapper(nom)}"{sel}>{echapper(nom)}</option>')
    financements = "".join(
        f'<option value="{echapper(nom)}"></option>' for nom in FINANCEMENTS_EXEMPLE
    )
    return (
        '<form method="post" action="' + action + '" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="code">Identifiant</label>'
        + f'<input id="code" name="code" required maxlength="20" value="{champ("code")}">'
        + '<label for="secteur-saisie">Secteur</label>'
        + f'<select id="secteur-saisie" name="secteur" required>{"".join(options_secteur)}</select>'
        + '<label for="titre">Projet</label>'
        + f'<input id="titre" name="titre" required maxlength="300" value="{champ("titre")}">'
        + '<label for="localisation">Localisation</label>'
        + f'<input id="localisation" name="localisation" required maxlength="200" value="{champ("localisation")}">'
        + '<label for="statut-saisie">Statut</label>'
        + f'<select id="statut-saisie" name="statut" required>{"".join(options_statut)}</select>'
        + '<label for="budget">Budget (Mds GNF)</label>'
        + f'<input id="budget" name="budget" required inputmode="decimal" value="{champ("budget")}">'
        + '<label for="decaissement">Décaissement (%)</label>'
        + f'<input id="decaissement" name="decaissement" required inputmode="decimal" value="{champ("decaissement")}">'
        + '<label for="avancement">Avancement physique (%)</label>'
        + f'<input id="avancement" name="avancement" required inputmode="decimal" value="{champ("avancement")}">'
        + '<label for="debut">Début</label>'
        + f'<input id="debut" name="debut" type="date" required value="{champ("debut")}">'
        + '<label for="echeance">Échéance</label>'
        + f'<input id="echeance" name="echeance" type="date" required value="{champ("echeance")}">'
        + '<label for="responsable">Direction responsable</label>'
        + f'<input id="responsable" name="responsable" required maxlength="200" value="{champ("responsable")}">'
        + '<label for="structure-saisie">Structure de rattachement</label>'
        + f'<select id="structure-saisie" name="structure_id">{_options_structures(structures, valeurs.get("structure_id"))}</select>'
        + '<p class="aide">Laisser vide si la correspondance avec l’arbre n’est pas établie.</p>'
        + '<label for="financement">Source de financement</label>'
        + f'<input id="financement" name="financement" list="financements" required maxlength="200" value="{champ("financement")}">'
        + f"<datalist id=\"financements\">{financements}</datalist>"
        + '<label for="jalon">Prochain jalon</label>'
        + f'<input id="jalon" name="jalon" required maxlength="300" value="{champ("jalon")}">'
        + '<label for="observations">Observations</label>'
        + f'<textarea id="observations" name="observations" required maxlength="2000">{champ("observations")}</textarea>'
        + '<button type="submit">Enregistrer</button></form>'
    )


def _valeurs_projet(projet):
    return {
        "code": projet["code"],
        "structure_id": "" if projet["structure_id"] is None else str(projet["structure_id"]),
        "secteur": projet["secteur"],
        "titre": projet["titre"],
        "localisation": projet["localisation"],
        "statut": projet["statut"],
        "budget": fmt_nombre(projet["budget_mds"]).replace(" ", ""),
        "decaissement": pourcent_saisi(projet["decaissement"]),
        "avancement": pourcent_saisi(projet["avancement"]),
        "debut": projet["debut"],
        "echeance": projet["echeance"],
        "responsable": projet["responsable"],
        "financement": projet["financement"],
        "jalon": projet["jalon"],
        "observations": projet["observations"],
    }


def _pastille(statut):
    classe = {
        "Terminé": "termine",
        "Dans les délais": "delais",
        "À risque": "risque",
        "En retard": "retard",
        "Suspendu": "suspendu",
        "En préparation": "preparation",
    }.get(statut, "autre")
    return f'<span class="statut statut-{classe}">{echapper(statut)}</span>'


def _structures(conn):
    return conn.execute(
        "SELECT id, nom FROM noeud WHERE genre = 'structure' ORDER BY nom"
    ).fetchall()


def _options_structures(structures, choisi):
    choisi = "" if choisi is None else str(choisi)
    options = ['<option value="">Aucune structure</option>']
    for structure in structures:
        sel = " selected" if str(structure["id"]) == choisi else ""
        options.append(
            f'<option value="{int(structure["id"])}"{sel}>{echapper(structure["nom"])}</option>'
        )
    return "".join(options)


def _structure_formulaire(conn, formulaire):
    brut = (formulaire.get("structure_id") or "").strip()
    if not brut:
        return None
    try:
        structure_id = int(brut)
    except ValueError as exc:
        raise ValeurRefusee("La structure n’est pas dans l’arbre.") from exc
    if conn.execute(
        "SELECT id FROM noeud WHERE id = ? AND genre = 'structure'",
        (structure_id,),
    ).fetchone() is None:
        raise ValeurRefusee("La structure n’est pas dans l’arbre.")
    return structure_id


def _lire_piece(formulaire):
    genre = (formulaire.get("genre") or "").strip()
    if genre not in ("note", "rapport", "physique"):
        raise ValeurRefusee("La sorte d’élément n’est pas reconnue.")
    titre = ligne(formulaire.get("titre"), 2, 200, "Intitulé")
    texte = (formulaire.get("texte") or "").strip()
    cote = (formulaire.get("cote") or "").strip()
    emplacement = (formulaire.get("emplacement") or "").strip()
    if texte:
        texte = bloc(texte, 1, 4000, "Texte")
    if cote:
        cote = ligne(cote, 1, 80, "Cote")
    if emplacement:
        emplacement = ligne(emplacement, 1, 200, "Emplacement")
    if genre == "note" and not texte:
        raise ValeurRefusee("Une note a un texte.")
    if genre == "physique" and (not cote or not emplacement):
        raise ValeurRefusee("Un document physique a une cote et un emplacement.")
    return genre, titre, texte, cote, emplacement


def _texte_jours(nombre):
    if nombre is None:
        return "—"
    if nombre < 0:
        jours = -nombre
        return f"échéance dépassée de {jours} jour" + ("s" if jours != 1 else "")
    if nombre == 0:
        return "échéance aujourd’hui"
    return f"{nombre} jour" + ("s" if nombre != 1 else "")
