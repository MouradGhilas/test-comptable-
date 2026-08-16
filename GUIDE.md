# Guide pratique

Trois publics, trois sections. Chacun ne lit que la sienne.

---

# 1. Pour le comptable (installation sur le PC)

## Installer — une seule fois

1. Copiez le dossier **cabinet-immo** sur le PC (clé USB, WeTransfer, e-mail…).
   Mettez-le dans `Documents`, pas sur le Bureau.
2. Double-cliquez sur **`INSTALLER.bat`**.
3. Répondez aux deux questions (Entrée pour accepter) :
   - *Démarrer automatiquement à chaque ouverture de session ?* → **Oui**
   - *Ouvrir l'application maintenant ?* → **Oui**

C'est fini. Un raccourci **Cabinet Immo** est apparu sur le Bureau.

> **Si Python n'est pas installé**, l'installateur le télécharge tout seul
> (11 Mo) et le range dans le dossier de l'application. Rien n'est installé
> dans Windows, aucun mot de passe administrateur n'est demandé.
>
> **Si le téléchargement échoue** (pas d'Internet au moment de l'installation) :
> installez Python depuis <https://www.python.org/downloads/> en cochant
> **« Add Python to PATH »**, puis relancez `INSTALLER.bat`.

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
- **Hors déclaration** — comptabilisé et suivi, mais exclu des déclarations.

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

## Sauvegarder

- Une sauvegarde part automatiquement à chaque fermeture de l'application.
- **Une fois par semaine**, copiez le dossier `donnees` sur une clé USB.
  Une sauvegarde restée sur le même disque ne protège de rien.
- Pour revenir en arrière : Paramètres → Sauvegarde → Restaurer.

## Mettre à jour

1. Recevez le fichier `.zip` de la nouvelle version.
2. Déposez-le dans `donnees\maj\` (créez le dossier s'il n'existe pas).
3. Double-cliquez sur **`METTRE-A-JOUR.bat`**.

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
| L'application ne s'ouvre pas | Relancer `INSTALLER.bat` : il répare l'installation sans toucher aux données. |
| « Le port est occupé » | Normal, l'application en choisit un autre toute seule. |
| Une écriture est refusée | Le message dit exactement pourquoi (déséquilibre, compte inconnu, exercice clôturé). |
| Erreur après une mise à jour | `METTRE-A-JOUR.bat --annuler` remet la version précédente. |
| Doute sur les données | `DEMARRER.bat --verifier` contrôle l'intégrité et l'équilibre. |
| Tout semble perdu | Paramètres → Sauvegarde → Restaurer une sauvegarde antérieure. |

Le dossier `donnees` contient tout. Tant qu'il existe, rien n'est perdu.
