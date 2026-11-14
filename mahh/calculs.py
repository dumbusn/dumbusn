"""Indicateurs du classeur, calculés sur les lignes du filtre."""

from datetime import date
from decimal import Decimal

STATUTS = (
    "Terminé",
    "Dans les délais",
    "À risque",
    "En retard",
    "Suspendu",
    "En préparation",
)
SECTEURS = (
    "Assainissement",
    "Hydraulique",
    "Hydrocarbures",
    "Administration",
)
SECTEURS_CLASSEUR = ("Assainissement", "Hydraulique", "Hydrocarbures")
EN_COURS = {"Dans les délais", "À risque", "En retard"}
FINANCEMENTS_EXEMPLE = (
    "Budget national",
    "Partenaire technique et financier",
    "Budget national et partenaires",
)


def _d(valeur):
    return Decimal(str(valeur))


def synthese(projets, secteur_demande=None):
    lignes = list(projets)
    budget = sum((_d(p["budget_mds"]) for p in lignes), Decimal("0"))
    decaisse = sum((_d(p["budget_mds"]) * _d(p["decaissement"]) for p in lignes), Decimal("0"))
    if budget == 0:
        avancement = None
        decaissement = None
    else:
        avance = sum((_d(p["budget_mds"]) * _d(p["avancement"]) for p in lignes), Decimal("0"))
        avancement = avance / budget
        decaissement = decaisse / budget

    def compte(statut=None, predicat=None):
        if predicat is not None:
            return sum(1 for p in lignes if predicat(p))
        return sum(1 for p in lignes if p["statut"] == statut)

    par_statut = []
    for statut in STATUTS:
        groupe = [p for p in lignes if p["statut"] == statut]
        montant = sum((_d(p["budget_mds"]) for p in groupe), Decimal("0"))
        part = (montant / budget) if budget else None
        par_statut.append(
            {"statut": statut, "nombre": len(groupe), "budget": montant, "part": part}
        )

    ordre = list(SECTEURS_CLASSEUR)
    for projet in lignes:
        if projet["secteur"] not in ordre:
            ordre.append(projet["secteur"])
    if secteur_demande and secteur_demande not in ordre:
        ordre.append(secteur_demande)

    par_secteur = []
    for secteur in ordre:
        groupe = [p for p in lignes if p["secteur"] == secteur]
        montant = sum((_d(p["budget_mds"]) for p in groupe), Decimal("0"))
        if montant == 0:
            av = None
            dec = None
        else:
            av = sum((_d(p["budget_mds"]) * _d(p["avancement"]) for p in groupe), Decimal("0")) / montant
            dec = sum((_d(p["budget_mds"]) * _d(p["decaissement"]) for p in groupe), Decimal("0")) / montant
        par_secteur.append(
            {
                "secteur": secteur,
                "nombre": len(groupe),
                "budget": montant,
                "avancement": av,
                "decaissement": dec,
            }
        )

    return {
        "nombre": len(lignes),
        "budget": budget,
        "decaisse": decaisse,
        "avancement": avancement,
        "decaissement": decaissement,
        "en_cours": compte(predicat=lambda p: p["statut"] in EN_COURS),
        "termines": compte("Terminé"),
        "retard_ou_risque": compte(predicat=lambda p: p["statut"] in ("En retard", "À risque")),
        "retard": compte("En retard"),
        "exemples": compte(predicat=lambda p: p["exemple"]),
        "par_statut": par_statut,
        "par_secteur": par_secteur,
    }


def points_attention(projets):
    lignes = [p for p in projets if p["statut"] in ("En retard", "À risque")]
    lignes.sort(key=lambda p: (0 if p["statut"] == "En retard" else 1, p["echeance"], p["code"]))
    return lignes


def jours_restants(projet, aujourd_hui):
    if projet["statut"] == "Terminé":
        return None
    return (date.fromisoformat(projet["echeance"]) - aujourd_hui).days


def budget_decaisse(projet):
    return _d(projet["budget_mds"]) * _d(projet["decaissement"])
