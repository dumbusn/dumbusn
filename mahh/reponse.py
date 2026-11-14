"""Réponses et exceptions du parcours HTTP."""


class Html:
    def __init__(self, corps, statut=200):
        self.corps = corps
        self.statut = statut


class Redirection:
    def __init__(self, url):
        self.url = url


class Octets:
    def __init__(self, contenu, type_mime, statut=200, disposition=None):
        self.contenu = contenu
        self.type_mime = type_mime
        self.statut = statut
        self.disposition = disposition


class NonConnecte(Exception):
    def __init__(self, chemin):
        self.chemin = chemin


class Interdit(Exception):
    def __init__(self, message):
        self.message = message


class ValeurRefusee(Exception):
    def __init__(self, message):
        self.message = message
