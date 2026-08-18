# Guide pratique

Trois publics, trois sections. Chacun ne lit que la sienne.

---

# 1. Pour le comptable (installation sur le PC)

## Installer — une seule fois

Vous avez reçu **soit** un dossier `.zip`, **soit** un seul fichier
`cabinet-immo-…-installateur.py`. Suivez la ligne qui correspond.

### A. Vous avez reçu le fichier `…-installateur.py`

1. Double-cliquez dessus.
2. Il indique où il va s'installer (vos `Documents`) — Entrée pour accepter.
3. Répondez aux deux questions, Entrée à chaque fois.

> **Si le double-clic n'ouvre rien**, Python n'est pas installé sur ce PC.
> Installez-le une seule fois depuis <https://www.python.org/downloads/> en
> cochant **« Add Python to PATH »**, puis double-cliquez à nouveau.

### B. Vous avez reçu l'archive `cabinet-immo-….zip`

1. Clic droit → **Extraire tout**, dans `Documents`.
2. Ouvrez le dossier extrait, double-cliquez sur **`INSTALLER.bat`**.
3. Répondez aux deux questions (Entrée pour accepter) :
   - *Démarrer automatiquement à chaque ouverture de session ?* → **Oui**
   - *Ouvrir l'application maintenant ?* → **Oui**

> Ici, **si Python n'est pas installé**, l'installateur le télécharge tout seul
> (11 Mo) et le range dans le dossier de l'application. Rien n'est installé
> dans Windows, aucun mot de passe administrateur n'est demandé.
>
> **Si le téléchargement échoue** (pas d'Internet au moment de l'installation) :
> installez Python depuis <https://www.python.org/downloads/> en cochant
> **« Add Python to PATH »**, puis relancez `INSTALLER.bat`.

Dans les deux cas c'est fini : un raccourci **Cabinet Immo** est apparu sur le
Bureau.

## Premier démarrage

Le navigateur s'ouvre sur l'application. Vous créez :
- votre compte (identifiant + mot de passe) ;
- le dossier de l'entreprise (raison sociale, NIF, registre de commerce…).

Ensuite, le tableau de bord affiche **« Pour bien démarrer »** : la liste de ce
qu'il reste à faire, cochée au fur et à mesure. Elle disparaît toute seule une
fois tout réglé. Suivez-la, elle remplace la lecture de ce guide.

### Essayer sans rien risquer

**Paramètres → Import de données → Créer un dossier d'essai.** Vous obtenez une
année d'activité complète — un programme de logements, des ventes sur plan, des
baux, des loyers, la paie, les déclarations — dans un dossier séparé du vôtre.
Vous pouvez tout y essayer, et le supprimer d'un clic quand vous avez compris.

### Où sont vos données

Si votre comptabilité se trouve dans un dossier **OneDrive, Google Drive ou
Dropbox**, l'application vous prévient. Ce n'est pas un détail : ces services
recopient la base pendant que l'application écrit dedans, ce qui peut
**l'abîmer définitivement**. Déplacez le dossier `donnees` hors de l'espace
synchronisé — une sauvegarde sur clé USB protège mieux, et sans risque.

## Vérifier les taux avant la première déclaration

**Avant votre première déclaration**, allez dans **Fiscalité → Taux et barèmes**
et vérifiez chaque valeur avec la loi de finances de l'année. Les valeurs
livrées sont des valeurs de départ, pas une référence légale.

## Au quotidien

| Pour… | Aller dans |
|---|---|
| Saisir une facture | Factures → + Facture |
| Encaisser un loyer | Agence → Loyers |
| Encaisser une tranche VSP | Promotion → Échéancier |
| Voir ce qu'on doit aux propriétaires | Agence → Propriétaires |
| Préparer la G50 | Fiscalité → Déclaration G50 |
| Voir la marge d'un programme | Promotion → Programmes → Budget & coût de revient |

Raccourcis : `Ctrl+E` écriture · `Ctrl+F` facture · `Ctrl+T` tiers · `Échap` fermer.

## Déclaré et hors déclaration

Chaque opération porte un **périmètre**, choisi à la saisie :

- **Déclaré** — entre dans la G50, le bilan et la liasse fiscale ;
- **Hors déclaration** — comptabilisé et suivi, mais exclu des déclarations ;
- **Totalité** — le montant réel, réparti entre les deux, en une seule saisie.

### Saisir une opération en totalité

C'est le cas courant : une vente de 16 000 000 DA dont 10 000 000 sont
facturés et 6 000 000 réglés en espèces. Dans la fenêtre de saisie, choisissez
**Périmètre → Totalité**. Deux colonnes supplémentaires apparaissent :

| Compte | Débit déclaré | Débit non décl. | Crédit déclaré | Crédit non décl. |
|---|---|---|---|---|
| 411 Clients | 10 000 000 | 6 000 000 | | |
| 7011 Ventes | | | 10 000 000 | 6 000 000 |

Le bas de la fenêtre affiche **Opération 16 000 000 · dont déclaré 10 000 000 ·
dont non déclaré 6 000 000**, et contrôle que **chacune des deux parts
s'équilibre** de son côté.

À la validation, l'application enregistre **deux écritures reliées entre
elles**. Au journal, chacune rappelle « part d'une opération de 16 000 000,00 ».

> **Pourquoi deux écritures et non une seule ?** Une écriture appartient tout
> entière à un périmètre : c'est ce qui permet d'éditer la G50 et le bilan sur
> le seul déclaré, sans retouche. Vous saisissez une fois, vous consultez le
> total d'un bloc, mais les déclarations restent justes.

Le sélecteur en haut à gauche change ce que vous regardez :

| Choix | Ce que vous voyez |
|---|---|
| **Tout — vue réelle** | l'activité complète, pour piloter la trésorerie |
| **Déclaré** | exactement ce qui part à l'administration |
| **Hors déclaration** | uniquement ce qui n'y figure pas |

L'écran **Déclaré / hors décl.** compare les deux et donne la part que
représente le hors déclaration.

> Chaque état imprimé ou exporté indique en tête le périmètre qu'il couvre, et
> la G50 rappelle en clair combien d'opérations en sont exclues. C'est ce qui
> évite de déposer une déclaration incohérente avec ce que la comptabilité
> contient réellement.

## Reprendre vos données existantes (Excel)

Vous avez déjà des fichiers Excel ? L'application vous donne les en-têtes, vous
les remplissez, vous les réintégrez.

1. **Paramètres → Import de données**.
2. En face du type voulu, **Télécharger le modèle**. Le fichier obtenu contient
   déjà la bonne ligne d'en-têtes, une ligne d'exemple et une notice.
3. Remplissez-le avec vos données, **sans modifier la ligne d'en-têtes**.
   Effacez la ligne d'exemple.
4. Revenez sur l'écran, choisissez le fichier, **Contrôler le fichier**.

L'application lit tout **sans rien enregistrer** et affiche les anomalies avec
leur **numéro de ligne** : compte inexistant, date impossible, écriture
déséquilibrée, doublon… Corrigez le fichier et recommencez, ou importez
uniquement les lignes saines.

### L'ordre compte

Chaque étape s'appuie sur la précédente : une facture a besoin de son tiers, un
bail de son bien, un contrat de son lot. L'écran affiche un **numéro d'ordre**
devant chaque modèle — suivez-le.

| # | Modèle | Contenu |
|---|---|---|
| 1 | Plan comptable | vos comptes en plus du plan SCF livré |
| 2 | Tiers | clients, fournisseurs, propriétaires, locataires, acquéreurs |
| 3 | Comptes de trésorerie | vos banques et vos caisses |
| **4** | **Balance d'ouverture** | **les soldes à la date de reprise** |
| 5 | Biens | le portefeuille de l'agence |
| 6 | Mandats | mandats de vente, de location et de gestion |
| 7 | Baux | les baux en cours |
| 8 | Loyers et quittances | l'historique des loyers appelés |
| 9 | Programmes | les opérations de promotion |
| 10 | Lots | les logements et locaux de chaque programme |
| 11 | Contrats VSP | les ventes sur plan signées |
| 12 | Échéanciers VSP | les tranches de paiement de chaque contrat |
| 13 | Immobilisations | le parc existant |
| 14 | Salariés | pour la paie |
| 15-16 | Factures de vente / d'achat | une ligne de fichier par ligne de facture |
| 17 | Règlements | les encaissements et décaissements déjà intervenus |
| 18 | Écritures comptables | le journal détaillé, si vous le reprenez |

### La balance d'ouverture, l'étape qui compte

C'est elle qui vous permet de **prendre le train en marche**. Vous indiquez,
pour chaque compte, son solde à la date de reprise — au débit ou au crédit,
jamais les deux — et l'application produit **une seule écriture d'à-nouveaux**
dans le journal AN, à la date que vous choisissez.

Le total des débits doit égaler le total des crédits. Sinon l'application
refuse le fichier **en indiquant le montant exact de l'écart**.

> **Balance d'ouverture ou écritures détaillées : choisissez.** Les deux
> ensemble compteraient deux fois la même chose. La balance suffit pour
> repartir ; le journal détaillé n'est utile que si vous voulez retrouver
> l'historique complet dans l'application.

### Remplissez le fichier comme vous tenez un journal

Vous n'avez pas à répéter ce qui ne change pas. **Une case laissée vide reprend
la valeur de la ligne du dessus** — c'est ainsi qu'on tient un journal, sur
papier comme dans un tableur :

| N° écriture | Date | Journal | Libellé | Compte | Débit | Crédit |
|---|---|---|---|---|---|---|
| 1 | 05/01/2026 | CAISSE | Encaissement loyer | 411 | | 9 000 |
| | | | Encaissement loyer | 531 | 9 000 | |
| 2 | 12/01/2026 | | Encaissement loyer | 411 | | 9 000 |
| | | | Encaissement loyer | 531 | 9 000 | |
| | | | **TOTAL** | | **18 000** | **18 000** |

Ce fichier passe tel quel. Trois choses à savoir :

- **Le journal s'écrit comme vous voulez** : son code (`CA`) ou son nom
  (`CAISSE`, `Journal de caisse`).
- **La ligne de totaux du bas est ignorée toute seule**, et l'application vous
  dit laquelle elle a écartée.
- **La colonne « N° écriture » est facultative.** Sans elle, les lignes d'une
  même écriture sont reconnues par leur date, leur journal et leur libellé.

### Si un compte est refusé

Message type : *« le compte 530 n'existe pas dans le plan comptable — le plus
proche dans votre plan : 53, 531. »*

Votre ancien logiciel n'utilisait pas les mêmes numéros que le plan SCF livré.
Deux solutions, au choix :

1. **Corriger le fichier** : remplacer 530 par 531 (c'est le même compte).
2. **Créer le compte** : modèle **Plan comptable**, une ligne `530 / Caisse`,
   puis relancer l'import des écritures.

La seconde est préférable si vous tenez à retrouver vos numéros habituels.

### Ce que l'import ne fait pas

L'import **reprend votre situation, il ne recomptabilise pas le passé**. Les
baux, lots, contrats, quittances et immobilisations décrivent l'existant : ils
ne génèrent aucune écriture. C'est la balance d'ouverture qui porte la
comptabilité. Sans cette règle, tout serait compté deux fois.

De même, une immobilisation reprise **ne rejoue pas son écriture
d'acquisition** : sa valeur et ses amortissements sont déjà dans la balance.

### Depuis les listes elles-mêmes

Le bouton **Importer** est posé là où il sert : Tiers, Portefeuille, Baux,
Programmes, Contrats VSP, Immobilisations, Salariés, et les listes de factures.
Il ouvre directement le bon modèle, sans passer par les paramètres.

### Depuis les listes Ventes et Achats

Pas besoin de passer par les paramètres : sur **Factures**, choisissez le type
(*Factures de vente* ou *Factures d'achat*), puis :

- **Importer** ouvre directement la fenêtre du bon modèle ;
- **Exporter** produit un fichier Excel de ce que vous avez à l'écran.

L'export respecte vos filtres — type, recherche, période et **périmètre**. Si
le sélecteur est sur *Déclaré*, le fichier ne contient que le déclaré. Il
comporte deux feuilles : les factures avec leurs totaux, puis le détail de
leurs lignes.

> Importez vos **tiers avant vos factures** : une facture se rattache à un
> client ou un fournisseur déjà enregistré. Un tiers inconnu est signalé,
> jamais créé au hasard.
>
> Les factures importées sont **en brouillon** : elles ne produisent leur
> écriture comptable qu'une fois validées, après votre relecture.

Points utiles :

- Les lignes qui portent le **même « N° écriture »** forment une seule écriture
  et doivent s'équilibrer entre elles.
- **Un même fichier peut contenir du déclaré et du non déclaré** : c'est la
  colonne *Périmètre* qui décide, ligne par ligne.
- Les écritures importées arrivent **en brouillon** : relisez-les au journal
  avant de les valider.
- Les en-têtes sont reconnus même avec des accents, des majuscules ou des
  variantes courantes (`numero`, `intitule`, `compte general`…).
- Le CSV enregistré depuis Excel est accepté aussi.

## Sauvegarder

- Une sauvegarde part automatiquement à chaque fermeture de l'application.
- **Une fois par semaine**, copiez le dossier `donnees` sur une clé USB.
  Une sauvegarde restée sur le même disque ne protège de rien.
- Pour revenir en arrière : Paramètres → Sauvegarde → Restaurer.

## Mettre à jour

**Depuis l'application, c'est le plus simple.** Vous recevez un fichier
`maj-….zip` : allez dans **Paramètres → Mise à jour**, choisissez le fichier,
cliquez sur **Contrôler le fichier**.

L'application vous dit alors quelle version il contient et ce qu'elle apporte.
Si tout va bien, un bouton **Installer la version …** apparaît. L'application se
ferme, s'installe et **se rouvre toute seule** ; la page se recharge d'elle-même.

Un fichier qui n'est pas une version de Cabinet Immo, une archive abîmée pendant
l'envoi, ou une version plus ancienne que la vôtre sont **refusés en disant
pourquoi**. Rien n'est touché tant que vous n'avez pas cliqué sur Installer.

### Les autres façons, si besoin

**Vous recevez un fichier `…-installateur.py`** → double-cliquez dessus. Il
reconnaît l'installation existante, sauvegarde la comptabilité et ne remplace
que le programme.

**Sans passer par l'application** →
1. Déposez le `.zip` dans `donnees\maj\` (créez le dossier s'il n'existe pas).
2. Double-cliquez sur **`METTRE-A-JOUR.bat`**.

L'outil sauvegarde vos données, remplace le programme, met la base au nouveau
format et vérifie que tout est cohérent. **En cas de problème, il remet
automatiquement l'ancienne version.** Vos données ne sont jamais touchées.

Pour revenir volontairement en arrière :
`METTRE-A-JOUR.bat --annuler`

---

# 2. Pour consulter à distance (depuis la France)

L'application tourne sur le PC en Algérie. Pour y accéder depuis l'étranger
**sans exposer quoi que ce soit sur Internet**, on crée un réseau privé entre
les deux ordinateurs avec **Tailscale** (gratuit, quelques minutes).

## Sur le PC du comptable (Algérie)

1. Installer Tailscale : <https://tailscale.com/download/windows>
2. Se connecter avec un compte (Google ou e-mail).
3. Noter le nom qui apparaît dans la fenêtre Tailscale, par exemple
   `pc-comptable`.
4. Autoriser l'application à répondre sur le réseau privé. Créer, à côté de
   `app.py`, un fichier **`configuration.json`** contenant :

```json
{
  "hote": "0.0.0.0",
  "port": 8781
}
```

Puis relancer l'application.

## Sur votre ordinateur (France)

1. Installer Tailscale et se connecter **avec le même compte**.
2. Ouvrir le navigateur sur : `http://pc-comptable:8781`

Vous voyez la même application, avec vos identifiants.

> **Ce que fait Tailscale :** un tunnel chiffré entre vos deux machines
> uniquement. Rien n'est publié sur Internet, aucun port n'est ouvert sur la
> box, et personne d'autre ne peut atteindre l'application.
>
> **Condition :** le PC en Algérie doit être allumé et l'application lancée.
> C'est pour cela que l'installateur propose le démarrage automatique.

Créez un compte séparé en **consultation seule** pour ceux qui doivent
seulement regarder : Paramètres → Utilisateurs → rôle « Consultation seule ».

---

# 3. Pour le dirigeant (recevoir la situation sur son téléphone)

Pas d'application à installer, pas de mot de passe à retenir : les chiffres
arrivent dans **Telegram**.

## Préparation — à faire une fois par le comptable

1. Sur Telegram, chercher **@BotFather**, lui envoyer `/newbot`, choisir un nom
   (par exemple *El Baraka Immo*). BotFather répond avec un **jeton**.
2. Dans l'application : **Paramètres → Notifications**, coller le jeton,
   **Enregistrer**.
3. **+ Destinataire** : nom (« Papa »), canal **Telegram**, fréquence
   (tous les jours à 8 h, par exemple), et le périmètre des chiffres
   (réels ou déclaré uniquement).
4. Un **code d'appairage** s'affiche (6 caractères). Le transmettre au
   destinataire.

## Côté dirigeant

1. Installer **Telegram** sur son téléphone.
2. Chercher le bot par son nom, ouvrir la conversation.
3. Envoyer le **code d'appairage**. Le bot confirme.

C'est terminé. Il reçoit ensuite la situation automatiquement à l'heure prévue.

## Ce qu'il peut demander à tout moment

Il écrit un mot, il reçoit la réponse dans la seconde :

| Il écrit | Il reçoit |
|---|---|
| **situation** | trésorerie, chiffre d'affaires, résultat, impayés, échéances VSP, avancement des programmes |
| **trésorerie** | banque, caisse, entrées et sorties du jour |
| **loyers** | la liste des loyers impayés, locataire par locataire |

Un exemple de ce qu'il voit :

```
SARL EL BARAKA IMMOBILIER
Situation au 16/08/2026

💰 Trésorerie
  Total : 38 838 169,50 DA
  Banque 38 718 169,50 · Caisse 120 000,00

📊 Exercice 2026
  Chiffre d'affaires : 535 250,00 DA
  Résultat : −2 284 070,00 DA

⚠️ Loyers impayés — 1
  Total : 45 000,00 DA
  • CHERIF Sofiane — 45 000,00 DA (juin 2026)

📅 Échéances VSP exigibles — 2 720 000,00 DA
  • ZEROUAL Mourad lot A05 — 2 720 000,00 DA

🏗️ Programmes
  • Résidence Les Jasmins — 40 % · encaissé 34 640 000,00 DA
    · reste 39 760 000,00 DA · 27 lot(s) libre(s)
```

> **Bon à savoir :** seuls les téléphones ayant envoyé le code d'appairage
> reçoivent des données. Un inconnu qui tomberait sur le bot obtient uniquement
> « ce numéro n'est pas autorisé ». Le message part du PC du comptable :
> aucune donnée n'est stockée ailleurs.

E-mail plutôt que Telegram ? Même écran, choisir le canal **Courriel** et
renseigner le serveur d'envoi.

---

# En cas de problème

| Symptôme | Que faire |
|---|---|
| **Bandeau rouge « Connexion perdue avec l'application »** | La fenêtre de l'application a été fermée, ou l'onglet date d'une session précédente. Rouvrir le raccourci **Cabinet Immo**, puis cliquer sur **Réessayer**. Aucune donnée n'est perdue. L'onglet se rétablit d'ailleurs tout seul dès que l'application redémarre. |
| L'application ne s'ouvre pas | Relancer l'installateur reçu (`INSTALLER.bat` ou le fichier `…-installateur.py`) : il répare l'installation sans toucher aux données. |
| Double-clic sur le raccourci alors qu'elle tourne déjà | L'application ne se dédouble pas : elle ramène la fenêtre existante. |
| Une erreur inexpliquée revient | **Paramètres → Sauvegarde & données → Signaler un problème.** L'application prépare un rapport technique, vous le lisez, puis vous le copiez, l'enregistrez ou l'envoyez. **Aucune donnée comptable n'y figure.** |
| Une écriture est refusée | Le message dit exactement pourquoi (déséquilibre, compte inconnu, exercice clôturé). |
| Erreur après une mise à jour | `METTRE-A-JOUR.bat --annuler` remet la version précédente. |
| Doute sur les données | `DEMARRER.bat --verifier` contrôle l'intégrité et l'équilibre. |
| Tout semble perdu | Paramètres → Sauvegarde → Restaurer une sauvegarde antérieure. |

Le dossier `donnees` contient tout. Tant qu'il existe, rien n'est perdu.
