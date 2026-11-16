"""Page d’instructions, destinée aux écrans du ministère. Pas un texte juridique."""

from datetime import date, timedelta

from mahh.db import base
from mahh.droits import FONCTIONS, est_hierarchie, exiger_connexion, peut_voir_instructions
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.tableau import _filtrer
from mahh.texte import echapper, fmt_date
from mahh.validation import bloc

CIRCUIT = (
    ("ministre", "Ministre", "Écrit à l’attention du chef de cabinet."),
    ("chef_cabinet", "Chef de cabinet", "Écrit à l’attention du secrétaire général."),
    ("secretaire_general", "Secrétaire général", "Écrit à l’attention d’une direction ou d’un service."),
    ("directions", "Directions et services", "Reçoivent l’instruction et le suivi."),
)
ECRITURE = {
    "ministre": "ministre",
    "chef_cabinet": "chef_cabinet",
    "secretaire_general": "secretaire_general",
}


def page_instructions(ctx, erreur=None):
    exiger_connexion(ctx)
    if not peut_voir_instructions(ctx.utilisateur):
        raise Interdit("Les instructions concernent la hiérarchie, le BSD, et les directions.")
    with base() as conn:
        instructions = _instructions_visibles(conn, ctx.utilisateur)
        retards = [
            projet
            for projet in _filtrer(conn, ctx.utilisateur, "", "", "")
            if projet["statut"] == "En retard"
        ]
        structures = conn.execute(
            "SELECT id, nom FROM noeud WHERE genre = 'structure' ORDER BY nom"
        ).fetchall()
        corps = _corps(ctx, instructions, retards, structures)
    return page("Instructions", corps, ctx, actif="instructions", erreur=erreur)


def action_instruction(ctx):
    exiger_connexion(ctx)
    echelon = (ctx.formulaire.get("echelon") or "").strip()
    if not _peut_ecrire(ctx.utilisateur, echelon):
        raise Interdit("Cet échelon n’écrit pas depuis votre compte.")
    try:
        texte = bloc(ctx.formulaire.get("texte"), 2, 2000, "Instruction")
    except ValeurRefusee as exc:
        return page_instructions(ctx, erreur=exc.message)
    echeance = _date(ctx.formulaire.get("echeance"))
    if echeance is False:
        return page_instructions(ctx, erreur="L’échéance n’est pas une date valide.")
    with base() as conn:
        structure_id = None
        if echelon == "secretaire_general":
            structure_id = _structure(conn, ctx.formulaire)
            if structure_id is None:
                return page_instructions(
                    ctx, erreur="Le secrétaire général désigne une direction ou un service."
                )
        conn.execute(
            """
            INSERT INTO instruction (
                echelon, structure_id, texte, cree_par, cree_le, echeance
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (echelon, structure_id, texte, ctx.utilisateur["id"], maintenant(), echeance or ""),
        )
    return Redirection("/instructions?message=instruction-creee")


def action_executer(ctx, identifiant):
    exiger_connexion(ctx)
    compte_rendu = (ctx.formulaire.get("compte_rendu") or "").strip()[:2000]
    with base() as conn:
        instruction = _instruction(conn, identifiant)
        if not peut_executer(ctx.utilisateur, instruction):
            raise Interdit("Seuls la structure destinataire, la hiérarchie et le BSD marquent cette instruction.")
        conn.execute(
            """
            UPDATE instruction
            SET etat = 'executee', execute_le = ?, execute_par = ?, compte_rendu = ?
            WHERE id = ?
            """,
            (maintenant(), ctx.utilisateur["id"], compte_rendu, instruction["id"]),
        )
    return Redirection("/instructions?message=instruction-executee")


def action_rouvrir(ctx, identifiant):
    exiger_connexion(ctx)
    if not est_hierarchie(ctx.utilisateur):
        raise Interdit("Rouvrir une instruction est réservé à la hiérarchie et au BSD.")
    with base() as conn:
        instruction = _instruction(conn, identifiant)
        conn.execute(
            """
            UPDATE instruction
            SET etat = 'en_cours', execute_le = NULL, execute_par = NULL, compte_rendu = ''
            WHERE id = ?
            """,
            (instruction["id"],),
        )
    return Redirection("/instructions?message=instruction-rouverte")


def _instruction(conn, identifiant):
    try:
        identifiant = int(identifiant)
    except (TypeError, ValueError):
        raise Interdit("Cette instruction n’existe pas.")
    ligne = conn.execute("SELECT * FROM instruction WHERE id = ?", (identifiant,)).fetchone()
    if ligne is None:
        raise Interdit("Cette instruction n’existe pas.")
    return ligne


def peut_executer(utilisateur, instruction):
    if instruction["etat"] == "executee":
        return False
    if est_hierarchie(utilisateur):
        return True
    return bool(utilisateur["structure_id"]) and instruction["structure_id"] == utilisateur["structure_id"]


def en_retard(instruction, aujourd_hui):
    return (
        instruction["etat"] != "executee"
        and bool(instruction["echeance"])
        and instruction["echeance"] < aujourd_hui.isoformat()
    )


def bilan(instructions, aujourd_hui):
    """Comptes lus sur les instructions déjà publiées : rien n’est inventé."""
    depuis = (aujourd_hui - timedelta(days=6)).isoformat()
    return {
        "semaine": sum(
            1
            for instruction in instructions
            if instruction["etat"] == "executee" and (instruction["execute_le"] or "")[:10] >= depuis
        ),
        "en_cours": sum(1 for instruction in instructions if instruction["etat"] != "executee"),
        "retard": sum(1 for instruction in instructions if en_retard(instruction, aujourd_hui)),
    }


def _date(brut):
    brut = (brut or "").strip()
    if not brut:
        return None
    try:
        return date.fromisoformat(brut).isoformat()
    except ValueError:
        return False


def _peut_ecrire(utilisateur, echelon):
    if echelon not in ECRITURE:
        return False
    if utilisateur["administrateur"]:
        return True
    return utilisateur["fonction"] == echelon


def _structure(conn, formulaire):
    brut = (formulaire.get("structure_id") or "").strip()
    if not brut:
        return None
    try:
        structure_id = int(brut)
    except ValueError:
        return None
    ligne = conn.execute(
        "SELECT id FROM noeud WHERE id = ? AND genre = 'structure'",
        (structure_id,),
    ).fetchone()
    return structure_id if ligne else None


def _instructions_visibles(conn, utilisateur):
    if est_hierarchie(utilisateur):
        return conn.execute(
            """
            SELECT i.*, u.nom AS auteur, n.nom AS structure
            FROM instruction i
            LEFT JOIN utilisateur u ON u.id = i.cree_par
            LEFT JOIN noeud n ON n.id = i.structure_id
            ORDER BY i.cree_le DESC, i.id DESC
            """
        ).fetchall()
    if not utilisateur["structure_id"]:
        return []
    return conn.execute(
        """
        SELECT i.*, u.nom AS auteur, n.nom AS structure
        FROM instruction i
        LEFT JOIN utilisateur u ON u.id = i.cree_par
        LEFT JOIN noeud n ON n.id = i.structure_id
        WHERE i.echelon = 'secretaire_general' AND i.structure_id = ?
        ORDER BY i.cree_le DESC, i.id DESC
        """,
        (utilisateur["structure_id"],),
    ).fetchall()


def _corps(ctx, instructions, retards, structures):
    etapes = []
    for cle, libelle, phrase in CIRCUIT:
        etapes.append(
            f'<li data-echelon="{cle}"><strong>{echapper(libelle)}</strong>'
            f"<span>{echapper(phrase)}</span></li>"
        )
    return (
        '<section class="ecran">'
        "<p class=\"ecran-ministere\">Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures</p>"
        "<h1>Instructions</h1>"
        "<p class=\"ecran-sous\">Du ministre aux directions. Page destinée aux écrans du ministère.</p>"
        f'<ol class="circuit">{"".join(etapes)}</ol>'
        "</section>"
        + _bilan(bilan(instructions, ctx.aujourd_hui))
        + _retards(retards)
        + _liste_instructions(ctx, instructions)
        + _formulaires(ctx, structures)
    )


def _retards(retards):
    if not retards:
        return "<h2>Projets en retard</h2><p>Aucun projet en retard dans votre vue.</p>"
    items = []
    for projet in retards:
        items.append(
            f'<li data-retard="{echapper(projet["code"])}">'
            f'<a href="/bsd/projet/{int(projet["id"])}">{echapper(projet["code"])}</a> '
            f"{echapper(projet['titre'])}</li>"
        )
    return "<h2>Projets en retard</h2><ul>" + "".join(items) + "</ul>"


def _bilan(chiffres):
    return (
        '<div class="bilan">'
        f'<div data-bilan="semaine"><strong>{chiffres["semaine"]}</strong> exécutées ces 7 derniers jours</div>'
        f'<div data-bilan="en-cours"><strong>{chiffres["en_cours"]}</strong> en cours</div>'
        f'<div data-bilan="retard"><strong>{chiffres["retard"]}</strong> échéance dépassée</div>'
        "</div>"
    )


def _etat(ctx, instruction):
    if instruction["etat"] == "executee":
        quand = fmt_date((instruction["execute_le"] or "")[:10]) if instruction["execute_le"] else ""
        return f'<span class="suivi suivi-executee">Exécutée le {echapper(quand)}</span>'
    if en_retard(instruction, ctx.aujourd_hui):
        return (
            f'<span class="suivi suivi-retard">En retard — échéance '
            f'{echapper(fmt_date(instruction["echeance"]))}</span>'
        )
    if instruction["echeance"]:
        return (
            f'<span class="suivi suivi-en-cours">En cours — échéance '
            f'{echapper(fmt_date(instruction["echeance"]))}</span>'
        )
    return '<span class="suivi suivi-en-cours">En cours</span>'


def _actions(ctx, instruction):
    identifiant = int(instruction["id"])
    if peut_executer(ctx.utilisateur, instruction):
        return (
            f'<form method="post" action="/instructions/{identifiant}/executer">'
            + jeton_cache(ctx)
            + f'<label for="cr-{identifiant}">Compte rendu</label>'
            + f'<input id="cr-{identifiant}" name="compte_rendu" maxlength="2000">'
            + '<button type="submit">Marquer exécutée</button></form>'
        )
    if instruction["etat"] == "executee" and est_hierarchie(ctx.utilisateur):
        return (
            f'<form method="post" action="/instructions/{identifiant}/rouvrir">'
            + jeton_cache(ctx)
            + '<button type="submit" class="secondaire">Rouvrir</button></form>'
        )
    return ""


def _liste_instructions(ctx, instructions):
    if not instructions:
        return "<h2>Instructions publiées</h2><p>Aucune instruction dans votre vue.</p>"
    items = []
    for instruction in instructions:
        auteur = instruction["auteur"] or "Compte retiré"
        cible = ""
        if instruction["structure"]:
            cible = f" — {echapper(instruction['structure'])}"
        compte = ""
        if instruction["compte_rendu"] and instruction["etat"] == "executee":
            compte = f"<p class=\"meta\">Compte rendu : {echapper(instruction['compte_rendu'])}</p>"
        items.append(
            "<article class=\"instruction\">"
            f"<p class=\"meta\">{echapper(FONCTIONS.get(instruction['echelon'], instruction['echelon']))}"
            f"{cible} · {echapper(auteur)} · {echapper(fmt_date(instruction['cree_le'][:10]))}</p>"
            f"<p>{echapper(instruction['texte'])}</p>"
            f"<p>{_etat(ctx, instruction)}</p>"
            + compte
            + _actions(ctx, instruction)
            + "</article>"
        )
    return "<h2>Instructions publiées</h2>" + "".join(items)


def _formulaires(ctx, structures):
    blocs = []
    for echelon, libelle in (
        ("ministre", "Instruction du ministre"),
        ("chef_cabinet", "Instruction du chef de cabinet"),
        ("secretaire_general", "Instruction du secrétaire général"),
    ):
        if not _peut_ecrire(ctx.utilisateur, echelon):
            continue
        structure = ""
        if echelon == "secretaire_general":
            structure = (
                '<label for="structure-instruction">Direction ou service</label>'
                + _select("structure-instruction", "structure_id", structures)
            )
        blocs.append(
            f"<h2>{echapper(libelle)}</h2>"
            '<form method="post" action="/instructions" class="formulaire">'
            + jeton_cache(ctx)
            + f'<input type="hidden" name="echelon" value="{echelon}">'
            + structure
            + '<label for="texte-' + echelon + '">Texte</label>'
            + f'<textarea id="texte-{echelon}" name="texte" required maxlength="2000"></textarea>'
            + f'<label for="echeance-{echelon}">Échéance (facultative)</label>'
            + f'<input type="date" id="echeance-{echelon}" name="echeance">'
            + '<button type="submit">Publier</button></form>'
        )
    return "".join(blocs)


def _select(identifiant, nom, structures):
    options = ['<option value="">Choisir</option>']
    for structure in structures:
        options.append(
            f'<option value="{int(structure["id"])}">{echapper(structure["nom"])}</option>'
        )
    return f'<select id="{identifiant}" name="{nom}" required>{"".join(options)}</select>'
