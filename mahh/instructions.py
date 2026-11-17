"""Instructions du ministère. Chaque niveau n’instruit que le niveau juste en dessous."""

from datetime import date, timedelta

from mahh.courriel import envoyer, lien_instruction
from mahh.db import base
from mahh.droits import FONCTIONS, est_hierarchie, exiger_connexion, peut_voir_instructions
from mahh.presentation import jeton_cache, page
from mahh.reponse import Interdit, Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.tableau import _filtrer
from mahh.texte import echapper, fmt_date
from mahh.validation import bloc

# Le chargé d’études reçoit. Il n’instruit pas en dessous.
CHAINE = (
    "ministre",
    "secretaire_general",
    "chef_cabinet",
    "directeur",
    "directeur_adjoint",
    "chef_division",
    "chef_section",
    "charge_etudes",
)
SUIVANT = {niveau: CHAINE[index + 1] for index, niveau in enumerate(CHAINE[:-1])}
MINISTERE = ("ministre", "secretaire_general", "chef_cabinet")
PHRASES = {
    "ministre": "Instruit le secrétaire général, et seulement lui.",
    "secretaire_general": "Instruit le chef de cabinet, et seulement lui.",
    "chef_cabinet": "Instruit les directeurs, et seulement eux.",
    "directeur": "Instruit les directeurs adjoints de sa direction.",
    "directeur_adjoint": "Instruit les chefs de division de sa direction.",
    "chef_division": "Instruit les chefs de section de sa direction.",
    "chef_section": "Instruit les chargés d’études de sa direction.",
    "charge_etudes": "Reçoit l’instruction. N’instruit pas en dessous.",
}


def page_instructions(ctx, erreur=None):
    exiger_connexion(ctx)
    if not peut_voir_instructions(ctx.utilisateur):
        raise Interdit("Les instructions concernent la chaîne du ministère et les directions.")
    with base() as conn:
        instructions = _instructions_visibles(conn, ctx.utilisateur)
        retards = [
            projet
            for projet in _filtrer(conn, ctx.utilisateur, "", "", "")
            if projet["statut"] == "En retard"
        ]
        corps = _corps(ctx, conn, instructions, retards)
    return page("Instructions", corps, ctx, actif="instructions", erreur=erreur)


def page_une_instruction(ctx, identifiant):
    exiger_connexion(ctx)
    with base() as conn:
        instruction = _instruction_visible(conn, ctx.utilisateur, identifiant)
        if instruction is None:
            raise Interdit("Cette instruction ne vous est pas destinée.")
        destinataires = _destinataires(conn, instruction["id"])
        corps = _article(ctx, instruction, destinataires, seule=True)
    return page("Instruction", "<h1>Instruction</h1>" + corps, ctx, actif="instructions")


def action_instruction(ctx):
    exiger_connexion(ctx)
    niveau = (ctx.utilisateur["fonction"] or "")
    cible = SUIVANT.get(niveau)
    if cible is None:
        raise Interdit("Ce compte ne transmet pas d’instruction à un niveau inférieur.")
    try:
        texte = bloc(ctx.formulaire.get("texte"), 2, 2000, "Instruction")
    except ValeurRefusee as exc:
        return page_instructions(ctx, erreur=exc.message)
    echeance = _date(ctx.formulaire.get("echeance"))
    if echeance is False:
        return page_instructions(ctx, erreur="L’échéance n’est pas une date valide.")
    demandes = _plusieurs(ctx, "destinataire")
    with base() as conn:
        possibles = {personne["id"]: personne for personne in _possibles(conn, ctx.utilisateur, cible)}
        choisis = []
        for brut in demandes:
            try:
                identifiant = int(brut)
            except ValueError:
                continue
            if identifiant in possibles:
                choisis.append(possibles[identifiant])
        if not choisis:
            return page_instructions(ctx, erreur="Choisissez au moins un destinataire du niveau juste en dessous.")
        structure_id = _structure_instruction(ctx.utilisateur, choisis)
        curseur = conn.execute(
            """
            INSERT INTO instruction (
                echelon, structure_id, texte, cree_par, cree_le, echeance
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (niveau, structure_id, texte, ctx.utilisateur["id"], maintenant(), echeance or ""),
        )
        instruction_id = curseur.lastrowid
        conn.executemany(
            """
            INSERT INTO instruction_destinataire (instruction_id, utilisateur_id)
            VALUES (?, ?)
            """,
            [(instruction_id, personne["id"]) for personne in choisis],
        )
        adresses = [personne["courriel"] for personne in choisis]
        lien = lien_instruction(instruction_id)
    resultat = envoyer(
        adresses,
        "Instruction du ministère",
        (
            f"{ctx.utilisateur['nom']} vous adresse une instruction.\n\n"
            f"{texte}\n\n"
            "Ouvrez le lien, identifiez-vous, puis lisez l’instruction :\n"
            f"{lien}\n"
        ),
    )
    messages = {
        "envoye": "instruction-envoyee",
        "absent": "instruction-sans-courriel",
        "sans-adresse": "instruction-sans-adresse",
        "echec": "instruction-courriel-echec",
    }
    return Redirection("/instructions?message=" + messages.get(resultat, "instruction-sans-courriel"))


def action_executer(ctx, identifiant):
    exiger_connexion(ctx)
    compte_rendu = (ctx.formulaire.get("compte_rendu") or "").strip()[:2000]
    with base() as conn:
        instruction = _instruction(conn, identifiant)
        if not _est_destinataire_ouvert(conn, ctx.utilisateur, instruction["id"]):
            raise Interdit("Seul le destinataire marque son retour.")
        conn.execute(
            """
            UPDATE instruction_destinataire
            SET etat = 'executee', execute_le = ?, compte_rendu = ?
            WHERE instruction_id = ? AND utilisateur_id = ?
            """,
            (maintenant(), compte_rendu, instruction["id"], ctx.utilisateur["id"]),
        )
        reste = conn.execute(
            """
            SELECT 1 FROM instruction_destinataire
            WHERE instruction_id = ? AND etat != 'executee'
            """,
            (instruction["id"],),
        ).fetchone()
        if reste is None:
            conn.execute(
                """
                UPDATE instruction
                SET etat = 'executee', execute_le = ?, execute_par = ?, compte_rendu = ?
                WHERE id = ?
                """,
                (maintenant(), ctx.utilisateur["id"], compte_rendu, instruction["id"]),
            )
    return Redirection(f"/instructions/{int(identifiant)}?message=instruction-executee")


def action_rouvrir(ctx, identifiant):
    exiger_connexion(ctx)
    with base() as conn:
        instruction = _instruction(conn, identifiant)
        if not (est_hierarchie(ctx.utilisateur) or instruction["cree_par"] == ctx.utilisateur["id"]):
            raise Interdit("Seul l’auteur, ou la hiérarchie, rouvre l’instruction.")
        conn.execute(
            """
            UPDATE instruction_destinataire
            SET etat = 'en_cours', execute_le = NULL, compte_rendu = ''
            WHERE instruction_id = ?
            """,
            (instruction["id"],),
        )
        conn.execute(
            """
            UPDATE instruction
            SET etat = 'en_cours', execute_le = NULL, execute_par = NULL, compte_rendu = ''
            WHERE id = ?
            """,
            (instruction["id"],),
        )
    return Redirection(f"/instructions/{int(identifiant)}?message=instruction-rouverte")


def _plusieurs(ctx, cle):
    valeurs = getattr(ctx, "listes", {}).get(cle)
    if valeurs:
        return [valeur for valeur in valeurs if str(valeur).strip()]
    brut = (ctx.formulaire.get(cle) or "").strip()
    return [brut] if brut else []


def _structure_instruction(utilisateur, choisis):
    if utilisateur["structure_id"]:
        return utilisateur["structure_id"]
    structures = {personne["structure_id"] for personne in choisis if personne["structure_id"]}
    if len(structures) == 1:
        return structures.pop()
    return None


def _possibles(conn, utilisateur, cible):
    if utilisateur["fonction"] in MINISTERE:
        return conn.execute(
            """
            SELECT id, nom, courriel, structure_id FROM utilisateur
            WHERE actif = 1 AND fonction = ?
            ORDER BY nom
            """,
            (cible,),
        ).fetchall()
    if not utilisateur["structure_id"]:
        return []
    return conn.execute(
        """
        SELECT id, nom, courriel, structure_id FROM utilisateur
        WHERE actif = 1 AND fonction = ? AND structure_id = ?
        ORDER BY nom
        """,
        (cible, utilisateur["structure_id"]),
    ).fetchall()


def _instruction(conn, identifiant):
    try:
        identifiant = int(identifiant)
    except (TypeError, ValueError):
        raise Interdit("Cette instruction n’existe pas.")
    ligne = conn.execute("SELECT * FROM instruction WHERE id = ?", (identifiant,)).fetchone()
    if ligne is None:
        raise Interdit("Cette instruction n’existe pas.")
    return ligne


def _instruction_visible(conn, utilisateur, identifiant):
    try:
        identifiant = int(identifiant)
    except (TypeError, ValueError):
        return None
    visibles = {ligne["id"]: ligne for ligne in _instructions_visibles(conn, utilisateur)}
    return visibles.get(identifiant)


def _est_destinataire_ouvert(conn, utilisateur, instruction_id):
    ligne = conn.execute(
        """
        SELECT etat FROM instruction_destinataire
        WHERE instruction_id = ? AND utilisateur_id = ?
        """,
        (instruction_id, utilisateur["id"]),
    ).fetchone()
    return ligne is not None and ligne["etat"] != "executee"


def _instructions_visibles(conn, utilisateur):
    requete = """
        SELECT DISTINCT i.*, u.nom AS auteur
        FROM instruction i
        LEFT JOIN utilisateur u ON u.id = i.cree_par
        LEFT JOIN instruction_destinataire d ON d.instruction_id = i.id
    """
    if est_hierarchie(utilisateur):
        requete += " ORDER BY i.cree_le DESC, i.id DESC"
        return conn.execute(requete).fetchall()
    if utilisateur["fonction"] == "directeur" and utilisateur["structure_id"]:
        requete += """
            WHERE i.cree_par = ? OR d.utilisateur_id = ? OR i.structure_id = ?
            ORDER BY i.cree_le DESC, i.id DESC
        """
        return conn.execute(
            requete,
            (utilisateur["id"], utilisateur["id"], utilisateur["structure_id"]),
        ).fetchall()
    requete += """
        WHERE i.cree_par = ? OR d.utilisateur_id = ?
        ORDER BY i.cree_le DESC, i.id DESC
    """
    return conn.execute(requete, (utilisateur["id"], utilisateur["id"])).fetchall()


def _destinataires(conn, instruction_id):
    return conn.execute(
        """
        SELECT d.*, u.nom, u.courriel
        FROM instruction_destinataire d
        JOIN utilisateur u ON u.id = d.utilisateur_id
        WHERE d.instruction_id = ?
        ORDER BY u.nom
        """,
        (instruction_id,),
    ).fetchall()


def en_retard(instruction, aujourd_hui):
    return (
        instruction["etat"] != "executee"
        and bool(instruction["echeance"])
        and instruction["echeance"] < aujourd_hui.isoformat()
    )


def bilan(instructions, aujourd_hui):
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


def _corps(ctx, conn, instructions, retards):
    etapes = []
    for niveau in CHAINE:
        etapes.append(
            f'<li data-echelon="{niveau}"><strong>{echapper(FONCTIONS[niveau])}</strong>'
            f"<span>{echapper(PHRASES[niveau])}</span></li>"
        )
    return (
        '<section class="ecran">'
        "<p class=\"ecran-ministere\">Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures</p>"
        "<h1>Instructions</h1>"
        "<p class=\"ecran-sous\">Chaque niveau instruit seulement le niveau juste en dessous, "
        "choisit ses destinataires et attend leur retour.</p>"
        f'<ol class="circuit">{"".join(etapes)}</ol>'
        "</section>"
        + _bilan(bilan(instructions, ctx.aujourd_hui))
        + _retards(retards)
        + _liste(ctx, conn, instructions)
        + _formulaire(ctx, conn)
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


def _liste(ctx, conn, instructions):
    if not instructions:
        return "<h2>Instructions</h2><p>Aucune instruction dans votre vue.</p>"
    articles = []
    for instruction in instructions:
        articles.append(_article(ctx, instruction, _destinataires(conn, instruction["id"])))
    return "<h2>Instructions</h2>" + "".join(articles)


def _article(ctx, instruction, destinataires, seule=False):
    auteur = instruction["auteur"] if "auteur" in instruction.keys() else ""
    if not auteur:
        auteur = "Compte retiré"
    lignes = []
    for personne in destinataires:
        etat = "Exécutée" if personne["etat"] == "executee" else "En cours"
        retour = ""
        if personne["compte_rendu"] and personne["etat"] == "executee":
            retour = f" — {echapper(personne['compte_rendu'])}"
        lignes.append(f"<li>{echapper(personne['nom'])} : {etat}{retour}</li>")
    retour_form = ""
    if any(personne["utilisateur_id"] == ctx.utilisateur["id"] and personne["etat"] != "executee" for personne in destinataires):
        identifiant = int(instruction["id"])
        retour_form = (
            f'<form method="post" action="/instructions/{identifiant}/executer">'
            + jeton_cache(ctx)
            + f'<label for="cr-{identifiant}">Votre retour</label>'
            + f'<input id="cr-{identifiant}" name="compte_rendu" maxlength="2000">'
            + '<button type="submit">Marquer exécutée</button></form>'
        )
    rouvrir = ""
    if instruction["etat"] == "executee" and (
        est_hierarchie(ctx.utilisateur) or instruction["cree_par"] == ctx.utilisateur["id"]
    ):
        identifiant = int(instruction["id"])
        rouvrir = (
            f'<form method="post" action="/instructions/{identifiant}/rouvrir">'
            + jeton_cache(ctx)
            + '<button type="submit" class="secondaire">Rouvrir</button></form>'
        )
    lien = ""
    if not seule:
        lien = f'<p><a href="/instructions/{int(instruction["id"])}">Ouvrir</a></p>'
    echeance = ""
    if instruction["echeance"]:
        marque = "En retard" if en_retard(instruction, ctx.aujourd_hui) else "Échéance"
        echeance = f"<p class=\"meta\">{marque} : {echapper(fmt_date(instruction['echeance']))}</p>"
    return (
        '<article class="instruction">'
        f"<p class=\"meta\">{echapper(FONCTIONS.get(instruction['echelon'], instruction['echelon']))}"
        f" · {echapper(auteur)} · {echapper(fmt_date(instruction['cree_le'][:10]))}</p>"
        f"<p>{echapper(instruction['texte'])}</p>"
        + echeance
        + f"<ul>{''.join(lignes)}</ul>"
        + lien
        + retour_form
        + rouvrir
        + "</article>"
    )


def _formulaire(ctx, conn):
    cible = SUIVANT.get(ctx.utilisateur["fonction"] or "")
    if cible is None:
        if ctx.utilisateur["fonction"] == "charge_etudes":
            return (
                "<h2>Votre niveau</h2>"
                "<p>Vous recevez les instructions. Vous n’instruisez pas en dessous.</p>"
            )
        return ""
    personnes = _possibles(conn, ctx.utilisateur, cible)
    if personnes:
        cases = "".join(
            "<label class=\"case\">"
            f'<input type="checkbox" name="destinataire" value="{int(personne["id"])}"> '
            f"{echapper(personne['nom'])}</label>"
            for personne in personnes
        )
    else:
        cases = (
            "<p>Aucun compte de ce niveau pour l’instant. "
            "L’administrateur le crée, puis vous pourrez lui adresser l’instruction.</p>"
        )
    portee = (
        "Vous voyez les destinataires de tout le ministère."
        if ctx.utilisateur["fonction"] in MINISTERE
        else "Vous ne voyez que les destinataires de votre direction."
    )
    return (
        f"<h2>Instruction vers : {echapper(FONCTIONS[cible])}</h2>"
        f'<form method="post" action="/instructions" class="formulaire" data-niveau="{cible}">'
        + jeton_cache(ctx)
        + f"<p>{echapper(portee)} Vous attendez leur retour.</p>"
        + cases
        + '<label for="texte-instruction">Texte</label>'
        + '<textarea id="texte-instruction" name="texte" required maxlength="2000"></textarea>'
        + '<label for="echeance-instruction">Échéance (facultative)</label>'
        + '<input type="date" id="echeance-instruction" name="echeance">'
        + '<button type="submit">Envoyer l’instruction</button></form>'
    )
