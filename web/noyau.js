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

/** Le serveur est injoignable : ni erreur métier, ni bogue applicatif. */
class ErreurReseau extends Error {
  constructor() {
    super("L'application n'est plus en cours d'exécution sur cet ordinateur, "
        + 'ou sa fenêtre a été fermée. Vos données sont intactes.');
    this.nom = 'reseau';
  }
}

async function api(chemin, options = {}) {
  const config = { headers: {}, credentials: 'same-origin', ...options };
  if (config.corps !== undefined) {
    config.method = config.method || 'POST';
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(config.corps);
    delete config.corps;
  }
  let reponse;
  try {
    reponse = await fetch(chemin, config);
  } catch (err) {
    // « NetworkError when attempting to fetch resource » sous Firefox,
    // « Failed to fetch » sous Chrome : illisibles pour un comptable.
    signaleServeurInjoignable();
    throw new ErreurReseau();
  }
  serveurRepond();
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

/* -------------------------------------------------- perte de connexion --- */

let _serveurInjoignable = false;
let _sondeReconnexion = null;

/** Affiche un bandeau persistant et tente de rétablir la liaison. */
function signaleServeurInjoignable() {
  if (_serveurInjoignable) return;
  _serveurInjoignable = true;

  let bandeau = document.getElementById('bandeau-hors-ligne');
  if (!bandeau) {
    bandeau = document.createElement('div');
    bandeau.id = 'bandeau-hors-ligne';
    bandeau.className = 'bandeau-hors-ligne';
    document.body.appendChild(bandeau);
  }
  bandeau.innerHTML = `
    <strong>Connexion perdue avec l'application.</strong>
    <span>Elle a été fermée, ou une autre fenêtre l'a remplacée.
    Aucune donnée n'est perdue&nbsp;: rouvrez-la depuis le raccourci
    « Cabinet Immo », puis cliquez sur Réessayer.</span>
    <button class="primaire" id="bouton-reessayer">Réessayer</button>`;
  bandeau.hidden = false;
  bandeau.querySelector('#bouton-reessayer')
         .addEventListener('click', () => location.reload());

  // Le serveur peut revenir seul (redémarrage) : on le guette.
  if (!_sondeReconnexion) {
    _sondeReconnexion = setInterval(async () => {
      try {
        const rep = await fetch('/api/etat', { cache: 'no-store' });
        if (rep.ok) location.reload();
      } catch (err) { /* toujours absent */ }
    }, 3000);
  }
}

function serveurRepond() {
  if (!_serveurInjoignable) return;
  _serveurInjoignable = false;
  clearInterval(_sondeReconnexion);
  _sondeReconnexion = null;
  const bandeau = document.getElementById('bandeau-hors-ligne');
  if (bandeau) bandeau.hidden = true;
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

/* Sur un écran de comptabilité, la même suite de chiffres se répète des
   dizaines de fois et tout y a le même poids : « 146 000 000,00 » consacre
   trois caractères sur douze à des centimes nuls. Les deux fonctions qui
   suivent n'enlèvent rien — elles allègent visuellement ce qui ne porte pas
   l'information, pour que les millions ressortent. Le montant reste exact,
   copiable et exportable tel quel. */

/** Passe les centimes d'un montant déjà formaté en gris clair. */
function centimesDiscrets(contenu) {
  const html = String(contenu ?? '');
  // Un champ de saisie n'est pas un montant affiché : on n'y touche pas.
  if (!html || html.includes('<input') || html.includes('<select')) return contenu;
  return html.replace(/,(\d\d)(?!\d)/g, '<span class="dec">,$1</span>');
}

/** Marque « 0,00 » pour qu'un montant nul ne pèse pas comme un vrai montant. */
function montantNul(contenu) {
  const html = String(contenu ?? '');
  return (html === '0,00' || html === '0,00 DA')
    ? `<span class="zero">${html}</span>` : contenu;
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
  const message = err.message || String(err);
  // Une panne technique n'apprend rien à un comptable : on lui propose de la
  // signaler plutôt que de le laisser photographier son écran.
  const technique = err.nom !== 'reseau' && /Erreur interne|Erreur 5\d\d/.test(message);
  notifie(message, 'danger', technique ? 12000 : 7000);
  if (technique) proposeSignalement(message);
}

/** Invite discrète à signaler, affichée sous la notification d'erreur. */
function proposeSignalement(message) {
  const boite = document.createElement('div');
  boite.className = 'notification danger';
  boite.innerHTML = `<strong>Ce n'est pas de votre fait.</strong>
    <div class="petit" style="margin:4px 0 8px">Envoyez le détail technique à
    la personne qui suit le logiciel — aucune donnée comptable n'y figure.</div>
    <button class="petit-bouton primaire">Signaler ce problème</button>`;
  boite.querySelector('button').onclick = () => {
    boite.remove();
    modaleSignalement(message);
  };
  $('#notifications').appendChild(boite);
  setTimeout(() => boite.remove(), 20000);
}

/** Montre le rapport avant tout envoi, et laisse choisir le moyen. */
async function modaleSignalement(message = '') {
  const ecran = location.hash || '/';
  let d;
  try {
    d = await api(requete('/api/incidents/rapport', { ecran, message }));
  } catch (err) { notifie(err.message, 'danger'); return; }

  const conteneur = document.createElement('div');
  conteneur.innerHTML = `
    <div class="message info">
      <strong>Voici exactement ce qui sera transmis</strong>
      La version, le système et le journal technique — rien d'autre. Aucune
      donnée comptable n'y figure : ni montant, ni nom de client, ni raison
      sociale. Les chemins de fichiers sont masqués, car ils portent votre nom
      de session.
    </div>
    <pre class="journal" id="rapport-incident">${ech(d.texte)}</pre>
    <div class="rangee" style="margin-top:12px; flex-wrap:wrap">
      <button id="rapport-copier">Copier</button>
      <button id="rapport-fichier">Enregistrer le fichier</button>
      ${d.canaux.length
        ? `<button class="primaire" id="rapport-envoyer">Envoyer par
             ${ech(d.canaux.map((c) => c.libelle).join(', '))}</button>`
        : '<span class="petit">Aucun canal configuré : copiez le rapport ou '
          + 'enregistrez-le, puis transmettez-le comme vous voulez.</span>'}
    </div>`;

  conteneur.querySelector('#rapport-copier').onclick = async () => {
    try {
      await navigator.clipboard.writeText(d.texte);
      notifie('Rapport copié. Collez-le dans votre message.', 'succes');
    } catch (err) {
      // Sans presse-papiers (navigateur ancien), on sélectionne le texte.
      const zone = conteneur.querySelector('#rapport-incident');
      const selection = window.getSelection();
      const plage = document.createRange();
      plage.selectNodeContents(zone);
      selection.removeAllRanges();
      selection.addRange(plage);
      notifie('Rapport sélectionné : faites Ctrl+C pour le copier.', 'info', 7000);
    }
  };
  conteneur.querySelector('#rapport-fichier').onclick = () =>
    telecharge('/api/incidents/fichier', { ecran, message });
  const bouton = conteneur.querySelector('#rapport-envoyer');
  if (bouton) {
    bouton.onclick = async () => {
      bouton.disabled = true;
      bouton.textContent = 'Envoi…';
      try {
        const r = await envoie('/api/incidents/envoyer', { ecran, message });
        notifie(`Signalement envoyé (${r.envoyes} destinataire(s)).`, 'succes');
        fermeModale();
      } catch (err) {
        notifie(err.message, 'danger', 9000);
        bouton.disabled = false;
        bouton.textContent = 'Réessayer l\'envoi';
      }
    };
  }

  modale({ titre: 'Signaler un problème', contenu: conteneur, large: true,
           boutons: [{ libelle: 'Fermer' }] });
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

/** Un formulaire précédé de ce qu'il faut savoir avant de le remplir.

    Une explication placée après coup n'est jamais lue : elle vient d'abord,
    dans le même bloc, et le formulaire suit. */
function avecNote(champs, genre, texte) {
  const conteneur = document.createElement('div');
  const note = document.createElement('p');
  note.className = `message ${genre}`;
  note.textContent = texte.replace(/\s+/g, ' ').trim();
  conteneur.appendChild(note);
  conteneur.appendChild(champs);
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

/**
 * Tableau générique. `colonnes` : {titre, cle|rendu, classe, largeur,
 * masquerSiVide}. Une colonne `masquerSiVide` dont aucune ligne n'est
 * remplie disparaît, elle et son entrée de pied : une colonne vide occupe
 * la place sans rien apprendre.
 * `options.coupure(ligne)` renvoie l'intitulé d'une section ; une ligne de
 * coupure est insérée à chaque changement.
 */
function tableau(colonnes, lignes, options = {}) {
  if (!lignes || !lignes.length) {
    return `<div class="vide"><span class="grand">${options.icone || '📭'}</span>
            ${ech(options.messageVide || 'Aucun élément à afficher.')}</div>`;
  }
  // Contenu de chaque cellule, calculé une seule fois : il sert à décider
  // quelles colonnes sont vides avant d'écrire quoi que ce soit.
  const grille = lignes.map((ligne, index) => colonnes.map(
    (c) => c.rendu ? c.rendu(ligne, index) : ech(ligne[c.cle] ?? '')));
  const gardees = colonnes.map((c, i) => !c.masquerSiVide
    || grille.some((cellules) => String(cellules[i] ?? '').trim() !== ''));

  const entetes = colonnes.map((c, i) => gardees[i]
    ? `<th class="${c.classe || ''}" ${c.largeur ? `style="width:${c.largeur}"` : ''}>${ech(c.titre)}</th>`
    : '').join('');
  const nbColonnes = gardees.filter(Boolean).length;

  let sectionCourante = null;
  const corps = lignes.map((ligne, index) => {
    const cellules = colonnes.map((c, i) => {
      if (!gardees[i]) return '';
      const classe = c.classe || '';
      let contenu = grille[index][i];
      if (classe.indexOf('num') >= 0) contenu = centimesDiscrets(montantNul(contenu));
      return `<td class="${classe}">${contenu}</td>`;
    }).join('');
    const attributs = options.attributsLigne ? options.attributsLigne(ligne) : '';
    // Le rayage suit le rang de la donnée, pas celui de la ligne HTML : les
    // lignes de coupure ne doivent pas inverser l'alternance derrière elles.
    const classes = `${options.clic ? 'cliquable ' : ''}${index % 2 ? 'paire' : ''}`;
    const rangee = `<tr class="${classes}" ${attributs}>${cellules}</tr>`;
    if (!options.coupure || Apparence.get('coupures') === 'non') return rangee;
    const section = options.coupure(ligne);
    if (section === sectionCourante) return rangee;
    sectionCourante = section;
    return (section
      ? `<tr class="coupure"><td colspan="${nbColonnes}">${ech(section)}</td></tr>`
      : '') + rangee;
  }).join('');

  const pied = options.pied ? `<tfoot><tr>${options.pied.map((c, i) => {
    if (!gardees[i]) return '';
    const classe = c.classe || '';
    const contenu = c.contenu ?? '';
    return `<td class="${classe}">${classe.indexOf('num') >= 0
      ? centimesDiscrets(montantNul(contenu)) : contenu}</td>`;
  }).join('')}</tr></tfoot>` : '';
  // Au-delà d'une trentaine de lignes, la liste défile dans son cadre :
  // c'est ce qui garde l'en-tête et les totaux visibles pendant la lecture.
  const defilante = lignes.length > 30 && options.defilante !== false ? ' defilante' : '';
  return `<div class="enveloppe-table${defilante}"><table class="donnees">
          <thead><tr>${entetes}</tr></thead><tbody>${corps}</tbody>${pied}</table></div>`;
}

/**
 * Une carte : un titre, un contenu, et les actions qui vont avec.
 *
 * L'en-tête ne s'affichait qu'en présence d'un titre — et comme il porte
 * aussi les boutons, une carte sans titre perdait ses actions en silence.
 * Trois écrans y ont laissé leurs boutons principaux : lettrer une
 * sélection, reverser aux propriétaires, comptabiliser la paie. Un titre
 * vide est un choix de mise en page, pas une raison de masquer un bouton.
 */
function carte(titre, contenu, actions = '', serre = false) {
  return `<div class="carte">
    ${titre || actions ? `<div class="entete-carte">
      ${titre ? `<h2>${ech(titre)}</h2>` : '<span></span>'}
      <div class="rangee">${actions}</div></div>` : ''}
    <div class="corps ${serre ? 'serre' : ''}">${contenu}</div></div>`;
}

function indicateur(libelle, valeur, detail = '', genre = '') {
  return `<div class="indicateur ${genre}">
    <div class="libelle">${ech(libelle)}</div>
    <div class="valeur">${centimesDiscrets(valeur)}</div>
    ${detail ? `<div class="detail">${detail}</div>` : ''}</div>`;
}

/* Un comptable lit une balance par classe : les comptes de bilan d'abord,
   puis la gestion. Vingt lignes d'affilée sans repère obligent à relire le
   numéro de chaque compte pour savoir où l'on en est. */
const CLASSES_SCF = {
  1: 'Classe 1 — Capitaux',
  2: 'Classe 2 — Immobilisations',
  3: 'Classe 3 — Stocks et en-cours',
  4: 'Classe 4 — Tiers',
  5: 'Classe 5 — Financiers',
  6: 'Classe 6 — Charges',
  7: 'Classe 7 — Produits',
};

function classeScf(compte) {
  return CLASSES_SCF[Number(String(compte || '').charAt(0))] || null;
}

const PERIMETRES = {
  declare: ['Déclaré', 'ordinaire'],
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
  brouillon: ['Brouillon', 'alerte'], validee: ['Validée', 'ordinaire'], payee: ['Payée', 'succes'],
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

/* ------------------------------------------------- Où suis-je ? --------

   Une application de comptabilité a une trentaine d'écrans qui se
   ressemblent : des tableaux de chiffres. Sans repère, on ne sait plus si
   l'on regarde le journal ou le grand livre. Trois marques répondent à la
   question, toujours au même endroit : l'entrée de menu en surbrillance
   pleine, le titre de sa rubrique éclairé, et le nom de la rubrique rappelé
   au-dessus du titre de la page. */

//: Écrans qui n'ont pas d'entrée de menu à eux : ils vivent sous une autre.
//: Sans cette table, ouvrir le rapprochement bancaire ou la fiche d'un lot
//: éteindrait tout le menu — l'utilisateur ne saurait plus d'où il vient.
const RATTACHEMENTS = {
  '/rapprochement': '/tresorerie',
  '/agence/mandats': '/agence/biens',
  '/promotion/lots': '/promotion/programmes',
  '/fiscalite/tva': '/fiscalite/g50',
  '/fiscalite/ibs': '/fiscalite/g50',
  '/fiscalite/parametres': '/fiscalite/g50',
  '/paie/salaries': '/paie/bulletins',
  '/paie/simulateur': '/paie/bulletins',
};

function _segments(chemin) { return chemin.split('/').filter(Boolean); }

/** À quel point cette entrée de menu correspond à la page affichée. */
function _pertinence(cible, chemin, seulEntree) {
  if (cible === chemin) return 100;
  const a = _segments(cible);
  const b = _segments(chemin);
  if (!a.length) return chemin === '/' ? 100 : 0;
  if (a[0] !== b[0]) return 0;
  // « /tiers » couvre « /tiers/12/releve »
  if (chemin.startsWith(cible + '/')) return 50 + a.length;
  // Une seule entrée porte cette rubrique : c'est forcément elle.
  if (seulEntree) return 20;
  // La fiche « promotion/programme/3 » rejoint la liste « promotion/programmes »
  if (a[1] && b[1] && (a[1].startsWith(b[1]) || b[1].startsWith(a[1]))) return 10;
  // Même rubrique, mais pas la même entrée : on éclaire le groupe seulement.
  return 1;
}

function marqueMenuActif(route) {
  const liens = $$('#menu a');
  // « /rapprochement/12 » comme « /rapprochement » doivent éclairer la
  // trésorerie : on essaie du plus précis au plus général.
  const chemin = RATTACHEMENTS[route.chemin]
    || RATTACHEMENTS['/' + route.segments.slice(0, 2).join('/')]
    || RATTACHEMENTS['/' + (route.segments[0] || '')]
    || route.chemin;

  const parRubrique = {};
  liens.forEach((a) => {
    const r = _segments(a.getAttribute('href').slice(1).split('?')[0])[0] || '/';
    parRubrique[r] = (parRubrique[r] || 0) + 1;
  });

  let gagnant = null;
  let meilleure = 0;
  liens.forEach((a) => {
    const cible = a.getAttribute('href').slice(1).split('?')[0];
    const rubrique = _segments(cible)[0] || '/';
    const score = _pertinence(cible, chemin, parRubrique[rubrique] === 1);
    a.dataset.pertinence = score;
    if (score > meilleure) { meilleure = score; gagnant = a; }
  });

  liens.forEach((a) => {
    const actif = a === gagnant && meilleure > 1;
    a.classList.toggle('actif', actif);
    if (actif) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });

  // La rubrique s'éclaire même quand aucune entrée ne convient exactement :
  // savoir qu'on est « dans la promotion » vaut mieux que rien du tout.
  $$('#menu .groupe-menu').forEach((g) => {
    g.classList.toggle('actif', gagnant ? g.contains(gagnant) : false);
  });

  const rubrique = gagnant?.closest('.groupe-menu')?.dataset.groupe || '';
  const chapeau = $('#section-courante');
  if (chapeau) {
    chapeau.textContent = rubrique;
    chapeau.hidden = !rubrique;
  }
  // Le menu est plus long que l'écran : l'entrée courante doit rester visible.
  if (gagnant) gagnant.scrollIntoView({ block: 'nearest' });
}

async function afficheRoute() {
  const route = routeCourante();
  const cle = route.segments.length
    ? (App.pages[route.segments.slice(0, 2).join('/')] ? route.segments.slice(0, 2).join('/')
      : route.segments[0])
    : 'accueil';
  const page = App.pages[cle] || App.pages.accueil;

  marqueMenuActif(route);

  const contenu = $('#contenu');
  contenu.innerHTML = '<div class="vide">Chargement…</div>';
  $('#actions-page').innerHTML = '';
  $('#sous-titre-page').textContent = '';

  try {
    $('#titre-page').textContent = page.titre || '';
    const chapeau = $('#section-courante');
    if (chapeau && chapeau.textContent === (page.titre || '')) chapeau.hidden = true;
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

/* ------------------------------------------------- Justificatifs -------- */

/* Une écriture sans sa pièce est une écriture indéfendable : le jour d'un
   contrôle, c'est la facture qu'on demande, pas le libellé. Le stockage, les
   routes et l'inclusion dans les sauvegardes existaient déjà — il manquait
   seulement de quoi s'en servir. Écrit une fois pour toutes les entités
   (écriture, facture, bail, contrat…), même si seule l'écriture s'en sert
   pour l'instant. */

const TAILLE_MAX_PIECE = 20 * 1024 * 1024;

function _octets(n) {
  const ko = Number(n || 0) / 1024;
  return ko < 1024 ? `${Math.max(1, Math.round(ko))} Ko`
                   : `${(ko / 1024).toFixed(1)} Mo`;
}

/** Liste des pièces d'une entité + zone de dépôt. */
function blocJustificatifs(entite, entiteId, pieces) {
  const lignes = (pieces || []).map((p) => `
    <li>
      <a href="/fichiers/${ech(encodeURI(p.chemin))}" target="_blank" rel="noopener">${ech(p.nom_fichier)}</a>
      <span class="tres-petit">${_octets(p.taille)} · ${ech((p.cree_le || '').slice(0, 10))}</span>
      <button class="petit-bouton danger" data-piece="${p.id}"
              title="Retirer ce justificatif">Retirer</button>
    </li>`).join('');

  return `<fieldset class="justificatifs">
    <legend>Justificatifs${pieces && pieces.length ? ` (${pieces.length})` : ''}</legend>
    ${lignes ? `<ul class="liste-pieces">${lignes}</ul>`
             : `<p class="aide">Aucune pièce rattachée. Ajoutez le scan ou la
                photo de la facture : c'est elle qu'on vous demandera.</p>`}
    <div class="rangee" style="align-items:center; gap:10px; margin-top:8px">
      <input type="file" id="pj-fichier"
             accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.tif,.tiff,.doc,.docx,.xls,.xlsx,.csv,.txt,.odt,.ods">
      <button class="petit-bouton primaire" id="pj-ajouter"
              data-entite="${ech(entite)}" data-id="${entiteId}">Ajouter</button>
    </div>
    <div id="pj-message"></div>
  </fieldset>`;
}

/** Branche le dépôt et le retrait, une fois la fenêtre affichée. */
function brancheJustificatifs(entite, entiteId) {
  const bouton = $('#pj-ajouter');
  if (!bouton) return;
  bouton.onclick = () => deposeJustificatif(entite, entiteId);
  document.querySelectorAll('#zone-justificatifs [data-piece]').forEach((b) => {
    b.onclick = () => retireJustificatif(b.dataset.piece, entite, entiteId, b);
  });
}

async function rafraichitJustificatifs(entite, entiteId) {
  const zone = $('#zone-justificatifs');
  if (!zone) return;
  const d = await charge('/api/pieces', { entite, entite_id: entiteId });
  zone.innerHTML = blocJustificatifs(entite, entiteId, d.pieces || []);
  brancheJustificatifs(entite, entiteId);
}

async function deposeJustificatif(entite, entiteId) {
  const champ = $('#pj-fichier');
  const message = $('#pj-message');
  const fichier = champ && champ.files[0];
  if (!fichier) { notifie('Choisissez d\'abord un fichier.', 'alerte'); return; }
  // Contrôlé ici pour éviter d'encoder 40 Mio avant de se faire refuser.
  if (fichier.size > TAILLE_MAX_PIECE) {
    message.innerHTML = `<div class="message alerte">Ce fichier fait
      ${_octets(fichier.size)}. Maximum : 20 Mo — scannez en qualité réduite,
      ou en noir et blanc.</div>`;
    return;
  }
  const bouton = $('#pj-ajouter');
  bouton.disabled = true;
  message.innerHTML = '<div class="petit">Enregistrement…</div>';
  try {
    const contenu = await litFichierBase64(fichier);
    await envoie('/api/pieces', {
      entite, entite_id: entiteId, contenu,
      nom_fichier: fichier.name, type_mime: fichier.type || '',
    });
    notifie('Justificatif ajouté.', 'succes');
    await rafraichitJustificatifs(entite, entiteId);
  } catch (err) {
    message.innerHTML = `<div class="message danger">${ech(err.message)}</div>`;
    bouton.disabled = false;
  }
}

/* La confirmation se fait sur le bouton lui-même, en deux temps. Passer par
   `confirme()` ouvrirait une seconde fenêtre dans la même boîte
   (`#corps-modale`) et effacerait l'écriture qu'on est en train de
   consulter — le piège avait déjà coûté une correction sur l'écran d'import. */
async function retireJustificatif(id, entite, entiteId, bouton) {
  if (bouton && bouton.dataset.confirme !== '1') {
    bouton.dataset.confirme = '1';
    bouton.textContent = 'Confirmer ?';
    bouton.title = 'Le fichier sera supprimé du dossier. L\'écriture ne bouge pas.';
    setTimeout(() => {
      if (!bouton.isConnected || bouton.dataset.confirme !== '1') return;
      delete bouton.dataset.confirme;
      bouton.textContent = 'Retirer';
    }, 4000);
    return;
  }
  await api(`/api/pieces/${id}`, { method: 'DELETE' });
  notifie('Justificatif retiré.', 'succes');
  await rafraichitJustificatifs(entite, entiteId);
}

/* ------------------------------------------- Version restée en mémoire ----

   Les fichiers de l'interface sont relus sur le disque à chaque requête ;
   le code Python, lui, n'est chargé qu'au démarrage. Une mise à jour dont
   l'application ne s'est pas relancée donne donc une interface neuve sur un
   moteur ancien : des écrans qui existent, des routes qui répondent
   « ressource introuvable ». C'est arrivé une fois, en silence. Plus
   jamais. */

function signaleRedemarrageRequis(etat) {
  if (!etat || !etat.redemarrage_requis) return;
  if ($('#bandeau-redemarrage')) return;
  const barre = document.createElement('div');
  barre.id = 'bandeau-redemarrage';
  barre.className = 'bandeau-redemarrage';
  barre.innerHTML = `
    <span style="font-size:20px">⚠️</span>
    <div>
      <strong>La mise à jour n'est pas terminée</strong>
      La version ${ech(etat.version_disque)} est installée sur le disque, mais
      l'application tourne encore sur la ${ech(etat.version)} : elle ne s'est
      pas relancée. Les écrans nouveaux s'affichent, mais répondent
      « ressource introuvable ». <strong>Fermez complètement l'application et
      rouvrez-la</strong> — vos données ne risquent rien.
    </div>
    <button id="quitter-pour-redemarrer">Fermer l'application</button>`;
  document.body.appendChild(barre);
  $('#quitter-pour-redemarrer').onclick = async () => {
    try { await api('/api/systeme/arreter', { method: 'POST', corps: {} }); }
    catch (err) { /* la fermeture coupe la réponse : c'est normal */ }
    document.body.innerHTML = `<div class="ecran-chargement">
      <div class="logo-grand">🏢</div>
      <div>L'application est fermée.</div>
      <div class="petit">Rouvrez-la par son raccourci habituel : elle
      redémarrera sur la version ${ech(etat.version_disque)}.</div></div>`;
  };
}

/* --------------------------------------- Où sont vraiment les données ----

   Windows ouvre une archive comme un dossier : on y voit l'application, on
   la lance, elle fonctionne — et le dossier provisoire est effacé ensuite.
   C'est arrivé : un poste a travaillé depuis l'aperçu d'un zip, dans
   AppData\Local\Temp. Rien à l'écran ne le disait. Le bandeau le dit, et
   il ne se ferme pas : ce n'est pas un conseil, c'est la perte du dossier. */

function signaleEmplacementRisque(etat) {
  const risque = etat && etat.emplacement_risque;
  if (!risque) return;
  if ($('#bandeau-emplacement')) return;
  const barre = document.createElement('div');
  barre.id = 'bandeau-emplacement';
  barre.className = 'bandeau-redemarrage';
  barre.innerHTML = `
    <span style="font-size:20px">⚠️</span>
    <div>
      <strong>${ech(risque.titre)}</strong>
      ${ech(risque.detail)}
    </div>`;
  document.body.appendChild(barre);
}

/* ------------------------------------------------- Recherche globale ----

   Un comptable ne se souvient pas de l'écran où se trouve ce qu'il cherche :
   il se souvient d'un nom, d'un numéro de facture — ou d'un montant. Le cas
   du montant est le plus utile et le moins évident : taper « 125 000 »
   retrouve la ligne d'écriture qui le porte, au débit comme au crédit. C'est
   ainsi qu'on remonte à l'origine d'un solde qui ne tombe pas juste. */

let _minuteurRecherche = null;
let _dernierTexteRecherche = '';

function _boiteRecherche() { return $('#resultats-recherche'); }

function fermeRecherche() {
  const boite = _boiteRecherche();
  if (boite) { boite.hidden = true; boite.innerHTML = ''; }
}

function _rendResultatsRecherche(d) {
  const boite = _boiteRecherche();
  if (!boite) return;
  if (!d.groupes.length) {
    boite.innerHTML = `<div class="rien">Rien trouvé pour «&nbsp;${ech(d.q)}&nbsp;».
      ${d.montant ? '' : 'Un montant se cherche tel qu\'il est écrit : 125000 ou 125 000,00.'}
      </div>`;
    boite.hidden = false;
    return;
  }
  boite.innerHTML = d.groupes.map((g) => `
    <div class="titre-groupe">${g.icone} ${ech(g.libelle)}
      <span class="compte">${g.total > g.resultats.length
        ? `${g.resultats.length} sur ${g.total}` : g.total}</span></div>
    ${g.resultats.map((r) => `
      <a class="resultat" href="#${r.route}">
        <span class="principal">${ech(r.titre || '(sans libellé)')}
          <span class="secondaire">${ech(r.detail || '')}${
            r.perimetre === 'hors_declaration'
              ? ' · <em>hors déclaration</em>' : ''}</span></span>
        ${r.montant != null
          ? `<span class="montant-resultat">${centimesDiscrets(fm(r.montant))}</span>`
          : ''}
      </a>`).join('')}`).join('')
    + `<div class="astuce">${d.total} résultat(s) · ↑ ↓ pour parcourir,
       Entrée pour ouvrir, Échap pour fermer</div>`;
  boite.hidden = false;
}

async function lanceRecherche(texte) {
  const boite = _boiteRecherche();
  if (!boite) return;
  if (texte.trim().length < 2) { fermeRecherche(); return; }
  boite.innerHTML = '<div class="attente">Recherche…</div>';
  boite.hidden = false;
  try {
    const d = await api(requete('/api/recherche',
      { societe: App.etat.societe?.id, q: texte.trim() }));
    // Une réponse arrivée en retard ne doit pas écraser une frappe plus récente.
    if (texte !== _dernierTexteRecherche) return;
    _rendResultatsRecherche(d);
  } catch (err) {
    boite.innerHTML = `<div class="rien">${ech(err.message)}</div>`;
  }
}

function _deplaceDansRecherche(pas) {
  const items = $$('#resultats-recherche a.resultat');
  if (!items.length) return;
  const courant = items.findIndex((a) => a.classList.contains('survol'));
  const suivant = Math.max(0, Math.min(items.length - 1,
    courant < 0 ? (pas > 0 ? 0 : items.length - 1) : courant + pas));
  items.forEach((a) => a.classList.remove('survol'));
  items[suivant].classList.add('survol');
  items[suivant].scrollIntoView({ block: 'nearest' });
}

function brancheRechercheGlobale() {
  const champ = $('#champ-recherche');
  if (!champ) return;
  champ.oninput = () => {
    _dernierTexteRecherche = champ.value;
    clearTimeout(_minuteurRecherche);
    _minuteurRecherche = setTimeout(() => lanceRecherche(champ.value), 220);
  };
  champ.onfocus = () => { if (champ.value.trim().length >= 2) lanceRecherche(champ.value); };
  champ.onkeydown = (ev) => {
    if (ev.key === 'Escape') { fermeRecherche(); champ.blur(); return; }
    if (ev.key === 'ArrowDown') { ev.preventDefault(); _deplaceDansRecherche(1); return; }
    if (ev.key === 'ArrowUp') { ev.preventDefault(); _deplaceDansRecherche(-1); return; }
    if (ev.key === 'Enter') {
      const cible = $('#resultats-recherche a.survol') || $('#resultats-recherche a.resultat');
      if (cible) { ev.preventDefault(); cible.click(); }
    }
  };
  // Un clic sur un résultat mène à la page : le panneau n'a plus lieu d'être.
  _boiteRecherche().onclick = (ev) => {
    if (ev.target.closest('a.resultat')) { fermeRecherche(); champ.blur(); }
  };
  document.addEventListener('click', (ev) => {
    if (!ev.target.closest('.recherche-globale')) fermeRecherche();
  });
  document.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      champ.focus();
      champ.select();
    }
  });
}
