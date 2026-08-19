/* ==========================================================================
   Pages : tableau de bord, tiers, trésorerie, paramètres, sauvegardes
   ========================================================================== */

/* ---------------------------------------------------- Tableau de bord --- */

App.pages.accueil = {
  titre: 'Tableau de bord',
  async afficher(zone) {
    const [d, pas] = await Promise.all([
      charge('/api/tableau-de-bord'),
      charge('/api/premiers-pas').catch(() => null),
    ]);
    const i = d.indicateurs;
    sousTitre(`${d.societe.raison_sociale} — exercice ${d.exercice.libelle}`);

    // Liste de démarrage : visible tant qu'il reste quelque chose à faire,
    // puis elle disparaît d'elle-même.
    const premiersPas = (pas && !pas.termine) ? carte('Pour bien démarrer', `
      <p class="petit">Il reste ${pas.restant} point(s) à régler. Cette liste
      disparaîtra une fois tout coché.</p>
      <ul class="premiers-pas">
        ${pas.etapes.map((e) => `
          <li class="${e.fait ? 'fait' : ''} ${e.alerte ? 'alerte' : ''}">
            <span class="coche">${e.fait ? '✓' : (e.alerte ? '!' : '·')}</span>
            <div>
              <strong>${ech(e.titre)}</strong>
              <div class="petit">${ech(e.detail)}</div>
            </div>
            ${e.fait ? '' : `<a class="bouton petit-bouton" href="${e.lien}">Y aller</a>`}
          </li>`).join('')}
      </ul>`) : '';

    const alertes = d.alertes.map((a) => {
      const genre = { urgent: 'danger', important: 'alerte', info: 'info' }[a.gravite] || 'info';
      return `<div class="message ${genre}">
        <div class="entre"><div>${ech(a.message)}</div>
        ${a.lien ? `<a class="bouton petit-bouton" href="${a.lien}">Traiter</a>` : ''}</div></div>`;
    }).join('');

    const maxEvolution = Math.max(1, ...d.evolution.flatMap((e) => [e.produits, e.charges]));
    const graphique = d.evolution.length ? `
      <div class="histogramme">
        ${d.evolution.map((e) => `
          <div class="colonne" title="${fperiode(e.periode)} — produits ${fm(e.produits, true)}, charges ${fm(e.charges, true)}">
            <div class="barre produits" style="height:${Math.max(1, (e.produits / maxEvolution) * 100)}%"></div>
            <div class="barre charges" style="height:${Math.max(1, (e.charges / maxEvolution) * 100)}%"></div>
            <div class="etiq">${e.periode.slice(5)}</div>
          </div>`).join('')}
      </div>
      <div class="legende"><span class="p">Produits</span><span class="c">Charges</span></div>`
      : '<div class="vide">Aucun mouvement enregistré sur cet exercice.</div>';

    let metiers = '';
    if (d.promotion) {
      metiers += carte('Promotion immobilière', `<div class="grille c4">
        ${indicateur('Programmes en cours', d.promotion.programmes)}
        ${indicateur('Lots vendus', d.promotion.lots_vendus,
          `${d.promotion.lots_disponibles} encore disponibles`)}
        ${indicateur('Encaissé sur contrats', fm(d.promotion.encaisse, true), '', 'succes')}
        ${indicateur('Reste à encaisser', fm(d.promotion.reste_a_encaisser, true))}
      </div>`, '<a class="bouton petit-bouton" href="#/promotion">Ouvrir</a>');
    }
    if (d.agence) {
      metiers += carte('Agence immobilière', `<div class="grille c4">
        ${indicateur('Mandats actifs', d.agence.mandats_actifs)}
        ${indicateur('Baux en gestion', d.agence.baux_actifs)}
        ${indicateur('Loyers du mois', fm(d.agence.loyers_du_mois, true))}
        ${indicateur('Commissions de l\'exercice', fm(d.agence.commissions_exercice, true), '', 'succes')}
      </div>`, '<a class="bouton petit-bouton" href="#/agence">Ouvrir</a>');
    }

    zone.innerHTML = `
      ${premiersPas}
      ${alertes}
      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Chiffre d\'affaires', fm(i.chiffre_affaires, true),
          'Comptes 70 — hors loyers encaissés pour compte de tiers', 'accent')}
        ${indicateur('Résultat de l\'exercice', fm(i.resultat, true),
          `Produits ${fm(i.produits)} − charges ${fm(i.charges)}`,
          i.resultat >= 0 ? 'succes' : 'danger')}
        ${indicateur('Trésorerie', fm(i.tresorerie, true),
          `Banque ${fm(i.banque)} · caisse ${fm(i.caisse)}`,
          i.tresorerie >= 0 ? '' : 'danger')}
        ${indicateur('TVA du mois', fm(Math.abs(i.tva_solde), true),
          i.tva_solde >= 0 ? 'à décaisser' : 'crédit de TVA')}
      </div>

      <div class="grille c2">
        ${carte('Activité de l\'exercice', graphique)}
        ${carte('Postes de bilan à surveiller', `<div class="liste-definitions">
          ${[['Créances clients', i.creances_clients],
             ['Dettes fournisseurs', i.dettes_fournisseurs],
             ['Avances reçues sur ventes sur plan', i.avances_clients_vsp],
             ['Dû aux propriétaires (gestion locative)', i.du_aux_proprietaires],
             ['TVA collectée', i.tva_collectee],
             ['TVA déductible', i.tva_deductible]].map(([libelle, valeur]) =>
            `<dt>${ech(libelle)}</dt><dd class="num">${
              centimesDiscrets(montantNul(fm(valeur, true)))}</dd>`).join('')}
        </div>`)}
      </div>

      ${metiers}

      <div class="grille c2">
        ${carte('Prochaines échéances déclaratives',
          d.obligations.length ? tableau([
            { titre: 'Obligation', cle: 'libelle' },
            { titre: 'Échéance', rendu: (o) => fdate(o.date_limite) },
            {
              titre: '', classe: 'num',
              rendu: (o) => o.date_limite < aujourdhui()
                ? '<span class="etiquette danger">En retard</span>' : '',
            },
          ], d.obligations)
            : `<div class="vide">Aucune échéance enregistrée.
               <div><button onclick="genereObligations()">Générer le calendrier fiscal</button></div></div>`,
          '<a class="bouton petit-bouton" href="#/fiscalite/obligations">Tout voir</a>', true)}

        ${carte('Dernières écritures', tableau([
          { titre: 'Date', rendu: (e) => fdate(e.date) },
          { titre: 'Jal', cle: 'journal' },
          { titre: 'Libellé', rendu: (e) => `<div class="tronque">${ech(e.libelle)}</div>` },
          { titre: 'Montant', classe: 'num', rendu: (e) => fm(e.montant) },
        ], d.dernieres_ecritures, { messageVide: 'Aucune écriture.' }),
          '<a class="bouton petit-bouton" href="#/comptabilite/ecritures">Journal</a>', true)}
      </div>`;
  },
};

async function genereObligations() {
  try {
    const r = await envoie('/api/obligations/generer', { annee: new Date().getFullYear() });
    notifie(`${r.creees} échéance(s) ajoutée(s) au calendrier ${r.annee}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* ---------------------------------------------------------------- Tiers -- */

const CHAMPS_TIERS = [
  { groupe: 'Identité' },
  {
    nom: 'type', libelle: 'Type de tiers', type: 'select', requis: true, vide: false,
    options: [['client', 'Client'], ['fournisseur', 'Fournisseur'],
      ['mandant', 'Propriétaire mandant'], ['notaire', 'Notaire'],
      ['administration', 'Administration'], ['autre', 'Autre']],
  },
  {
    nom: 'forme', libelle: 'Forme', type: 'select', vide: false,
    options: [['physique', 'Personne physique'], ['morale', 'Personne morale']],
  },
  { nom: 'raison_sociale', libelle: 'Raison sociale / Nom complet', requis: true, large: true },
  { nom: 'nom', libelle: 'Nom' },
  { nom: 'prenom', libelle: 'Prénom' },
  { nom: 'piece_identite', libelle: 'Pièce d\'identité (n°)' },
  { groupe: 'Coordonnées' },
  { nom: 'telephone', libelle: 'Téléphone' },
  { nom: 'telephone2', libelle: 'Téléphone 2' },
  { nom: 'email', libelle: 'Courriel', type: 'email' },
  { nom: 'adresse', libelle: 'Adresse', large: true },
  { nom: 'commune', libelle: 'Commune' },
  { nom: 'wilaya', libelle: 'Wilaya' },
  { groupe: 'Identifiants fiscaux' },
  { nom: 'nif', libelle: 'NIF', aide: '15 ou 20 chiffres' },
  { nom: 'nis', libelle: 'NIS' },
  { nom: 'rc', libelle: 'Registre de commerce' },
  { nom: 'article_imposition', libelle: 'Article d\'imposition' },
  { nom: 'banque_rib', libelle: 'RIB' },
  { nom: 'compte_comptable', libelle: 'Compte comptable', aide: 'Vide = compte par défaut du type' },
  { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
];

App.pages.tiers = {
  titre: 'Tiers',
  async afficher(zone, route) {
    if (route.segments[1] && route.segments[1] !== 'nouveau') return ficheTiers(zone, route.segments[1]);

    const type = route.parametres.type || '';
    const q = route.parametres.q || '';
    actionsPage(`<button class="primaire" onclick="editeTiers()">+ Nouveau tiers</button>`
      + boutonImport('tiers', 'Importer des tiers')
      + `<button onclick="telecharge('/api/export/balance-auxiliaire',{type:'${type || 'client'}'})">Balance auxiliaire</button>`);

    const d = await charge('/api/tiers', { type, q, limite: 500 });
    zone.innerHTML = `
      <div class="barre-outils">
        <label class="champ recherche"><span>Rechercher</span>
          <input id="q" value="${ech(q)}" placeholder="Nom, code, téléphone, NIF…"></label>
        <label class="champ"><span>Type</span>
          <select id="type">
            <option value="">Tous</option>
            ${[['client', 'Clients'], ['fournisseur', 'Fournisseurs'],
              ['mandant', 'Propriétaires'], ['notaire', 'Notaires'],
              ['administration', 'Administrations'], ['autre', 'Autres']]
              .map(([v, l]) => `<option value="${v}" ${v === type ? 'selected' : ''}>${l}</option>`).join('')}
          </select></label>
      </div>
      ${carte('', tableau([
        { titre: 'Code', cle: 'code', largeur: '80px' },
        { titre: 'Raison sociale', rendu: (t) => `<strong>${ech(t.raison_sociale)}</strong>` },
        { titre: 'Type', rendu: (t) => etiquette(t.type) },
        { titre: 'Téléphone', cle: 'telephone' },
        { titre: 'Commune', cle: 'commune' },
        { titre: 'NIF', cle: 'nif' },
        {
          titre: '', classe: 'num',
          rendu: (t) => `<button class="petit-bouton" onclick="event.stopPropagation();editeTiers(${t.id})">Modifier</button>`,
        },
      ], d.tiers, {
        clic: true, icone: '👥', messageVide: 'Aucun tiers. Créez votre premier client ou fournisseur.',
        attributsLigne: (t) => `onclick="navigue('/tiers/${t.id}')"`,
      }), '', true)}`;

    const relance = () => navigue(`/tiers?type=${$('#type').value}&q=${encodeURIComponent($('#q').value)}`);
    $('#type').onchange = relance;
    $('#q').onkeydown = (e) => { if (e.key === 'Enter') relance(); };
  },
};

async function ficheTiers(zone, id) {
  const t = await api(`/api/tiers/${id}`);
  sousTitre(`${t.code} — ${ETIQUETTES[t.type]?.[0] || t.type}`);
  $('#titre-page').textContent = t.raison_sociale;
  actionsPage(`<button onclick="editeTiers(${t.id})">Modifier</button>
    ${t.type === 'mandant' ? `<button onclick="window.open('/api/proprietaires/${t.id}/releve','_blank')">Relevé de gestion</button>` : ''}
    <a class="bouton" href="#/tiers">Retour</a>`);

  const solde = t.solde;
  zone.innerHTML = `
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Solde du compte', fm(solde, true),
        solde > 0 ? 'Débiteur — il vous doit' : (solde < 0 ? 'Créditeur — vous lui devez' : 'Soldé'),
        solde > 0 ? 'danger' : (solde < 0 ? 'succes' : ''))}
      ${indicateur('Total débit', fm(t.total_debit, true))}
      ${indicateur('Total crédit', fm(t.total_credit, true))}
      ${indicateur('Compte collectif', ech(t.compte))}
    </div>

    <div class="grille c2">
      ${carte('Coordonnées', `<div class="liste-definitions">
        <dt>Adresse</dt><dd>${ech(t.adresse || '—')} ${ech(t.commune || '')} ${ech(t.wilaya || '')}</dd>
        <dt>Téléphone</dt><dd>${ech(t.telephone || '—')}</dd>
        <dt>Courriel</dt><dd>${ech(t.email || '—')}</dd>
        <dt>NIF</dt><dd>${ech(t.nif || '—')}</dd>
        <dt>NIS</dt><dd>${ech(t.nis || '—')}</dd>
        <dt>RC</dt><dd>${ech(t.rc || '—')}</dd>
        <dt>Article d'imposition</dt><dd>${ech(t.article_imposition || '—')}</dd>
        <dt>RIB</dt><dd>${ech(t.banque_rib || '—')}</dd>
      </div>`)}
      ${carte('Factures', tableau([
        { titre: 'N°', cle: 'numero' },
        { titre: 'Date', rendu: (f) => fdate(f.date) },
        { titre: 'Objet', rendu: (f) => `<div class="tronque">${ech(f.objet || '')}</div>` },
        { titre: 'TTC', classe: 'num', rendu: (f) => fm(f.montant_ttc) },
        { titre: 'Statut', rendu: (f) => etiquette(f.statut) },
      ], t.factures, { messageVide: 'Aucune facture.' }), '', true)}
    </div>

    ${carte('Mouvements du compte', tableau([
      { titre: 'Date', rendu: (m) => fdate(m.date) },
      { titre: 'Jal', cle: 'journal' },
      { titre: 'Pièce', cle: 'num_ecriture' },
      { titre: 'Compte', cle: 'compte' },
      { titre: 'Libellé', rendu: (m) => ech(m.libelle || m.libelle_ecriture) },
      { titre: 'Débit', classe: 'num', rendu: (m) => m.debit ? fm(m.debit) : '' },
      { titre: 'Crédit', classe: 'num', rendu: (m) => m.credit ? fm(m.credit) : '' },
      { titre: 'Lettr.', cle: 'lettrage' },
    ], t.mouvements, { messageVide: 'Aucun mouvement comptable.' }), '', true)}`;
}

async function editeTiers(id) {
  const existant = id ? await api(`/api/tiers/${id}`) : {};
  const corps = modale({
    titre: id ? 'Modifier le tiers' : 'Nouveau tiers',
    contenu: formulaire(CHAMPS_TIERS, existant),
    large: true,
    boutons: [
      { libelle: 'Annuler' },
      {
        libelle: 'Enregistrer', classe: 'primaire',
        action: async (racine) => {
          const donnees = litFormulaire(racine, CHAMPS_TIERS);
          if (id) await envoie(`/api/tiers/${id}`, donnees, 'PUT');
          else await envoie('/api/tiers', donnees);
          videCache('tiers');
          notifie('Tiers enregistré.', 'succes');
          afficheRoute();
        },
      },
    ],
  });
  return corps;
}

/* ---------------------------------------------------------- Trésorerie -- */

App.pages.tresorerie = {
  titre: 'Trésorerie',
  async afficher(zone, route) {
    if (route.segments[1]) return detailTresorerie(zone, route.segments[1]);
    const d = await charge('/api/tresorerie');
    actionsPage(`<button onclick="mouvementRapide()">Saisie rapide</button>
      <button onclick="virementInterne()">Virement interne</button>
      <button class="primaire" onclick="editeCompteTresorerie()">+ Compte</button>`);

    zone.innerHTML = `
      <div class="grille c3" style="margin-bottom:16px">
        ${d.comptes.map((c) => `
          <div class="indicateur ${c.solde < 0 ? 'danger' : 'accent'} pointeur"
               onclick="navigue('/tresorerie/${c.id}')">
            <div class="libelle">${ech(c.libelle)} ${c.est_sequestre ? '· séquestre' : ''}</div>
            <div class="valeur">${fm(c.solde, true)}</div>
            <div class="detail">${ech(c.type)} — compte ${ech(c.compte)}
              ${c.rib ? '· ' + ech(c.rib) : ''}</div>
          </div>`).join('')}
        ${indicateur('Total disponible', fm(d.total, true), `au ${fdate(d.au)}`, 'succes')}
      </div>
      ${carte('Derniers règlements', await listeReglements(), '', true)}`;
  },
};

async function listeReglements() {
  const d = await charge('/api/reglements', { limite: 40 });
  return tableau([
    { titre: 'Date', rendu: (r) => fdate(r.date) },
    { titre: 'Sens', rendu: (r) => r.sens === 'encaissement' ? '<span class="vert">Entrée</span>' : '<span class="rouge">Sortie</span>' },
    { titre: 'Tiers', cle: 'tiers_nom' },
    { titre: 'Compte', cle: 'tresorerie' },
    { titre: 'Libellé', rendu: (r) => `<div class="tronque">${ech(r.libelle || '')}</div>` },
    { titre: 'Référence', cle: 'reference' },
    { titre: 'Montant', classe: 'num', rendu: (r) => fm(r.montant) },
  ], d.reglements, { messageVide: 'Aucun règlement enregistré.' });
}

async function detailTresorerie(zone, id) {
  const d = await api(`/api/tresorerie/${id}/mouvements?au=${aujourdhui()}`);
  $('#titre-page').textContent = d.compte.libelle;
  sousTitre(`Compte ${d.compte.compte} — ${d.compte.type}`);
  actionsPage(`<button onclick="mouvementRapide(${id})">Saisie rapide</button>
    <button onclick="telecharge('/api/export/tresorerie',{tresorerie:${id}})">Exporter</button>
    <button onclick="nouveauRapprochement(${id})">Rapprochement bancaire</button>
    <a class="bouton" href="#/tresorerie">Retour</a>`);

  zone.innerHTML = `
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Solde actuel', fm(d.solde_final, true), '', d.solde_final < 0 ? 'danger' : 'succes')}
      ${indicateur('Total des entrées', fm(d.total_entrees, true))}
      ${indicateur('Total des sorties', fm(d.total_sorties, true))}
      ${indicateur('Nombre de mouvements', d.mouvements.length)}
    </div>
    ${carte('Mouvements', tableau([
      { titre: 'Date', rendu: (m) => fdate(m.date) },
      { titre: 'Jal', cle: 'journal' },
      { titre: 'N°', cle: 'num_ecriture' },
      { titre: 'Libellé', rendu: (m) => ech(m.libelle || m.libelle_ecriture) },
      { titre: 'Tiers', cle: 'tiers' },
      { titre: 'Entrée', classe: 'num', rendu: (m) => m.debit ? `<span class="vert">${fm(m.debit)}</span>` : '' },
      { titre: 'Sortie', classe: 'num', rendu: (m) => m.credit ? `<span class="rouge">${fm(m.credit)}</span>` : '' },
      { titre: 'Solde', classe: 'num', rendu: (m) => `<strong>${fm(m.solde_progressif)}</strong>` },
      { titre: 'Pointé', classe: 'centre', rendu: (m) => m.pointee ? '✓' : '' },
    ], d.mouvements, { messageVide: 'Aucun mouvement sur ce compte.' }), '', true)}`;
}

async function mouvementRapide(tresorerieId) {
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Compte', type: 'select', requis: true, vide: false, options: await optionsTresorerie(), defaut: tresorerieId },
    { nom: 'sens', libelle: 'Sens', type: 'select', requis: true, vide: false, options: [['sortie', 'Sortie (décaissement)'], ['entree', 'Entrée (encaissement)']] },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'montant', libelle: 'Montant', type: 'montant', requis: true },
    { nom: 'compte', libelle: 'Compte de contrepartie', type: 'select', requis: true, options: await optionsComptes(), aide: 'Charge, produit ou compte de tiers' },
    { nom: 'tiers_id', libelle: 'Tiers (facultatif)', type: 'select', options: await optionsTiers() },
    { nom: 'libelle', libelle: 'Libellé', requis: true, large: true },
    { nom: 'piece', libelle: 'N° de pièce' },
  ];
  modale({
    titre: 'Saisie rapide de trésorerie',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/tresorerie/mouvement', litFormulaire(r, champs));
        notifie('Mouvement enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function virementInterne() {
  const comptes = await optionsTresorerie();
  const champs = [
    { nom: 'source_id', libelle: 'Depuis', type: 'select', requis: true, vide: false, options: comptes },
    { nom: 'destination_id', libelle: 'Vers', type: 'select', requis: true, vide: false, options: comptes },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'montant', libelle: 'Montant', type: 'montant', requis: true },
    { nom: 'libelle', libelle: 'Libellé', large: true },
  ];
  modale({
    titre: 'Virement interne',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Virer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/tresorerie/virement', litFormulaire(r, champs));
        notifie('Virement enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function editeCompteTresorerie() {
  const champs = [
    { nom: 'code', libelle: 'Code', requis: true },
    { nom: 'libelle', libelle: 'Libellé', requis: true },
    { nom: 'type', libelle: 'Type', type: 'select', vide: false, options: [['banque', 'Banque'], ['caisse', 'Caisse'], ['ccp', 'CCP']] },
    { nom: 'compte', libelle: 'Compte comptable', type: 'select', requis: true, options: await optionsComptes('5') },
    { nom: 'banque', libelle: 'Banque' },
    { nom: 'agence', libelle: 'Agence' },
    { nom: 'rib', libelle: 'RIB', large: true },
    { nom: 'est_sequestre', libelle: 'Compte séquestre (fonds VSP)', type: 'case' },
  ];
  modale({
    titre: 'Nouveau compte de trésorerie',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/tresorerie', litFormulaire(r, champs));
        videCache('tresorerie');
        notifie('Compte créé.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function nouveauRapprochement(tresorerieId) {
  const champs = [
    { nom: 'date_arrete', libelle: 'Date d\'arrêté du relevé', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'solde_releve', libelle: 'Solde figurant sur le relevé', type: 'montant', requis: true },
  ];
  modale({
    titre: 'Nouveau rapprochement bancaire',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/rapprochements', { tresorerie_id: tresorerieId, ...litFormulaire(r, champs) });
        navigue(`/rapprochement/${d.id}`);
      },
    }],
  });
}

App.pages.rapprochement = {
  titre: 'Rapprochement bancaire',
  async afficher(zone, route) {
    const id = route.segments[1];
    const d = await api(`/api/rapprochements/${id}`);
    sousTitre(`${d.compte_libelle} — arrêté au ${fdate(d.date_arrete)}`);
    actionsPage('<a class="bouton" href="#/tresorerie">Retour</a>');

    zone.innerHTML = `
      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Solde comptable', fm(d.solde_comptable, true))}
        ${indicateur('Solde du relevé', fm(d.solde_releve, true))}
        ${indicateur('Mouvements non pointés', fm(d.montant_non_pointe, true))}
        ${indicateur('Écart', fm(d.ecart, true), d.ecart === 0 ? 'Rapprochement juste' : 'À justifier',
          d.ecart === 0 ? 'succes' : 'danger')}
      </div>
      ${carte('Mouvements à pointer', `
        <div class="message info">Cochez les opérations qui figurent sur le relevé bancaire.
          Les mouvements non pointés expliquent l'écart entre la banque et la comptabilité.</div>
        ${tableau([
          { titre: '', classe: 'centre', rendu: (m) => `<input type="checkbox" data-ligne="${m.id}" ${m.pointee ? 'checked' : ''}>` },
          { titre: 'Date', rendu: (m) => fdate(m.date) },
          { titre: 'N°', cle: 'num_ecriture' },
          { titre: 'Libellé', rendu: (m) => ech(m.libelle) },
          { titre: 'Tiers', cle: 'tiers' },
          { titre: 'Débit', classe: 'num', rendu: (m) => m.debit ? fm(m.debit) : '' },
          { titre: 'Crédit', classe: 'num', rendu: (m) => m.credit ? fm(m.credit) : '' },
        ], d.mouvements, { messageVide: 'Aucun mouvement sur la période.' })}`,
        `<button class="primaire" onclick="enregistrePointage(${id})">Enregistrer le pointage</button>`)}`;
  },
};

async function enregistrePointage(id) {
  const cochees = $$('[data-ligne]').filter((c) => c.checked).map((c) => +c.dataset.ligne);
  const decochees = $$('[data-ligne]').filter((c) => !c.checked).map((c) => +c.dataset.ligne);
  try {
    await api(`/api/rapprochements/${id}/pointer`, { method: 'POST', corps: { lignes: cochees, pointer: true } });
    await api(`/api/rapprochements/${id}/pointer`, { method: 'POST', corps: { lignes: decochees, pointer: false } });
    notifie('Pointage enregistré.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* ---------------------------------------------------------- Paramètres -- */

App.pages.parametres = {
  titre: 'Paramètres',
  async afficher(zone, route) {
    const onglet = route.segments[1] || 'dossier';
    const onglets = [['dossier', 'Dossier'], ['exercices', 'Exercices'],
      ['plan', 'Plan comptable'], ['fiscalite', 'Fiscalité'],
      ['notifications', 'Notifications'], ['import', 'Import de données'],
      ['utilisateurs', 'Utilisateurs'], ['sauvegarde', 'Sauvegarde & données'],
      ['apparence', 'Personnalisation'], ['maj', 'Mise à jour']];
    zone.innerHTML = `<div class="onglets">${onglets.map(([v, l]) =>
      `<button class="${v === onglet ? 'actif' : ''}" onclick="navigue('/parametres/${v}')">${l}</button>`).join('')}</div>
      <div id="zone-onglet"><div class="vide">Chargement…</div></div>`;
    const cible = $('#zone-onglet');
    const rendus = {
      dossier: ongletDossier, exercices: ongletExercices, plan: ongletPlan,
      fiscalite: ongletFiscalite, notifications: ongletNotifications,
      import: ongletImport, maj: ongletMaj, apparence: ongletApparence,
      utilisateurs: ongletUtilisateurs, sauvegarde: ongletSauvegarde,
    };
    await (rendus[onglet] || ongletDossier)(cible);
  },
};

const CHAMPS_SOCIETE = [
  { groupe: 'Identité' },
  { nom: 'raison_sociale', libelle: 'Raison sociale', requis: true, large: true },
  { nom: 'forme_juridique', libelle: 'Forme juridique', type: 'select', options: ['SARL', 'EURL', 'SPA', 'SNC', 'SCS', 'Personne physique'] },
  {
    nom: 'activite', libelle: 'Activité', type: 'select', vide: false,
    options: [['agence', 'Agence immobilière'], ['promotion', 'Promotion immobilière'], ['mixte', 'Agence + promotion']],
  },
  { nom: 'capital', libelle: 'Capital social', type: 'montant' },
  { groupe: 'Coordonnées' },
  { nom: 'adresse', libelle: 'Adresse', large: true },
  { nom: 'commune', libelle: 'Commune' },
  { nom: 'wilaya', libelle: 'Wilaya' },
  { nom: 'telephone', libelle: 'Téléphone' },
  { nom: 'email', libelle: 'Courriel', type: 'email' },
  { groupe: 'Identifiants fiscaux (mentions obligatoires sur factures)' },
  { nom: 'nif', libelle: 'NIF' },
  { nom: 'nis', libelle: 'NIS' },
  { nom: 'rc', libelle: 'Registre de commerce' },
  { nom: 'article_imposition', libelle: 'Article d\'imposition' },
  { nom: 'taux_ibs', libelle: 'Taux IBS', type: 'taux', aide: '23 % BTPH · 26 % services' },
  { nom: 'assujetti_tva', libelle: 'Assujetti à la TVA', type: 'case' },
  { groupe: 'Promotion immobilière' },
  { nom: 'agrement_promoteur', libelle: 'N° d\'agrément de promoteur' },
  { nom: 'num_fgcmpi', libelle: 'N° d\'adhésion FGCMPI' },
  { groupe: 'Banque' },
  { nom: 'banque_nom', libelle: 'Banque' },
  { nom: 'banque_rib', libelle: 'RIB', large: true },
];

async function ongletDossier(zone) {
  const soc = await api(`/api/societes/${App.etat.societe.id}`);
  const form = formulaire(CHAMPS_SOCIETE, { ...soc, capital: soc.capital_cts, assujetti_tva: soc.assujetti_tva });
  zone.innerHTML = '';
  const boite = document.createElement('div');
  boite.className = 'carte';
  boite.innerHTML = '<div class="corps"></div>';
  $('.corps', boite).appendChild(form);
  const bouton = document.createElement('button');
  bouton.className = 'primaire';
  bouton.textContent = 'Enregistrer les modifications';
  bouton.onclick = async () => {
    try {
      await api(`/api/societes/${soc.id}`, { method: 'PUT', corps: litFormulaire(form, CHAMPS_SOCIETE) });
      notifie('Dossier mis à jour.', 'succes');
      await chargeSocietes();
    } catch (err) { erreur(err); }
  };
  $('.corps', boite).appendChild(bouton);
  zone.appendChild(boite);
}

/** Raccourci vers l'éditeur des taux et barèmes (défini dans pages-fisc.js). */
async function ongletFiscalite(zone) {
  return vueParametresFiscaux(zone, routeCourante());
}

async function ongletExercices(zone) {
  const d = await charge('/api/exercices');
  zone.innerHTML = carte('Exercices comptables', tableau([
    { titre: 'Libellé', cle: 'libelle' },
    { titre: 'Du', rendu: (e) => fdate(e.date_debut) },
    { titre: 'Au', rendu: (e) => fdate(e.date_fin) },
    { titre: 'État', rendu: (e) => e.cloture ? '<span class="etiquette">Clôturé</span>' : '<span class="etiquette succes">Ouvert</span>' },
    { titre: 'Clôturé le', rendu: (e) => fdate(e.date_cloture) },
    {
      titre: '', classe: 'num',
      rendu: (e) => e.cloture ? '' : `<button class="petit-bouton" onclick="navigue('/comptabilite/cloture')">Clôturer</button>`,
    },
  ], d.exercices), '<button class="primaire" onclick="nouvelExercice()">+ Exercice</button>', true);
}

async function nouvelExercice() {
  const annee = new Date().getFullYear() + 1;
  const champs = [
    { nom: 'libelle', libelle: 'Libellé', requis: true, defaut: String(annee) },
    { nom: 'date_debut', libelle: 'Du', type: 'date', requis: true, defaut: `${annee}-01-01` },
    { nom: 'date_fin', libelle: 'Au', type: 'date', requis: true, defaut: `${annee}-12-31` },
  ];
  modale({
    titre: 'Nouvel exercice',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/exercices', litFormulaire(r, champs));
        notifie('Exercice créé.', 'succes');
        await chargeSocietes();
        afficheRoute();
      },
    }],
  });
}

async function ongletPlan(zone) {
  const d = await charge('/api/comptes');
  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ recherche"><span>Rechercher un compte</span>
        <input id="rech-compte" placeholder="Numéro ou intitulé"></label>
    </div>
    ${carte(`Plan comptable SCF — ${d.comptes.length} comptes`, `<div id="table-comptes">${tableComptes(d.comptes)}</div>`,
      '<button class="primaire" onclick="editeCompte()">+ Compte</button>', true)}`;
  $('#rech-compte').oninput = (e) => {
    const q = e.target.value.toLowerCase();
    const filtres = d.comptes.filter((c) =>
      c.numero.startsWith(q) || c.intitule.toLowerCase().includes(q));
    $('#table-comptes').innerHTML = tableComptes(filtres);
  };
}

function tableComptes(comptes) {
  return tableau([
    { titre: 'Numéro', cle: 'numero', largeur: '90px' },
    { titre: 'Intitulé', rendu: (c) => ech(c.intitule) },
    { titre: 'Classe', cle: 'classe', classe: 'centre' },
    { titre: 'Nature', cle: 'nature' },
    { titre: 'Collectif', rendu: (c) => c.collectif ? etiquette(c.collectif) : '' },
    { titre: 'Lettrable', classe: 'centre', rendu: (c) => c.lettrable ? '✓' : '' },
    { titre: 'Actif', classe: 'centre', rendu: (c) => c.actif ? '✓' : '✗' },
    {
      titre: '', classe: 'num',
      rendu: (c) => `<button class="petit-bouton" onclick='editeCompte(${JSON.stringify(c).replace(/'/g, "&#39;")})'>Modifier</button>`,
    },
  ], comptes.slice(0, 600), { messageVide: 'Aucun compte.' });
}

async function editeCompte(compte) {
  const champs = [
    { nom: 'numero', libelle: 'Numéro', requis: true, attributs: compte ? 'readonly' : '' },
    { nom: 'intitule', libelle: 'Intitulé', requis: true, large: true },
    {
      nom: 'nature', libelle: 'Nature', type: 'select', vide: false,
      options: [['actif', 'Actif'], ['passif', 'Passif'], ['charge', 'Charge'], ['produit', 'Produit'], ['mixte', 'Mixte']],
    },
    {
      nom: 'collectif', libelle: 'Compte collectif de', type: 'select',
      options: [['client', 'Clients'], ['fournisseur', 'Fournisseurs'], ['mandant', 'Mandants'], ['salarie', 'Salariés']],
    },
    { nom: 'lettrable', libelle: 'Lettrable', type: 'case' },
    { nom: 'actif', libelle: 'Actif', type: 'case', defaut: true },
  ];
  modale({
    titre: compte ? `Compte ${compte.numero}` : 'Nouveau compte',
    contenu: formulaire(champs, compte || { actif: true }),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, champs);
        if (compte) await envoie(`/api/comptes/${compte.id}`, donnees, 'PUT');
        else await envoie('/api/comptes', donnees);
        videCache('comptes');
        notifie('Compte enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function ongletUtilisateurs(zone) {
  const d = await api('/api/utilisateurs');
  zone.innerHTML = carte('Utilisateurs', tableau([
    { titre: 'Identifiant', cle: 'identifiant' },
    { titre: 'Nom', cle: 'nom_complet' },
    { titre: 'Rôle', rendu: (u) => etiquette(u.role) },
    { titre: 'Dernière connexion', rendu: (u) => u.derniere_visite || '—' },
    { titre: 'Actif', classe: 'centre', rendu: (u) => u.actif ? '✓' : '✗' },
  ], d.utilisateurs), '<button class="primaire" onclick="nouvelUtilisateur()">+ Utilisateur</button>', true)
    + carte('Mon mot de passe', `
      <div class="ligne-champs">
        <label class="champ"><span>Mot de passe actuel</span><input type="password" id="mdp-ancien"></label>
        <label class="champ"><span>Nouveau mot de passe</span><input type="password" id="mdp-nouveau"></label>
      </div>
      <button class="primaire" onclick="changeMotDePasse()">Changer</button>`);
}

async function changeMotDePasse() {
  try {
    await api('/api/mot-de-passe', {
      method: 'POST',
      corps: { ancien: $('#mdp-ancien').value, nouveau: $('#mdp-nouveau').value },
    });
    notifie('Mot de passe modifié.', 'succes');
    $('#mdp-ancien').value = ''; $('#mdp-nouveau').value = '';
  } catch (err) { erreur(err); }
}

async function nouvelUtilisateur() {
  const champs = [
    { nom: 'identifiant', libelle: 'Identifiant', requis: true },
    { nom: 'nom_complet', libelle: 'Nom complet', requis: true },
    { nom: 'mot_de_passe', libelle: 'Mot de passe', type: 'password', requis: true },
    {
      nom: 'role', libelle: 'Rôle', type: 'select', vide: false,
      options: [['comptable', 'Comptable'], ['admin', 'Administrateur'], ['lecture', 'Consultation seule']],
    },
  ];
  modale({
    titre: 'Nouvel utilisateur',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        await api('/api/utilisateurs', { method: 'POST', corps: litFormulaire(r, champs) });
        notifie('Utilisateur créé.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* --------------------------------------------------- Mise à jour -------- */

/** Fichier de mise à jour choisi, conservé entre le contrôle et l'application. */
let _paquetMaj = null;

async function ongletMaj(zone) {
  const d = await api('/api/maj/etat');
  zone.innerHTML = `
    ${await compteRenduDerniereMaj()}
    ${carte('Mettre à jour', `
      <div class="message info">
        <strong>Vous êtes en version ${ech(d.version)}</strong>
        Quand vous recevez un fichier de mise à jour, déposez-le ici. Il est
        contrôlé avant d'être appliqué, vos données sont sauvegardées, et
        l'application se rouvre toute seule. <strong>Rien n'est perdu&nbsp;:</strong>
        en cas de problème, la version précédente est remise en place
        automatiquement.
      </div>
      <div class="rangee" style="align-items:flex-end; gap:12px">
        <label class="champ" style="flex:1">
          <span>Fichier de mise à jour (.zip)</span>
          <input type="file" id="maj-fichier" accept=".zip"></label>
        <button class="primaire" id="maj-controler">Contrôler le fichier</button>
      </div>
      <div id="maj-resultat"></div>`)}

    ${d.changelog ? carte('Ce que contient votre version', `
      <div class="notes-version">${notesEnHtml(d.changelog)}</div>`) : ''}`;

  _paquetMaj = null;
  $('#maj-fichier').onchange = (e) => {
    _paquetMaj = e.target.files[0] || null;
    $('#maj-resultat').innerHTML = '';
  };
  $('#maj-controler').onclick = controleMaj;
  annonceVersionPubliee();
}

/* Si l'utilisateur a fermé l'onglet pendant l'installation — ou rouvert
   l'application lui-même — il n'a jamais vu le résultat. Il le trouve ici. */
async function compteRenduDerniereMaj() {
  let etat = null;
  try { etat = await api('/api/maj/resultat'); } catch (err) { return ''; }
  if (!etat || !etat.present) return '';

  const reussi = etat.ok === true
    || (etat.version_apres && etat.version_apres === etat.version_actuelle);
  const memeVersion = etat.version_avant === etat.version_actuelle;
  // Un compte rendu de réussite déjà constaté n'a plus rien à dire.
  if (reussi && memeVersion) return '';

  if (reussi) {
    return `<div class="message succes"><strong>Dernière mise à jour&nbsp;:
      version ${ech(etat.version_avant || '?')} → ${ech(etat.version_actuelle)},
      faite.</strong> Vos données n'ont pas été touchées.</div>`;
  }
  return `<div class="message danger">
    <strong>La dernière mise à jour n'a pas abouti.</strong>
    ${ech(etat.message || '')} Vous êtes en version ${ech(etat.version_actuelle)}.
    ${etat.journal ? `<details><summary>Détail technique</summary>
      <pre class="journal">${ech(etat.journal)}</pre></details>` : ''}</div>`;
}

/**
 * Annonce une version plus récente, si une adresse de publication est
 * configurée. Sans elle, aucun appel réseau n'est fait.
 */
async function annonceVersionPubliee() {
  let d;
  try { d = await api('/api/maj/verifier'); } catch (err) { return; }
  if (!d.active) return;
  const zone = $('#maj-resultat');
  if (!zone) return;
  if (!d.joignable) {
    zone.innerHTML = `<div class="message info">
      <strong>Impossible de vérifier les nouvelles versions</strong>
      Pas de connexion pour l'instant. Cela n'empêche rien&nbsp;: l'application
      fonctionne hors ligne.</div>`;
    return;
  }
  if (!d.disponible) {
    zone.innerHTML = `<div class="message succes">
      <strong>Vous êtes à jour</strong>
      La dernière version publiée est la ${ech(d.derniere || d.version)}.</div>`;
    return;
  }
  zone.innerHTML = `<div class="message alerte">
    <strong>La version ${ech(d.derniere)} est disponible</strong>
    Vous êtes en ${ech(d.version)}.
    ${d.lien ? `<div><a href="${ech(d.lien)}" target="_blank" rel="noopener">
      Télécharger le fichier</a>, puis déposez-le ci-dessus.</div>` : ''}</div>
    ${d.notes ? `<div class="notes-version">${notesEnHtml(d.notes)}</div>` : ''}`;
}

/** Rendu minimal des notes de version : titres, listes et gras. */
function notesEnHtml(texte) {
  // Un point de changelog court sur plusieurs lignes (retour à la ligne du
  // fichier). Sans rassembler ces lignes, un « **gras** » ouvert sur l'une
  // et fermé sur la suivante s'afficherait tel quel. On regroupe donc chaque
  // puce ou paragraphe avant de le mettre en forme.
  const sortie = [];
  let bloc = null;   // { type: 'li' | 'p', texte }
  const vide = () => {
    if (!bloc) return;
    sortie.push(bloc.type === 'li' ? `<li>${gras(bloc.texte)}</li>`
                                   : `<p>${gras(bloc.texte)}</p>`);
    bloc = null;
  };
  for (const ligne of String(texte).split('\n')) {
    if (/^##\s+/.test(ligne)) { vide(); sortie.push(`<h4>${ech(ligne.replace(/^##\s+/, ''))}</h4>`); continue; }
    if (/^#\s+/.test(ligne)) { vide(); continue; }
    if (/^[-*]\s+/.test(ligne)) { vide(); bloc = { type: 'li', texte: ligne.replace(/^[-*]\s+/, '') }; continue; }
    if (!ligne.trim()) { vide(); continue; }
    // Ligne de continuation : rattachée au bloc en cours.
    if (bloc) bloc.texte += ' ' + ligne.trim();
    else bloc = { type: 'p', texte: ligne.trim() };
  }
  vide();
  return sortie.join('');
}

function gras(texte) {
  return ech(texte).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                   .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* La toute première section « ## … » du changelog : ce que la version qu'on
   vient d'installer apporte. Sert à le montrer sur l'écran de confirmation,
   pour qu'une mise à jour réussie dise enfin ce qu'elle a changé. */
function notesDerniereVersion(changelog) {
  if (!changelog) return '';
  const lignes = String(changelog).split('\n');
  const debut = lignes.findIndex((l) => /^##\s+/.test(l));
  if (debut < 0) return '';
  const suite = lignes.slice(debut + 1).findIndex((l) => /^##\s+/.test(l));
  const fin = suite < 0 ? lignes.length : debut + 1 + suite;
  return lignes.slice(debut, fin).join('\n').trim();
}

async function controleMaj() {
  if (!_paquetMaj) { notifie('Choisissez d\'abord un fichier.', 'alerte'); return; }
  const zone = $('#maj-resultat');
  zone.innerHTML = '<div class="vide">Contrôle du fichier…</div>';
  try {
    const contenu = await litFichierBase64(_paquetMaj);
    const d = await envoie('/api/maj/analyse', { contenu });
    afficheControleMaj(zone, d, contenu);
  } catch (err) {
    zone.innerHTML = `<div class="message danger"><strong>Fichier refusé</strong>
      ${ech(err.message)}</div>`;
  }
}

function afficheControleMaj(zone, d, contenu) {
  if (d.avertissement) {
    zone.innerHTML = `<div class="message alerte">
      <strong>Rien à faire</strong>${ech(d.avertissement)}</div>`;
    return;
  }
  zone.innerHTML = `
    <div class="message succes">
      <strong>Version ${ech(d.version)} prête à être installée</strong>
      Vous êtes en ${ech(d.version_installee)}. ${d.fichiers} fichier(s) seront
      remplacés. Votre comptabilité n'est pas touchée.
    </div>
    ${d.changelog ? `<div class="notes-version">${notesEnHtml(d.changelog)}</div>` : ''}
    <div class="rangee" style="margin-top:12px">
      <button class="primaire" id="maj-appliquer">
        Installer la version ${ech(d.version)}</button>
    </div>`;

  $('#maj-appliquer', zone).onclick = async () => {
    const bouton = $('#maj-appliquer', zone);
    bouton.disabled = true;
    bouton.textContent = 'Installation en cours…';
    try {
      const r = await envoie('/api/maj/appliquer', { contenu });
      zone.innerHTML = `<div class="message succes">
        <strong>Mise à jour en cours</strong>${ech(r.message)}</div>`;
      // Le serveur s'arrête : la sonde de reconnexion reprendra la main et
      // rechargera la page dès que la nouvelle version répondra.
      attendRetourApresMaj(r.version);
    } catch (err) {
      zone.innerHTML = `<div class="message danger">
        <strong>Mise à jour refusée</strong>${ech(err.message)}</div>`;
    }
  };
}

/* La mise à jour se déroule alors que l'application est fermée : impossible
   de suivre les étapes en direct, il n'y a plus personne pour répondre. On
   montre donc où l'on en est, on attend le retour, puis on affiche ce que
   l'outil a réellement fait — succès comme échec. Une attente muette qui ne
   finit jamais, c'est ce qui donnait l'impression que le bouton ne faisait
   rien. */

const ETAPES_ATTENDUES = [
  'Fermeture de l\'application',
  'Sauvegarde des données',
  'Installation de la nouvelle version',
  'Mise à niveau de la base',
  'Vérification de la comptabilité',
  'Réouverture de l\'application',
];

//: Au-delà, on cesse d'attendre et on dit quoi faire plutôt que de tourner.
const DELAI_MAX_MAJ = 300;

/** Panneau plein écran : attente, puis résultat réel de la mise à jour. */
function attendRetourApresMaj(version) {
  const panneau = document.createElement('div');
  panneau.className = 'ecran-maj';
  panneau.innerHTML = `<div class="carte-maj">
      <div class="logo-grand">⚙️</div>
      <h2>Installation de la version ${ech(version)}</h2>
      <p class="petit">L'application se ferme, s'installe et se rouvre toute
        seule. Ne fermez pas cette fenêtre : elle vous dira ce qui s'est passé.</p>
      <ol class="etapes-maj">${ETAPES_ATTENDUES.map((e) =>
        `<li>${ech(e)}</li>`).join('')}</ol>
      <div class="barre-attente"><div></div></div>
      <p class="petit" id="maj-compteur">Fermeture en cours…</p>
    </div>`;
  document.body.appendChild(panneau);

  const corps = $('.carte-maj', panneau);
  const debut = Date.now();
  let absente = false;

  const secondes = () => Math.round((Date.now() - debut) / 1000);

  const conclut = (html) => {
    clearInterval(minuteur);
    corps.innerHTML = html;
  };

  const minuteur = setInterval(async () => {
    const compteur = $('#maj-compteur', panneau);
    if (compteur) {
      compteur.textContent = absente
        ? `Installation en cours… (${secondes()} s)`
        : `Fermeture en cours… (${secondes()} s)`;
    }
    if (secondes() > DELAI_MAX_MAJ) {
      conclut(`<div class="logo-grand">⏳</div>
        <h2>L'application n'a pas rouvert</h2>
        <div class="message alerte">La mise à jour a été lancée, mais
          l'application ne répond toujours pas après ${DELAI_MAX_MAJ} secondes.
          <strong>Vos données n'ont rien perdu</strong> : une sauvegarde a été
          faite avant toute chose, et l'outil remet la version précédente en
          place s'il n'a pas pu aller au bout.</div>
        <p>Ouvrez le raccourci <strong>Cabinet Immo</strong>. L'écran
          Paramètres → Mise à jour vous dira ce que l'installation a donné.</p>
        <button class="primaire" onclick="location.reload()">Réessayer maintenant</button>`);
      return;
    }
    try {
      const rep = await fetch('/api/etat', { cache: 'no-store' });
      // On n'agit qu'après avoir constaté l'arrêt : sinon on lirait
      // l'ancienne version, encore en train de répondre.
      if (rep.ok && absente) { clearInterval(minuteur); montreResultatMaj(conclut); }
    } catch (err) { absente = true; }
  }, 1500);
}

/** Lit ce que l'outil a consigné et le présente sans enjoliver. */
async function montreResultatMaj(conclut) {
  let etat = null;
  try { etat = await api('/api/maj/resultat'); } catch (err) { /* voir plus bas */ }

  if (!etat || !etat.present) {
    conclut(`<div class="logo-grand">✅</div>
      <h2>L'application a rouvert</h2>
      <p>Elle n'a pas trouvé de compte rendu de la mise à jour. Vérifiez la
        version affichée en haut du menu.</p>
      <button class="primaire" onclick="location.reload()">Continuer</button>`);
    return;
  }

  const reussi = etat.ok === true
    || (etat.version_apres && etat.version_apres === etat.version_actuelle);

  if (reussi) {
    // Ce que la nouvelle version apporte, montré sur la confirmation :
    // une mise à jour réussie dit enfin ce qu'elle a changé.
    let notes = '';
    try {
      const e = await api('/api/maj/etat');
      notes = notesDerniereVersion(e.changelog);
    } catch (err) { /* les notes sont un plus, pas un dû */ }
    conclut(`<div class="logo-grand">✅</div>
      <h2>Mise à jour faite</h2>
      <div class="message succes">Version ${ech(etat.version_avant || '?')} →
        <strong>${ech(etat.version_actuelle)}</strong>. Vos données n'ont pas
        été touchées.</div>
      ${etat.relance === false ? `<div class="message alerte">L'application
        n'a pas pu être rouverte automatiquement, mais vous l'avez rouverte :
        tout est en place.</div>` : ''}
      ${notes ? `<div class="notes-version notes-nouveaute">${notesEnHtml(notes)}</div>` : ''}
      <button class="primaire" onclick="location.reload()">Continuer</button>`);
    return;
  }

  conclut(`<div class="logo-grand">⚠️</div>
    <h2>La mise à jour n'a pas abouti</h2>
    <div class="message danger">${ech(etat.message
      || 'L\'outil s\'est interrompu sans laisser de raison.')}</div>
    <p class="petit">Version installée : <strong>${ech(etat.version_actuelle)}</strong>.
      Une sauvegarde a été faite avant toute opération ; elle est dans
      Paramètres → Sauvegarde &amp; données.</p>
    ${etat.journal ? `<details><summary>Détail technique</summary>
      <pre class="journal">${ech(etat.journal)}</pre></details>` : ''}
    <button class="primaire" onclick="location.reload()">Continuer</button>`);
}

/* ----------------------------------------------- Import de données ------ */

/** Fichier choisi par l'utilisateur, gardé entre le contrôle et la validation. */
let _fichierImport = null;

async function ongletImport(zone) {
  const d = await api('/api/import/modeles');
  const parGroupe = (groupe) => d.modeles.filter((m) => m.groupe === groupe);

  const tableauModeles = (modeles) => `
    <table class="tableau"><thead><tr>
      <th style="width:44px">Ordre</th><th style="width:30%">Données</th>
      <th>Colonnes attendues</th><th style="width:150px"></th>
    </tr></thead><tbody>
      ${modeles.map((m) => `<tr>
        <td class="num tres-petit">${m.rang}</td>
        <td><strong>${ech(m.libelle)}</strong></td>
        <td class="tres-petit">${m.colonnes.map((c) =>
          c.requis ? `<strong>${ech(c.nom)}</strong>` : ech(c.nom)).join(' · ')}</td>
        <td><button class="petit-bouton" onclick="telechargeModele('${m.cle}')">
          Télécharger</button></td>
      </tr>`).join('')}
    </tbody></table>`;

  zone.innerHTML = `
    ${carte('Reprendre un dossier déjà tenu', `
      <div class="message info">
        <strong>Comment procéder</strong>
        1. Téléchargez le modèle correspondant : il contient déjà les en-têtes
        attendus, une ligne d'exemple et une notice. 2. Remplissez-le avec vos
        données, sans toucher à la ligne d'en-têtes. 3. Déposez-le plus bas :
        l'application contrôle tout et vous montre les anomalies
        <em>avant</em> d'enregistrer quoi que ce soit.
      </div>
      <div class="message alerte">
        <strong>Suivez l'ordre indiqué</strong>
        Chaque étape s'appuie sur la précédente : une facture a besoin de son
        tiers, un bail de son bien, un contrat de son lot. Un élément
        introuvable est signalé, jamais créé au hasard.
      </div>
      <p class="petit">L'import <strong>reprend</strong> votre situation, il ne
      recomptabilise pas le passé : baux, lots, contrats et immobilisations
      décrivent l'existant, tandis que la <strong>balance d'ouverture</strong>
      (ou les écritures importées) portent la comptabilité. Sans cela, tout
      serait compté deux fois.</p>`)}

    ${carte('Essayer avant de se lancer', `
      <p>Vous préférez voir à quoi ressemble un dossier rempli avant d'y mettre
      vos propres données&nbsp;? L'application peut créer un
      <strong>dossier d'essai</strong> contenant une année complète : un
      programme de logements, des contrats de vente sur plan, des baux, des
      loyers, la paie et les déclarations.</p>
      <p class="petit">Il vit à côté du vôtre, sans jamais le toucher, et se
      supprime en un clic quand vous n'en avez plus besoin.</p>
      <div id="zone-demo"></div>`,
      `<button id="bouton-demo">Créer un dossier d'essai</button>`)}

    ${d.groupes.map((groupe) => parGroupe(groupe).length
      ? carte(groupe, tableauModeles(parGroupe(groupe)), '', true) : '').join('')}

    ${carte('Déposer un fichier rempli', `
      <div class="ligne-champs">
        <label class="champ"><span>Type de données</span>
          <select id="import-modele">
            ${d.modeles.map((m) =>
              `<option value="${m.cle}">${m.rang}. ${ech(m.libelle)}</option>`).join('')}
          </select></label>
        <label class="champ" id="champ-date-reprise" hidden>
          <span>Date de reprise</span>
          <input type="date" id="import-date-reprise"></label>
        <label class="champ"><span>Fichier</span>
          <input type="file" id="import-fichier" accept=".xlsx,.csv"></label>
      </div>
      <div id="import-resultat"></div>`,
      `<button class="primaire" id="bouton-controler">Contrôler le fichier</button>`)}

    <p class="petit">Les colonnes en gras sont obligatoires. Formats acceptés :
    Excel (.xlsx) et CSV enregistré depuis Excel.</p>`;

  _fichierImport = null;
  const choix = $('#import-modele');
  // La balance d'ouverture est la seule à demander une date.
  const majDateReprise = () => {
    $('#champ-date-reprise').hidden = choix.value !== 'balance_ouverture';
  };
  choix.onchange = () => { majDateReprise(); $('#import-resultat').innerHTML = ''; };
  majDateReprise();
  brancheDepot(zone, () => choix.value);
  $('#bouton-demo', zone).onclick = creeDossierEssai;
}

async function creeDossierEssai() {
  const bouton = $('#bouton-demo');
  const zone = $('#zone-demo');
  bouton.disabled = true;
  bouton.textContent = 'Création en cours…';
  zone.innerHTML = '<div class="vide">Une année d\'activité se construit…</div>';
  try {
    const r = await envoie('/api/demonstration', {});
    zone.innerHTML = `<div class="message succes">
      <strong>${ech(r.message)}</strong>
      Choisissez « SARL EL BARAKA IMMOBILIER (démonstration) » dans la liste
      des dossiers, en haut à gauche, pour l'explorer.</div>
      <div class="rangee" style="margin-top:10px">
        <button class="danger" id="bouton-demo-supprimer">
          Supprimer le dossier d'essai</button>
      </div>`;
    await chargeSocietes();
    $('#bouton-demo-supprimer').onclick = () => supprimeDossierEssai(r.id);
  } catch (err) {
    zone.innerHTML = `<div class="message danger">${ech(err.message)}</div>`;
  } finally {
    bouton.disabled = false;
    bouton.textContent = 'Créer un dossier d\'essai';
  }
}

async function supprimeDossierEssai(id) {
  if (!await confirme('Supprimer le dossier d\'essai ?',
    'Tout son contenu disparaît. Vos dossiers réels ne sont pas touchés, et '
    + 'une sauvegarde est prise avant l\'opération.', 'Supprimer')) return;
  try {
    const r = await api(`/api/societes/${id}`, { method: 'DELETE', corps: {} });
    notifie(`Dossier « ${r.supprime} » supprimé.`, 'succes');
    await chargeSocietes();
    afficheRoute();
  } catch (err) { erreur(err); }
}

/** Câble le choix de fichier et le bouton de contrôle dans une zone donnée. */
function brancheDepot(racine, litModele) {
  _fichierImport = null;
  $('#import-fichier', racine).onchange = (e) => {
    _fichierImport = e.target.files[0] || null;
    $('#import-resultat', racine).innerHTML = '';
  };
  $('#bouton-controler', racine).onclick = () =>
    controleImport(racine, litModele());
}

function telechargeModele(cle) {
  window.open(`/api/import/modele/${cle}`, '_blank');
}

/**
 * Bouton d'import à poser sur une liste. Le titre passe par un attribut
 * `data-`, jamais par la chaîne d'un onclick : une apostrophe française y
 * fermerait la chaîne.
 */
function boutonImport(cle, titre) {
  return `<button data-import="${ech(cle)}" data-titre="${ech(titre)}"
    onclick="modaleImport(this.dataset.import, this.dataset.titre)">Importer</button>`;
}

/**
 * Import ouvert depuis une liste : le type de données est déjà connu, il n'y
 * a donc rien à choisir. Le comptable reste sur son écran.
 */
async function modaleImport(cle, titre) {
  const conteneur = document.createElement('div');
  conteneur.innerHTML = `
    <div class="message info">
      <strong>Vos données, vos en-têtes</strong>
      Téléchargez le modèle, remplissez-le, redéposez-le ici. Le fichier est
      contrôlé ligne par ligne <em>avant</em> tout enregistrement.
    </div>
    <div class="rangee" style="margin-bottom:12px">
      <button class="petit-bouton" id="modele-import">Télécharger le modèle</button>
    </div>
    <div class="rangee" style="align-items:flex-end; gap:12px">
      <label class="champ" style="flex:1"><span>Fichier rempli (.xlsx ou .csv)</span>
        <input type="file" id="import-fichier" accept=".xlsx,.csv"></label>
      <button class="primaire" id="bouton-controler">Contrôler le fichier</button>
    </div>
    <div id="import-resultat"></div>`;

  conteneur.querySelector('#modele-import').onclick = () => telechargeModele(cle);
  brancheDepot(conteneur, () => cle);
  modale({
    titre: titre || 'Importer des données',
    contenu: conteneur,
    large: true,
    boutons: [{ libelle: 'Fermer' }],
  });
}

/** Lit le fichier choisi et le renvoie encodé, sans en-tête « data: ». */
function litFichierBase64(fichier) {
  return new Promise((resolve, rejette) => {
    const lecteur = new FileReader();
    lecteur.onload = () => resolve(String(lecteur.result).split(',', 2)[1]);
    lecteur.onerror = () => rejette(new Error('Fichier illisible.'));
    lecteur.readAsDataURL(fichier);
  });
}

/** Champs supplémentaires propres à certains modèles. */
function optionsImport(racine) {
  const date = $('#import-date-reprise', racine);
  return date && date.value ? { date_reprise: date.value } : {};
}

async function controleImport(racine, modele) {
  if (!_fichierImport) { notifie('Choisissez d\'abord un fichier.', 'alerte'); return; }
  const zone = $('#import-resultat', racine);
  zone.innerHTML = '<div class="vide">Contrôle en cours…</div>';
  try {
    const contenu = await litFichierBase64(_fichierImport);
    const options = optionsImport(racine);
    const d = await envoie('/api/import/analyse', { modele, contenu, ...options });
    afficheControleImport(zone, d, modele, contenu, options);
  } catch (err) {
    zone.innerHTML = `<div class="message danger"><strong>Fichier refusé</strong>
      ${ech(err.message)}</div>`;
  }
}

function afficheControleImport(zone, d, modele, contenu, options = {}) {
  const anomalies = d.anomalies || [];
  const ignorees = (d.colonnes_ignorees || []).length
    ? `<p class="petit">Colonnes du fichier non utilisées :
       ${d.colonnes_ignorees.map(ech).join(', ')}.</p>` : '';
  const lignesIgnorees = (d.lignes_ignorees || []).length
    ? `<p class="petit">Ligne(s) de totaux ignorée(s) :
       ${d.lignes_ignorees.join(', ')}. Une ligne sans compte dont le débit et
       le crédit sont tous deux remplis est comprise comme un total de
       tableau.</p>` : '';

  const resume = anomalies.length
    ? `<div class="message alerte">
         <strong>${d.nb_valides} ligne(s) prête(s), ${anomalies.length} anomalie(s)</strong>
         Rien n'est encore enregistré. Corrigez le fichier et recommencez, ou
         importez uniquement les lignes saines.</div>`
    : `<div class="message succes">
         <strong>${d.nb_valides} ligne(s) prête(s) à être importée(s)</strong>
         Aucune anomalie détectée.</div>`;

  const detail = anomalies.length ? `
    <table class="tableau"><thead><tr>
      <th style="width:90px">Ligne</th><th>Anomalie</th>
    </tr></thead><tbody>
      ${anomalies.slice(0, 100).map((a) => `<tr>
        <td>${a.ligne}</td><td>${ech(a.message)}</td></tr>`).join('')}
    </tbody></table>
    ${anomalies.length > 100 ? `<p class="petit">… et ${anomalies.length - 100} autre(s).</p>` : ''}` : '';

  // Le bouton énonce lui-même ce qu'il va faire : pas de fenêtre de
  // confirmation par-dessus, qui remplacerait celle de l'import.
  const libelleImport = anomalies.length
    ? `Importer les ${d.nb_valides} ligne(s) saines et ignorer `
      + `${anomalies.length} anomalie(s)`
    : `Importer ${d.nb_valides} ligne(s)`;

  zone.innerHTML = resume + ignorees + lignesIgnorees + detail + `
    <div class="rangee" style="margin-top:12px">
      ${d.nb_valides ? `<button class="primaire" id="bouton-importer">
        ${libelleImport}</button>` : ''}
    </div>`;

  if (!d.nb_valides) return;
  $('#bouton-importer', zone).onclick = async () => {
    const bouton = $('#bouton-importer', zone);
    bouton.disabled = true;                 // un double clic doublerait l'import
    bouton.textContent = 'Import en cours…';
    try {
      const r = await envoie('/api/import/valider',
        { modele, contenu, ...options,
          ignorer_anomalies: anomalies.length ? 1 : 0 });
      notifie(`${r.crees} ligne(s) importée(s).`
            + (r.rejetes ? ` ${r.rejetes} ignorée(s).` : ''), 'succes', 7000);
      const brouillon = modele === 'ecritures'
        ? 'Les écritures sont en brouillon : relisez-les au journal avant de les valider.'
        : (modele.startsWith('factures_')
          ? 'Les factures sont en brouillon : elles ne génèrent leur écriture '
            + 'comptable qu\'une fois validées.' : '');
      zone.innerHTML = `<div class="message succes">
        <strong>Import terminé</strong>
        ${r.crees} ligne(s) enregistrée(s)${r.rejetes ? `, ${r.rejetes} ignorée(s)` : ''}.
        ${brouillon}</div>`;
      // Import lancé depuis une liste : rafraîchir ce qui est affiché derrière,
      // sans effacer le compte rendu qui, lui, est dans la fenêtre.
      if (!$('#contenu').contains(zone)) afficheRoute();
    } catch (err) {
      zone.innerHTML = `<div class="message danger"><strong>Import refusé</strong>
        ${ech(err.message)}</div>`;
    }
  };
}

async function ongletSauvegarde(zone) {
  const [infos, sauvegardes] = await Promise.all([
    api('/api/systeme/infos'), api('/api/sauvegardes'),
  ]);
  const mo = (o) => `${(o / 1024 / 1024).toFixed(2)} Mo`;
  zone.innerHTML = `
    ${carte('Vos données', `
      <div class="message info"><strong>Vos données ne quittent jamais ce poste.</strong>
        Elles sont stockées dans le dossier ci-dessous. Copiez-le régulièrement sur un
        disque externe ou une clé USB.</div>
      <div class="liste-definitions">
        <dt>Dossier de données</dt><dd><code>${ech(infos.dossier_donnees)}</code></dd>
        <dt>Base de données</dt><dd>${mo(infos.taille_base)}</dd>
        <dt>Pièces justificatives</dt><dd>${infos.nombre_pieces} fichier(s) — ${mo(infos.taille_pieces)}</dd>
        <dt>Écritures comptables</dt><dd>${infos.nombre_ecritures}</dd>
        <dt>Dossiers gérés</dt><dd>${infos.nombre_societes}</dd>
      </div>`,
      `<button class="primaire" onclick="lanceSauvegarde()">Sauvegarder maintenant</button>
       <button onclick="verifieIntegrite()">Vérifier l'intégrité</button>`)}

    ${carteCopieExterne(sauvegardes.copie_externe || {})}

    ${carte('Sauvegardes disponibles', tableau([
      { titre: 'Fichier', cle: 'nom' },
      { titre: 'Date', cle: 'date' },
      { titre: 'Taille', classe: 'num', rendu: (s) => mo(s.taille) },
      {
        titre: '', classe: 'num',
        rendu: (s) => `<button class="petit-bouton" onclick="telecharge('/api/sauvegardes/telecharger',{nom:'${ech(s.nom)}'})">Télécharger</button>
          <button class="petit-bouton danger" onclick="restaure('${ech(s.nom)}')">Restaurer</button>`,
      },
    ], sauvegardes.sauvegardes, { messageVide: 'Aucune sauvegarde. Créez-en une dès maintenant.' }), '', true)}

    ${carte('Journal des incidents', `
      <p class="petit">Lancée depuis un raccourci, l'application n'affiche aucune
      fenêtre de messages : les erreurs sont consignées dans un fichier. À
      transmettre en cas de problème inexpliqué.</p>
      <div id="zone-diagnostic"><div class="vide">Non chargé.</div></div>`,
      `<button onclick="afficheDiagnostic()">Afficher le journal</button>
       <button class="primaire" onclick="modaleSignalement()">Signaler un problème</button>`)}`;

  // Le chemin d'une clé USB contient souvent une apostrophe ou un antislash :
  // on branche le bouton plutôt que de glisser la valeur dans un onclick.
  $('#copie-lancer', zone).onclick = copieSauvegardeExterne;
  $('#copie-destination', zone).addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); copieSauvegardeExterne(); }
  });
}

async function afficheDiagnostic() {
  const zone = $('#zone-diagnostic');
  zone.innerHTML = '<div class="vide">Chargement…</div>';
  try {
    const d = await api('/api/diagnostic');
    const journal = d.journal.length
      ? `<pre class="journal">${ech(d.journal.join('\n'))}</pre>`
      : '<div class="message succes"><strong>Aucun incident enregistré.</strong>'
        + ' Rien à signaler depuis la dernière remise à zéro.</div>';
    zone.innerHTML = `
      <div class="liste-definitions">
        <dt>Version</dt><dd>${ech(d.application)} ${ech(d.version)}</dd>
        <dt>Système</dt><dd>${ech(d.systeme)} — Python ${ech(d.python)}</dd>
        <dt>Adresse</dt><dd><code>${ech(d.adresse)}</code></dd>
        <dt>Fichier</dt><dd><code>${ech(d.fichier_journal)}</code></dd>
      </div>${journal}`;
  } catch (err) {
    zone.innerHTML = `<div class="message danger">${ech(err.message)}</div>`;
  }
}

async function lanceSauvegarde() {
  try {
    const r = await api('/api/sauvegardes', { method: 'POST', corps: { motif: 'manuelle' } });
    notifie(r.message, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function verifieIntegrite() {
  try {
    const r = await api('/api/systeme/verifier', { method: 'POST', corps: {} });
    const lignes = [
      `Intégrité de la base : <strong>${r.integrite_base}</strong>`,
      `Lignes orphelines : ${r.lignes_orphelines}`,
      `Écritures déséquilibrées : ${r.ecritures_desequilibrees.length}`,
      `Comptes inconnus : ${r.comptes_inconnus.length ? r.comptes_inconnus.join(', ') : 'aucun'}`,
      `Pièces jointes manquantes : ${r.pieces_manquantes.length}`,
    ];
    modale({
      titre: 'Contrôle d\'intégrité',
      contenu: `<div class="message ${r.conforme ? 'succes' : 'alerte'}">
          <strong>${r.conforme ? 'Aucune anomalie détectée.' : 'Des points sont à vérifier.'}</strong></div>
        <ul>${lignes.map((l) => `<li>${l}</li>`).join('')}</ul>`,
      boutons: [{ libelle: 'Fermer' }],
    });
  } catch (err) { erreur(err); }
}

async function restaure(nom) {
  modale({
    titre: 'Restaurer une sauvegarde',
    contenu: `<div class="message danger"><strong>Attention</strong>
        Toutes les données actuelles seront remplacées par celles de
        <code>${ech(nom)}</code>. Une sauvegarde de sécurité sera créée avant l'opération.</div>
      <label class="champ"><span>Saisissez RESTAURER pour confirmer</span>
        <input id="confirmation-restauration" placeholder="RESTAURER"></label>`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Restaurer', classe: 'danger',
      action: async (r) => {
        const reponse = await api('/api/sauvegardes/restaurer', {
          method: 'POST',
          corps: { nom, confirmation: $('#confirmation-restauration', r).value },
        });
        notifie(reponse.message, 'succes', 9000);
        setTimeout(() => window.location.reload(), 1600);
      },
    }],
  });
}


/* ------------------------------------------------- Déclaré / hors déclaration */

App.pages.perimetres = {
  titre: 'Déclaré et hors déclaration',
  async afficher(zone) {
    const d = await charge('/api/perimetres/synthese');
    const dec = d.perimetres.declare;
    const hors = d.perimetres.hors_declaration;
    actionsPage('');

    const mois = [...new Set(d.par_mois.map((l) => l.periode))];
    const parMois = (periode, perimetre) =>
      (d.par_mois.find((l) => l.periode === periode && l.perimetre === perimetre) || {}).produits || 0;
    const maxi = Math.max(1, ...d.par_mois.map((l) => l.produits));

    zone.innerHTML = `
      <div class="message info">Cet écran compare ce qui entre dans les déclarations
        et ce qui n'y entre pas. Les deux sont comptabilisés : la vue « réelle » du
        tableau de bord additionne les deux, les états fiscaux ne reprennent que le
        périmètre déclaré.</div>

      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Produits déclarés', fm(dec.produits, true),
          `${dec.nb_ecritures} écriture(s)`, 'accent')}
        ${indicateur('Produits hors déclaration', fm(hors.produits, true),
          `${hors.nb_ecritures} écriture(s)`, hors.produits ? 'danger' : '')}
        ${indicateur('Part hors déclaration', ft(d.part_hors_declaration) + ' %',
          jauge(d.part_hors_declaration, 10000,
            d.part_hors_declaration > 3000 ? 'danger' : 'alerte'))}
        ${indicateur('Résultat réel', fm(dec.resultat + hors.resultat, true),
          `déclaré ${fm(dec.resultat)}`)}
      </div>

      <div class="grille c2">
        ${carte('Comparaison', `<div class="enveloppe-table"><table class="donnees">
          <thead><tr><th>Poste</th><th class="num">Déclaré</th>
            <th class="num">Hors déclaration</th><th class="num">Réel</th></tr></thead>
          <tbody>
            <tr><td>Produits</td><td class="num">${fm(dec.produits)}</td>
              <td class="num">${fm(hors.produits)}</td>
              <td class="num gras">${fm(dec.produits + hors.produits)}</td></tr>
            <tr><td>Charges</td><td class="num">${fm(dec.charges)}</td>
              <td class="num">${fm(hors.charges)}</td>
              <td class="num gras">${fm(dec.charges + hors.charges)}</td></tr>
            <tr class="total"><td>Résultat</td><td class="num">${fm(dec.resultat)}</td>
              <td class="num">${fm(hors.resultat)}</td>
              <td class="num">${fm(dec.resultat + hors.resultat)}</td></tr>
            <tr><td>Trésorerie mouvementée</td><td class="num">${fm(dec.tresorerie)}</td>
              <td class="num">${fm(hors.tresorerie)}</td>
              <td class="num gras">${fm(dec.tresorerie + hors.tresorerie)}</td></tr>
            <tr><td>Nombre d'écritures</td><td class="num">${dec.nb_ecritures}</td>
              <td class="num">${hors.nb_ecritures}</td>
              <td class="num gras">${dec.nb_ecritures + hors.nb_ecritures}</td></tr>
          </tbody></table></div>
          ${d.plus_ancienne ? `<div class="aide">Opération hors déclaration la plus
            ancienne sur la période : ${fdate(d.plus_ancienne)}.</div>` : ''}`, '', true)}

        ${carte('Produits mois par mois', mois.length ? `
          <div class="histogramme">
            ${mois.map((m) => `
              <div class="colonne" title="${fperiode(m)} — déclaré ${fm(parMois(m, 'declare'), true)}, hors déclaration ${fm(parMois(m, 'hors_declaration'), true)}">
                <div class="barre produits" style="height:${Math.max(1, (parMois(m, 'declare') / maxi) * 100)}%"></div>
                <div class="barre charges" style="height:${Math.max(1, (parMois(m, 'hors_declaration') / maxi) * 100)}%"></div>
                <div class="etiq">${m.slice(5)}</div>
              </div>`).join('')}
          </div>
          <div class="legende"><span class="p">Déclaré</span><span class="c">Hors déclaration</span></div>`
          : '<div class="vide">Aucun produit sur la période.</div>')}
      </div>`;
  },
};


/* ------------------------------------------------------- Notifications -- */

async function ongletNotifications(zone) {
  const d = await charge('/api/notifications');
  const apercu = await charge('/api/notifications/apercu');

  zone.innerHTML = `
    <div class="message info"><strong>Recevoir la situation sur son téléphone</strong>
      Le résumé part de ce poste, à l'heure choisie ou à la demande. Aucun service
      payant, aucune donnée hébergée ailleurs.</div>

    ${carte('Destinataires', tableau([
      { titre: 'Nom', rendu: (c) => `<strong>${ech(c.libelle)}</strong>` },
      { titre: 'Canal', rendu: (c) => c.type === 'telegram' ? 'Telegram' : 'Courriel' },
      {
        titre: 'État',
        rendu: (c) => c.destinataire
          ? '<span class="etiquette succes">Appairé</span>'
          : `<span class="etiquette alerte">Code : ${ech(c.code_appairage || '—')}</span>`,
      },
      { titre: 'Fréquence', rendu: (c) => c.frequence === 'a_la_demande' ? 'À la demande' : `${c.frequence} à ${c.heure}` },
      { titre: 'Périmètre', rendu: (c) => badgePerimetre(c.perimetre) },
      { titre: 'Dernier envoi', rendu: (c) => c.dernier_envoi || '—' },
      { titre: 'Actif', classe: 'centre', rendu: (c) => c.actif ? '✓' : '✗' },
      {
        titre: '', classe: 'num',
        rendu: (c) => `<button class="petit-bouton" onclick="envoieResume(${c.id})">Envoyer</button>
          <button class="petit-bouton danger" onclick="supprimeCanal(${c.id})">Retirer</button>`,
      },
    ], d.canaux, {
      icone: '📱',
      messageVide: 'Aucun destinataire. Ajoutez-en un pour envoyer la situation.',
    }), '<button class="primaire" onclick="ajouteCanal()">+ Destinataire</button>', true)}

    <div class="grille c2">
      ${carte('Telegram' + (d.telegram_configure ? ' ✓' : ''),
        etapesTelegram(d))}

      ${carte('Courriel' + (d.smtp_configure ? ' ✓' : ''), `
        <p class="petit">Facultatif — utile si le destinataire préfère l'e-mail.</p>
        <div class="ligne-champs">
          <label class="champ"><span>Serveur SMTP</span>
            <input id="smtp-hote" value="${ech(d.smtp.hote)}" placeholder="smtp.gmail.com"></label>
          <label class="champ"><span>Port</span>
            <input id="smtp-port" value="${ech(d.smtp.port)}" placeholder="587"></label>
          <label class="champ"><span>Identifiant</span>
            <input id="smtp-utilisateur" value="${ech(d.smtp.utilisateur)}"></label>
          <label class="champ"><span>Mot de passe</span>
            <input id="smtp-mot-de-passe" type="password" placeholder="inchangé"></label>
          <label class="champ" style="grid-column:1/-1"><span>Adresse d'expédition</span>
            <input id="smtp-expediteur" value="${ech(d.smtp.expediteur)}"></label>
        </div>
        <button class="primaire" onclick="enregistreReglagesNotif()">Enregistrer</button>`)}
    </div>

    ${carte('Aperçu du message envoyé', `<pre style="white-space:pre-wrap;font-family:inherit;
      background:var(--fond-doux);padding:13px;border-radius:6px;margin:0;font-size:12.5px">${ech(apercu.texte)}</pre>`)}`;
}

async function enregistreReglagesNotif() {
  const donnees = {};
  const jeton = $('#tg-token')?.value;
  if (jeton) donnees.telegram_token = jeton;
  for (const [id, cle] of [['smtp-hote', 'smtp_hote'], ['smtp-port', 'smtp_port'],
    ['smtp-utilisateur', 'smtp_utilisateur'], ['smtp-expediteur', 'smtp_expediteur']]) {
    const el = $('#' + id);
    if (el) donnees[cle] = el.value;
  }
  const mdp = $('#smtp-mot-de-passe')?.value;
  if (mdp) donnees.smtp_mot_de_passe = mdp;
  try {
    await envoie('/api/notifications/reglages', donnees, 'PUT');
    notifie('Réglages enregistrés.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function ajouteCanal() {
  const champs = [
    { nom: 'libelle', libelle: 'Nom du destinataire', requis: true, aide: 'Ex : Papa' },
    {
      nom: 'type', libelle: 'Canal', type: 'select', vide: false,
      options: [['telegram', 'Telegram (instantané, gratuit)'], ['email', 'Courriel']],
    },
    {
      nom: 'destinataire', libelle: 'Adresse (courriel uniquement)',
      aide: 'Pour Telegram, laissez vide : un code d\'appairage sera généré.',
    },
    {
      nom: 'frequence', libelle: 'Fréquence', type: 'select', vide: false,
      options: [['quotidien', 'Tous les jours'], ['hebdomadaire', 'Chaque dimanche'],
        ['a_la_demande', 'Uniquement à la demande']],
    },
    { nom: 'heure', libelle: 'Heure d\'envoi', type: 'time', defaut: '08:00' },
    {
      nom: 'perimetre', libelle: 'Chiffres transmis', type: 'select', vide: false,
      options: [['tous', 'Réels (déclaré + hors déclaration)'],
        ['declare', 'Déclaré uniquement']],
    },
    { nom: 'actif', libelle: 'Actif', type: 'case', defaut: true },
  ];
  modale({
    titre: 'Nouveau destinataire',
    contenu: formulaire(champs), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Ajouter', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/notifications', litFormulaire(r, champs));
        if (d.code_appairage) {
          notifie(`Destinataire créé. Code d'appairage : ${d.code_appairage}`, 'succes', 15000);
        } else {
          notifie('Destinataire créé.', 'succes');
        }
        afficheRoute();
      },
    }],
  });
}

async function envoieResume(canalId) {
  try {
    const d = await envoie('/api/notifications/envoyer', { canal_id: canalId });
    const echecs = d.resultats.filter((r) => !r.ok);
    if (echecs.length) {
      notifie(`Échec : ${echecs.map((e) => e.erreur).join(' · ')}`, 'danger', 9000);
    } else {
      notifie(`Résumé envoyé (${d.envoyes} destinataire(s)).`, 'succes');
    }
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function supprimeCanal(id) {
  if (!await confirme('Retirer ce destinataire ?',
    'Il ne recevra plus de résumé.', 'Retirer')) return;
  try {
    await envoie(`/api/notifications/${id}`, {}, 'DELETE');
    notifie('Destinataire retiré.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* ------------------------------------------------- Personnalisation ----- */

/* Un logiciel de comptabilité s'utilise huit heures par jour : ce qui plaît
   à l'un fatigue l'autre. Rien ici ne touche aux données, aux calculs ni
   aux exports — uniquement à ce que l'œil reçoit. Les réglages restent sur
   le poste, pas dans le dossier : deux personnes sur la même comptabilité
   gardent chacune son écran. */

const APERCU_APPARENCE = [
  ['401', 'Fournisseurs de stocks et services', '', '7 140 000,00', 'validee', 'declare'],
  ['4191', 'Avances sur ventes sur plan (VSP)', '', '29 109 243,71', 'validee', 'declare'],
  ['5121', 'Banque — compte d\'exploitation', '6 490 000,00', '2 411 830,50', 'brouillon', 'declare'],
  ['606', 'Achats non stockés', '30 000,00', '', 'validee', 'hors_declaration'],
];

function apercuApparence() {
  return tableau([
    { titre: 'Compte', cle: 0, largeur: '80px', rendu: (l) => ech(l[0]) },
    { titre: 'Intitulé', rendu: (l) => ech(l[1]) },
    { titre: 'Débit', classe: 'num', largeur: '124px', rendu: (l) => l[2] },
    { titre: 'Crédit', classe: 'num solde', largeur: '124px', rendu: (l) => l[3] },
    { titre: 'État', rendu: (l) => etiquette(l[4]) },
    { titre: 'Périmètre', rendu: (l) => badgePerimetre(l[5]) },
  ], APERCU_APPARENCE, { coupure: (l) => classeScf(l[0]) });
}

function ongletApparence(zone) {
  const bloc = (r) => {
    const actuelle = Apparence.get(r.cle);
    const choix = r.valeurs.map(([v, libelle]) => `
      <button class="choix-apparence ${v === actuelle ? 'actif' : ''}"
              data-reglage="${r.cle}" data-valeur="${v}">
        ${r.pastilles ? `<span class="pastille-accent accent-${v}"></span>` : ''}
        ${ech(libelle)}
      </button>`).join('');
    return `<div class="reglage-apparence">
      <div class="titre-reglage">${ech(r.libelle)}</div>
      <div class="aide">${ech(r.aide)}</div>
      <div class="groupe-boutons">${choix}</div>
    </div>`;
  };

  zone.innerHTML = `
    <div class="message info">Ces réglages ne changent que la présentation.
      Aucun montant, aucun calcul, aucun export n'en dépend. Ils restent sur
      ce poste et sur ce navigateur : la comptabilité, elle, ne bouge pas.</div>

    ${carte('Aperçu', `<div class="aide" style="margin-bottom:9px">Quatre lignes
      pour voir l'effet de chaque réglage tout de suite. Elles sont fictives.</div>
      <div id="apercu-apparence">${apercuApparence()}</div>`)}

    ${carte('Réglages',
      `<div class="grille-apparence">${APPARENCE_REGLAGES.map(bloc).join('')}</div>`,
      '<button id="reinit-apparence">Revenir aux réglages livrés</button>')}`;

  zone.querySelectorAll('.choix-apparence').forEach((bouton) => {
    bouton.onclick = () => {
      Apparence.change(bouton.dataset.reglage, bouton.dataset.valeur);
      ongletApparence(zone);
      notifie('Réglage appliqué.', 'succes');
    };
  });
  $('#reinit-apparence', zone).onclick = () => {
    Apparence.reinitialise();
    ongletApparence(zone);
    notifie('Réglages d\'apparence remis à leur valeur livrée.', 'succes');
  };
}

/* ------------------------------------------ Copie hors du poste --------- */

/* Les sauvegardes vivent dans le dossier de données, donc sur le disque qui
   porte déjà la comptabilité : une panne, un vol ou un rançongiciel emporte
   les comptes et toutes leurs copies ensemble. Cet écran rend la copie
   ailleurs faisable en un clic — et surtout visible quand elle date. */

function carteCopieExterne(etat) {
  const jours = etat.jours;
  const jamais = !etat.date;
  const enRetard = etat.a_rappeler;

  const bandeau = jamais
    ? `<div class="message alerte"><strong>Vos sauvegardes sont sur le même
        disque que votre comptabilité.</strong> Une panne de disque, un vol ou
        un rançongiciel emporterait les comptes et toutes leurs copies d'un
        seul coup. Copiez-les sur une clé USB ou un disque externe.</div>`
    : (enRetard
      ? `<div class="message alerte"><strong>Dernière copie il y a ${jours} jour(s).</strong>
          Tout ce qui a été saisi depuis n'existe qu'à un seul endroit.</div>`
      : `<div class="message succes"><strong>Copie faite il y a
          ${jours === 0 ? "moins d'un jour" : jours + ' jour(s)'}.</strong>
          Votre comptabilité existe à deux endroits.</div>`);

  const memoire = etat.destination || localStorage.getItem('copie_destination') || '';

  return carte('Copie hors du poste', `
    ${bandeau}
    <p class="aide">Branchez la clé USB, indiquez sa lettre (par exemple
      <code>E:\\</code>) ou le dossier d'un disque externe, puis copiez. La
      sauvegarde la plus récente est copiée telle quelle&nbsp;; si aucune
      n'existe encore, elle est créée pour l'occasion.</p>
    <div class="rangee" style="align-items:flex-end; gap:12px">
      <label class="champ" style="flex:1">
        <span>Où copier</span>
        <input id="copie-destination" value="${ech(memoire)}"
               placeholder="E:\\ ou D:\\sauvegardes-compta"></label>
      <button class="primaire" id="copie-lancer">Copier maintenant</button>
    </div>
    <div id="copie-resultat"></div>
    ${etat.date ? `<div class="petit" style="margin-top:8px">Dernière copie :
      ${ech(etat.date)} — <code>${ech(etat.destination || '')}</code></div>` : ''}`);
}

async function copieSauvegardeExterne() {
  const champ = $('#copie-destination');
  const zone = $('#copie-resultat');
  const bouton = $('#copie-lancer');
  const destination = (champ.value || '').trim();
  if (!destination) {
    notifie('Indiquez d\'abord où copier.', 'alerte');
    champ.focus();
    return;
  }
  bouton.disabled = true;
  zone.innerHTML = '<div class="vide">Copie en cours…</div>';
  try {
    const d = await envoie('/api/sauvegardes/copier', { destination });
    // On retient l'emplacement : la même clé USB revient chaque semaine.
    localStorage.setItem('copie_destination', destination);
    zone.innerHTML = `<div class="message succes"><strong>${ech(d.nom)}</strong>
      copiée dans <code>${ech(d.destination)}</code>. Vous pouvez retirer le
      support.</div>`;
    notifie('Copie faite.', 'succes');
    // Le bandeau du haut doit refléter la nouvelle date.
    await afficheRoute();
  } catch (err) {
    zone.innerHTML = `<div class="message danger"><strong>Copie impossible</strong>
      ${ech(err.message)}</div>`;
  } finally {
    bouton.disabled = false;
  }
}

/* --------------------------------------------- Telegram, pas à pas ------ */

/* Le code d'appairage n'est pas global : il en existe un PAR destinataire, et
   il n'apparaît donc qu'une fois le destinataire créé. L'écran disait
   « le code affiché ci-dessus » devant un tableau vide — on montre plutôt
   où l'on en est, dans l'ordre, et le code là où on le cherche. */

function etapesTelegram(d) {
  const enAttente = (d.canaux || []).filter(
    (c) => c.type === 'telegram' && !c.destinataire);
  const appaires = (d.canaux || []).filter(
    (c) => c.type === 'telegram' && c.destinataire);
  const fait = (v) => v ? '<span class="vert">✓</span>' : '<span class="discret">·</span>';

  const codes = enAttente.map((c) => `
    <div class="code-appairage">
      <div>
        <div class="petit">Code pour <strong>${ech(c.libelle)}</strong></div>
        <div class="jeton-appairage">${ech(c.code_appairage || '—')}</div>
      </div>
      <button class="petit-bouton" onclick="copieCode('${ech(c.code_appairage || '')}')">Copier</button>
    </div>`).join('');

  return `
    <ol class="etapes-telegram">
      <li>${fait(d.telegram_configure)} <strong>Créer le bot</strong> — une seule
        fois. Dans Telegram, cherchez <strong>@BotFather</strong>, envoyez
        <code>/newbot</code>, choisissez un nom, puis collez ici le jeton
        qu'il vous donne.
        <label class="champ" style="margin-top:6px"><span>Jeton du bot</span>
          <input id="tg-token" type="password"
            placeholder="${d.telegram_configure ? '•••••• (déjà enregistré)' : '123456789:AAE...'}"></label>
        <button class="primaire" onclick="enregistreReglagesNotif()">Enregistrer</button>
      </li>

      <li>${fait(enAttente.length || appaires.length)} <strong>Ajouter le
        destinataire</strong> — c'est lui qui fait apparaître le code.
        ${(enAttente.length || appaires.length) ? '' :
          `<div class="message alerte" style="margin-top:6px">Aucun destinataire
            Telegram pour l'instant : c'est pour cela qu'aucun code ne
            s'affiche. Créez-en un avec le bouton
            <strong>« + Destinataire »</strong> ci-dessus.</div>`}
      </li>

      <li>${fait(appaires.length)} <strong>Lui transmettre le code</strong> —
        il installe Telegram, ouvre votre bot, et envoie ce code. Une seule
        fois : il n'expire pas.
        ${codes || (appaires.length
          ? `<div class="message succes" style="margin-top:6px">
              ${appaires.length} destinataire(s) déjà appairé(s).</div>`
          : '')}
      </li>
    </ol>
    <p class="petit">Une fois appairé, il écrit « situation », « trésorerie »
      ou « loyers » à tout moment et reçoit la réponse dans la seconde.</p>`;
}

async function copieCode(code) {
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code);
    notifie('Code copié — collez-le dans WhatsApp.', 'succes');
  } catch (err) {
    notifie(`Copie impossible. Le code est : ${code}`, 'alerte', 12000);
  }
}
