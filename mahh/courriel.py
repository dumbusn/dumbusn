"""Envoi d’une instruction. Les secrets restent dans l’environnement, jamais dans le code."""

import os
import smtplib
from email.message import EmailMessage

from mahh.config import url_publique


def reglages():
    hote = os.environ.get("MAHH_SMTP_HOTE", "").strip()
    expediteur = os.environ.get("MAHH_SMTP_EXPEDITEUR", "").strip()
    if not hote or not expediteur:
        return None
    port_brut = os.environ.get("MAHH_SMTP_PORT", "").strip() or "587"
    try:
        port = int(port_brut)
    except ValueError:
        port = 587
    return {
        "hote": hote,
        "port": port,
        "utilisateur": os.environ.get("MAHH_SMTP_UTILISATEUR", "").strip(),
        "mot_de_passe": os.environ.get("MAHH_SMTP_MOT_DE_PASSE", ""),
        "expediteur": expediteur,
    }


def lien_instruction(identifiant):
    return f"{url_publique()}/instructions/{int(identifiant)}"


def envoyer(destinataires, sujet, corps):
    """Retourne envoye, absent, sans-adresse ou echec. N’interrompt pas l’enregistrement."""
    adresses = [adresse.strip() for adresse in destinataires if adresse and adresse.strip()]
    if not adresses:
        return "sans-adresse"
    config = reglages()
    if config is None:
        return "absent"
    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = config["expediteur"]
    message["To"] = ", ".join(adresses)
    message.set_content(corps)
    try:
        if config["port"] == 465:
            client = smtplib.SMTP_SSL(config["hote"], config["port"], timeout=20)
        else:
            client = smtplib.SMTP(config["hote"], config["port"], timeout=20)
            client.ehlo()
            client.starttls()
            client.ehlo()
        if config["utilisateur"]:
            client.login(config["utilisateur"], config["mot_de_passe"])
        client.send_message(message)
        client.quit()
    except Exception:
        return "echec"
    return "envoye"
