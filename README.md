# Application du ministère

Socle local de l’application unique du Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures, République de Guinée.

Trois blocs sont en service : la gestion documentaire des directions, le tableau de bord du BSD, et la collecte des ordures. Une page d’instructions suit le circuit du ministre au chef de cabinet, au secrétaire général, puis aux directions. Le ministre, le secrétaire général, le chef de cabinet et le BSD ont l’accès complet. Une direction ne voit que ses projets et ce qui la concerne. Le SEG et le SNAPE sont décrits dans l’application et ne sont pas construits.

Les dix-huit projets chargés au premier lancement sont un **exemple fictif**, repris d’un classeur de démonstration. Ce ne sont pas les projets du ministère, et les totaux ne sont pas des chiffres officiels.

## Lancer

Depuis la racine de ce dépôt, avec Python 3.11 ou plus récent. Aucune dépendance à installer.

```bash
python3 -m mahh
```

Puis ouvrir http://127.0.0.1:8000/

Après la connexion, la première page est l’accueil : les quatre blocs, la page d’instructions, et le rappel que les projets affichés sont des exemples. Le bouton Accueil, en tête de chaque page, y ramène.

Au premier lancement, le compte administrateur est créé.

- Si `MAHH_ADMIN_MOT_DE_PASSE` est défini (10 caractères au minimum), ce mot de passe est utilisé et il n’est pas réécrit.
- Sinon, un mot de passe est tiré au hasard, affiché une fois, et copié dans `data/mot-de-passe-initial.txt`. Ce fichier n’est pas versionné. Changez le mot de passe dans Compte, puis supprimez le fichier.

L’identifiant par défaut est `admin`. `MAHH_ADMIN_IDENTIFIANT` le remplace au premier lancement seulement.

Autres réglages : `MAHH_HOTE` (défaut `127.0.0.1`), `MAHH_PORT` (défaut `8000`), `MAHH_DATA` (défaut le dossier `data/` à côté du programme).

La base SQLite et les fichiers déposés restent dans `data/`. Ils ne vont pas dans git.

## Vérifier le parcours

```bash
python3 tests/test_parcours.py
```

Le test crée une base temporaire, se connecte, ouvre une direction, crée un dossier, accorde un droit à un groupe, et contrôle l’écran du BSD.

## Périmètre de ce socle

- Comptes, session, et un administrateur qui crée les groupes et accorde les privilèges.
- Arbre des domaines et des structures de la note du 10 novembre 2026. Les sigles qu’elle ne développe pas restent des sigles.
- Dossiers et fichiers, avec créer, consulter, modifier, supprimer par groupe.
- Écran BSD : registre filtrable, indicateurs du classeur, jeu d’exemple marqué. Le code d’un projet ouvre ses notes, ses rapports et le classement des documents physiques.
- Page d’instructions, et sommation d’une direction en retard depuis cette page.
- Accès complet pour la hiérarchie et le BSD ; vue limitée au rattachement pour une direction.
- Collecte des ordures : abonnement, paiement enregistré, GPS, rattachement, PME, points ANASP, agents, signalement. Le jeu de départ est un exemple.

Hors de ce socle : demande, abonnement et tableaux de bord du SEG et du SNAPE.
