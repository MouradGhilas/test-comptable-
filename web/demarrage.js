/* ==========================================================================
   Démarrage : installation, connexion, menu, sélection du dossier
   ========================================================================== */

const MENU = [
  {
    groupe: null, entrees: [
      { route: '/', libelle: 'Tableau de bord', ico: '📊' },
    ],
  },
  {
    groupe: 'Comptabilité', entrees: [
      { route: '/comptabilite/ecritures', libelle: 'Écritures', ico: '📒' },
      { route: '/factures', libelle: 'Factures', ico: '🧾' },
      { route: '/tresorerie', libelle: 'Trésorerie', ico: '🏦' },
      { route: '/tiers', libelle: 'Tiers', ico: '👥' },
      { route: '/comptabilite/grand-livre', libelle: 'Grand livre', ico: '📖' },
      { route: '/comptabilite/balance', libelle: 'Balance', ico: '⚖️' },
      { route: '/comptabilite/lettrage', libelle: 'Lettrage', ico: '🔗' },
      { route: '/comptabilite/etats', libelle: 'États financiers', ico: '📈' },
      { route: '/perimetres', libelle: 'Déclaré / hors décl.', ico: '⚖️' },
    ],
  },
  {
    groupe: 'Agence immobilière', activite: ['agence', 'mixte'], entrees: [
      { route: '/agence/biens', libelle: 'Portefeuille', ico: '🏠' },
      { route: '/agence/transactions', libelle: 'Ventes', ico: '🤝' },
      { route: '/agence/baux', libelle: 'Baux', ico: '🔑' },
      { route: '/agence/quittances', libelle: 'Loyers', ico: '📬' },
      { route: '/agence/proprietaires', libelle: 'Propriétaires', ico: '🏘️' },
    ],
  },
  {
    groupe: 'Promotion immobilière', activite: ['promotion', 'mixte'], entrees: [
      { route: '/promotion/programmes', libelle: 'Programmes', ico: '🏗️' },
      { route: '/promotion/contrats', libelle: 'Contrats VSP', ico: '📝' },
      { route: '/promotion/echeances', libelle: 'Échéancier', ico: '📅' },
      { route: '/promotion/travaux', libelle: 'Situations de travaux', ico: '🧱' },
    ],
  },
  {
    groupe: 'Déclarations & social', entrees: [
      { route: '/fiscalite/g50', libelle: 'Déclaration G50', ico: '🧮' },
      { route: '/fiscalite/obligations', libelle: 'Calendrier fiscal', ico: '⏰' },
      { route: '/paie/bulletins', libelle: 'Paie', ico: '💼' },
      { route: '/immobilisations', libelle: 'Immobilisations', ico: '🖥️' },
    ],
  },
  {
    groupe: 'Clôture', entrees: [
      { route: '/comptabilite/cloture', libelle: 'Contrôles & clôture', ico: '🔒' },
      { route: '/parametres/dossier', libelle: 'Paramètres', ico: '⚙️' },
    ],
  },
];

function construitMenu() {
  const activite = App.etat.societe?.activite || 'mixte';
  $('#menu').innerHTML = MENU
    .filter((g) => !g.activite || g.activite.includes(activite))
    .map((g) => `<div class="groupe-menu" data-groupe="${ech(g.groupe || '')}">
      ${g.groupe ? `<div class="titre-groupe">${ech(g.groupe)}</div>` : ''}
      ${g.entrees.map((e) => `<a href="#${e.route}">
        <span class="ico">${e.ico}</span>${ech(e.libelle)}</a>`).join('')}
    </div>`).join('');
}

/* --------------------------------------------------- Authentification -- */

function afficheAuth(installe = true) {
  $('#chargement').hidden = true;
  $('#application').hidden = true;
  $('#ecran-auth').hidden = false;

  if (!installe) {
    $('#zone-auth').innerHTML = `
      <div class="message info"><strong>Première utilisation</strong>
        Créez votre compte administrateur et le dossier comptable de votre entreprise.
        Tout reste sur ce poste.</div>
      <form id="form-installation">
        <fieldset><legend>Votre compte</legend><div class="ligne-champs">
          <label class="champ"><span>Identifiant *</span><input name="identifiant" required autocomplete="username"></label>
          <label class="champ"><span>Nom complet</span><input name="nom_complet" placeholder="Prénom Nom"></label>
          <label class="champ" style="grid-column:1/-1"><span>Mot de passe * (6 caractères minimum)</span>
            <input type="password" name="mot_de_passe" required minlength="6" autocomplete="new-password"></label>
        </div></fieldset>
        <fieldset><legend>Votre entreprise</legend><div class="ligne-champs">
          <label class="champ" style="grid-column:1/-1"><span>Raison sociale *</span>
            <input name="raison_sociale" required placeholder="SARL ..."></label>
          <label class="champ"><span>Forme juridique</span>
            <select name="forme_juridique">
              <option>SARL</option><option>EURL</option><option>SPA</option>
              <option>SNC</option><option>Personne physique</option></select></label>
          <label class="champ"><span>Activité *</span>
            <select name="activite">
              <option value="mixte">Agence + promotion immobilière</option>
              <option value="agence">Agence immobilière</option>
              <option value="promotion">Promotion immobilière</option>
            </select></label>
          <label class="champ"><span>NIF</span><input name="nif"></label>
          <label class="champ"><span>Registre de commerce</span><input name="rc"></label>
          <label class="champ"><span>Commune</span><input name="commune"></label>
          <label class="champ"><span>Wilaya</span><input name="wilaya" placeholder="16 Alger"></label>
          <label class="champ"><span>Premier exercice</span>
            <input name="annee_exercice" type="number" value="${new Date().getFullYear()}"></label>
        </div></fieldset>
        <button class="primaire" style="width:100%;justify-content:center" type="submit">
          Créer le dossier et démarrer</button>
      </form>`;

    $('#form-installation').onsubmit = async (ev) => {
      ev.preventDefault();
      const bouton = $('button', ev.target);
      bouton.disabled = true;
      try {
        const donnees = Object.fromEntries(new FormData(ev.target));
        await api('/api/installation', { method: 'POST', corps: donnees });
        notifie('Dossier créé. Bienvenue !', 'succes');
        await demarre();
      } catch (err) { erreur(err); bouton.disabled = false; }
    };
    return;
  }

  $('#zone-auth').innerHTML = `
    <form id="form-connexion">
      <label class="champ"><span>Identifiant</span>
        <input name="identifiant" required autocomplete="username" autofocus></label>
      <label class="champ"><span>Mot de passe</span>
        <input type="password" name="mot_de_passe" required autocomplete="current-password"></label>
      <button class="primaire" style="width:100%;justify-content:center" type="submit">Se connecter</button>
    </form>`;

  $('#form-connexion').onsubmit = async (ev) => {
    ev.preventDefault();
    const bouton = $('button', ev.target);
    bouton.disabled = true;
    try {
      await api('/api/connexion', {
        method: 'POST',
        corps: Object.fromEntries(new FormData(ev.target)),
      });
      await demarre();
    } catch (err) { erreur(err); bouton.disabled = false; }
  };
}

/* ---------------------------------------------- Dossiers et exercices --- */

async function chargeSocietes() {
  const etat = await api('/api/etat');
  App.etat.societes = etat.societes || [];
  if (!App.etat.societes.length) return;

  const memorise = +localStorage.getItem('societe_courante');
  App.etat.societe = App.etat.societes.find((s) => s.id === memorise) || App.etat.societes[0];

  const exercices = await api(`/api/exercices?societe=${App.etat.societe.id}`);
  App.etat.exercices = exercices.exercices;
  const memoriseEx = +localStorage.getItem(`exercice_${App.etat.societe.id}`);
  App.etat.exercice = App.etat.exercices.find((e) => e.id === memoriseEx)
    || App.etat.exercices.find((e) => !e.cloture)
    || App.etat.exercices[0];

  $('#choix-societe').innerHTML = App.etat.societes.map((s) =>
    `<option value="${s.id}" ${s.id === App.etat.societe.id ? 'selected' : ''}>${ech(s.raison_sociale)}</option>`).join('');
  $('#choix-exercice').innerHTML = App.etat.exercices.map((e) =>
    `<option value="${e.id}" ${e.id === App.etat.exercice?.id ? 'selected' : ''}>${ech(e.libelle)}${e.cloture ? ' (clôturé)' : ''}</option>`).join('');

  construitMenu();
}

async function demarre() {
  const etat = await api('/api/etat');
  App.etat.version = etat.version;

  if (!etat.installe) { afficheAuth(false); return; }
  if (!etat.connecte) { afficheAuth(true); return; }

  App.etat.utilisateur = etat.utilisateur;
  App.etat.perimetre = localStorage.getItem('perimetre') || 'tous';
  $('#choix-perimetre').value = App.etat.perimetre;
  $('#version-app').textContent = `v${etat.version}`;
  $('#info-utilisateur').innerHTML =
    `${ech(etat.utilisateur.nom_complet)}<br><span class="tres-petit">${ech(etat.utilisateur.role)}</span>`;

  await chargeSocietes();

  $('#chargement').hidden = true;
  $('#ecran-auth').hidden = true;
  // On vide le formulaire d'authentification : inutile de laisser des champs
  // de mot de passe dans le document une fois la session ouverte.
  $('#zone-auth').innerHTML = '';
  $('#application').hidden = false;
  brancheRechercheGlobale();

  if (!App.etat.societes.length) {
    $('#contenu').innerHTML = '<div class="message alerte">Aucun dossier comptable. '
      + 'Créez-en un depuis Paramètres.</div>';
    return;
  }
  await afficheRoute();
}

/* ----------------------------------------------------------- Événements */

$('#choix-societe').onchange = async (ev) => {
  localStorage.setItem('societe_courante', ev.target.value);
  videCache();
  await chargeSocietes();
  await afficheRoute();
};

$('#choix-perimetre').onchange = async (ev) => {
  App.etat.perimetre = ev.target.value;
  localStorage.setItem('perimetre', ev.target.value);
  await afficheRoute();
};

$('#choix-exercice').onchange = async (ev) => {
  App.etat.exercice = App.etat.exercices.find((e) => e.id === +ev.target.value);
  localStorage.setItem(`exercice_${App.etat.societe.id}`, ev.target.value);
  await afficheRoute();
};

$('#bouton-deconnexion').onclick = async () => {
  await api('/api/deconnexion', { method: 'POST', corps: {} });
  window.location.reload();
};

/* La bascule clair / sombre reste à portée de clic ; tout le reste des
   réglages d'apparence vit dans Paramètres → Personnalisation. */
$('#bouton-theme').onclick = () => Apparence.basculeTheme();

// Raccourcis clavier du comptable
document.addEventListener('keydown', (ev) => {
  if (!(ev.ctrlKey || ev.metaKey) || ev.shiftKey) return;
  const raccourcis = {
    e: () => saisieEcriture(),
    f: () => editeFacture(null, 'vente'),
    t: () => navigue('/tiers'),
  };
  if (raccourcis[ev.key]) { ev.preventDefault(); raccourcis[ev.key](); }
});

demarre().catch((err) => {
  $('#chargement').innerHTML = `<div class="logo-grand">⚠️</div>
    <div>Impossible de démarrer l'application</div>
    <div class="petit">${ech(err.message)}</div>`;
});
