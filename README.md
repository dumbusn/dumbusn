# Application du ministère

Socle local de l’application unique du Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures, République de Guinée.

Les quatre blocs sont en service : la gestion documentaire des directions, le tableau de bord du BSD, la collecte des ordures, et l’eau (SEG en ville, SNAPE en zone rurale). Une page d’instructions suit le circuit du ministre au chef de cabinet, au secrétaire général, puis aux directions. Le ministre, le secrétaire général, le chef de cabinet et le BSD ont l’accès complet. À partir du directeur, le compte ne voit que sa direction.

Le registre des projets, les actualités, les communiqués et les tableaux de la collecte, du SEG et du SNAPE restent vides tant que les services n’ont pas saisi leurs données.

La page publique, ouverte sans connexion, reprend le menu d’un site de ministère. La cellule de communication rédige la présentation, les actualités et les communiqués. L’organigramme est une arborescence : le ministre, le secrétaire général, le chef de cabinet ou un administrateur crée les entités depuis la racine et y ajoute les agents. L’annuaire porte le poste, l’entité et les rôles. Le rôle choisi parmi les niveaux du ministère est celui de la personne affectée : elle ne voit que ce que ce rôle autorise. Les dossiers se créent sans limite de profondeur affichée. Tout type de fichier est accepté, jusqu’à 100 Mo. Après connexion : carte des points GPS déjà saisis, export CSV du registre visible, journal des actions pour l’administrateur. Aucun chiffre n’est affiché s’il n’a pas été saisi.

Chaque niveau d’instruction n’écrit qu’au niveau juste en dessous et choisit ses destinataires. Le chargé d’études reçoit, il n’instruit pas. L’instruction part par e-mail si `MAHH_SMTP_HOTE`, `MAHH_SMTP_PORT`, `MAHH_SMTP_UTILISATEUR`, `MAHH_SMTP_MOT_DE_PASSE` et `MAHH_SMTP_EXPEDITEUR` sont définis. Le lien utilise `MAHH_URL_PUBLIQUE` (défaut `https://mhhc.nasad.gn`). Sans ces réglages, l’instruction est quand même enregistrée. Les indicateurs d’assainissement comptent les zones de traitement et de tri, les PME et les abonnés réellement créés, selon le découpage officiel des dix régions.

## Lancer

Depuis la racine de ce dépôt, avec Python 3.11 ou plus récent. Aucune dépendance à installer.

```bash
python3 -m mahh
```

Puis ouvrir http://127.0.0.1:8000/

Après la connexion, la première page est l’accueil : les quatre blocs et la page d’instructions. Le bouton Accueil, en tête de chaque page, y ramène.

Au premier lancement, le compte administrateur est créé.

- Si `MAHH_ADMIN_MOT_DE_PASSE` est défini (10 caractères au minimum), ce mot de passe est utilisé et il n’est pas réécrit.
- Sinon, un mot de passe est tiré au hasard, affiché une fois, et copié dans `data/mot-de-passe-initial.txt`. Ce fichier n’est pas versionné. Changez le mot de passe dans Compte, puis supprimez le fichier.

L’identifiant par défaut est `admin`. `MAHH_ADMIN_IDENTIFIANT` le remplace au premier lancement seulement.

Autres réglages : `MAHH_HOST` (défaut `0.0.0.0`), `MAHH_PORT` (défaut `8000`), `MAHH_DATA` (défaut le dossier `data/` à côté du programme). En local, l’adresse de travail reste http://127.0.0.1:8000/.

La base SQLite et les fichiers déposés restent dans `data/`. Ils ne vont pas dans git.

## Déployer

Sur un VPS Debian ou Ubuntu, depuis ce dépôt, avec sudo. Le script installe Python 3 et Caddy s’ils manquent, crée l’utilisateur de service `mahh`, et active une unité systemd qui lance `python3 -m mahh` depuis ce dossier.

```bash
sudo bash deploy/deploiement.sh
```

Le service écoute sur `MAHH_HOST` (défaut `0.0.0.0`, port 8000) pour qu’un proxy du réseau local puisse le joindre. L’adresse publique reste `https://mhhc.nasad.gn`. Le bloc du domaine est ajouté ou remplacé dans le Caddyfile ; les autres sites restent en place.

Une deuxième exécution ne vide pas `data/`. Le nom `mhhc.nasad.gn` doit pointer vers le serveur pour que Caddy obtienne le certificat. Le redémarrage du service est automatique.

## Vérifier le parcours

```bash
python3 tests/test_parcours.py
```

Le test crée une base temporaire, se connecte, ouvre une direction, crée un dossier, accorde un droit à un groupe, et contrôle l’écran du BSD.

## Périmètre de ce socle

- Comptes, session, et un administrateur qui crée les groupes et accorde les privilèges.
- Arbre des domaines et des structures de la note du 10 novembre 2026. Les sigles qu’elle ne développe pas restent des sigles.
- Dossiers et fichiers, avec créer, consulter, modifier, supprimer par groupe.
- Écran BSD : registre filtrable. Le code d’un projet ouvre ses notes, ses rapports et le classement des documents physiques. Le BSD saisit les projets.
- Page d’instructions, du ministre aux directions. Le suivi des retards se lit dans les tableaux. Une instruction peut porter une échéance et être marquée exécutée, avec un compte rendu.
- Carte des coordonnées GPS déjà enregistrées, export CSV du registre visible, journal d’activité réservé à l’administrateur.
- Page publique : menu du ministère, pages à compléter par la cellule de communication, organigramme construit par l’administrateur.
- Accès complet pour la hiérarchie et le BSD ; vue limitée au rattachement pour une direction.
- Collecte des ordures : localités, PME, abonnement, paiement enregistré, GPS, agents, signalement. L’ANASP saisit ces éléments.
- Eau : demande et abonnement SEG et SNAPE. Chaque service saisit ses villes ou ses villages. La hiérarchie et le BSD voient les deux. Chaque structure ne voit que le sien.
