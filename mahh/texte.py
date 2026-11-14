"""Mise en forme française et échappement HTML."""

import html
from decimal import Decimal, ROUND_HALF_UP

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def echapper(valeur):
    return html.escape("" if valeur is None else str(valeur), quote=True)


def fmt_date(iso):
    if not iso:
        return "—"
    annee, mois, jour = (int(partie) for partie in str(iso).split("-"))
    nom = MOIS[mois - 1]
    if jour == 1:
        return f"1er {nom} {annee}"
    return f"{jour} {nom} {annee}"


def _decimal(valeur):
    return Decimal(str(valeur))


def fmt_nombre(valeur):
    if valeur is None:
        return "—"
    nombre = _decimal(valeur).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    signe = "-" if nombre < 0 else ""
    nombre = abs(nombre)
    entier = int(nombre)
    centimes = int((nombre - Decimal(entier)) * 100)
    groupes = f"{entier:,}".replace(",", " ")
    if centimes == 0:
        return signe + groupes
    if centimes % 10 == 0:
        return f"{signe}{groupes},{centimes // 10}"
    return f"{signe}{groupes},{centimes:02d}"


def fmt_pourcent(fraction):
    if fraction is None:
        return "—"
    nombre = (_decimal(fraction) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if nombre == nombre.to_integral():
        texte = str(int(nombre))
    else:
        texte = f"{nombre:.1f}".replace(".", ",")
    return texte + "\u00a0%"


def attribut_decimal(valeur):
    if valeur is None:
        return ""
    nombre = _decimal(valeur).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(nombre, "f")


def attribut_pourcent(fraction):
    if fraction is None:
        return ""
    nombre = (_decimal(fraction) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{nombre:.1f}"


def pourcent_saisi(fraction):
    """Valeur à remettre dans un champ, avec une virgule."""
    nombre = (_decimal(fraction) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texte = format(nombre, "f").rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def classe_barre(part):
    if part is None or part <= 0:
        return "b-0"
    nombre = int((_decimal(part) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    nombre = max(0, min(100, nombre))
    cran = int((Decimal(nombre) / 5).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 5
    cran = max(0, min(100, cran))
    return f"b-{cran}"
