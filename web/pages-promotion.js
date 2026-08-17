/* ==========================================================================
   Pages promotion immobilière : programmes, lots, contrats VSP, échéances,
   coût de revient, situations de travaux
   ========================================================================== */

App.pages.promotion = {
  titre: 'Promotion immobilière',
  async afficher(zone, route) {
    const vue = route.segments[1] || 'programmes';
    if (vue === 'programme') return ficheProgramme(zone, route.segments[2], route);
    const onglets = [['programmes', 'Programmes'], ['lots', 'Lots'],
      ['contrats', 'Contrats VSP'], ['echeances', 'Échéancier'],
      ['travaux', 'Situations de travaux']];
    zone.innerHTML = `<div class="onglets">${onglets.map(([v, l]) =>
      `<button class="${v === vue ? 'actif' : ''}" onclick="navigue('/promotion/${v}')">${l}</button>`).join('')}</div>
      <div id="vue-promo"><div class="vide">Chargement…</div></div>`;
    const vues = {
      programmes: vueProgrammes, lots: vueLots, contrats: vueContrats,
      echeances: vueEcheances, travaux: vueTravaux,
    };
    await (vues[vue] || vueProgrammes)($('#vue-promo'), route);
  },
};

['programmes', 'lots', 'contrats', 'echeances', 'travaux', 'programme'].forEach((v) => {
  App.pages[`promotion/${v}`] = App.pages.promotion;
});

/* --------------------------------------------------------- Programmes -- */

async function vueProgrammes(zone) {
  actionsPage('<button class="primaire" onclick="editeProgramme()">+ Programme</button>'
    + boutonImport('programmes', 'Importer des programmes')
    + boutonImport('lots', 'Importer des lots'));
  const d = await charge('/api/programmes');
  zone.innerHTML = d.programmes.length ? `<div class="grille c2">${d.programmes.map((p) => {
    const commercialise = pourcent(p.vendu, p.chiffre_affaires_prevu || 1);
    return `<div class="carte">
      <div class="entete-carte">
        <div><h2>${ech(p.intitule)}</h2>
          <div class="petit">${ech(p.code)} — ${ech(p.commune || '')} ${ech(p.wilaya || '')}</div></div>
        ${etiquette(p.statut)}
      </div>
      <div class="corps">
        <div class="grille c3" style="gap:9px;margin-bottom:12px">
          <div><div class="petit">Lots</div><strong>${p.nb_lots_saisis}</strong>
            <span class="petit">(${p.nb_vendus} vendus, ${p.nb_reserves} réservés)</span></div>
          <div><div class="petit">Budget</div><strong>${fm(p.budget_total)}</strong></div>
          <div><div class="petit">Engagé</div><strong>${fm(p.cout_engage)}</strong></div>
        </div>
        <div class="petit">Avancement des travaux — ${ft(p.avancement)} %</div>
        ${jauge(p.avancement, 10000)}
        <div class="petit" style="margin-top:8px">Commercialisation — ${commercialise} %</div>
        ${jauge(p.vendu, p.chiffre_affaires_prevu || 1, 'succes')}
        <div class="separateur"></div>
        <div class="liste-definitions">
          <dt>Encaissé</dt><dd class="num">${fm(p.encaisse, true)}</dd>
          <dt>Reste à encaisser</dt><dd class="num">${fm(p.vendu - p.encaisse, true)}</dd>
          <dt>Permis de construire</dt><dd>${ech(p.num_permis_construire || '—')}</dd>
        </div>
      </div>
      <div class="entete-carte" style="border-top:1px solid var(--bordure);border-bottom:0">
        <a class="bouton primaire petit-bouton" href="#/promotion/programme/${p.id}">Ouvrir</a>
        <button class="petit-bouton" onclick="editeProgramme(${p.id})">Modifier</button>
      </div></div>`;
  }).join('')}</div>`
    : `<div class="vide"><span class="grand">🏗️</span>
       Aucun programme immobilier. Créez votre premier programme pour suivre les lots,
       les contrats de vente sur plan et le coût de revient.</div>`;
}

const CHAMPS_PROGRAMME = [
  { groupe: 'Identification' },
  { nom: 'code', libelle: 'Code', requis: true, aide: 'Ex : RES-JASMIN' },
  { nom: 'intitule', libelle: 'Intitulé', requis: true },
  { nom: 'adresse', libelle: 'Adresse', large: true },
  { nom: 'commune', libelle: 'Commune' },
  { nom: 'wilaya', libelle: 'Wilaya' },
  {
    nom: 'statut', libelle: 'Statut', type: 'select', vide: false,
    options: [['etude', 'Étude'], ['lancement', 'Lancement'], ['en_cours', 'En cours'],
      ['acheve', 'Achevé'], ['livre', 'Livré'], ['cloture', 'Clôturé']],
  },
  { groupe: 'Assiette foncière et consistance' },
  { nom: 'surface_terrain', libelle: 'Surface du terrain (m²)' },
  { nom: 'surface_batie', libelle: 'Surface bâtie (m²)' },
  { nom: 'nb_logements', libelle: 'Nombre de logements', type: 'number' },
  { nom: 'nb_locaux', libelle: 'Nombre de locaux', type: 'number' },
  { groupe: 'Autorisations administratives' },
  { nom: 'num_permis_construire', libelle: 'N° du permis de construire' },
  { nom: 'date_permis', libelle: 'Date du permis', type: 'date' },
  { nom: 'num_acte_terrain', libelle: 'N° de l\'acte du terrain' },
  { nom: 'date_acte_terrain', libelle: 'Date de l\'acte', type: 'date' },
  { nom: 'num_certificat_conformite', libelle: 'N° du certificat de conformité' },
  { nom: 'date_conformite', libelle: 'Date de conformité', type: 'date' },
  { groupe: 'Calendrier' },
  { nom: 'date_debut_travaux', libelle: 'Début des travaux', type: 'date' },
  { nom: 'date_fin_prevue', libelle: 'Fin prévue', type: 'date' },
  { nom: 'date_livraison', libelle: 'Livraison', type: 'date' },
  { groupe: 'Budget prévisionnel' },
  { nom: 'budget_terrain', libelle: 'Terrain', type: 'montant' },
  { nom: 'budget_etudes', libelle: 'Études et honoraires', type: 'montant' },
  { nom: 'budget_travaux', libelle: 'Travaux', type: 'montant' },
  { nom: 'budget_vrd', libelle: 'VRD et raccordements', type: 'montant' },
  { nom: 'budget_frais_divers', libelle: 'Frais divers', type: 'montant' },
  { nom: 'budget_frais_financiers', libelle: 'Frais financiers', type: 'montant' },
  { nom: 'chiffre_affaires_prevu', libelle: 'Chiffre d\'affaires prévu', type: 'montant' },
  { groupe: 'Régime comptable et fiscal' },
  {
    nom: 'methode_produit', libelle: 'Constatation du produit', type: 'select', vide: false,
    options: [['achevement', 'À l\'achèvement (livraison du lot)'], ['avancement', 'À l\'avancement']],
    aide: 'À l\'achèvement : le chiffre d\'affaires n\'est constaté qu\'à la livraison.',
  },
  {
    nom: 'fait_generateur_tva', libelle: 'Fait générateur de la TVA', type: 'select', vide: false,
    options: [['livraison', 'À la livraison'], ['encaissement', 'À l\'encaissement']],
    aide: 'À l\'encaissement : la TVA est collectée sur chaque tranche VSP reçue.',
  },
  { nom: 'taux_tva', libelle: 'Taux de TVA', type: 'taux', defaut: 1900 },
  { nom: 'fgcmpi_police', libelle: 'N° de police FGCMPI' },
  { nom: 'fgcmpi_taux', libelle: 'Taux de prime FGCMPI', type: 'taux' },
  { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
];

async function editeProgramme(id) {
  const existant = id ? await api(`/api/programmes/${id}`) : {};
  if (existant.surface_terrain) existant.surface_terrain = existant.surface_terrain / 100;
  if (existant.surface_batie) existant.surface_batie = existant.surface_batie / 100;
  modale({
    titre: id ? 'Modifier le programme' : 'Nouveau programme immobilier',
    contenu: formulaire(CHAMPS_PROGRAMME, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, CHAMPS_PROGRAMME);
        if (id) await envoie(`/api/programmes/${id}`, donnees, 'PUT');
        else await envoie('/api/programmes', donnees);
        notifie('Programme enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* --------------------------------------------- Fiche détaillée programme */

async function ficheProgramme(zone, id, route) {
  const p = await api(`/api/programmes/${id}`);
  const s = p.synthese;
  $('#titre-page').textContent = p.intitule;
  sousTitre(`${p.code} — ${p.commune || ''} ${p.wilaya || ''}`);
  actionsPage(`
    <button onclick="majAvancement(${id}, ${p.avancement})">Mettre à jour l'avancement</button>
    <button onclick="editeProgramme(${id})">Modifier</button>
    <button onclick="telecharge('/api/export/programme',{programme:${id}})">Exporter</button>
    <a class="bouton" href="#/promotion/programmes">Retour</a>`);

  const onglet = route.parametres.vue || 'synthese';
  zone.innerHTML = `
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Avancement des travaux', ft(p.avancement) + ' %',
        jauge(p.avancement, 10000), 'accent')}
      ${indicateur('Budget total', fm(s.budget_total, true),
        `engagé ${fm(s.cout_engage)} (${ft(s.taux_consommation_budget)} %)`)}
      ${indicateur('Commercialisation', ft(s.taux_commercialisation) + ' %',
        `${s.nb_vendus}/${s.nb_lots} lots — ${fm(s.ca_contractualise)}`)}
      ${indicateur('Marge prévisionnelle', fm(s.marge_prevue, true),
        `${ft(s.marge_taux)} % du chiffre d'affaires`,
        s.marge_prevue >= 0 ? 'succes' : 'danger')}
    </div>

    <div class="onglets">${[['synthese', 'Synthèse'], ['lots', 'Lots'],
      ['contrats', 'Contrats'], ['cout', 'Budget & coût de revient'], ['compta', 'Opérations comptables']]
      .map(([v, l]) => `<button class="${v === onglet ? 'actif' : ''}"
        onclick="navigue('/promotion/programme/${id}?vue=${v}')">${l}</button>`).join('')}</div>
    <div id="vue-prog"><div class="vide">Chargement…</div></div>`;

  const cible = $('#vue-prog');
  if (onglet === 'lots') cible.innerHTML = tableLots(p.lots, id);
  else if (onglet === 'contrats') cible.innerHTML = tableContrats(p.contrats);
  else if (onglet === 'cout') await vueCoutRevient(cible, id);
  else if (onglet === 'compta') cible.innerHTML = vueOperationsProgramme(p);
  else cible.innerHTML = vueSyntheseProgramme(p, s);
}

function vueSyntheseProgramme(p, s) {
  return `<div class="grille c2">
    ${carte('Encaissements', `<div class="liste-definitions">
      <dt>Chiffre d'affaires prévu</dt><dd class="num">${fm(s.ca_prevu, true)}</dd>
      <dt>Contractualisé</dt><dd class="num">${fm(s.ca_contractualise, true)}</dd>
      <dt>Encaissé</dt><dd class="num vert">${fm(s.encaisse, true)}</dd>
      <dt>Reste à encaisser</dt><dd class="num">${fm(s.reste_a_encaisser, true)}</dd>
    </div>
    <div class="separateur"></div>
    <div class="petit">Recouvrement des ventes</div>
    ${jauge(s.encaisse, s.ca_contractualise || 1, 'succes')}`)}

    ${carte('Consistance et administration', `<div class="liste-definitions">
      <dt>Surface du terrain</dt><dd>${(p.surface_terrain / 100).toFixed(2)} m²</dd>
      <dt>Surface bâtie</dt><dd>${(p.surface_batie / 100).toFixed(2)} m²</dd>
      <dt>Lots</dt><dd>${s.nb_lots} — ${s.nb_disponibles} disponibles, ${s.nb_reserves} réservés, ${s.nb_vendus} vendus</dd>
      <dt>Surface habitable totale</dt><dd>${(s.surface_totale / 100).toFixed(2)} m²</dd>
      <dt>Prix de revient au m²</dt><dd>${fm(s.prix_revient_m2, true)}</dd>
      <dt>Permis de construire</dt><dd>${ech(p.num_permis_construire || '—')} ${p.date_permis ? 'du ' + fdate(p.date_permis) : ''}</dd>
      <dt>Certificat de conformité</dt><dd>${ech(p.num_certificat_conformite || '—')}</dd>
      <dt>Début des travaux</dt><dd>${fdate(p.date_debut_travaux) || '—'}</dd>
      <dt>Livraison prévue</dt><dd>${fdate(p.date_fin_prevue) || '—'}</dd>
      <dt>Fait générateur TVA</dt><dd>${p.fait_generateur_tva === 'encaissement' ? 'À l\'encaissement' : 'À la livraison'}</dd>
    </div>`)}
  </div>`;
}

function vueOperationsProgramme(p) {
  return `
    <div class="message info">Ces opérations traduisent comptablement la vie du programme
      selon le SCF : les charges de chantier sont stockées en travaux en cours, puis
      transférées en produits finis à l'achèvement, avant d'être déstockées lot par lot
      lors des livraisons.</div>
    <div class="grille c2">
      ${carte('Travaux en cours (33 / 723)', `
        <p class="petit">Porte au stock les charges du programme qui ne sont pas encore
          vendues. À faire à chaque arrêté comptable, et obligatoirement à la clôture.</p>
        <label class="champ"><span>Date d'arrêté</span>
          <input type="date" id="date-encours" value="${aujourdhui()}"></label>
        <button class="primaire" onclick="stockEncours(${p.id})">Constater les travaux en cours</button>`)}
      ${carte('Achèvement (33 → 355)', `
        <p class="petit">Transfère les travaux en cours en produits finis lorsque le
          programme est achevé et réceptionné.</p>
        <label class="champ"><span>Date d'achèvement</span>
          <input type="date" id="date-achevement" value="${aujourdhui()}"></label>
        <button class="primaire" onclick="acheveProgramme(${p.id})">Déclarer l'achèvement</button>`)}
      ${carte('Répartition du coût de revient', `
        <p class="petit">Ventile le coût du programme sur chaque lot pour obtenir la
          marge réelle par logement.</p>
        <div class="ligne-champs">
          <label class="champ"><span>Base</span><select id="base-repartition">
            <option value="reel">Coût réellement engagé</option>
            <option value="budget">Budget prévisionnel</option></select></label>
          <label class="champ"><span>Clé</span><select id="cle-repartition">
            <option value="surface">Surface habitable</option>
            <option value="prix">Prix de vente</option></select></label>
        </div>
        <button class="primaire" onclick="repartitCout(${p.id})">Répartir</button>`)}
      ${carte('Situation de travaux', `
        <p class="petit">Enregistre la facture d'avancement d'une entreprise, avec
          retenue de garantie.</p>
        <button class="primaire" onclick="editeSituation(${p.id})">+ Situation de travaux</button>`)}
    </div>`;
}

async function majAvancement(id, actuel) {
  const champs = [
    { nom: 'avancement', libelle: 'Avancement des travaux (%)', type: 'taux', requis: true, defaut: actuel },
  ];
  modale({
    titre: 'Avancement du chantier',
    contenu: `<div class="message info">Les échéances VSP adossées à un seuil d'avancement
        deviennent automatiquement exigibles.</div>${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const d = await api(`/api/programmes/${id}/avancement`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie(d.message, 'succes', 6000);
        afficheRoute();
      },
    }],
  });
}

async function stockEncours(id) {
  try {
    const d = await api(`/api/programmes/${id}/stock-encours`, {
      method: 'POST', corps: { date: $('#date-encours').value },
    });
    notifie(d.message || `Travaux en cours constatés : ${fm(d.montant, true)}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function acheveProgramme(id) {
  if (!await confirme('Déclarer l\'achèvement ?',
    'Les travaux en cours seront transférés en produits finis et l\'avancement porté à 100 %.',
    'Déclarer', false)) return;
  try {
    const d = await api(`/api/programmes/${id}/achever`, {
      method: 'POST', corps: { date: $('#date-achevement').value },
    });
    notifie(`Achèvement enregistré — ${fm(d.montant, true)} transférés en stock.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function repartitCout(id) {
  try {
    const d = await api(`/api/programmes/${id}/repartir-cout`, {
      method: 'POST',
      corps: { base: $('#base-repartition').value, cle: $('#cle-repartition').value },
    });
    notifie(`${fm(d.total_reparti, true)} répartis sur ${d.lots} lot(s).`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* ----------------------------------------------------------------- Lots */

function tableLots(lots, programmeId) {
  return carte(`${lots.length} lot(s)`, tableau([
    { titre: 'N°', cle: 'numero', largeur: '70px' },
    { titre: 'Type', cle: 'type_lot' },
    { titre: 'Typologie', cle: 'typologie' },
    { titre: 'Bât.', cle: 'batiment' },
    { titre: 'Étage', cle: 'etage' },
    { titre: 'Surface', classe: 'num', rendu: (l) => (l.surface_habitable / 100).toFixed(2) + ' m²' },
    { titre: 'Prix de vente', classe: 'num', rendu: (l) => fm(l.prix_vente) },
    { titre: 'Coût de revient', classe: 'num', rendu: (l) => l.cout_revient ? fm(l.cout_revient) : '' },
    {
      titre: 'Marge', classe: 'num',
      rendu: (l) => l.cout_revient
        ? `<span class="${l.prix_vente - l.cout_revient >= 0 ? 'vert' : 'rouge'}">${fm(l.prix_vente - l.cout_revient)}</span>` : '',
    },
    { titre: 'Acquéreur', cle: 'acquereur' },
    { titre: 'Statut', rendu: (l) => etiquette(l.statut) },
    {
      titre: '', classe: 'num',
      rendu: (l) => l.contrat_id
        ? `<a class="bouton petit-bouton" href="#/promotion/contrat/${l.contrat_id}">Contrat</a>`
        : `<button class="petit-bouton primaire" onclick="editeContrat(null, ${l.id})">Vendre</button>`,
    },
  ], lots, { icone: '🏢', messageVide: 'Aucun lot. Créez-les un par un ou en série.' }),
    `<button class="petit-bouton" onclick="editeLot(null, ${programmeId})">+ Lot</button>
     <button class="petit-bouton primaire" onclick="genereLots(${programmeId})">Générer en série</button>`, true);
}

async function vueLots(zone, route) {
  const d = await charge('/api/lots', { programme: route.parametres.programme, statut: route.parametres.statut });
  actionsPage('');
  zone.innerHTML = carte(`${d.lots.length} lot(s)`, tableau([
    { titre: 'Programme', cle: 'programme_code' },
    { titre: 'N°', cle: 'numero' },
    { titre: 'Type', cle: 'type_lot' },
    { titre: 'Typologie', cle: 'typologie' },
    { titre: 'Surface', classe: 'num', rendu: (l) => (l.surface_habitable / 100).toFixed(2) },
    { titre: 'Prix', classe: 'num', rendu: (l) => fm(l.prix_vente) },
    { titre: 'Acquéreur', cle: 'acquereur' },
    { titre: 'Encaissé', classe: 'num', rendu: (l) => l.montant_encaisse ? fm(l.montant_encaisse) : '' },
    { titre: 'Statut', rendu: (l) => etiquette(l.statut) },
  ], d.lots, { icone: '🏢', messageVide: 'Aucun lot enregistré.' }), '', true);
}

const CHAMPS_LOT = [
  { nom: 'numero', libelle: 'N° du lot', requis: true },
  {
    nom: 'type_lot', libelle: 'Type', type: 'select', vide: false,
    options: [['logement', 'Logement'], ['local_commercial', 'Local commercial'],
      ['bureau', 'Bureau'], ['parking', 'Parking'], ['cave', 'Cave'], ['terrain', 'Terrain']],
  },
  { nom: 'typologie', libelle: 'Typologie', aide: 'F2, F3, F4…' },
  { nom: 'batiment', libelle: 'Bâtiment' },
  { nom: 'etage', libelle: 'Étage' },
  { nom: 'surface_habitable', libelle: 'Surface habitable (m²)' },
  { nom: 'surface_utile', libelle: 'Surface utile (m²)' },
  { nom: 'quote_part_terrain', libelle: 'Quote-part (millièmes)', type: 'number' },
  { nom: 'prix_m2', libelle: 'Prix au m²', type: 'montant' },
  { nom: 'prix_vente', libelle: 'Prix de vente', type: 'montant', aide: 'Vide = surface × prix au m²' },
];

async function editeLot(id, programmeId) {
  const existant = id ? {} : {};
  modale({
    titre: 'Nouveau lot',
    contenu: formulaire(CHAMPS_LOT, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/lots', { programme_id: programmeId, ...litFormulaire(r, CHAMPS_LOT) });
        notifie('Lot créé.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function genereLots(programmeId) {
  const champs = [
    { nom: 'prefixe', libelle: 'Préfixe des numéros', defaut: 'A', requis: true },
    { nom: 'debut', libelle: 'Du numéro', type: 'number', defaut: 1, requis: true },
    { nom: 'fin', libelle: 'Au numéro', type: 'number', defaut: 12, requis: true },
    { nom: 'batiment', libelle: 'Bâtiment', defaut: 'A' },
    {
      nom: 'type_lot', libelle: 'Type', type: 'select', vide: false,
      options: [['logement', 'Logement'], ['local_commercial', 'Local commercial'],
        ['parking', 'Parking'], ['cave', 'Cave']],
    },
    { nom: 'typologie', libelle: 'Typologie', defaut: 'F3' },
    { nom: 'surface_habitable', libelle: 'Surface (m²)', requis: true },
    { nom: 'prix_m2', libelle: 'Prix au m²', type: 'montant', requis: true },
    { nom: 'lots_par_etage', libelle: 'Lots par étage', type: 'number', defaut: 4 },
  ];
  modale({
    titre: 'Générer des lots en série',
    contenu: `<div class="message info">Crée d'un coup tous les lots d'un bâtiment.
        Vous pourrez ajuster chaque lot ensuite.</div>${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Générer', classe: 'primaire',
      action: async (r) => {
        const v = litFormulaire(r, champs);
        const parEtage = parseInt(v.lots_par_etage, 10) || 4;
        const lots = [];
        for (let n = parseInt(v.debut, 10); n <= parseInt(v.fin, 10); n += 1) {
          lots.push({
            numero: `${v.prefixe}${String(n).padStart(2, '0')}`,
            type_lot: v.type_lot, typologie: v.typologie, batiment: v.batiment,
            etage: String(Math.floor((n - parseInt(v.debut, 10)) / parEtage) + 1),
            surface_habitable: v.surface_habitable, prix_m2: v.prix_m2,
          });
        }
        const d = await envoie('/api/lots/generer', { programme_id: programmeId, lots });
        notifie(`${d.crees} lot(s) créé(s).`, 'succes');
        afficheRoute();
      },
    }],
  });
}

/* -------------------------------------------------------- Contrats VSP -- */

function tableContrats(contrats) {
  return carte('Contrats de vente sur plan', tableau([
    { titre: 'N°', cle: 'numero' },
    { titre: 'Lot', cle: 'lot_numero' },
    { titre: 'Acquéreur', cle: 'acquereur' },
    { titre: 'Date', rendu: (c) => fdate(c.date_contrat) },
    { titre: 'Prix TTC', classe: 'num', rendu: (c) => fm(c.prix_total) },
    { titre: 'Encaissé', classe: 'num', rendu: (c) => fm(c.montant_encaisse) },
    { titre: 'Reste', classe: 'num', rendu: (c) => fm(c.prix_total - c.montant_encaisse) },
    { titre: 'FGCMPI', classe: 'centre', rendu: (c) => c.fgcmpi_atteste ? '✓' : '<span class="orange" title="Garantie FGCMPI non enregistrée">!</span>' },
    { titre: 'Statut', rendu: (c) => etiquette(c.statut) },
    {
      titre: '', classe: 'num',
      rendu: (c) => `<a class="bouton petit-bouton" href="#/promotion/contrat/${c.id}">Ouvrir</a>`,
    },
  ], contrats, { icone: '📝', messageVide: 'Aucun contrat de vente sur plan.' }), '', true);
}

async function vueContrats(zone, route) {
  actionsPage('<button class="primaire" onclick="editeContrat()">+ Contrat VSP</button>'
    + boutonImport('contrats_vsp', 'Importer des contrats VSP')
    + boutonImport('echeances_vsp', 'Importer des échéanciers'));
  const d = await charge('/api/contrats-vsp', { programme: route.parametres.programme, statut: route.parametres.statut });
  zone.innerHTML = tableContrats(d.contrats.map((c) => ({ ...c, lot_numero: `${c.programme_code} / ${c.lot_numero}` })));
}

App.pages['promotion/contrat'] = {
  titre: 'Contrat de vente sur plan',
  async afficher(zone, route) {
    const c = await api(`/api/contrats-vsp/${route.segments[2]}`);
    $('#titre-page').textContent = `Contrat ${c.numero}`;
    sousTitre(`${c.programme} — lot ${c.lot_numero} — ${c.acquereur}`);
    actionsPage(`
      <button onclick="window.open('/api/contrats-vsp/${c.id}/impression','_blank')">Échéancier imprimable</button>
      ${c.statut === 'en_cours' || c.statut === 'solde'
        ? `<button class="primaire" onclick="livreLot(${c.id})">Livrer le lot</button>
           <button class="danger" onclick="resilieContrat(${c.id})">Résilier</button>` : ''}
      <a class="bouton" href="#/promotion/contrats">Retour</a>`);

    zone.innerHTML = `
      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Prix de vente TTC', fm(c.prix_total, true),
          `HT ${fm(c.prix_ht)} + TVA ${fm(c.tva)}`, 'accent')}
        ${indicateur('Encaissé', fm(c.montant_encaisse, true), ft(c.taux_encaissement) + ' %', 'succes')}
        ${indicateur('Reste à encaisser', fm(c.reste_a_encaisser, true), '',
          c.reste_a_encaisser > 0 ? 'danger' : '')}
        ${indicateur('Statut', etiquette(c.statut),
          c.date_livraison ? `livré le ${fdate(c.date_livraison)}` : '')}
      </div>

      ${c.fgcmpi_atteste ? '' : `<div class="message alerte">
        <strong>Garantie FGCMPI non enregistrée</strong>
        La vente sur plan requiert l'attestation de garantie du Fonds de garantie et de
        caution mutuelle de la promotion immobilière. Renseignez-la dans le contrat.</div>`}

      <div class="grille c2">
        ${carte('Contrat', `<div class="liste-definitions">
          <dt>Type</dt><dd>${ech(c.type_contrat)}</dd>
          <dt>Date du contrat</dt><dd>${fdate(c.date_contrat)}</dd>
          <dt>Réservation</dt><dd>${fdate(c.date_reservation) || '—'}</dd>
          <dt>Acte notarié</dt><dd>${ech(c.num_acte_notarie || '—')}</dd>
          <dt>Publication</dt><dd>${fdate(c.date_publication) || '—'}</dd>
          <dt>Financement</dt><dd>${ech(c.mode_financement || '—')} ${c.banque ? '(' + ech(c.banque) + ')' : ''}</dd>
          <dt>Montant du crédit</dt><dd class="num">${fm(c.montant_credit, true)}</dd>
          <dt>Aide de l'État</dt><dd class="num">${fm(c.aide_etat, true)}</dd>
          <dt>FGCMPI</dt><dd>${c.fgcmpi_atteste ? ech(c.fgcmpi_numero || 'attestée') : 'non attestée'}</dd>
        </div>`, `<button class="petit-bouton" onclick="editeContrat(${c.id})">Modifier</button>`)}

        ${carte('Lot vendu', `<div class="liste-definitions">
          <dt>Programme</dt><dd>${ech(c.programme)} (${ech(c.programme_code)})</dd>
          <dt>Lot</dt><dd>n° ${ech(c.lot_numero)} — ${ech(c.type_lot)} ${ech(c.typologie || '')}</dd>
          <dt>Bâtiment / étage</dt><dd>${ech(c.batiment || '—')} / ${ech(c.etage || '—')}</dd>
          <dt>Surface habitable</dt><dd>${(c.surface_habitable / 100).toFixed(2)} m²</dd>
          <dt>Avancement du chantier</dt><dd>${ft(c.avancement)} %</dd>
          <dt>Fait générateur TVA</dt><dd>${c.fait_generateur_tva === 'encaissement' ? 'À l\'encaissement' : 'À la livraison'}</dd>
        </div>`)}
      </div>

      ${carte('Échéancier de paiement', tableau([
        { titre: '#', rendu: (e) => e.ordre + 1, largeur: '40px' },
        { titre: 'Échéance', rendu: (e) => `<strong>${ech(e.libelle)}</strong>` },
        {
          titre: 'Déclencheur',
          rendu: (e) => e.declencheur === 'avancement'
            ? `Avancement ≥ ${ft(e.seuil_avancement)} %`
            : (e.declencheur === 'livraison' ? 'Remise des clés' : fdate(e.date_prevue)),
        },
        { titre: '%', classe: 'num', rendu: (e) => ft(e.pourcentage) + ' %' },
        { titre: 'Montant', classe: 'num', rendu: (e) => fm(e.montant) },
        { titre: 'Réglé', classe: 'num', rendu: (e) => e.montant_regle ? fm(e.montant_regle) : '' },
        { titre: 'Reste', classe: 'num', rendu: (e) => fm(e.montant - e.montant_regle) },
        { titre: 'Statut', rendu: (e) => etiquette(e.statut) },
        {
          titre: '', classe: 'num',
          rendu: (e) => e.montant_regle < e.montant
            ? `<button class="petit-bouton primaire" onclick="encaisseEcheance(${e.id})">Encaisser</button>
               <button class="petit-bouton" onclick="appelDeFonds(${e.id})">Appel de fonds</button>` : '',
        },
      ], c.echeances, { messageVide: 'Aucune échéance.' }), '', true)}`;
  },
};

async function editeContrat(id, lotId) {
  const [lots, clients, notaires, modeles] = await Promise.all([
    charge('/api/lots', { statut: 'disponible' }), optionsTiers('client'),
    optionsTiers('notaire'), charge('/api/modeles-echeancier'),
  ]);
  const existant = id ? await api(`/api/contrats-vsp/${id}`) : { lot_id: lotId };
  const champs = [
    { groupe: 'Objet de la vente' },
    ...(id ? [] : [{
      nom: 'lot_id', libelle: 'Lot vendu', type: 'select', requis: true,
      options: lots.lots.map((l) => [l.id,
        `${l.programme_code} / ${l.numero} — ${l.typologie || l.type_lot} — ${fm(l.prix_vente, true)}`]),
    }]),
    { nom: 'acquereur_id', libelle: 'Acquéreur', type: 'select', requis: !id, options: clients },
    {
      nom: 'type_contrat', libelle: 'Type de contrat', type: 'select', vide: false,
      options: [['vsp', 'Vente sur plan (VSP)'], ['reservation', 'Contrat de réservation'],
        ['vente_definitive', 'Vente définitive']],
    },
    { nom: 'date_reservation', libelle: 'Date de réservation', type: 'date' },
    { nom: 'date_contrat', libelle: 'Date du contrat', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'prix_total', libelle: 'Prix de vente TTC', type: 'montant', aide: 'Vide = prix du lot' },
    { nom: 'taux_tva', libelle: 'TVA', type: 'taux', defaut: 1900 },
    { groupe: 'Formalités' },
    { nom: 'notaire_id', libelle: 'Notaire', type: 'select', options: notaires },
    { nom: 'num_acte_notarie', libelle: 'N° de l\'acte notarié' },
    { nom: 'date_publication', libelle: 'Publication à la conservation foncière', type: 'date' },
    { nom: 'fgcmpi_atteste', libelle: 'Garantie FGCMPI attestée', type: 'case' },
    { nom: 'fgcmpi_numero', libelle: 'N° de l\'attestation FGCMPI' },
    { nom: 'fgcmpi_prime', libelle: 'Prime FGCMPI', type: 'montant' },
    { groupe: 'Financement' },
    {
      nom: 'mode_financement', libelle: 'Mode de financement', type: 'select',
      options: [['fonds_propres', 'Fonds propres'], ['credit_bancaire', 'Crédit bancaire'],
        ['cnl_aide', 'Aide CNL / FNPOS'], ['mixte', 'Mixte']],
    },
    { nom: 'banque', libelle: 'Banque' },
    { nom: 'montant_credit', libelle: 'Montant du crédit', type: 'montant' },
    { nom: 'aide_etat', libelle: 'Aide de l\'État', type: 'montant' },
    ...(id ? [] : [
      { groupe: 'Échéancier' },
      {
        nom: 'modele_echeancier', libelle: 'Modèle d\'échéancier', type: 'select', vide: false,
        options: modeles.modeles.map((m) => [m.code, m.libelle]),
        aide: 'Les tranches sont réparties automatiquement sur le prix de vente.',
      },
      { nom: 'intervalle_mois', libelle: 'Intervalle entre échéances à date fixe (mois)', type: 'number', defaut: 3 },
    ]),
    { nom: 'notes', libelle: 'Notes', type: 'zone', large: true },
  ];

  modale({
    titre: id ? 'Modifier le contrat' : 'Nouveau contrat de vente sur plan',
    contenu: formulaire(champs, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, champs);
        if (id) {
          await envoie(`/api/contrats-vsp/${id}`, donnees, 'PUT');
          notifie('Contrat mis à jour.', 'succes');
          afficheRoute();
        } else {
          const d = await envoie('/api/contrats-vsp', donnees);
          notifie(`Contrat ${d.numero} créé avec son échéancier.`, 'succes');
          navigue(`/promotion/contrat/${d.id}`);
        }
      },
    }],
  });
}

async function encaisseEcheance(id) {
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Encaissé sur', type: 'select', requis: true, vide: false, options: await optionsTresorerie() },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'montant', libelle: 'Montant (vide = solde de l\'échéance)', type: 'montant' },
    {
      nom: 'mode', libelle: 'Mode', type: 'select', vide: false,
      options: [['virement', 'Virement'], ['cheque', 'Chèque'], ['espece', 'Espèces']],
    },
    { nom: 'reference', libelle: 'Référence' },
  ];
  modale({
    titre: 'Encaisser une tranche VSP',
    contenu: `<div class="message info">L'encaissement est porté en avance client (compte 4191).
        Le chiffre d'affaires ne sera constaté qu'à la livraison du lot.</div>${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Encaisser', classe: 'primaire',
      action: async (r) => {
        await api(`/api/echeances-vsp/${id}/encaisser`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie('Encaissement enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function appelDeFonds(id) {
  try {
    await api(`/api/echeances-vsp/${id}/appel`, { method: 'POST', corps: { date: aujourdhui() } });
    notifie('Échéance marquée comme appelée et exigible.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function livreLot(id) {
  const champs = [
    { nom: 'date', libelle: 'Date de livraison', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'date_pv_reception', libelle: 'Date du PV de réception', type: 'date' },
    { nom: 'destocker', libelle: 'Sortir le lot du stock (724 / 355)', type: 'case', defaut: true },
  ];
  modale({
    titre: 'Livrer le lot et constater la vente',
    contenu: `<div class="message alerte"><strong>Constatation du chiffre d'affaires</strong>
        Les avances reçues sont soldées, le chiffre d'affaires est enregistré en compte 701x
        et le solde éventuel devient une créance client.</div>${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Livrer', classe: 'primaire',
      action: async (r) => {
        const d = await api(`/api/contrats-vsp/${id}/livrer`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie(`Livraison comptabilisée — chiffre d'affaires ${fm(d.chiffre_affaires, true)}`
          + (d.solde_du > 0 ? `, solde client ${fm(d.solde_du, true)}.` : '.'), 'succes', 7000);
        afficheRoute();
      },
    }],
  });
}

async function resilieContrat(id) {
  const champs = [
    { nom: 'date', libelle: 'Date de résiliation', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'indemnite', libelle: 'Indemnité conservée', type: 'montant' },
    { nom: 'tresorerie_id', libelle: 'Restitution depuis', type: 'select', options: await optionsTresorerie() },
  ];
  modale({
    titre: 'Résilier le contrat',
    contenu: `<div class="message danger">Les avances reçues sont restituées à l'acquéreur,
        déduction faite de l'indemnité éventuellement conservée. Le lot redevient disponible.</div>
      ${formulaire(champs).outerHTML}`,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Résilier', classe: 'danger',
      action: async (r) => {
        const d = await api(`/api/contrats-vsp/${id}/resilier`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie(`Contrat résilié — ${fm(d.restitue, true)} restitués.`, 'succes');
        navigue('/promotion/contrats');
      },
    }],
  });
}

/* ------------------------------------------------------------ Échéances */

async function vueEcheances(zone, route) {
  const statut = route.parametres.statut || '';
  actionsPage('');
  const d = await charge('/api/echeances-vsp', { statut, programme: route.parametres.programme });
  const t = d.totaux;
  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ"><span>Filtre</span><select onchange="navigue('/promotion/echeances?statut='+this.value)">
        <option value="">Toutes</option>
        <option value="exigible" ${statut === 'exigible' ? 'selected' : ''}>Exigibles</option>
        <option value="retard" ${statut === 'retard' ? 'selected' : ''}>En retard</option>
        <option value="a_venir" ${statut === 'a_venir' ? 'selected' : ''}>À venir</option>
        <option value="reglee" ${statut === 'reglee' ? 'selected' : ''}>Réglées</option>
      </select></label>
    </div>
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Total des échéances', fm(t.montant, true))}
      ${indicateur('Déjà réglé', fm(t.regle, true), '', 'succes')}
      ${indicateur('Reste à encaisser', fm(t.reste, true))}
      ${indicateur('Dont en retard', fm(t.en_retard, true), '', t.en_retard ? 'danger' : '')}
    </div>
    ${carte('', tableau([
      { titre: 'Programme', cle: 'programme_code' },
      { titre: 'Lot', cle: 'lot_numero' },
      { titre: 'Contrat', cle: 'contrat_numero' },
      { titre: 'Acquéreur', cle: 'acquereur' },
      { titre: 'Téléphone', cle: 'acquereur_tel' },
      { titre: 'Échéance', rendu: (e) => ech(e.libelle) },
      { titre: 'Date prévue', rendu: (e) => e.date_prevue ? `<span class="${e.en_retard ? 'rouge gras' : ''}">${fdate(e.date_prevue)}</span>` : '—' },
      { titre: 'Montant', classe: 'num', rendu: (e) => fm(e.montant) },
      { titre: 'Reste', classe: 'num', rendu: (e) => fm(e.reste) },
      { titre: 'Statut', rendu: (e) => etiquette(e.en_retard && e.statut !== 'reglee' ? 'retard' : e.statut) },
      {
        titre: '', classe: 'num',
        rendu: (e) => e.reste > 0 ? `<button class="petit-bouton primaire" onclick="encaisseEcheance(${e.id})">Encaisser</button>` : '',
      },
    ], d.echeances, { icone: '📅', messageVide: 'Aucune échéance sur ce filtre.' }), '', true)}`;
}

/* --------------------------------------------- Situations de travaux --- */

async function vueTravaux(zone, route) {
  actionsPage('<button class="primaire" onclick="editeSituation()">+ Situation de travaux</button>');
  const d = await charge('/api/situations-travaux', { programme: route.parametres.programme });
  zone.innerHTML = carte('Situations de travaux', tableau([
    { titre: 'N°', cle: 'numero' },
    { titre: 'Date', rendu: (s) => fdate(s.date) },
    { titre: 'Programme', cle: 'programme' },
    { titre: 'Entreprise', cle: 'entreprise' },
    { titre: 'Lot de travaux', cle: 'lot_travaux' },
    { titre: 'Marché', classe: 'num', rendu: (s) => fm(s.montant_marche) },
    { titre: 'Avanc.', classe: 'num', rendu: (s) => ft(s.avancement) + ' %' },
    { titre: 'Montant HT', classe: 'num', rendu: (s) => fm(s.montant_ht) },
    { titre: 'Retenue', classe: 'num', rendu: (s) => s.retenue_garantie ? fm(s.retenue_garantie) : '' },
    { titre: 'Net à payer', classe: 'num', rendu: (s) => `<strong>${fm(s.net_a_payer)}</strong>` },
    { titre: 'Statut', rendu: (s) => etiquette(s.statut) },
  ], d.situations, { icone: '🧱', messageVide: 'Aucune situation de travaux enregistrée.' }), '', true);
}

async function editeSituation(programmeId) {
  const [programmes, entreprises, comptes] = await Promise.all([
    charge('/api/programmes'), optionsTiers('fournisseur'), optionsComptes('60'),
  ]);
  const champs = [
    {
      nom: 'programme_id', libelle: 'Programme', type: 'select', requis: true, defaut: programmeId,
      options: programmes.programmes.map((p) => [p.id, `${p.code} — ${p.intitule}`]),
    },
    { nom: 'entreprise_id', libelle: 'Entreprise', type: 'select', requis: true, options: entreprises },
    { nom: 'numero', libelle: 'N° de situation' },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'lot_travaux', libelle: 'Lot de travaux', aide: 'Gros œuvre, étanchéité, menuiserie…' },
    { nom: 'montant_marche', libelle: 'Montant du marché', type: 'montant' },
    { nom: 'avancement', libelle: 'Avancement cumulé', type: 'taux' },
    { nom: 'montant_ht', libelle: 'Montant HT de la situation', type: 'montant', requis: true },
    { nom: 'taux_tva', libelle: 'TVA', type: 'taux', defaut: 1900 },
    { nom: 'taux_retenue', libelle: 'Retenue de garantie', type: 'taux', aide: 'Souvent 5 % ou 10 %' },
    {
      nom: 'compte', libelle: 'Compte de charge', type: 'select', vide: false, options: comptes,
      defaut: '6051',
    },
    {
      nom: 'poste_budget', libelle: 'Poste budgétaire', type: 'select', vide: false,
      options: [['gros_oeuvre', 'Gros œuvre'], ['second_oeuvre', 'Second œuvre'],
        ['vrd', 'VRD'], ['etudes', 'Études'], ['terrain', 'Terrain'],
        ['frais_generaux', 'Frais généraux']],
    },
  ];
  modale({
    titre: 'Nouvelle situation de travaux',
    contenu: formulaire(champs), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer et comptabiliser', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/situations-travaux', { ...litFormulaire(r, champs), comptabiliser: true });
        notifie('Situation enregistrée et comptabilisée.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* --------------------------------------------------- Coût de revient --- */

async function vueCoutRevient(zone, programmeId) {
  const d = await api(`/api/programmes/${programmeId}/cout-revient`);
  zone.innerHTML = `
    ${carte('Budget et réalisé par poste', tableau([
      { titre: 'Poste', rendu: (p) => `<strong>${ech(p.libelle)}</strong>` },
      { titre: 'Comptes', rendu: (p) => `<span class="tres-petit">${ech(p.comptes || '')}</span>` },
      { titre: 'Budget', classe: 'num', rendu: (p) => fm(p.montant_prevu) },
      { titre: 'Réalisé', classe: 'num', rendu: (p) => fm(p.realise) },
      {
        titre: 'Écart', classe: 'num',
        rendu: (p) => `<span class="${p.ecart < 0 ? 'rouge' : 'vert'}">${fm(p.ecart)}</span>`,
      },
      {
        titre: 'Consommation', largeur: '150px',
        rendu: (p) => `${ft(p.taux)} % ${jauge(p.realise, p.montant_prevu || 1,
          p.realise > p.montant_prevu ? 'danger' : '')}`,
      },
    ], d.postes, {
      pied: [{ contenu: '<strong>TOTAL</strong>' }, {},
        { contenu: `<strong>${fm(d.total_prevu)}</strong>`, classe: 'num' },
        { contenu: `<strong>${fm(d.total_realise)}</strong>`, classe: 'num' },
        { contenu: `<strong>${fm(d.total_prevu - d.total_realise)}</strong>`, classe: 'num' }, {}],
    }), '<button class="petit-bouton" onclick="editeBudget(' + programmeId + ')">Modifier le budget</button>', true)}

    ${carte('Marge par lot', tableau([
      { titre: 'Lot', cle: 'numero' },
      { titre: 'Type', cle: 'type_lot' },
      { titre: 'Surface', classe: 'num', rendu: (l) => (l.surface_habitable / 100).toFixed(2) },
      { titre: 'Prix de vente', classe: 'num', rendu: (l) => fm(l.prix_effectif) },
      { titre: 'Coût de revient', classe: 'num', rendu: (l) => fm(l.cout_revient) },
      {
        titre: 'Marge', classe: 'num',
        rendu: (l) => `<strong class="${l.marge >= 0 ? 'vert' : 'rouge'}">${fm(l.marge)}</strong>`,
      },
      { titre: 'Taux', classe: 'num', rendu: (l) => ft(l.taux_marge) + ' %' },
      { titre: 'Statut', rendu: (l) => etiquette(l.statut) },
    ], d.lots, { messageVide: 'Aucun lot.' }), '', true)}`;
}

async function editeBudget(programmeId) {
  const d = await api(`/api/programmes/${programmeId}/cout-revient`);
  const postes = d.postes.filter((p) => p.id);
  const conteneur = document.createElement('div');
  conteneur.innerHTML = `<table class="saisie"><thead><tr>
      <th>Poste</th><th style="width:26%">Comptes rattachés</th><th style="width:22%">Budget</th>
    </tr></thead><tbody>${postes.map((p) => `<tr data-id="${p.id}">
      <td><input class="b-libelle" value="${ech(p.libelle)}"></td>
      <td><input class="b-comptes" value="${ech(p.comptes || '')}"></td>
      <td><input class="b-montant num" value="${pourChamp(p.montant_prevu)}"></td>
    </tr>`).join('')}</tbody></table>
    <div class="aide">Séparez plusieurs comptes par un point-virgule (ex : 6051;611).</div>`;

  modale({
    titre: 'Budget du programme', contenu: conteneur, large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const lignes = $$('tr[data-id]', r).map((tr) => ({
          id: +tr.dataset.id,
          libelle: $('.b-libelle', tr).value,
          comptes: $('.b-comptes', tr).value,
          montant_prevu: $('.b-montant', tr).value,
        }));
        await envoie(`/api/programmes/${programmeId}/budget`, { postes: lignes }, 'PUT');
        notifie('Budget mis à jour.', 'succes');
        afficheRoute();
      },
    }],
  });
}
