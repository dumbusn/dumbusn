"""Contrôles des saisies. Les messages sont les nôtres, pas le texte brut de l'utilisateur."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from mahh.calculs import SECTEURS, STATUTS
from mahh.reponse import ValeurRefusee
from mahh.securite import mot_de_passe_acceptable

IDENTIFIANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,39}")
CODE_PROJET = re.compile(r"[A-Z0-9][A-Z0-9-]{1,19}")


def ligne(valeur, minimum, maximum, libelle):
    texte = "" if valeur is None else str(valeur).strip()
    if len(texte) < minimum or len(texte) > maximum:
        raise ValeurRefusee(
            f"Le champ « {libelle} » doit contenir entre {minimum} et {maximum} caractères."
        )
    if any(ord(caractere) < 32 for caractere in texte):
        raise ValeurRefusee(f"Le champ « {libelle} » contient un caractère refusé.")
    return texte


def bloc(valeur, minimum, maximum, libelle):
    texte = "" if valeur is None else str(valeur).replace("\r\n", "\n").strip()
    if len(texte) < minimum or len(texte) > maximum:
        raise ValeurRefusee(
            f"Le champ « {libelle} » doit contenir entre {minimum} et {maximum} caractères."
        )
    if any(ord(caractere) < 32 and caractere != "\n" for caractere in texte):
        raise ValeurRefusee(f"Le champ « {libelle} » contient un caractère refusé.")
    return texte


def identifiant(valeur):
    texte = "" if valeur is None else str(valeur).strip()
    if IDENTIFIANT.fullmatch(texte) is None:
        raise ValeurRefusee(
            "L’identifiant doit faire 3 à 40 caractères : lettres, chiffres, point, tiret."
        )
    return texte


def mot_de_passe(valeur):
    if not mot_de_passe_acceptable(valeur):
        raise ValeurRefusee("Le mot de passe doit contenir entre 10 et 200 caractères.")
    return valeur


def nom_noeud(valeur):
    return ligne(valeur, 1, 120, "Nom")


def _decimal(valeur, libelle):
    texte = (
        ""
        if valeur is None
        else str(valeur).strip().replace("\u202f", "").replace("\u00a0", "").replace(" ", "")
    )
    texte = texte.replace("%", "").replace(",", ".")
    if texte.count(".") > 1 or texte in ("", ".", "-", "-."):
        raise ValeurRefusee(f"Le champ « {libelle} » doit être un nombre.")
    try:
        return Decimal(texte)
    except InvalidOperation as exc:
        raise ValeurRefusee(f"Le champ « {libelle} » doit être un nombre.") from exc


def budget(valeur):
    nombre = _decimal(valeur, "Budget")
    if nombre < 0 or nombre > Decimal("1000000000"):
        raise ValeurRefusee("Le budget doit être un nombre positif, en milliards de francs guinéens.")
    return format(nombre.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def pourcent(valeur, libelle):
    nombre = _decimal(valeur, libelle)
    if nombre < 0 or nombre > 100:
        raise ValeurRefusee(f"Le champ « {libelle} » doit être entre 0 et 100.")
    nombre = nombre.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    fraction = (nombre / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(fraction, "f")


def date_iso(valeur, libelle):
    texte = "" if valeur is None else str(valeur).strip()
    try:
        return date.fromisoformat(texte).isoformat()
    except ValueError as exc:
        raise ValeurRefusee(f"La date « {libelle} » est invalide.") from exc


def projet(formulaire):
    code = "" if formulaire.get("code") is None else str(formulaire.get("code")).strip().upper()
    if CODE_PROJET.fullmatch(code) is None:
        raise ValeurRefusee(
            "L’identifiant du projet doit faire 2 à 20 caractères : lettres, chiffres et tiret."
        )
    secteur = formulaire.get("secteur", "")
    if secteur not in SECTEURS:
        raise ValeurRefusee("Le secteur n’est pas reconnu.")
    statut = formulaire.get("statut", "")
    if statut not in STATUTS:
        raise ValeurRefusee("Le statut n’est pas reconnu.")
    debut = date_iso(formulaire.get("debut"), "Début")
    echeance = date_iso(formulaire.get("echeance"), "Échéance")
    if echeance < debut:
        raise ValeurRefusee("L’échéance est antérieure au début.")
    return {
        "code": code,
        "secteur": secteur,
        "titre": ligne(formulaire.get("titre"), 3, 300, "Projet"),
        "localisation": ligne(formulaire.get("localisation"), 2, 200, "Localisation"),
        "statut": statut,
        "budget_mds": budget(formulaire.get("budget")),
        "decaissement": pourcent(formulaire.get("decaissement"), "Décaissement"),
        "avancement": pourcent(formulaire.get("avancement"), "Avancement physique"),
        "debut": debut,
        "echeance": echeance,
        "responsable": ligne(formulaire.get("responsable"), 2, 200, "Direction responsable"),
        "financement": ligne(formulaire.get("financement"), 2, 200, "Source de financement"),
        "jalon": ligne(formulaire.get("jalon"), 2, 300, "Prochain jalon"),
        "observations": bloc(formulaire.get("observations"), 2, 2000, "Observations"),
    }
