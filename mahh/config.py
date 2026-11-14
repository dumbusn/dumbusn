"""Chemins et port. Rien ici n'est un secret."""

import os
from pathlib import Path

RACINE_DEPOT = Path(__file__).resolve().parent.parent


def repertoire_donnees():
    brut = os.environ.get("MAHH_DATA")
    chemin = Path(brut).expanduser() if brut else RACINE_DEPOT / "data"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def repertoire_fichiers():
    chemin = repertoire_donnees() / "fichiers"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def hote():
    return os.environ.get("MAHH_HOTE", "127.0.0.1")


def port():
    return int(os.environ.get("MAHH_PORT", "8000"))
