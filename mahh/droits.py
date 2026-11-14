"""Privilèges. La hiérarchie voit tout. Une direction ne voit que ce qui la concerne. Les groupes complètent."""

from mahh.reponse import Interdit, NonConnecte

ACTIONS = ("creer", "consulter", "modifier", "supprimer")
FONCTIONS = {
    "ministre": "Ministre",
    "chef_cabinet": "Chef de cabinet",
    "secretaire_general": "Secrétaire général",
    "bsd": "BSD",
}


def exiger_connexion(ctx):
    if ctx.utilisateur is None:
        raise NonConnecte(ctx.chemin)


def exiger_admin(ctx):
    exiger_connexion(ctx)
    if not ctx.utilisateur["administrateur"]:
        raise Interdit("Cette page est réservée à l’administrateur.")


def vide():
    return {action: False for action in ACTIONS}


def plein():
    return {action: True for action in ACTIONS}


def est_hierarchie(utilisateur):
    if not utilisateur:
        return False
    if utilisateur["administrateur"]:
        return True
    return (utilisateur["fonction"] or "") in FONCTIONS


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
