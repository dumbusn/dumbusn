"""Journal d’activité : qui a fait quoi, et quand. Lecture réservée à l’administrateur."""

from mahh.db import base
from mahh.droits import exiger_admin
from mahh.presentation import page
from mahh.securite import maintenant
from mahh.texte import echapper

LIBELLES = (
    ("/executer", "Instruction marquée exécutée"),
    ("/rouvrir", "Instruction rouverte"),
    ("/instructions", "Instruction publiée"),
    ("/bsd/saisie", "Projet saisi"),
    ("/modifier", "Modification"),
    ("/supprimer", "Suppression"),
    ("/piece", "Pièce ajoutée à un projet"),
    ("/dossier", "Dossier créé"),
    ("/fichier", "Fichier déposé"),
    ("/renommer", "Renommage"),
    ("/droit", "Privilèges modifiés"),
    ("/membre", "Membre ajouté à un groupe"),
    ("/utilisateurs", "Compte créé ou modifié"),
    ("/payer", "Paiement enregistré"),
    ("/signalement", "Signalement « poubelle pleine »"),
    ("/passage", "Position d’agent enregistrée"),
    ("/deconnexion", "Déconnexion"),
)


def libelle(chemin):
    for motif, texte in LIBELLES:
        if motif in chemin:
            return texte
    return "Action"


def consigner(utilisateur_id, chemin):
    with base() as conn:
        conn.execute(
            "INSERT INTO journal (utilisateur_id, action, chemin, quand) VALUES (?, ?, ?, ?)",
            (utilisateur_id, libelle(chemin), chemin, maintenant()),
        )


def page_journal(ctx):
    exiger_admin(ctx)
    with base() as conn:
        lignes = conn.execute(
            """
            SELECT j.*, u.nom AS nom FROM journal j
            LEFT JOIN utilisateur u ON u.id = j.utilisateur_id
            ORDER BY j.id DESC LIMIT 500
            """
        ).fetchall()
    if lignes:
        rangs = "".join(
            f"<tr><td>{echapper(l['quand'][:16].replace('T', ' '))}</td>"
            f"<td>{echapper(l['nom'] or 'Compte retiré')}</td>"
            f"<td>{echapper(l['action'])}</td><td><code>{echapper(l['chemin'])}</code></td></tr>"
            for l in lignes
        )
        table = (
            "<table><thead><tr><th>Quand</th><th>Qui</th><th>Action</th><th>Adresse</th></tr></thead>"
            f"<tbody>{rangs}</tbody></table>"
        )
    else:
        table = "<p>Aucune action enregistrée pour l’instant.</p>"
    corps = (
        "<h1>Journal d’activité</h1>"
        "<p class=\"aide\">Les 500 dernières actions enregistrées (créations, modifications, suppressions, paiements…).</p>"
        + table
    )
    return page("Journal", corps, ctx, actif="journal")
