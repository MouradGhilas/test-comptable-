/* ==========================================================================
   Cabinet Immo — noyau de l'interface
   Client API, formatage algérien, composants et routeur. Aucune dépendance.
   ========================================================================== */

const App = {
  etat: {
    utilisateur: null,
    societes: [],
    societe: null,
    exercices: [],
    exercice: null,
    perimetre: 'tous',
    version: '',
  },
  pages: {},
  cache: {},
};

/* ---------------------------------------------------------------- API ---- */

async function api(chemin, options = {}) {
  const config = { headers: {}, credentials: 'same-origin', ...options };
  if (config.corps !== undefined) {
    config.method = config.method || 'POST';
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(config.corps);
    delete config.corps;
  }
  const reponse = await fetch(chemin, config);
  const type = reponse.headers.get('Content-Type') || '';
  if (!type.includes('application/json')) {
    if (!reponse.ok) throw new Error(`Erreur ${reponse.status}`);
    return reponse;
  }
  const donnees = await reponse.json();
  if (!reponse.ok) {
    if (reponse.status === 401 && App.etat.utilisateur) {
      App.etat.utilisateur = null;
      afficheAuth();
    }
    throw new Error(donnees.erreur || `Erreur ${reponse.status}`);
  }
  return donnees;
}

function requete(chemin, parametres = {}) {
  const p = new URLSearchParams();
  if (App.etat.societe) p.set('societe', App.etat.societe.id);
  if (App.etat.exercice) p.set('exercice', App.etat.exercice.id);
  if (App.etat.perimetre && App.etat.perimetre !== 'tous') {
    p.set('perimetre', App.etat.perimetre);
  }
  for (const [cle, valeur] of Object.entries(parametres)) {
    if (valeur !== undefined && valeur !== null && valeur !== '') p.set(cle, valeur);
  }
  return `${chemin}?${p.toString()}`;
}

function charge(chemin, parametres) { return api(requete(chemin, parametres)); }

function envoie(chemin, corps, methode = 'POST') {
  const donnees = { societe_id: App.etat.societe?.id, ...corps };
  return api(chemin, { method: methode, corps: donnees });
}

function telecharge(chemin, parametres) { window.open(requete(chemin, parametres), '_blank'); }

/* --------------------------------------------------------- Formatage ---- */

const DEVISE = 'DA';

/** Centimes -> « 1 234 567,89 ». */
function fm(centimes, avecDevise = false) {
  const valeur = Number(centimes || 0);
  const signe = valeur < 0 ? '-' : '';
  const absolu = Math.abs(valeur);
  const entier = Math.floor(absolu / 100);
  const dec = String(absolu % 100).padStart(2, '0');
  const groupes = String(entier).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${signe}${groupes},${dec}${avecDevise ? ' ' + DEVISE : ''}`;
}

/** Centimes -> montant coloré selon le signe. */
function fmc(centimes) {
  const v = Number(centimes || 0);
  const classe = v < 0 ? 'rouge' : (v > 0 ? '' : 'discret');
  return `<span class="${classe}">${fm(v)}</span>`;
}

/** Saisie utilisateur -> centimes. */
function cts(valeur) {
  if (valeur === null || valeur === undefined || valeur === '') return 0;
  if (typeof valeur === 'number') return Math.round(valeur * 100);
  const texte = String(valeur).replace(/[^\d,.\-]/g, '').replace(/\s/g, '');
  if (!texte) return 0;
  const dernierPoint = texte.lastIndexOf('.');
  const derniereVirgule = texte.lastIndexOf(',');
  const sep = Math.max(dernierPoint, derniereVirgule);
  let entier = texte, decimales = '';
  if (sep >= 0) { entier = texte.slice(0, sep); decimales = texte.slice(sep + 1); }
  const negatif = entier.startsWith('-');
  entier = entier.replace(/[.,-]/g, '') || '0';
  decimales = (decimales.replace(/[.,]/g, '') + '00').slice(0, 2);
  const total = parseInt(entier, 10) * 100 + parseInt(decimales, 10);
  return negatif ? -total : total;
}

/** Centimes -> valeur d'un champ input (sans séparateur de milliers). */
function pourChamp(centimes) {
  if (!centimes) return '';
  return (Number(centimes) / 100).toFixed(2).replace('.', ',');
}

/** Taux (centièmes de %) -> « 19 ». */
function ft(taux) {
  const v = Number(taux || 0) / 100;
  return Number.isInteger(v) ? String(v) : String(v).replace('.', ',');
}

function fdate(iso) {
  if (!iso) return '';
  const [a, m, j] = String(iso).slice(0, 10).split('-');
  return j ? `${j}/${m}/${a}` : iso;
}

const MOIS = ['', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
  'août', 'septembre', 'octobre', 'novembre', 'décembre'];

function fperiode(periode) {
  if (!periode) return '';
  const [a, m] = periode.split('-');
  return `${MOIS[parseInt(m, 10)]} ${a}`;
}

function aujourdhui() { return new Date().toISOString().slice(0, 10); }
function periodeCourante() { return aujourdhui().slice(0, 7); }
function moisPrecedent(periode) {
  let [a, m] = periode.split('-').map(Number);
  m -= 1; if (m === 0) { m = 12; a -= 1; }
  return `${a}-${String(m).padStart(2, '0')}`;
}

function ech(texte) {
  return String(texte ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function pourcent(valeur, total) {
  if (!total) return 0;
  return Math.round((valeur / total) * 1000) / 10;
}

/* --------------------------------------------------------- Composants --- */

function $(selecteur, racine = document) { return racine.querySelector(selecteur); }
function $$(selecteur, racine = document) { return [...racine.querySelectorAll(selecteur)]; }

function notifie(message, genre = 'info', duree = 4200) {
  const boite = document.createElement('div');
  boite.className = `notification ${genre}`;
  boite.innerHTML = ech(message);
  $('#notifications').appendChild(boite);
  setTimeout(() => { boite.style.opacity = '0'; setTimeout(() => boite.remove(), 250); }, duree);
}

function erreur(err) {
  console.error(err);
  notifie(err.message || String(err), 'danger', 7000);
}

/** Modale générique. `contenu` peut être du HTML ou un élément. */
function modale({ titre, contenu, boutons = [], large = false }) {
  const fond = $('#fenetre');
  const boite = $('#corps-modale');
  boite.className = 'modale' + (large ? ' large' : '');
  boite.innerHTML = `
    <div class="entete-modale"><h2>${ech(titre)}</h2>
      <button class="plat" data-fermer>✕</button></div>
    <div class="corps-modale"></div>
    <div class="pied-modale"></div>`;
  const corps = $('.corps-modale', boite);
  if (typeof contenu === 'string') corps.innerHTML = contenu; else corps.appendChild(contenu);

  const pied = $('.pied-modale', boite);
  boutons.forEach((b) => {
    const bouton = document.createElement('button');
    bouton.className = b.classe || '';
    bouton.textContent = b.libelle;
    bouton.onclick = async () => {
      try {
        bouton.disabled = true;
        const resultat = await b.action?.(corps);
        if (resultat !== false) fermeModale();
      } catch (err) { erreur(err); } finally { bouton.disabled = false; }
    };
    pied.appendChild(bouton);
  });
  if (!boutons.length) pied.remove();

  $('[data-fermer]', boite).onclick = fermeModale;
  fond.hidden = false;
  fond.onclick = (ev) => { if (ev.target === fond) fermeModale(); };
  setTimeout(() => $('input, select, textarea', corps)?.focus(), 60);
  return corps;
}

function fermeModale() { $('#fenetre').hidden = true; $('#corps-modale').innerHTML = ''; }

document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('#fenetre').hidden) fermeModale();
});

async function confirme(titre, message, libelleAction = 'Confirmer', dangereux = true) {
  return new Promise((resoudre) => {
    modale({
      titre,
      contenu: `<div>${message}</div>`,
      boutons: [
        { libelle: 'Annuler', action: () => { resoudre(false); } },
        {
          libelle: libelleAction, classe: dangereux ? 'danger' : 'primaire',
          action: () => { resoudre(true); },
        },
      ],
    });
  });
}

/** Construit un formulaire à partir d'une description de champs. */
function formulaire(champs, valeurs = {}) {
  const conteneur = document.createElement('div');
  let html = '';
  let groupeOuvert = false;

  for (const champ of champs) {
    if (champ.groupe) {
      if (groupeOuvert) html += '</div></fieldset>';
      html += `<fieldset><legend>${ech(champ.groupe)}</legend><div class="ligne-champs">`;
      groupeOuvert = true;
      continue;
    }
    const valeur = valeurs[champ.nom] ?? champ.defaut ?? '';
    const requis = champ.requis ? 'required' : '';
    const large = champ.large ? ' style="grid-column:1/-1"' : '';
    let controle;

    if (champ.type === 'select') {
      const options = (champ.options || []).map((o) => {
        const [v, libelle] = Array.isArray(o) ? o : [o, o];
        return `<option value="${ech(v)}" ${String(v) === String(valeur) ? 'selected' : ''}>${ech(libelle)}</option>`;
      }).join('');
      controle = `<select name="${champ.nom}" ${requis}>${champ.vide !== false ? '<option value=""></option>' : ''}${options}</select>`;
    } else if (champ.type === 'zone') {
      controle = `<textarea name="${champ.nom}" rows="${champ.lignes || 3}">${ech(valeur)}</textarea>`;
    } else if (champ.type === 'case') {
      controle = `<input type="checkbox" name="${champ.nom}" ${valeur ? 'checked' : ''}>`;
    } else if (champ.type === 'montant') {
      controle = `<input type="text" inputmode="decimal" class="num" name="${champ.nom}"
                   value="${ech(pourChamp(valeur))}" ${requis} data-montant>`;
    } else if (champ.type === 'taux') {
      controle = `<input type="text" inputmode="decimal" class="num" name="${champ.nom}"
                   value="${valeur ? ft(valeur) : ''}" data-taux placeholder="%">`;
    } else {
      controle = `<input type="${champ.type || 'text'}" name="${champ.nom}"
                   value="${ech(valeur)}" ${requis} ${champ.attributs || ''}>`;
    }
    html += `<label class="champ"${large}><span>${ech(champ.libelle)}${champ.requis ? ' *' : ''}</span>
             ${controle}${champ.aide ? `<div class="aide">${ech(champ.aide)}</div>` : ''}</label>`;
  }
  if (groupeOuvert) html += '</div></fieldset>';
  conteneur.innerHTML = html;
  return conteneur;
}

/** Lit un formulaire construit par `formulaire()`. */
function litFormulaire(racine, champs) {
  const donnees = {};
  for (const champ of champs) {
    if (champ.groupe) continue;
    const element = racine.querySelector(`[name="${champ.nom}"]`);
    if (!element) continue;
    if (champ.type === 'case') donnees[champ.nom] = element.checked;
    else if (champ.type === 'montant') donnees[champ.nom] = element.value;
    else if (champ.type === 'taux') donnees[champ.nom] = element.value;
    else donnees[champ.nom] = element.value;
  }
  return donnees;
}

/** Tableau générique. `colonnes` : {titre, cle|rendu, classe, largeur}. */
function tableau(colonnes, lignes, options = {}) {
  if (!lignes || !lignes.length) {
    return `<div class="vide"><span class="grand">${options.icone || '📭'}</span>
            ${ech(options.messageVide || 'Aucun élément à afficher.')}</div>`;
  }
  const entetes = colonnes.map((c) =>
    `<th class="${c.classe || ''}" ${c.largeur ? `style="width:${c.largeur}"` : ''}>${ech(c.titre)}</th>`
  ).join('');
  const corps = lignes.map((ligne, index) => {
    const cellules = colonnes.map((c) => {
      const contenu = c.rendu ? c.rendu(ligne, index) : ech(ligne[c.cle] ?? '');
      return `<td class="${c.classe || ''}">${contenu}</td>`;
    }).join('');
    const attributs = options.attributsLigne ? options.attributsLigne(ligne) : '';
    return `<tr class="${options.clic ? 'cliquable' : ''}" ${attributs}>${cellules}</tr>`;
  }).join('');
  const pied = options.pied ? `<tfoot><tr>${options.pied.map((c) =>
    `<td class="${c.classe || ''}">${c.contenu ?? ''}</td>`).join('')}</tr></tfoot>` : '';
  return `<div class="enveloppe-table"><table class="donnees">
          <thead><tr>${entetes}</tr></thead><tbody>${corps}</tbody>${pied}</table></div>`;
}

function carte(titre, contenu, actions = '', serre = false) {
  return `<div class="carte">
    ${titre ? `<div class="entete-carte"><h2>${ech(titre)}</h2><div class="rangee">${actions}</div></div>` : ''}
    <div class="corps ${serre ? 'serre' : ''}">${contenu}</div></div>`;
}

function indicateur(libelle, valeur, detail = '', genre = '') {
  return `<div class="indicateur ${genre}">
    <div class="libelle">${ech(libelle)}</div>
    <div class="valeur">${valeur}</div>
    ${detail ? `<div class="detail">${detail}</div>` : ''}</div>`;
}

const PERIMETRES = {
  declare: ['Déclaré', 'info'],
  hors_declaration: ['Hors déclaration', 'alerte'],
  tous: ['Vue réelle', ''],
};

/** Pastille de périmètre, affichée sans détour à côté des opérations. */
function badgePerimetre(perimetre) {
  const [libelle, genre] = PERIMETRES[perimetre] || PERIMETRES.declare;
  return `<span class="etiquette ${genre}">${ech(libelle)}</span>`;
}

/** Bandeau rappelant le périmètre couvert par un état ou une déclaration. */
function bandeauPerimetre(perimetre, complement = '') {
  const [libelle] = PERIMETRES[perimetre] || PERIMETRES.tous;
  const genre = perimetre === 'declare' ? 'info'
    : (perimetre === 'hors_declaration' ? 'alerte' : '');
  return `<div class="message ${genre}"><strong>Périmètre : ${ech(libelle)}</strong>
    ${complement ? ech(complement) : ''}</div>`;
}

const ETIQUETTES = {
  brouillon: ['Brouillon', ''], validee: ['Validée', 'info'], payee: ['Payée', 'succes'],
  partielle: ['Partielle', 'alerte'], annulee: ['Annulée', 'danger'],
  actif: ['Actif', 'succes'], disponible: ['Disponible', 'succes'],
  reserve: ['Réservé', 'alerte'], vendu: ['Vendu', 'info'], livre: ['Livré', 'succes'],
  loue: ['Loué', 'info'], resilie: ['Résilié', 'danger'], expire: ['Expiré', ''],
  en_cours: ['En cours', 'info'], solde: ['Soldé', 'succes'], acheve: ['Achevé', 'succes'],
  etude: ['Étude', ''], lancement: ['Lancement', 'info'], cloture: ['Clôturé', ''],
  a_encaisser: ['À encaisser', 'alerte'], encaissee: ['Encaissée', 'info'],
  reversee: ['Reversée', 'succes'], impayee: ['Impayée', 'danger'],
  a_venir: ['À venir', ''], exigible: ['Exigible', 'alerte'], reglee: ['Réglée', 'succes'],
  retard: ['En retard', 'danger'], calculee: ['Calculée', 'info'],
  deposee: ['Déposée', 'succes'], comptabilise: ['Comptabilisé', 'info'],
  paye: ['Payé', 'succes'], a_faire: ['À faire', 'alerte'], fait: ['Fait', 'succes'],
  en_service: ['En service', 'succes'], cede: ['Cédé', ''], signee: ['Signée', 'succes'],
  realise: ['Réalisé', 'succes'], comptabilisee: ['Comptabilisée', 'info'],
};

function etiquette(statut) {
  const [libelle, genre] = ETIQUETTES[statut] || [statut || '—', ''];
  return `<span class="etiquette ${genre}">${ech(libelle)}</span>`;
}

function jauge(valeur, total, genre = '') {
  const p = Math.min(100, Math.max(0, pourcent(valeur, total)));
  return `<div class="jauge ${genre}"><div style="width:${p}%"></div></div>`;
}

/** Champ de recherche de tiers avec liste déroulante native. */
async function optionsTiers(type) {
  const cle = `tiers_${type || 'tous'}`;
  if (!App.cache[cle]) {
    const donnees = await charge('/api/tiers', { type, actifs_seuls: 1, limite: 1000 });
    App.cache[cle] = donnees.tiers.map((t) => [t.id, `${t.code} — ${t.raison_sociale}`]);
  }
  return App.cache[cle];
}

function videCache(prefixe = '') {
  for (const cle of Object.keys(App.cache)) {
    if (!prefixe || cle.startsWith(prefixe)) delete App.cache[cle];
  }
}

async function optionsComptes(filtre = '') {
  const cle = `comptes_${filtre}`;
  if (!App.cache[cle]) {
    const donnees = await charge('/api/comptes', { q: filtre, actifs_seuls: 1 });
    App.cache[cle] = donnees.comptes.map((c) => [c.numero, `${c.numero} — ${c.intitule}`]);
  }
  return App.cache[cle];
}

async function optionsTresorerie() {
  if (!App.cache.tresorerie) {
    const donnees = await charge('/api/tresorerie');
    App.cache.tresorerie = donnees.comptes
      .filter((c) => c.actif)
      .map((c) => [c.id, `${c.libelle} (${c.compte})`]);
  }
  return App.cache.tresorerie;
}

/* ------------------------------------------------------------ Routeur --- */

function navigue(route) { window.location.hash = route; }

function routeCourante() {
  const brut = window.location.hash.slice(1) || '/';
  const [chemin, requeteTexte] = brut.split('?');
  const parametres = Object.fromEntries(new URLSearchParams(requeteTexte || ''));
  return { chemin, parametres, segments: chemin.split('/').filter(Boolean) };
}

async function afficheRoute() {
  const route = routeCourante();
  const cle = route.segments.length
    ? (App.pages[route.segments.slice(0, 2).join('/')] ? route.segments.slice(0, 2).join('/')
      : route.segments[0])
    : 'accueil';
  const page = App.pages[cle] || App.pages.accueil;

  $$('#menu a').forEach((a) => {
    const cible = a.getAttribute('href').slice(1).split('?')[0];
    a.classList.toggle('actif', cible === route.chemin
      || (cible !== '/' && route.chemin.startsWith(cible)));
  });

  const contenu = $('#contenu');
  contenu.innerHTML = '<div class="vide">Chargement…</div>';
  $('#actions-page').innerHTML = '';
  $('#sous-titre-page').textContent = '';

  try {
    $('#titre-page').textContent = page.titre || '';
    await page.afficher(contenu, route);
  } catch (err) {
    erreur(err);
    contenu.innerHTML = `<div class="message danger"><strong>Impossible d'afficher cette page</strong>
      ${ech(err.message)}</div>`;
  }
}

function actionsPage(html) { $('#actions-page').innerHTML = html; }
function sousTitre(texte) { $('#sous-titre-page').textContent = texte; }

window.addEventListener('hashchange', afficheRoute);
