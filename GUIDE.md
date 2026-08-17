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

Ce qui peut être repris :

| Modèle | Contenu |
|---|---|
| Écritures comptables | le journal, avec la colonne **Périmètre** (Déclaré / Non déclaré) |
| Factures de vente | vos ventes, une ligne de fichier par ligne de facture |
| Factures d'achat | vos achats fournisseurs, avec leur numéro d'origine |
| Tiers | clients, fournisseurs, propriétaires, locataires, acquéreurs |
| Plan comptable | vos comptes en plus du plan SCF livré |
| Biens | le portefeuille de l'agence |
| Salariés | pour la paie |

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

Deux façons, selon ce que vous recevez. **Les deux gardent vos données.**

**Vous recevez un fichier `…-installateur.py`** → double-cliquez dessus. Il
reconnaît l'installation existante, sauvegarde la comptabilité et ne remplace
que le programme.

**Vous recevez un fichier `maj-….zip`** →
1. Déposez-le dans `donnees\maj\` (créez le dossier s'il n'existe pas).
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
| Une erreur inexpliquée revient | **Paramètres → Sauvegarde & données** affiche le journal des incidents (`donnees\journal.log`). Ce fichier contient de quoi diagnostiquer à distance. |
| Une écriture est refusée | Le message dit exactement pourquoi (déséquilibre, compte inconnu, exercice clôturé). |
| Erreur après une mise à jour | `METTRE-A-JOUR.bat --annuler` remet la version précédente. |
| Doute sur les données | `DEMARRER.bat --verifier` contrôle l'intégrité et l'équilibre. |
| Tout semble perdu | Paramètres → Sauvegarde → Restaurer une sauvegarde antérieure. |

Le dossier `donnees` contient tout. Tant qu'il existe, rien n'est perdu.
