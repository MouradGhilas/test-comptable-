/* ==========================================================================
   Aide contextuelle — la question comptable que pose cet écran-là.

   Un logiciel de comptabilité ne se devine pas : il applique des règles qui
   ont une raison d'être. Pourquoi un loyer encaissé pour un propriétaire
   n'est pas un produit de l'agence, pourquoi une avance sur vente sur plan
   n'est pas du chiffre d'affaires — ces réponses existaient dans le manuel,
   à l'écart de l'écran qui les pose. Elles sont ici, à un clic.

   Ce sont des rappels, pas des textes officiels : en cas de doute, la loi
   de finances de l'année fait foi. Aucun taux n'est cité ici pour cette
   raison ; les taux vivent dans Paramètres → Fiscalité, où ils se vérifient.
   ========================================================================== */

const AIDES = {
  '/': {
    titre: 'Tableau de bord',
    quoi: 'Les quelques chiffres qui disent où en est le dossier, et ce qui '
        + 'demande une action dans les jours qui viennent.',
    points: [
      'Le chiffre d\'affaires affiché exclut les loyers encaissés pour le '
      + 'compte des propriétaires : cet argent transite, il n\'est pas à vous.',
      'Les alertes sont datées d\'après le calendrier fiscal du dossier. '
      + 'Une déclaration en retard y reste tant qu\'elle n\'est pas déposée.',
      'Le périmètre choisi dans la barre de gauche change tous ces chiffres : '
      + 'en vue réelle, ils incluent le hors déclaration.',
    ],
  },
  '/comptabilite/ecritures': {
    titre: 'Journal des écritures',
    quoi: 'Toutes les écritures du dossier, dans l\'ordre des dates. C\'est '
        + 'le livre-journal : ce que la loi comptable demande de tenir.',
    points: [
      'Une écriture doit s\'équilibrer : total des débits égal au total des '
      + 'crédits. Le logiciel refuse le contraire, sans exception.',
      'Une écriture <strong>validée</strong> ne se modifie plus. On la corrige '
      + 'par une <strong>extourne</strong> — une écriture inverse qui l\'annule '
      + 'sans l\'effacer. C\'est ce qui rend la comptabilité opposable.',
      'Une écriture en <strong>brouillon</strong> compte déjà dans vos états '
      + 'mais reste modifiable : relisez-la, puis validez-la.',
      'Le numéro est attribué par journal et par année, dans l\'ordre de '
      + 'saisie. Il ne doit pas y avoir de trou dans la suite.',
    ],
  },
  '/comptabilite/grand-livre': {
    titre: 'Grand livre',
    quoi: 'Le détail de chaque compte, mouvement par mouvement, avec son '
        + 'solde qui court. C\'est là qu\'on va comprendre d\'où vient un solde.',
    points: [
      'Le grand livre et la balance disent forcément la même chose : la '
      + 'balance n\'est que le total de chaque compte du grand livre.',
      'Le filtre « non lettrées » ne garde que ce qui reste ouvert : les '
      + 'factures non réglées, les règlements non affectés.',
    ],
  },
  '/comptabilite/balance': {
    titre: 'Balance générale',
    quoi: 'Le solde de chaque compte à une date. Le total des débits doit '
        + 'égaler le total des crédits — c\'est le premier contrôle qu\'on fait.',
    points: [
      'Les comptes de classes 1 à 5 forment le bilan ; les classes 6 et 7 '
      + 'forment le résultat. La balance porte les deux.',
      'Un report à nouveau apparaît en début de colonne : c\'est le solde '
      + 'repris de l\'exercice précédent.',
      'Si la balance n\'est pas équilibrée, aucun état financier n\'est '
      + 'fiable. Passez par Santé du dossier pour trouver l\'écriture fautive.',
    ],
  },
  '/comptabilite/lettrage': {
    titre: 'Lettrage',
    quoi: 'Rapprocher une facture de son règlement, pour ne garder ouvert '
        + 'que ce qui est réellement dû.',
    points: [
      'Tant qu\'une facture n\'est pas lettrée avec son règlement, elle reste '
      + 'comptée comme due : la balance des tiers et les relances disent alors '
      + 'autre chose que la réalité.',
      'Le lettrage ne change aucun montant. Il ne fait que marquer ce qui se '
      + 'compense.',
      'Le lettrage automatique rapproche les montants égaux d\'un même tiers. '
      + 'Les cas partiels restent à traiter à la main.',
    ],
  },
  '/comptabilite/etats': {
    titre: 'États financiers',
    quoi: 'Le bilan, le compte de résultat (TCR) et le tableau des flux, '
        + 'présentés selon le SCF algérien.',
    points: [
      'Ces états portent leur périmètre en clair. Un état tiré en vue réelle '
      + 'n\'est pas un état fiscal : il inclut le hors déclaration.',
      'L\'actif doit égaler le passif. Un écart signale une écriture abîmée, '
      + 'jamais une erreur de présentation.',
      'Le résultat du TCR et celui du bilan sont le même chiffre, vu de deux '
      + 'côtés.',
    ],
  },
  '/comptabilite/cloture': {
    titre: 'Contrôles et clôture',
    quoi: 'Fermer l\'exercice : vérifier, virer le résultat, générer les '
        + 'à-nouveaux, puis verrouiller.',
    points: [
      'La clôture est <strong>irréversible</strong> : après elle, plus aucune '
      + 'écriture ne peut être passée sur l\'exercice.',
      'Le résultat est viré en 120 (bénéfice) ou 129 (perte).',
      'Les à-nouveaux reprennent les seuls comptes de bilan : les charges et '
      + 'les produits repartent de zéro, c\'est le principe de l\'exercice.',
      'Faites une sauvegarde, et une copie hors du poste, avant de clôturer.',
    ],
  },
  '/factures': {
    titre: 'Factures',
    quoi: 'Les factures de vente et d\'achat, avec leur règlement et leur '
        + 'écriture comptable.',
    points: [
      'Une facture en <strong>brouillon</strong> ne produit aucune écriture : '
      + 'elle n\'existe pas encore pour la comptabilité. C\'est la validation '
      + 'qui la comptabilise.',
      'Les mentions obligatoires en Algérie (NIF, NIS, RC, article '
      + 'd\'imposition) viennent du dossier et du tiers : complétez-les une '
      + 'fois, elles figureront sur toutes les factures.',
      'Le droit de timbre ne s\'applique qu\'aux règlements en espèces.',
    ],
  },
  '/tresorerie': {
    titre: 'Trésorerie',
    quoi: 'Les banques et les caisses du dossier, avec leur solde comptable.',
    points: [
      'Le solde affiché est celui des comptes, pas celui du relevé bancaire. '
      + 'C\'est le rapprochement qui explique l\'écart entre les deux.',
      'Une caisse ne peut jamais être créditrice : on ne sort pas d\'un tiroir '
      + 'plus d\'argent qu\'il n\'en contient. Si cela arrive, il manque un '
      + 'encaissement.',
    ],
  },
  '/rapprochement': {
    titre: 'Rapprochement bancaire',
    quoi: 'Pointer les mouvements comptables face au relevé de la banque, '
        + 'pour justifier l\'écart entre les deux soldes.',
    points: [
      'Un chèque émis et non encore débité explique légitimement un écart : '
      + 'il reste non pointé jusqu\'à ce que la banque le passe.',
      'Un écart qui ne s\'explique pas est une erreur : un montant saisi de '
      + 'travers, un mouvement oublié, ou un double.',
      '<strong>Importez le relevé fourni par la banque</strong> plutôt que de '
      + 'pointer à la main : l\'application rapproche ce qui se correspond, à '
      + 'quelques jours d\'écart près, et ne laisse que les cas douteux. Rien '
      + 'n\'est pointé avant que vous ayez vu le compte rendu.',
      'Attention au sens des colonnes : ce que la banque appelle '
      + '« crédit » est une entrée d\'argent, donc un <strong>débit</strong> '
      + 'dans vos livres. L\'application essaie les deux conventions et vous '
      + 'dit laquelle elle a retenue.',
    ],
  },
  '/tiers': {
    titre: 'Tiers',
    quoi: 'Clients, fournisseurs, propriétaires mandants, salariés. Chaque '
        + 'tiers est rattaché à un compte collectif du plan SCF.',
    points: [
      'Un client débiteur vous doit de l\'argent ; un fournisseur créditeur '
      + 'attend d\'être payé. L\'inverse est presque toujours une erreur — '
      + 'sauf sur les comptes d\'avances (409 et 419), faits pour cela.',
      'Le <strong>relevé de compte</strong> d\'un tiers donne le détail de ses '
      + 'mouvements avec le solde qui court : c\'est le document à joindre à '
      + 'une relance, et celui qu\'on oppose quand un solde est contesté.',
      'Un tiers employé dans une écriture ne se supprime pas : désactivez-le.',
    ],
  },
  '/relances': {
    titre: 'Relances clients',
    quoi: 'Ce que chaque client doit, depuis quand, et quand il a été relancé '
        + 'pour la dernière fois.',
    points: [
      'Seules les pièces <strong>non lettrées</strong> figurent ici. Une '
      + 'facture réglée mais non lettrée avec son règlement y apparaîtrait à '
      + 'tort : c\'est alors le lettrage qu\'il faut faire, pas la relance.',
      'Trois niveaux : le <strong>rappel</strong> suppose un oubli, la '
      + '<strong>relance</strong> constate qu\'il n\'en était pas un, la '
      + '<strong>mise en demeure</strong> a des effets juridiques — elle fait '
      + 'courir les intérêts de retard et sert de preuve. Le niveau proposé '
      + 'tient compte du retard et de ce qui a déjà été envoyé.',
      'Consigner une relance n\'écrit aucune écriture : une relance ne crée '
      + 'pas de dette, elle constate celle qui existe.',
      'Le <strong>relevé de compte</strong> du client se joint utilement à '
      + 'la lettre : il justifie le solde pièce par pièce.',
    ],
  },
  '/perimetres': {
    titre: 'Déclaré et hors déclaration',
    quoi: 'Le rapprochement entre ce que voient les déclarations et ce que '
        + 'voit la trésorerie réelle.',
    points: [
      'Chaque part — déclarée et non déclarée — <strong>s\'équilibre de son '
      + 'côté</strong> : ce sont deux comptabilités justes, pas une comptabilité '
      + 'coupée en deux.',
      'Les déclarations fiscales ne prennent que le déclaré, et <strong>disent '
      + 'ce qu\'elles écartent</strong> : le montant exclu et le nombre '
      + 'd\'écritures figurent sur chacune.',
      'La vue réelle sert à piloter la trésorerie. Elle n\'est jamais un état '
      + 'fiscal, et chaque document tiré en vue réelle le dit sur lui-même.',
    ],
  },
  '/agence/biens': {
    titre: 'Portefeuille de biens',
    quoi: 'Les biens confiés à l\'agence, en vente comme en gestion locative.',
    points: [
      'Un bien du portefeuille n\'est pas à l\'actif du bilan : il appartient '
      + 'à son propriétaire. Seuls vos honoraires vous concernent.',
    ],
  },
  '/agence/transactions': {
    titre: 'Ventes et transactions',
    quoi: 'Les ventes réalisées par l\'agence et la commission qui en découle.',
    points: [
      'Le produit de l\'agence est la <strong>commission</strong>, jamais le '
      + 'prix du bien : le bien n\'a jamais été à vous.',
      'La commission se facture, et c\'est la facture qui porte l\'écriture.',
    ],
  },
  '/agence/baux': {
    titre: 'Baux',
    quoi: 'Les contrats de location gérés pour le compte des propriétaires.',
    points: [
      'Un bail « encaissé par l\'agence » fait transiter le loyer par vos '
      + 'comptes ; sinon, le locataire paie directement le propriétaire et '
      + 'vous ne facturez que vos honoraires.',
      'La caution reçue n\'est pas un produit : c\'est une dette, rendue en '
      + 'fin de bail.',
    ],
  },
  '/agence/quittances': {
    titre: 'Loyers et quittances',
    quoi: 'Les loyers appelés, encaissés, puis reversés aux propriétaires.',
    points: [
      'Le loyer encaissé pour le compte d\'un propriétaire <strong>n\'est pas '
      + 'un produit de l\'agence</strong> : il transite par le compte 4671 '
      + '« Propriétaires mandants », qui est une dette envers lui.',
      'Seuls les <strong>honoraires de gestion</strong> sont votre produit. '
      + 'Ils sont prélevés sur le compte du mandant au premier encaissement.',
      'Le reversement solde le 4671 pour la période : après lui, vous ne devez '
      + 'plus rien au propriétaire sur ces loyers.',
    ],
  },
  '/agence/proprietaires': {
    titre: 'Situation des propriétaires',
    quoi: 'Ce que l\'agence détient pour le compte de chaque propriétaire.',
    points: [
      'Ce solde est une <strong>dette</strong> : cet argent ne vous appartient '
      + 'pas, il est chez vous en attendant d\'être reversé.',
    ],
  },
  '/promotion/programmes': {
    titre: 'Programmes immobiliers',
    quoi: 'Les opérations de promotion, leur avancement et leur coût de '
        + 'revient.',
    points: [
      'Les dépenses d\'un programme en cours ne sont pas des charges de '
      + 'l\'exercice : elles constituent un <strong>stock d\'en-cours</strong>, '
      + 'sorti au moment de la livraison.',
      'Le coût de revient réparti sur les lots sert à mesurer la marge réelle '
      + 'de chaque vente.',
    ],
  },
  '/promotion/contrats': {
    titre: 'Contrats de vente sur plan (VSP)',
    quoi: 'Les ventes sur plan régies par la loi n° 11-04, avec leur '
        + 'échéancier et leur garantie FGCMPI.',
    points: [
      'Une avance reçue sur une vente sur plan <strong>n\'est pas du chiffre '
      + 'd\'affaires</strong> : c\'est une dette envers l\'acquéreur, portée au '
      + 'compte 4191, tant que le lot n\'est pas livré.',
      'Le produit n\'est constaté qu\'à la <strong>livraison</strong> : le '
      + 'compte d\'avances est soldé, le prix passe en produit, et le reste dû '
      + 'devient une créance client.',
      'Constater le produit plus tôt gonflerait le résultat — et l\'impôt — '
      + 'd\'une année qui n\'a encore rien vendu.',
    ],
  },
  '/promotion/echeances': {
    titre: 'Échéancier VSP',
    quoi: 'Les appels de fonds prévus par chaque contrat, et leur '
        + 'encaissement.',
    points: [
      'Un appel de fonds suit l\'avancement des travaux : c\'est ce que la loi '
      + 'n° 11-04 encadre.',
      'Chaque encaissement alimente le compte d\'avances, pas un compte de '
      + 'produit.',
    ],
  },
  '/promotion/travaux': {
    titre: 'Situations de travaux',
    quoi: 'Les factures d\'avancement des entreprises intervenant sur un '
        + 'programme.',
    points: [
      'Ces dépenses entrent dans le coût de revient du programme, et de là '
      + 'dans le stock d\'en-cours.',
      'La retenue de garantie n\'est pas payée tout de suite : elle reste due '
      + 'à l\'entreprise jusqu\'à la levée des réserves.',
    ],
  },
  '/fiscalite/g50': {
    titre: 'Déclaration G n° 50',
    quoi: 'La déclaration mensuelle unique : TVA, TAP le cas échéant, '
        + 'retenues à la source et droit de timbre.',
    points: [
      'Elle est calculée <strong>depuis la comptabilité</strong>, pas saisie à '
      + 'la main : ce sont vos écritures du mois qui la remplissent.',
      'Elle ne reprend que les opérations marquées « déclaré », et annonce en '
      + 'clair ce qu\'elle a écarté.',
      'Une fois déposée, ne touchez plus aux écritures du mois : Santé du '
      + 'dossier vous préviendra si elles ne correspondent plus.',
      'Les taux et la date limite viennent de Paramètres → Fiscalité. '
      + '<strong>Vérifiez-les</strong> contre la loi de finances de l\'année.',
    ],
  },
  '/fiscalite/annuelles': {
    titre: 'Déclarations annuelles',
    quoi: 'La déclaration annuelle des salaires (série G n° 29) et l\'état '
        + 'des clients, tous deux déduits de ce que vous avez déjà saisi.',
    points: [
      'La DAS récapitule, salarié par salarié, ce qui a été payé et l\'IRG '
      + 'retenu. Le <strong>recoupement</strong> doit tomber juste : les '
      + 'bulletins, les douze G50 déposées et le compte 4421 doivent porter '
      + 'le même IRG. Un écart signale un mois déclaré autrement qu\'il n\'a '
      + 'été payé.',
      'L\'état des clients liste les ventes de l\'année par client, avec son '
      + 'identité fiscale. Un client sans NIF y est signalé : l\'identifiant '
      + 'est attendu sur cet état.',
      'Si le total des factures diffère des comptes de produits, une vente a '
      + 'été comptabilisée sans facture : elle manquerait à l\'état.',
      'Le seuil applicable et la date limite viennent des paramètres '
      + 'fiscaux : <strong>vérifiez-les</strong> contre la loi de finances.',
    ],
  },
  '/fiscalite/obligations': {
    titre: 'Calendrier fiscal',
    quoi: 'Les échéances déclaratives du dossier, à faire, faites ou en '
        + 'retard.',
    points: [
      'Les dates limites sont celles enregistrées dans les paramètres '
      + 'fiscaux de l\'année : elles se vérifient comme les taux.',
    ],
  },
  '/paie/bulletins': {
    titre: 'Paie',
    quoi: 'Les bulletins de salaire, les cotisations CNAS et l\'IRG retenu à '
        + 'la source.',
    points: [
      'Le net à payer se déduit du brut : cotisations salariales, puis IRG '
      + 'calculé sur le barème de l\'année.',
      'La part patronale est une charge de l\'entreprise, pas une retenue sur '
      + 'le salarié : elle s\'ajoute au coût, elle ne diminue pas le net.',
      'L\'IRG retenu et les cotisations sont des dettes : ils figurent dans '
      + 'la G50 du mois et se paient ensuite.',
      'Barème et taux viennent de Paramètres → Fiscalité, et sont à vérifier '
      + 'chaque année.',
    ],
  },
  '/immobilisations': {
    titre: 'Immobilisations',
    quoi: 'Le registre des biens durables et leur amortissement.',
    points: [
      'L\'amortissement étale le coût d\'un bien sur sa durée d\'usage : c\'est '
      + 'une charge qui ne sort aucun argent.',
      'Un bien acheté en cours d\'année ne s\'amortit que sur les mois où il a '
      + 'servi (prorata temporis).',
      'Le cumul d\'amortissement ne peut jamais dépasser la valeur '
      + 'amortissable, et le tableau doit concorder avec les comptes 28.',
    ],
  },
  '/sante': {
    titre: 'Santé du dossier',
    quoi: 'Les anomalies repérées au fil de l\'eau, sans attendre la clôture.',
    points: [
      'Une erreur trouvée en mars se corrige en une minute. La même, trouvée '
      + 'en décembre, a onze mois d\'écritures posées par-dessus.',
      'Ces contrôles <strong>n\'empêchent rien</strong> : ceux qui bloquent une '
      + 'clôture sont sur l\'écran de clôture, à leur place.',
    ],
  },
  '/parametres': {
    titre: 'Paramètres',
    quoi: 'Le dossier, les exercices, le plan comptable, la fiscalité, les '
        + 'sauvegardes et la mise à jour.',
    points: [
      'Les <strong>taux fiscaux livrés sont un point de départ, pas une '
      + 'référence légale</strong>. Comparez-les à la loi de finances de '
      + 'l\'année : ils ne se mettent jamais à jour tout seuls.',
      'Vos données vivent dans un dossier local. Les sauvegardes aussi : '
      + 'copiez-les régulièrement hors du poste, sinon une panne de disque '
      + 'emporte les deux.',
      'Un import ne refuse rien et ne perd rien : ce qu\'il ne sait pas '
      + 'écrire est <strong>mis de côté dans l\'application</strong>, avec ses '
      + 'valeurs. On le corrige dans la grille, ou on le laisse — il repart '
      + 'tout seul dès que ce qui lui manquait existe.',
      'Il n\'y a <strong>aucun ordre d\'importation</strong> à respecter. '
      + 'Ce qu\'un fichier cite et que le dossier ne connaît pas est créé '
      + 'avec lui, marqué « à compléter » ; le fichier qui le décrit '
      + 'vraiment le remplira, qu\'il passe avant ou après.',
      'Les versions déjà installées restent sur le poste : on peut '
      + '<strong>revenir à l\'une d\'elles</strong> si une mise à jour '
      + 'déplaît. Tant que la version visée sait lire votre base, seul le '
      + 'programme recule et rien n\'est perdu. Si elle est plus ancienne '
      + 'que la structure de la base, il faut remettre les données de '
      + 'l\'époque avec : l\'écran le dit et vous fait choisir la '
      + 'sauvegarde.',
    ],
  },
};

/** L'aide de l'écran affiché : exacte, puis par rubrique. */
function aidePourRoute(chemin) {
  const segments = String(chemin || '/').split('/').filter(Boolean);
  return AIDES[chemin]
    || AIDES['/' + segments.slice(0, 2).join('/')]
    || AIDES['/' + (segments[0] || '')]
    || AIDES['/'];
}

function montreAide() {
  const a = aidePourRoute(routeCourante().chemin);
  modale({
    titre: a.titre,
    large: true,
    contenu: `
      <p>${a.quoi}</p>
      <ul class="points-aide">
        ${a.points.map((p) => `<li>${p}</li>`).join('')}
      </ul>
      <p class="petit">Ce sont des rappels, pas des textes officiels. En cas de
      doute — et toujours pour un taux ou une date limite — la loi de finances
      de l'année fait foi.</p>`,
    boutons: [{ libelle: 'Fermer' }],
  });
}
