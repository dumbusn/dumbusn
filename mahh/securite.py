"""Mots de passe, session, cookies. Aucun secret n'est écrit dans le dépôt."""

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from mahh.config import repertoire_donnees

ITERATIONS = 200_000
DUREE_SESSION = 12 * 60 * 60
_FACTICE = None


def maintenant():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mot_de_passe_acceptable(mot):
    return isinstance(mot, str) and 10 <= len(mot) <= 200


def hasher(mot):
    sel = secrets.token_bytes(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", mot.encode("utf-8"), sel, ITERATIONS)
    return f"{ITERATIONS}${sel.hex()}${empreinte.hex()}"


def _factice():
    global _FACTICE
    if _FACTICE is None:
        _FACTICE = hasher("socle-factice-ne-sert-pas-a-ouvrir")
    return _FACTICE


def verifier(mot, stocke):
    if not isinstance(mot, str) or len(mot) > 200 or not stocke or stocke.count("$") != 2:
        verifier("x" * 16, _factice())
        return False
    iterations, sel, empreinte = stocke.split("$")
    try:
        calcule = hashlib.pbkdf2_hmac(
            "sha256",
            mot.encode("utf-8"),
            bytes.fromhex(sel),
            int(iterations),
        )
    except ValueError:
        return False
    return hmac.compare_digest(calcule.hex(), empreinte)


def verifier_ou_factice(mot, stocke):
    if not stocke:
        verifier(mot if isinstance(mot, str) else "", _factice())
        return False
    return verifier(mot, stocke)


def ouvrir_session(conn, utilisateur_id):
    jeton = secrets.token_urlsafe(32)
    empreinte = hashlib.sha256(jeton.encode("utf-8")).hexdigest()
    expire = (datetime.now(timezone.utc) + timedelta(seconds=DUREE_SESSION)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    conn.execute(
        "INSERT INTO session (empreinte, utilisateur_id, expire_le) VALUES (?, ?, ?)",
        (empreinte, utilisateur_id, expire),
    )
    conn.execute("DELETE FROM session WHERE expire_le <= ?", (maintenant(),))
    return jeton


def fermer_sessions(conn, utilisateur_id):
    conn.execute("DELETE FROM session WHERE utilisateur_id = ?", (utilisateur_id,))


def utilisateur_par_jeton(conn, jeton):
    if not jeton:
        return None
    empreinte = hashlib.sha256(jeton.encode("utf-8")).hexdigest()
    ligne = conn.execute(
        """
        SELECT u.* FROM session s
        JOIN utilisateur u ON u.id = s.utilisateur_id
        WHERE s.empreinte = ? AND s.expire_le > ? AND u.actif = 1
        """,
        (empreinte, maintenant()),
    ).fetchone()
    return _avec_role_entite(conn, ligne)


def _avec_role_entite(conn, ligne):
    """Le rôle de l’entité s’ajoute aux rôles du compte pour l’accès aux écrans."""
    if ligne is None:
        return None
    personne = dict(ligne)
    roles = set()
    if personne.get("fonction"):
        roles.add(personne["fonction"])
    roles.update((personne.get("roles") or "").split())
    if personne.get("organigramme_id"):
        poste = conn.execute(
            "SELECT niveau FROM organigramme WHERE id = ?",
            (personne["organigramme_id"],),
        ).fetchone()
        if poste and poste["niveau"]:
            roles.add(poste["niveau"])
            if not personne["fonction"]:
                personne["fonction"] = poste["niveau"]
    personne["roles"] = " ".join(role for role in roles if role)
    return personne


def cookie_jeton(valeur):
    return f"mahh_jeton={valeur}; Path=/; HttpOnly; SameSite=Lax; Max-Age={DUREE_SESSION}"


def cookie_session(valeur):
    return f"mahh_session={valeur}; Path=/; HttpOnly; SameSite=Lax; Max-Age={DUREE_SESSION}"


def cookie_session_vide():
    return "mahh_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def jeton_valide(cookie, formulaire):
    if not cookie or not formulaire:
        return False
    if len(cookie) != len(formulaire):
        return False
    return hmac.compare_digest(cookie, formulaire)


def nouveau_jeton():
    return secrets.token_hex(32)


def jeton_cookie_acceptable(valeur):
    return isinstance(valeur, str) and re.fullmatch(r"[a-f0-9]{64}", valeur) is not None


def url_sure(suivant):
    if not suivant or not isinstance(suivant, str):
        return "/"
    if not suivant.startswith("/") or suivant.startswith("//") or suivant.startswith("/\\"):
        return "/"
    if "\\" in suivant or "\r" in suivant or "\n" in suivant:
        return "/"
    return suivant


def preparer_mot_admin():
    """Retourne (mot, genere). Le mot n'est pas lu dans un fichier du dépôt."""
    mot = os.environ.get("MAHH_ADMIN_MOT_DE_PASSE")
    if mot is None or mot == "":
        return secrets.token_urlsafe(18), True
    if not mot_de_passe_acceptable(mot):
        raise SystemExit(
            "MAHH_ADMIN_MOT_DE_PASSE doit contenir entre 10 et 200 caractères."
        )
    return mot, False


def ecrire_mot_initial(identifiant, mot):
    chemin = repertoire_donnees() / "mot-de-passe-initial.txt"
    chemin.write_text(
        f"Identifiant : {identifiant}\n"
        f"Mot de passe : {mot}\n"
        "Créé au premier lancement. Changez-le dans Compte, puis supprimez ce fichier.\n",
        encoding="utf-8",
    )
    os.chmod(chemin, 0o600)
    return chemin
