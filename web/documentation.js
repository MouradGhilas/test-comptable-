/* ==========================================================================
   Documentation — comment faire, écran par écran.

   L'aide contextuelle (le « ? » en haut) répond à « pourquoi cet écran fait
   ça ». Elle ne répond pas à « par où je commence ». Cette page-ci est
   l'autre moitié : des marches à suivre, dans l'ordre, pour chaque chose
   que le logiciel sait faire.

   Chaque fiche porte une rubrique « ce qui coince souvent ». Elle n'est pas
   décorative : elle recense les pannes réellement rencontrées, avec le geste
   qui les évite. C'est la partie la plus utile du texte.
   ========================================================================== */

const TUTORIELS = [
  {
    groupe: 'Installer et transporter',
    fiches: [
      {
        titre: 'Installer l\'application sur un nouveau PC',
        quand: 'Vous avez reçu le fichier « cabinet-immo-….zip ».',
        etapes: [
          'Clic droit sur le fichier .zip → <strong>« Extraire tout… »</strong>, '
          + 'et choisissez le dossier <strong>Documents</strong>.',
          'Ouvrez <strong>le dossier extrait</strong>, puis double-cliquez sur '
          + '<code>INSTALLER.bat</code>.',
          'Répondez aux deux questions (Entrée à chaque fois). Un raccourci '
          + '« Cabinet Immo » apparaît sur le Bureau.',
          'Double-cliquez le raccourci : l\'application s\'ouvre dans votre '
          + 'navigateur.',
        ],
        pieges: [
          'N\'installez <strong>jamais</strong> depuis la fenêtre qui s\'ouvre '
          + 'quand on double-clique un .zip : Windows n\'a rien extrait, il '
          + 'montre le contenu dans un dossier provisoire qu\'il efface '
          + 'ensuite. Une comptabilité tenue là disparaît sans avertissement. '
          + 'L\'installateur s\'arrête de lui-même dans ce cas.',
          'Ce PC n\'a pas Python ? Vous n\'avez rien à installer : '
          + '<code>INSTALLER.bat</code> dépose son propre moteur, sans droit '
          + 'administrateur.',
        ],
      },
      {
        titre: 'Déplacer votre dossier sur un second poste',
        quand: 'Vous changez d\'ordinateur, ou vous travaillez sur deux postes.',
        etapes: [
          'Sur le poste d\'origine : <strong>Paramètres → Sauvegarde &amp; '
          + 'données → Créer une sauvegarde</strong>.',
          'Copiez le fichier <code>sauvegarde_….zip</code> obtenu sur une clé USB.',
          'Installez l\'application sur le second poste (fiche précédente).',
          'À la première ouverture, sur l\'écran qui demande de créer un '
          + 'compte : dépliez <strong>« J\'ai déjà un dossier sur un autre '
          + 'poste »</strong> et déposez la sauvegarde.',
          'Connectez-vous avec vos identifiants habituels : ce sont les mêmes.',
        ],
        route: '/parametres/sauvegarde',
        pieges: [
          'Ne créez pas un nouveau compte sur le second poste : vous auriez '
          + 'deux dossiers séparés. C\'est la sauvegarde qui apporte le vôtre, '
          + 'avec vos comptes et vos pièces.',
          'Les deux postes ne se synchronisent pas entre eux. Travaillez sur '
          + 'un seul à la fois, et refaites le transport dans l\'autre sens '
          + 'quand vous changez.',
        ],
      },
      {
        titre: 'Mettre l\'application à jour',
        quand: 'Vous avez reçu un fichier « maj-….zip ».',
        etapes: [
          '<strong>Paramètres → Mettre à jour</strong>, puis déposez le fichier.',
          'Lisez ce que la version apporte, puis appliquez.',
          'Fermez complètement l\'application et rouvrez-la.',
        ],
        route: '/parametres/maj',
        pieges: [
          'Vos données ne sont jamais touchées : une sauvegarde est prise '
          + 'avant, et l\'application revient en arrière toute seule si '
          + 'quelque chose échoue.',
          'Si un bandeau rouge dit « la mise à jour n\'est pas terminée », '
          + 'c\'est qu\'elle ne s\'est pas relancée : fermez-la et rouvrez-la.',
        ],
      },
      {
        titre: 'Sauvegarder, et où mettre la copie',
        quand: 'Chaque semaine, et avant toute opération importante.',
        etapes: [
          '<strong>Paramètres → Sauvegarde &amp; données → Créer une '
          + 'sauvegarde</strong>.',
          'Copiez le fichier obtenu sur une <strong>clé USB</strong> ou un '
          + 'disque externe.',
        ],
        route: '/parametres/sauvegarde',
        pieges: [
          'Les sauvegardes vivent sur le même disque que la comptabilité. '
          + 'Une panne de disque, un vol ou un rançongiciel emporte les deux '
          + 'd\'un coup : une copie hors du poste est le seul vrai filet.',
          'Un dossier de données rangé dans OneDrive, Google Drive ou Dropbox '
          + 'abîme la base à la longue. L\'application vous prévient si c\'est '
          + 'le cas.',
        ],
      },
    ],
  },
  {
    groupe: 'Reprendre un dossier déjà tenu',
    fiches: [
      {
        titre: 'Importer tous vos tiers d\'un coup',
        quand: 'Vous avez la liste de vos clients et fournisseurs sous Excel.',
        etapes: [
          '<strong>Paramètres → Import</strong>, groupe <strong>Tiers</strong>.',
          'Téléchargez le <strong>modèle de fichier</strong> depuis l\'écran.',
          'Remplissez-le sous Excel, une ligne par tiers.',
          'Redéposez-le au même endroit, vérifiez l\'aperçu, puis validez.',
        ],
        route: '/parametres/import',
        pieges: [
          'La colonne « Type » accepte : client, fournisseur, mandant, '
          + 'locataire, acquereur, salarie, autre.',
          'Vous n\'êtes pas obligé de commencer par les tiers : un tiers cité '
          + 'par un autre fichier est créé au passage, et se complétera quand '
          + 'sa fiche arrivera.',
        ],
      },
      {
        titre: 'Importer vos factures',
        quand: 'Vous reprenez plusieurs mois — ou plusieurs années — de ventes.',
        etapes: [
          '<strong>Paramètres → Import</strong>, groupe Comptabilité, '
          + '<strong>Factures de vente</strong> (ou d\'achat).',
          'Téléchargez le modèle, reportez-y vos données, redéposez le fichier.',
          '<strong>Regardez les montants de l\'aperçu</strong> avant de '
          + 'valider : c\'est le moment de voir une somme fausse.',
          'Validez. Les factures arrivent en <strong>brouillon</strong>.',
          'Sur la liste des factures : cochez-les toutes, puis '
          + '<strong>« Comptabiliser la sélection »</strong>.',
        ],
        route: '/parametres/import',
        pieges: [
          '<strong>« Montant HT » et « Prix unitaire » ne sont pas la même '
          + 'colonne.</strong> Si votre fichier donne le total d\'une ligne, '
          + 'mettez-le dans « Montant HT » : il l\'emporte, et la quantité ne '
          + 'le multiplie pas. Dans « Prix unitaire », il serait multiplié.',
          'Si votre fichier couvre 2021 à 2025, <strong>créez d\'abord les '
          + 'exercices de ces années</strong> (Paramètres → Exercices). '
          + 'L\'application refuse d\'inventer une période comptable.',
          'Une reprise ratée s\'efface : cochez les factures fautives et '
          + '« Supprimer la sélection ». Leurs écritures partent avec elles.',
          'Laissez cochée la case <b>« Comptabiliser ces factures tout de '
          + 'suite »</b>. Décochée, elles restent en brouillon : elles '
          + 'n\'ont alors <b>aucune écriture</b>, et le grand livre reste '
          + 'vide — ce qui est exact, et déroutant.',
        ],
      },
      {
        titre: 'Reprendre les soldes en cours d\'année',
        quand: 'Vous démarrez en cours d\'exercice, avec des soldes déjà là.',
        etapes: [
          '<strong>Paramètres → Import</strong>, <strong>Balance '
          + 'd\'ouverture</strong>.',
          'Indiquez pour chaque compte son solde à la date de reprise, en '
          + 'débit <em>ou</em> en crédit — jamais les deux.',
          'Déposez le fichier : l\'application vérifie que la balance '
          + 's\'équilibre avant d\'écrire quoi que ce soit.',
        ],
        route: '/parametres/import',
        pieges: [
          'Les comptes de tiers doivent être détaillés client par client, '
          + 'sinon vous perdrez le suivi de qui doit quoi.',
        ],
      },
    ],
  },
  {
    groupe: 'Au quotidien',
    fiches: [
      {
        titre: 'Saisir une écriture, et la corriger',
        quand: 'Toute opération qui ne passe pas par une facture.',
        etapes: [
          '<strong>Écritures → + Écriture</strong>.',
          'Choisissez le journal, la date, le libellé.',
          'Saisissez les lignes : un compte, un débit ou un crédit. '
          + 'L\'application propose la contrepartie que vous employez '
          + 'd\'habitude dans ce journal.',
          'Le bandeau du bas doit afficher un écart nul avant d\'enregistrer.',
        ],
        route: '/comptabilite/ecritures',
        pieges: [
          '<strong>Double-cliquez une ligne du journal</strong> pour corriger '
          + 'une écriture, même validée. Elle se réenregistre en place : même '
          + 'numéro, mêmes justificatifs.',
          'Sur un exercice déjà déclaré, préférez l\'<strong>extourne</strong> '
          + ': une écriture inverse annule sans effacer.',
        ],
      },
      {
        titre: 'Établir une facture de vente',
        quand: 'Une commission, des honoraires, une vente de logement.',
        etapes: [
          '<strong>Factures → + Facture</strong>.',
          'Client, date, puis une ligne par prestation : désignation, '
          + 'quantité, prix unitaire, TVA, compte de produit.',
          '<strong>« Enregistrer »</strong> la laisse en brouillon, '
          + '<strong>« Enregistrer et valider »</strong> la comptabilise.',
        ],
        route: '/factures',
        pieges: [
          'Une facture en brouillon ne compte pas encore dans vos états. '
          + 'C\'est la validation qui écrit l\'écriture.',
          'Une facture validée reste modifiable tant que personne n\'a payé : '
          + 'son écriture est refaite, pas doublée.',
        ],
      },
      {
        titre: 'Une vente déclarée et non déclarée à la fois',
        quand: 'Une partie de la vente est facturée, l\'autre réglée à côté.',
        etapes: [
          'Sur la facture, champ <strong>Périmètre</strong> : choisissez '
          + '<strong>« Déclaré + non déclaré »</strong>.',
          'Saisissez les lignes de la part facturée, comme d\'habitude.',
          'Dans le bloc qui s\'ouvre : le <strong>montant</strong> de la part '
          + 'non déclarée, son <strong>compte de produit</strong> (proposé '
          + 'd\'après la première ligne) et, si elle est déjà payée, la '
          + '<strong>caisse qui l\'a reçue</strong>.',
          'Le bandeau affiche les trois chiffres : facturé, non déclaré, '
          + '<strong>prix réel</strong>.',
        ],
        route: '/factures',
        pieges: [
          'Laissez « Déjà encaissée sur » <strong>vide</strong> si le client '
          + 'n\'a pas encore payé : la somme reste due et se solde plus tard '
          + 'depuis « Encaisser ».',
          'La part non déclarée <strong>n\'apparaît pas</strong> sur la '
          + 'facture imprimée remise au client. Une pièce qui la porte vous '
          + 'met en cause.',
          'Elle n\'entre dans aucune déclaration, et la G 50 continue '
          + 'd\'annoncer ce qu\'elle écarte.',
        ],
      },
      {
        titre: 'Encaisser : chèque et espèces sur la même vente',
        quand: 'Le client apporte plusieurs moyens de paiement.',
        etapes: [
          'Ouvrez la facture, bouton <strong>« Encaisser »</strong> en haut à '
          + 'droite — il porte le montant qui reste.',
          'Une ligne par moyen de paiement : mode, compte de trésorerie, '
          + 'référence, montant. <strong>« + Moyen de paiement »</strong> en '
          + 'ajoute une.',
          'Sur une vente à deux parts, chaque ligne dit aussi laquelle elle '
          + 'solde : <strong>Déclaré</strong> ou <strong>Non déclaré</strong>.',
          'Le bandeau montre le reste après encaissement. Enregistrez.',
        ],
        route: '/factures',
        pieges: [
          'L\'application refuse d\'encaisser plus que ce qui est dû '
          + '<strong>sur cette part-là</strong>.',
          'Une vente n\'est marquée « payée » que lorsque ses deux moitiés '
          + 'le sont.',
        ],
      },
      {
        titre: 'Savoir ce qu\'un client doit encore',
        quand: 'Avant de relancer, ou quand il vous appelle.',
        etapes: [
          '<strong>Tiers</strong>, puis le client.',
          'Le bloc <strong>Situation</strong> donne trois colonnes : '
          + 'déclaré, non déclaré, total réel — avec dû, réglé et reste.',
          'La liste de ses factures porte une colonne « Reste non déclaré ».',
          '<strong>« Relevé de compte »</strong> imprime le détail, mouvement '
          + 'par mouvement.',
        ],
        route: '/tiers',
        pieges: [
          'Le relevé suit le périmètre choisi dans la barre de gauche : en '
          + 'vue déclarée il ne montre pas le reste, et il le dit en tête du '
          + 'document. C\'est celui-là qu\'on envoie à un client.',
        ],
      },
    ],
  },
  {
    groupe: 'Agence immobilière',
    fiches: [
      {
        titre: 'Du bien à la commission encaissée',
        quand: 'Une vente que vous avez négociée.',
        etapes: [
          '<strong>Portefeuille → + Bien</strong> : le bien et son propriétaire.',
          '<strong>Mandat</strong> : le taux ou le montant de commission convenu.',
          '<strong>Ventes → Nouvelle vente</strong> : bien, acquéreur, prix, '
          + 'dates du compromis et de l\'acte.',
          'Sur la vente, <strong>« Facturer la commission »</strong> : la '
          + 'facture est établie au compte 7061.',
        ],
        route: '/agence/transactions',
        pieges: [
          'La commission est reprise du mandat si vous ne la saisissez pas. '
          + 'Sans mandat, saisissez-la à la main : ce n\'est pas bloquant.',
        ],
      },
      {
        titre: 'Gestion locative : loyer, quittance, reversement',
        quand: 'Vous gérez un bien pour le compte d\'un propriétaire.',
        etapes: [
          '<strong>Baux → + Bail</strong> : bien, propriétaire, locataire, '
          + 'loyer, charges, honoraires de gestion.',
          '<strong>Loyers</strong> : appelez le loyer du mois, puis encaissez-le.',
          'Le reversement au propriétaire se fait depuis '
          + '<strong>Propriétaires</strong>, honoraires déduits.',
        ],
        route: '/agence/quittances',
        pieges: [
          'Un loyer encaissé pour un propriétaire <strong>n\'est pas un '
          + 'produit de l\'agence</strong> : il transite par le compte 4671. '
          + 'Seuls vos honoraires sont votre chiffre d\'affaires.',
        ],
      },
    ],
  },
  {
    groupe: 'Promotion immobilière',
    fiches: [
      {
        titre: 'Créer un programme et ses lots',
        quand: 'Avant tout contrat de vente sur plan.',
        etapes: [
          '<strong>Programmes → + Programme</strong> : code, intitulé, wilaya, '
          + 'garantie FGCMPI.',
          'Sur le programme, créez les <strong>lots</strong> un à un, ou '
          + 'utilisez « Générer » pour une série (bâtiment, étages, typologie).',
          'Renseignez le prix de vente de chaque lot.',
        ],
        route: '/promotion/programmes',
        pieges: [
          'Sans programme ni lot, l\'écran des contrats VSP n\'a rien à vous '
          + 'proposer — il vous le dit maintenant, au lieu d\'afficher une '
          + 'liste vide.',
        ],
      },
      {
        titre: 'Contrat de vente sur plan et échéancier',
        quand: 'Un acquéreur signe.',
        etapes: [
          '<strong>Contrats VSP → + Contrat VSP</strong>.',
          'Lot vendu, acquéreur, prix, notaire, attestation FGCMPI.',
          'Choisissez un <strong>modèle d\'échéancier</strong> : les tranches '
          + 'sont réparties automatiquement sur le prix.',
          'Les appels de fonds se suivent dans <strong>Échéancier</strong>.',
        ],
        route: '/promotion/contrats',
        pieges: [
          'Une part <b>non déclarée</b> se saisit sur le contrat, champ '
          + '« Dont part non déclarée ». Elle n\'entre ni dans l\'échéancier, '
          + 'ni dans la TVA, ni dans les états fiscaux, et s\'encaisse par son '
          + 'propre bouton, sur la caisse de votre choix.',
          'Un lot déjà marqué « vendu » ou « réservé » reste proposable tant '
          + 'qu\'aucun contrat vivant ne le prend : c\'est le cas normal d\'un '
          + 'dossier repris en cours de route.',
          'Une avance VSP <strong>n\'est pas du chiffre d\'affaires</strong> : '
          + 'elle est encaissée en 4191 et ne devient un produit qu\'à la '
          + 'livraison.',
        ],
      },
    ],
  },
  {
    groupe: 'Paie et déclarations',
    fiches: [
      {
        titre: 'Établir un bulletin de paie',
        quand: 'Chaque mois.',
        etapes: [
          '<strong>Paie → Salariés</strong> : créez la fiche (matricule, '
          + 'salaire de base, situation familiale).',
          '<strong>Bulletins</strong> : choisissez le mois, ajoutez les '
          + '<strong>primes</strong> et les <strong>retenues</strong>.',
          'Le brut, la CNAS, l\'IRG et le net se calculent. Vérifiez, puis '
          + 'validez.',
          '« Comptabiliser la paie » passe l\'écriture du mois.',
        ],
        route: '/paie/bulletins',
        pieges: [
          'Une retenue sur salaire s\'ajoute sur le bulletin, pas sur la fiche '
          + 'du salarié : elle change d\'un mois à l\'autre.',
          'Un bulletin validé se <strong>reprend</strong> : l\'ancien est '
          + 'extourné et un brouillon repart de ses valeurs.',
        ],
      },
      {
        titre: 'Déposer la G 50',
        quand: 'Chaque mois, avant le 20.',
        etapes: [
          '<strong>Déclaration G50</strong>, choisissez la période.',
          'Vérifiez les bases : elles viennent de vos écritures déclarées.',
          'Imprimez, déposez, puis marquez la déclaration comme déposée.',
        ],
        route: '/fiscalite/g50',
        pieges: [
          'La G 50 ne voit que le périmètre déclaré, et elle indique en clair '
          + 'ce qu\'elle a écarté. Ce n\'est pas un oubli : c\'est le contrat.',
          'Les taux livrés sont un point de départ, pas une référence légale. '
          + 'Comparez-les à la loi de finances : Paramètres → Fiscalité.',
        ],
      },
    ],
  },
  {
    groupe: 'Entretien du dossier',
    fiches: [
      {
        titre: 'Créer, corriger ou supprimer un exercice',
        quand: 'Au changement d\'année, ou après une erreur de saisie.',
        etapes: [
          '<strong>Paramètres → Exercices</strong>.',
          '<strong>+ Exercice</strong> pour l\'année suivante.',
          '<strong>Corriger</strong> change le libellé, et les dates tant '
          + 'qu\'aucune écriture ne s\'y rattache.',
          '<strong>Supprimer</strong> enlève un exercice créé par erreur.',
        ],
        route: '/parametres/exercices',
        pieges: [
          'Un exercice qui porte des écritures dit exactement ce qu\'il '
          + 'emporterait et demande le mot SUPPRIMER. Vos sauvegardes, elles, '
          + 'gardent tout.',
          'Le dernier exercice du dossier ne se supprime pas : créez le bon '
          + 'd\'abord.',
        ],
      },
      {
        titre: 'Le grand livre ne montre rien : pourquoi',
        quand: 'Vous avez saisi ou importé, et l\'écran reste vide.',
        etapes: [
          'Regardez le <b>périmètre</b>, dans la barre de gauche : sur '
          + '« Déclaré », les écritures hors déclaration n\'apparaissent pas. '
          + 'Passez sur « Tout — vue réelle ».',
          'Ouvrez la liste des <b>factures</b> : celles en <b>brouillon</b> '
          + 'n\'ont pas d\'écriture. Cochez-les, puis « Comptabiliser la '
          + 'sélection ».',
          'Vérifiez enfin les <b>dates</b> demandées en haut de l\'écran : '
          + 'elles se limitent à l\'exercice courant par défaut.',
        ],
        route: '/comptabilite/grand-livre',
        pieges: [
          'Le grand livre vous dit désormais laquelle de ces raisons '
          + 'l\'explique, avec les nombres. Un écran vide qui ne dit rien '
          + 'était la vraie panne.',
        ],
      },
      {
        titre: 'Vérifier la santé du dossier',
        quand: 'Une fois par mois, et avant toute clôture.',
        etapes: [
          '<strong>Santé du dossier</strong>.',
          'Les anomalies sont classées du plus grave au plus anodin.',
          'Chacune dit ce qui ne va pas, pourquoi ça compte, et mène à '
          + 'l\'écran où la corriger.',
        ],
        route: '/sante',
        pieges: [
          'Une anomalie n\'est pas forcément une erreur : un brouillon en '
          + 'attente, une facture sans justificatif. C\'est une liste de '
          + 'choses à regarder, pas un verdict.',
        ],
      },
      {
        titre: 'Signaler un problème',
        quand: 'L\'application affiche une erreur que vous ne comprenez pas.',
        etapes: [
          'Cliquez <strong>« Signaler ce problème »</strong> sur le message '
          + 'd\'erreur.',
          'La fenêtre montre <strong>exactement</strong> ce qui sera transmis.',
          'Copiez-le, ou enregistrez le fichier, et envoyez-le comme vous '
          + 'voulez.',
        ],
        pieges: [
          'Le rapport ne contient <strong>aucune donnée comptable</strong> : '
          + 'ni montant, ni nom de client, ni raison sociale. Seulement la '
          + 'version, le système et les dernières lignes du journal technique.',
        ],
      },
    ],
  },
];

App.pages.documentation = {
  titre: 'Documentation',
  async afficher(zone) {
    sousTitre('Comment faire, fonctionnalité par fonctionnalité');
    actionsPage('<a class="bouton" href="#/">Retour au tableau de bord</a>');

    zone.innerHTML = `
      <div class="barre-outils">
        <label class="champ recherche" style="flex:1">
          <span>Rechercher dans la documentation</span>
          <input id="doc-q" placeholder="facture, import, sauvegarde, exercice…"></label>
      </div>
      <p class="message info">
        <strong>Deux aides, deux questions</strong>
        Le <b>« ? »</b> en haut de chaque écran explique <em>pourquoi</em> cet
        écran fait ce qu'il fait. Cette page-ci dit <em>comment s'y prendre</em>,
        dans l'ordre. La rubrique « ce qui coince souvent » recense les pannes
        réellement rencontrées, avec le geste qui les évite.
      </p>
      <div id="doc-liste">${TUTORIELS.map(rendGroupe).join('')}</div>
      <p class="vide" id="doc-vide" hidden>Aucune fiche ne correspond.</p>`;

    $('#doc-q').oninput = (e) => filtreDocumentation(e.target.value);
  },
};

function rendGroupe(groupe) {
  return carte(groupe.groupe, groupe.fiches.map(rendFiche).join(''), '', true);
}

function rendFiche(fiche) {
  const texte = [fiche.titre, fiche.quand, ...fiche.etapes,
                 ...(fiche.pieges || [])].join(' ');
  return `<details class="fiche-doc" data-texte="${ech(texte.toLowerCase())}">
    <summary><strong>${ech(fiche.titre)}</strong>
      <span class="petit"> — ${ech(fiche.quand)}</span></summary>
    <ol class="etapes-doc">${fiche.etapes.map((e) => `<li>${e}</li>`).join('')}</ol>
    ${fiche.pieges?.length ? `<div class="pieges-doc">
      <div class="libelle">Ce qui coince souvent</div>
      <ul>${fiche.pieges.map((p) => `<li>${p}</li>`).join('')}</ul></div>` : ''}
    ${fiche.route ? `<div class="rangee" style="margin-top:10px">
      <button class="petit-bouton" onclick="navigue('${fiche.route}')">
        Aller à l'écran</button></div>` : ''}
  </details>`;
}

/** Filtre les fiches sur leur contenu, et replie les groupes devenus vides. */
function filtreDocumentation(recherche) {
  const q = (recherche || '').trim().toLowerCase();
  let visibles = 0;
  $$('.fiche-doc').forEach((fiche) => {
    const garde = !q || fiche.dataset.texte.includes(q);
    fiche.hidden = !garde;
    fiche.open = Boolean(q) && garde;
    if (garde) visibles += 1;
  });
  $$('#doc-liste .carte').forEach((carteGroupe) => {
    carteGroupe.hidden = !$$('.fiche-doc', carteGroupe).some((f) => !f.hidden);
  });
  $('#doc-vide').hidden = visibles > 0;
}
