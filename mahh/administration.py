"""Comptes, groupes et privilèges. Réservé à l'administrateur, sauf le changement de mot de passe."""

from mahh.db import base
from mahh.droits import FONCTION_COMMUNICATION, FONCTIONS, exiger_admin, exiger_connexion
from mahh.presentation import jeton_cache, page
from mahh.reponse import Redirection, ValeurRefusee
from mahh.securite import (
    cookie_jeton,
    cookie_session_vide,
    fermer_sessions,
    hasher,
    maintenant,
    nouveau_jeton,
    verifier_ou_factice,
)
from mahh.texte import echapper
from mahh.validation import identifiant as valider_identifiant
from mahh.validation import ligne, mot_de_passe


def page_groupes(ctx, erreur=None):
    exiger_admin(ctx)
    with base() as conn:
        groupes = conn.execute("SELECT * FROM groupe ORDER BY nom").fetchall()
        lignes = []
        for groupe in groupes:
            nombre = conn.execute(
                "SELECT COUNT(*) AS n FROM appartenance WHERE groupe_id = ?",
                (groupe["id"],),
            ).fetchone()["n"]
            bsd = "oui" if groupe["consulter_bsd"] else "non"
            lignes.append(
                "<tr>"
                f'<td><a href="/groupes/{int(groupe["id"])}">{echapper(groupe["nom"])}</a></td>'
                f"<td>{int(nombre)}</td><td>{bsd}</td></tr>"
            )
        tableau = (
            "<table><caption>Groupes</caption><thead><tr>"
            "<th>Groupe</th><th>Membres</th><th>Tableau de bord</th>"
            "</tr></thead><tbody>"
            + ("".join(lignes) or '<tr><td colspan="3">Aucun groupe.</td></tr>')
            + "</tbody></table>"
        )
    corps = (
        "<h1>Groupes</h1>"
        "<p class=\"chapeau\">Un groupe reçoit des privilèges. Les personnes du groupe les exercent. "
        "La lecture retenue du mot « GRUB » est celle-ci : CRUD et groupes.</p>"
        + tableau
        + '<form method="post" action="/groupes" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="nom-groupe">Nom du groupe</label>'
        + '<input id="nom-groupe" name="nom" maxlength="80" required>'
        + '<button type="submit">Créer le groupe</button></form>'
    )
    return page("Groupes", corps, ctx, actif="groupes", erreur=erreur)


def action_groupe(ctx):
    exiger_admin(ctx)
    try:
        nom = ligne(ctx.formulaire.get("nom"), 2, 80, "Nom du groupe")
    except ValeurRefusee as exc:
        return page_groupes(ctx, erreur=exc.message)
    with base() as conn:
        if conn.execute(
            "SELECT id FROM groupe WHERE lower(nom) = lower(?)", (nom,)
        ).fetchone():
            return page_groupes(ctx, erreur="Un groupe porte déjà ce nom.")
        curseur = conn.execute(
            "INSERT INTO groupe (nom, consulter_bsd, cree_le) VALUES (?, 0, ?)",
            (nom, maintenant()),
        )
        nouveau = curseur.lastrowid
    return Redirection(f"/groupes/{nouveau}?message=groupe-cree")


def page_groupe(ctx, groupe_id, erreur=None):
    exiger_admin(ctx)
    with base() as conn:
        groupe = conn.execute("SELECT * FROM groupe WHERE id = ?", (int(groupe_id),)).fetchone()
        if groupe is None:
            return page("Introuvable", "<h1>Introuvable</h1><p>Ce groupe n’existe pas.</p>", ctx, statut=404)
        membres = conn.execute(
            """
            SELECT u.* FROM utilisateur u
            JOIN appartenance a ON a.utilisateur_id = u.id
            WHERE a.groupe_id = ? ORDER BY u.nom
            """,
            (groupe["id"],),
        ).fetchall()
        deja = {m["id"] for m in membres}
        candidats = conn.execute(
            "SELECT * FROM utilisateur WHERE actif = 1 ORDER BY nom"
        ).fetchall()
        droits = conn.execute(
            """
            SELECT d.*, n.nom AS noeud_nom, n.genre
            FROM droit d JOIN noeud n ON n.id = d.noeud_id
            WHERE d.groupe_id = ?
            ORDER BY n.nom
            """,
            (groupe["id"],),
        ).fetchall()
        noeuds = _noeuds_pour_droit(conn)
        corps = _corps_groupe(ctx, groupe, membres, deja, candidats, droits, noeuds)
    return page(groupe["nom"], corps, ctx, actif="groupes", erreur=erreur)


def _corps_groupe(ctx, groupe, membres, deja, candidats, droits, noeuds):
    liste_membres = []
    for membre in membres:
        liste_membres.append(
            "<li>"
            f'<span data-membre="{echapper(membre["identifiant"])}">{echapper(membre["nom"])} '
            f'({echapper(membre["identifiant"])})</span>'
            f'<form method="post" action="/groupes/{int(groupe["id"])}/retirer">'
            f'{jeton_cache(ctx)}<input type="hidden" name="utilisateur_id" value="{int(membre["id"])}">'
            '<button type="submit" class="secondaire">Retirer</button></form></li>'
        )
    options = ['<option value="">Choisir</option>']
    for candidat in candidats:
        if candidat["id"] in deja:
            continue
        options.append(
            f'<option value="{int(candidat["id"])}" data-identifiant="{echapper(candidat["identifiant"])}">'
            f'{echapper(candidat["nom"])} ({echapper(candidat["identifiant"])})</option>'
        )
    options_noeuds = ['<option value="">Choisir un dossier ou une structure</option>']
    for noeud, profondeur in noeuds:
        prefixe = "· " * profondeur
        options_noeuds.append(
            f'<option value="{int(noeud["id"])}" data-noeud-nom="{echapper(noeud["nom"])}">'
            f'{echapper(prefixe + noeud["nom"])}</option>'
        )
    lignes_droits = []
    for droit in droits:
        tenus = [
            nom
            for nom, colonne in (
                ("créer", "creer"),
                ("consulter", "consulter"),
                ("modifier", "modifier"),
                ("supprimer", "supprimer"),
            )
            if droit[colonne]
        ]
        lignes_droits.append(
            f'<tr data-noeud="{int(droit["noeud_id"])}" data-noeud-nom="{echapper(droit["noeud_nom"])}">'
            f'<td>{echapper(droit["noeud_nom"])}</td>'
            f'<td data-droits="{" ".join(tenus)}">{echapper(", ".join(tenus) if tenus else "aucun")}</td></tr>'
        )
    coche = "checked" if groupe["consulter_bsd"] else ""
    return (
        f'<p class="fil"><a href="/groupes">Groupes</a></p>'
        f'<h1>{echapper(groupe["nom"])}</h1>'
        "<h2>Personnes</h2>"
        + (f'<ul class="membres">{"".join(liste_membres)}</ul>' if liste_membres else "<p>Aucune personne dans ce groupe.</p>")
        + f'<form method="post" action="/groupes/{int(groupe["id"])}/membre" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="utilisateur">Ajouter une personne</label>'
        + f'<select id="utilisateur" name="utilisateur_id" required>{"".join(options)}</select>'
        + '<button type="submit">Ajouter</button></form>'
        + "<h2>Tableau de bord</h2>"
        + f'<form method="post" action="/groupes/{int(groupe["id"])}/bsd" class="formulaire">'
        + jeton_cache(ctx)
        + f'<label class="case"><input type="checkbox" name="consulter_bsd" {coche}> '
        + "Consulter le tableau de bord</label>"
        + '<button type="submit">Enregistrer ce privilège</button></form>'
        + "<h2>Dossiers et fichiers</h2>"
        + "<p>Créer, consulter, modifier, supprimer. Un privilège posé sur une structure vaut aussi pour ses dossiers.</p>"
        + '<table><caption>Privilèges de ce groupe</caption><thead><tr><th>Emplacement</th><th>Privilèges</th></tr></thead><tbody>'
        + ("".join(lignes_droits) or '<tr><td colspan="2">Aucun privilège.</td></tr>')
        + "</tbody></table>"
        + f'<form method="post" action="/groupes/{int(groupe["id"])}/droit" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="noeud">Emplacement</label>'
        + f'<select id="noeud" name="noeud_id" required>{"".join(options_noeuds)}</select>'
        + '<fieldset><legend>Privilèges</legend>'
        + '<label class="case"><input type="checkbox" name="creer"> Créer</label>'
        + '<label class="case"><input type="checkbox" name="consulter"> Consulter</label>'
        + '<label class="case"><input type="checkbox" name="modifier"> Modifier</label>'
        + '<label class="case"><input type="checkbox" name="supprimer"> Supprimer</label>'
        + "</fieldset>"
        + "<p class=\"aide\">Tout décocher retire le privilège de ce groupe sur l’emplacement choisi.</p>"
        + '<button type="submit">Enregistrer les privilèges</button></form>'
    )


def action_membre(ctx, groupe_id):
    exiger_admin(ctx)
    try:
        utilisateur_id = int(ctx.formulaire.get("utilisateur_id", ""))
    except ValueError:
        return page_groupe(ctx, groupe_id, erreur="Choisissez une personne.")
    with base() as conn:
        if conn.execute("SELECT id FROM groupe WHERE id = ?", (int(groupe_id),)).fetchone() is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        personne = conn.execute(
            "SELECT id FROM utilisateur WHERE id = ? AND actif = 1", (utilisateur_id,)
        ).fetchone()
        if personne is None:
            return page_groupe(ctx, groupe_id, erreur="Cette personne ne peut pas être ajoutée.")
        conn.execute(
            "INSERT OR IGNORE INTO appartenance (groupe_id, utilisateur_id) VALUES (?, ?)",
            (int(groupe_id), utilisateur_id),
        )
    return Redirection(f"/groupes/{int(groupe_id)}?message=membre-ajoute")


def action_retirer(ctx, groupe_id):
    exiger_admin(ctx)
    try:
        utilisateur_id = int(ctx.formulaire.get("utilisateur_id", ""))
    except ValueError:
        return page_groupe(ctx, groupe_id, erreur="Personne inconnue.")
    with base() as conn:
        conn.execute(
            "DELETE FROM appartenance WHERE groupe_id = ? AND utilisateur_id = ?",
            (int(groupe_id), utilisateur_id),
        )
    return Redirection(f"/groupes/{int(groupe_id)}?message=membre-retire")


def action_droit(ctx, groupe_id):
    exiger_admin(ctx)
    try:
        noeud_id = int(ctx.formulaire.get("noeud_id", ""))
    except ValueError:
        return page_groupe(ctx, groupe_id, erreur="Choisissez un emplacement.")
    flags = {
        action: 1 if ctx.formulaire.get(action) is not None else 0
        for action in ("creer", "consulter", "modifier", "supprimer")
    }
    with base() as conn:
        if conn.execute("SELECT id FROM groupe WHERE id = ?", (int(groupe_id),)).fetchone() is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        noeud = conn.execute(
            "SELECT id, genre FROM noeud WHERE id = ?", (noeud_id,)
        ).fetchone()
        if noeud is None or noeud["genre"] == "fichier":
            return page_groupe(ctx, groupe_id, erreur="Cet emplacement ne reçoit pas de privilège direct.")
        if not any(flags.values()):
            conn.execute(
                "DELETE FROM droit WHERE groupe_id = ? AND noeud_id = ?",
                (int(groupe_id), noeud_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO droit (groupe_id, noeud_id, creer, consulter, modifier, supprimer)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(groupe_id, noeud_id) DO UPDATE SET
                    creer = excluded.creer,
                    consulter = excluded.consulter,
                    modifier = excluded.modifier,
                    supprimer = excluded.supprimer
                """,
                (int(groupe_id), noeud_id, flags["creer"], flags["consulter"], flags["modifier"], flags["supprimer"]),
            )
    return Redirection(f"/groupes/{int(groupe_id)}?message=droit-enregistre")


def action_bsd(ctx, groupe_id):
    exiger_admin(ctx)
    valeur = 1 if ctx.formulaire.get("consulter_bsd") is not None else 0
    with base() as conn:
        if conn.execute("SELECT id FROM groupe WHERE id = ?", (int(groupe_id),)).fetchone() is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        conn.execute(
            "UPDATE groupe SET consulter_bsd = ? WHERE id = ?",
            (valeur, int(groupe_id)),
        )
    return Redirection(f"/groupes/{int(groupe_id)}?message=bsd-enregistre")


def page_utilisateurs(ctx, erreur=None):
    exiger_admin(ctx)
    with base() as conn:
        personnes = conn.execute("SELECT * FROM utilisateur ORDER BY nom").fetchall()
        structures = conn.execute(
            "SELECT id, nom FROM noeud WHERE genre = 'structure' ORDER BY nom"
        ).fetchall()
        lignes = []
        for personne in personnes:
            role = _role(personne)
            etat = "actif" if personne["actif"] else "désactivé"
            action = ""
            if personne["actif"] and personne["id"] != ctx.utilisateur["id"]:
                action = (
                    f'<form method="post" action="/utilisateurs/{int(personne["id"])}/desactiver">'
                    f'{jeton_cache(ctx)}<button type="submit" class="secondaire">Désactiver</button></form>'
                )
            lignes.append(
                f'<tr data-identifiant="{echapper(personne["identifiant"])}">'
                f'<td>{echapper(personne["nom"])}</td>'
                f'<td>{echapper(personne["identifiant"])}</td>'
                f"<td>{role}</td><td>{etat}</td><td>{action}</td></tr>"
            )
    corps = (
        "<h1>Utilisateurs</h1>"
        "<table><caption>Comptes</caption><thead><tr>"
        "<th>Nom</th><th>Identifiant</th><th>Rôle</th><th>État</th><th></th>"
        "</tr></thead><tbody>"
        + "".join(lignes)
        + "</tbody></table>"
        + '<form method="post" action="/utilisateurs" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="identifiant">Identifiant</label>'
        + '<input id="identifiant" name="identifiant" maxlength="40" required autocomplete="off">'
        + '<label for="nom">Nom affiché</label>'
        + '<input id="nom" name="nom" maxlength="80" required>'
        + '<label for="mot">Mot de passe initial</label>'
        + '<input id="mot" name="mot_de_passe" type="password" required autocomplete="new-password">'
        + '<label class="case"><input type="checkbox" name="administrateur"> Administrateur</label>'
        + '<label for="fonction">Fonction</label>'
        + '<select id="fonction" name="fonction">'
        + '<option value="">Aucune fonction de hiérarchie</option>'
        + "".join(
            f'<option value="{cle}">{echapper(libelle)}</option>' for cle, libelle in FONCTIONS.items()
        )
        + '<option value="communication">Cellule de communication</option>'
        + "</select>"
        + '<label for="structure">Rattachement</label>'
        + '<select id="structure" name="structure_id">'
        + '<option value="">Aucun rattachement</option>'
        + "".join(
            f'<option value="{int(structure["id"])}">{echapper(structure["nom"])}</option>'
            for structure in structures
        )
        + "</select>"
        + '<p class="aide">Une fonction de hiérarchie ouvre tout le ministère. '
        "La cellule de communication rédige la page publique, sans ouvrir les directions. "
        "Sans fonction, le rattachement limite le compte à une direction ou un service. "
        "Une direction ne gère pas la page publique.</p>"
        + '<button type="submit">Créer le compte</button></form>'
    )
    return page("Utilisateurs", corps, ctx, actif="utilisateurs", erreur=erreur)


def action_utilisateur(ctx):
    exiger_admin(ctx)
    try:
        ident = valider_identifiant(ctx.formulaire.get("identifiant"))
        nom = ligne(ctx.formulaire.get("nom"), 2, 80, "Nom affiché")
        mot = mot_de_passe(ctx.formulaire.get("mot_de_passe"))
    except ValeurRefusee as exc:
        return page_utilisateurs(ctx, erreur=exc.message)
    admin = 1 if ctx.formulaire.get("administrateur") is not None else 0
    fonction = (ctx.formulaire.get("fonction") or "").strip()
    if fonction not in FONCTIONS and fonction not in ("", FONCTION_COMMUNICATION):
        return page_utilisateurs(ctx, erreur="Cette fonction n’est pas reconnue.")
    with base() as conn:
        if conn.execute(
            "SELECT id FROM utilisateur WHERE lower(identifiant) = lower(?)", (ident,)
        ).fetchone():
            return page_utilisateurs(ctx, erreur="Cet identifiant est déjà utilisé.")
        structure_id = None
        if not fonction:
            structure_id = _structure_compte(conn, ctx.formulaire)
            if structure_id == "invalide":
                return page_utilisateurs(ctx, erreur="La structure n’est pas dans l’arbre.")
        conn.execute(
            """
            INSERT INTO utilisateur (
                identifiant, nom, mot_de_passe, administrateur, fonction, structure_id, actif, cree_le
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (ident, nom, hasher(mot), admin, fonction, structure_id, maintenant()),
        )
    return Redirection("/utilisateurs?message=utilisateur-cree")


def _role(personne):
    morceaux = []
    if personne["administrateur"]:
        morceaux.append("administrateur")
    if personne["fonction"] in FONCTIONS:
        morceaux.append(FONCTIONS[personne["fonction"]])
    elif personne["fonction"] == FONCTION_COMMUNICATION:
        morceaux.append("cellule de communication")
    elif personne["structure_id"]:
        morceaux.append("direction ou service")
    return ", ".join(morceaux) if morceaux else "compte"


def _structure_compte(conn, formulaire):
    brut = (formulaire.get("structure_id") or "").strip()
    if not brut:
        return None
    try:
        structure_id = int(brut)
    except ValueError:
        return "invalide"
    if conn.execute(
        "SELECT id FROM noeud WHERE id = ? AND genre = 'structure'",
        (structure_id,),
    ).fetchone() is None:
        return "invalide"
    return structure_id


def action_desactiver(ctx, utilisateur_id):
    exiger_admin(ctx)
    with base() as conn:
        cible = conn.execute(
            "SELECT * FROM utilisateur WHERE id = ?", (int(utilisateur_id),)
        ).fetchone()
        if cible is None:
            return page("Introuvable", "<h1>Introuvable</h1>", ctx, statut=404)
        if cible["id"] == ctx.utilisateur["id"]:
            return page_utilisateurs(ctx, erreur="Vous ne pouvez pas désactiver votre propre compte.")
        if cible["administrateur"]:
            reste = conn.execute(
                """
                SELECT COUNT(*) AS n FROM utilisateur
                WHERE administrateur = 1 AND actif = 1 AND id != ?
                """,
                (cible["id"],),
            ).fetchone()["n"]
            if reste < 1:
                return page_utilisateurs(
                    ctx, erreur="Le dernier administrateur actif ne peut pas être désactivé."
                )
        conn.execute("UPDATE utilisateur SET actif = 0 WHERE id = ?", (cible["id"],))
        fermer_sessions(conn, cible["id"])
    return Redirection("/utilisateurs?message=utilisateur-desactive")


def page_compte(ctx, erreur=None):
    exiger_connexion(ctx)
    corps = (
        f'<h1>Compte</h1><p>{echapper(ctx.utilisateur["nom"])} '
        f'({echapper(ctx.utilisateur["identifiant"])})</p>'
        '<form method="post" action="/compte" class="formulaire">'
        + jeton_cache(ctx)
        + '<label for="actuel">Mot de passe actuel</label>'
        + '<input id="actuel" name="actuel" type="password" required autocomplete="current-password">'
        + '<label for="nouveau">Nouveau mot de passe</label>'
        + '<input id="nouveau" name="nouveau" type="password" required autocomplete="new-password">'
        + '<label for="confirmation">Confirmation</label>'
        + '<input id="confirmation" name="confirmation" type="password" required autocomplete="new-password">'
        + '<button type="submit">Changer le mot de passe</button></form>'
    )
    return page("Compte", corps, ctx, actif="compte", erreur=erreur)


def action_compte(ctx):
    exiger_connexion(ctx)
    try:
        nouveau = mot_de_passe(ctx.formulaire.get("nouveau"))
    except ValeurRefusee as exc:
        return page_compte(ctx, erreur=exc.message)
    if ctx.formulaire.get("nouveau") != ctx.formulaire.get("confirmation"):
        return page_compte(ctx, erreur="La confirmation ne correspond pas.")
    with base() as conn:
        ligne_user = conn.execute(
            "SELECT * FROM utilisateur WHERE id = ?", (ctx.utilisateur["id"],)
        ).fetchone()
        if not verifier_ou_factice(ctx.formulaire.get("actuel", ""), ligne_user["mot_de_passe"]):
            return page_compte(ctx, erreur="Le mot de passe actuel est incorrect.")
        conn.execute(
            "UPDATE utilisateur SET mot_de_passe = ? WHERE id = ?",
            (hasher(nouveau), ctx.utilisateur["id"]),
        )
        fermer_sessions(conn, ctx.utilisateur["id"])
    ctx.cookies.append(cookie_session_vide())
    ctx.cookies.append(cookie_jeton(nouveau_jeton()))
    return Redirection("/connexion?message=mot-de-passe-change")


def _noeuds_pour_droit(conn):
    lignes = conn.execute("SELECT * FROM noeud WHERE genre != 'fichier'").fetchall()
    par_parent = {}
    for ligne in lignes:
        par_parent.setdefault(ligne["parent_id"], []).append(ligne)
    rang = {"domaine": 0, "structure": 1, "dossier": 2}

    def marcher(parent_id, profondeur, acc):
        enfants = par_parent.get(parent_id, [])
        enfants.sort(key=lambda n: (rang.get(n["genre"], 9), n["ordre"], n["nom"].lower()))
        for enfant in enfants:
            acc.append((enfant, profondeur))
            marcher(enfant["id"], profondeur + 1, acc)

    acc = []
    marcher(None, 0, acc)
    return acc
