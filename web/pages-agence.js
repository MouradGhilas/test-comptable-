/* ==========================================================================
   Pages agence immobilière : biens, mandats, transactions, baux, loyers
   ========================================================================== */

App.pages.agence = {
  titre: 'Agence immobilière',
  async afficher(zone, route) {
    const vue = route.segments[1] || 'biens';
    const onglets = [['biens', 'Portefeuille'], ['mandats', 'Mandats'],
      ['transactions', 'Ventes & commissions'], ['baux', 'Baux'],
      ['quittances', 'Loyers'], ['proprietaires', 'Propriétaires']];
    zone.innerHTML = `<div class="onglets">${onglets.map(([v, l]) =>
      `<button class="${v === vue ? 'actif' : ''}" onclick="navigue('/agence/${v}')">${l}</button>`).join('')}</div>
      <div id="vue-agence"><div class="vide">Chargement…</div></div>`;
    const cible = $('#vue-agence');
    const vues = {
      biens: vueBiens, mandats: vueMandats, transactions: vueTransactions,
      baux: vueBaux, quittances: vueQuittances, proprietaires: vueProprietaires,
    };
    await (vues[vue] || vueBiens)(cible, route);
  },
};

App.pages['agence/biens'] = App.pages.agence;
App.pages['agence/mandats'] = App.pages.agence;
App.pages['agence/transactions'] = App.pages.agence;
App.pages['agence/baux'] = App.pages.agence;
App.pages['agence/quittances'] = App.pages.agence;
App.pages['agence/proprietaires'] = App.pages.agence;

const TYPES_BIEN = [['appartement', 'Appartement'], ['villa', 'Villa'],
  ['local_commercial', 'Local commercial'], ['bureau', 'Bureau'],
  ['terrain', 'Terrain'], ['hangar', 'Hangar'], ['garage', 'Garage'],
  ['immeuble', 'Immeuble']];

/* --------------------------------------------------------------- Biens -- */

async function vueBiens(zone, route) {
  actionsPage('<button class="primaire" onclick="editeBien()">+ Bien</button>');
  const d = await charge('/api/biens', { statut: route.parametres.statut, q: route.parametres.q });
  zone.innerHTML = carte(`${d.biens.length} bien(s) au portefeuille`, tableau([
    { titre: 'Réf.', cle: 'reference', largeur: '80px' },
    { titre: 'Désignation', rendu: (b) => `<strong>${ech(b.designation)}</strong>` },
    { titre: 'Type', rendu: (b) => ech((TYPES_BIEN.find((t) => t[0] === b.type_bien) || [])[1] || b.type_bien) },
    { titre: 'Commune', cle: 'commune' },
    { titre: 'Surface', classe: 'num', rendu: (b) => b.surface ? (b.surface / 100).toFixed(0) + ' m²' : '' },
    { titre: 'Propriétaire', cle: 'proprietaire' },
    { titre: 'Prix demandé', classe: 'num', rendu: (b) => b.prix_demande ? fm(b.prix_demande) : '' },
    { titre: 'Loyer', classe: 'num', rendu: (b) => b.loyer_mensuel ? fm(b.loyer_mensuel) : '' },
    { titre: 'Statut', rendu: (b) => etiquette(b.statut) },
    {
      titre: '', classe: 'num',
      rendu: (b) => `<button class="petit-bouton" onclick="editeBien(${b.id})">Modifier</button>`,
    },
  ], d.biens, { icone: '🏠', messageVide: 'Aucun bien. Ajoutez les biens que vous commercialisez ou gérez.' }), '', true);
}

const CHAMPS_BIEN = [
  { groupe: 'Description' },
  { nom: 'designation', libelle: 'Désignation', requis: true, large: true },
  { nom: 'type_bien', libelle: 'Type', type: 'select', vide: false, options: TYPES_BIEN },
  { nom: 'nb_pieces', libelle: 'Typologie', aide: 'F2, F3, F4…' },
  { nom: 'surface', libelle: 'Surface (m²)' },
  { nom: 'etage', libelle: 'Étage' },
  { groupe: 'Localisation' },
  { nom: 'adresse', libelle: 'Adresse', large: true },
  { nom: 'commune', libelle: 'Commune' },
  { nom: 'wilaya', libelle: 'Wilaya' },
  { groupe: 'Situation juridique et commerciale' },
  {
    nom: 'nature_juridique', libelle: 'Nature du titre', type: 'select',
    options: [['acte_notarie', 'Acte notarié'], ['livret_foncier', 'Livret foncier'],
      ['acte_admin', 'Acte administratif'], ['indivision', 'Indivision'],
      ['sans_titre', 'Sans titre']],
  },
  { nom: 'num_acte', libelle: 'N° de l\'acte' },
  { nom: 'proprietaire_id', libelle: 'Propriétaire', type: 'select', options: [] },
  { nom: 'prix_demande', libelle: 'Prix de vente demandé', type: 'montant' },
  { nom: 'loyer_mensuel', libelle: 'Loyer mensuel', type: 'montant' },
  {
    nom: 'statut', libelle: 'Statut', type: 'select', vide: false,
    options: [['disponible', 'Disponible'], ['sous_compromis', 'Sous compromis'],
      ['vendu', 'Vendu'], ['loue', 'Loué'], ['retire', 'Retiré']],
  },
  { nom: 'description', libelle: 'Description', type: 'zone', large: true },
];

async function editeBien(id) {
  const champs = structuredClone(CHAMPS_BIEN);
  champs.find((c) => c.nom === 'proprietaire_id').options = await optionsTiers('mandant');
  const existant = id ? await api(`/api/biens/${id}`) : {};
  if (existant.surface) existant.surface = existant.surface / 100;
  modale({
    titre: id ? 'Modifier le bien' : 'Nouveau bien',
    contenu: formulaire(champs, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, champs);
        if (id) await envoie(`/api/biens/${id}`, donnees, 'PUT');
        else await envoie('/api/biens', donnees);
        notifie('Bien enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ------------------------------------------------------------- Mandats -- */

async function vueMandats(zone) {
  actionsPage('<button class="primaire" onclick="editeMandat()">+ Mandat</button>');
  const d = await charge('/api/mandats');
  zone.innerHTML = carte('Mandats', tableau([
    { titre: 'N°', cle: 'numero' },
    { titre: 'Bien', rendu: (m) => ech(m.bien || '') },
    { titre: 'Mandant', cle: 'mandant' },
    { titre: 'Type', rendu: (m) => m.type_mandat === 'vente' ? 'Vente' : (m.type_mandat === 'location' ? 'Location' : 'Gestion') },
    { titre: 'Exclusif', classe: 'centre', rendu: (m) => m.exclusif ? '✓' : '' },
    { titre: 'Du', rendu: (m) => fdate(m.date_debut) },
    { titre: 'Au', rendu: (m) => fdate(m.date_fin) },
    { titre: 'Prix', classe: 'num', rendu: (m) => fm(m.prix_mandat) },
    {
      titre: 'Commission', classe: 'num',
      rendu: (m) => m.commission_forfait ? fm(m.commission_forfait) : (m.taux_commission ? ft(m.taux_commission) + ' %' : ''),
    },
    { titre: 'Statut', rendu: (m) => etiquette(m.statut) },
  ], d.mandats, { icone: '📄', messageVide: 'Aucun mandat enregistré.' }), '', true);
}

async function editeMandat() {
  const [biens, mandants] = await Promise.all([charge('/api/biens'), optionsTiers('mandant')]);
  const champs = [
    {
      nom: 'bien_id', libelle: 'Bien', type: 'select', requis: true,
      options: biens.biens.map((b) => [b.id, `${b.reference} — ${b.designation}`]),
    },
    { nom: 'mandant_id', libelle: 'Mandant (propriétaire)', type: 'select', options: mandants },
    {
      nom: 'type_mandat', libelle: 'Type de mandat', type: 'select', vide: false,
      options: [['vente', 'Vente'], ['location', 'Location'], ['gestion', 'Gestion locative']],
    },
    { nom: 'exclusif', libelle: 'Mandat exclusif', type: 'case' },
    { nom: 'date_debut', libelle: 'Date de début', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'date_fin', libelle: 'Date de fin', type: 'date' },
    { nom: 'prix_mandat', libelle: 'Prix / loyer convenu', type: 'montant' },
    { nom: 'taux_commission', libelle: 'Taux de commission', type: 'taux', aide: 'En % du prix de vente' },
    { nom: 'commission_forfait', libelle: 'ou commission forfaitaire', type: 'montant' },
    {
      nom: 'charge_commission', libelle: 'Commission à la charge de', type: 'select', vide: false,
      options: [['vendeur', 'Vendeur'], ['acquereur', 'Acquéreur'], ['partage', 'Partagée']],
    },
    { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
  ];
  modale({
    titre: 'Nouveau mandat', contenu: formulaire(champs), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/mandats', litFormulaire(r, champs));
        notifie('Mandat créé.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* -------------------------------------------------------- Transactions -- */

async function vueTransactions(zone) {
  actionsPage('<button class="primaire" onclick="editeTransaction()">+ Vente</button>');
  const d = await charge('/api/transactions');
  zone.innerHTML = `
    <div class="message info">La commission de l'agence n'est un produit qu'une fois facturée.
      Utilisez « Facturer » pour générer la facture d'honoraires et son écriture comptable.</div>
    ${carte('Transactions', tableau([
      { titre: 'N°', cle: 'numero' },
      { titre: 'Bien', rendu: (t) => ech(t.bien || '') },
      { titre: 'Vendeur', cle: 'vendeur' },
      { titre: 'Acquéreur', cle: 'acquereur' },
      { titre: 'Compromis', rendu: (t) => fdate(t.date_compromis) },
      { titre: 'Acte', rendu: (t) => fdate(t.date_acte) },
      { titre: 'Prix de vente', classe: 'num', rendu: (t) => fm(t.prix_vente) },
      { titre: 'Commission HT', classe: 'num', rendu: (t) => `<strong>${fm(t.commission_ht)}</strong>` },
      { titre: 'Statut', rendu: (t) => etiquette(t.statut) },
      {
        titre: '', classe: 'num',
        rendu: (t) => t.facture_id
          ? `<a class="bouton petit-bouton" href="#/factures/${t.facture_id}">${ech(t.facture_numero)}</a>`
          : `<button class="petit-bouton primaire" onclick="factureCommission(${t.id})">Facturer</button>`,
      },
    ], d.transactions, { icone: '🤝', messageVide: 'Aucune transaction enregistrée.' }), '', true)}`;
}

async function editeTransaction() {
  const [biens, mandats, clients, notaires] = await Promise.all([
    charge('/api/biens'), charge('/api/mandats', { statut: 'actif' }),
    optionsTiers('client'), optionsTiers('notaire'),
  ]);
  const champs = [
    {
      nom: 'bien_id', libelle: 'Bien vendu', type: 'select', requis: true,
      options: biens.biens.map((b) => [b.id, `${b.reference} — ${b.designation}`]),
    },
    {
      nom: 'mandat_id', libelle: 'Mandat', type: 'select',
      options: mandats.mandats.map((m) => [m.id, `${m.numero} — ${m.bien || ''}`]),
      aide: 'La commission est reprise du mandat si elle n\'est pas saisie.',
    },
    { nom: 'vendeur_id', libelle: 'Vendeur', type: 'select', options: await optionsTiers() },
    { nom: 'acquereur_id', libelle: 'Acquéreur', type: 'select', options: clients },
    { nom: 'notaire_id', libelle: 'Notaire', type: 'select', options: notaires },
    { nom: 'date_compromis', libelle: 'Date du compromis', type: 'date' },
    { nom: 'date_acte', libelle: 'Date de l\'acte définitif', type: 'date' },
    { nom: 'prix_vente', libelle: 'Prix de vente', type: 'montant', requis: true },
    { nom: 'commission_ht', libelle: 'Commission HT', type: 'montant' },
    { nom: 'taux_tva', libelle: 'TVA', type: 'taux', defaut: 1900 },
    { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
  ];
  modale({
    titre: 'Nouvelle vente', contenu: formulaire(champs), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/transactions', litFormulaire(r, champs));
        notifie(`Transaction ${d.numero} créée — commission TTC ${fm(d.commission_ttc, true)}.`, 'succes');
        afficheRoute();
      },
    }],
  });
}

async function factureCommission(id) {
  const champs = [
    { nom: 'date', libelle: 'Date de la facture', type: 'date', requis: true, defaut: aujourdhui() },
    {
      nom: 'tiers_id', libelle: 'Facturer à', type: 'select', options: await optionsTiers(),
      aide: 'Par défaut : la partie désignée dans le mandat.',
    },
  ];
  modale({
    titre: 'Facturer la commission',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Émettre la facture', classe: 'primaire',
      action: async (r) => {
        const d = await api(`/api/transactions/${id}/facturer`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie(`Facture ${d.numero} émise et comptabilisée.`, 'succes');
        navigue(`/factures/${d.facture_id}`);
      },
    }],
  });
}

/* ---------------------------------------------------------------- Baux -- */

async function vueBaux(zone) {
  actionsPage('<button class="primaire" onclick="editeBail()">+ Bail</button>');
  const d = await charge('/api/baux');
  zone.innerHTML = carte('Baux en portefeuille', tableau([
    { titre: 'N°', cle: 'numero' },
    { titre: 'Bien', rendu: (b) => ech(b.bien || '') },
    { titre: 'Propriétaire', cle: 'proprietaire' },
    { titre: 'Locataire', cle: 'locataire' },
    { titre: 'Usage', cle: 'usage' },
    { titre: 'Du', rendu: (b) => fdate(b.date_debut) },
    { titre: 'Au', rendu: (b) => fdate(b.date_fin) },
    { titre: 'Loyer', classe: 'num', rendu: (b) => fm(b.loyer_mensuel) },
    { titre: 'Charges', classe: 'num', rendu: (b) => b.charges_mensuelles ? fm(b.charges_mensuelles) : '' },
    { titre: 'Gestion', classe: 'num', rendu: (b) => b.taux_gestion ? ft(b.taux_gestion) + ' %' : '' },
    { titre: 'Enreg.', classe: 'centre', rendu: (b) => b.enregistre ? '✓' : '<span class="orange">✗</span>' },
    { titre: 'Statut', rendu: (b) => etiquette(b.statut) },
    {
      titre: '', classe: 'num',
      rendu: (b) => `<button class="petit-bouton" onclick="editeBail(${b.id})">Modifier</button>`,
    },
  ], d.baux, { icone: '🔑', messageVide: 'Aucun bail en gestion.' }), '', true);
}

async function editeBail(id) {
  const [biens, proprietaires, locataires] = await Promise.all([
    charge('/api/biens'), optionsTiers('mandant'), optionsTiers('client'),
  ]);
  const champs = [
    { groupe: 'Parties et bien' },
    {
      nom: 'bien_id', libelle: 'Bien loué', type: 'select', requis: true,
      options: biens.biens.map((b) => [b.id, `${b.reference} — ${b.designation}`]),
    },
    { nom: 'proprietaire_id', libelle: 'Propriétaire', type: 'select', options: proprietaires },
    { nom: 'locataire_id', libelle: 'Locataire', type: 'select', options: locataires },
    {
      nom: 'usage', libelle: 'Usage', type: 'select', vide: false,
      options: [['habitation', 'Habitation'], ['commercial', 'Commercial'], ['professionnel', 'Professionnel']],
    },
    { groupe: 'Durée et loyer' },
    { nom: 'date_debut', libelle: 'Date de début', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'duree_mois', libelle: 'Durée (mois)', type: 'number', defaut: 12 },
    { nom: 'date_fin', libelle: 'Date de fin', type: 'date' },
    { nom: 'loyer_mensuel', libelle: 'Loyer mensuel', type: 'montant', requis: true },
    { nom: 'charges_mensuelles', libelle: 'Charges mensuelles', type: 'montant' },
    { nom: 'caution', libelle: 'Dépôt de garantie', type: 'montant' },
    { nom: 'jour_echeance', libelle: 'Jour d\'échéance', type: 'number', defaut: 5 },
    { nom: 'periodicite_mois', libelle: 'Périodicité (mois)', type: 'number', defaut: 1, aide: '1 = mensuel, 3 = trimestriel' },
    { groupe: 'Gestion par l\'agence' },
    { nom: 'taux_gestion', libelle: 'Honoraires de gestion', type: 'taux', aide: 'En % du loyer encaissé' },
    { nom: 'honoraires_entremise', libelle: 'Honoraires d\'entremise', type: 'montant' },
    {
      nom: 'encaisse_par_agence', libelle: 'L\'agence encaisse le loyer', type: 'case', defaut: true,
      aide: 'Si décoché, seuls vos honoraires sont comptabilisés.',
    },
    { nom: 'enregistre', libelle: 'Bail enregistré aux impôts', type: 'case' },
    { nom: 'date_enregistrement', libelle: 'Date d\'enregistrement', type: 'date' },
    { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
  ];
  const existant = id ? await api(`/api/baux/${id}`) : {};
  modale({
    titre: id ? 'Modifier le bail' : 'Nouveau bail',
    contenu: formulaire(champs, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, champs);
        if (id) await envoie(`/api/baux/${id}`, donnees, 'PUT');
        else await envoie('/api/baux', donnees);
        notifie('Bail enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ------------------------------------------------------------- Loyers --- */

async function vueQuittances(zone, route) {
  const periode = route.parametres.periode || periodeCourante();
  const statut = route.parametres.statut || '';
  actionsPage(`<button class="primaire" onclick="genereQuittances('${periode}')">Générer les quittances du mois</button>
    <button onclick="telecharge('/api/export/quittances',{periode:'${periode}'})">Exporter</button>`);

  const d = await charge('/api/quittances', { periode: statut ? '' : periode, statut });
  const t = d.totaux;

  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ"><span>Période</span>
        <input type="month" id="q-periode" value="${periode}"
          onchange="navigue('/agence/quittances?periode='+this.value)"></label>
      <label class="champ"><span>Filtre</span><select id="q-statut"
        onchange="navigue('/agence/quittances?periode=${periode}&statut='+this.value)">
        <option value="">Période sélectionnée</option>
        <option value="impayee" ${statut === 'impayee' ? 'selected' : ''}>Impayés (toutes périodes)</option>
        <option value="encaissee" ${statut === 'encaissee' ? 'selected' : ''}>Encaissées non reversées</option>
      </select></label>
    </div>
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Loyers attendus', fm(t.attendu, true))}
      ${indicateur('Encaissés', fm(t.encaisse, true), '', 'succes')}
      ${indicateur('Reversés aux propriétaires', fm(t.reverse, true))}
      ${indicateur('Vos honoraires', fm(t.honoraires, true), '', 'accent')}
    </div>
    ${t.impaye ? `<div class="message alerte"><strong>${fm(t.impaye, true)} d'impayés</strong>
      Relancez les locataires concernés.</div>` : ''}
    ${carte('', tableau([
      { titre: '', classe: 'centre', rendu: (q) => q.montant_encaisse > q.montant_reverse ? `<input type="checkbox" data-q="${q.id}" data-p="${q.proprietaire}">` : '' },
      { titre: 'Période', rendu: (q) => fperiode(q.periode) },
      { titre: 'N°', cle: 'numero' },
      { titre: 'Bien', rendu: (q) => `<div class="tronque">${ech(q.bien || '')}</div>` },
      { titre: 'Locataire', cle: 'locataire' },
      { titre: 'Propriétaire', cle: 'proprietaire' },
      { titre: 'Échéance', rendu: (q) => fdate(q.date_echeance) },
      { titre: 'Total dû', classe: 'num', rendu: (q) => fm(q.total) },
      { titre: 'Encaissé', classe: 'num', rendu: (q) => q.montant_encaisse ? fm(q.montant_encaisse) : '' },
      { titre: 'Honoraires', classe: 'num', rendu: (q) => fm(q.honoraires_gestion_ht + q.tva_honoraires) },
      { titre: 'Net propriétaire', classe: 'num', rendu: (q) => fm(q.net_proprietaire) },
      { titre: 'Reversé', classe: 'num', rendu: (q) => q.montant_reverse ? fm(q.montant_reverse) : '' },
      { titre: 'Statut', rendu: (q) => etiquette(q.statut) },
      {
        titre: '', classe: 'num',
        rendu: (q) => `
          ${q.montant_encaisse < q.total ? `<button class="petit-bouton primaire" onclick="encaisseQuittance(${q.id})">Encaisser</button>` : ''}
          <button class="petit-bouton" onclick="window.open('/api/quittances/${q.id}/impression','_blank')">Quittance</button>`,
      },
    ], d.quittances, {
      icone: '🧾',
      messageVide: 'Aucune quittance sur cette période. Cliquez sur « Générer les quittances du mois ».',
    }),
      '<button onclick="reverseSelection()">Reverser aux propriétaires la sélection</button>', true)}`;
}

async function genereQuittances(periode) {
  try {
    const r = await envoie('/api/quittances/generer', { periode });
    notifie(r.message, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function encaisseQuittance(id) {
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Encaissé sur', type: 'select', requis: true, vide: false, options: await optionsTresorerie() },
    { nom: 'date', libelle: 'Date d\'encaissement', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'montant', libelle: 'Montant (vide = solde dû)', type: 'montant' },
  ];
  modale({
    titre: 'Encaisser le loyer',
    contenu: `<div class="message info">L'écriture générée porte le loyer au crédit du compte
        4671 « Propriétaires mandants » — jamais en produit de l'agence — et constate
        vos honoraires de gestion en 7063.</div>${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Encaisser', classe: 'primaire',
      action: async (r) => {
        await api(`/api/quittances/${id}/encaisser`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie('Loyer encaissé et comptabilisé.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function reverseSelection() {
  const cochees = $$('[data-q]').filter((c) => c.checked);
  if (!cochees.length) { notifie('Sélectionnez au moins une quittance encaissée.', 'alerte'); return; }
  const proprietaires = new Set(cochees.map((c) => c.dataset.p));
  if (proprietaires.size > 1) {
    notifie('Sélectionnez les quittances d\'un seul propriétaire à la fois.', 'alerte');
    return;
  }
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Payé depuis', type: 'select', requis: true, vide: false, options: await optionsTresorerie() },
    { nom: 'date', libelle: 'Date du reversement', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'reference', libelle: 'Référence (n° chèque/virement)' },
  ];
  modale({
    titre: `Reverser à ${[...proprietaires][0]}`,
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Reverser', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/quittances/reverser', {
          ...litFormulaire(r, champs),
          quittances: cochees.map((c) => +c.dataset.q),
        });
        notifie(`Reversement de ${fm(d.montant, true)} enregistré.`, 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ------------------------------------------------------- Propriétaires -- */

async function vueProprietaires(zone) {
  const d = await charge('/api/situation-proprietaires');
  actionsPage('');
  zone.innerHTML = `
    <div class="message info">Solde du compte 4671 par propriétaire : ce que l'agence détient
      pour leur compte et doit leur reverser.</div>
    ${carte(`Dû aux propriétaires : ${fm(d.total_du, true)}`, tableau([
      { titre: 'Code', cle: 'code' },
      { titre: 'Propriétaire', rendu: (p) => `<strong>${ech(p.raison_sociale)}</strong>` },
      { titre: 'Téléphone', cle: 'telephone' },
      { titre: 'RIB', cle: 'banque_rib' },
      { titre: 'Quittances à reverser', classe: 'num', cle: 'quittances_a_reverser' },
      { titre: 'Solde dû', classe: 'num', rendu: (p) => `<strong>${fm(p.solde)}</strong>` },
      {
        titre: '', classe: 'num',
        rendu: (p) => `<button class="petit-bouton" onclick="window.open('/api/proprietaires/${p.id}/releve','_blank')">Relevé</button>
          <a class="bouton petit-bouton" href="#/tiers/${p.id}">Fiche</a>`,
      },
    ], d.proprietaires, { icone: '🏘️', messageVide: 'Aucun solde propriétaire en cours.' }), '', true)}`;
}
