"""Arbre de la note et dix-huit projets d'exemple du classeur du 10 novembre 2026.

Les projets sont fictifs. Ils ne sont pas les projets du ministère.
"""

from decimal import Decimal

NON_ETABLI = (
    "Ce sigle n’est pas développé dans la note. Son développement n’est pas établi."
)

ARBRES = (
    {
        "nom": "Assainissement",
        "lecture": "Domaine écrit dans la note du 10 novembre 2026.",
        "structures": (
            {
                "nom": "DGA",
                "intitule": "",
                "lecture": NON_ETABLI,
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Document stratégique disponible",
                    "Taux d’accès à l’Assainissement",
                    "Taux de raccordement au réseau d’assainissement",
                ),
            },
            {
                "nom": "ANASP",
                "intitule": "Agence nationale d’assainissement et de la salubrité publique",
                "lecture": (
                    "Développement indiqué par le commanditaire. La note n’écrit que le sigle. "
                    "ZTT et PME ne sont pas développés dans la note."
                ),
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Nombre de ZTT",
                    "Nombre et liste de PME /zone",
                    "Nombre d’abonnée/préfecture",
                    "Taux de couverture/préfecture",
                ),
            },
        ),
    },
    {
        "nom": "Hydraulique",
        "lecture": "Domaine écrit dans la note du 10 novembre 2026.",
        "structures": (
            {
                "nom": "SEG",
                "intitule": "",
                "lecture": (
                    "Sigle conservé tel que dans la note. Le commanditaire le situe sur la "
                    "distribution d’eau en ville, par opposition au SNAPE en zone rurale."
                ),
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Nombre d’abonné",
                    "Nombre de ville couverte",
                    "La liste des villes couvertes",
                    "Taux de desserte urbain",
                    "Taux de facturation et de recouvrement",
                    "Volume d’eau produit et distribué",
                ),
            },
            {
                "nom": "DNH",
                "intitule": "",
                "lecture": NON_ETABLI,
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Document de politique disponible",
                ),
            },
            {
                "nom": "Fonds de l’Hydraulique",
                "intitule": "",
                "lecture": "Nom écrit en toutes lettres dans la note.",
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Taux de recouvrement des redevances et taxes",
                ),
            },
            {
                "nom": "SNAPE",
                "intitule": "Service national d’aménagement des points d’eau",
                "lecture": (
                    "Développement indiqué par le commanditaire. La note n’écrit que le sigle. "
                    "Le commanditaire le situe en zone rurale."
                ),
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Nombre de villages couvert",
                    "Nombre de population couverte par village",
                    "Nombre de points d’eau realisés par village",
                ),
            },
        ),
    },
    {
        "nom": "Hydrocarbures",
        "lecture": "Domaine écrit dans la note du 10 novembre 2026.",
        "structures": (
            {
                "nom": "FAPGAZ",
                "intitule": "",
                "lecture": NON_ETABLI,
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Quantité de gaz importée",
                    "Nombre de bouteille de gaz vendu/mois",
                    "Prix de gaz/Kg",
                    "Revenu annuel",
                ),
            },
            {
                "nom": "DNHc",
                "intitule": "",
                "lecture": (
                    "Ce sigle n’est pas développé dans la note. La graphie DNHc est celle de la note. "
                    "Son développement n’est pas établi."
                ),
                "libelles": (
                    "Organigramme",
                    "Attribution",
                    "Document de politique",
                ),
            },
        ),
    },
    {
        "nom": "Administration",
        "lecture": "Domaine écrit dans la note du 10 novembre 2026.",
        "structures": (
            {
                "nom": "BSD",
                "intitule": "Bureau de stratégie et de développement",
                "lecture": "Développement indiqué par le commanditaire. La note n’écrit que le sigle.",
                "libelles": (
                    "Nombre de Projet en cours",
                    "Nombre de projet terminé",
                    "Projet par secteur",
                    "Montant du Projet",
                    "Mode de financement",
                    "Zone du Projet",
                ),
            },
            {
                "nom": "PRMP",
                "intitule": "",
                "lecture": (
                    "Ce sigle n’est pas développé dans la note. Son développement n’est pas établi. "
                    "Les libellés Assainissement, Hydraulique, Hydrocarbures et Autres sont au même "
                    "niveau que le nombre de contrats. La note ne dit pas s’ils le ventilent."
                ),
                "libelles": (
                    "Nombre de Contrat signés",
                    "Assainissement",
                    "Hydraulique",
                    "Hydrocarbures",
                    "Autres",
                ),
            },
        ),
    },
)

# code, secteur, titre, localisation, statut, budget, décaissement %, avancement %,
# début, échéance, responsable, financement, jalon, observations.
# Pourcentages et montants : ceux du classeur d'exemple.
_LIGNES = (
    (
        "ASS-01", "Assainissement",
        "Réhabilitation du réseau de drainage des eaux pluviales",
        "Conakry (Matoto, Ratoma)", "Dans les délais", 420, 58, 62,
        "2025-03-01", "2027-02-28",
        "Direction nationale de l'Assainissement",
        "Budget national et partenaires",
        "Livraison du collecteur secondaire, tronçon 3",
        "Travaux conformes au calendrier. Saison des pluies suivie de près.",
    ),
    (
        "ASS-02", "Assainissement",
        "Station de traitement des boues de vidange",
        "Conakry", "En retard", 310, 40, 35,
        "2025-06-01", "2026-12-15",
        "Direction nationale de l'Assainissement",
        "Partenaire technique et financier",
        "Montage des bassins de décantation",
        "Retard de livraison des équipements importés. Nouvelle date à valider avec l'entreprise.",
    ),
    (
        "ASS-03", "Assainissement",
        "Blocs sanitaires publics dans les marchés",
        "Kindia, Mamou, Labé", "Terminé", 95, 100, 100,
        "2025-01-15", "2026-09-30",
        "Direction régionale de l'Assainissement",
        "Budget national",
        "Réception définitive prononcée",
        "Ouvrages remis aux communes. Suivi de la maintenance à organiser.",
    ),
    (
        "ASS-04", "Assainissement",
        "Collecte et gestion des déchets solides",
        "Kankan", "Dans les délais", 150, 45, 48,
        "2025-09-01", "2027-06-30",
        "Direction régionale de l'Assainissement",
        "Partenaire technique et financier",
        "Mise en service du centre de transfert",
        "Acquisition des bacs et camions réalisée.",
    ),
    (
        "ASS-05", "Assainissement",
        "Curage des canaux d'évacuation avant la saison des pluies",
        "Conakry", "Terminé", 60, 97, 100,
        "2026-02-01", "2026-06-30",
        "Direction nationale de l'Assainissement",
        "Budget national",
        "Rapport de fin de campagne",
        "Campagne terminée avant les premières fortes pluies.",
    ),
    (
        "ASS-06", "Assainissement",
        "Assainissement autonome en zones rurales",
        "N'Zérékoré, Faranah", "À risque", 120, 30, 22,
        "2026-02-01", "2027-09-30",
        "Direction régionale de l'Assainissement",
        "Partenaire technique et financier",
        "Sensibilisation des 40 villages restants",
        "Accès difficile en saison des pluies. Rythme d'exécution à renforcer.",
    ),
    (
        "HYD-01", "Hydraulique",
        "Extension du réseau d'adduction d'eau potable",
        "Conakry-Est", "Dans les délais", 680, 66, 71,
        "2024-11-01", "2026-12-31",
        "Direction nationale de l'Hydraulique",
        "Partenaire technique et financier",
        "Raccordement de 6 000 ménages",
        "Exécution soutenue, clôture prévue à la date contractuelle.",
    ),
    (
        "HYD-02", "Hydraulique",
        "Forages équipés de pompes à motricité humaine",
        "Boké, Télimélé", "À risque", 140, 52, 55,
        "2025-04-01", "2026-11-30",
        "Direction nationale de l'Hydraulique",
        "Budget national",
        "Réalisation des 25 derniers forages",
        "Échéance proche, 11 forages restent à équiper.",
    ),
    (
        "HYD-03", "Hydraulique",
        "Réhabilitation du barrage et de l'usine de production d'eau",
        "Kindia", "En retard", 520, 25, 18,
        "2025-10-01", "2027-12-31",
        "Direction nationale de l'Hydraulique",
        "Partenaire technique et financier",
        "Fin des travaux de génie civil du barrage",
        "Démarrage tardif des travaux. Plan de rattrapage demandé à l'entreprise.",
    ),
    (
        "HYD-04", "Hydraulique",
        "Adduction d'eau potable des centres urbains",
        "Labé, Pita", "Dans les délais", 380, 41, 44,
        "2025-05-01", "2027-03-31",
        "Direction régionale de l'Hydraulique",
        "Partenaire technique et financier",
        "Pose de la conduite principale Labé-Pita",
        "Avancement régulier.",
    ),
    (
        "HYD-05", "Hydraulique",
        "Études de gestion intégrée des ressources en eau",
        "Faranah", "Dans les délais", 85, 10, 12,
        "2026-03-01", "2027-10-31",
        "Direction nationale de l'Hydraulique",
        "Budget national",
        "Remise du diagnostic des bassins versants",
        "Phase de collecte de données en cours.",
    ),
    (
        "HYD-06", "Hydraulique",
        "Château d'eau et réservoirs de stockage",
        "Mamou", "En préparation", 210, 0, 0,
        "2027-01-15", "2028-06-30",
        "Direction régionale de l'Hydraulique",
        "Partenaire technique et financier",
        "Lancement de l'appel d'offres",
        "Dossier d'appel d'offres en cours de validation.",
    ),
    (
        "HYC-01", "Hydrocarbures",
        "Extension du dépôt de stockage de produits pétroliers",
        "Conakry (Kaloum)", "Dans les délais", 750, 63, 58,
        "2025-02-01", "2027-03-31",
        "Direction nationale des Hydrocarbures",
        "Partenaire technique et financier",
        "Montage du bac de stockage n°3",
        "Conforme au planning, contrôles de sécurité réalisés.",
    ),
    (
        "HYC-02", "Hydrocarbures",
        "Laboratoire d'analyse de la qualité des carburants",
        "Conakry", "Terminé", 90, 100, 100,
        "2025-07-01", "2026-06-30",
        "Direction nationale des Hydrocarbures",
        "Budget national",
        "Accréditation du laboratoire",
        "Laboratoire opérationnel, équipe formée.",
    ),
    (
        "HYC-03", "Hydrocarbures",
        "Réhabilitation des stations-service publiques",
        "Kankan, N'Zérékoré", "En retard", 230, 28, 33,
        "2025-08-01", "2026-10-15",
        "Direction nationale des Hydrocarbures",
        "Budget national",
        "Réception des 4 stations restantes",
        "Échéance dépassée. Avenant de prolongation à instruire.",
    ),
    (
        "HYC-04", "Hydrocarbures",
        "Système d'information de suivi de la production et de la fiscalité",
        "Conakry", "À risque", 65, 35, 40,
        "2026-01-15", "2027-01-31",
        "Cellule informatique et statistiques",
        "Partenaire technique et financier",
        "Recette de la plateforme de déclaration",
        "Interconnexion avec les services fiscaux non finalisée.",
    ),
    (
        "HYC-05", "Hydrocarbures",
        "Étude de faisabilité d'un réseau de distribution intérieure",
        "National", "Suspendu", 110, 12, 8,
        "2026-05-01", "2027-08-31",
        "Direction nationale des Hydrocarbures",
        "Partenaire technique et financier",
        "Reprise sous réserve de l'accord du financeur",
        "Suspendu dans l'attente d'une décision sur le périmètre de l'étude.",
    ),
    (
        "HYC-06", "Hydrocarbures",
        "Extension du réseau de distribution de gaz domestique",
        "Boké", "En préparation", 175, 0, 0,
        "2027-03-01", "2028-09-30",
        "Direction nationale des Hydrocarbures",
        "Budget national",
        "Validation du cahier des charges",
        "Phase de programmation.",
    ),
)


def _fraction(pourcent):
    return format(Decimal(pourcent) / Decimal(100), "f")


def projets_exemples():
    projets = []
    for ligne in _LIGNES:
        (
            code, secteur, titre, localisation, statut, budget, dec, avancement,
            debut, echeance, responsable, financement, jalon, observations,
        ) = ligne
        projets.append(
            {
                "code": code,
                "secteur": secteur,
                "titre": titre,
                "localisation": localisation,
                "statut": statut,
                "budget_mds": str(budget),
                "decaissement": _fraction(dec),
                "avancement": _fraction(avancement),
                "debut": debut,
                "echeance": echeance,
                "responsable": responsable,
                "financement": financement,
                "jalon": jalon,
                "observations": observations,
                "exemple": 1,
            }
        )
    return projets
