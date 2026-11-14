"""SQLite : schéma, connexion, premier remplissage."""

import os
import sqlite3
from contextlib import contextmanager

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


def migrer(conn):
    def colonnes(table):
        return {ligne[1] for ligne in conn.execute(f"PRAGMA table_info({table})")}

    if "fonction" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN fonction TEXT NOT NULL DEFAULT ''")
    if "structure_id" not in colonnes("utilisateur"):
        conn.execute("ALTER TABLE utilisateur ADD COLUMN structure_id INTEGER")
    if "structure_id" not in colonnes("projet"):
        conn.execute("ALTER TABLE projet ADD COLUMN structure_id INTEGER")


def preparer():
    conn = connecter()
    try:
        conn.executescript(SCHEMA)
        migrer(conn)
        info = semer(conn)
        conn.commit()
        return info
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
