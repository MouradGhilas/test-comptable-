/* ==========================================================================
   Pages : tableau de bord, tiers, trésorerie, paramètres, sauvegardes
   ========================================================================== */

/* ---------------------------------------------------- Tableau de bord --- */

App.pages.accueil = {
  titre: 'Tableau de bord',
  async afficher(zone) {
    const d = await charge('/api/tableau-de-bord');
    const i = d.indicateurs;
    sousTitre(`${d.societe.raison_sociale} — exercice ${d.exercice.libelle}`);

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
          <dt>Créances clients</dt><dd class="num">${fm(i.creances_clients, true)}</dd>
          <dt>Dettes fournisseurs</dt><dd class="num">${fm(i.dettes_fournisseurs, true)}</dd>
          <dt>Avances reçues sur ventes sur plan</dt><dd class="num">${fm(i.avances_clients_vsp, true)}</dd>
          <dt>Dû aux propriétaires (gestion locative)</dt><dd class="num">${fm(i.du_aux_proprietaires, true)}</dd>
          <dt>TVA collectée</dt><dd class="num">${fm(i.tva_collectee, true)}</dd>
          <dt>TVA déductible</dt><dd class="num">${fm(i.tva_deductible, true)}</dd>
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
    actionsPage(`<button class="primaire" onclick="editeTiers()">+ Nouveau tiers</button>
      <button onclick="telecharge('/api/export/balance-auxiliaire',{type:'${type || 'client'}'})">Balance auxiliaire</button>`);

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
      ['utilisateurs', 'Utilisateurs'], ['sauvegarde', 'Sauvegarde & données']];
    zone.innerHTML = `<div class="onglets">${onglets.map(([v, l]) =>
      `<button class="${v === onglet ? 'actif' : ''}" onclick="navigue('/parametres/${v}')">${l}</button>`).join('')}</div>
      <div id="zone-onglet"><div class="vide">Chargement…</div></div>`;
    const cible = $('#zone-onglet');
    const rendus = {
      dossier: ongletDossier, exercices: ongletExercices, plan: ongletPlan,
      fiscalite: ongletFiscalite, utilisateurs: ongletUtilisateurs, sauvegarde: ongletSauvegarde,
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

    ${carte('Sauvegardes disponibles', tableau([
      { titre: 'Fichier', cle: 'nom' },
      { titre: 'Date', cle: 'date' },
      { titre: 'Taille', classe: 'num', rendu: (s) => mo(s.taille) },
      {
        titre: '', classe: 'num',
        rendu: (s) => `<button class="petit-bouton" onclick="telecharge('/api/sauvegardes/telecharger',{nom:'${ech(s.nom)}'})">Télécharger</button>
          <button class="petit-bouton danger" onclick="restaure('${ech(s.nom)}')">Restaurer</button>`,
      },
    ], sauvegardes.sauvegardes, { messageVide: 'Aucune sauvegarde. Créez-en une dès maintenant.' }), '', true)}`;
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
