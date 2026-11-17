"""Export des projets visibles au format CSV, lisible par Excel."""

import csv
import io

from mahh.db import base
from mahh.droits import exiger_bsd
from mahh.reponse import Octets
from mahh.tableau import _filtrer

COLONNES = (
    ("code", "Code"), ("secteur", "Secteur"), ("titre", "Titre"), ("localisation", "Localisation"),
    ("statut", "Statut"), ("budget_mds", "Budget (Mds GNF)"), ("decaissement", "Décaissement"),
    ("avancement", "Avancement"), ("debut", "Début"), ("echeance", "Échéance"),
    ("responsable", "Responsable"), ("financement", "Financement"), ("jalon", "Jalon"),
    ("observations", "Observations"),
)


def export_projets(ctx):
    with base() as conn:
        exiger_bsd(ctx, conn)
        r = ctx.requete
        projets = _filtrer(conn, ctx.utilisateur, r.get("secteur", ""), r.get("direction", ""), r.get("statut", ""))
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow([titre for _, titre in COLONNES])
    for p in projets:
        ecrivain.writerow([p[cle] for cle, _ in COLONNES])
    contenu = ("\ufeff" + tampon.getvalue()).encode("utf-8")
    return Octets(
        contenu,
        "text/csv; charset=utf-8",
        disposition=f'attachment; filename="projets-{ctx.aujourd_hui.isoformat()}.csv"',
    )
