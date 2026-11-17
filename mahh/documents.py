"""Arbre des directions, dossiers et fichiers."""

import re
from pathlib import Path
from urllib.parse import quote

from mahh.config import repertoire_fichiers
from mahh.db import base
from mahh.droits import (
    a_un_privilege,
    effectifs,
    est_hierarchie,
    exiger_connexion,
    libelle_droits,
)
from mahh.presentation import jeton_cache, page
from mahh.reponse import Html, Interdit, Octets, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import echapper
from mahh.validation import nom_noeud

EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".csv",
    ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods",
}
TAILLE_MAX = 15 * 1024 * 1024
_STOCKAGE = re.compile(r"[a-f0-9]{32}\.[a-z0-9]{1,8}")


def _noeud(conn, noeud_id):
    return conn.execute("SELECT * FROM noeud WHERE id = ?", (noeud_id,)).fetchone()


def _exiger_noeud(conn, noeud_id):
    noeud = _noeud(conn, int(noeud_id))
    if noeud is None:
        raise Interdit("Cet élément n’existe pas.")
    return noeud


def _fil(conn, noeud):
    chaine = []
    courant = noeud
    garde = 0
    while courant is not None and garde < 30:
        chaine.append(courant)
        if courant["parent_id"] is None:
            break
        courant = _noeud(conn, courant["parent_id"])
        garde += 1
    chaine.reverse()
    return chaine


def _enfants(conn, parent_id):
    return conn.execute(
        """
        SELECT * FROM noeud WHERE parent_id = ?
        ORDER BY CASE genre
            WHEN 'domaine' THEN 0 WHEN 'structure' THEN 1
            WHEN 'dossier' THEN 2 ELSE 3 END,
            ordre, nom
        """,
        (parent_id,),
    ).fetchall()


def _visible(conn, utilisateur, noeud):
    if utilisateur is None:
        return False
    if est_hierarchie(utilisateur):
        return True
    if a_un_privilege(effectifs(conn, utilisateur, noeud["id"])):
        return True
    if noeud["genre"] not in ("domaine", "structure"):
        return False
    descendants = conn.execute(
        """
        WITH RECURSIVE sous(id) AS (
            SELECT id FROM noeud WHERE parent_id = ?
            UNION ALL
            SELECT n.id FROM noeud n JOIN sous s ON n.parent_id = s.id
        )
        SELECT id FROM sous
        """,
        (noeud["id"],),
    ).fetchall()
    return any(
        a_un_privilege(effectifs(conn, utilisateur, ligne["id"])) for ligne in descendants
    )


def _profondeur(conn, noeud_id):
    profondeur = 0
    courant = noeud_id
    while courant is not None and profondeur < 30:
        ligne = conn.execute("SELECT parent_id FROM noeud WHERE id = ?", (courant,)).fetchone()
        if ligne is None:
            break
        courant = ligne["parent_id"]
        profondeur += 1
    return profondeur


def _lien_fil(conn, utilisateur, noeud):
    if not _visible(conn, utilisateur, noeud):
        return echapper(noeud["nom"])
    return f'<a href="/noeud/{int(noeud["id"])}">{echapper(noeud["nom"])}</a>'


def page_directions(ctx, erreur=None):
    exiger_connexion(ctx)
    from mahh.organigramme import rendu_attributions, rendu_organigramme

    with base() as conn:
        domaines = conn.execute(
            """
            SELECT * FROM noeud WHERE genre = 'domaine' ORDER BY ordre, nom
            """
        ).fetchall()
        blocs = []
        for domaine in domaines:
            structures = _enfants(conn, domaine["id"])
            cartes = []
            for structure in structures:
                if not _visible(conn, ctx.utilisateur, structure):
                    continue
                sous_titre = (
                    f'<p class="intitule">{echapper(structure["intitule"])}</p>'
                    if structure["intitule"]
                    else ""
                )
                cartes.append(
                    "<li>"
                    f'<a href="/noeud/{int(structure["id"])}" data-nom="{echapper(structure["nom"])}">'
                    f'{echapper(structure["nom"])}</a>'
                    f"{sous_titre}"
                    "</li>"
                )
            if not cartes:
                continue
            blocs.append(
                f'<section class="domaine" data-domaine="{echapper(domaine["nom"])}">'
                f"<h2>{echapper(domaine['nom'])}</h2>"
                f'<ul class="structures">{"".join(cartes)}</ul>'
                "</section>"
            )
        if not blocs and not est_hierarchie(ctx.utilisateur):
            raise Interdit("Vous n’avez pas de privilège sur les directions.")
        schema = rendu_organigramme(ctx, conn)
        attributions = rendu_attributions(ctx, conn)
    corps = (
        "<h1>Directions</h1>"
        '<p class="chapeau">Les directions du ministère, leur place dans l’organigramme, '
        "et les attributions de chacune.</p>"
        + schema
        + attributions
        + "<h2>Dossiers</h2>"
        + "".join(blocs)
    )
    return page("Directions", corps, ctx, actif="directions", erreur=erreur)


def page_noeud(ctx, noeud_id, erreur=None):
    exiger_connexion(ctx)
    with base() as conn:
        noeud = _noeud(conn, int(noeud_id))
        if noeud is None:
            return page_message_absent(ctx)
        if not _visible(conn, ctx.utilisateur, noeud):
            raise Interdit("Vous n’avez pas de privilège sur cet élément.")
        droits = effectifs(conn, ctx.utilisateur, noeud["id"])
        fil = _fil(conn, noeud)
        enfants = [e for e in _enfants(conn, noeud["id"]) if _visible(conn, ctx.utilisateur, e)]
        libelles = conn.execute(
            "SELECT texte FROM libelle WHERE noeud_id = ? ORDER BY ordre",
            (noeud["id"],),
        ).fetchall()
        corps = _corps_noeud(ctx, conn, noeud, droits, fil, enfants, libelles)
    return page(noeud["nom"], corps, ctx, actif="directions", erreur=erreur)


def page_message_absent(ctx):
    return page(
        "Introuvable",
        "<h1>Introuvable</h1><p>Cet élément n’est pas dans l’arborescence.</p>",
        ctx,
        actif="directions",
        statut=404,
    )


def _corps_noeud(ctx, conn, noeud, droits, fil, enfants, libelles):
    fil_html = " <span class=\"sep\">/</span> ".join(
        _lien_fil(conn, ctx.utilisateur, element) for element in fil
    )
    titre = echapper(noeud["nom"])
    if noeud["intitule"]:
        titre += f' <span class="intitule-titre">{echapper(noeud["intitule"])}</span>'
    lecture = f'<p class="lecture">{echapper(noeud["lecture"])}</p>' if noeud["lecture"] else ""
    privileges = " ".join(action for action, tenu in droits.items() if tenu)
    admin = 1 if ctx.utilisateur["administrateur"] else 0
    entete = (
        f'<p class="fil">{fil_html}</p>'
        f"<h1>{titre}</h1>"
        f"{lecture}"
        f'<p class="privileges" data-privileges="{echapper(privileges)}" data-admin="{admin}">'
        f"{echapper(libelle_droits(droits, ctx.utilisateur['administrateur']))}</p>"
    )
    from mahh.organigramme import rendu_attributions, rendu_organigramme

    fonctions = ""
    if noeud["genre"] in ("domaine", "structure"):
        fonctions = rendu_organigramme(
            ctx, conn, noeud_id=noeud["id"], edition=False
        ) + rendu_attributions(ctx, conn, noeud_id=noeud["id"])
    from mahh.indicateurs import LIBELLES, rendu as rendu_indicateurs

    if noeud["nom"] == "ANASP":
        restants = [
            ligne for ligne in libelles
            if ligne["texte"] not in ("Organigramme", "Attribution") and ligne["texte"] not in LIBELLES
        ]
        indicateurs = rendu_indicateurs(ctx, conn, f"/noeud/{int(noeud['id'])}")
    elif noeud["nom"] == "DGA":
        restants = [
            ligne for ligne in libelles if ligne["texte"] not in ("Organigramme", "Attribution")
        ]
        indicateurs = rendu_indicateurs(ctx, conn, f"/noeud/{int(noeud['id'])}")
    else:
        restants = [
            ligne for ligne in libelles if ligne["texte"] not in ("Organigramme", "Attribution")
        ]
        indicateurs = ""
    catalogue = fonctions + indicateurs
    if restants:
        cartes = "".join(
            f'<article class="carte"><h3>{echapper(ligne["texte"])}</h3></article>'
            for ligne in restants
        )
        catalogue += (
            '<section class="indicateurs-direction"><h2>Indicateurs</h2>'
            f'<div class="cartes">{cartes}</div></section>'
        )
    if noeud["nom"] == "BSD" and noeud["genre"] == "structure":
        catalogue += (
            '<p><a href="/bsd">Ouvrir le tableau de bord des projets.</a> '
            "L’accès dépend du privilège accordé au groupe, ou du rôle d’administrateur.</p>"
        )
    lignes = []
    for enfant in enfants:
        if enfant["genre"] == "fichier":
            consultation = (
                f' <a href="/fichier/{int(enfant["id"])}">Télécharger</a>'
                if droits["consulter"] or ctx.utilisateur["administrateur"]
                else ""
            )
            # Le téléchargement exige consulter. L'admin a consulter via effectifs.
            if not effectifs(conn, ctx.utilisateur, enfant["id"])["consulter"]:
                consultation = ""
            detail = consultation
            marque = "fichier"
        else:
            detail = ""
            marque = enfant["genre"]
        actions = ""
        droits_enfant = effectifs(conn, ctx.utilisateur, enfant["id"])
        if enfant["systeme"]:
            actions = ""
        else:
            if droits_enfant["modifier"]:
                actions += (
                    f'<form method="post" action="/noeud/{int(enfant["id"])}/renommer" class="ligne-form">'
                    f"{jeton_cache(ctx)}"
                    f'<label class="visually-hidden" for="nom-{int(enfant["id"])}">Nouveau nom</label>'
                    f'<input id="nom-{int(enfant["id"])}" name="nom" value="{echapper(enfant["nom"])}" maxlength="120" required>'
                    '<button type="submit" class="secondaire">Renommer</button></form>'
                )
            if droits_enfant["supprimer"]:
                actions += (
                    f'<form method="post" action="/noeud/{int(enfant["id"])}/supprimer" class="ligne-form">'
                    f"{jeton_cache(ctx)}"
                    '<button type="submit" class="danger">Supprimer</button></form>'
                )
        nom_affiche = (
            f'<a href="/noeud/{int(enfant["id"])}" data-dossier="{echapper(enfant["nom"])}">'
            f'{echapper(enfant["nom"])}</a>'
            if enfant["genre"] != "fichier"
            else f'<span data-fichier="{echapper(enfant["nom"])}">{echapper(enfant["nom"])}</span>'
        )
        lignes.append(
            "<li>"
            f'<span class="genre">{echapper(marque)}</span> {nom_affiche}{detail}'
            f'<span class="actions">{actions}</span>'
            "</li>"
        )
    liste = (
        '<ul class="contenu">' + "".join(lignes) + "</ul>"
        if lignes
        else '<p class="vide">Aucun dossier ni fichier visible ici.</p>'
    )
    formulaires = ""
    if noeud["genre"] != "fichier" and (droits["creer"] or ctx.utilisateur["administrateur"]):
        formulaires = (
            '<section class="outils"><h2>Ajouter</h2>'
            f'<form method="post" action="/noeud/{int(noeud["id"])}/dossier" class="formulaire">'
            f"{jeton_cache(ctx)}"
            '<label for="nom-dossier">Nom du dossier</label>'
            '<input id="nom-dossier" name="nom" maxlength="120" required>'
            '<button type="submit">Créer le dossier</button></form>'
            f'<form method="post" action="/noeud/{int(noeud["id"])}/fichier" class="formulaire" enctype="multipart/form-data">'
            f"{jeton_cache(ctx)}"
            '<label for="fichier">Fichier</label>'
            '<input id="fichier" name="fichier" type="file" required>'
            "<p class=\"aide\">PDF, image, texte, CSV ou document bureautique. 15&nbsp;Mo au plus.</p>"
            '<button type="submit">Déposer le fichier</button></form></section>'
        )
    return entete + catalogue + "<h2>Dossiers et fichiers</h2>" + liste + formulaires


def action_dossier(ctx, noeud_id):
    exiger_connexion(ctx)
    try:
        nom = nom_noeud(ctx.formulaire.get("nom"))
    except ValeurRefusee as exc:
        return page_noeud(ctx, noeud_id, erreur=exc.message)
    with base() as conn:
        parent = _exiger_parent_creation(conn, ctx, noeud_id)
        if _profondeur(conn, parent["id"]) >= 12:
            return page_noeud(ctx, noeud_id, erreur="Ce dossier est déjà trop profond.")
        if conn.execute(
            "SELECT id FROM noeud WHERE parent_id = ? AND nom = ?",
            (parent["id"], nom),
        ).fetchone():
            return page_noeud(ctx, noeud_id, erreur="Un élément porte déjà ce nom ici.")
        quand = maintenant()
        curseur = conn.execute(
            """
            INSERT INTO noeud (
                parent_id, genre, nom, systeme, ordre, cree_par, cree_le, modifie_le
            ) VALUES (?, 'dossier', ?, 0, ?, ?, ?, ?)
            """,
            (parent["id"], nom, _prochain_ordre(conn, parent["id"]), ctx.utilisateur["id"], quand, quand),
        )
        nouveau = curseur.lastrowid
    return Redirection(f"/noeud/{nouveau}?message=dossier-cree")


def action_fichier(ctx, noeud_id):
    exiger_connexion(ctx)
    if ctx.fichier is None:
        return page_noeud(ctx, noeud_id, erreur="Choisissez un fichier.")
    nom_original, contenu = ctx.fichier
    try:
        nom = _nom_fichier(nom_original)
    except ValeurRefusee as exc:
        return page_noeud(ctx, noeud_id, erreur=exc.message)
    if not contenu:
        return page_noeud(ctx, noeud_id, erreur="Le fichier est vide.")
    if len(contenu) > TAILLE_MAX:
        return page_noeud(ctx, noeud_id, erreur="Le fichier dépasse 15 Mo.")
    suffixe = Path(nom).suffix.lower()
    from secrets import token_hex

    stockage = token_hex(16) + suffixe
    with base() as conn:
        parent = _exiger_parent_creation(conn, ctx, noeud_id)
        if conn.execute(
            "SELECT id FROM noeud WHERE parent_id = ? AND nom = ?",
            (parent["id"], nom),
        ).fetchone():
            return page_noeud(ctx, noeud_id, erreur="Un élément porte déjà ce nom ici.")
        quand = maintenant()
        conn.execute(
            """
            INSERT INTO noeud (
                parent_id, genre, nom, systeme, ordre, nom_stockage, taille,
                cree_par, cree_le, modifie_le
            ) VALUES (?, 'fichier', ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent["id"], nom, _prochain_ordre(conn, parent["id"]), stockage,
                len(contenu), ctx.utilisateur["id"], quand, quand,
            ),
        )
    chemin = repertoire_fichiers() / stockage
    chemin.write_bytes(contenu)
    return Redirection(f"/noeud/{int(noeud_id)}?message=fichier-ajoute")


def action_renommer(ctx, noeud_id):
    exiger_connexion(ctx)
    try:
        nom = nom_noeud(ctx.formulaire.get("nom"))
    except ValeurRefusee as exc:
        return _retour_parent(ctx, noeud_id, exc.message)
    with base() as conn:
        noeud = _exiger_noeud(conn, noeud_id)
        _exiger_action(conn, ctx, noeud, "modifier")
        if noeud["systeme"]:
            raise Interdit("Les domaines et les structures de la note ne se renomment pas dans ce socle.")
        conflit = conn.execute(
            "SELECT id FROM noeud WHERE parent_id = ? AND nom = ? AND id != ?",
            (noeud["parent_id"], nom, noeud["id"]),
        ).fetchone()
        if conflit:
            return _retour_parent(ctx, noeud_id, "Un élément porte déjà ce nom ici.")
        conn.execute(
            "UPDATE noeud SET nom = ?, modifie_le = ? WHERE id = ?",
            (nom, maintenant(), noeud["id"]),
        )
        parent = noeud["parent_id"]
    return Redirection(f"/noeud/{int(parent)}?message=renomme")


def action_supprimer(ctx, noeud_id):
    exiger_connexion(ctx)
    with base() as conn:
        noeud = _exiger_noeud(conn, noeud_id)
        _exiger_action(conn, ctx, noeud, "supprimer")
        if noeud["systeme"]:
            raise Interdit("Les domaines et les structures de la note ne se suppriment pas dans ce socle.")
        stockages = _stockages_sous(conn, noeud["id"])
        parent = noeud["parent_id"]
        conn.execute("DELETE FROM noeud WHERE id = ?", (noeud["id"],))
    for nom in stockages:
        chemin = _chemin_stockage(nom)
        if chemin is not None and chemin.exists():
            chemin.unlink()
    return Redirection(f"/noeud/{int(parent)}?message=supprime")


def telecharger(ctx, noeud_id):
    exiger_connexion(ctx)
    with base() as conn:
        noeud = _noeud(conn, int(noeud_id))
        if noeud is None or noeud["genre"] != "fichier":
            return page_message_absent(ctx)
        if not effectifs(conn, ctx.utilisateur, noeud["id"])["consulter"]:
            raise Interdit("Le téléchargement demande le privilège consulter.")
        chemin = _chemin_stockage(noeud["nom_stockage"])
        if chemin is None or not chemin.exists():
            return page_message_absent(ctx)
        contenu = chemin.read_bytes()
        nom = noeud["nom"]
    disposition = "attachment; filename*=UTF-8''" + quote(nom)
    return Octets(contenu, "application/octet-stream", disposition=disposition)


def _exiger_parent_creation(conn, ctx, noeud_id):
    parent = _exiger_noeud(conn, noeud_id)
    if parent["genre"] == "fichier":
        raise Interdit("On ne dépose rien dans un fichier.")
    droits = effectifs(conn, ctx.utilisateur, parent["id"])
    if not droits["creer"]:
        raise Interdit("Créer un dossier ou un fichier demande le privilège créer.")
    return parent


def _exiger_action(conn, ctx, noeud, action):
    if not effectifs(conn, ctx.utilisateur, noeud["id"])[action]:
        raise Interdit("Ce privilège ne vous est pas accordé.")


def _prochain_ordre(conn, parent_id):
    ligne = conn.execute(
        "SELECT COALESCE(MAX(ordre), 0) + 1 AS n FROM noeud WHERE parent_id = ?",
        (parent_id,),
    ).fetchone()
    return ligne["n"]


def _nom_fichier(nom_original):
    base = Path(str(nom_original)).name.replace("\\", "").replace("/", "").strip()
    if not base or base in {".", ".."}:
        raise ValeurRefusee("Le fichier n’a pas de nom.")
    if any(ord(caractere) < 32 for caractere in base):
        raise ValeurRefusee("Le nom du fichier contient un caractère refusé.")
    suffixe = Path(base).suffix.lower()
    if suffixe not in EXTENSIONS:
        raise ValeurRefusee(
            "Ce type de fichier n’est pas accepté. Déposez un PDF, une image, un texte, un CSV ou un document bureautique."
        )
    if len(base) > 120:
        base = base[-120:]
    return base


def _stockages_sous(conn, noeud_id):
    lignes = conn.execute(
        """
        WITH RECURSIVE sous(id) AS (
            SELECT id FROM noeud WHERE id = ?
            UNION ALL
            SELECT n.id FROM noeud n JOIN sous s ON n.parent_id = s.id
        )
        SELECT nom_stockage FROM noeud
        WHERE genre = 'fichier' AND nom_stockage IS NOT NULL AND id IN (SELECT id FROM sous)
        """,
        (noeud_id,),
    ).fetchall()
    return [ligne["nom_stockage"] for ligne in lignes]


def _chemin_stockage(nom):
    if not nom or _STOCKAGE.fullmatch(nom) is None:
        return None
    base = repertoire_fichiers().resolve()
    cible = (base / nom).resolve()
    if not cible.is_relative_to(base):
        return None
    return cible


def _retour_parent(ctx, noeud_id, message):
    with base() as conn:
        noeud = _noeud(conn, int(noeud_id))
        if noeud and noeud["parent_id"]:
            return page_noeud(ctx, noeud["parent_id"], erreur=message)
    return page_noeud(ctx, noeud_id, erreur=message)
