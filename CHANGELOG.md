# Journal des versions

Ce que chaque version apporte, en clair. L'application affiche ces notes avant
et après une mise à jour.

## 1.7.7

- **Le rapprochement bancaire se fait à partir du fichier de la banque.**
  Sur l'écran de rapprochement, un bouton **« Importer le relevé de la
  banque »** : déposez le fichier téléchargé depuis le site de votre banque
  (.csv ou .xlsx), et l'application rapproche d'elle-même ce qui se
  correspond. Pointer trois cents lignes une par une, c'était une soirée.
- **Rien n'est pointé sans que vous l'ayez vu.** Le compte rendu montre
  d'abord les correspondances proposées, puis les deux listes qui comptent :
  les lignes du relevé **sans écriture** (agios, prélèvements, virements
  reçus non saisis — à saisir), et les écritures **absentes du relevé** (un
  chèque émis non encore débité — c'est normal, ce sont elles qui expliquent
  l'écart de solde).
- Deux pièges sont traités tout seuls : le **sens des colonnes** — ce que la
  banque appelle « crédit » est une entrée d'argent, donc un débit dans vos
  livres, mais certaines banques inversent pour parler au client : les deux
  conventions sont essayées et l'écran dit laquelle a été retenue — et
  l'**écart de date**, une opération étant rarement passée le même jour de
  part et d'autre (six jours de tolérance, la date la plus proche gagne).
- Les colonnes sont reconnues sous leurs noms usuels (Date / Date valeur,
  Libellé / Opération / Nature, Débit / Retrait, Crédit / Versement, ou une
  simple colonne Montant signée). Un fichier qui n'est pas un relevé est
  refusé en disant quelle colonne manque.

## 1.7.6

- **Relances clients**, nouvel écran dans la rubrique Comptabilité. Il répond
  à la question que la balance des tiers ne répond pas : **qui me doit quoi,
  depuis quand, et lui ai-je déjà écrit ?**
- Chaque client apparaît avec le détail de ses factures échues, le retard le
  plus ancien, le total dû, et la date de la dernière relance envoyée.
- **Trois niveaux de lettre**, imprimables à l'en-tête de la société : le
  *rappel* suppose un oubli, la *relance* constate qu'il n'en était pas un,
  la *mise en demeure* annonce ses effets. Le niveau proposé tient compte du
  retard **et** de ce qui a déjà été envoyé — après une relance, c'est la
  mise en demeure qui est mise en avant.
- Les relances sont consignées, avec le moyen employé et une note libre : on
  ne relance plus deux fois en huit jours, et on n'oublie plus six mois.
  Consigner n'écrit **aucune écriture** : une relance ne crée pas de dette,
  elle constate celle qui existe.
- Seules les pièces **non lettrées** figurent ici : une facture réglée mais
  non lettrée avec son règlement y apparaîtrait à tort — c'est alors le
  lettrage qu'il faut faire, et l'aide de l'écran le dit.

## 1.7.5

- **Correction : une mise à jour restée à mi-chemin ne passe plus inaperçue.**
  Les fichiers de l'interface sont relus sur le disque à chaque affichage, le
  moteur Python une seule fois au démarrage. Si l'application ne s'est pas
  relancée après une mise à jour, on se retrouve avec les écrans neufs sur
  l'ancien moteur : les nouvelles rubriques apparaissent, mais répondent
  « Ressource introuvable », et la version affichée reste l'ancienne.
  L'application s'en aperçoit désormais toute seule et affiche un bandeau,
  avec un bouton pour la fermer proprement — il n'y a plus qu'à la rouvrir.
- Le message d'erreur lui-même le dit maintenant, au lieu de « Ressource
  introuvable » : *« cet écran appartient à la version X, déjà installée,
  mais l'application tourne encore sur la version Y »*.
- **La mise à jour ne peut plus provoquer cet état** : avant de remplacer
  quoi que ce soit, elle vérifie non seulement que le processus a disparu,
  mais que le port de l'application ne répond plus. Un identifiant de
  processus peut être réattribué ; un port qui répond, lui, ne ment pas.
- Le « ? » de l'aide est correctement centré dans son cercle.

## 1.7.4

- **Les deux déclarations de janvier**, dans Fiscalité → « Déclarations
  annuelles ». Elles ne se saisissent pas : tout est déjà dans le dossier.
- La **déclaration annuelle des salaires** (série G n° 29) récapitule chaque
  salarié — matricule, n° de sécurité sociale, mois payés, brut, CNAS, base
  IRG, IRG retenu, net payé — avec les totaux et la date limite.
- L'**état des clients** liste les ventes de l'année par client, avec son
  identité fiscale (NIF, RC, article d'imposition). Un client sans NIF est
  signalé : l'identifiant est attendu sur cet état. Un seuil permet d'écarter
  les petits montants, et l'écran dit combien il a écarté.
- **Chacun porte son recoupement**, à l'écran et sur le papier. C'est ce qui
  fait leur valeur : pour la DAS, les bulletins, le cumul des G50 déposées et
  le compte 4421 doivent porter le même IRG — un écart signale un mois
  déclaré autrement qu'il n'a été payé. Pour l'état des clients, le total des
  factures doit égaler les comptes de produits — un écart signale une vente
  comptabilisée sans facture, qui manquerait à l'état.
- Les deux s'impriment à l'en-tête de la société, avec emplacement de cachet
  et de signature, et s'exportent vers Excel.

## 1.7.3

- **Santé du dossier**, nouvel écran dans la rubrique Clôture. Dix contrôles
  tournent au fil de l'eau, sans attendre la clôture : une erreur trouvée en
  mars se corrige en une minute, la même trouvée en décembre a onze mois
  d'écritures posées par-dessus. Chaque anomalie dit **ce qui ne va pas,
  pourquoi ça compte, et où aller pour le corriger**.
- Sont surveillés : l'équilibre de la comptabilité, les trous dans la
  numérotation d'un journal, une caisse passée en négatif, les factures
  validées sans écriture, les clients créditeurs ou fournisseurs débiteurs,
  les G50 déposées qui ne collent plus aux comptes, les brouillons, les
  écritures sans justificatif, le lettrage qui traîne, et la dernière copie
  de sauvegarde hors du poste.
- Ces contrôles **n'empêchent rien** : ceux qui bloquent une clôture restent
  sur l'écran de clôture, à leur place.
- **Un « ? » dans la barre du haut**, sur chaque écran. Il explique en
  français simple le point comptable qui compte là où vous êtes : pourquoi un
  loyer encaissé pour un propriétaire n'est pas un produit de l'agence,
  pourquoi une avance sur vente sur plan n'est pas du chiffre d'affaires,
  pourquoi une écriture validée se corrige par extourne. Aucun taux n'y est
  cité : ils vivent dans Paramètres → Fiscalité, où ils se vérifient.

## 1.7.2

- **Le compte se cherche au nom autant qu'au numéro.** Dans la saisie, la
  liste déroulante de 250 comptes est remplacée par un champ où l'on tape
  « 401 » ou « fourniss » : la liste se réduit d'elle-même. Même chose pour
  le tiers, qu'on trouve désormais par son nom et plus seulement par son code.
- **Entrée met ce qui manque.** Dans une case de montant vide, la touche
  Entrée y inscrit le montant qui équilibre l'écriture, du bon côté. Un
  bouton **Solder** fait la même chose à la souris. C'est le geste le plus
  répété d'une saisie : le dernier montant est toujours celui qui solde.
- **La contrepartie habituelle est proposée.** Si vous avez passé trente fois
  un achat 6051 contre 4011 au journal des achats, la trente et unième saisie
  vous propose 4011 sur la ligne d'en face — en italique, modifiable, et en
  disant combien de fois elle a servi. Sans historique, rien n'est proposé :
  mieux vaut un champ vide qu'un compte inventé.
- Le bandeau d'équilibre dit maintenant **de quel côté** il manque
  (« il manque 12 500,00 au crédit ») au lieu d'un écart sans direction.
- Un compte absent du plan, ou un montant tapé sur une ligne sans compte,
  se signalent pendant la saisie et non au moment d'enregistrer.

## 1.7.1

- **On voit enfin où l'on est.** L'entrée du menu correspondant à l'écran
  affiché est maintenant peinte en plein, et non plus simplement teintée :
  elle se trouve sans la chercher. Le titre de sa rubrique s'éclaire aussi,
  et la rubrique est rappelée en petit au-dessus du titre de la page
  (« COMPTABILITÉ » puis « Journal des écritures »).
- Le repère suit partout, y compris là où il manquait : la fiche d'un
  programme éclaire « Programmes », un contrat éclaire « Contrats VSP »,
  l'onglet TVA éclaire « Déclaration G50 », et **tous** les onglets des
  paramètres éclairent « Paramètres » — jusqu'ici, aucune entrée n'était
  marquée sur ces écrans-là.
- Si le menu est plus long que l'écran, il défile de lui-même pour garder
  l'entrée courante en vue.
- L'onglet ouvert à l'intérieur d'une page se distingue lui aussi mieux.
- **Personnalisation → « Où je suis »** permet de revenir au repère discret
  d'avant, pour qui préfère un menu qui ne saute pas aux yeux.
- Correction : ouvrir un rapprochement bancaire sans numéro — un signet, une
  adresse tapée à la main — affichait « Erreur interne ». L'écran montre
  maintenant la liste des rapprochements existants.

## 1.7.0

- **Défaire un import.** Vous vous êtes trompé de fichier, ou vous avez passé
  le même deux fois ? Chaque reprise reste inscrite dans **Paramètres →
  Import de données → « Reprises déjà faites »**, avec un bouton pour
  l'annuler. L'application regarde ce qui a été fait depuis et vous dit
  elle-même comment elle s'y prendra, **avant** d'y toucher : elle retire les
  écritures si rien n'a bougé — les numéros repartent d'où ils venaient, sans
  laisser de trou dans le journal — et les **contre-passe** dès qu'une
  écriture a été passée depuis. Rien n'est jamais effacé de la piste d'audit.
- Pour un import de tiers, de comptes ou de biens, ce qui sert déjà reste en
  place et l'écran dit lequel. Un exercice clôturé, une ligne lettrée ou une
  facture réglée depuis empêchent la suppression, en le disant.
- **Rechercher partout, d'un seul champ.** En haut de chaque page, ou par
  **Ctrl + K** : tapez un nom, un numéro de facture, un compte, et le
  résultat vous mène directement à sa page. L'écriture cherchée s'ouvre
  d'elle-même.
- **Chercher un montant.** Tapez `125 000` : l'application retrouve la ligne
  d'écriture qui porte cette somme, au débit comme au crédit, avec son compte
  et son journal. C'est ce qu'il faut pour remonter à l'origine d'un solde qui
  ne tombe pas juste.
- **Relevé de compte d'un tiers.** Depuis la liste des tiers ou depuis sa
  fiche : le détail de tous ses mouvements sur une période, avec le solde
  d'ouverture, le solde qui court ligne à ligne, le lettrage, et l'ancienneté
  de ce qui reste dû. Imprimable pour être envoyé à un client, exportable vers
  Excel. C'est le document qu'on joint à une relance, et celui qu'on oppose
  quand un tiers conteste son solde.
- Le relevé annonce son périmètre : un relevé « déclaré » ne montre que le
  déclaré, et le dit en toutes lettres sur le papier.

## 1.6.6

- **Dupliquer une écriture.** Ouvrez une écriture, cliquez sur
  **Dupliquer** : la saisie se rouvre avec le même journal, le même libellé,
  les mêmes comptes, tiers et montants. Seule la date repart d'aujourd'hui,
  et le numéro de pièce reste à vous. Le périmètre d'origine est conservé —
  une opération hors déclaration ne devient pas déclarée par mégarde.
- **Modèles d'écriture.** Le loyer, la paie, les charges fixes reviennent
  chaque mois à l'identique. Remplissez la saisie une fois, cliquez sur
  **« Garder comme modèle »**, donnez-lui un nom. Ensuite, le bouton
  **« Depuis un modèle »** du journal la rejoue en un clic.
- Les modèles les plus employés remontent en tête de liste, et chacun
  indique combien de fois il a servi. Un modèle s'oublie quand il ne sert
  plus ; les écritures déjà passées, elles, ne bougent pas.

## 1.6.5

- **Telegram : le parcours est enfin dit dans l'ordre.** L'écran renvoyait
  au « code d'appairage affiché ci-dessus » alors qu'aucun code n'existe
  tant qu'aucun destinataire n'a été créé — le code est propre à chaque
  destinataire. Trois étapes numérotées montrent maintenant où vous en êtes,
  et disent quoi faire quand il n'y a encore rien.
- **Le code s'affiche en grand, avec un bouton « Copier »** : il est fait
  pour être recopié dans WhatsApp ou lu au téléphone. Il n'expire pas.

## 1.6.4

- **Le justificatif se rattache enfin à l'écriture.** Ouvrez une écriture,
  déposez le scan ou la photo de la facture : c'est elle qu'on vous
  demandera lors d'un contrôle. Le fichier est rangé dans votre dossier de
  données, part avec les sauvegardes et avec la copie sur clé USB.
- **Le journal montre d'un coup d'œil ce qui manque** : un trombone sur les
  écritures justifiées, et une case **« Sans justificatif »** pour n'afficher
  que celles qui restent à documenter.
- Formats acceptés : PDF, images, documents bureautiques, jusqu'à 20 Mo. Un
  fichier d'un autre type est refusé en disant pourquoi.
- **Le barème IRG devient modifiable** (Fiscalité → Paramètres). Sa remarque
  disait « à vérifier et adapter » alors qu'il était le seul paramètre
  affiché en lecture seule — or la loi de finances le change presque chaque
  année, et il commande tous les bulletins de paie. Les tranches s'ajoutent,
  se modifient et se retirent une par une.

## 1.6.3

- **Copie de vos sauvegardes hors du poste**, dans Paramètres → Sauvegarde &
  données. Jusqu'ici les sauvegardes étaient rangées à côté de la
  comptabilité, donc **sur le même disque** : une panne, un vol ou un
  rançongiciel emportait les comptes et toutes leurs copies d'un seul coup.
  Vous branchez une clé USB, vous indiquez sa lettre, vous cliquez.
- **L'application vous dit depuis quand la dernière copie date**, et le
  signale au bout d'une semaine. Elle refuse de copier dans votre dossier de
  données ou dans celui du programme : cela ne protégerait de rien.
- Une clé débranchée, un support plein ou protégé en écriture donnent un
  message clair au lieu d'une erreur technique.

## 1.6.2

- **Correction de la panne qui empêchait toute mise à jour depuis
  l'application.** Sur un Windows français, l'affichage utilise la page de
  codes cp1252, qui ne connaît ni les cadres `═` ni les flèches `→` de
  l'outil de mise à jour. Celui-ci s'arrêtait donc sur sa toute première
  ligne, avant d'avoir rien installé — et comme sa sortie partait au néant,
  cela se voyait seulement à un chargement qui n'en finissait pas. C'était
  la vraie raison du « bouton qui ne fait pas grand-chose ».
- L'application, l'outil de mise à jour et l'installateur forcent désormais
  l'UTF-8 pour leur affichage, avec un garde-fou : un caractère qui passe
  mal dégrade l'affichage, il n'interrompt plus jamais une mise à jour.

## 1.6.1

- **Après une mise à jour réussie, l'application dit ce qu'elle vient
  d'apporter.** L'écran de confirmation ne se contente plus d'un « c'est
  fait » : il affiche les nouveautés de la version installée, directement
  sous vos yeux. Le compte rendu reste aussi rappelé en haut de
  Paramètres → Mise à jour.

## 1.6.0

Cette version ne change rien aux calculs ni aux données : elle ne change que
la façon dont les chiffres se présentent à l'écran — et elle vous laisse
décider comment.

- **Nouvel onglet Paramètres → Personnalisation.** Thème, couleur d'accent,
  taille du texte, hauteur des lignes, traitement des centimes, rayage,
  coupures, états ordinaires, défilement des longues listes. Un aperçu de
  quatre lignes montre l'effet de chaque réglage tout de suite, et un bouton
  ramène tout aux valeurs livrées. Les réglages restent sur le poste : deux
  personnes sur le même dossier gardent chacune son écran.
- **La balance retrouve la structure du plan comptable** : une coupure à
  chaque classe (Capitaux, Immobilisations, Stocks, Tiers, Financiers,
  Charges, Produits), les soldes séparés des mouvements par un filet, et les
  colonnes de report qui disparaissent quand elles sont vides.
- **Le journal se lit par mois**, avec un titre à chaque changement.
- **L'en-tête et la ligne de totaux restent visibles** pendant qu'on fait
  défiler une longue liste. À l'impression, la liste ressort en entier.
- **La ligne survolée est nettement marquée**, pour suivre un compte jusqu'à
  la dernière colonne sans se perdre. Une ligne sur deux est légèrement
  teintée.
- **Les états ordinaires ne crient plus.** « Validée » et « Déclaré »
  s'affichent en gris : la couleur est réservée à ce qui demande une action
  (brouillon, hors déclaration, impayé). Rien n'est masqué.
- Dans le grand livre, les colonnes s'alignent d'un compte à l'autre et un
  solde créditeur se distingue au premier coup d'œil.
- **Le bouton « Mettre à jour » fait toute la mise à jour, tout seul.** Plus
  de fenêtre noire à surveiller ni à relancer à la main : vous déposez le
  fichier, et l'application se ferme, s'installe, se contrôle et se rouvre
  d'elle-même. Un écran d'attente montre les étapes, et à la réouverture
  l'application affiche ce qui s'est passé — réussite ou échec, avec la
  raison. En cas de pépin, la version précédente est remise en place puis
  l'application rouvre quand même, pour ne jamais vous laisser devant un
  écran fermé.
- Les centimes peuvent être affichés en gris clair pour laisser les millions
  ressortir. **Ce n'est pas le réglage livré** : par défaut ils gardent la
  couleur du reste. Le montant est exact dans tous les cas et les exports
  Excel ne changent jamais.

## 1.5.0

- **Pour bien démarrer.** Sur un dossier neuf, le tableau de bord affiche ce
  qu'il reste à faire, coché au fur et à mesure, puis la liste disparaît.
- **Dossier d'essai en un clic** (Paramètres → Import de données) : une année
  d'activité complète pour découvrir sans rien risquer, supprimable d'un clic.
- **Avertissement si vos données sont dans OneDrive, Google Drive ou Dropbox.**
  Une comptabilité stockée dans un dossier synchronisé peut être abîmée : le
  service recopie la base pendant que l'application écrit dedans.
- **Signaler un problème** : l'application prépare un rapport technique, vous
  le lisez, puis vous le copiez, l'enregistrez ou l'envoyez. Aucune donnée
  comptable n'y figure.
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
