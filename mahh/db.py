"""SQLite : schéma, connexion, premier remplissage."""

import os
import sqlite3
from contextlib import contextmanager
from mahh.config import repertoire_donnees
from mahh.securite import ecrire_mot_initial, hasher, maintenant, preparer_mot_admin
from mahh.seed import ARBRES
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
    courriel TEXT NOT NULL DEFAULT '',
    organigramme_id INTEGER,
    matricule TEXT NOT NULL DEFAULT '',
    telephone TEXT NOT NULL DEFAULT '',
    intitule_poste TEXT NOT NULL DEFAULT '',
    roles TEXT NOT NULL DEFAULT '',
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
    echelon TEXT NOT NULL,
    structure_id INTEGER REFERENCES noeud(id),
    texte TEXT NOT NULL,
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL,
    echeance TEXT NOT NULL DEFAULT '',
    etat TEXT NOT NULL DEFAULT 'en_cours',
    execute_le TEXT,
    execute_par INTEGER,
    compte_rendu TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS instruction_destinataire (
    instruction_id INTEGER NOT NULL REFERENCES instruction(id) ON DELETE CASCADE,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateur(id),
    etat TEXT NOT NULL DEFAULT 'en_cours',
    execute_le TEXT,
    compte_rendu TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (instruction_id, utilisateur_id)
);

CREATE TABLE IF NOT EXISTS maille (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES maille(id),
    genre TEXT NOT NULL CHECK (genre IN ('region', 'prefecture', 'sous_prefecture', 'quartier', 'secteur')),
    nom TEXT NOT NULL,
    code TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    exemple INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ztt (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    maille_id INTEGER NOT NULL REFERENCES maille(id),
    cree_par INTEGER REFERENCES utilisateur(id),
    cree_le TEXT NOT NULL
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


def retirer_jeu(conn):
    """Retire les lignes du jeu d’exemple déjà écrites. Les saisies (exemple = 0) restent."""
    mailles = "SELECT id FROM maille WHERE exemple = 1"
    lieux = "SELECT id FROM eau_lieu WHERE exemple = 1"
    abonnements = (
        "SELECT id FROM abonnement WHERE exemple = 1 "
        f"OR secteur_id IN ({mailles})"
    )
    conn.execute(f"DELETE FROM signalement WHERE exemple = 1 OR abonnement_id IN ({abonnements})")
    conn.execute(f"DELETE FROM passage WHERE exemple = 1 OR abonnement_id IN ({abonnements})")
    conn.execute(f"DELETE FROM abonnement WHERE id IN ({abonnements})")
    conn.execute(
        "DELETE FROM effectif WHERE exemple = 1 OR pme_id IN (SELECT id FROM pme WHERE exemple = 1)"
    )
    conn.execute(
        "DELETE FROM trajet WHERE exemple = 1 OR pme_id IN (SELECT id FROM pme WHERE exemple = 1)"
    )
    conn.execute("DELETE FROM pme_secteur WHERE pme_id IN (SELECT id FROM pme WHERE exemple = 1)")
    conn.execute(f"DELETE FROM pme_secteur WHERE secteur_id IN ({mailles})")
    conn.execute(
        f"UPDATE point_collecte SET secteur_id = NULL WHERE secteur_id IN ({mailles})"
    )
    conn.execute("DELETE FROM point_collecte WHERE exemple = 1")
    conn.execute("DELETE FROM pme WHERE exemple = 1")
    for genre in ("secteur", "quartier", "sous_prefecture", "prefecture", "region"):
        conn.execute("DELETE FROM maille WHERE exemple = 1 AND genre = ?", (genre,))
    conn.execute(f"DELETE FROM eau_abonnement WHERE exemple = 1 OR lieu_id IN ({lieux})")
    conn.execute(f"DELETE FROM eau_demande WHERE exemple = 1 OR lieu_id IN ({lieux})")
    conn.execute(f"DELETE FROM eau_site WHERE exemple = 1 OR lieu_id IN ({lieux})")
    conn.execute("DELETE FROM eau_situation WHERE exemple = 1")
    conn.execute("DELETE FROM eau_lieu WHERE exemple = 1")
    conn.execute("DELETE FROM projet WHERE exemple = 1")


# Présentation reformulée d’après le décret d’attributions d’août 2025.
# Les actualités et les communiqués sont rédigés par la cellule, pas chargés ici.
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
)

# Titres déjà publiés par le jeu d’exemple ou par un chargement de communiqués.
# Ils sont retirés au démarrage. Un texte dont le titre a été réécrit par la cellule reste.
TITRES_RETIRES = (
    "Trois domaines",
    "Réunion de coordination, exemple",
    "Réunion de coordination exemple",
    "Chantier de démonstration",
    "Communiqué de démonstration",
    "Avis de service, exemple",
    "Avis de service exemple",
    "Lancement du Projet eau et assainissement en Guinée",
    "Eau potable, déchets et gaz butane",
    "Plan de mobilisation des parties prenantes",
    "Suivi du projet eau et assainissement",
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
    for titre in TITRES_RETIRES:
        conn.execute("DELETE FROM bloc_public WHERE titre = ?", (titre,))
    conn.execute(
        """
        DELETE FROM bloc_public
        WHERE genre IN ('actualite', 'communique') AND exemple = 1
        """
    )
    conn.execute(
        """
        DELETE FROM bloc_public
        WHERE texte LIKE '%lorem%' OR texte LIKE '%Lorem%'
           OR texte LIKE '%Texte d’exemple%' OR texte LIKE '%Texte d''exemple%'
        """
    )
    for bloc in BLOCS_VITRINE:
        titre = bloc[1]
        if conn.execute(
            "SELECT id FROM bloc_public WHERE titre = ?",
            (titre,),
        ).fetchone() is None:
            _inserer_bloc_public(conn, bloc, quand)


def migrer(conn):
    def colonnes(table):
        return {ligne[1] for ligne in conn.execute(f"PRAGMA table_info({table})")}

    definition = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instruction'"
    ).fetchone()
    if definition and definition["sql"] and "CHECK" in definition["sql"]:
        conn.execute("ALTER TABLE instruction RENAME TO instruction_ancienne")
        conn.execute(
            """
            CREATE TABLE instruction (
                id INTEGER PRIMARY KEY,
                echelon TEXT NOT NULL,
                structure_id INTEGER REFERENCES noeud(id),
                texte TEXT NOT NULL,
                cree_par INTEGER REFERENCES utilisateur(id),
                cree_le TEXT NOT NULL,
                echeance TEXT NOT NULL DEFAULT '',
                etat TEXT NOT NULL DEFAULT 'en_cours',
                execute_le TEXT,
                execute_par INTEGER,
                compte_rendu TEXT NOT NULL DEFAULT ''
            )
            """
        )
        anciennes = colonnes("instruction_ancienne")
        gardees = [
            nom
            for nom in (
                "id", "echelon", "structure_id", "texte", "cree_par", "cree_le",
                "echeance", "etat", "execute_le", "execute_par", "compte_rendu",
            )
            if nom in anciennes
        ]
        liste = ", ".join(gardees)
        conn.execute(
            f"INSERT INTO instruction ({liste}) SELECT {liste} FROM instruction_ancienne"
        )
        conn.execute("DROP TABLE instruction_ancienne")

    if "courriel" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN courriel TEXT NOT NULL DEFAULT ''")
    if "code" not in colonnes("maille"):
        conn.execute("ALTER TABLE maille ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    if "detail" not in colonnes("maille"):
        conn.execute("ALTER TABLE maille ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
    if "fonction" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN fonction TEXT NOT NULL DEFAULT ''")
    if "structure_id" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN structure_id INTEGER")
    if "organigramme_id" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN organigramme_id INTEGER")
    for colonne, definition in (
        ("matricule", "TEXT NOT NULL DEFAULT ''"),
        ("telephone", "TEXT NOT NULL DEFAULT ''"),
        ("intitule_poste", "TEXT NOT NULL DEFAULT ''"),
        ("roles", "TEXT NOT NULL DEFAULT ''"),
    ):
        if colonne not in colonnes("utilisateur"):
            conn.execute(f"ALTER TABLE utilisateur ADD COLUMN {colonne} {definition}")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organigramme (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES organigramme(id) ON DELETE CASCADE,
            nom TEXT NOT NULL,
            code TEXT NOT NULL DEFAULT '',
            intitule TEXT NOT NULL DEFAULT '',
            ordre INTEGER NOT NULL DEFAULT 0,
            noeud_id INTEGER REFERENCES noeud(id) ON DELETE SET NULL,
            niveau TEXT NOT NULL DEFAULT '',
            cree_le TEXT NOT NULL,
            modifie_le TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attribution (
            id INTEGER PRIMARY KEY,
            noeud_id INTEGER NOT NULL REFERENCES noeud(id) ON DELETE CASCADE,
            texte TEXT NOT NULL,
            ordre INTEGER NOT NULL DEFAULT 0,
            modifie_le TEXT NOT NULL
        )
        """
    )
    for colonne, definition in (
        ("echeance", "TEXT NOT NULL DEFAULT ''"),
        ("etat", "TEXT NOT NULL DEFAULT 'en_cours'"),
        ("execute_le", "TEXT"),
        ("execute_par", "INTEGER"),
        ("compte_rendu", "TEXT NOT NULL DEFAULT ''"),
    ):
        if colonne not in colonnes("instruction"):
            conn.execute(f"ALTER TABLE instruction ADD COLUMN {colonne} {definition}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY,
            utilisateur_id INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            chemin TEXT NOT NULL,
            quand TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_quand ON journal(quand)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_maille_parent ON maille(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_maille_code ON maille(code)")
    if "niveau" not in colonnes("organigramme"):
        conn.execute("ALTER TABLE organigramme ADD COLUMN niveau TEXT NOT NULL DEFAULT ''")
    if "code" not in colonnes("organigramme"):
        conn.execute("ALTER TABLE organigramme ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_organigramme_code "
        "ON organigramme(code) WHERE code != ''"
    )


def semer_organigramme(conn):
    if conn.execute("SELECT COUNT(*) AS n FROM organigramme").fetchone()["n"]:
        return
    quand = maintenant()
    domaines = conn.execute(
        "SELECT * FROM noeud WHERE genre = 'domaine' ORDER BY ordre, nom"
    ).fetchall()
    for domaine in domaines:
        curseur = conn.execute(
            """
            INSERT INTO organigramme (
                parent_id, nom, intitule, ordre, noeud_id, cree_le, modifie_le
            ) VALUES (NULL, ?, '', ?, ?, ?, ?)
            """,
            (domaine["nom"], domaine["ordre"], domaine["id"], quand, quand),
        )
        parent = curseur.lastrowid
        structures = conn.execute(
            """
            SELECT * FROM noeud
            WHERE parent_id = ? AND genre = 'structure'
            ORDER BY ordre, nom
            """,
            (domaine["id"],),
        ).fetchall()
        for structure in structures:
            conn.execute(
                """
                INSERT INTO organigramme (
                    parent_id, nom, intitule, ordre, noeud_id, cree_le, modifie_le
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parent,
                    structure["nom"],
                    structure["intitule"],
                    structure["ordre"],
                    structure["id"],
                    quand,
                    quand,
                ),
            )


def preparer():
    conn = connecter()
    try:
        conn.executescript(SCHEMA)
        migrer(conn)
        info = semer(conn)
        retirer_jeu(conn)
        semer_vitrine(conn)
        semer_organigramme(conn)
        from mahh.decoupage import semer_decoupage

        semer_decoupage(conn)
        conn.commit()
        return info
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
