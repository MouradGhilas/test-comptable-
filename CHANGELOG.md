# Journal des versions

Ce que chaque version apporte, en clair. L'application affiche ces notes avant
et après une mise à jour.

## 1.11.0

- **Un import n'ajoute plus de zéros à des sommes justes.** « Montant HT »
  était un simple synonyme de « Prix unitaire » : un fichier qui donne le
  **total d'une ligne** *et* une quantité voyait donc sa somme multipliée —
  100 × 4 954 100 au lieu de 4 954 100. Les deux colonnes sont désormais
  distinctes, et **le montant l'emporte** quand il est renseigné ; la
  quantité n'est plus qu'une indication. Un prix unitaire, lui, continue de
  se multiplier normalement.
- Une quantité écrite « 1,00 » ne fait plus échouer la ligne : les nombres à
  la française sont lus partout.
- **L'aperçu d'import dit combien**, facture par facture. Il annonçait « 1
  ligne sera écrite » sans un montant : c'est ainsi qu'une somme centuplée
  est passée jusqu'au total de l'écran.
- **Cocher des factures et les comptabiliser d'un coup.** Un import dépose
  des brouillons ; les valider une par une, sur des dizaines de factures,
  prenait la matinée. La liste gagne une colonne de cases, « tout
  sélectionner », et deux actions : **Comptabiliser la sélection** et
  **Supprimer la sélection**. Ce qui ne passe pas est nommé, avec sa raison.
- **Une facture se supprime**, et son écriture avec elle — c'est ainsi qu'on
  corrige une reprise ratée, plutôt qu'en empilant des avoirs sur des
  factures qui n'auraient jamais dû exister. Une facture déjà réglée résiste
  et dit par quoi commencer.
- **Une facture validée redevient modifiable** tant que personne n'a payé :
  son écriture est refaite, pas doublée.
- **Le bouton de paiement est en haut à droite**, dès que la facture est
  comptabilisée, et il porte le montant qui reste : *« Encaisser — reste
  1 315 000,00 »*. La liste gagne elle aussi une colonne **Reste**, qui
  compte les deux parts d'une vente.
- **Plus de droit de timbre sur une facture hors déclaration.** Le net à
  payer dépassait le HT de 1 % : c'était le timbre, une taxe déclarée,
  ajoutée à une facture qui ne l'est pas.

## 1.10.1

- **Les dates d'un fichier Excel sont enfin comprises.** Une reprise de
  quatre ans s'arrêtait sur *« 1 ligne sera écrite, 96 mises de côté »*, avec
  à chaque ligne « date **45195** incompréhensible ». Ce n'était pas une date
  illisible : c'est ainsi qu'un tableur range les dates — un nombre de jours
  depuis le 30/12/1899 — et seul le **format de la cellule** les distingue
  d'un nombre ordinaire. L'application ne reconnaissait que le format de ses
  propres modèles ; un fichier venu de votre Excel livrait donc « 45195 » là
  où il y avait le 26/09/2023.
- L'application lit maintenant **les formats du classeur lui-même** : le
  format court d'Excel, les formats personnalisés (`jj/mm/aaaa`,
  `aaaa-mm-jj`…), et les formats de date propres aux autres tableurs. Les
  montants, eux, restent des montants.
- **Un numéro de série reste compris même sans son format** — c'est le cas
  d'un fichier enregistré en CSV, où la colonne perd sa mise en forme.
  Une année écrite seule (« 2024 ») n'est en revanche jamais prise pour une
  date : elle donnerait le 16/07/1905 sans que rien ne le dise.
- Si le fichier couvre des années dont l'exercice n'existe pas encore,
  l'application le dit clairement, avec l'année concernée et l'écran où le
  créer. Elle n'invente pas de période comptable.

## 1.10.0

- **La part non déclarée est une créance, plus une somme réputée encaissée.**
  C'était une erreur de conception de la 1.9.0 : cette part allait droit au
  compte de caisse à la validation de la facture, donc elle passait pour
  réglée le jour même. *« Si je fais le non déclaré, je ne peux pas désigner
  combien le client a payé ou pas encore »* — c'était exact. Elle naît
  désormais **due**, au compte du client et hors déclaration, et se solde par
  des règlements comme n'importe quelle créance. Le champ « Déjà encaissée
  sur » reste disponible et veut dire *payée comptant* : renseigné, le
  règlement suit la validation ; laissé vide, la somme reste à recevoir.
- **Chaque règlement dit quelle part il solde.** L'écran d'encaissement d'une
  vente mixte s'ouvre sur ses deux restes dus — une ligne pour le déclaré, une
  pour le non déclaré, chacune déjà servie du montant qui reste. Le chèque
  solde l'un, les espèces l'autre, et l'application refuse d'encaisser plus
  que ce qui est dû **sur cette part-là**. Une vente n'est « payée » que
  lorsque ses deux moitiés le sont.
- **La situation d'un client, les deux parts côte à côte.** Sur sa fiche :
  ce qui est dû, ce qui est réglé, ce qui reste — pour le déclaré, pour le non
  déclaré, et au total réel. La liste de ses factures gagne une colonne
  « Reste non déclaré ». La question *« a-t-il payé le black ? »* se lit
  maintenant d'un coup d'œil, là où elle n'avait aucune réponse.
- Le **relevé de compte** montre lui aussi ces mouvements, puisqu'ils passent
  enfin par le compte du client : en vue réelle ils y sont, en vue déclarée
  ils n'y sont pas, et le document continue d'annoncer son périmètre.
- Rappel : l'**import des tiers existe déjà** — Paramètres → Import, groupe
  « Tiers ». Le modèle de fichier se télécharge depuis l'écran, se remplit
  sous Excel et se redépose : tous les clients d'un coup.

## 1.9.1

- **La liste des lots d'un contrat VSP n'est plus vide.** À la création d'un
  contrat, « Lot vendu » s'affichait comme un rectangle gris ne proposant
  rien. Deux causes, l'une et l'autre muettes. D'abord, l'écran ne montrait
  que les lots au statut « disponible », alors que **le serveur, lui, accepte
  tout lot qui n'est pas déjà sous contrat** : un lot repris avec la mention
  « vendu » ou « réservé » — le cas normal d'un dossier commencé ailleurs —
  devenait introuvable. La liste propose maintenant tous les lots libres de
  contrat, en indiquant l'état de chacun, et dit combien sont écartés parce
  qu'ils sont déjà vendus.
- **Une liste vide dit désormais ce qui manque et où le créer.** C'était vrai
  du lot, mais aussi de l'acquéreur, du notaire, du bien, du mandat, du
  propriétaire, du locataire : un dossier neuf n'a rien de tout cela, et
  aucun de ces champs ne le disait. Chacun affiche à présent la phrase utile
  — « Aucun lot dans ce dossier. Créez d'abord un programme et ses lots :
  Promotion immobilière → Programmes. » — au lieu d'un cadre vide.
- La suite d'essais navigateur couvre ces deux cas, y compris celui du lot
  déjà marqué « vendu » qui doit rester saisissable.

## 1.9.0

- **Une vente porte ses deux parts, dans une seule saisie.** Le périmètre
  était un choix par facture : *Déclaré* ou *Hors déclaration*. Or une vente
  de logement est souvent les deux à la fois — une part facturée, une part
  réglée à côté. Il fallait saisir deux factures sans lien entre elles, et le
  prix réellement convenu n'apparaissait nulle part. Le périmètre offre
  désormais un troisième choix, **« Déclaré + non déclaré »** : la part non
  déclarée s'inscrit à part, avec son compte de produit et la caisse qui
  l'encaisse, et l'écran affiche les trois chiffres — **facturé, non déclaré,
  prix réel**.
- Cette part donne **sa propre écriture**, équilibrée seule, sans TVA ni droit
  de timbre, du compte de produit à la caisse. Les deux écritures portent la
  même référence d'opération : le journal les montre côte à côte plutôt que
  comme deux ventes sans rapport. La G 50, le TCR et le bilan fiscal
  continuent de n'en voir aucune trace, et continuent de dire ce qu'ils
  écartent.
- **La facture remise au client ne porte que la part facturée.** Une pièce
  signée qui mentionne une part non déclarée met en cause celui qui l'a
  établie ; c'est vérifié à chaque version.
- **Un encaissement peut arriver en plusieurs fois.** Le client apporte un
  chèque **et** des espèces pour la même vente : l'écran d'encaissement prend
  autant de lignes que de moyens de paiement, chacune avec son compte et sa
  référence, et le reste dû se met à jour sous les yeux. Cela fait bien
  plusieurs règlements — c'est la réalité du relevé — mais une seule saisie.
- **Le droit de timbre ne porte plus que sur la part en espèces.** Un mode de
  règlement « Chèque + espèces » ouvre un champ *dont espèces*, et le timbre
  se calcule sur ce montant seul, au lieu du TTC entier.
- **Un exercice se corrige, et se supprime.** Se tromper d'année ou de date de
  fin n'a rien d'exceptionnel, et rien ne permettait d'y revenir. Le libellé
  se corrige toujours ; les dates tant qu'aucune écriture ne s'y rattache. Un
  exercice créé par erreur s'enlève d'un clic s'il est vide ; s'il porte la
  comptabilité, l'application dit **exactement ce qu'il emporterait** et
  demande le mot, comme pour une restauration.
- **Les comptes annexes fonctionnaient déjà** : *Paramètres → Plan comptable →
  Nouveau compte* accepte un `5300005` sans difficulté. C'est de là que se
  choisit la caisse qui reçoit la part non déclarée.
- Nouvelle suite d'essais **dans un vrai navigateur** (`outils/test_ecrans.py`,
  19 contrôles) : un formulaire peut être juste et ne rien afficher — c'est
  arrivé, et seul un navigateur le voit.

## 1.8.7

- **La reprise d'une sauvegarde ne s'arrête plus sur « [WinError 32] ».**
  Sous Windows, remettre une sauvegarde en place échouait avec *« le
  processus ne peut pas accéder au fichier … comptabilite.db-wal »*.
  L'opération effaçait la base et son journal avant d'écrire la nouvelle ;
  or Windows refuse d'effacer un fichier ouvert. Le remplacement passe
  désormais **par SQLite** : le fichier reste en place, seul son contenu
  change. Plus rien à effacer, donc plus rien à débloquer — et si la copie
  échoue en route, le poste garde sa base d'avant.
- **L'application dit quand vos données sont dans un dossier que Windows va
  effacer.** Ouvrir un `.zip` d'un double-clic n'extrait rien : Windows en
  montre le contenu dans un dossier provisoire, situé dans
  `AppData\Local\Temp`. L'application s'y lance et fonctionne — puis tout
  disparaît. Ce cas est maintenant reconnu et annoncé **dès l'accueil, avant
  même la connexion**, avec le geste à faire : extraire l'archive dans
  *Documents*, puis relancer depuis le dossier extrait.
- **L'installation refuse de se faire depuis la fenêtre du `.zip`.** C'est
  par là que la comptabilité a atterri dans `Temp` : ouvrir une archive d'un
  double-clic n'extrait rien, Windows en montre le contenu dans un dossier
  provisoire, et `INSTALLER.bat` s'y installait sans broncher. Les deux
  lanceurs Windows s'arrêtent maintenant dans ce cas, en rappelant le geste :
  clic droit, « Extraire tout… », Documents. L'installateur en un seul
  fichier, lui, pose l'application dans *Documents* au lieu du dossier
  provisoire — il ne reconnaissait jusqu'ici que les dossiers nommés
  « Temp », or celui d'un aperçu s'appelle « …maj1.8.4 (3).zip ».
- **Plus personne n'est renvoyé vers python.org.** Sur un ordinateur neuf,
  qui n'a aucun moteur Python, quatre messages disaient encore d'aller en
  installer un. C'est `INSTALLER.bat` qui s'en charge, sans droit
  administrateur et sans rien changer au système : les messages le disent
  désormais. `LANCER.bat` utilise ce moteur, et lance l'installation si
  l'application n'a jamais été installée.
- Le contrôle d'emplacement, jusqu'ici limité aux dossiers synchronisés
  (OneDrive, Google Drive, Dropbox…), couvre aussi les **dossiers
  temporaires** et les **aperçus d'archive**. Il apparaît dans *Santé du
  dossier*, dans les premiers pas, et dans la fenêtre de démarrage.

## 1.8.6

- **Sur Mac, plus rien à installer.** La version précédente demandait
  d'installer Python depuis un site — pour quelqu'un qui ne code pas, c'est
  une étape de trop, et je n'aurais pas dû l'ajouter. L'installateur
  **cherche un moteur sur le poste et en dépose un s'il n'y en a pas**
  (17 Mo, rangés dans `~/.cabinet-immo/runtime`) : rien dans le système,
  aucun mot de passe, aucune case à cocher. C'est ce que l'installateur
  Windows faisait déjà de son côté.
- **Le blocage « développeur non identifié » est contourné, sans rien
  désactiver.** macOS refuse d'ouvrir d'un double-clic un programme non
  signé par un éditeur enregistré chez Apple — et ne propose qu'un bouton
  *OK*. On passe donc une seule fois par le Terminal : `sh`, un espace, puis
  on **fait glisser le fichier** dans la fenêtre. Le raccourci que
  l'installation pose ensuite sur le Bureau est, lui, créé sur place :
  macOS ne le bloque pas, il s'ouvre d'un double-clic.
- Le guide décrit ces trois gestes, avec la raison du blocage.

## 1.8.5

- **L'application s'installe sur un Mac.** Elle y fonctionnait déjà, mais
  rien ne permettait de la lancer : le Finder n'exécute ni un `.py` ni un
  `.sh` — il les ouvre dans un éditeur de texte. Le paquet contient
  désormais un **`…-installateur-MAC.command`**, que macOS sait lancer, et
  l'installation pose un **`Cabinet Immo.command` sur le Bureau** qui ouvre
  l'application d'un double-clic.
- La première fois, macOS demande confirmation pour un fichier venu
  d'Internet : **clic droit → Ouvrir**, puis *Ouvrir*. Ensuite le double-clic
  suffit. C'est écrit dans le guide, avec la marche à suivre complète.
- L'installateur est un fichier **à la fois script shell et programme
  Python** : un seul contenu, deux noms, aucun risque de divergence entre la
  version Windows et la version Mac.

## 1.8.4

- **Une retenue sur salaire se saisit enfin.** « Y a pas de case retenue » :
  le calcul savait déduire depuis le début, l'écran n'offrait aucun champ
  pour le dire. Chaque bulletin porte maintenant un bouton **Modifier** —
  jours travaillés, primes du mois, et **retenues**, ligne par ligne avec
  leur libellé.
- **Chaque retenue est nommée et imputée.** Une avance sur salaire, un
  acompte, un remboursement de prêt vont au **425** ; une opposition, une
  absence, au **427**. Le compte est proposé d'après le libellé et reste
  modifiable — l'écriture de paie ventile ensuite chaque retenue sur son
  compte, au lieu de tout empiler sur un seul.
- **Le bulletin imprimé les détaille**, au lieu d'une ligne « Autres
  retenues » sans explication. Elles se déduisent du net **après** la CNAS et
  l'IRG : elles ne changent ni les cotisations ni l'impôt.
- **Une paie déjà comptabilisée peut être reprise.** Une retenue qui remonte
  après coup, un jour d'absence signalé en retard : le bouton **Reprendre
  cette paie** extourne les écritures du mois — elles restent lisibles au
  journal — et repasse les bulletins en brouillon. Sans cela, pouvoir
  corriger un bulletin n'aurait servi à rien : ils sont comptabilisés dès le
  lendemain.

- **Trois écrans avaient perdu leur bouton principal.** Une carte sans titre
  n'affichait pas son en-tête — or c'est l'en-tête qui porte les actions.
  Étaient donc invisibles, depuis toujours : **Lettrer la sélection** et
  **Délettrer** (écran Lettrage), **Comptabiliser la paie** et **Enregistrer
  le paiement** (écran Paie), **Reverser aux propriétaires la sélection**
  (écran Loyers). Un contrôle permanent garde ce piège fermé.

## 1.8.3

- **La restauration d'une sauvegarde ne marchait pas.** Depuis toujours :
  l'écran répondait « Erreur interne : disk I/O error » et rien n'était
  restauré. Le journal d'écriture de l'ancienne base était retiré *après*
  que la nouvelle ait pris sa place — SQLite retrouvait alors un journal qui
  décrivait une autre base. C'est le filet de sécurité de tout le dossier :
  il fonctionne, et un contrôle permanent le vérifie désormais à chaque
  livraison.
- **Un second poste peut reprendre le dossier du premier.** L'écran de
  première utilisation ne proposait que de créer un compte et une entreprise
  — alors qu'on a déjà les deux, et une sauvegarde en main. Il porte
  maintenant **« J'ai déjà un dossier sur un autre poste »** : déposez la
  sauvegarde, la comptabilité, les pièces justificatives et votre compte
  sont repris tels quels, et vous vous connectez avec vos identifiants
  habituels. L'écran rappelle lesquels, et prévient que les deux postes ont
  désormais chacun leur copie.
- **Apporter une sauvegarde d'un autre poste** quand celui-ci a déjà un
  dossier : l'écran Sauvegarde & données ne savait restaurer que les fichiers
  déjà présents sur la machine — il fallait trouver soi-même le dossier
  `donnees\sauvegardes\` et y glisser le fichier. Il se dépose maintenant
  depuis l'écran, et rejoint la liste comme les autres.
- Chaque requête refermait mal sa connexion à la base : elles s'accumulaient
  jusqu'au passage du ramasse-miettes. Sans conséquence visible, mais c'est
  ce qui rendait le remplacement du fichier de base hasardeux.

## 1.8.2

- **Les primes valaient cent fois trop.** « Je mets 200 DA, il fait 20 000. »
  Le défaut ne s'arrêtait pas à l'affichage : la prime était **multipliée par
  cent dans le bulletin, dans la base CNAS et dans l'IRG**. Une prime de
  5 000 DA sur un salaire de 50 000 donnait un brut de 550 000 au lieu de
  55 000. La cause : deux conventions pour un même champ — l'écran envoyait
  des centimes, le serveur reconvertissait. Il n'en reste qu'une, la même que
  partout ailleurs : on tape des dinars, le serveur convertit, une seule fois.
- **À vérifier après la mise à jour.** Les fiches de vos salariés peuvent
  porter un montant faux, et les bulletins déjà établis avec une prime sont à
  refaire. Rien n'est corrigé d'office : rien ne distingue une prime de
  20 000 DA d'une prime de 200 DA centuplée, et un bulletin comptabilisé a
  produit ses écritures. **Deux nouveaux contrôles dans Santé du dossier** les
  listent : les salariés dont les primes dépassent trois fois le salaire de
  base, et les bulletins dans le même cas.
- **Importer des salariés avec une prime** déposait un nombre là où
  l'application attend une liste : l'écran des salariés et le calcul du
  bulletin s'en trouvaient cassés. L'import produit désormais une prime en
  bonne et due forme.
- **Le matricule proposé** ne tenait pas compte des salariés arrivés par un
  import ou par le jeu d'essai : il proposait un matricule déjà pris et le
  bouton « Enregistrer » restait sans effet. Il avance maintenant jusqu'au
  premier libre.

## 1.8.1

- **Une écriture se corrige.** La fiche d'une écriture n'offrait que
  *Fermer · Dupliquer · Extourner* : il n'y avait **aucun bouton
  Modifier**. Ce n'était pas une règle comptable, c'était un oubli — le
  moteur savait le faire depuis le début, l'écran ne l'a jamais proposé.
  Faute de mieux, on extournait : d'où les journaux qui accumulent des
  « Extourne de l'extourne de… ».
- **Double-clic sur une ligne du journal** : l'écriture s'ouvre directement
  en correction. Un simple clic ouvre la fiche, qui porte désormais un
  bouton **Modifier**.
- **La correction se fait en place** : même identifiant, **même numéro**,
  mêmes justificatifs. L'ancienne route supprimait puis recréait l'écriture
  — elle changeait donc de numéro (un trou dans le journal), perdait ses
  pièces jointes et son lettrage.
- **Une écriture validée n'est pas figée.** On la corrige après confirmation,
  elle repasse en brouillon (ou reste validée si vous enregistrez et
  validez), et l'opération est inscrite au journal des opérations.
- **Ce que la correction entraîne est dit avant** : lettrage défait des deux
  côtés, écriture produite par un document qui, lui, ne change pas, moitié
  d'une opération saisie en totalité.
- **Ce qui reste protégé** : un exercice clos, et une écriture pointée dans
  un **rapprochement bancaire déjà clôturé** — un relevé arrêté ne change
  pas de contenu dans le dos de celui qui l'a signé.

## 1.8.0

**L'application ne refuse plus rien, et ne perd plus rien.** Jusqu'ici elle
se comportait en gardien : neuf lignes douteuses sur quatre cents, et le
fichier entier repartait. Pour quelqu'un qui tient une comptabilité depuis
quinze ans, c'est du temps perdu à corriger un tableur pour satisfaire un
logiciel. Le rôle du logiciel est d'organiser, pas d'arbitrer.

- **Un import écrit ce qui est écrivable et met le reste de côté.** Les
  lignes non écrites vous attendent **dans l'application**, avec leurs
  valeurs telles qu'elles étaient dans le fichier, et la raison en une
  phrase. Plus de « rien n'a été importé ».
- **On les corrige sur place**, dans une grille, et on clique sur
  *Reprendre*. Plus de retour au tableur, plus d'import à refaire.
- **Ce qui attend quelque chose repart tout seul.** Une quittance déposée
  avant son bail attend ; le jour où le bail arrive, elle est reprise
  d'elle-même, sans que personne n'y pense. Idem pour tout le reste.
- **Un encaissement sans facture reste un encaissement.** Il est repris
  **non affecté**, avec le numéro qu'il cite, et se rattache tout seul à sa
  facture quand elle est enregistrée — le montant réglé et le statut de la
  facture suivent.
- **Un compte de trésorerie inconnu est créé** (512 par défaut), marqué à
  compléter, plutôt que de bloquer la reprise.
- **Ce qui reste refusé, c'est ce qui produirait des comptes faux** : une
  écriture déséquilibrée, une date impossible. Elle n'entre pas en
  comptabilité — elle attend d'être corrigée, ce qui n'est pas la même
  chose qu'être rejetée.
- Correction d'un défaut ancien : un fichier de règlements **sans colonne
  « Mode »** faisait échouer tout l'import sur une contrainte de la base.

## 1.7.9

- **Plus aucun ordre d'importation.** L'écran affichait une colonne « Ordre »
  numérotée de 1 à 18 et un encadré « Suivez l'ordre indiqué ». C'est fini :
  déposez les fichiers que vous voulez, dans l'ordre qui vous arrange.
- **Ce qu'un fichier cite, l'import le crée** — comptes, tiers, journaux
  (déjà en 1.7.8), et désormais aussi **biens, programmes et lots**. La fiche
  naît avec son seul nom et reste **marquée « à compléter »**.
- **Le fichier qui décrit vraiment remplit la fiche.** Passez le fichier des
  programmes après celui des lots : au lieu de dire « déjà enregistré, rien à
  faire », l'import **complète** le programme créé en passant. Avant, après :
  cela revient au même. Une fiche déjà complète, elle, reste intacte — un
  import ne réécrit jamais ce que vous avez saisi.
- **Les quatre exceptions sont nommées, et expliquées.** Un règlement se
  rattache à une facture, une quittance à un bail, une échéance à un contrat,
  un mouvement à un compte de trésorerie. Ce n'est pas un ordre imposé, c'est
  ce que sont ces objets — et le message le dit, au lieu d'un « importez
  d'abord… ».
- **Santé du dossier** : un nouveau contrôle compte les fiches créées par un
  import qui restent à remplir. En information, pas en alerte : rien n'est
  faux, il manque seulement l'adresse d'un client ou la surface d'un lot.

## 1.7.8

- **On peut revenir à une version précédente.** Une mise à jour qui déplaît
  n'était plus défaisable : le fichier de l'ancienne version n'existait
  nulle part, et l'application refusait de toute façon d'installer plus
  ancien qu'elle. Désormais **chaque version installée est conservée sur le
  poste** — Paramètres → Mise à jour en dresse la liste — et on y revient
  d'un bouton, sans redemander le fichier à personne.
- **Deux retours, dits clairement.** Si la version visée sait lire votre
  base, **seul le programme recule** : rien de ce que vous avez saisi n'est
  perdu. Si elle est antérieure à la structure de la base, le programme seul
  ne suffit pas : il faut remettre les données de l'époque, donc perdre ce
  qui a été saisi depuis. L'écran le dit avant, fait choisir la sauvegarde,
  et **garde l'état actuel** pour que le mouvement reste réversible.
- **Réinstaller la version en place** est possible : c'est la réponse à une
  mise à jour restée à mi-chemin, où l'application affiche des écrans neufs
  sur un moteur ancien.
- **L'outil de mise à jour travaillait sur le mauvais dossier de données**
  quand l'application tournait sur un dossier choisi à la main (`--donnees`,
  une clé USB) : la sauvegarde préalable, la migration et la vérification
  visaient le dossier par défaut. Il reçoit maintenant le bon chemin.

- **L'import crée ce dont il a besoin, au lieu de le réclamer.** Un journal
  d'écritures qui cite un sous-compte, un tiers ou un journal absent était
  rejeté ligne par ligne, avec autant d'anomalies que de lignes — il fallait
  monter le plan comptable, puis les tiers, puis les journaux, et
  recommencer. Ces trois-là ne sont qu'un nom : ils sont **créés avec
  l'import**.
- **Annoncé avant, listé après, repris si vous annulez.** L'écran de
  contrôle dit « 3 comptes, 12 tiers et 1 journal seront créés au passage »
  et les énumère ; le compte rendu final les redit ; et annuler la reprise
  les retire avec elle, sauf ceux qui servent déjà ailleurs.
- Un compte créé **hérite de son compte de rattachement** : 40101 prend la
  nature, la rubrique et le caractère lettrable de 4011. Un tiers est rangé
  d'après son compte — 411 client, 401 fournisseur, 4671 mandant, 421
  salarié — et reçoit son compte collectif.
- **Ce qui porte une décision continue d'être réclamé** : un programme, un
  lot, un bail, un bien ont une surface, un prix, une durée. On ne les
  invente pas au milieu d'une reprise.

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
