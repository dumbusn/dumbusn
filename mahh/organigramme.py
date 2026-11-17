"""Organigramme des directions et attributions.

L’arbre démarre vide. Seul l’administrateur crée une entité racine, puis des
sous-entités (code, nom, rattachement) et y affecte des agents déjà créés.
"""

import re

from mahh.db import base
from mahh.droits import FONCTIONS, exiger_admin, exiger_organigramme, peut_tenir_organigramme
from mahh.presentation import jeton_cache, page
from mahh.reponse import ValeurRefusee
from mahh.securite import maintenant, url_sure
from mahh.texte import echapper
from mahh.validation import ligne

_ROLES_MINISTERE = ("ministre", "secretaire_general", "chef_cabinet")


def page_organigramme(ctx, erreur=None):
    exiger_organigramme(ctx)
    with base() as conn:
        corps = rendu_organigramme(ctx, conn, plein=True)
    return page("Organigramme", corps, ctx, actif="organigramme", erreur=erreur)


def rendu_organigramme(ctx, conn, noeud_id=None, edition=True, plein=False):
    postes = _visibles(conn, ctx.utilisateur)
    racines = _racines(postes, noeud_id)
    enfants = _enfants(postes)
    membres = _membres(conn)
    tenir = bool(edition and peut_tenir_organigramme(ctx.utilisateur))
    arbre = _foret(ctx, racines, enfants, membres, tenir)
    if not arbre:
        arbre = '<p class="vide">Aucune entité enregistrée.</p>'
    nombre = len(postes) if noeud_id is None else _compter_branche(racines, enfants)
    libelle = "1 entité" if nombre == 1 else f"{nombre} entités"
    outils = _dialogues(ctx, conn, postes, membres) if tenir else ""
    panneau = ""
    if tenir and noeud_id is None:
        requete = ctx.requete if hasattr(ctx, "requete") else {}
        panneau = _panneau_suppression(ctx, postes, enfants, membres, _entier(requete.get("retirer")))
    bouton = ""
    if tenir:
        bouton = '<a class="bouton" href="#nouvelle-entite">+ Nouvelle entité racine</a>'
    titre = "<h1>Organigramme</h1>" if plein else "<h2>Organigramme</h2>"
    return (
        '<section class="org" data-fonction="organigramme" data-organigramme="1">'
        '<header class="org-entete">'
        "<div>"
        '<p class="sur-titre">Structure</p>'
        f"{titre}"
        '<p class="chapeau">Directions, services et affectation des agents. '
        "Les entités se créent depuis la racine, puis se rattachent.</p>"
        "</div>"
        f"{bouton}"
        "</header>"
        f"{panneau}"
        '<section class="carte-arbre">'
        f"<h2>Arborescence ({libelle})</h2>"
        f'<ul class="arbre">{arbre}</ul>'
        "</section>"
        f"{_sans_affectation(conn) if noeud_id is None else ''}"
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
    exiger_organigramme(ctx)
    try:
        code, nom, intitule, parent_id, niveau = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_organigramme(ctx, erreur=exc.message)
    with base() as conn:
        try:
            _verifier_parent(conn, parent_id, None)
            _verifier_code(conn, code, None)
        except ValeurRefusee as exc:
            return page_organigramme(ctx, erreur=exc.message)
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
            INSERT INTO organigramme (
                parent_id, code, nom, intitule, ordre, niveau, cree_le, modifie_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (parent_id, code, nom, intitule, ordre, niveau, quand, quand),
        )
    return _retour(ctx, "poste-cree")


def action_modifier_poste(ctx, poste_id):
    exiger_organigramme(ctx)
    try:
        code, nom, intitule, parent_id, niveau = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_organigramme(ctx, erreur=exc.message)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_organigramme(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        try:
            _verifier_parent(conn, parent_id, poste["id"])
            _verifier_code(conn, code, poste["id"])
        except ValeurRefusee as exc:
            return page_organigramme(ctx, erreur=exc.message)
        conn.execute(
            """
            UPDATE organigramme
            SET code = ?, nom = ?, intitule = ?, parent_id = ?, niveau = ?, modifie_le = ?
            WHERE id = ?
            """,
            (code, nom, intitule, parent_id, niveau, maintenant(), poste["id"]),
        )
    return _retour(ctx, "poste-modifie")


def action_retirer_poste(ctx, poste_id):
    exiger_organigramme(ctx)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_organigramme(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        if poste["noeud_id"]:
            return page_organigramme(
                ctx,
                erreur="Cette case est une direction du ministère. Retirez seulement une case ajoutée.",
            )
        enfants = conn.execute(
            "SELECT COUNT(*) AS n FROM organigramme WHERE parent_id = ?",
            (poste["id"],),
        ).fetchone()["n"]
        agents = conn.execute(
            "SELECT COUNT(*) AS n FROM utilisateur WHERE organigramme_id = ?",
            (poste["id"],),
        ).fetchone()["n"]
        if enfants or agents:
            from mahh.reponse import Redirection

            return Redirection(f"/organigramme?retirer={int(poste['id'])}")
        conn.execute("DELETE FROM organigramme WHERE id = ?", (poste["id"],))
    return _retour(ctx, "poste-retire")


def action_detacher(ctx, poste_id):
    """Retire les agents de l’entité, sans changer leur rôle."""
    exiger_organigramme(ctx)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_organigramme(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        conn.execute(
            "UPDATE utilisateur SET organigramme_id = NULL WHERE organigramme_id = ?",
            (poste["id"],),
        )
    from mahh.reponse import Redirection

    return Redirection(f"/organigramme?retirer={int(poste['id'])}")


def action_affecter_liste(ctx):
    return action_affecter(ctx, ctx.formulaire.get("poste_id"))


def action_affecter(ctx, poste_id):
    exiger_organigramme(ctx)
    try:
        utilisateur_id = int((ctx.formulaire.get("utilisateur_id") or "").strip())
    except ValueError:
        return page_organigramme(ctx, erreur="Choisissez une personne.")
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_organigramme(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        personne = conn.execute(
            "SELECT id, fonction FROM utilisateur WHERE id = ? AND actif = 1",
            (utilisateur_id,),
        ).fetchone()
        if personne is None:
            return page_organigramme(ctx, erreur="Cette personne n’est pas dans l’annuaire.")
        # Le modèle ne change que le rattachement. Le rôle reste celui de la fiche.
        # Le périmètre de direction suit l’entité quand elle est sous une direction.
        structure_id = _structure_du_poste(conn, poste)
        if (personne["fonction"] or "") in _ROLES_MINISTERE:
            structure_id = None
        if structure_id is None:
            conn.execute(
                "UPDATE utilisateur SET organigramme_id = ? WHERE id = ?",
                (poste["id"], personne["id"]),
            )
        else:
            conn.execute(
                "UPDATE utilisateur SET organigramme_id = ?, structure_id = ? WHERE id = ?",
                (poste["id"], structure_id, personne["id"]),
            )
    return _retour(ctx, "personne-affectee")


def action_desaffecter(ctx, poste_id):
    exiger_organigramme(ctx)
    try:
        utilisateur_id = int((ctx.formulaire.get("utilisateur_id") or "").strip())
    except ValueError:
        return page_organigramme(ctx, erreur="Choisissez une personne.")
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_organigramme(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        conn.execute(
            """
            UPDATE utilisateur
            SET organigramme_id = NULL
            WHERE id = ? AND organigramme_id = ? AND administrateur = 0
            """,
            (utilisateur_id, poste["id"]),
        )
    return _retour(ctx, "personne-retiree")


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
    code = (formulaire.get("code") or "").strip().upper()
    if code and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,19}", code) is None:
        raise ValeurRefusee("Le code ne contient que des lettres, des chiffres et le tiret.")
    nom = ligne(formulaire.get("nom"), 2, 120, "Nom")
    brut = (formulaire.get("intitule") or "").strip()
    intitule = ligne(brut, 2, 200, "Intitulé") if brut else ""
    niveau = (formulaire.get("niveau") or "").strip()
    if niveau and niveau not in _niveaux_poste():
        raise ValeurRefusee("Ce rôle n’est pas parmi les niveaux prévus.")
    parent = (formulaire.get("parent_id") or "").strip()
    if not parent:
        return code, nom, intitule, None, niveau
    try:
        return code, nom, intitule, int(parent), niveau
    except ValueError as exc:
        raise ValeurRefusee("Le rattachement n’est pas reconnu.") from exc


def _verifier_code(conn, code, poste_id):
    if not code:
        return
    autre = conn.execute(
        "SELECT id FROM organigramme WHERE code = ? AND id != ?",
        (code, poste_id or 0),
    ).fetchone()
    if autre:
        raise ValeurRefusee("Ce code est déjà utilisé.")


def _structure_du_poste(conn, poste):
    courant = poste
    garde = 0
    while courant is not None and garde < 40:
        if courant["noeud_id"] and _est_structure(conn, courant["noeud_id"]):
            return courant["noeud_id"]
        if courant["parent_id"] is None:
            break
        courant = _poste(conn, courant["parent_id"])
        garde += 1
    return None


def _niveaux_poste():
    return (
        "ministre",
        "secretaire_general",
        "chef_cabinet",
        "directeur",
        "directeur_adjoint",
        "chef_division",
        "chef_section",
        "charge_etudes",
    )


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
    for liste in groupes.values():
        liste.sort(key=lambda poste: (poste["ordre"], (poste["code"] or "").upper(), poste["nom"].upper()))
    return groupes


def _racines(postes, noeud_id):
    if noeud_id is None:
        racines = [poste for poste in postes if poste["parent_id"] is None]
        racines.sort(key=lambda poste: (poste["ordre"], (poste["code"] or "").upper(), poste["nom"].upper()))
        return racines
    ancre = next((poste for poste in postes if poste["noeud_id"] == noeud_id), None)
    if ancre is None:
        return []
    return [ancre]


def _membres(conn):
    groupes = {}
    for personne in conn.execute(
        """
        SELECT id, identifiant, nom, organigramme_id
        FROM utilisateur
        WHERE actif = 1 AND organigramme_id IS NOT NULL
        ORDER BY nom
        """
    ).fetchall():
        groupes.setdefault(personne["organigramme_id"], []).append(personne)
    return groupes


def _compter_branche(racines, enfants):
    total = 0
    pile = list(racines)
    while pile:
        poste = pile.pop()
        total += 1
        pile.extend(enfants.get(poste["id"], []))
    return total


def _foret(ctx, racines, enfants, membres, tenir):
    return "".join(
        _ligne_entite(ctx, poste, enfants, membres, tenir, 0) for poste in racines
    )


def _ligne_entite(ctx, poste, enfants, membres, tenir, profondeur):
    suite = enfants.get(poste["id"], [])
    gens = membres.get(poste["id"], [])
    code = (
        f'<span class="code-entite">{echapper(poste["code"])}</span>'
        if poste["code"]
        else ""
    )
    nom = echapper(poste["nom"])
    role = FONCTIONS.get(poste["niveau"] or "", "")
    role_html = f'<span class="role-entite">{echapper(role)}</span>' if role else ""
    affectes = "".join(
        f'<span class="visually-hidden" data-affecte="{echapper(personne["identifiant"])}"></span>'
        for personne in gens
    )
    attributs = f'data-poste="{int(poste["id"])}" data-nom="{echapper(poste["nom"])}"'
    if poste["code"]:
        attributs += f' data-code="{echapper(poste["code"])}"'
    if poste["niveau"]:
        attributs += f' data-niveau="{echapper(poste["niveau"])}"'
    compteur = (
        f'<span class="compteur" title="{len(gens)}">{len(gens)}</span>' if gens else ""
    )
    actions = _actions_entite(ctx, poste, suite, gens) if tenir else ""
    etiquette = (
        f'<span class="etiquette-entite" {attributs}>{code} '
        f'<span class="nom-entite">{nom}</span> {role_html} {compteur}{affectes}</span>'
    )
    if suite:
        dessous = "".join(
            _ligne_entite(ctx, enfant, enfants, membres, tenir, profondeur + 1)
            for enfant in suite
        )
        ouvert = " open" if profondeur == 0 else ""
        return (
            f"<li><details{ouvert}><summary>{etiquette}</summary>"
            f"{actions}<ul class=\"arbre\">{dessous}</ul></details></li>"
        )
    return f'<li class="feuille"><div class="ligne-org">{etiquette}{actions}</div></li>'


def _actions_entite(ctx, poste, enfants, membres):
    identifiant = int(poste["id"])
    chemin = "/organigramme"
    boutons = (
        f'<a class="bouton secondaire bouton-ligne" href="{chemin}?affecter={identifiant}#affecter-agent">Affecter</a> '
        f'<a class="bouton secondaire bouton-ligne" href="{chemin}?parent={identifiant}#nouvelle-entite">Sous-entité</a> '
        f'<a class="bouton secondaire bouton-ligne" href="{chemin}?modifier={identifiant}#modifier-entite">Modifier</a> '
    )
    if poste["noeud_id"]:
        return f'<span class="actions-entite">{boutons}</span>'
    if not enfants and not membres:
        retrait = (
            f'<form class="action-ligne" method="post" action="/organigramme/{identifiant}/retirer">'
            f"{jeton_cache(ctx)}"
            '<input type="hidden" name="retour" value="/organigramme">'
            '<button type="submit" class="danger bouton-ligne">Supprimer</button></form>'
        )
    else:
        retrait = (
            f'<a class="bouton secondaire bouton-ligne danger" href="{chemin}?retirer={identifiant}">Supprimer</a>'
        )
    return f'<span class="actions-entite">{boutons}{retrait}</span>'


def _panneau_suppression(ctx, postes, enfants, membres, retirer_id):
    if not retirer_id:
        return ""
    poste = next((element for element in postes if element["id"] == retirer_id), None)
    if poste is None or poste["noeud_id"]:
        return ""
    fils = enfants.get(poste["id"], [])
    gens = membres.get(poste["id"], [])
    identifiant = int(poste["id"])
    if not fils and not gens:
        return (
            '<section class="carte-arbre alerte-suppression">'
            f"<h2>Supprimer « {echapper(poste['nom'])} »</h2>"
            "<p>Cette entité n’a ni sous-entité ni agent. Elle peut être supprimée.</p>"
            f'<form method="post" action="/organigramme/{identifiant}/retirer">'
            f"{jeton_cache(ctx)}"
            '<input type="hidden" name="retour" value="/organigramme">'
            '<button type="submit" class="danger">Supprimer</button></form>'
            "</section>"
        )
    blocs = []
    if gens:
        texte = "1 agent y est encore affecté." if len(gens) == 1 else f"{len(gens)} agents y sont encore affectés."
        blocs.append(
            f"<p>{texte} Détachez-les, puis supprimez l’entité.</p>"
            f'<form method="post" action="/organigramme/{identifiant}/detacher">'
            f"{jeton_cache(ctx)}"
            '<button type="submit" class="secondaire">Détacher les agents</button></form>'
        )
    if fils:
        texte = (
            "1 sous-entité y est rattachée."
            if len(fils) == 1
            else f"{len(fils)} sous-entités y sont rattachées."
        )
        lignes = []
        for enfant in fils:
            nom = echapper(enfant["nom"])
            if enfant["noeud_id"] or enfants.get(enfant["id"]) or membres.get(enfant["id"]):
                lignes.append(
                    f'<li><a class="bouton secondaire" href="/organigramme?retirer={int(enfant["id"])}">'
                    f"Supprimer « {nom} » d’abord</a></li>"
                )
            else:
                lignes.append(
                    "<li>"
                    f'<form method="post" action="/organigramme/{int(enfant["id"])}/retirer">'
                    f"{jeton_cache(ctx)}"
                    f'<input type="hidden" name="retour" value="/organigramme?retirer={identifiant}">'
                    f'<button type="submit" class="danger">Supprimer « {nom} »</button></form></li>'
                )
        blocs.append(
            f"<p>{texte} Supprimez les sous-entités d’abord.</p>"
            f'<ul class="actions-detacher">{"".join(lignes)}</ul>'
        )
    return (
        '<section class="carte-arbre alerte-suppression">'
        f"<h2>Supprimer « {echapper(poste['nom'])} »</h2>"
        "<p>La suppression est refusée tant que des sous-entités ou des agents y sont rattachés.</p>"
        + "".join(blocs)
        + "</section>"
    )


def _sans_affectation(conn):
    personnes = conn.execute(
        """
        SELECT nom, matricule FROM utilisateur
        WHERE actif = 1 AND administrateur = 0 AND organigramme_id IS NULL
        ORDER BY nom
        """
    ).fetchall()
    if not personnes:
        return ""
    pastilles = "".join(
        "<span class=\"pastille\">"
        f"{echapper(personne['nom'])}"
        + (
            f" <span class=\"meta-agent\">· {echapper(personne['matricule'])}</span>"
            if personne["matricule"]
            else ""
        )
        + "</span>"
        for personne in personnes
    )
    return (
        '<section class="carte-arbre orphelins">'
        f"<h2>Agents sans affectation ({len(personnes)})</h2>"
        f'<p class="pastilles">{pastilles}</p>'
        "</section>"
    )


def _dialogues(ctx, conn, postes, membres):
    requete = ctx.requete if hasattr(ctx, "requete") else {}
    parent_voulu = _entier(requete.get("parent"))
    modifier_id = _entier(requete.get("modifier"))
    affecter_id = _entier(requete.get("affecter"))
    cible = next((poste for poste in postes if poste["id"] == modifier_id), None)
    personnes = conn.execute(
        """
        SELECT id, identifiant, nom, courriel, matricule, intitule_poste,
               organigramme_id, administrateur
        FROM utilisateur WHERE actif = 1
        ORDER BY nom, identifiant
        """
    ).fetchall()
    choix_personnes = "".join(
        f'<option value="{int(personne["id"])}" data-identifiant="{echapper(personne["identifiant"])}">'
        f'{echapper(personne["nom"])}</option>'
        for personne in personnes
        if not personne["administrateur"]
    )
    retour = ctx.chemin if ctx.chemin in ("/organigramme", "/directions") else "/organigramme"
    creation = (
        f'<div class="voile" id="nouvelle-entite" hidden><form class="dialogue" method="post" action="/organigramme">'
        f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
        "<h2>Nouvelle entité</h2>"
        '<p class="chapeau">Direction, département ou service. Le code doit être unique.</p>'
        f"{jeton_cache(ctx)}"
        f'<input type="hidden" name="retour" value="{echapper(retour)}">'
        '<div class="champ"><label for="code-poste">Code *</label>'
        '<input id="code-poste" name="code" maxlength="20" required autocomplete="off" class="majuscules"></div>'
        '<div class="champ"><label for="nom-poste">Nom *</label>'
        '<input id="nom-poste" name="nom" maxlength="120" required></div>'
        '<div class="champ"><label for="parent-poste">Rattachement</label>'
        f'<select id="parent-poste" name="parent_id">{_options_parents(postes, parent_voulu, set())}</select></div>'
        '<p class="pied-dialogue"><a class="bouton secondaire" href="'
        f'{echapper(retour)}">Annuler</a><button type="submit">Créer</button></p>'
        "</form></div>"
    )
    if cible is None and postes:
        cible = postes[0]
    edition = ""
    if cible is not None:
        exclus = {cible["id"]}
        edition = (
            f'<div class="voile" id="modifier-entite" hidden><form class="dialogue" method="post" '
            f'action="/organigramme/{int(cible["id"])}">'
            f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
            "<h2>Modifier l’entité</h2>"
            f"{jeton_cache(ctx)}"
            f'<input type="hidden" name="retour" value="{echapper(retour)}">'
            '<div class="champ"><label for="code-modifier">Code *</label>'
            f'<input id="code-modifier" name="code" maxlength="20" value="{echapper(cible["code"] or "")}" class="majuscules"></div>'
            '<div class="champ"><label for="nom-modifier">Nom *</label>'
            f'<input id="nom-modifier" name="nom" maxlength="120" required value="{echapper(cible["nom"])}"></div>'
            '<div class="champ"><label for="parent-modifier">Rattachement</label>'
            f'<select id="parent-modifier" name="parent_id">'
            f'{_options_parents(postes, cible["parent_id"], exclus)}</select></div>'
            f'<input type="hidden" name="niveau" value="{echapper(cible["niveau"] or "")}">'
            '<p class="pied-dialogue"><a class="bouton secondaire" href="'
            f'{echapper(retour)}">Annuler</a><button type="submit">Enregistrer</button></p>'
            "</form></div>"
        )
    cible_aff = next((poste for poste in postes if poste["id"] == affecter_id), None)
    if cible_aff is None and postes:
        cible_aff = postes[0]
    noms_entites = {poste["id"]: poste["nom"] for poste in postes}
    affectation = _dialogue_affectation(ctx, cible_aff, personnes, noms_entites, retour, choix_personnes)
    return creation + edition + affectation


def _dialogue_affectation(ctx, cible, personnes, noms_entites, retour, choix_personnes):
    if cible is None:
        return ""
    identifiant = int(cible["id"])
    membres = [
        personne for personne in personnes
        if personne["organigramme_id"] == cible["id"] and not personne["administrateur"]
    ]
    liste_membres = "".join(
        "<li>"
        f"<div><strong>{echapper(personne['nom'])}</strong>"
        + (
            f"<span class=\"meta-agent\">{echapper(personne['intitule_poste'])}</span>"
            if personne["intitule_poste"]
            else ""
        )
        + "</div>"
        f'<form method="post" action="/organigramme/{identifiant}/desaffecter">'
        f"{jeton_cache(ctx)}"
        f'<input type="hidden" name="retour" value="{echapper(retour)}">'
        f'<input type="hidden" name="utilisateur_id" value="{int(personne["id"])}">'
        '<button type="submit" class="icone" title="Retirer">×</button></form></li>'
        for personne in membres
    ) or '<li class="vide">Aucun membre.</li>'
    candidats = []
    for personne in personnes:
        if personne["administrateur"] or personne["organigramme_id"] == cible["id"]:
            continue
        ailleurs = noms_entites.get(personne["organigramme_id"]) or "Sans affectation"
        candidats.append(
            f'<li data-agent="{echapper((personne["nom"] + " " + (personne["courriel"] or "")).lower())}">'
            f'<form method="post" action="/organigramme/{identifiant}/affecter">'
            f"{jeton_cache(ctx)}"
            f'<input type="hidden" name="retour" value="{echapper(retour)}">'
            f'<button type="submit" name="utilisateur_id" value="{int(personne["id"])}" '
            f'data-identifiant="{echapper(personne["identifiant"])}">'
            f"<strong>{echapper(personne['nom'])}</strong>"
            f"<span class=\"meta-agent\">{echapper(ailleurs)}</span>"
            "</button></form></li>"
        )
    return (
        f'<div class="voile" id="affecter-agent" hidden><div class="dialogue large">'
        f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
        f"<h2>Affecter des agents à « {echapper(cible['nom'])} »</h2>"
        "<p class=\"chapeau\">Cliquez sur un agent pour l’ajouter, ou sur × pour le retirer. "
        "Le rôle du compte ne change pas.</p>"
        '<div class="colonnes-agents">'
        f"<div><h3>Membres actuels ({len(membres)})</h3><ul class=\"liste-agents\">{liste_membres}</ul></div>"
        "<div><h3>Ajouter un agent</h3>"
        '<label class="visually-hidden" for="filtre-agent">Rechercher</label>'
        '<input id="filtre-agent" data-filtre="candidats-agent" placeholder="Rechercher…">'
        f'<ul id="candidats-agent" class="liste-agents">{"".join(candidats)}</ul>'
        f'<select class="visually-hidden" aria-hidden="true">{choix_personnes}</select>'
        "</div></div></div></div>"
    )


def _entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _options_parents(postes, choisi, exclus):
    options = ['<option value="">— Racine (aucun parent) —</option>']
    for poste in postes:
        if poste["id"] in exclus:
            continue
        sel = " selected" if poste["id"] == choisi else ""
        marque = f'{poste["code"]} · ' if poste["code"] else ""
        options.append(
            f'<option value="{int(poste["id"])}"{sel}>{echapper(marque + poste["nom"])}</option>'
        )
    return "".join(options)


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


def _options_niveaux(choisi):
    options = ['<option value="">Sans rôle</option>']
    for cle in _niveaux_poste():
        sel = " selected" if cle == choisi else ""
        options.append(f'<option value="{cle}"{sel}>{echapper(FONCTIONS[cle])}</option>')
    return "".join(options)


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
    while courant and garde < 40:
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
