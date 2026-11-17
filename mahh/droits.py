"""Privilèges. Le haut de la chaîne voit tout. À partir du directeur, le compte ne voit que sa direction."""

from mahh.reponse import Interdit, NonConnecte

ACTIONS = ("creer", "consulter", "modifier", "supprimer")
NIVEAUX = (
    ("ministre", "Ministre"),
    ("secretaire_general", "Secrétaire général"),
    ("chef_cabinet", "Chef de cabinet"),
    ("directeur", "Directeur"),
    ("directeur_adjoint", "Directeur adjoint"),
    ("chef_division", "Chef de division"),
    ("chef_section", "Chef de section"),
    ("charge_etudes", "Chargé d’études"),
)
ACCES_COMPLET = ("ministre", "secretaire_general", "chef_cabinet", "bsd")
NIVEAUX_DIRECTION = tuple(cle for cle, _libelle in NIVEAUX if cle not in ACCES_COMPLET)
FONCTIONS = dict(NIVEAUX)
FONCTIONS["bsd"] = "BSD"
FONCTION_COMMUNICATION = "communication"


def exiger_connexion(ctx):
    if ctx.utilisateur is None:
        raise NonConnecte(ctx.chemin)


def exiger_admin(ctx):
    exiger_connexion(ctx)
    if not ctx.utilisateur["administrateur"]:
        raise Interdit("Cette page est réservée à l’administrateur.")


def peut_tenir_organigramme(utilisateur):
    """Le modèle MIYAH réserve l’organigramme au DG, au DGA et à l’IT.
    Ici : ministre, secrétaire général, chef de cabinet, ou administrateur."""
    if not utilisateur:
        return False
    if utilisateur["administrateur"]:
        return True
    return (utilisateur["fonction"] or "") in ("ministre", "secretaire_general", "chef_cabinet")


def exiger_organigramme(ctx):
    exiger_connexion(ctx)
    if not peut_tenir_organigramme(ctx.utilisateur):
        raise Interdit(
            "L’organigramme est tenu par le ministre, le secrétaire général, "
            "le chef de cabinet, ou un administrateur."
        )


def vide():
    return {action: False for action in ACTIONS}


def plein():
    return {action: True for action in ACTIONS}


def est_hierarchie(utilisateur):
    if not utilisateur:
        return False
    if utilisateur["administrateur"]:
        return True
    return (utilisateur["fonction"] or "") in ACCES_COMPLET


def peut_gerer_vitrine(utilisateur):
    """La page publique : hiérarchie, BSD, administrateur, cellule de communication."""
    if not utilisateur:
        return False
    if est_hierarchie(utilisateur):
        return True
    return (utilisateur["fonction"] or "") == FONCTION_COMMUNICATION


def dans_perimetre(conn, noeud_id, structure_id):
    """Vrai si le nœud est la structure, ou un dossier ou un fichier qui en descend."""
    if not structure_id:
        return False
    ligne = conn.execute(
        """
        WITH RECURSIVE chaine(id) AS (
            SELECT id FROM noeud WHERE id = ?
            UNION ALL
            SELECT n.parent_id FROM noeud n
            JOIN chaine c ON n.id = c.id
            WHERE n.parent_id IS NOT NULL
        )
        SELECT 1 AS ok FROM chaine WHERE id = ?
        """,
        (noeud_id, structure_id),
    ).fetchone()
    return ligne is not None


def peut_voir_projet(utilisateur, projet):
    if est_hierarchie(utilisateur):
        return True
    structure = utilisateur["structure_id"]
    return structure is not None and projet["structure_id"] == structure


def peut_tenir_projet(utilisateur, projet):
    return peut_voir_projet(utilisateur, projet)


def effectifs(conn, utilisateur, noeud_id):
    if utilisateur is None:
        return vide()
    if est_hierarchie(utilisateur):
        return plein()
    droits = plein() if dans_perimetre(conn, noeud_id, utilisateur["structure_id"]) else vide()
    lignes = conn.execute(
        """
        WITH RECURSIVE chaine(id) AS (
            SELECT id FROM noeud WHERE id = ?
            UNION ALL
            SELECT n.parent_id FROM noeud n
            JOIN chaine c ON n.id = c.id
            WHERE n.parent_id IS NOT NULL
        )
        SELECT d.creer, d.consulter, d.modifier, d.supprimer
        FROM droit d
        JOIN appartenance a ON a.groupe_id = d.groupe_id
        WHERE a.utilisateur_id = ?
          AND d.noeud_id IN (SELECT id FROM chaine)
        """,
        (noeud_id, utilisateur["id"]),
    ).fetchall()
    for ligne in lignes:
        for action in ACTIONS:
            if ligne[action]:
                droits[action] = True
    return droits


def a_un_privilege(droits):
    return any(droits.values())


def peut_voir_bsd(conn, utilisateur):
    if utilisateur is None:
        return False
    if est_hierarchie(utilisateur) or utilisateur["structure_id"]:
        return True
    ligne = conn.execute(
        """
        SELECT 1 FROM appartenance a
        JOIN groupe g ON g.id = a.groupe_id
        WHERE a.utilisateur_id = ? AND g.consulter_bsd = 1
        """,
        (utilisateur["id"],),
    ).fetchone()
    return ligne is not None


def peut_voir_directions(conn, utilisateur):
    if utilisateur is None:
        return False
    if est_hierarchie(utilisateur) or utilisateur["structure_id"]:
        return True
    ligne = conn.execute(
        """
        SELECT 1 FROM appartenance a
        JOIN droit d ON d.groupe_id = a.groupe_id
        WHERE a.utilisateur_id = ?
          AND (d.creer = 1 OR d.consulter = 1 OR d.modifier = 1 OR d.supprimer = 1)
        """,
        (utilisateur["id"],),
    ).fetchone()
    return ligne is not None


def peut_voir_instructions(utilisateur):
    if not utilisateur:
        return False
    return est_hierarchie(utilisateur) or bool(utilisateur["structure_id"])


def nom_structure(conn, utilisateur):
    if not utilisateur or not utilisateur["structure_id"]:
        return ""
    ligne = conn.execute(
        "SELECT nom FROM noeud WHERE id = ?",
        (utilisateur["structure_id"],),
    ).fetchone()
    return ligne["nom"] if ligne else ""


def peut_voir_ordures(conn, utilisateur):
    if utilisateur is None:
        return False
    if est_hierarchie(utilisateur):
        return True
    return nom_structure(conn, utilisateur) == "ANASP"


def peut_voir_reseau(conn, utilisateur, reseau):
    if utilisateur is None:
        return False
    if est_hierarchie(utilisateur):
        return True
    attendu = "SEG" if reseau == "seg" else "SNAPE"
    return nom_structure(conn, utilisateur) == attendu


def peut_voir_seg(conn, utilisateur):
    return peut_voir_reseau(conn, utilisateur, "seg")


def peut_voir_snape(conn, utilisateur):
    return peut_voir_reseau(conn, utilisateur, "snape")


def entrees_menu(conn, utilisateur):
    if utilisateur is None:
        return []
    entrees = [("/", "Accueil", "accueil")]
    if peut_voir_directions(conn, utilisateur):
        entrees.append(("/directions", "Directions", "directions"))
    if peut_voir_bsd(conn, utilisateur):
        entrees.append(("/bsd", "Tableau de bord", "bsd"))
    if peut_voir_instructions(utilisateur):
        entrees.append(("/instructions", "Instructions", "instructions"))
    if peut_voir_ordures(conn, utilisateur):
        entrees.append(("/ordures", "Ordures", "ordures"))
    if peut_voir_seg(conn, utilisateur):
        entrees.append(("/eau/seg", "SEG", "seg"))
    if peut_voir_snape(conn, utilisateur):
        entrees.append(("/eau/snape", "SNAPE", "snape"))
    if peut_gerer_vitrine(utilisateur):
        entrees.append(("/communication", "Communication", "communication"))
    if utilisateur["administrateur"]:
        entrees.append(("/groupes", "Groupes", "groupes"))
        entrees.append(("/utilisateurs", "Utilisateurs", "utilisateurs"))
        entrees.append(("/journal", "Journal", "journal"))
    if (
        est_hierarchie(utilisateur)
        or peut_voir_ordures(conn, utilisateur)
        or peut_voir_seg(conn, utilisateur)
        or peut_voir_snape(conn, utilisateur)
    ):
        entrees.append(("/carte", "Carte", "carte"))
    entrees.append(("/compte", "Compte", "compte"))
    return entrees


def exiger_bsd(ctx, conn):
    exiger_connexion(ctx)
    if not peut_voir_bsd(conn, ctx.utilisateur):
        raise Interdit(
            "Le tableau de bord est ouvert à la hiérarchie, au BSD, et à chaque direction pour ses projets."
        )


def libelle_droits(droits, administrateur=False):
    if administrateur:
        return "Tous les privilèges, en tant qu’administrateur."
    tenus = [action for action in ACTIONS if droits[action]]
    if not tenus:
        return "Aucun privilège sur les dossiers et les fichiers."
    noms = {"creer": "créer", "consulter": "consulter", "modifier": "modifier", "supprimer": "supprimer"}
    return "Privilèges ici : " + ", ".join(noms[action] for action in tenus) + "."
