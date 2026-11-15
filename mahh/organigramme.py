"""Organigramme des directions et attributions, tenus par l’administrateur."""

from mahh.db import base
from mahh.droits import exiger_admin
from mahh.presentation import jeton_cache
from mahh.reponse import ValeurRefusee
from mahh.securite import maintenant, url_sure
from mahh.texte import echapper
from mahh.validation import ligne


def rendu_organigramme(ctx, conn, noeud_id=None, edition=True):
    postes = _visibles(conn, ctx.utilisateur)
    racines = _racines(postes, noeud_id)
    schema = _schema(racines, _enfants(postes))
    if not schema:
        schema = '<p class="vide">Aucune case dans cette branche.</p>'
    outils = ""
    if ctx.utilisateur["administrateur"] and edition:
        outils = _forme_organigramme(ctx, postes)
    elif ctx.utilisateur["administrateur"]:
        outils = '<p><a href="/directions">Modifier l’organigramme</a></p>'
    return (
        '<section data-fonction="organigramme">'
        "<h2>Organigramme</h2>"
        '<p class="chapeau">Schéma des directions. L’administrateur ajoute, déplace et retire les cases.</p>'
        f'<div class="schema" data-organigramme="1">{schema}</div>'
        f"{outils}"
        "</section>"
    )


def rendu_attributions(ctx, conn, noeud_id=None):
    structures = _structures_visibles(conn, ctx.utilisateur, noeud_id)
    if not structures:
        return ""
    domaines = {}
    for structure in structures:
        domaines.setdefault(structure["domaine"], []).append(structure)
    blocs = []
    for domaine, lignes in domaines.items():
        menus = "".join(_menu(ctx, conn, structure) for structure in lignes)
        blocs.append(f'<section class="domaine-attributions"><h3>{echapper(domaine)}</h3>{menus}</section>')
    return (
        '<section data-fonction="attribution">'
        "<h2>Attributions</h2>"
        '<p class="chapeau">Un menu par direction. Il se déplie et contient les attributions de cette direction.</p>'
        + "".join(blocs)
        + "</section>"
    )


def action_creer_poste(ctx):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    try:
        nom, intitule, parent_id = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        try:
            _verifier_parent(conn, parent_id, None)
        except ValeurRefusee as exc:
            return page_directions(ctx, erreur=exc.message)
        if parent_id is None:
            ordre = conn.execute(
                "SELECT COALESCE(MAX(ordre), 0) + 1 AS n FROM organigramme WHERE parent_id IS NULL"
            ).fetchone()["n"]
        else:
            ordre = conn.execute(
                "SELECT COALESCE(MAX(ordre), 0) + 1 AS n FROM organigramme WHERE parent_id = ?",
                (parent_id,),
            ).fetchone()["n"]
        quand = maintenant()
        conn.execute(
            """
            INSERT INTO organigramme (parent_id, nom, intitule, ordre, cree_le, modifie_le)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (parent_id, nom, intitule, ordre, quand, quand),
        )
    return _retour(ctx, "poste-cree")


def action_modifier_poste(ctx, poste_id):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    try:
        nom, intitule, parent_id = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        try:
            _verifier_parent(conn, parent_id, poste["id"])
        except ValeurRefusee as exc:
            return page_directions(ctx, erreur=exc.message)
        conn.execute(
            """
            UPDATE organigramme
            SET nom = ?, intitule = ?, parent_id = ?, modifie_le = ?
            WHERE id = ?
            """,
            (nom, intitule, parent_id, maintenant(), poste["id"]),
        )
    return _retour(ctx, "poste-modifie")


def action_retirer_poste(ctx, poste_id):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        if poste["noeud_id"]:
            return page_directions(
                ctx,
                erreur="Cette case est une direction du ministère. Retirez seulement une case ajoutée.",
            )
        conn.execute("DELETE FROM organigramme WHERE id = ?", (poste["id"],))
    return _retour(ctx, "poste-retire")


def action_creer_attribution(ctx):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    try:
        noeud_id, texte = _saisie_attribution(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        if not _est_structure(conn, noeud_id):
            return page_directions(ctx, erreur="Choisissez une direction.")
        ordre = conn.execute(
            "SELECT COALESCE(MAX(ordre), 0) + 1 AS n FROM attribution WHERE noeud_id = ?",
            (noeud_id,),
        ).fetchone()["n"]
        conn.execute(
            """
            INSERT INTO attribution (noeud_id, texte, ordre, modifie_le)
            VALUES (?, ?, ?, ?)
            """,
            (noeud_id, texte, ordre, maintenant()),
        )
    return _retour(ctx, "attribution-creee")


def action_modifier_attribution(ctx, attribution_id):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    try:
        texte = ligne(ctx.formulaire.get("texte"), 2, 500, "Attribution")
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        attribution = _attribution(conn, attribution_id)
        if attribution is None:
            return page_directions(ctx, erreur="Cette attribution n’existe pas.")
        conn.execute(
            "UPDATE attribution SET texte = ?, modifie_le = ? WHERE id = ?",
            (texte, maintenant(), attribution["id"]),
        )
    return _retour(ctx, "attribution-modifiee")


def action_retirer_attribution(ctx, attribution_id):
    from mahh.documents import page_directions

    exiger_admin(ctx)
    with base() as conn:
        attribution = _attribution(conn, attribution_id)
        if attribution is None:
            return page_directions(ctx, erreur="Cette attribution n’existe pas.")
        conn.execute("DELETE FROM attribution WHERE id = ?", (attribution["id"],))
    return _retour(ctx, "attribution-retiree")


def _retour(ctx, message):
    from mahh.reponse import Redirection

    retour = url_sure(ctx.formulaire.get("retour") or "/directions")
    separateur = "&" if "?" in retour else "?"
    return Redirection(f"{retour}{separateur}message={message}")


def _saisie_poste(formulaire):
    nom = ligne(formulaire.get("nom"), 2, 120, "Nom")
    brut = (formulaire.get("intitule") or "").strip()
    intitule = ligne(brut, 2, 200, "Intitulé") if brut else ""
    parent = (formulaire.get("parent_id") or "").strip()
    if not parent:
        return nom, intitule, None
    try:
        return nom, intitule, int(parent)
    except ValueError as exc:
        raise ValeurRefusee("Le rattachement n’est pas reconnu.") from exc


def _saisie_attribution(formulaire):
    try:
        noeud_id = int(formulaire.get("noeud_id") or "")
    except ValueError as exc:
        raise ValeurRefusee("Choisissez une direction.") from exc
    return noeud_id, ligne(formulaire.get("texte"), 2, 500, "Attribution")


def _verifier_parent(conn, parent_id, poste_id):
    if parent_id is None:
        return
    if poste_id is not None and parent_id == poste_id:
        raise ValeurRefusee("Une case ne peut pas se rattacher à elle-même.")
    parent = _poste(conn, parent_id)
    if parent is None:
        raise ValeurRefusee("Le rattachement n’est pas reconnu.")
    if poste_id is None:
        return
    courant = parent
    garde = 0
    while courant is not None and garde < 30:
        if courant["id"] == poste_id:
            raise ValeurRefusee("Une case ne peut pas se rattacher à l’une de ses cases.")
        if courant["parent_id"] is None:
            break
        courant = _poste(conn, courant["parent_id"])
        garde += 1


def _visibles(conn, utilisateur):
    postes = conn.execute(
        "SELECT * FROM organigramme ORDER BY ordre, nom, id"
    ).fetchall()
    from mahh.documents import _noeud, _visible

    if _tout_voir(utilisateur):
        return postes
    par_id = {poste["id"]: poste for poste in postes}
    enfants = {}
    for poste in postes:
        if poste["parent_id"]:
            enfants.setdefault(poste["parent_id"], []).append(poste["id"])
    gardes = set()
    for poste in postes:
        if not poste["noeud_id"]:
            continue
        noeud = _noeud(conn, poste["noeud_id"])
        if noeud is None or noeud["genre"] == "domaine":
            continue
        if _visible(conn, utilisateur, noeud):
            gardes.add(poste["id"])
    origines = set(gardes)
    for identifiant in origines:
        courant = par_id[identifiant]["parent_id"]
        while courant:
            gardes.add(courant)
            courant = par_id[courant]["parent_id"] if courant in par_id else None
    pile = list(origines)
    while pile:
        identifiant = pile.pop()
        for enfant in enfants.get(identifiant, []):
            if enfant not in gardes:
                gardes.add(enfant)
                pile.append(enfant)
    return [poste for poste in postes if poste["id"] in gardes]


def _structures_visibles(conn, utilisateur, noeud_id):
    from mahh.documents import _noeud, _visible

    requete = """
        SELECT structure.*, domaine.nom AS domaine
        FROM noeud AS structure
        JOIN noeud AS domaine ON domaine.id = structure.parent_id
        WHERE structure.genre = 'structure' AND domaine.genre = 'domaine'
        ORDER BY domaine.ordre, structure.ordre, structure.nom
    """
    lignes = []
    for structure in conn.execute(requete).fetchall():
        if noeud_id is not None and structure["id"] != noeud_id and structure["parent_id"] != noeud_id:
            continue
        if noeud_id is not None and structure["id"] != noeud_id and structure["parent_id"] == noeud_id:
            pass
        if not _tout_voir(utilisateur):
            noeud = _noeud(conn, structure["id"])
            if noeud is None or not _visible(conn, utilisateur, noeud):
                continue
        lignes.append(structure)
    if noeud_id is not None:
        return [ligne for ligne in lignes if ligne["id"] == noeud_id or ligne["parent_id"] == noeud_id]
    return lignes


def _tout_voir(utilisateur):
    from mahh.droits import est_hierarchie

    return est_hierarchie(utilisateur)


def _enfants(postes):
    groupes = {}
    for poste in postes:
        groupes.setdefault(poste["parent_id"], []).append(poste)
    return groupes


def _racines(postes, noeud_id):
    if noeud_id is None:
        return [poste for poste in postes if poste["parent_id"] is None]
    ancre = next((poste for poste in postes if poste["noeud_id"] == noeud_id), None)
    if ancre is None:
        return []
    return [ancre]


def _schema(racines, enfants):
    return "".join(_branche(poste, enfants) for poste in racines)


def _branche(poste, enfants):
    suite = enfants.get(poste["id"], [])
    dessous = ""
    if suite:
        dessous = f'<div class="enfants">{"".join(_branche(enfant, enfants) for enfant in suite)}</div>'
    if poste["noeud_id"]:
        nom = (
            f'<a href="/noeud/{int(poste["noeud_id"])}" data-nom="{echapper(poste["nom"])}">'
            f'{echapper(poste["nom"])}</a>'
        )
    else:
        nom = f'<strong data-nom="{echapper(poste["nom"])}">{echapper(poste["nom"])}</strong>'
    intitule = (
        f'<p class="intitule">{echapper(poste["intitule"])}</p>' if poste["intitule"] else ""
    )
    classe = "boite boite-racine" if poste["parent_id"] is None else "boite"
    return (
        '<div class="branche">'
        f'<div class="{classe}" data-poste="{int(poste["id"])}" data-nom="{echapper(poste["nom"])}">'
        f"{nom}{intitule}</div>{dessous}</div>"
    )


def _menu(ctx, conn, structure):
    attributions = conn.execute(
        "SELECT * FROM attribution WHERE noeud_id = ? ORDER BY ordre, id",
        (structure["id"],),
    ).fetchall()
    if attributions:
        lignes = []
        for attribution in attributions:
            lignes.append(_ligne_attribution(ctx, attribution))
        corps = f'<ol class="attributions">{"".join(lignes)}</ol>'
    else:
        corps = '<p class="vide">Aucune attribution enregistrée.</p>'
    if ctx.utilisateur["administrateur"]:
        corps += (
            f'<form method="post" action="/attribution" class="formulaire">'
            f'{jeton_cache(ctx)}'
            f'<input type="hidden" name="noeud_id" value="{int(structure["id"])}">'
            f'<input type="hidden" name="retour" value="/noeud/{int(structure["id"])}">'
            f'<label for="attribution-{int(structure["id"])}">Ajouter une attribution</label>'
            f'<input id="attribution-{int(structure["id"])}" name="texte" maxlength="500" required>'
            '<button type="submit">Ajouter</button></form>'
        )
    intitule = (
        f' <span class="intitule">{echapper(structure["intitule"])}</span>'
        if structure["intitule"]
        else ""
    )
    return (
        f'<details class="menu-direction" data-direction="{echapper(structure["nom"])}">'
        f"<summary>{echapper(structure['nom'])}{intitule}</summary>"
        f"{corps}</details>"
    )


def _ligne_attribution(ctx, attribution):
    texte = f'<span>{echapper(attribution["texte"])}</span>'
    if not ctx.utilisateur["administrateur"]:
        return f'<li data-attribution="{int(attribution["id"])}">{texte}</li>'
    identifiant = int(attribution["id"])
    return (
        f'<li data-attribution="{identifiant}">{texte}'
        f'<form method="post" action="/attribution/{identifiant}" class="ligne-form">'
        f'{jeton_cache(ctx)}'
        '<input type="hidden" name="retour" value="/directions">'
        f'<label class="visually-hidden" for="texte-{identifiant}">Attribution</label>'
        f'<input id="texte-{identifiant}" name="texte" maxlength="500" required value="{echapper(attribution["texte"])}">'
        '<button type="submit" class="secondaire">Enregistrer</button></form>'
        f'<form method="post" action="/attribution/{identifiant}/retirer" class="ligne-form">'
        f'{jeton_cache(ctx)}'
        '<input type="hidden" name="retour" value="/directions">'
        '<button type="submit" class="danger">Retirer</button></form>'
        "</li>"
    )


def _forme_organigramme(ctx, postes):
    options = '<option value="">Au premier rang</option>' + "".join(
        f'<option value="{int(poste["id"])}">{echapper(_chemin(poste, postes))}</option>'
        for poste in postes
    )
    ajout = (
        '<form method="post" action="/organigramme" class="formulaire" data-creation="organigramme">'
        f"{jeton_cache(ctx)}"
        '<input type="hidden" name="retour" value="/directions">'
        '<label for="nom-poste">Nom de la case</label>'
        '<input id="nom-poste" name="nom" maxlength="120" required>'
        '<label for="intitule-poste">Intitulé</label>'
        '<input id="intitule-poste" name="intitule" maxlength="200">'
        '<label for="parent-poste">Rattachement</label>'
        f'<select id="parent-poste" name="parent_id">{options}</select>'
        '<button type="submit">Ajouter la case</button></form>'
    )
    lignes = []
    for poste in postes:
        identifiant = int(poste["id"])
        interdits = _descendants(poste["id"], postes) | {poste["id"]}
        choix = '<option value="">Au premier rang</option>' + "".join(
            f'<option value="{int(autre["id"])}"'
            f'{" selected" if autre["id"] == poste["parent_id"] else ""}>'
            f'{echapper(_chemin(autre, postes))}</option>'
            for autre in postes
            if autre["id"] not in interdits
        )
        retrait = ""
        if not poste["noeud_id"]:
            retrait = (
                f'<form method="post" action="/organigramme/{identifiant}/retirer">'
                f"{jeton_cache(ctx)}"
                '<input type="hidden" name="retour" value="/directions">'
                '<button type="submit" class="danger">Retirer la case</button></form>'
            )
        lignes.append(
            f'<form method="post" action="/organigramme/{identifiant}" class="formulaire" data-poste="{identifiant}">'
            f"{jeton_cache(ctx)}"
            '<input type="hidden" name="retour" value="/directions">'
            f'<label for="nom-{identifiant}">Nom</label>'
            f'<input id="nom-{identifiant}" name="nom" maxlength="120" required value="{echapper(poste["nom"])}">'
            f'<label for="intitule-{identifiant}">Intitulé</label>'
            f'<input id="intitule-{identifiant}" name="intitule" maxlength="200" value="{echapper(poste["intitule"])}">'
            f'<label for="parent-{identifiant}">Rattachement</label>'
            f'<select id="parent-{identifiant}" name="parent_id">{choix}</select>'
            '<button type="submit">Enregistrer</button></form>'
            f"{retrait}"
        )
    return (
        '<section class="outils"><h2>Construire l’organigramme</h2>'
        f"{ajout}<h3>Modifier les cases</h3>{''.join(lignes)}</section>"
    )


def _descendants(poste_id, postes):
    enfants = {}
    for poste in postes:
        if poste["parent_id"]:
            enfants.setdefault(poste["parent_id"], []).append(poste["id"])
    vus = set()
    pile = list(enfants.get(poste_id, []))
    while pile:
        identifiant = pile.pop()
        if identifiant in vus:
            continue
        vus.add(identifiant)
        pile.extend(enfants.get(identifiant, []))
    return vus


def _chemin(poste, postes):
    par_id = {element["id"]: element for element in postes}
    noms = [poste["nom"]]
    courant = poste["parent_id"]
    garde = 0
    while courant and garde < 12:
        parent = par_id.get(courant)
        if parent is None:
            break
        noms.append(parent["nom"])
        courant = parent["parent_id"]
        garde += 1
    noms.reverse()
    return " / ".join(noms)


def _poste(conn, poste_id):
    try:
        identifiant = int(poste_id)
    except (TypeError, ValueError):
        return None
    return conn.execute("SELECT * FROM organigramme WHERE id = ?", (identifiant,)).fetchone()


def _attribution(conn, attribution_id):
    try:
        identifiant = int(attribution_id)
    except (TypeError, ValueError):
        return None
    return conn.execute("SELECT * FROM attribution WHERE id = ?", (identifiant,)).fetchone()


def _est_structure(conn, noeud_id):
    return conn.execute(
        "SELECT id FROM noeud WHERE id = ? AND genre = 'structure'",
        (noeud_id,),
    ).fetchone() is not None
