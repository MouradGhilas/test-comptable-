/* ==========================================================================
   Apparence — réglages de présentation, poste par poste.

   Aucun de ces réglages ne touche aux données ni aux calculs : ils ne
   changent que ce que l'œil reçoit. Ils sont donc gardés dans le
   navigateur (localStorage) et non dans la base : deux personnes qui
   travaillent sur le même dossier n'ont pas le même écran ni la même vue.
   ========================================================================== */

const APPARENCE_DEFAUTS = {
  theme: 'clair',
  accent: 'ardoise',
  densite: 'normal',
  taille: 'normal',
  centimes: 'normal',
  rayage: 'oui',
  coupures: 'oui',
  etiquettes: 'discret',
  listes: 'cadre',
};

/* Chaque réglage : ce qu'il fait, ce qu'il vaut, et comment le dire en
   français. `attribut` est posé sur <html> ; le style s'occupe du reste. */
const APPARENCE_REGLAGES = [
  {
    cle: 'theme', libelle: 'Thème', attribut: 'theme',
    aide: 'Le fond de toute l\'application.',
    valeurs: [['clair', 'Clair'], ['sombre', 'Sombre'], ['systeme', 'Comme Windows']],
  },
  {
    cle: 'accent', libelle: 'Couleur d\'accent', attribut: 'accent',
    aide: 'Titres, liens, boutons principaux et ligne survolée.',
    valeurs: [['ardoise', 'Bleu ardoise'], ['nuit', 'Bleu nuit'], ['foret', 'Vert forêt'],
      ['terre', 'Terre cuite'], ['prune', 'Prune'], ['graphite', 'Graphite']],
    pastilles: true,
  },
  {
    cle: 'taille', libelle: 'Taille du texte', attribut: 'taille',
    aide: 'Toute l\'application, pas seulement les tableaux.',
    valeurs: [['petit', 'Petit'], ['normal', 'Normal'], ['grand', 'Grand'],
      ['tres-grand', 'Très grand']],
  },
  {
    cle: 'densite', libelle: 'Hauteur des lignes', attribut: 'densite',
    aide: 'Compact fait tenir plus de lignes ; aéré soulage la lecture.',
    valeurs: [['compact', 'Compact'], ['normal', 'Normal'], ['aere', 'Aéré']],
  },
  {
    cle: 'centimes', libelle: 'Les centimes', attribut: 'centimes',
    aide: 'Sur « 146 000 000,00 », choisir si les centimes pèsent autant '
        + 'que les millions. Le montant reste exact dans tous les cas, et '
        + 'les exports Excel ne changent jamais.',
    valeurs: [['normal', 'Comme le reste'], ['discret', 'En gris clair']],
  },
  {
    cle: 'rayage', libelle: 'Une ligne sur deux teintée', attribut: 'rayage',
    aide: 'Aide à ne pas sauter de ligne sur un tableau large.',
    valeurs: [['oui', 'Oui'], ['non', 'Non']],
  },
  {
    cle: 'coupures', libelle: 'Coupures dans les listes', attribut: 'coupures',
    aide: 'Un titre à chaque classe comptable dans la balance, à chaque '
        + 'mois dans le journal.',
    valeurs: [['oui', 'Oui'], ['non', 'Non']],
  },
  {
    cle: 'etiquettes', libelle: 'États ordinaires', attribut: 'etiquettes',
    aide: '« Validée » et « Déclaré » figurent sur presque chaque ligne. '
        + 'En gris, la couleur reste disponible pour ce qui demande une action.',
    valeurs: [['discret', 'En gris'], ['couleur', 'En couleur']],
  },
  {
    cle: 'listes', libelle: 'Longues listes', attribut: 'listes',
    aide: 'Dans leur cadre, l\'en-tête et les totaux restent sous les yeux. '
        + 'Sur toute la page, on retrouve le défilement d\'avant.',
    valeurs: [['cadre', 'Défilent dans leur cadre'], ['page', 'Défilent avec la page']],
  },
];

const Apparence = {
  valeurs: { ...APPARENCE_DEFAUTS },

  charge() {
    let enregistre = {};
    try {
      const brut = JSON.parse(localStorage.getItem('apparence') || '{}');
      if (brut && typeof brut === 'object') enregistre = brut;
    } catch (e) { /* réglage illisible : on repart des valeurs livrées */ }

    // Reprise des deux réglages qui existaient avant cet onglet, pour que
    // personne ne retrouve son thème remis à zéro après la mise à jour.
    const ancienTheme = localStorage.getItem('theme');
    if (ancienTheme && !('theme' in enregistre)) {
      this.valeurs.theme = ancienTheme === 'sombre' ? 'sombre' : 'clair';
    }
    const ancienneDensite = localStorage.getItem('densite');
    if (ancienneDensite && !('densite' in enregistre)) {
      this.valeurs.densite = ancienneDensite || 'normal';
    }

    // Une valeur inconnue (réglage supprimé, fichier bricolé) est ignorée
    // plutôt que posée telle quelle sur <html>.
    for (const reglage of APPARENCE_REGLAGES) {
      const valeur = enregistre[reglage.cle];
      if (reglage.valeurs.some(([v]) => v === valeur)) this.valeurs[reglage.cle] = valeur;
    }
    return this.valeurs;
  },

  /** Valeur d'un réglage, utilisable partout dans l'application. */
  get(cle) { return this.valeurs[cle] ?? APPARENCE_DEFAUTS[cle]; },

  applique() {
    const racine = document.documentElement;
    for (const reglage of APPARENCE_REGLAGES) {
      racine.dataset[reglage.attribut] = this.get(reglage.cle);
    }
    // « Comme Windows » : c'est le navigateur qui tranche, et il peut
    // changer d'avis pendant que l'application tourne.
    if (this.get('theme') === 'systeme') {
      const sombre = window.matchMedia
        && window.matchMedia('(prefers-color-scheme: dark)').matches;
      racine.dataset.theme = sombre ? 'sombre' : 'clair';
      racine.dataset.themeChoisi = 'systeme';
    } else {
      delete racine.dataset.themeChoisi;
    }
  },

  change(cle, valeur) {
    this.valeurs[cle] = valeur;
    localStorage.setItem('apparence', JSON.stringify(this.valeurs));
    localStorage.removeItem('theme');
    localStorage.removeItem('densite');
    this.applique();
  },

  reinitialise() {
    this.valeurs = { ...APPARENCE_DEFAUTS };
    localStorage.setItem('apparence', JSON.stringify(this.valeurs));
    localStorage.removeItem('theme');
    localStorage.removeItem('densite');
    this.applique();
  },

  /** Bascule rapide clair / sombre depuis le menu. */
  basculeTheme() {
    const actuel = document.documentElement.dataset.theme === 'sombre';
    this.change('theme', actuel ? 'clair' : 'sombre');
  },
};

Apparence.charge();
Apparence.applique();

if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (Apparence.get('theme') === 'systeme') Apparence.applique();
  });
}
