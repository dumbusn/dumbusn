"""SQLite : schéma, connexion, premier remplissage."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date

from mahh.config import repertoire_donnees
from mahh.securite import ecrire_mot_initial, hasher, maintenant, preparer_mot_admin
from mahh.seed import ARBRES, projets_exemples
from mahh.validation import identifiant as valider_identifiant

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateur (
    id INTEGER PRIMARY KEY,
    identifiant TEXT NOT NULL UNIQUE,
    nom TEXT NOT NULL,
    mot_de_passe TEXT NOT NULL,
    administrateur INTEGER NOT NULL DEFAULT 0,
    fonction TEXT NOT NULL DEFAULT '',
    structure_id INTEGER,
    actif INTEGER NOT NULL DEFAULT 1,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session (
    empreinte TEXT PRIMARY KEY,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    expire_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groupe (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    consulter_bsd INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appartenance (
    groupe_id INTEGER NOT NULL REFERENCES groupe(id) ON DELETE CASCADE,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    PRIMARY KEY (groupe_id, utilisateur_id)
);

CREATE TABLE IF NOT EXISTS noeud (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES noeud(id) ON DELETE CASCADE,
    genre TEXT NOT NULL CHECK (genre IN ('domaine', 'structure', 'dossier', 'fichier')),
    nom TEXT NOT NULL,
    intitule TEXT NOT NULL DEFAULT '',
    lecture TEXT NOT NULL DEFAULT '',
    systeme INTEGER NOT NULL DEFAULT 0,
    ordre INTEGER NOT NULL DEFAULT 0,
    nom_stockage TEXT,
    taille INTEGER,
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS libelle (
    id INTEGER PRIMARY KEY,
    noeud_id INTEGER NOT NULL REFERENCES noeud(id) ON DELETE CASCADE,
    texte TEXT NOT NULL,
    ordre INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS droit (
    id INTEGER PRIMARY KEY,
    groupe_id INTEGER NOT NULL REFERENCES groupe(id) ON DELETE CASCADE,
    noeud_id INTEGER NOT NULL REFERENCES noeud(id) ON DELETE CASCADE,
    creer INTEGER NOT NULL DEFAULT 0,
    consulter INTEGER NOT NULL DEFAULT 0,
    modifier INTEGER NOT NULL DEFAULT 0,
    supprimer INTEGER NOT NULL DEFAULT 0,
    UNIQUE (groupe_id, noeud_id)
);

CREATE TABLE IF NOT EXISTS projet (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    secteur TEXT NOT NULL,
    titre TEXT NOT NULL,
    localisation TEXT NOT NULL,
    statut TEXT NOT NULL,
    budget_mds TEXT NOT NULL,
    decaissement TEXT NOT NULL,
    avancement TEXT NOT NULL,
    debut TEXT NOT NULL,
    echeance TEXT NOT NULL,
    responsable TEXT NOT NULL,
    financement TEXT NOT NULL,
    jalon TEXT NOT NULL,
    observations TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0,
    structure_id INTEGER REFERENCES noeud(id),
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS piece (
    id INTEGER PRIMARY KEY,
    projet_id INTEGER NOT NULL REFERENCES projet(id) ON DELETE CASCADE,
    genre TEXT NOT NULL CHECK (genre IN ('note', 'rapport', 'physique')),
    titre TEXT NOT NULL,
    texte TEXT NOT NULL DEFAULT '',
    cote TEXT NOT NULL DEFAULT '',
    emplacement TEXT NOT NULL DEFAULT '',
    nom_stockage TEXT,
    nom_fichier TEXT,
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruction (
    id INTEGER PRIMARY KEY,
    echelon TEXT NOT NULL CHECK (echelon IN ('ministre', 'chef_cabinet', 'secretaire_general')),
    structure_id INTEGER REFERENCES noeud(id),
    texte TEXT NOT NULL,
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sommation (
    id INTEGER PRIMARY KEY,
    structure_id INTEGER NOT NULL REFERENCES noeud(id),
    projet_id INTEGER REFERENCES projet(id) ON DELETE SET NULL,
    texte TEXT NOT NULL,
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS maille (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES maille(id),
    genre TEXT NOT NULL CHECK (genre IN ('region', 'prefecture', 'sous_prefecture', 'quartier', 'secteur')),
    nom TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pme (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    gestion TEXT NOT NULL CHECK (gestion IN ('commune', 'gouvernorat')),
    contact TEXT NOT NULL,
    jour_collecte TEXT NOT NULL,
    heure_collecte TEXT NOT NULL,
    frais_hors_jour TEXT NOT NULL DEFAULT '0',
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pme_secteur (
    pme_id INTEGER NOT NULL REFERENCES pme(id) ON DELETE CASCADE,
    secteur_id INTEGER NOT NULL REFERENCES maille(id),
    PRIMARY KEY (pme_id, secteur_id)
);

CREATE TABLE IF NOT EXISTS effectif (
    id INTEGER PRIMARY KEY,
    pme_id INTEGER NOT NULL REFERENCES pme(id) ON DELETE CASCADE,
    jour TEXT NOT NULL,
    nombre INTEGER NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trajet (
    id INTEGER PRIMARY KEY,
    pme_id INTEGER NOT NULL REFERENCES pme(id) ON DELETE CASCADE,
    jour TEXT NOT NULL,
    libelle TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS point_collecte (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    secteur_id INTEGER REFERENCES maille(id),
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS abonnement (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    nom TEXT NOT NULL,
    telephone TEXT NOT NULL,
    secteur_id INTEGER NOT NULL REFERENCES maille(id),
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    pme_id INTEGER REFERENCES pme(id),
    montant_gnf TEXT NOT NULL,
    paye INTEGER NOT NULL DEFAULT 0,
    exemple INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS passage (
    id INTEGER PRIMARY KEY,
    abonnement_id INTEGER NOT NULL REFERENCES abonnement(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    jour TEXT NOT NULL,
    heure TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signalement (
    id INTEGER PRIMARY KEY,
    abonnement_id INTEGER NOT NULL REFERENCES abonnement(id) ON DELETE CASCADE,
    jour TEXT NOT NULL,
    hors_jour INTEGER NOT NULL,
    frais_gnf TEXT NOT NULL DEFAULT '0',
    exemple INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eau_lieu (
    id INTEGER PRIMARY KEY,
    reseau TEXT NOT NULL CHECK (reseau IN ('seg', 'snape')),
    nom TEXT NOT NULL,
    population INTEGER NOT NULL DEFAULT 0,
    population_couverte INTEGER NOT NULL DEFAULT 0,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eau_site (
    id INTEGER PRIMARY KEY,
    lieu_id INTEGER NOT NULL REFERENCES eau_lieu(id),
    nom TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eau_situation (
    id INTEGER PRIMARY KEY,
    reseau TEXT NOT NULL CHECK (reseau IN ('seg')),
    volume_produit TEXT NOT NULL,
    volume_distribue TEXT NOT NULL,
    montant_du TEXT NOT NULL,
    montant_facture TEXT NOT NULL,
    montant_recouvre TEXT NOT NULL,
    exemple INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS eau_demande (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    reseau TEXT NOT NULL CHECK (reseau IN ('seg', 'snape')),
    lieu_id INTEGER NOT NULL REFERENCES eau_lieu(id),
    nom TEXT NOT NULL,
    telephone TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    etat TEXT NOT NULL CHECK (etat IN ('recue', 'abonne')),
    exemple INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eau_abonnement (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    demande_id INTEGER REFERENCES eau_demande(id),
    reseau TEXT NOT NULL CHECK (reseau IN ('seg', 'snape')),
    lieu_id INTEGER NOT NULL REFERENCES eau_lieu(id),
    nom TEXT NOT NULL,
    telephone TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    paye INTEGER NOT NULL DEFAULT 0,
    exemple INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_noeud_parent ON noeud(parent_id);
CREATE INDEX IF NOT EXISTS idx_session_utilisateur ON session(utilisateur_id);
"""


def connecter():
    chemin = repertoire_donnees() / "mahh.sqlite"
    conn = sqlite3.connect(chemin, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def base():
    conn = connecter()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _inserer_noeud(conn, parent_id, genre, nom, intitule, lecture, ordre, quand):
    curseur = conn.execute(
        """
        INSERT INTO noeud (
            parent_id, genre, nom, intitule, lecture, systeme, ordre, cree_le, modifie_le
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (parent_id, genre, nom, intitule, lecture, ordre, quand, quand),
    )
    return curseur.lastrowid


def semer(conn):
    if conn.execute("SELECT COUNT(*) AS n FROM utilisateur").fetchone()["n"]:
        return None
    quand = maintenant()
    for index_domaine, domaine in enumerate(ARBRES):
        domaine_id = _inserer_noeud(
            conn, None, "domaine", domaine["nom"], "", domaine["lecture"], index_domaine, quand
        )
        for index_structure, structure in enumerate(domaine["structures"]):
            structure_id = _inserer_noeud(
                conn,
                domaine_id,
                "structure",
                structure["nom"],
                structure["intitule"],
                structure["lecture"],
                index_structure,
                quand,
            )
            for index_libelle, texte in enumerate(structure["libelles"]):
                conn.execute(
                    "INSERT INTO libelle (noeud_id, texte, ordre) VALUES (?, ?, ?)",
                    (structure_id, texte, index_libelle),
                )
    for projet in projets_exemples():
        conn.execute(
            """
            INSERT INTO projet (
                code, secteur, titre, localisation, statut, budget_mds, decaissement,
                avancement, debut, echeance, responsable, financement, jalon,
                observations, exemple, cree_le, modifie_le
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                projet["code"], projet["secteur"], projet["titre"], projet["localisation"],
                projet["statut"], projet["budget_mds"], projet["decaissement"],
                projet["avancement"], projet["debut"], projet["echeance"],
                projet["responsable"], projet["financement"], projet["jalon"],
                projet["observations"], quand, quand,
            ),
        )
    brut = os.environ.get("MAHH_ADMIN_IDENTIFIANT", "admin")
    nom_admin = valider_identifiant(brut)
    mot, genere = preparer_mot_admin()
    conn.execute(
        """
        INSERT INTO utilisateur (identifiant, nom, mot_de_passe, administrateur, actif, cree_le)
        VALUES (?, ?, ?, 1, 1, ?)
        """,
        (nom_admin, "Administrateur", hasher(mot), quand),
    )
    fichier = ecrire_mot_initial(nom_admin, mot) if genere else None
    return {
        "identifiant": nom_admin,
        "mot": mot if genere else None,
        "fichier": str(fichier) if fichier else None,
    }


def semer_ordures(conn):
    if conn.execute("SELECT COUNT(*) AS n FROM maille").fetchone()["n"]:
        return
    def ajouter(parent, genre, nom):
        curseur = conn.execute(
            "INSERT INTO maille (parent_id, genre, nom, exemple) VALUES (?, ?, ?, 1)",
            (parent, genre, nom),
        )
        return curseur.lastrowid

    region = ajouter(None, "region", "Région exemple")
    prefecture = ajouter(region, "prefecture", "Préfecture exemple")
    commune = ajouter(prefecture, "sous_prefecture", "Commune exemple")
    nord = ajouter(commune, "quartier", "Quartier Nord")
    sud = ajouter(commune, "quartier", "Quartier Sud")
    secteur_a = ajouter(nord, "secteur", "Secteur A")
    secteur_b = ajouter(sud, "secteur", "Secteur B")
    secteur_c = ajouter(sud, "secteur", "Secteur C")

    def creer_pme(nom, gestion, contact, jour, heure, frais, secteurs):
        curseur = conn.execute(
            """
            INSERT INTO pme (
                nom, gestion, contact, jour_collecte, heure_collecte, frais_hors_jour, exemple
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (nom, gestion, contact, jour, heure, frais),
        )
        pme_id = curseur.lastrowid
        for secteur in secteurs:
            conn.execute(
                "INSERT INTO pme_secteur (pme_id, secteur_id) VALUES (?, ?)",
                (pme_id, secteur),
            )
        return pme_id

    alpha = creer_pme(
        "PME Alpha", "commune", "620 00 00 01", "mardi", "7 h 00 – 9 h 00", "15000",
        (secteur_a, secteur_b),
    )
    beta = creer_pme(
        "PME Bêta", "gouvernorat", "620 00 00 02", "jeudi", "8 h 00 – 10 h 00", "20000",
        (secteur_c,),
    )
    aujourd_hui = date.today().isoformat()
    conn.execute(
        "INSERT INTO effectif (pme_id, jour, nombre, exemple) VALUES (?, ?, 6, 1)",
        (alpha, aujourd_hui),
    )
    conn.execute(
        "INSERT INTO effectif (pme_id, jour, nombre, exemple) VALUES (?, ?, 4, 1)",
        (beta, aujourd_hui),
    )
    conn.execute(
        "INSERT INTO trajet (pme_id, jour, libelle, exemple) VALUES (?, ?, ?, 1)",
        (alpha, aujourd_hui, "Secteur A, puis Secteur B"),
    )
    conn.execute(
        "INSERT INTO trajet (pme_id, jour, libelle, exemple) VALUES (?, ?, ?, 1)",
        (beta, aujourd_hui, "Secteur C, aller et retour"),
    )
    conn.execute(
        """
        INSERT INTO point_collecte (nom, latitude, longitude, secteur_id, exemple)
        VALUES (?, ?, ?, ?, 1)
        """,
        ("Point ANASP Nord", "9.641200", "-13.578400", secteur_a),
    )
    conn.execute(
        """
        INSERT INTO point_collecte (nom, latitude, longitude, secteur_id, exemple)
        VALUES (?, ?, ?, ?, 1)
        """,
        ("Point ANASP Sud", "9.632100", "-13.590200", secteur_c),
    )
    quand = maintenant()
    awa = conn.execute(
        """
        INSERT INTO abonnement (
            reference, nom, telephone, secteur_id, latitude, longitude, pme_id,
            montant_gnf, paye, exemple, cree_le
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
        """,
        ("ORD-EX-01", "Awa Camara", "621 00 00 11", secteur_a, "9.641110", "-13.578310", alpha, "50000", quand),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO abonnement (
            reference, nom, telephone, secteur_id, latitude, longitude, pme_id,
            montant_gnf, paye, exemple, cree_le
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
        """,
        ("ORD-EX-02", "Moussa Barry", "621 00 00 12", secteur_c, "9.632050", "-13.590150", beta, "50000", quand),
    )
    conn.execute(
        """
        INSERT INTO passage (abonnement_id, agent, latitude, longitude, jour, heure, exemple)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (awa, "Aïssatou Bah", "9.641150", "-13.578330", aujourd_hui, "7 h 20"),
    )
    conn.execute(
        """
        INSERT INTO signalement (abonnement_id, jour, hors_jour, frais_gnf, exemple, cree_le)
        VALUES (?, ?, 1, ?, 1, ?)
        """,
        (awa, aujourd_hui, "15000", quand),
    )


def semer_eau(conn):
    if conn.execute("SELECT COUNT(*) AS n FROM eau_lieu").fetchone()["n"]:
        return

    def lieu(reseau, nom, population, couverte):
        curseur = conn.execute(
            """
            INSERT INTO eau_lieu (reseau, nom, population, population_couverte, exemple)
            VALUES (?, ?, ?, ?, 1)
            """,
            (reseau, nom, population, couverte),
        )
        return curseur.lastrowid

    alpha = lieu("seg", "Ville Alpha", 10, 6)
    beta = lieu("seg", "Ville Bêta", 5, 2)
    nord = lieu("snape", "Village Nord", 400, 250)
    sud = lieu("snape", "Village Sud", 200, 80)

    def site(lieu_id, nom, latitude, longitude):
        conn.execute(
            """
            INSERT INTO eau_site (lieu_id, nom, latitude, longitude, exemple)
            VALUES (?, ?, ?, ?, 1)
            """,
            (lieu_id, nom, latitude, longitude),
        )

    site(alpha, "Site Alpha 1", "9.650100", "-13.570100")
    site(alpha, "Site Alpha 2", "9.651200", "-13.571200")
    site(beta, "Site Bêta 1", "9.660300", "-13.580300")
    site(nord, "Forage Nord 1", "10.100100", "-13.200100")
    site(nord, "Forage Nord 2", "10.101200", "-13.201200")
    site(sud, "Forage Sud 1", "10.050100", "-13.250100")
    conn.execute(
        """
        INSERT INTO eau_situation (
            reseau, volume_produit, volume_distribue, montant_du, montant_facture,
            montant_recouvre, exemple
        ) VALUES ('seg', '1000', '800', '500000', '400000', '250000', 1)
        """
    )
    quand = maintenant()

    def abonne(reference, reseau, lieu_id, nom, latitude, longitude):
        conn.execute(
            """
            INSERT INTO eau_abonnement (
                reference, reseau, lieu_id, nom, telephone, latitude, longitude,
                paye, exemple, cree_le
            ) VALUES (?, ?, ?, ?, '623 00 00 01', ?, ?, 1, 1, ?)
            """,
            (reference, reseau, lieu_id, nom, latitude, longitude, quand),
        )

    for index in range(1, 5):
        abonne(f"EAU-EX-S{index}", "seg", alpha, f"Abonné exemple {index}", "9.650000", "-13.570000")
    abonne("EAU-EX-S5", "seg", beta, "Abonné exemple 5", "9.660000", "-13.580000")
    abonne("EAU-EX-N1", "snape", nord, "Abonné rural 1", "10.100000", "-13.200000")
    abonne("EAU-EX-N2", "snape", sud, "Abonné rural 2", "10.050000", "-13.250000")
    conn.execute(
        """
        INSERT INTO eau_demande (
            reference, reseau, lieu_id, nom, telephone, latitude, longitude, etat, exemple, cree_le
        ) VALUES ('EAU-EX-D1', 'seg', ?, 'Demande exemple', '623 00 00 09', '9.650500', '-13.570500', 'recue', 1, ?)
        """,
        (alpha, quand),
    )


# Textes courts reformulés d’après le décret d’attributions d’août 2025,
# mehh.gov.gn et les communiqués repris par gouvernement.gov.gn.
BLOCS_VITRINE = (
    (
        "presentation",
        "Le ministère",
        "Le ministère conçoit, prépare et met en œuvre la politique du Gouvernement "
        "pour l’assainissement, l’hydraulique et les hydrocarbures, puis en suit l’exécution. "
        "Il prépare les textes de ces trois domaines et veille à leur application.",
        "2025-08-27",
        1,
    ),
    (
        "presentation",
        "Eau, salubrité et hydrocarbures",
        "L’assainissement porte sur les déchets, les eaux usées et les eaux pluviales, "
        "en ville comme en zone rurale. L’hydraulique porte sur l’accès à l’eau et la protection "
        "des ressources. Les hydrocarbures portent sur la qualité des produits, les prix et le gaz butane. "
        "La Société des eaux de Guinée, l’Agence nationale d’assainissement et de salubrité publique "
        "et la Société guinéenne des hydrocarbures relèvent de ce périmètre.",
        "2025-08-27",
        2,
    ),
    (
        "actualite",
        "Lancement du Projet eau et assainissement en Guinée",
        "Le 29 juin 2026, à Conakry, le ministère a lancé le Projet eau et assainissement en Guinée. "
        "Il finance des infrastructures et renforce les services d’eau, d’assainissement et d’hygiène "
        "à Conakry et dans les villes voisines. Son coordonnateur, Arafan Bayo, a indiqué que le projet "
        "doit profiter à plus de 2,6 millions de personnes.",
        "2026-06-29",
        1,
    ),
    (
        "actualite",
        "Eau potable, déchets et gaz butane",
        "Le 8 juin 2026, le ministre Aboubacar Camara a présenté les chantiers du département : "
        "fermeture progressive de la décharge de Dar-es-Salam, réorganisation de la collecte des déchets "
        "dans les communes de Conakry, réforme du Fonds hydraulique et promotion du gaz butane. "
        "En zone rurale, les forages anciens doivent laisser place, peu à peu, à des ouvrages modernes "
        "alimentés au solaire et reliés à un réseau.",
        "2026-06-08",
        2,
    ),
    (
        "communique",
        "Plan de mobilisation des parties prenantes",
        "Le 30 janvier 2025, le département a publié le plan de mobilisation des parties prenantes "
        "du Projet eau et assainissement en Guinée. Ce document indique comment les communes, "
        "les services publics et les partenaires sont associés au projet. Il a été mis en ligne "
        "sur le site du ministère et sur celui de la Société des eaux de Guinée.",
        "2025-01-30",
        1,
    ),
    (
        "communique",
        "Suivi du projet eau et assainissement",
        "Lors du lancement du 29 juin 2026, le ministre Aboubacar Camara a rappelé que le département "
        "coordonne le projet et en suit l’exécution. La qualité des travaux et une gestion lisible "
        "sont les exigences retenues pour Conakry et les agglomérations voisines.",
        "2026-06-29",
        2,
    ),
)

# Anciens titres du jeu de démonstration, remplacés une seule fois s’ils n’ont pas été réécrits.
_ANCIENS_VITRINE = (
    "Le ministère",
    "Trois domaines",
    "Réunion de coordination, exemple",
    "Chantier de démonstration",
    "Communiqué de démonstration",
    "Avis de service, exemple",
)


def _inserer_bloc_public(conn, bloc, quand):
    genre, titre, texte, publie_le, ordre = bloc
    conn.execute(
        """
        INSERT INTO bloc_public (genre, titre, texte, publie_le, ordre, exemple, cree_le, modifie_le)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (genre, titre, texte, publie_le, ordre, quand, quand),
    )


def semer_vitrine(conn):
    quand = maintenant()
    if conn.execute("SELECT COUNT(*) AS n FROM bloc_public").fetchone()["n"] == 0:
        for bloc in BLOCS_VITRINE:
            _inserer_bloc_public(conn, bloc, quand)
        return
    for ancien, bloc in zip(_ANCIENS_VITRINE, BLOCS_VITRINE):
        ligne = conn.execute(
            "SELECT id FROM bloc_public WHERE titre = ? AND exemple = 1",
            (ancien,),
        ).fetchone()
        if ligne is None:
            continue
        genre, titre, texte, publie_le, ordre = bloc
        conn.execute(
            """
            UPDATE bloc_public
            SET genre = ?, titre = ?, texte = ?, publie_le = ?, ordre = ?, exemple = 0, modifie_le = ?
            WHERE id = ?
            """,
            (genre, titre, texte, publie_le, ordre, quand, ligne["id"]),
        )


def migrer(conn):
    def colonnes(table):
        return {ligne[1] for ligne in conn.execute(f"PRAGMA table_info({table})")}

    if "fonction" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN fonction TEXT NOT NULL DEFAULT ''")
    if "structure_id" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN structure_id INTEGER")
    if "structure_id" not in colonnes("projet"):
        conn.execute("ALTER TABLE projet ADD COLUMN structure_id INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bloc_public (
            id INTEGER PRIMARY KEY,
            genre TEXT NOT NULL CHECK (genre IN ('presentation', 'actualite', 'communique')),
            titre TEXT NOT NULL,
            texte TEXT NOT NULL,
            publie_le TEXT NOT NULL,
            ordre INTEGER NOT NULL DEFAULT 0,
            exemple INTEGER NOT NULL DEFAULT 0,
            cree_le TEXT NOT NULL,
            modifie_le TEXT NOT NULL
        )
        """
    )


def preparer():
    conn = connecter()
    try:
        conn.executescript(SCHEMA)
        migrer(conn)
        info = semer(conn)
        semer_ordures(conn)
        semer_eau(conn)
        semer_vitrine(conn)
        conn.commit()
        return info
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
