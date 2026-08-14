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

## Démarrer

```bash
python3 app.py
```

Le navigateur s'ouvre sur `http://127.0.0.1:8781`. Au premier lancement, vous
créez votre compte et le dossier comptable de votre entreprise.

Sous Windows : double-cliquez sur `LANCER.bat`.
Sous Linux ou macOS : double-cliquez sur `lancer.sh` (ou `./lancer.sh`).

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
python3 outils/test_fonctionnel.py   # 80 contrôles métier et comptables
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
└── fichiers.py             pièces jointes, sauvegarde, restauration
reference/
├── plan_comptable_scf.json nomenclature SCF et modèles d'échéancier
└── parametres_fiscaux.json taux et barèmes par année
web/                        interface (HTML, CSS et JavaScript sans dépendance)
outils/                     tests et générateur de données de démonstration
```

### Deux règles internes

**Aucun montant n'est manipulé en nombre à virgule flottante.** Tout est stocké
et calculé en centimes entiers ; les taux sont en centièmes de pour-cent
(19 % = 1900). Les répartitions garantissent qu'aucun centime ne se perd.

**Il n'existe qu'un seul chemin d'écriture comptable.** Tous les modules passent
par `comptabilite.enregistre_ecriture`, qui contrôle l'équilibre, l'existence des
comptes, l'ouverture de l'exercice et enregistre l'origine du mouvement.

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

**Puis-je rouvrir un exercice clôturé ?** Oui, un administrateur le peut
(Paramètres → Exercices). Vérifiez ensuite les écritures de clôture et
d'à-nouveaux existantes avant de re-clôturer.
