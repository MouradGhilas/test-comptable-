# Cabinet Immo

**Application de comptabilité pour un comptable qui gère à la fois une agence
immobilière et une promotion immobilière, en Algérie.**

Comptabilité conforme au **SCF** (Système Comptable Financier), aide à la
déclaration **G n° 50**, gestion des **ventes sur plan (loi n° 11-04)** et de la
**gestion locative pour compte de propriétaires**.

* Les données restent **dans un dossier local** sur votre poste. Rien n'est envoyé sur Internet.
* **Aucune installation** : Python 3.9+ suffit, zéro dépendance à télécharger.
* Fonctionne **hors ligne**, y compris sur un poste sans connexion.

---

> **Vous installez pour quelqu'un d'autre ?** Le [GUIDE.md](GUIDE.md) contient
> les marches à suivre, séparées par public : installation sur le PC, accès à
> distance depuis l'étranger, et réception des chiffres sur le téléphone du
> dirigeant.

## Démarrer

**Windows** — double-cliquez sur `INSTALLER.bat`. Il trouve Python, ou le
télécharge tout seul si le poste n'en a pas, crée le raccourci du Bureau et
propose le démarrage automatique. Aucun droit administrateur.

**Linux / macOS**

```bash
python3 app.py
```

Le navigateur s'ouvre sur `http://127.0.0.1:8781`. Au premier lancement, vous
créez votre compte et le dossier comptable de votre entreprise.

Ensuite, pour ouvrir l'application : le raccourci **Cabinet Immo** du Bureau
(Windows), ou `./lancer.sh` (Linux, macOS).

### Découvrir avec un jeu d'essai

**Depuis l'application** : Paramètres → Import de données → *Créer un dossier
d'essai*. Une année d'activité complète — programme de 24 logements, contrats
VSP, baux, loyers, paie et déclarations — apparaît dans un dossier séparé,
à côté du vôtre, supprimable d'un clic.

En ligne de commande, dans un dossier de données distinct :

```bash
python3 outils/donnees_demonstration.py --donnees donnees_demo
python3 app.py --donnees donnees_demo
```

Identifiant `demo`, mot de passe `demo1234`.

### Accompagnement au démarrage

Sur un dossier neuf, le tableau de bord affiche **« Pour bien démarrer »** :
créer le dossier, vérifier les taux fiscaux, reprendre ses données ou essayer,
**vérifier où sont les données**, faire une première sauvegarde. Chaque point se
coche tout seul, et la liste disparaît une fois complète.

L'étape « où sont les données » n'est pas cosmétique : si le dossier `donnees`
est sous **OneDrive, Google Drive ou Dropbox**, l'application avertit. La base
est ouverte en mode WAL, et un service de synchronisation qui recopie
`.db`, `.db-wal` et `.db-shm` séparément pendant que l'application écrit peut
**corrompre la comptabilité**.

### Options utiles

```bash
python3 app.py --donnees /media/usb/comptabilite   # données sur une clé USB
python3 app.py --port 9000                         # autre port
python3 app.py --verifier                          # contrôle d'intégrité
python3 app.py --sauvegarder                       # sauvegarde sans ouvrir l'appli
```

---

## Ce que fait l'application

### Comptabilité générale (SCF)

| Fonction | Détail |
|---|---|
| Plan comptable | Nomenclature SCF complète (244 comptes), enrichie de sous-comptes immobiliers, modifiable |
| Journaux | Ventes, achats, banque, caisse, paie, opérations diverses, à-nouveaux |
| Saisie | Partie double avec contrôle d'équilibre en direct ; une écriture déséquilibrée est refusée. Compte et tiers cherchés au nom comme au numéro, montant qui solde proposé par la touche Entrée, contrepartie habituelle apprise de l'historique du journal |
| Grand livre | Par compte, par tiers, avec solde progressif et filtre « non lettrées » |
| Balance | Générale ou agrégée par classe, avec reports à nouveau |
| Lettrage | Manuel et automatique (rapprochement facture ↔ règlement d'un même tiers) |
| Relances clients | Qui doit quoi et depuis quand, avec la dernière relance envoyée ; lettre imprimable à trois niveaux, du rappel à la mise en demeure |
| Relevé de compte tiers | Détail des mouvements sur une période, solde d'ouverture, solde progressif, ancienneté de ce qui reste dû ; imprimable et exportable |
| Rapprochement bancaire | Import du relevé fourni par la banque et rapprochement automatique (sens des colonnes et écart de date reconnus), pointage manuel, calcul de l'écart |
| États financiers | Bilan, compte de résultat par nature (TCR), tableau des flux de trésorerie |
| Clôture | Contrôles préalables, virement du résultat en 120/129, génération des à-nouveaux, verrouillage |
| Exports | Excel natif : balance, grand livre, livre-journal, liasse, livres de TVA |

Toute opération métier génère son écriture comptable automatiquement, avec
traçabilité de son origine.

**Une écriture se corrige.** Double-clic sur une ligne du journal : elle
s'ouvre dans la grille de saisie et se réenregistre **en place** — même
identifiant, même numéro, mêmes justificatifs. Une écriture validée n'est pas
figée pour autant : on confirme, elle repasse en brouillon, et l'opération est
inscrite au journal des opérations. Ce que la correction entraîne est dit
avant : lettrage défait des deux côtés, document d'origine qui, lui, ne change
pas. Restent protégés un exercice clos et une écriture pointée dans un
rapprochement bancaire **clôturé** — un relevé arrêté ne change pas de contenu
dans le dos de celui qui l'a signé. L'extourne demeure, pour qui préfère
laisser l'écriture telle quelle.

### Santé du dossier

Dix contrôles tournent au fil de l'eau, dans la rubrique **Clôture** : équilibre
de la comptabilité, trous dans la numérotation d'un journal, caisse passée en
négatif, factures validées sans écriture, clients créditeurs ou fournisseurs
débiteurs, G50 déposées qui ne correspondent plus aux comptes, brouillons,
écritures sans justificatif, lettrage ancien, dernière copie de sauvegarde hors
du poste. Chaque anomalie dit ce qui ne va pas, **pourquoi ça compte**, et mène
à l'écran où la corriger.

Ils n'empêchent rien : les contrôles qui *bloquent* une clôture restent sur
l'écran de clôture.

### Une aide par écran

Un **?** dans la barre du haut, sur chaque écran, explique en français simple la
règle comptable qui s'y applique — pourquoi les loyers transitent par 4671,
pourquoi une avance VSP n'est pas du chiffre d'affaires, ce que l'application
fait de vos chiffres sur cet écran-là. Aucun taux n'y figure : ils vivent dans
Paramètres → Fiscalité, où ils se vérifient.

### Retrouver quelque chose

Un comptable ne se souvient pas de l'écran où se trouve ce qu'il cherche : il se
souvient d'un nom, d'un numéro de facture — ou d'un montant. Le champ de
recherche de la barre haute (`Ctrl + K`) interroge d'un coup les écritures, les
tiers, les factures, le plan comptable, les biens, les baux, les programmes, les
contrats de vente sur plan et les salariés. Chaque résultat mène directement à sa
page, et l'écriture visée s'ouvre d'elle-même.

**Chercher un montant** est le cas le plus utile et le moins évident : taper
`125 000` retrouve la ligne d'écriture qui porte cette somme, au débit comme au
crédit, avec son compte et son journal. C'est ainsi qu'on remonte à l'origine
d'un solde qui ne tombe pas juste.

### Agence immobilière

* Portefeuille de biens (nature du titre : acte notarié, livret foncier, acte administratif…)
* Mandats de vente, de location et de gestion, exclusifs ou non
* Transactions : la commission est calculée depuis le mandat, facturée et comptabilisée en 7061
* Baux d'habitation, commerciaux et professionnels ; suivi de l'enregistrement aux impôts
* **Gestion locative** : génération mensuelle des quittances, encaissement, prélèvement des
  honoraires, reversement aux propriétaires, relevé par propriétaire
* Quittances de loyer imprimables

> **Le point comptable qui compte.** Les loyers encaissés pour le compte des
> propriétaires ne sont **jamais** un produit de l'agence. Ils transitent par le
> compte 4671 « Propriétaires mandants ». Seuls les honoraires (commission de
> vente 7061, entremise 7062, gestion 7063) constituent votre chiffre d'affaires.
> C'est précisément ce qui est vérifié en cas de contrôle fiscal, et
> l'application vous empêche de vous tromper.

### Promotion immobilière (loi n° 11-04)

* Programmes : assiette foncière, permis de construire, certificat de conformité, calendrier
* Tranches et lots (logements, locaux, parkings), création en série
* **Contrats de vente sur plan** : échéancier adossé à l'avancement des travaux,
  modèles réutilisables, garantie FGCMPI, financement (crédit bancaire, aide CNL)
* Appels de fonds, encaissements, suivi des retards
* Mise à jour de l'avancement : les échéances liées deviennent automatiquement exigibles
* Livraison : constatation du chiffre d'affaires, solde des avances, sortie de stock
* Résiliation avec restitution des fonds et indemnité éventuelle
* Situations de travaux des entreprises, avec retenue de garantie
* **Coût de revient** : budget vs réalisé par poste, répartition sur les lots, marge par logement

> **Le point comptable qui compte.** Les sommes encaissées avant livraison sont
> des **avances** (compte 4191), pas du chiffre d'affaires. Le produit n'est
> constaté qu'à la livraison du lot (compte 7011). Entre-temps, les dépenses de
> chantier sont stockées en travaux en cours (332 / 723) puis transférées en
> produits finis (355 / 724) à l'achèvement.

### Déclaré et hors déclaration

Chaque écriture porte un **périmètre** : `déclaré` ou `hors déclaration`.

* Les déclarations fiscales (G50, IBS, livres de TVA) ne retiennent que le
  périmètre déclaré, et **le disent en tête de document**. La G50 indique en
  clair combien d'opérations en sont exclues et pour quel montant.
* Le bilan, le compte de résultat et la balance se calculent sur le périmètre
  choisi et le mentionnent sur l'export.
* Un sélecteur global bascule entre la vue déclarée, la vue hors déclaration
  et la vue réelle qui additionne les deux — celle qui sert à piloter la
  trésorerie effective.
* L'écran **Déclaré / hors décl.** compare les deux, mois par mois, et donne
  la part que représente le hors déclaration.

**Saisie en totalité.** Une opération réelle se décompose souvent en une part
déclarée et une part qui ne l'est pas. Le périmètre `totalité` permet de la
saisir d'un seul geste : chaque ligne reçoit un montant déclaré et un montant
non déclaré, l'écran affiche le total et sa décomposition, et contrôle que
**chaque part s'équilibre séparément**.

L'enregistrement produit **deux écritures reliées par une référence
d'opération** (`ecritures.operation_ref`) plutôt qu'une écriture hybride : une
écriture appartient tout entière à un périmètre, faute de quoi la G50, le bilan
et la liasse ne seraient plus établissables sur le seul déclaré. Le journal
rappelle sur chaque part le montant de l'opération entière.

### Signaler un problème

Les pannes rencontrées jusqu'ici ont été diagnostiquées depuis des **photos
d'écran**. L'application prépare désormais elle-même un rapport : version,
système, écran concerné et dernières lignes de `donnees/journal.log`.

* L'utilisateur **voit le rapport avant de l'envoyer**.
* Il ne contient **aucune donnée comptable** — ni montant, ni nom de tiers, ni
  raison sociale — et les chemins absolus sont masqués, car ils portent le nom
  de la session.
* Trois moyens, sans dépendance : **copier**, **enregistrer un fichier**, ou
  **envoyer** par un canal Telegram ou courriel déjà configuré. Sans canal,
  l'application le dit et propose les deux autres.

### Reprise de données depuis Excel

L'application **fournit les en-têtes** : le comptable télécharge un modèle
`.xlsx`, le remplit avec ses propres données et le redépose. **Dix-huit
modèles** couvrent la reprise complète d'un dossier déjà tenu ailleurs —
plan comptable, tiers, trésorerie, balance d'ouverture, biens, mandats, baux,
quittances, programmes, lots, contrats VSP, échéanciers, immobilisations,
salariés, factures, règlements et écritures.

La **balance d'ouverture** est la pièce maîtresse : elle reprend les soldes à
une date choisie et produit une écriture d'à-nouveaux unique dans le journal AN,
après avoir vérifié que débits et crédits s'équilibrent. C'est elle qui permet
de reprendre un dossier en cours d'année.

**L'import reprend la situation, il ne recomptabilise pas le passé.** Baux,
lots, contrats, quittances et immobilisations décrivent l'existant sans générer
d'écriture ; la comptabilité est portée par la balance d'ouverture ou par les
écritures importées. Sans cette règle, tout serait compté deux fois.

Les modèles sont **déclaratifs** (`Colonne(nom, …, champ, type, reference)`) :
conversion, contrôle des valeurs admises, résolution des références et
détection des doublons sont génériques, une nouvelle table ne demande qu'une
description.

Les listes **Ventes** et **Achats** portent les deux actions directement :
*Importer* ouvre le modèle correspondant, *Exporter* produit un classeur — une
feuille d'en-têtes de factures, une feuille de lignes — en respectant les
filtres affichés, périmètre compris.

* **Rien n'est refusé, rien n'est perdu.** L'import écrit ce qui est
  écrivable et **met le reste de côté** : les lignes non écrites attendent
  dans l'application (table `lignes_attente`), avec leurs valeurs telles
  qu'elles étaient dans le fichier et la raison en une phrase. On les corrige
  **dans une grille, sur place**, et elles repartent — pas de retour au
  tableur, pas d'import à refaire.
* **Ce qui attend quelque chose repart tout seul.** Après chaque import,
  l'application rejoue ce qui attendait : une quittance déposée avant son bail
  est reprise d'elle-même le jour où le bail arrive. Personne n'a à y penser.
* **Un encaissement sans facture reste un encaissement** : il est repris
  *non affecté*, garde le numéro qu'il cite (`reglements.reference_facture`),
  et se rattache seul quand la facture est enregistrée — montant réglé et
  statut de la facture suivent.
* **Ce qui reste refusé est ce qui produirait des comptes faux** : une
  écriture déséquilibrée, une date impossible. Elle n'entre pas en
  comptabilité, elle attend d'être corrigée — ce n'est pas la même chose.
* L'import se fait **en deux temps** : contrôle complet sans écriture, puis
  validation. Chaque ligne mise de côté l'est avec son **numéro de ligne**.
* **Aucun ordre à respecter.** Les fichiers se déposent dans l'ordre qui
  arrange celui qui les a, et seulement ceux qui l'intéressent. Ce qu'un
  fichier cite et que le dossier ne connaît pas — un compte, un tiers, un
  journal, un bien, un programme, un lot — est **créé avec lui**, avec son
  seul nom, et marqué `incomplet`. C'est **annoncé avant** (« 3 comptes et 12
  tiers seront créés au passage », avec la liste), **redit après**, et
  **rattaché à la reprise** : l'annuler les reprend, sauf ceux qui servent
  déjà ailleurs. Un compte hérite de son compte de rattachement — nature,
  rubrique, caractère lettrable ; un tiers est rangé d'après le sien (411
  client, 401 fournisseur, 4671 mandant, 421 salarié).
* **Le fichier qui décrit vraiment remplit la fiche.** Une fiche `incomplet`
  n'est pas « déjà enregistrée » : l'import qui la décrit la **complète** au
  lieu de la sauter. Passer les lots avant les programmes revient donc à les
  passer après. Une fiche déjà complète, elle, n'est jamais réécrite.
* **Quatre renvois restent exigés, et ce n'est pas un ordre** : un règlement
  se rattache à une facture, une quittance à un bail, une échéance à un
  contrat VSP, un mouvement à un compte de trésorerie — sans quoi il irait se
  poser sur un compte comptable choisi au hasard. Le message dit lequel et
  pourquoi. Seule autre limite : un lot demande que sa colonne *Programme*
  soit renseignée, faute de quoi on ne sait pas où le ranger.
* La santé du dossier compte les fiches qui restent à compléter — en
  information, pas en alerte : rien n'est faux, il manque un NIF ou une
  surface.
* Le fichier est lu **comme un journal se lit** : une cellule vide reprend la
  valeur de la ligne du dessus, de sorte que la date, le journal et le numéro
  ne s'écrivent qu'une fois par écriture. Le journal est reconnu par son code
  ou par son intitulé, et la ligne de totaux d'un tableau est écartée d'elle-même
  puis signalée.
* Les écritures passent par `comptabilite.enregistre_ecriture`, donc par les
  mêmes contrôles que la saisie manuelle, et arrivent **en brouillon**.
* Les lignes partageant un même « N° écriture » forment une écriture et doivent
  s'équilibrer ; la colonne *Périmètre* permet de mêler déclaré et non déclaré
  dans un seul fichier.
* Lecture `.xlsx` en Python pur (`noyau/tableur.py`), CSV francophone accepté,
  en-têtes reconnus malgré accents, casse et synonymes usuels.

**Défaire un import.** Se tromper de fichier, ou passer le même deux fois,
arrive. Chaque reprise reste inscrite au journal des imports, avec de quoi
l'annuler — et l'application choisit elle-même comment, en le disant avant
d'agir :

| Cas | Ce qu'elle fait |
|---|---|
| L'import est le dernier à avoir numéroté ses journaux | **Suppression** : les écritures partent, les compteurs repartent d'où ils venaient, aucun trou dans la numérotation |
| Des écritures ont été passées depuis | **Contre-passation** : chaque écriture importée est extournée à une date choisie ; tout reste visible |
| Import de référentiel (tiers, comptes, biens…) | Ce qui sert déjà reste en place, le reste est retiré, et l'écran dit lequel est lequel |

Un exercice clôturé, une ligne lettrée ou une facture réglée depuis interdisent
la suppression. Ce que l'écran annonce n'est pas une description écrite à la
main : c'est le résultat de l'annulation réelle, jouée puis annulée — ce qui est
annoncé est donc exactement ce qui se produira.

### Fiscalité algérienne

* **Déclaration G n° 50** calculée depuis la comptabilité : TVA collectée et déductible,
  précompte reporté, retenues IRG, droit de timbre, TAP le cas échéant
* Écriture de liquidation de TVA et enregistrement du paiement
* Livres des ventes et des achats (justificatifs de la G50)
* **IBS** : résultat fiscal avec réintégrations et déductions, acomptes provisionnels
* Calendrier des obligations : G50, CNAS, acomptes IBS, liasse fiscale, DAS
* Droit de timbre calculé automatiquement sur les règlements en espèces

### Déclarations annuelles

Dans **Fiscalité → Déclarations annuelles**, les deux états de début d'année,
déduits de ce qui est déjà saisi :

* La **déclaration annuelle des salaires** (série G n° 29) : chaque salarié avec
  son matricule, son n° de sécurité sociale, ses mois payés, son brut, sa CNAS,
  sa base IRG, l'IRG retenu et le net payé.
* L'**état des clients** : les ventes de l'année par client, avec son identité
  fiscale. Un client sans NIF est signalé ; un seuil facultatif écarte les
  petits montants, et l'écran dit combien.

**Chacun porte son recoupement**, à l'écran comme sur le papier — c'est ce qui
fait leur valeur. Pour la DAS : les bulletins, le cumul des G50 déposées et le
compte 4421 doivent porter le même IRG. Pour l'état des clients : le total des
factures doit égaler les comptes de produits, faute de quoi une vente a été
comptabilisée sans facture et manquerait à l'état.

### Paie

* Salariés, primes soumises et non soumises à cotisation
* Bulletins : CNAS part salariale et patronale, IRG au barème progressif avec abattement
* Écriture de paie, règlement des salaires, livre de paie exportable
* Simulateur brut → net → coût employeur

### Immobilisations

* Registre, plans d'amortissement linéaire et dégressif, prorata temporis au mois
* Écriture d'acquisition, dotations de l'exercice, cession avec plus ou moins-value

### Résumés sur téléphone

Le dirigeant reçoit la situation sans se connecter à l'application :
trésorerie, chiffre d'affaires, résultat, loyers impayés, échéances VSP,
avancement des programmes et prochaine échéance déclarative.

* **Telegram** — gratuit et instantané. Le destinataire s'appaire avec un code
  à six caractères, puis reçoit le résumé à l'heure choisie. Il peut écrire
  « situation », « trésorerie » ou « loyers » et obtenir la réponse dans la
  seconde. Un téléphone non appairé n'obtient aucune donnée.
* **Courriel** — via le serveur SMTP de votre choix.

Le message part du poste du comptable. Aucune donnée n'est hébergée ailleurs,
aucun service payant n'intervient.

---

## ⚠️ Les taux fiscaux sont à vérifier chaque année

La loi de finances algérienne modifie régulièrement les taux et barèmes.
**L'application ne les met pas à jour toute seule.**

Les valeurs livrées (TVA 19 %, CNAS 9 % / 26 %, IBS 23 % BTPH et 26 % services,
barème IRG, droit de timbre) sont des **valeurs par défaut** pour que
l'application fonctionne dès l'installation. Certaines sont explicitement
marquées « À VÉRIFIER » — en particulier :

* **la TAP**, livrée désactivée : elle a fait l'objet de suppressions et
  d'aménagements successifs. Activez-la et renseignez son taux si elle
  s'applique encore à votre activité ;
* **le barème IRG et son abattement**, à recaler sur la loi de finances de l'exercice ;
* **le minimum d'imposition IBS** et **le droit de timbre**.

Rendez-vous dans **Fiscalité → Taux et barèmes**, choisissez l'exercice et
ajustez. Chaque année dispose de son propre jeu de paramètres : les déclarations
passées gardent les taux qui leur étaient applicables. Aucun taux n'est codé en
dur dans le programme.

L'application est une **aide à la déclaration** : elle calcule à partir de votre
comptabilité, vous vérifiez et reportez sur l'imprimé officiel.

---

## Vos données

Tout est dans le dossier `donnees/` situé à côté de l'application :

```
donnees/
├── comptabilite.db            la base de données — à sauvegarder en priorité
├── pieces_justificatives/     factures et documents scannés
├── exports/                   fichiers Excel produits
├── sauvegardes/               copies de sécurité horodatées
└── modeles_documents/         vos modèles personnalisés
```

Vous pouvez déplacer ce dossier où vous voulez (clé USB, disque réseau, dossier
synchronisé) et le désigner au lancement :

```bash
python3 app.py --donnees /chemin/vers/le/dossier
```

### Mises à jour

Le chemin complet — installation ancienne, dépôt du paquet, retour de
l'application sur la nouvelle version avec ses données intactes — est rejoué à
chaque fois par `outils/test_mise_a_jour.py` sur une copie jetable. Il vérifie
aussi que **l'état mixte se voit** : si les fichiers sont remplacés sans que
l'application se relance, elle affiche un bandeau et ses messages d'erreur en
donnent la raison, au lieu du « Ressource introuvable » qui n'apprend rien.

Le code et les données vivent séparément : une mise à jour remplace le
programme, jamais le dossier `donnees/`.

Le chemin normal passe par l'application : **Paramètres → Mise à jour**,
le fichier reçu est déposé, contrôlé, puis installé en un clic. L'application se
ferme, se met à jour et se rouvre toute seule, **en rejouant ses options de
lancement** (port, dossier de données) pour ne pas rouvrir sur une autre
comptabilité. Le paquet est refusé s'il n'est pas une version de Cabinet Immo
ou s'il est incomplet.

**On peut aussi reculer.** Chaque version installée est conservée sur le poste
(`donnees/versions/`), et l'écran en dresse la liste : on y revient d'un bouton,
sans redemander le fichier à personne. Deux situations, distinguées parce
qu'elles n'ont pas le même prix :

| Situation | Ce qui se passe |
|---|---|
| La version visée sait lire la base telle qu'elle est | **Seul le programme recule.** Rien de ce qui a été saisi n'est perdu. Une confirmation suffit |
| Elle est antérieure au schéma de la base | Le programme seul ne suffit pas : la base ne défait pas ses migrations. Il faut **remettre les données de l'époque** — l'écran fait choisir la sauvegarde, chiffre ce qui sera perdu, et garde l'état actuel pour que le mouvement reste réversible |
| Même version que celle installée | **Réinstallation** : la réponse à une mise à jour restée à mi-chemin |

En ligne de commande :

```bash
python3 outils/mise_a_jour.py nouvelle_version.zip   # ou METTRE-A-JOUR.bat
python3 outils/mise_a_jour.py --annuler              # retour arrière
```

L'outil sauvegarde les données, met la version actuelle de côté, installe la
nouvelle, applique les **migrations de schéma** puis vérifie l'intégrité et
l'équilibre de la comptabilité. Si l'un de ces contrôles échoue, il restaure
automatiquement la version précédente.

Les migrations sont versionnées et idempotentes : une base existante reçoit
les nouvelles colonnes et tables sans qu'aucune donnée saisie ne soit modifiée,
et une copie de la base est prise avant toute transformation.

### Sauvegardes

* Une sauvegarde automatique est créée à chaque fermeture propre de l'application.
* **Paramètres → Sauvegarde** permet d'en créer une à la demande, de la télécharger
  et de restaurer une version antérieure.
* Les 30 dernières sauvegardes sont conservées.
* **Copiez régulièrement le dossier `donnees/` sur un support externe.** Une
  sauvegarde qui reste sur le même disque que l'original ne protège de rien.

### Sécurité

* Le serveur écoute par défaut sur `127.0.0.1` : l'application n'est accessible
  que depuis votre poste.
* Mots de passe stockés en PBKDF2-SHA256 (240 000 itérations).
* Trois rôles : administrateur, comptable, consultation seule.
* Journal d'audit horodaté de toutes les opérations sensibles.

Pour un usage à plusieurs postes sur le réseau local :
`python3 app.py --hote 0.0.0.0` — à ne faire que sur un réseau de confiance.

---

## Vérifier que tout fonctionne

```bash
python3 outils/test_fonctionnel.py   # 96 contrôles métier et comptables
python3 outils/test_http.py          # 63 contrôles du serveur et de l'interface
python3 outils/test_comptable.py     # 395 contrôles de conformité comptable
python3 outils/test_mise_a_jour.py   # 39 contrôles du chemin de mise à jour
python3 app.py --verifier            # intégrité de vos données
```

Le test fonctionnel simule une année complète d'activité sur les deux métiers et
vérifie à chaque étape que la comptabilité reste équilibrée, que les produits
sont constatés au bon moment et que la clôture se déroule correctement.

Le test de conformité comptable, lui, ne regarde pas l'interface : il attaque
l'application par ses interfaces de programmation et vérifie les règles qui,
si elles cèdent, produisent des comptes **faux sans que rien ne le signale**.
Treize familles, lançables séparément
(`python3 outils/test_comptable.py perimetre`) :

| Suite | Ce qu'elle vérifie |
|---|---|
| `conformite` | partie double, cohérence des états entre eux, TVA, IRG, VSP, gestion locative |
| `limites` | ce que le logiciel doit **refuser** : déséquilibre, date impossible, compte inexistant, écriture d'un exercice clos |
| `cloture` | l'exercice clos ne bouge plus, les à-nouveaux reportent les seuls comptes de bilan, l'extourne annule sans effacer |
| `perimetre` | l'étanchéité entre le déclaré et le hors déclaration |
| `cycles` | les cycles métier en mouvement : numérotation, saisies simultanées, une avance sur plan qui devient produit à la livraison, un loyer encaissé qui repart chez son propriétaire |
| `reprises` | annuler un import déjà validé sans laisser de trou dans la numérotation ni effacer ce qui sert déjà |
| `creation` | l'import crée ce qu'il cite, et le complète quand le vrai fichier arrive |
| `attente` | rien n'est refusé, rien n'est perdu : ce qui ne passe pas attend, se corrige sur place et repart tout seul |
| `correction` | corriger une écriture en place — même numéro, mêmes justificatifs, lettrage défait proprement, rapprochement clôturé protégé |
| `sante` | les contrôles de santé du dossier, chacun mis à l'épreuve sur une anomalie provoquée pour lui |
| `annuelles` | la DAS et l'état des clients, et surtout leurs recoupements |
| `relances` | ce qui est dû et depuis quand, et la lettre à ses trois niveaux |
| `banque` | le relevé de la banque, lu et rapproché — sens des colonnes et écart de date compris |

La suite `perimetre` est la plus importante du lot. Chaque montant hors
déclaration y est un multiple de 7 777, donc reconnaissable ; on vérifie
ensuite qu'aucun de ces montants n'apparaît dans une G50, un bilan fiscal, un
calcul d'IBS ou un livre de TVA — et, réciproquement, que ces états **annoncent
ce qu'ils ont écarté** plutôt que de l'omettre en silence.

---

## Organisation du code

```
app.py                      point d'entrée
noyau/
├── config.py               emplacement du dossier de données, options
├── base.py                 accès SQLite, transactions, compteurs, audit
├── schema.sql              schéma complet de la base
├── serveur.py              serveur HTTP, routeur, sessions, mots de passe
├── util.py                 montants en centimes, dates, montants en lettres
└── tableur.py              génération de fichiers Excel en Python pur
modules/
├── systeme.py              installation, connexion, dossiers, tableau de bord
├── comptabilite.py         écritures, grand livre, balance, lettrage, clôture
├── tiers.py                clients, fournisseurs, propriétaires, balance auxiliaire
├── facturation.py          factures, avoirs, règlements
├── tresorerie.py           caisses, banques, rapprochement bancaire
├── agence.py               biens, mandats, transactions, baux, loyers
├── promotion.py            programmes, lots, VSP, coût de revient
├── fiscalite.py            G50, TVA, IBS, calendrier des obligations
├── paie.py                 salariés, bulletins, CNAS, IRG
├── immobilisations.py      amortissements et cessions
├── etats.py                bilan, TCR, flux de trésorerie
├── documents.py            éditions imprimables
├── fichiers.py             pièces jointes, sauvegarde, restauration
├── rapports.py             résumés Telegram et courriel
└── imports.py              reprise depuis Excel (modèles, contrôle, création du manquant)
reference/
├── plan_comptable_scf.json nomenclature SCF et modèles d'échéancier
└── parametres_fiscaux.json taux et barèmes par année
web/                        interface (HTML, CSS et JavaScript sans dépendance)
outils/
├── test_fonctionnel.py     96 contrôles métier
├── test_http.py            63 contrôles serveur et interface
├── test_comptable.py       395 contrôles de conformité comptable
├── test_mise_a_jour.py     39 contrôles du chemin de mise à jour
├── donnees_demonstration.py jeu d'essai complet
├── installer.ps1           installation Windows sans droits administrateur
├── installer.py            même installation, sans fichier bloqué par les messageries
├── faire_paquet.py         fabrique les paquets de distribution
└── mise_a_jour.py          mise à jour avec migrations et retour arrière
```

### Deux règles internes

**Aucun montant n'est manipulé en nombre à virgule flottante.** Tout est stocké
et calculé en centimes entiers ; les taux sont en centièmes de pour-cent
(19 % = 1900). Les répartitions garantissent qu'aucun centime ne se perd.

**Il n'existe qu'un seul chemin d'écriture comptable.** Tous les modules passent
par `comptabilite.enregistre_ecriture`, qui contrôle l'équilibre, l'existence des
comptes, l'ouverture de l'exercice, enregistre l'origine du mouvement et son
périmètre déclaratif.

**Le schéma est versionné.** `noyau/base.py` porte un numéro de version et une
liste de migrations idempotentes. Toute évolution de structure passe par là,
ce qui rend les mises à jour sûres sur une base contenant déjà des écritures.

---

## Raccourcis clavier

| Raccourci | Action |
|---|---|
| `Ctrl + E` | Nouvelle écriture |
| `Ctrl + F` | Nouvelle facture |
| `Ctrl + T` | Liste des tiers |
| `Ctrl + K` | Rechercher partout (nom, n° de facture, montant) |
| `Échap` | Fermer l'aide ou la fenêtre en cours |
| `Échap` | Fermer la fenêtre en cours |

---

## Questions fréquentes

**Puis-je gérer l'agence et la promotion dans deux dossiers séparés ?**
Oui. Créez un second dossier dans Paramètres et basculez de l'un à l'autre par le
sélecteur en haut à gauche. Chaque dossier a sa propre comptabilité, ses
exercices et ses déclarations. Choisissez « mixte » si les deux activités sont
exercées dans la même entité juridique.

**L'application fonctionne-t-elle sans Internet ?** Oui, entièrement.

**Que se passe-t-il si je saisis une écriture déséquilibrée ?** Elle est refusée
avec le montant exact de l'écart. Le contrôle est aussi affiché en direct pendant
la saisie.

**Comment corriger une facture déjà validée ?** Par un avoir. Les écritures
validées ne sont pas modifiables afin de préserver la piste d'audit exigée en cas
de contrôle.

**Comment mon père voit-il les chiffres sans utiliser l'application ?**
Paramètres → Notifications : il reçoit un résumé sur Telegram, automatiquement
ou à la demande. Voir le [GUIDE.md](GUIDE.md), section 3.

**Puis-je consulter depuis l'étranger ?** Oui, via un réseau privé Tailscale
entre les deux ordinateurs — rien n'est exposé sur Internet. Voir le
[GUIDE.md](GUIDE.md), section 2.

**Une mise à jour peut-elle effacer mes données ?** Non. Le dossier `donnees/`
n'est jamais touché, une sauvegarde est prise avant chaque mise à jour, et
l'outil revient automatiquement en arrière si un contrôle échoue.

**Et si une nouvelle version ne me convient pas ?** On revient à la
précédente : Paramètres → Mise à jour liste les versions présentes sur le
poste. Tant que la version visée sait lire la base, seul le programme recule
et rien n'est perdu. Si elle est plus ancienne que la structure de la base, il
faut aussi remettre les données de l'époque — l'écran le dit, fait choisir la
sauvegarde, et garde l'état actuel.

**Puis-je rouvrir un exercice clôturé ?** Oui, un administrateur le peut
(Paramètres → Exercices). Vérifiez ensuite les écritures de clôture et
d'à-nouveaux existantes avant de re-clôturer.
