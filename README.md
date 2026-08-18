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

```bash
python3 outils/donnees_demonstration.py --donnees donnees_demo
python3 app.py --donnees donnees_demo
```

Identifiant `demo`, mot de passe `demo1234`. Vous obtenez une année d'activité
complète : programme de 24 logements, contrats VSP, baux, loyers, paie et
déclarations. **Utilisez un dossier séparé pour votre comptabilité réelle.**

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
| Saisie | Partie double avec contrôle d'équilibre en direct ; une écriture déséquilibrée est refusée |
| Grand livre | Par compte, par tiers, avec solde progressif et filtre « non lettrées » |
| Balance | Générale ou agrégée par classe, avec reports à nouveau |
| Lettrage | Manuel et automatique (rapprochement facture ↔ règlement d'un même tiers) |
| Rapprochement bancaire | Pointage des mouvements face au relevé, calcul de l'écart |
| États financiers | Bilan, compte de résultat par nature (TCR), tableau des flux de trésorerie |
| Clôture | Contrôles préalables, virement du résultat en 120/129, génération des à-nouveaux, verrouillage |
| Exports | Excel natif : balance, grand livre, livre-journal, liasse, livres de TVA |

Toute opération métier génère son écriture comptable automatiquement, avec
traçabilité de son origine. Une écriture validée n'est plus modifiable :
on la corrige par extourne, ce qui préserve la piste d'audit.

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

* L'import se fait **en deux temps** : contrôle complet sans écriture, puis
  validation. Chaque anomalie est rapportée avec son **numéro de ligne**, et le
  message dit quoi faire — un compte absent propose les plus proches du plan,
  un journal inconnu liste ceux qui existent.
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

### Fiscalité algérienne

* **Déclaration G n° 50** calculée depuis la comptabilité : TVA collectée et déductible,
  précompte reporté, retenues IRG, droit de timbre, TAP le cas échéant
* Écriture de liquidation de TVA et enregistrement du paiement
* Livres des ventes et des achats (justificatifs de la G50)
* **IBS** : résultat fiscal avec réintégrations et déductions, acomptes provisionnels
* Calendrier des obligations : G50, CNAS, acomptes IBS, liasse fiscale, DAS
* Droit de timbre calculé automatiquement sur les règlements en espèces

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

Le code et les données vivent séparément : une mise à jour remplace le
programme, jamais le dossier `donnees/`.

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
python3 outils/test_http.py          # 40 contrôles du serveur et de l'interface
python3 app.py --verifier            # intégrité de vos données
```

Le test fonctionnel simule une année complète d'activité sur les deux métiers et
vérifie à chaque étape que la comptabilité reste équilibrée, que les produits
sont constatés au bon moment et que la clôture se déroule correctement.

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
└── imports.py              reprise de données depuis Excel (modèles + contrôle)
reference/
├── plan_comptable_scf.json nomenclature SCF et modèles d'échéancier
└── parametres_fiscaux.json taux et barèmes par année
web/                        interface (HTML, CSS et JavaScript sans dépendance)
outils/
├── test_fonctionnel.py     96 contrôles métier
├── test_http.py            40 contrôles serveur et interface
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

**Puis-je rouvrir un exercice clôturé ?** Oui, un administrateur le peut
(Paramètres → Exercices). Vérifiez ensuite les écritures de clôture et
d'à-nouveaux existantes avant de re-clôturer.
