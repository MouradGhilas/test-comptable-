# Journal des versions

Ce que chaque version apporte, en clair. L'application affiche ces notes avant
et après une mise à jour.

## 1.5.0

- **Mise à jour depuis l'application.** Plus besoin de trouver `donnees\maj\`
  ni de lancer un fichier `.bat` : le fichier reçu se dépose directement dans
  Paramètres → Mise à jour. Il est contrôlé avant d'être appliqué, et
  l'application se rouvre toute seule.
- Un fichier qui n'est pas une version de Cabinet Immo, une archive abîmée ou
  une version plus ancienne que la vôtre sont refusés en expliquant pourquoi.
- Ce journal des versions est désormais livré avec l'application.

## 1.4.1

- **Le fichier d'import se lit comme un journal.** Une case laissée vide reprend
  la valeur de la ligne du dessus : la date, le journal et le numéro ne
  s'écrivent qu'une fois par écriture.
- Le journal s'écrit par son code (`CA`) ou par son nom (`CAISSE`,
  `Journal de caisse`).
- La ligne de totaux au bas d'un tableau est ignorée d'elle-même, et signalée.
- Un compte absent du plan propose les plus proches et rappelle comment le
  créer ; un journal inconnu liste ceux qui existent.
- La colonne « N° écriture » devient facultative.

## 1.4.0

- **Reprise complète d'un dossier déjà tenu ailleurs** : 18 modèles d'import.
- **Balance d'ouverture** : les soldes à une date choisie produisent une
  écriture d'à-nouveaux unique, après vérification de l'équilibre. C'est elle
  qui permet de reprendre un dossier en cours d'année.
- Nouveaux modèles : comptes de trésorerie, mandats, baux, loyers et quittances,
  programmes, lots, contrats VSP, échéanciers, immobilisations, règlements.
- Les modèles sont numérotés dans l'ordre de reprise et regroupés par domaine.
- Bouton **Importer** sur les listes : tiers, biens, baux, programmes, contrats,
  immobilisations, salariés.

## 1.3.0

- **Import et export sur les listes de ventes et d'achats.** L'export reprend
  les filtres affichés, périmètre compris, avec une feuille de factures et une
  feuille de lignes.
- La liste des factures suit enfin le sélecteur de périmètre.

## 1.2.0

- **Saisie en totalité** : une opération dont le montant se répartit entre une
  part déclarée et une part non déclarée se saisit en une seule fois.
- **Import Excel** : l'application fournit les en-têtes, vous remplissez, vous
  redéposez. Contrôle ligne par ligne avant tout enregistrement.
- **Correction du « NetworkError »** : l'application ne se dédouble plus quand
  on la rouvre alors qu'elle tourne déjà. En cas de perte de liaison, un message
  clair remplace le message technique, et la connexion se rétablit seule.
- Journal des incidents consultable dans Paramètres → Sauvegarde & données.

## 1.1.0

- Périmètre déclaré / hors déclaration sur chaque opération, avec vue réelle.
- Résumés automatiques sur téléphone (Telegram, courriel).
- Mise à jour sans perte de données, avec retour arrière automatique.
