"""Organigramme des directions et attributions.

Les entités se créent depuis la racine, avec un code, un rôle et un rattachement.
Le ministre, le secrétaire général, le chef de cabinet ou un administrateur
tiennent cet organigramme. L’affectation donne à la personne le rôle de l’entité.
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
    from mahh.droits import exiger_connexion

    exiger_connexion(ctx)
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
        arbre = '<p class="vide">Aucune entité dans cette branche. Créez la première depuis la racine.</p>'
    nombre = len(postes) if noeud_id is None else _compter_branche(racines, enfants)
    libelle = "1 entité" if nombre == 1 else f"{nombre} entités"
    outils = _dialogues(ctx, conn, postes, membres) if tenir else ""
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
        '<section class="carte-arbre">'
        f"<h2>Arborescence ({libelle})</h2>"
        f'<ul class="arbre">{arbre}</ul>'
        "</section>"
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

    exiger_organigramme(ctx)
    try:
        code, nom, intitule, parent_id, niveau = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        try:
            _verifier_parent(conn, parent_id, None)
            _verifier_code(conn, code, None)
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
            INSERT INTO organigramme (
                parent_id, code, nom, intitule, ordre, niveau, cree_le, modifie_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (parent_id, code, nom, intitule, ordre, niveau, quand, quand),
        )
    return _retour(ctx, "poste-cree")


def action_modifier_poste(ctx, poste_id):
    from mahh.documents import page_directions

    exiger_organigramme(ctx)
    try:
        code, nom, intitule, parent_id, niveau = _saisie_poste(ctx.formulaire)
    except ValeurRefusee as exc:
        return page_directions(ctx, erreur=exc.message)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        try:
            _verifier_parent(conn, parent_id, poste["id"])
            _verifier_code(conn, code, poste["id"])
        except ValeurRefusee as exc:
            return page_directions(ctx, erreur=exc.message)
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
    from mahh.documents import page_directions

    exiger_organigramme(ctx)
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        if poste["noeud_id"]:
            return page_directions(
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
            return page_directions(
                ctx,
                erreur="Cette entité a encore des rattachements ou des personnes. Retirez-les d’abord.",
            )
        conn.execute("DELETE FROM organigramme WHERE id = ?", (poste["id"],))
    return _retour(ctx, "poste-retire")


def action_affecter_liste(ctx):
    return action_affecter(ctx, ctx.formulaire.get("poste_id"))


def action_affecter(ctx, poste_id):
    from mahh.documents import page_directions

    exiger_organigramme(ctx)
    try:
        utilisateur_id = int((ctx.formulaire.get("utilisateur_id") or "").strip())
    except ValueError:
        return page_directions(ctx, erreur="Choisissez une personne.")
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        if (poste["niveau"] or "") not in _niveaux_poste():
            return page_directions(ctx, erreur="Choisissez d’abord un rôle pour cette entité.")
        personne = conn.execute(
            "SELECT id FROM utilisateur WHERE id = ? AND actif = 1",
            (utilisateur_id,),
        ).fetchone()
        if personne is None:
            return page_directions(ctx, erreur="Cette personne n’est pas dans l’annuaire.")
        structure_id = None
        if poste["niveau"] not in _ROLES_MINISTERE:
            structure_id = _structure_du_poste(conn, poste)
            if structure_id is None:
                return page_directions(
                    ctx,
                    erreur="Rattachez cette entité à une direction avant d’y affecter une personne.",
                )
        conn.execute(
            """
            UPDATE utilisateur
            SET fonction = ?, roles = ?, structure_id = ?, organigramme_id = ?
            WHERE id = ?
            """,
            (poste["niveau"], poste["niveau"], structure_id, poste["id"], personne["id"]),
        )
    return _retour(ctx, "personne-affectee")


def action_desaffecter(ctx, poste_id):
    from mahh.documents import page_directions

    exiger_organigramme(ctx)
    try:
        utilisateur_id = int((ctx.formulaire.get("utilisateur_id") or "").strip())
    except ValueError:
        return page_directions(ctx, erreur="Choisissez une personne.")
    with base() as conn:
        poste = _poste(conn, poste_id)
        if poste is None:
            return page_directions(ctx, erreur="Cette case n’est pas dans l’organigramme.")
        conn.execute(
            """
            UPDATE utilisateur
            SET fonction = '', roles = '', structure_id = NULL, organigramme_id = NULL
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
    return groupes


def _racines(postes, noeud_id):
    if noeud_id is None:
        return [poste for poste in postes if poste["parent_id"] is None]
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
        f'<span class="compteur" title="{len(gens)}">{len(gens)}</span>'
    )
    actions = _actions_entite(ctx, poste) if tenir else ""
    etiquette = (
        f'<span class="etiquette-entite" {attributs}>{code}'
        f'<span class="nom-entite">{nom}</span>{role_html}{compteur}{affectes}</span>'
    )
    if suite:
        dessous = "".join(
            _ligne_entite(ctx, enfant, enfants, membres, tenir, profondeur + 1)
            for enfant in suite
        )
        ouvert = " open" if profondeur < 2 else ""
        return (
            f"<li><details{ouvert}><summary>{etiquette}</summary>"
            f"{actions}<ul class=\"arbre\">{dessous}</ul></details></li>"
        )
    return f'<li class="feuille"><div class="ligne-org">{etiquette}{actions}</div></li>'


def _actions_entite(ctx, poste):
    identifiant = int(poste["id"])
    chemin = ctx.chemin if ctx.chemin in ("/organigramme", "/directions") else "/organigramme"
    retrait = ""
    if not poste["noeud_id"]:
        retrait = f'<a class="danger-lien" href="{chemin}?retirer={identifiant}#retirer-entite">Retirer</a>'
    return (
        '<span class="actions-entite">'
        f'<a href="{chemin}?parent={identifiant}#nouvelle-entite">Sous-entité</a>'
        f'<a href="/annuaire?entite={identifiant}#nouvel-agent">Ajouter un agent</a>'
        f'<a href="{chemin}#affecter-compte">Compte existant</a>'
        f'<a href="{chemin}?modifier={identifiant}#modifier-entite">Modifier</a>'
        f"{retrait}</span>"
    )


def _dialogues(ctx, conn, postes, membres):
    requete = ctx.requete if hasattr(ctx, "requete") else {}
    parent_voulu = _entier(requete.get("parent"))
    modifier_id = _entier(requete.get("modifier"))
    retirer_id = _entier(requete.get("retirer"))
    cible = next((poste for poste in postes if poste["id"] == modifier_id), None)
    personnes = conn.execute(
        """
        SELECT id, identifiant, nom, organigramme_id
        FROM utilisateur WHERE actif = 1
        ORDER BY nom, identifiant
        """
    ).fetchall()
    choix_personnes = "".join(
        f'<option value="{int(personne["id"])}" data-identifiant="{echapper(personne["identifiant"])}">'
        f'{echapper(personne["nom"])}</option>'
        for personne in personnes
    )
    retour = ctx.chemin if ctx.chemin in ("/organigramme", "/directions") else "/organigramme"
    creation = (
        f'<div class="voile" id="nouvelle-entite"><form class="dialogue" method="post" action="/organigramme">'
        f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
        "<h2>Nouvelle entité</h2>"
        '<p class="chapeau">Direction, département ou service. Le code doit être unique.</p>'
        f"{jeton_cache(ctx)}"
        f'<input type="hidden" name="retour" value="{echapper(retour)}">'
        '<div class="deux-champs">'
        '<div class="champ"><label for="code-poste">Code *</label>'
        '<input id="code-poste" name="code" maxlength="20" required autocomplete="off"></div>'
        '<div class="champ"><label for="nom-poste">Nom *</label>'
        '<input id="nom-poste" name="nom" maxlength="120" required></div>'
        "</div>"
        '<div class="champ"><label for="parent-poste">Rattachement</label>'
        f'<select id="parent-poste" name="parent_id">{_options_parents(postes, parent_voulu, set())}</select></div>'
        '<div class="champ"><label for="niveau-poste">Rôle de l’entité</label>'
        f'<select id="niveau-poste" name="niveau">{_options_niveaux("")}</select></div>'
        '<p class="aide">Sans rattachement, l’entité est à la racine. '
        "Le rôle de l’entité ouvre les écrans des personnes qui y sont affectées.</p>"
        '<p class="pied-dialogue"><a class="bouton secondaire" href="'
        f'{echapper(retour)}">Annuler</a><button type="submit">Créer</button></p>'
        "</form></div>"
    )
    if cible is None and postes:
        cible = postes[0]
    edition = ""
    if cible is not None:
        exclus = _descendants(cible["id"], postes) | {cible["id"]}
        edition = (
            f'<div class="voile" id="modifier-entite"><form class="dialogue" method="post" '
            f'action="/organigramme/{int(cible["id"])}">'
            f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
            "<h2>Modifier l’entité</h2>"
            f"{jeton_cache(ctx)}"
            f'<input type="hidden" name="retour" value="{echapper(retour)}">'
            '<div class="deux-champs">'
            '<div class="champ"><label for="code-modifier">Code *</label>'
            f'<input id="code-modifier" name="code" maxlength="20" value="{echapper(cible["code"] or "")}"></div>'
            '<div class="champ"><label for="nom-modifier">Nom *</label>'
            f'<input id="nom-modifier" name="nom" maxlength="120" required value="{echapper(cible["nom"])}"></div>'
            "</div>"
            '<div class="champ"><label for="parent-modifier">Rattachement</label>'
            f'<select id="parent-modifier" name="parent_id">'
            f'{_options_parents(postes, cible["parent_id"], exclus)}</select></div>'
            '<div class="champ"><label for="niveau-modifier">Rôle de l’entité</label>'
            f'<select id="niveau-modifier" name="niveau">{_options_niveaux(cible["niveau"] or "")}</select></div>'
            '<p class="pied-dialogue"><a class="bouton secondaire" href="'
            f'{echapper(retour)}">Annuler</a><button type="submit">Enregistrer</button></p>'
            "</form></div>"
        )
    choix_entites = "".join(
        f'<option value="{int(poste["id"])}">{echapper((poste["code"] + " · ") if poste["code"] else "")}'
        f'{echapper(poste["nom"])}</option>'
        for poste in postes
    )
    affectation = (
        '<div class="voile" id="affecter-compte"><form class="dialogue" method="post" action="/organigramme/affecter">'
        f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
        "<h2>Affecter un compte</h2>"
        '<p class="chapeau">La personne reçoit le rôle de l’entité.</p>'
        f"{jeton_cache(ctx)}"
        f'<input type="hidden" name="retour" value="{echapper(retour)}">'
        '<label for="personne-existante">Personne</label>'
        f'<select id="personne-existante" name="utilisateur_id">{choix_personnes}</select>'
        '<label for="entite-affectation">Entité</label>'
        f'<select id="entite-affectation" name="poste_id">{choix_entites}</select>'
        '<p class="pied-dialogue"><a class="bouton secondaire" href="'
        f'{echapper(retour)}">Annuler</a><button type="submit">Affecter</button></p>'
        "</form></div>"
    )
    retire = next((poste for poste in postes if poste["id"] == retirer_id and not poste["noeud_id"]), None)
    confirmation = ""
    if retire is not None:
        confirmation = (
            f'<div class="voile" id="retirer-entite"><form class="dialogue" method="post" '
            f'action="/organigramme/{int(retire["id"])}/retirer">'
            f'<a class="fermer" href="{echapper(retour)}" aria-label="Fermer">×</a>'
            f'<h2>Retirer {echapper(retire["nom"])}</h2>'
            "<p>L’entité est retirée si elle n’a plus de sous-entité ni de personne.</p>"
            f"{jeton_cache(ctx)}"
            f'<input type="hidden" name="retour" value="{echapper(retour)}">'
            '<p class="pied-dialogue"><a class="bouton secondaire" href="'
            f'{echapper(retour)}">Annuler</a>'
            '<button type="submit" class="danger">Retirer</button></p>'
            "</form></div>"
        )
    return creation + edition + affectation + confirmation


def _entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _options_parents(postes, choisi, exclus):
    options = ['<option value="">— Racine —</option>']
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
