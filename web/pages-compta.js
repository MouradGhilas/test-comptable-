/* ==========================================================================
   Pages comptables : écritures, grand livre, balance, lettrage,
   états financiers, clôture, facturation
   ========================================================================== */

App.pages['comptabilite/ecritures'] = {
  titre: 'Journal des écritures',
  async afficher(zone, route) {
    const filtres = {
      journal: route.parametres.journal || '',
      du: route.parametres.du || '',
      au: route.parametres.au || '',
      q: route.parametres.q || '',
      sans_piece: route.parametres.sans_piece || '',
    };
    // Venu de la recherche globale : on ouvre directement l'écriture visée,
    // plutôt que de laisser le comptable la chercher dans la liste.
    const ecritureVisee = route.parametres.ecriture;
    actionsPage(`<button class="primaire" onclick="saisieEcriture()">+ Écriture</button>
      <button onclick="choisitModeleEcriture()">Depuis un modèle</button>
      <button onclick="telecharge('/api/export/journal', ${JSON.stringify(filtres).replace(/"/g, "'")})">Exporter le journal</button>`);

    const [d, journaux] = await Promise.all([
      charge('/api/ecritures', { ...filtres, limite: 300 }),
      charge('/api/journaux'),
    ]);

    zone.innerHTML = `
      <div class="barre-outils">
        <label class="champ recherche"><span>Rechercher</span>
          <input id="f-q" value="${ech(filtres.q)}" placeholder="Libellé, n°, pièce…"></label>
        <label class="champ"><span>Journal</span><select id="f-journal">
          <option value="">Tous</option>
          ${journaux.journaux.map((j) => `<option value="${j.code}" ${j.code === filtres.journal ? 'selected' : ''}>${j.code} — ${ech(j.libelle)}</option>`).join('')}
        </select></label>
        <label class="champ"><span>Du</span><input type="date" id="f-du" value="${filtres.du}"></label>
        <label class="champ"><span>Au</span><input type="date" id="f-au" value="${filtres.au}"></label>
        <label class="champ"><span><input type="checkbox" id="f-sans-piece"
          ${filtres.sans_piece === '1' ? 'checked' : ''}> Sans justificatif</span></label>
        <button onclick="appliqueFiltresEcritures()">Filtrer</button>
      </div>
      ${carte(`${d.total} écriture(s)`, tableau([
        { titre: 'Date', rendu: (e) => fdate(e.date), largeur: '90px' },
        { titre: 'Jal', cle: 'journal', largeur: '50px' },
        { titre: 'N°', cle: 'numero', largeur: '110px' },
        { titre: 'Pièce', cle: 'piece' },
        { titre: 'Libellé', rendu: (e) => ech(e.libelle) },
        { titre: 'Montant', classe: 'num', rendu: (e) => fm(e.montant) },
        // Un trombone vaut mieux qu'une colonne de plus : présent ou absent,
        // cela se voit en balayant la liste.
        { titre: '', classe: 'centre', largeur: '34px',
          rendu: (e) => e.nb_pieces
            ? `<span title="${e.nb_pieces} justificatif(s)">📎</span>`
            : '<span class="discret" title="Aucun justificatif">·</span>' },
        { titre: 'État', rendu: (e) => e.validee ? etiquette('validee') : etiquette('brouillon') },
        { titre: 'Périmètre', rendu: (e) => badgePerimetre(e.perimetre) + rappelOperation(e) },
        { titre: 'Origine', rendu: (e) => `<span class="tres-petit">${ech(e.module || '')}</span>` },
      ], d.ecritures, {
        clic: true, icone: '📒',
        messageVide: 'Aucune écriture. Utilisez « + Écriture » ou laissez les modules métier les générer.',
        // Un clic ouvre l'écriture, un double-clic la corrige directement :
        // c'est le geste attendu par quelqu'un qui tient un journal.
        attributsLigne: (e) => `onclick="detailEcriture(${e.id})" `
          + `ondblclick="modifieEcriture(${e.id})" title="Double-clic : modifier"`,
        // Un journal se lit par mois : sans repère, trois cents lignes
        // obligent à relire chaque date pour savoir où l'on en est.
        coupure: (e) => fperiode(String(e.date || '').slice(0, 7)),
      }), '', true)}`;

    if (ecritureVisee) detailEcriture(ecritureVisee);
  },
};

/** Rappelle qu'une écriture n'est qu'une part d'une opération plus large. */
function rappelOperation(e) {
  if (!e.operation) return '';
  return `<div class="tres-petit" title="Saisie en totalité : les deux parts `
       + `forment une seule opération">part d'une opération de ${fm(e.operation.total)}`
       + `</div>`;
}

function appliqueFiltresEcritures() {
  const p = new URLSearchParams();
  for (const c of ['q', 'journal', 'du', 'au']) {
    const v = $(`#f-${c}`).value;
    if (v) p.set(c, v);
  }
  if ($('#f-sans-piece').checked) p.set('sans_piece', '1');
  navigue(`/comptabilite/ecritures?${p}`);
}

async function detailEcriture(id) {
  const e = await api(`/api/ecritures/${id}`);
  const totalDebit = e.lignes.reduce((s, l) => s + l.debit, 0);
  const totalCredit = e.lignes.reduce((s, l) => s + l.credit, 0);
  modale({
    titre: `Écriture ${e.numero} — ${e.journal}`,
    large: true,
    contenu: `
      <div class="liste-definitions" style="margin-bottom:14px">
        <dt>Date</dt><dd>${fdate(e.date)}</dd>
        <dt>Libellé</dt><dd>${ech(e.libelle)}</dd>
        <dt>Pièce</dt><dd>${ech(e.piece || '—')}</dd>
        <dt>Origine</dt><dd>${ech(e.module || 'saisie manuelle')}
          ${e.source_type ? `(${ech(e.source_type)})` : ''}</dd>
        <dt>État</dt><dd>${e.validee ? etiquette('validee') : etiquette('brouillon')}</dd>
        <dt>Périmètre</dt><dd>${badgePerimetre(e.perimetre)}</dd>
        <dt>Saisie</dt><dd>${ech(e.cree_par || '—')} le ${e.cree_le}</dd>
      </div>
      ${tableau([
        { titre: 'Compte', rendu: (l) => `<strong>${ech(l.compte)}</strong>` },
        { titre: 'Intitulé', rendu: (l) => `<span class="petit">${ech(l.compte_intitule || '')}</span>` },
        { titre: 'Tiers', cle: 'tiers_nom' },
        { titre: 'Libellé', rendu: (l) => ech(l.libelle || '') },
        { titre: 'Débit', classe: 'num', rendu: (l) => l.debit ? fm(l.debit) : '' },
        { titre: 'Crédit', classe: 'num', rendu: (l) => l.credit ? fm(l.credit) : '' },
        { titre: 'Lettr.', cle: 'lettrage' },
      ], e.lignes, {
        pied: [{ contenu: '<strong>TOTAUX</strong>' }, {}, {}, {},
          { contenu: `<strong>${fm(totalDebit)}</strong>`, classe: 'num' },
          { contenu: `<strong>${fm(totalCredit)}</strong>`, classe: 'num' }, {}],
      })}
      <div id="zone-justificatifs">${blocJustificatifs('ecriture', id, e.pieces || [])}</div>`,
    boutons: [
      { libelle: 'Fermer' },
      {
        libelle: 'Modifier', classe: 'primaire',
        action: () => { modifieEcriture(id); return false; },
      },
      {
        libelle: 'Dupliquer',
        action: () => { dupliqueEcriture(e); return false; },
      },
      {
        libelle: 'Extourner', classe: 'danger',
        action: async () => {
          if (!await confirme('Contre-passer cette écriture ?',
            'Une écriture inverse sera créée à la date du jour. L\'écriture d\'origine est conservée.',
            'Extourner')) return false;
          await api(`/api/ecritures/${id}/extourner`, { method: 'POST', corps: {} });
          notifie('Écriture extournée.', 'succes');
          afficheRoute();
        },
      },
    ],
  });
  brancheJustificatifs('ecriture', id);
}

/* ------------------------------------------------- Saisie d'écriture ---- */

async function saisieEcriture(prefill = {}) {
  const [journaux, comptes, tiers] = await Promise.all([
    charge('/api/journaux'), optionsComptes(), optionsTiers(),
  ]);
  const conteneur = document.createElement('div');
  conteneur.innerHTML = `
    <div class="ligne-champs">
      <label class="champ"><span>Journal *</span><select id="e-journal">
        ${journaux.journaux.map((j) => `<option value="${j.code}">${j.code} — ${ech(j.libelle)}</option>`).join('')}
      </select></label>
      <label class="champ"><span>Date *</span><input type="date" id="e-date" value="${prefill.date || aujourdhui()}"></label>
      <label class="champ"><span>N° de pièce</span><input id="e-piece" value="${ech(prefill.piece || '')}"></label>
      <label class="champ"><span>Périmètre</span><select id="e-perimetre">
        <option value="declare">Déclaré</option>
        <option value="hors_declaration">Hors déclaration</option>
        <option value="totalite">Totalité — déclaré + non déclaré</option>
      </select></label>
      <label class="champ" style="grid-column:1/-1"><span>Libellé *</span>
        <input id="e-libelle" value="${ech(prefill.libelle || '')}" placeholder="Ex : Facture fournisseur ETP El Amel"></label>
    </div>
    <p class="message info" id="note-totalite" hidden>
      <strong>Saisie en totalité</strong>
      Répartissez chaque montant entre sa part déclarée et sa part non déclarée.
      Les deux parts sont enregistrées ensemble, comme une seule opération, et
      chacune doit s'équilibrer de son côté.
    </p>
    <table class="saisie"><thead><tr>
      <th style="width:22%">Compte</th><th style="width:16%">Tiers</th>
      <th>Libellé</th>
      <th style="width:13%" id="th-debit">Débit</th>
      <th style="width:13%" class="col-hors">Débit non décl.</th>
      <th style="width:13%" id="th-credit">Crédit</th>
      <th style="width:13%" class="col-hors">Crédit non décl.</th>
      <th></th>
    </tr></thead><tbody id="lignes-saisie"></tbody></table>
    <div class="rangee" style="margin-top:8px">
      <button class="petit-bouton" id="ajout-ligne">+ Ligne</button>
      <span class="petit">Le compte se cherche au numéro comme au nom
        (« 401 » ou « fourniss »). Tab passe au champ suivant, la dernière
        ligne s'ajoute d'elle-même, et <strong>Entrée dans une case de montant
        vide y met ce qui manque</strong> pour équilibrer.</span>
    </div>
    <div class="bandeau-equilibre">
      <span>Total débit <strong id="tot-debit">0,00</strong></span>
      <span>Total crédit <strong id="tot-credit">0,00</strong></span>
      <span class="ecart" id="ecart"></span>
      <button type="button" class="petit-bouton" id="solder" hidden>Solder</button>
    </div>
    <div class="bandeau-equilibre" id="bandeau-totalite" hidden>
      <span>Opération <strong id="tot-operation">0,00</strong></span>
      <span>dont déclaré <strong id="tot-declare">0,00</strong></span>
      <span>dont non déclaré <strong id="tot-hors">0,00</strong></span>
      <span class="ecart" id="ecart-hors"></span>
      <button type="button" class="petit-bouton" id="solder-hors" hidden>Solder</button>
    </div>`;

  const corps = $('#lignes-saisie', conteneur);
  // Deux cent cinquante comptes dans une liste déroulante, c'est un compte
  // qu'on cherche à la molette. Un champ à liste native se cherche au
  // clavier, par le numéro comme par l'intitulé : « 401 » ou « fourniss ».
  conteneur.insertAdjacentHTML('beforeend', `
    <datalist id="liste-comptes">${comptes.map(([, l]) =>
      `<option value="${ech(l)}"></option>`).join('')}</datalist>
    <datalist id="liste-tiers">${tiers.map(([, l]) =>
      `<option value="${ech(l)}"></option>`).join('')}</datalist>`);

  /** Le numéro derrière ce qui a été tapé — ou le texte tel quel, pour que
      le serveur puisse dire précisément ce qui ne va pas. */
  const numeroCompte = (texte) => {
    const t = String(texte || '').trim();
    if (!t) return '';
    const exact = comptes.find(([, l]) => l === t);
    if (exact) return exact[0];
    const chiffres = t.match(/^(\d+)/);
    if (chiffres) return chiffres[1];
    const bas = t.toLowerCase();
    const proches = comptes.filter(([, l]) => l.toLowerCase().includes(bas));
    return proches.length === 1 ? proches[0][0] : t;
  };
  const libelleCompte = (numero) =>
    (comptes.find(([v]) => v === String(numero)) || [null, String(numero || '')])[1];

  const idTiers = (texte) => {
    const t = String(texte || '').trim();
    if (!t) return null;
    const exact = tiers.find(([, l]) => l === t);
    if (exact) return exact[0];
    const bas = t.toLowerCase();
    const proches = tiers.filter(([, l]) => l.toLowerCase().includes(bas));
    return proches.length === 1 ? proches[0][0] : null;
  };
  const libelleTiers = (id) =>
    (tiers.find(([v]) => String(v) === String(id)) || [null, ''])[1];

  function ajouteLigne(donnees = {}) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input class="l-compte" list="liste-comptes" autocomplete="off"
                 spellcheck="false" placeholder="N° ou nom"></td>
      <td><input class="l-tiers" list="liste-tiers" autocomplete="off"
                 spellcheck="false"></td>
      <td><input class="l-libelle" value="${ech(donnees.libelle || '')}"></td>
      <td><input class="l-debit num" inputmode="decimal" value="${donnees.debit ? pourChamp(donnees.debit) : ''}"></td>
      <td class="col-hors"><input class="l-debit-hors num" inputmode="decimal" value="${donnees.debit_hors ? pourChamp(donnees.debit_hors) : ''}"></td>
      <td><input class="l-credit num" inputmode="decimal" value="${donnees.credit ? pourChamp(donnees.credit) : ''}"></td>
      <td class="col-hors"><input class="l-credit-hors num" inputmode="decimal" value="${donnees.credit_hors ? pourChamp(donnees.credit_hors) : ''}"></td>
      <td><button class="plat petit-bouton" title="Supprimer">✕</button></td>`;
    if (donnees.compte) $('.l-compte', tr).value = libelleCompte(donnees.compte);
    if (donnees.tiers_id) $('.l-tiers', tr).value = libelleTiers(donnees.tiers_id);
    $('button', tr).onclick = () => { tr.remove(); recalcule(); };
    $$('input, select', tr).forEach((el) => {
      el.oninput = recalcule;
      el.onfocus = () => {
        if (tr === corps.lastElementChild) ajouteLigne();
      };
    });
    // Le débit et le crédit s'excluent, de part et d'autre.
    const exclut = (rempli, vide) => () => {
      if (cts($(rempli, tr).value)) $(vide, tr).value = '';
      recalcule();
    };
    $('.l-debit', tr).onchange = exclut('.l-debit', '.l-credit');
    $('.l-credit', tr).onchange = exclut('.l-credit', '.l-debit');
    $('.l-debit-hors', tr).onchange = exclut('.l-debit-hors', '.l-credit-hors');
    $('.l-credit-hors', tr).onchange = exclut('.l-credit-hors', '.l-debit-hors');

    // Entrée dans une case de montant vide : y mettre ce qui manque.
    $$('.l-debit, .l-credit, .l-debit-hors, .l-credit-hors', tr).forEach((el) => {
      el.onkeydown = (ev) => {
        if (ev.key !== 'Enter' || cts(el.value)) return;
        if (soldeRangee(tr, el.className.includes('hors'))) ev.preventDefault();
      };
    });

    // Le compte saisi appelle sa contrepartie habituelle sur la ligne d'en
    // face, quand elle est encore vide.
    $('.l-compte', tr).onchange = () => {
      marqueCompteInconnu($('.l-compte', tr));
      proposeContrepartie(tr);
      recalcule();
    };
    corps.appendChild(tr);
    return tr;
  }

  const enTotalite = () => $('#e-perimetre', conteneur).value === 'totalite';

  /** Un compte que le plan ne connaît pas se signale tout de suite, plutôt
      qu'au moment d'enregistrer. */
  function marqueCompteInconnu(champ) {
    const numero = numeroCompte(champ.value);
    const connu = !numero || comptes.some(([v]) => v === numero);
    champ.classList.toggle('invalide', !connu);
    champ.title = connu ? '' : `Le compte ${numero} n'est pas au plan comptable.`;
  }

  /** Propose le compte qui fait habituellement face, dans ce journal.

      Rien n'est deviné : la proposition vient de ce que le comptable a
      lui-même passé. Sans historique, le champ reste vide. */
  async function proposeContrepartie(tr) {
    const numero = numeroCompte($('.l-compte', tr).value);
    if (!numero) return;
    const remplies = $$('tr', corps).filter((l) => $('.l-compte', l).value.trim());
    if (remplies.length !== 1) return;            // seulement au premier compte
    const vides = $$('tr', corps).filter((l) => !$('.l-compte', l).value.trim());
    if (vides.length !== 1) return;               // et sur une seule ligne libre
    let d;
    try {
      d = await charge('/api/comptes/contrepartie',
                       { compte: numero, journal: $('#e-journal', conteneur).value });
    } catch (err) { return; }
    if (!d.compte || $('.l-compte', vides[0]).value.trim()) return;
    $('.l-compte', vides[0]).value = libelleCompte(d.compte);
    $('.l-compte', vides[0]).title =
      `Contrepartie habituelle de ${numero} dans ce journal (${d.emplois} fois). `
      + 'Modifiable.';
    $('.l-compte', vides[0]).classList.add('propose');
  }

  function litLignes() {
    const totalite = enTotalite();
    return $$('tr', corps).map((tr) => {
      const base = {
        compte: numeroCompte($('.l-compte', tr).value),
        tiers_id: idTiers($('.l-tiers', tr).value),
        libelle: $('.l-libelle', tr).value,
      };
      if (!totalite) {
        return { ...base, debit: $('.l-debit', tr).value,
                 credit: $('.l-credit', tr).value };
      }
      return { ...base,
        debit_declare: $('.l-debit', tr).value,
        credit_declare: $('.l-credit', tr).value,
        debit_hors: $('.l-debit-hors', tr).value,
        credit_hors: $('.l-credit-hors', tr).value };
    }).filter((l) => l.compte && (cts(l.debit) || cts(l.credit)
      || cts(l.debit_declare) || cts(l.credit_declare)
      || cts(l.debit_hors) || cts(l.credit_hors)));
  }

  /** Ce qui est tapé à l'écran, ligne à ligne — y compris les lignes
      incomplètes, que `litLignes` écarte pour l'enregistrement. Le bandeau
      d'équilibre doit dire ce qu'on voit, pas ce qui partira. */
  function lignesBrutes() {
    return $$('tr', corps).map((tr) => ({
      tr,
      compte: numeroCompte($('.l-compte', tr).value),
      debit: $('.l-debit', tr).value,
      credit: $('.l-credit', tr).value,
      debit_hors: $('.l-debit-hors', tr).value,
      credit_hors: $('.l-credit-hors', tr).value,
    }));
  }

  /** Ce qui manque pour équilibrer : positif = il manque au crédit. */
  function montantQuiSolde(hors) {
    const brutes = lignesBrutes();
    const somme = (champ) => brutes.reduce((s, l) => s + cts(l[champ]), 0);
    return hors ? somme('debit_hors') - somme('credit_hors')
                : somme('debit') - somme('credit');
  }

  /** Met dans cette ligne, du bon côté, ce qui manque pour équilibrer.

      C'est le geste le plus répété d'une saisie : le dernier montant est
      toujours celui qui solde. Le proposer évite une soustraction de tête
      à chaque écriture — et les erreurs qui vont avec. */
  function soldeRangee(tr, hors) {
    const ecart = montantQuiSolde(hors);
    if (!ecart || !tr) return false;
    const suffixe = hors ? '-hors' : '';
    const cible = `.l-${ecart > 0 ? 'credit' : 'debit'}${suffixe}`;
    const autre = `.l-${ecart > 0 ? 'debit' : 'credit'}${suffixe}`;
    $(autre, tr).value = '';
    $(cible, tr).value = pourChamp(Math.abs(ecart));
    recalcule();
    // Un montant sur une ligne sans compte ne s'enregistrerait pas : c'est
    // le compte qu'il faut aller chercher, pas le montant qu'il faut relire.
    const champ = $('.l-compte', tr).value.trim() ? $(cible, tr) : $('.l-compte', tr);
    champ.focus();
    if (champ.select) champ.select();
    return true;
  }

  /** La ligne où poser le montant qui solde : la dernière qui porte un
      compte sans montant, à défaut la dernière tout court. */
  function rangeeASolder(hors) {
    const suffixe = hors ? '-hors' : '';
    const libres = $$('tr', corps).filter((tr) =>
      !cts($(`.l-debit${suffixe}`, tr).value)
      && !cts($(`.l-credit${suffixe}`, tr).value));
    // D'abord une ligne qui porte déjà son compte : le montant y est utile
    // tout de suite. À défaut, la dernière — et on ira chercher son compte.
    return libres.filter((tr) => $('.l-compte', tr).value.trim()).pop()
      || libres.pop() || corps.lastElementChild;
  }

  /** Affiche un écart, ou la coche verte si la part s'équilibre.

      Le bouton « Solder » est un élément fixe du bandeau, seulement montré
      ou caché : recréé à chaque frappe, il disparaîtrait sous le clic —
      appuyer dessus déclenche d'abord la sortie du champ, donc un recalcul. */
  function afficheEcart(element, debit, credit, libelle, hors = false) {
    const bouton = $(hors ? '#solder-hors' : '#solder', conteneur);
    if (debit === credit && debit > 0) {
      element.innerHTML = `<span class="vert">✓ ${libelle} équilibré${libelle.endsWith('e') ? 'e' : ''}</span>`;
      bouton.hidden = true;
      return;
    }
    if (!debit && !credit) { element.textContent = ''; bouton.hidden = true; return; }
    const ecart = debit - credit;
    element.innerHTML = `<span class="rouge">${libelle} : il manque
      ${fm(Math.abs(ecart))} au ${ecart > 0 ? 'crédit' : 'débit'}</span>`;
    bouton.hidden = false;
    bouton.title = `Mettre ${fm(Math.abs(ecart))} au `
      + `${ecart > 0 ? 'crédit' : 'débit'} de la ligne libre.`;
  }

  function recalcule() {
    const brutes = lignesBrutes();
    const totalite = enTotalite();
    const somme = (champ) => brutes.reduce((s, l) => s + cts(l[champ]), 0);

    // Un montant sans compte ne partira pas : autant le dire pendant qu'on
    // regarde encore la ligne.
    brutes.forEach((l) => {
      const montant = cts(l.debit) || cts(l.credit)
        || cts(l.debit_hors) || cts(l.credit_hors);
      const champ = $('.l-compte', l.tr);
      if (montant && !l.compte) {
        champ.classList.add('invalide');
        champ.title = 'Un montant sans compte ne sera pas enregistré.';
      } else if (champ.title === 'Un montant sans compte ne sera pas enregistré.') {
        champ.classList.remove('invalide');
        champ.title = '';
      }
    });

    const d = somme('debit');
    const c = somme('credit');
    $('#tot-debit', conteneur).textContent = fm(d);
    $('#tot-credit', conteneur).textContent = fm(c);
    afficheEcart($('#ecart', conteneur), d, c,
                 totalite ? 'Part déclarée' : 'Écriture');

    if (!totalite) return;
    const dh = somme('debit_hors');
    const ch = somme('credit_hors');
    $('#tot-declare', conteneur).textContent = fm(d);
    $('#tot-hors', conteneur).textContent = fm(dh);
    $('#tot-operation', conteneur).textContent = fm(d + dh);
    afficheEcart($('#ecart-hors', conteneur), dh, ch, 'Part non déclarée', true);
  }

  /** Bascule entre saisie simple et saisie en totalité. */
  function appliqueMode() {
    const totalite = enTotalite();
    conteneur.classList.toggle('totalite', totalite);
    $('#note-totalite', conteneur).hidden = !totalite;
    $('#bandeau-totalite', conteneur).hidden = !totalite;
    $('#th-debit', conteneur).textContent = totalite ? 'Débit déclaré' : 'Débit';
    $('#th-credit', conteneur).textContent = totalite ? 'Crédit déclaré' : 'Crédit';
    recalcule();
  }

  (prefill.lignes || [{}, {}]).forEach(ajouteLigne);
  // Par défaut « opérations diverses » : les ventes et achats passent
  // normalement par la facturation, qui tient ses propres journaux.
  $('#e-journal', conteneur).value = prefill.journal
    || (journaux.journaux.some((j) => j.code === 'OD') ? 'OD' : journaux.journaux[0]?.code);
  $('#ajout-ligne', conteneur).onclick = () => ajouteLigne();
  $('#solder', conteneur).onclick = () => soldeRangee(rangeeASolder(false), false);
  $('#solder-hors', conteneur).onclick = () => soldeRangee(rangeeASolder(true), true);
  if (prefill.perimetre) {
    // Reprise d'une écriture ou d'un modèle : son périmètre fait foi, sinon
    // dupliquer une opération hors déclaration la rendrait déclarée.
    $('#e-perimetre', conteneur).value = prefill.perimetre;
  } else if (App.etat.perimetre && App.etat.perimetre !== 'tous') {
    $('#e-perimetre', conteneur).value = App.etat.perimetre;
  } else {
    // En vue réelle, la saisie en totalité est le mode qui correspond.
    $('#e-perimetre', conteneur).value = 'totalite';
  }
  $('#e-perimetre', conteneur).onchange = appliqueMode;
  appliqueMode();

  modale({
    titre: prefill.titre || 'Nouvelle écriture comptable',
    contenu: conteneur,
    large: true,
    boutons: [
      { libelle: 'Annuler' },
      ...(prefill.id ? [] : [{
        libelle: 'Garder comme modèle',
        action: () => { gardeModeleEcriture(conteneur, litLignes); return false; },
      }]),
      {
        libelle: prefill.id ? 'Enregistrer en brouillon' : 'Enregistrer en brouillon',
        action: () => enregistreEcriture(conteneur, litLignes, false, prefill),
      },
      {
        libelle: prefill.id ? 'Enregistrer et valider' : 'Valider', classe: 'primaire',
        action: () => enregistreEcriture(conteneur, litLignes, true, prefill),
      },
    ],
  });
}

async function enregistreEcriture(conteneur, litLignes, valider, prefill = {}) {
  const donnees = {
    journal: $('#e-journal', conteneur).value,
    date: $('#e-date', conteneur).value,
    piece: $('#e-piece', conteneur).value,
    libelle: $('#e-libelle', conteneur).value,
    perimetre: $('#e-perimetre', conteneur).value,
    lignes: litLignes(),
    valider,
  };
  // Modifier une écriture, c'est la même saisie : on écrit au même endroit,
  // sous le même numéro, plutôt que d'en créer une seconde.
  const reponse = prefill.id
    ? await envoie(`/api/ecritures/${prefill.id}`,
                   { ...donnees, devalider: true }, 'PUT')
    : await envoie('/api/ecritures', donnees);
  if (reponse && reponse.totaux) {
    const t = reponse.totaux;
    notifie(`Opération de ${fm(t.total)} enregistrée : ${fm(t.declare)} déclaré, `
          + `${fm(t.hors_declaration)} hors déclaration.`, 'succes', 6000);
  } else {
    notifie(reponse?.message || 'Écriture enregistrée.', 'succes',
            reponse?.message ? 7000 : 4000);
  }
  afficheRoute();
}

/**
 * Corriger une écriture déjà enregistrée.
 *
 * Elle se rouvre dans la grille de saisie, telle qu'elle est, et se
 * réenregistre sous le même numéro. Une écriture validée n'est pas figée
 * pour autant : on le dit, on la repasse en brouillon, et l'opération est
 * tracée. Ce que le logiciel ne fera pas dans son dos, c'est toucher à un
 * exercice clos ou à un rapprochement bancaire déjà arrêté.
 */
async function modifieEcriture(id) {
  let e;
  try { e = await api(`/api/ecritures/${id}`); }
  catch (err) { notifie(err.message, 'danger'); return; }
  // Ce que la correction entraîne, dit avant, sans faire la leçon.
  const suites = [];
  if (e.validee) {
    suites.push('Elle est validée : la corriger la repasse en brouillon, et '
      + 'l\'opération est inscrite au journal des opérations.');
  }
  if (e.source_type && e.source_type !== 'extourne') {
    suites.push(`Elle a été produite automatiquement (${ech(e.source_type)}) : `
      + 'la corriger ici ne change pas le document dont elle vient.');
  }
  if (e.operation_ref) {
    suites.push('Elle est la moitié d\'une opération saisie en totalité : '
      + 'l\'autre part, elle, ne bouge pas.');
  }
  if (suites.length && !await confirme(
      `Modifier l'écriture ${e.numero} ?`,
      suites.join(' ') + ' Vous pouvez aussi la laisser telle quelle et passer '
      + 'une extourne.', 'Modifier')) return;
  fermeModale();
  saisieEcriture({
    id,
    titre: `Modifier l'écriture ${e.numero}`,
    journal: e.journal,
    date: e.date,
    piece: e.piece || '',
    libelle: e.libelle,
    perimetre: e.perimetre,
    lignes: (e.lignes || []).map((l) => ({
      compte: l.compte, tiers_id: l.tiers_id, libelle: l.libelle,
      debit: l.debit, credit: l.credit,
    })),
  });
}

/* --------------------------------------------------------- Grand livre -- */

App.pages['comptabilite/grand-livre'] = {
  titre: 'Grand livre',
  async afficher(zone, route) {
    const p = route.parametres;
    actionsPage(`<button onclick="telecharge('/api/export/grand-livre', ${JSON.stringify(p).replace(/"/g, "'")})">Exporter</button>`);
    const d = await charge('/api/grand-livre', p);

    zone.innerHTML = `
      <div class="barre-outils">
        <label class="champ"><span>Du compte</span><input id="gl-debut" value="${ech(p.compte_debut || '')}" placeholder="411"></label>
        <label class="champ"><span>Au compte</span><input id="gl-fin" value="${ech(p.compte_fin || '')}" placeholder="411"></label>
        <label class="champ"><span>Du</span><input type="date" id="gl-du" value="${p.du || ''}"></label>
        <label class="champ"><span>Au</span><input type="date" id="gl-au" value="${p.au || ''}"></label>
        <label class="champ"><span><input type="checkbox" id="gl-nl" ${p.non_lettrees === '1' ? 'checked' : ''}> Non lettrées</span></label>
        <button onclick="filtreGrandLivre()">Afficher</button>
      </div>
      ${d.groupes.length ? d.groupes.map((g) => carte(
        `${g.compte} — ${g.intitule || ''}`,
        tableau([
          { titre: 'Date', rendu: (l) => fdate(l.date), largeur: '90px' },
          { titre: 'Jal', cle: 'journal', largeur: '46px' },
          { titre: 'N°', cle: 'num_ecriture', largeur: '104px' },
          { titre: 'Pièce', cle: 'piece', largeur: '104px' },
          { titre: 'Libellé', rendu: (l) => ech(l.libelle || l.libelle_ecriture) },
          { titre: 'Tiers', cle: 'tiers', largeur: '150px' },
          /* Largeurs fixes : le grand livre empile une carte par compte et
             des colonnes qui se décalent d'une carte à l'autre obligent à
             relire l'en-tête à chaque fois. */
          { titre: 'Débit', classe: 'num', largeur: '124px', rendu: (l) => l.debit ? fm(l.debit) : '' },
          { titre: 'Crédit', classe: 'num', largeur: '124px', rendu: (l) => l.credit ? fm(l.credit) : '' },
          { titre: 'Solde', classe: 'num solde', largeur: '130px', rendu: (l) => fmc(l.solde_progressif) },
          { titre: 'Let.', cle: 'lettrage', largeur: '48px' },
        ], g.lignes, {
          pied: [{ contenu: '<strong>Totaux</strong>' }, {}, {}, {}, {}, {},
            { contenu: `<strong>${fm(g.total_debit)}</strong>`, classe: 'num' },
            { contenu: `<strong>${fm(g.total_credit)}</strong>`, classe: 'num' },
            { contenu: `<strong>${fmc(g.solde)}</strong>`, classe: 'num solde' }, {}],
        }), '', true)).join('')
        : '<div class="vide"><span class="grand">📖</span>Aucun mouvement sur cette sélection.</div>'}`;
  },
};

function filtreGrandLivre() {
  const p = new URLSearchParams();
  const v = (id) => $(`#${id}`).value;
  if (v('gl-debut')) p.set('compte_debut', v('gl-debut'));
  if (v('gl-fin')) p.set('compte_fin', v('gl-fin'));
  if (v('gl-du')) p.set('du', v('gl-du'));
  if (v('gl-au')) p.set('au', v('gl-au'));
  if ($('#gl-nl').checked) p.set('non_lettrees', '1');
  navigue(`/comptabilite/grand-livre?${p}`);
}

/* ------------------------------------------------------------- Balance -- */

App.pages['comptabilite/balance'] = {
  titre: 'Balance générale',
  async afficher(zone, route) {
    const niveau = route.parametres.niveau || '';
    actionsPage(`<button onclick="telecharge('/api/export/balance')">Exporter Excel</button>
      <button onclick="window.print()">Imprimer</button>`);
    const d = await charge('/api/balance', { niveau, du: route.parametres.du, au: route.parametres.au });
    sousTitre(`Du ${fdate(d.du)} au ${fdate(d.au)}`);

    zone.innerHTML = `
      ${bandeauPerimetre(d.perimetre)}
      <div class="barre-outils">
        <label class="champ"><span>Regroupement</span><select id="b-niveau" onchange="navigue('/comptabilite/balance?niveau='+this.value)">
          <option value="">Compte détaillé</option>
          <option value="1" ${niveau === '1' ? 'selected' : ''}>Classe (1 chiffre)</option>
          <option value="2" ${niveau === '2' ? 'selected' : ''}>2 chiffres</option>
          <option value="3" ${niveau === '3' ? 'selected' : ''}>3 chiffres</option>
        </select></label>
      </div>
      ${d.equilibree ? '' : '<div class="message danger"><strong>Balance déséquilibrée</strong>Le total des débits diffère du total des crédits. Lancez le contrôle de cohérence.</div>'}
      ${carte('', tableau([
        { titre: 'Compte', cle: 'compte', largeur: '90px' },
        { titre: 'Intitulé', rendu: (l) => ech(l.intitule) },
        { titre: 'Report débit', classe: 'num', largeur: '128px', masquerSiVide: true,
          rendu: (l) => l.report_debit ? fm(l.report_debit) : '' },
        { titre: 'Report crédit', classe: 'num', largeur: '128px', masquerSiVide: true,
          rendu: (l) => l.report_credit ? fm(l.report_credit) : '' },
        { titre: 'Mvt débit', classe: 'num', largeur: '128px', rendu: (l) => l.debit ? fm(l.debit) : '' },
        { titre: 'Mvt crédit', classe: 'num', largeur: '128px', rendu: (l) => l.credit ? fm(l.credit) : '' },
        { titre: 'Solde débit', classe: 'num solde', largeur: '134px',
          rendu: (l) => l.solde_debit ? `<strong>${fm(l.solde_debit)}</strong>` : '' },
        { titre: 'Solde crédit', classe: 'num solde', largeur: '134px',
          rendu: (l) => l.solde_credit ? `<strong>${fm(l.solde_credit)}</strong>` : '' },
      ], d.lignes, {
        icone: '⚖️', messageVide: 'Aucun mouvement comptable sur la période.',
        coupure: niveau === '1' ? null : (l) => classeScf(l.compte),
        pied: [{ contenu: '<strong>TOTAUX</strong>' }, {},
          { contenu: fm(d.totaux.report_debit), classe: 'num' },
          { contenu: fm(d.totaux.report_credit), classe: 'num' },
          { contenu: fm(d.totaux.debit), classe: 'num' },
          { contenu: fm(d.totaux.credit), classe: 'num' },
          { contenu: fm(d.totaux.solde_debit), classe: 'num' },
          { contenu: fm(d.totaux.solde_credit), classe: 'num' }],
      }), '', true)}`;
  },
};

/* ------------------------------------------------------------ Lettrage -- */

App.pages['comptabilite/lettrage'] = {
  titre: 'Lettrage des comptes de tiers',
  async afficher(zone, route) {
    const compte = route.parametres.compte || '411';
    const etat = route.parametres.etat || 'non_lettre';
    const d = await charge('/api/lettrage', { compte, etat, tiers: route.parametres.tiers });
    actionsPage(`<button onclick="lettrageAuto('${compte}')">Lettrage automatique</button>`);

    zone.innerHTML = `
      <div class="message info">Sélectionnez les lignes qui se compensent (facture et son règlement),
        puis lettrez-les. Le total des débits doit égaler le total des crédits.</div>
      <div class="barre-outils">
        <label class="champ"><span>Compte</span>
          <input id="l-compte" value="${ech(compte)}" placeholder="411"></label>
        <label class="champ"><span>État</span><select id="l-etat">
          <option value="non_lettre" ${etat === 'non_lettre' ? 'selected' : ''}>Non lettrées</option>
          <option value="lettre" ${etat === 'lettre' ? 'selected' : ''}>Lettrées</option>
          <option value="" ${etat === '' ? 'selected' : ''}>Toutes</option>
        </select></label>
        <button onclick="navigue('/comptabilite/lettrage?compte='+$('#l-compte').value+'&etat='+$('#l-etat').value)">Afficher</button>
      </div>
      ${carte('', tableau([
        { titre: '', classe: 'centre', rendu: (l) => `<input type="checkbox" data-l="${l.id}" data-d="${l.debit}" data-c="${l.credit}" onchange="majSelectionLettrage()">` },
        { titre: 'Date', rendu: (l) => fdate(l.date) },
        { titre: 'Jal', cle: 'journal' },
        { titre: 'N°', cle: 'num_ecriture' },
        { titre: 'Tiers', cle: 'tiers' },
        { titre: 'Libellé', rendu: (l) => ech(l.libelle || l.libelle_ecriture) },
        { titre: 'Échéance', rendu: (l) => fdate(l.echeance) },
        { titre: 'Débit', classe: 'num', rendu: (l) => l.debit ? fm(l.debit) : '' },
        { titre: 'Crédit', classe: 'num', rendu: (l) => l.credit ? fm(l.credit) : '' },
        { titre: 'Lettr.', rendu: (l) => l.lettrage ? `<span class="etiquette info">${ech(l.lettrage)}</span>` : '' },
      ], d.lignes, { messageVide: 'Aucune ligne à lettrer sur ce compte.' }),
        `<span id="resume-lettrage" class="petit"></span>
         <button class="primaire" onclick="lettreSelection()">Lettrer la sélection</button>
         <button onclick="delettreSelection()">Délettrer</button>`, true)}`;
  },
};

function majSelectionLettrage() {
  const cochees = $$('[data-l]').filter((c) => c.checked);
  const d = cochees.reduce((s, c) => s + Number(c.dataset.d), 0);
  const c = cochees.reduce((s, x) => s + Number(x.dataset.c), 0);
  const resume = $('#resume-lettrage');
  if (!resume) return;
  resume.innerHTML = cochees.length
    ? `${cochees.length} ligne(s) — débit ${fm(d)} / crédit ${fm(c)} —
       ${d === c ? '<span class="vert">équilibré</span>' : `<span class="rouge">écart ${fm(Math.abs(d - c))}</span>`}`
    : '';
}

async function lettreSelection() {
  const lignes = $$('[data-l]').filter((c) => c.checked).map((c) => +c.dataset.l);
  try {
    const r = await envoie('/api/lettrage', { lignes });
    notifie(`Lettrage ${r.code} appliqué à ${r.lignes} ligne(s).`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function delettreSelection() {
  const lignes = $$('[data-l]').filter((c) => c.checked).map((c) => +c.dataset.l);
  try {
    await envoie('/api/delettrage', { lignes });
    notifie('Lignes délettrées.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function lettrageAuto(compte) {
  try {
    const r = await envoie('/api/lettrage/automatique', { compte });
    notifie(`${r.apparies} rapprochement(s) automatique(s).`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* --------------------------------------------------- États financiers --- */

App.pages['comptabilite/etats'] = {
  titre: 'États financiers',
  async afficher(zone, route) {
    const onglet = route.parametres.vue || 'bilan';
    actionsPage(`<button onclick="telecharge('/api/export/etats-financiers')">Exporter la liasse</button>
      <button onclick="window.print()">Imprimer</button>`);

    zone.innerHTML = `<div class="onglets">
      ${[['bilan', 'Bilan'], ['tcr', 'Compte de résultat'], ['flux', 'Flux de trésorerie']]
        .map(([v, l]) => `<button class="${v === onglet ? 'actif' : ''}" onclick="navigue('/comptabilite/etats?vue=${v}')">${l}</button>`).join('')}
      </div><div id="zone-etat"><div class="vide">Chargement…</div></div>`;

    if (onglet === 'bilan') await afficheBilan($('#zone-etat'));
    else if (onglet === 'tcr') await afficheTcr($('#zone-etat'));
    else await afficheFlux($('#zone-etat'));
  },
};

async function afficheBilan(zone) {
  const d = await charge('/api/etats/bilan');
  const section = (s) => `
    <tr class="groupe"><td colspan="2">${ech(s.titre)}</td></tr>
    ${s.lignes.map((l) => `<tr><td>${ech(l.libelle)}</td><td class="num">${fm(l.montant)}</td></tr>`).join('')}
    <tr class="sous-total"><td>Total ${ech(s.titre.toLowerCase())}</td><td class="num">${fm(s.total)}</td></tr>`;

  zone.innerHTML = `
    ${bandeauPerimetre(d.perimetre, d.perimetre === 'declare'
      ? "Ce bilan correspond à ce qui est déposé à l'administration."
      : (d.perimetre === 'tous' ? "Vue de gestion : déclaré et hors déclaration confondus." : ''))}
    ${d.equilibre ? '' : `<div class="message danger"><strong>Bilan déséquilibré</strong>
      Écart de ${fm(d.ecart, true)} entre l'actif et le passif.</div>`}
    <div class="grille c2">
      ${carte('ACTIF', `<div class="enveloppe-table"><table class="donnees">
        <thead><tr><th>Rubrique</th><th class="num">Montant net</th></tr></thead>
        <tbody>${d.actif.map(section).join('')}
        <tr class="total"><td>TOTAL GÉNÉRAL ACTIF</td><td class="num">${fm(d.total_actif)}</td></tr>
        </tbody></table></div>`, '', true)}
      ${carte('PASSIF', `<div class="enveloppe-table"><table class="donnees">
        <thead><tr><th>Rubrique</th><th class="num">Montant</th></tr></thead>
        <tbody>${d.passif.map(section).join('')}
        <tr class="total"><td>TOTAL GÉNÉRAL PASSIF</td><td class="num">${fm(d.total_passif)}</td></tr>
        </tbody></table></div>`, '', true)}
    </div>`;
}

async function afficheTcr(zone) {
  const d = await charge('/api/etats/tcr');
  zone.innerHTML = bandeauPerimetre(d.perimetre)
    + carte(`Compte de résultat par nature — exercice ${d.exercice.libelle}`, `
    <div class="enveloppe-table"><table class="donnees">
      <thead><tr><th>Libellé</th><th class="num">Montant</th></tr></thead>
      <tbody>${d.lignes.map((l) => {
        const classe = l.genre === 'solde' ? 'total' : (l.genre === 'total' ? 'sous-total' : '');
        return `<tr class="${classe}"><td>${ech(l.libelle)}</td>
                <td class="num">${fm(l.montant)}</td></tr>`;
      }).join('')}</tbody></table></div>`, '', true)
    + `<div class="grille c4">
      ${indicateur('Valeur ajoutée', fm(d.valeur_ajoutee, true))}
      ${indicateur('Excédent brut d\'exploitation', fm(d.ebe, true))}
      ${indicateur('Résultat opérationnel', fm(d.resultat_operationnel, true))}
      ${indicateur('Résultat net', fm(d.resultat_net, true), '',
        d.resultat_net >= 0 ? 'succes' : 'danger')}
    </div>`;
}

async function afficheFlux(zone) {
  const d = await charge('/api/etats/flux');
  const l = (libelle, valeur, gras = false) =>
    `<tr class="${gras ? 'total' : ''}"><td>${libelle}</td><td class="num">${fm(valeur)}</td></tr>`;
  zone.innerHTML = carte('Tableau des flux de trésorerie (méthode indirecte)', `
    <div class="enveloppe-table"><table class="donnees">
      <thead><tr><th>Libellé</th><th class="num">Montant</th></tr></thead><tbody>
      <tr class="groupe"><td colspan="2">Flux des activités opérationnelles</td></tr>
      ${l('Résultat net de l\'exercice', d.resultat_net)}
      ${l('+ Dotations aux amortissements et pertes de valeur', d.dotations)}
      ${l('Variation des stocks et en-cours', d.variation_stocks)}
      ${l('Variation des créances clients', d.variation_clients)}
      ${l('Variation des dettes fournisseurs', d.variation_fournisseurs)}
      ${l('Variation des dettes de personnel et sociales', d.variation_personnel)}
      ${l('Variation des dettes et créances fiscales', d.variation_fiscal)}
      ${l('Variation des autres comptes de tiers', d.variation_autres_tiers)}
      ${l('FLUX NET DES ACTIVITÉS OPÉRATIONNELLES', d.flux_exploitation, true)}
      <tr class="groupe"><td colspan="2">Flux des activités d'investissement</td></tr>
      ${l('Acquisitions d\'immobilisations', d.acquisitions_immobilisations)}
      ${l('Immobilisations financières', d.immobilisations_financieres)}
      ${l('FLUX NET DES ACTIVITÉS D\'INVESTISSEMENT', d.flux_investissement, true)}
      <tr class="groupe"><td colspan="2">Flux des activités de financement</td></tr>
      ${l('Variation des capitaux propres', d.variation_capitaux_propres)}
      ${l('Variation des subventions et provisions', d.variation_subventions_provisions)}
      ${l('Variation des emprunts', d.variation_emprunts)}
      ${l('FLUX NET DES ACTIVITÉS DE FINANCEMENT', d.flux_financement, true)}
      ${l('VARIATION DE TRÉSORERIE DE LA PÉRIODE', d.variation_tresorerie, true)}
      ${l('Trésorerie à l\'ouverture', d.tresorerie_ouverture)}
      ${l('Trésorerie à la clôture', d.tresorerie_cloture, true)}
      </tbody></table></div>
    ${d.controle === 0 ? '<div class="message succes">Le tableau s\'articule exactement avec la variation de trésorerie.</div>'
      : `<div class="message danger">Écart d'articulation : ${fm(d.controle, true)}</div>`}`, '', true);
}

/* ------------------------------------------------------------- Clôture -- */

App.pages['comptabilite/cloture'] = {
  titre: 'Contrôles et clôture d\'exercice',
  async afficher(zone) {
    const ex = App.etat.exercice;
    const d = await api(`/api/exercices/${ex.id}/controles`);
    const exercices = App.etat.exercices.filter((e) => e.id !== ex.id && !e.cloture);

    const genres = { bloquant: 'danger', avertissement: 'alerte', info: 'info' };
    zone.innerHTML = `
      <div class="grille c3" style="margin-bottom:16px">
        ${indicateur('Exercice', ex.libelle, `${fdate(ex.date_debut)} → ${fdate(ex.date_fin)}`)}
        ${indicateur('Résultat calculé', fm(d.resultat, true), '',
          d.resultat >= 0 ? 'succes' : 'danger')}
        ${indicateur('Anomalies bloquantes', d.bloquants, d.bloquants ? 'à corriger avant clôture' : 'aucune',
          d.bloquants ? 'danger' : 'succes')}
      </div>

      ${carte('Contrôles de cohérence', d.anomalies.length
        ? d.anomalies.map((a) => `<div class="message ${genres[a.gravite]}">
            <strong>${ech(a.message)}</strong>${a.detail ? ech(a.detail) : ''}
            ${a.lien ? `<div><a href="${a.lien}">Ouvrir</a></div>` : ''}</div>`).join('')
        : '<div class="message succes"><strong>Tous les contrôles sont au vert.</strong>La comptabilité est cohérente : vous pouvez clôturer.</div>')}

      ${ex.cloture ? '<div class="message info">Cet exercice est déjà clôturé.</div>' : carte('Clôturer l\'exercice', `
        <div class="message alerte"><strong>Opération importante</strong>
          La clôture solde les comptes de charges et de produits, vire le résultat au compte 120/129,
          génère les à-nouveaux sur l'exercice suivant et verrouille toute saisie sur ${ech(ex.libelle)}.</div>
        <label class="champ" style="max-width:340px"><span>Reporter les à-nouveaux sur</span>
          <select id="ex-suivant"><option value="">Ne pas générer d'à-nouveaux</option>
          ${exercices.map((e) => `<option value="${e.id}">${ech(e.libelle)}</option>`).join('')}</select></label>
        ${exercices.length ? '' : '<div class="aide">Aucun exercice suivant ouvert. Créez-le dans Paramètres > Exercices.</div>'}`,
        `<button class="primaire" onclick="lanceCloture(${ex.id})" ${d.bloquants ? 'disabled' : ''}>Clôturer l'exercice</button>`)}`;
  },
};

async function lanceCloture(id) {
  const suivant = $('#ex-suivant')?.value;
  if (!await confirme('Clôturer l\'exercice ?',
    'Cette opération est difficilement réversible. Une sauvegarde préalable est recommandée.',
    'Clôturer')) return;
  try {
    const r = await api(`/api/exercices/${id}/cloturer`, {
      method: 'POST', corps: { exercice_suivant: suivant || null },
    });
    notifie(r.message, 'succes', 8000);
    await chargeSocietes();
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* --------------------------------------------------------- Facturation -- */

App.pages.factures = {
  titre: 'Factures',
  async afficher(zone, route) {
    if (route.segments[1]) return ficheFacture(zone, route.segments[1]);
    const sens = route.parametres.sens || 'vente';
    const filtres = { sens, statut: route.parametres.statut, q: route.parametres.q };
    // L'import ne concerne que les vraies factures : un avoir se crée depuis
    // la facture d'origine, une proforma n'a pas de valeur comptable.
    // Apostrophe typographique : celle du clavier fermerait la chaîne du
    // gestionnaire onclick.
    const IMPORTABLES = {
      vente: ['factures_vente', 'Importer des factures de vente'],
      achat: ['factures_achat', "Importer des factures d'achat"],
    };
    const importable = IMPORTABLES[sens];
    const argsExport = JSON.stringify(filtres).replace(/"/g, "'");
    actionsPage(
      `<button class="primaire" onclick="editeFacture(null,'${sens}')">+ Facture</button>`
      + (importable ? boutonImport(importable[0], importable[1]) : '')
      + `<button onclick="telecharge('/api/export/factures', ${argsExport})">Exporter</button>`);
    const d = await charge('/api/factures', filtres);

    zone.innerHTML = `
      <div class="barre-outils">
        <label class="champ recherche"><span>Rechercher</span>
          <input id="f-q" value="${ech(route.parametres.q || '')}" placeholder="N°, objet, client…"></label>
        <label class="champ"><span>Type</span><select id="f-sens" onchange="navigue('/factures?sens='+this.value)">
          ${[['vente', 'Factures de vente'], ['achat', 'Factures d\'achat'],
            ['avoir_vente', 'Avoirs clients'], ['avoir_achat', 'Avoirs fournisseurs'],
            ['proforma', 'Proforma']].map(([v, l]) =>
            `<option value="${v}" ${v === sens ? 'selected' : ''}>${l}</option>`).join('')}
        </select></label>
      </div>
      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Total HT', fm(d.totaux.ht, true))}
        ${indicateur('TVA', fm(d.totaux.tva, true))}
        ${indicateur('Total TTC', fm(d.totaux.ttc, true))}
        ${indicateur('Reste à encaisser', fm(d.totaux.reste, true), '',
          d.totaux.reste > 0 ? 'danger' : 'succes')}
      </div>
      ${carte('', tableau([
        { titre: 'N°', cle: 'numero', largeur: '110px' },
        { titre: 'Date', rendu: (f) => fdate(f.date) },
        { titre: 'Tiers', rendu: (f) => ech(f.tiers_nom || '') },
        { titre: 'Objet', rendu: (f) => `<div class="tronque">${ech(f.objet || '')}</div>` },
        { titre: 'HT', classe: 'num', rendu: (f) => fm(f.montant_ht) },
        { titre: 'TVA', classe: 'num', rendu: (f) => fm(f.montant_tva) },
        { titre: 'Net à payer', classe: 'num', rendu: (f) => `<strong>${fm(f.net_a_payer)}</strong>` },
        { titre: 'Réglé', classe: 'num', rendu: (f) => fm(f.montant_regle) },
        { titre: 'Statut', rendu: (f) => etiquette(f.statut) },
        { titre: 'Périmètre', rendu: (f) => badgePerimetre(f.perimetre) },
      ], d.factures, {
        clic: true, icone: '🧾', messageVide: 'Aucune facture.',
        attributsLigne: (f) => `onclick="navigue('/factures/${f.id}')"`,
      }), '', true)}`;

    $('#f-q').onkeydown = (e) => {
      if (e.key === 'Enter') navigue(`/factures?sens=${sens}&q=${encodeURIComponent(e.target.value)}`);
    };
  },
};

async function ficheFacture(zone, id) {
  const f = await api(`/api/factures/${id}`);
  $('#titre-page').textContent = `Facture ${f.numero}`;
  sousTitre(`${f.tiers?.raison_sociale || ''} — ${fdate(f.date)}`);
  actionsPage(`
    <button onclick="window.open('/api/factures/${id}/impression','_blank')">Imprimer</button>
    ${f.statut === 'brouillon' ? `<button onclick="editeFacture(${id})">Modifier</button>
      <button class="primaire" onclick="valideFacture(${id})">Valider</button>` : ''}
    ${f.statut === 'validee' || f.statut === 'partielle' ? `<button class="primaire" onclick="regleFacture(${id})">Encaisser</button>` : ''}
    ${f.statut !== 'brouillon' && f.statut !== 'annulee' ? `<button onclick="creeAvoir(${id})">Avoir</button>` : ''}
    <a class="bouton" href="#/factures?sens=${f.sens}">Retour</a>`);

  zone.innerHTML = `
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Total HT', fm(f.montant_ht, true))}
      ${indicateur('TVA', fm(f.montant_tva, true))}
      ${indicateur('Net à payer', fm(f.net_a_payer, true), f.timbre ? `dont timbre ${fm(f.timbre)}` : '', 'accent')}
      ${indicateur('Reste dû', fm(f.net_a_payer - f.montant_regle, true), etiquette(f.statut),
        f.net_a_payer - f.montant_regle > 0 ? 'danger' : 'succes')}
    </div>
    ${f.montant_hors ? `<div class="grille c3" style="margin-bottom:16px">
      ${indicateur('Facturé (déclaré)', fm(f.net_a_payer, true),
        `réglé ${fm(f.montant_regle)} — reste ${fm(f.reste_declare)}`)}
      ${indicateur('Non déclaré', fm(f.montant_hors, true),
        `réglé ${fm(f.montant_hors_regle)} — reste ${fm(f.reste_hors)}`,
        f.reste_hors > 0 ? 'attention' : 'succes')}
      ${indicateur('Prix réel', fm(f.prix_reel, true),
        f.reste_total > 0 ? `reste dû ${fm(f.reste_total)} en tout`
          : 'intégralement réglé', 'accent')}
    </div>` : ''}
    ${carte('Lignes', tableau([
      { titre: 'Désignation', rendu: (l) => ech(l.designation) },
      { titre: 'Qté', classe: 'num', rendu: (l) => (l.quantite / 1000).toFixed(2) },
      { titre: 'P.U. HT', classe: 'num', rendu: (l) => fm(l.prix_unitaire) },
      { titre: 'Remise', classe: 'num', rendu: (l) => l.remise_taux ? ft(l.remise_taux) + ' %' : '' },
      { titre: 'TVA', classe: 'num', rendu: (l) => ft(l.taux_tva) + ' %' },
      { titre: 'Compte', cle: 'compte' },
      { titre: 'Montant HT', classe: 'num', rendu: (l) => fm(l.montant_ht) },
    ], f.lignes), '', true)}
    ${f.reglements.length ? carte('Règlements', tableau([
      { titre: 'Date', rendu: (r) => fdate(r.date) },
      { titre: 'Part', masquerSiVide: true,
        rendu: (r) => r.part === 'hors_declaration'
          ? badgePerimetre('hors_declaration') : '' },
      { titre: 'Mode', cle: 'mode' },
      { titre: 'Compte', cle: 'compte_tresorerie' },
      { titre: 'Référence', cle: 'reference' },
      { titre: 'Montant', classe: 'num', rendu: (r) => fm(r.montant) },
    ], f.reglements), '', true) : ''}
    ${f.ecriture ? carte('Écriture comptable générée',
      `<div class="rangee"><span>${ech(f.ecriture.journal)} — ${ech(f.ecriture.numero)} du ${fdate(f.ecriture.date)}</span>
       <button class="petit-bouton" onclick="detailEcriture(${f.ecriture_id})">Voir le détail</button></div>
       ${f.ecriture_hors ? `<div class="rangee" style="margin-top:8px">
         <span>${badgePerimetre('hors_declaration')} ${ech(f.ecriture_hors.journal)} — ${ech(f.ecriture_hors.numero)} du ${fdate(f.ecriture_hors.date)}</span>
         <button class="petit-bouton" onclick="detailEcriture(${f.ecriture_hors_id})">Voir le détail</button></div>` : ''}`) : ''}`;
}

const COMPTES_PRODUIT = [
  ['7061', '7061 — Commissions sur ventes immobilières'],
  ['7062', '7062 — Honoraires d\'entremise location'],
  ['7063', '7063 — Honoraires de gestion locative'],
  ['7064', '7064 — Honoraires d\'expertise'],
  ['7065', '7065 — Frais de dossier'],
  ['7011', '7011 — Ventes de logements'],
  ['7012', '7012 — Ventes de locaux commerciaux'],
  ['704', '704 — Ventes de travaux'],
  ['708', '708 — Produits des activités annexes'],
];

async function editeFacture(id, sens = 'vente') {
  const existante = id ? await api(`/api/factures/${id}`) : null;
  if (existante) sens = existante.sens;
  const achat = sens.includes('achat');
  const [tiersOptions, comptes, tresoreries] = await Promise.all([
    optionsTiers(achat ? 'fournisseur' : 'client'),
    achat ? optionsComptes('6') : Promise.resolve(COMPTES_PRODUIT),
    optionsTresorerie(),
  ]);

  const conteneur = document.createElement('div');
  conteneur.innerHTML = `
    <div class="ligne-champs">
      <label class="champ"><span>${achat ? 'Fournisseur' : 'Client'} *</span>
        <select id="f-tiers">${tiersOptions.map(([v, l]) =>
          `<option value="${v}" ${existante?.tiers_id === v ? 'selected' : ''}>${ech(l)}</option>`).join('')}</select></label>
      ${achat ? `<label class="champ"><span>N° de la facture fournisseur *</span>
        <input id="f-numero" value="${ech(existante?.numero || '')}"></label>` : ''}
      <label class="champ"><span>Date *</span><input type="date" id="f-date" value="${existante?.date || aujourdhui()}"></label>
      <label class="champ"><span>Échéance</span><input type="date" id="f-echeance" value="${existante?.date_echeance || ''}"></label>
      <label class="champ"><span>Mode de règlement</span><select id="f-mode">
        <option value="">—</option>
        ${[['virement', 'Virement'], ['cheque', 'Chèque'], ['espece', 'Espèces'],
           ['traite', 'Traite'], ['mixte', 'Chèque + espèces']]
          .map(([v, l]) => `<option value="${v}" ${existante?.mode_reglement === v ? 'selected' : ''}>${l}</option>`).join('')}
      </select><div class="aide">Espèces : le droit de timbre est ajouté automatiquement.</div></label>
      <label class="champ" id="f-bloc-espece" hidden><span>dont espèces</span>
        <input class="num" id="f-espece" value="${existante?.montant_espece ? pourChamp(existante.montant_espece) : ''}">
        <div class="aide">Le droit de timbre ne porte que sur cette part.</div></label>
      <label class="champ"><span>Périmètre</span><select id="f-perimetre">
        <option value="declare">Déclaré</option>
        <option value="hors_declaration">Hors déclaration</option>
        <option value="totalite">Déclaré + non déclaré</option>
      </select></label>
      <label class="champ" style="grid-column:1/-1"><span>Objet</span>
        <input id="f-objet" value="${ech(existante?.objet || '')}"></label>
    </div>
    <table class="saisie"><thead><tr>
      <th style="width:34%">Désignation</th><th style="width:9%">Qté</th>
      <th style="width:15%">P.U. HT</th><th style="width:9%">Remise %</th>
      <th style="width:9%">TVA %</th><th style="width:18%">Compte</th><th class="num">HT</th><th></th>
    </tr></thead><tbody id="f-lignes"></tbody></table>
    <div class="rangee" style="margin-top:8px"><button class="petit-bouton" id="f-ajout">+ Ligne</button></div>
    <div class="bandeau-equilibre">
      <span>Total HT <strong id="f-ht">0,00</strong></span>
      <span>TVA <strong id="f-tva">0,00</strong></span>
      <span>Total TTC <strong id="f-ttc">0,00</strong></span>
    </div>
    <div id="f-bloc-hors" hidden>
      <p class="message info">
        <strong>Part non déclarée</strong>
        Elle n'apparaît pas sur la facture remise au ${achat ? 'fournisseur' : 'client'} :
        une pièce qui la porte vous met en cause. Elle est enregistrée à part,
        sans TVA ni droit de timbre, et suivie comme une créance : vous voyez
        à tout moment ce qui en a été payé et ce qui reste dû.
      </p>
      <div class="ligne-champs">
        <label class="champ"><span>Montant</span>
          <input class="num" id="f-hors-montant" value="${existante?.montant_hors ? pourChamp(existante.montant_hors) : ''}"></label>
        <label class="champ"><span>Compte de ${achat ? 'charge' : 'produit'}</span>
          <select id="f-hors-compte">${comptes.map(([v, l]) =>
            `<option value="${ech(v)}">${ech(l)}</option>`).join('')}</select>
          <div class="aide">Par défaut, celui de la première ligne.</div></label>
        <label class="champ"><span>Déjà encaissée sur</span>
          <select id="f-hors-tresorerie"><option value="">— pas encore réglée</option>${tresoreries.map(([v, l]) =>
            `<option value="${v}">${ech(l)}</option>`).join('')}</select>
          <div class="aide">Laissez vide si le ${achat ? 'fournisseur' : 'client'}
            n'a pas encore payé : la somme reste due, et se solde plus tard
            depuis « Encaisser ».</div></label>
      </div>
      <div class="bandeau-equilibre">
        <span>Facturé (déclaré) <strong id="f-recap-declare">0,00</strong></span>
        <span>Non déclaré <strong id="f-recap-hors">0,00</strong></span>
        <span>Prix réel <strong id="f-recap-total">0,00</strong></span>
      </div>
    </div>`;

  const corps = $('#f-lignes', conteneur);
  const optionsHtml = comptes.map(([v, l]) => `<option value="${ech(v)}">${ech(l)}</option>`).join('');

  function ajouteLigne(l = {}) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input class="d-designation" value="${ech(l.designation || '')}"></td>
      <td><input class="d-qte num" value="${l.quantite ? (l.quantite / 1000) : 1}"></td>
      <td><input class="d-pu num" value="${l.prix_unitaire ? pourChamp(l.prix_unitaire) : ''}"></td>
      <td><input class="d-remise num" value="${l.remise_taux ? ft(l.remise_taux) : ''}"></td>
      <td><input class="d-tva num" value="${l.taux_tva !== undefined ? ft(l.taux_tva) : 19}"></td>
      <td><select class="d-compte">${optionsHtml}</select></td>
      <td class="num d-total">0,00</td>
      <td><button class="plat petit-bouton">✕</button></td>`;
    if (l.compte) $('.d-compte', tr).value = l.compte;
    $('button', tr).onclick = () => { tr.remove(); recalcule(); };
    $$('input, select', tr).forEach((el) => { el.oninput = recalcule; });
    corps.appendChild(tr);
  }

  function litLignes() {
    return $$('tr', corps).map((tr) => ({
      designation: $('.d-designation', tr).value,
      quantite: parseFloat(String($('.d-qte', tr).value).replace(',', '.')) || 0,
      prix_unitaire: $('.d-pu', tr).value,
      remise_taux: $('.d-remise', tr).value,
      taux_tva: $('.d-tva', tr).value,
      compte: $('.d-compte', tr).value,
    })).filter((l) => l.designation);
  }

  function recalcule() {
    let ht = 0, tva = 0;
    $$('tr', corps).forEach((tr) => {
      const qte = parseFloat(String($('.d-qte', tr).value).replace(',', '.')) || 0;
      const pu = cts($('.d-pu', tr).value);
      const remise = parseFloat(String($('.d-remise', tr).value).replace(',', '.')) || 0;
      const tauxTva = parseFloat(String($('.d-tva', tr).value).replace(',', '.')) || 0;
      const brut = Math.round(pu * qte);
      const net = brut - Math.round(brut * remise / 100);
      const t = Math.round(net * tauxTva / 100);
      $('.d-total', tr).textContent = fm(net);
      ht += net; tva += t;
    });
    $('#f-ht', conteneur).textContent = fm(ht);
    $('#f-tva', conteneur).textContent = fm(tva);
    $('#f-ttc', conteneur).textContent = fm(ht + tva);
    suitLePremierCompte();
    recapitule(ht + tva);
  }

  /* Une vente de logement reste une vente de logement, déclarée ou non : le
     compte de la part non déclarée suit celui de la première ligne — jusqu'à
     ce qu'il en choisisse un autre, et alors on ne le lui reprend plus. */
  let compteHorsChoisi = Boolean(existante?.compte_hors);
  function suitLePremierCompte() {
    if (compteHorsChoisi) return;
    const premier = $$('tr', corps).map((tr) => $('.d-compte', tr).value)
      .find(Boolean);
    const champ = $('#f-hors-compte', conteneur);
    if (premier && champ && champ.value !== premier) champ.value = premier;
  }

  /** Les trois chiffres de la vente : ce qui est facturé, ce qui est encaissé
      à côté, et le prix réellement convenu — celui qui doit tomber juste. */
  function recapitule(ttc) {
    const hors = cts($('#f-hors-montant', conteneur).value);
    $('#f-recap-declare', conteneur).textContent = fm(ttc);
    $('#f-recap-hors', conteneur).textContent = fm(hors);
    $('#f-recap-total', conteneur).textContent = fm(ttc + hors);
  }

  /** Le bloc « part non déclarée » ne s'ouvre que si la vente en porte une ;
      le champ « dont espèces » que si le client paie en deux fois. */
  function appliqueModes() {
    const totalite = $('#f-perimetre', conteneur).value === 'totalite';
    $('#f-bloc-hors', conteneur).hidden = !totalite;
    $('#f-bloc-espece', conteneur).hidden = $('#f-mode', conteneur).value !== 'mixte';
    if (!totalite) $('#f-hors-montant', conteneur).value = '';
    recalcule();
  }

  (existante?.lignes?.length ? existante.lignes : [{}]).forEach(ajouteLigne);
  // Une facture déclarée qui porte une part encaissée à côté se rouvre sur
  // le choix qui la décrit, pas sur « Déclaré » tout court.
  $('#f-perimetre', conteneur).value = existante?.montant_hors ? 'totalite'
    : (existante?.perimetre
       || (App.etat.perimetre !== 'tous' ? App.etat.perimetre : 'declare'));
  if (existante?.compte_hors) $('#f-hors-compte', conteneur).value = existante.compte_hors;
  if (existante?.tresorerie_hors_id) {
    $('#f-hors-tresorerie', conteneur).value = existante.tresorerie_hors_id;
  }
  $('#f-ajout', conteneur).onclick = () => ajouteLigne();
  $('#f-perimetre', conteneur).onchange = appliqueModes;
  $('#f-mode', conteneur).onchange = appliqueModes;
  $('#f-hors-montant', conteneur).oninput = recalcule;
  $('#f-hors-compte', conteneur).onchange = () => { compteHorsChoisi = true; };
  appliqueModes();

  const collecte = () => ({
    sens,
    numero: $('#f-numero', conteneur)?.value,
    tiers_id: $('#f-tiers', conteneur).value,
    date: $('#f-date', conteneur).value,
    date_echeance: $('#f-echeance', conteneur).value,
    mode_reglement: $('#f-mode', conteneur).value,
    montant_espece: $('#f-espece', conteneur).value,
    objet: $('#f-objet', conteneur).value,
    perimetre: $('#f-perimetre', conteneur).value,
    montant_hors: $('#f-perimetre', conteneur).value === 'totalite'
      ? $('#f-hors-montant', conteneur).value : '',
    compte_hors: $('#f-hors-compte', conteneur).value,
    tresorerie_hors_id: $('#f-hors-tresorerie', conteneur).value,
    lignes: litLignes(),
  });

  modale({
    titre: id ? `Modifier la facture ${existante.numero}` : `Nouvelle facture ${achat ? 'd\'achat' : 'de vente'}`,
    contenu: conteneur, large: true,
    boutons: [
      { libelle: 'Annuler' },
      {
        libelle: 'Enregistrer',
        action: async () => {
          const r = id ? await envoie(`/api/factures/${id}`, collecte(), 'PUT')
            : await envoie('/api/factures', collecte());
          notifie('Facture enregistrée en brouillon.', 'succes');
          if (!id && r.id) navigue(`/factures/${r.id}`); else afficheRoute();
        },
      },
      {
        libelle: 'Enregistrer et valider', classe: 'primaire',
        action: async () => {
          const donnees = { ...collecte(), valider: true };
          const r = id ? await envoie(`/api/factures/${id}`, donnees, 'PUT')
            : await envoie('/api/factures', donnees);
          notifie('Facture validée et comptabilisée.', 'succes');
          if (!id && r.id) navigue(`/factures/${r.id}`); else afficheRoute();
        },
      },
    ],
  });
}

async function valideFacture(id) {
  try {
    await api(`/api/factures/${id}/valider`, { method: 'POST', corps: {} });
    notifie('Facture validée : l\'écriture comptable a été générée.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function creeAvoir(id) {
  const champs = [
    { nom: 'date', libelle: 'Date de l\'avoir', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'motif', libelle: 'Motif', large: true },
  ];
  modale({
    titre: 'Établir un avoir',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Créer l\'avoir', classe: 'primaire',
      action: async (r) => {
        const d = await api(`/api/factures/${id}/avoir`, { method: 'POST', corps: litFormulaire(r, champs) });
        notifie(`Avoir ${d.numero} créé.`, 'succes');
        navigue(`/factures/${d.id}`);
      },
    }],
  });
}

async function regleFacture(id) {
  const f = await api(`/api/factures/${id}`);
  const achat = f.sens.includes('achat');
  const deuxParts = Boolean(f.montant_hors);
  const reste = deuxParts ? f.reste_total : (f.net_a_payer - f.montant_regle);
  const tresoreries = await optionsTresorerie();
  const MODES = [['virement', 'Virement'], ['cheque', 'Chèque'],
                 ['espece', 'Espèces'], ['traite', 'Traite']];

  const conteneur = document.createElement('div');
  conteneur.innerHTML = `
    <div class="ligne-champs">
      <label class="champ"><span>Date *</span>
        <input type="date" id="r-date" value="${aujourdhui()}"></label>
      ${deuxParts ? `
      <label class="champ"><span>Reste dû — déclaré</span>
        <input value="${fm(f.reste_declare)}" disabled></label>
      <label class="champ"><span>Reste dû — non déclaré</span>
        <input value="${fm(f.reste_hors)}" disabled></label>`
      : `<label class="champ"><span>Reste dû</span>
        <input value="${fm(reste)}" disabled></label>`}
    </div>
    <p class="message info">
      Un même règlement peut arriver en plusieurs fois — un chèque et des
      espèces pour la même vente. Ajoutez une ligne par moyen de paiement :
      chacun garde son compte et sa référence${deuxParts
        ? ', et dit laquelle des deux parts il solde' : ''},
      et l'ensemble reste une seule opération.
    </p>
    <table class="saisie"><thead><tr>
      ${deuxParts ? '<th style="width:18%">Part</th>' : ''}
      <th style="width:16%">Mode</th><th style="width:26%">Compte</th>
      <th style="width:20%">Référence</th><th style="width:20%" class="num">Montant</th><th></th>
    </tr></thead><tbody id="r-lignes"></tbody></table>
    <div class="rangee" style="margin-top:8px">
      <button class="petit-bouton" id="r-ajout">+ Moyen de paiement</button></div>
    <div class="bandeau-equilibre">
      <span>Total saisi <strong id="r-total">0,00</strong></span>
      <span>Reste après <strong id="r-apres">0,00</strong></span>
    </div>`;

  const corps = $('#r-lignes', conteneur);

  function ajouteLigne(montant = '', part = 'declare') {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      ${deuxParts ? `<td><select class="r-part">
        <option value="declare" ${part === 'declare' ? 'selected' : ''}>Déclaré</option>
        <option value="hors_declaration" ${part === 'hors_declaration' ? 'selected' : ''}>Non déclaré</option>
      </select></td>` : ''}
      <td><select class="r-mode">${MODES.map(([v, l]) =>
        `<option value="${v}">${l}</option>`).join('')}</select></td>
      <td><select class="r-tresorerie">${tresoreries.map(([v, l]) =>
        `<option value="${v}">${ech(l)}</option>`).join('')}</select></td>
      <td><input class="r-reference" placeholder="n° chèque"></td>
      <td><input class="r-montant num" value="${montant}"></td>
      <td><button class="plat petit-bouton">✕</button></td>`;
    $('button', tr).onclick = () => {
      if ($$('tr', corps).length > 1) { tr.remove(); recalcule(); }
    };
    $$('input, select', tr).forEach((el) => { el.oninput = recalcule; });
    corps.appendChild(tr);
    recalcule();
  }

  function recalcule() {
    const total = $$('tr', corps)
      .reduce((somme, tr) => somme + cts($('.r-montant', tr).value), 0);
    $('#r-total', conteneur).textContent = fm(total);
    $('#r-apres', conteneur).textContent = fm(reste - total);
  }

  function litLignes() {
    return $$('tr', corps).map((tr) => ({
      part: deuxParts ? $('.r-part', tr).value : undefined,
      mode: $('.r-mode', tr).value,
      tresorerie_id: $('.r-tresorerie', tr).value,
      reference: $('.r-reference', tr).value,
      montant: $('.r-montant', tr).value,
    })).filter((l) => cts(l.montant) > 0);
  }

  // Une vente à deux parts s'ouvre sur ses deux restes dus : c'est le cas
  // ordinaire — le chèque solde l'une, les espèces l'autre.
  if (deuxParts) {
    if (f.reste_declare > 0) ajouteLigne(pourChamp(f.reste_declare), 'declare');
    if (f.reste_hors > 0) ajouteLigne(pourChamp(f.reste_hors), 'hors_declaration');
    if (!$$('tr', corps).length) ajouteLigne();
  } else {
    ajouteLigne(pourChamp(reste));
  }
  $('#r-ajout', conteneur).onclick = () => ajouteLigne();

  modale({
    titre: `${achat ? 'Régler' : 'Encaisser'} la facture ${f.numero}`,
    contenu: conteneur, large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async () => {
        const lignes = litLignes();
        if (!lignes.length) throw new Error('Saisissez au moins un montant.');
        const d = await envoie('/api/reglements/multiple', {
          societe_id: App.etat.societe.id,
          sens: achat ? 'decaissement' : 'encaissement',
          date: $('#r-date', conteneur).value,
          facture_id: id, tiers_id: f.tiers_id, lignes,
        });
        notifie(lignes.length > 1
          ? `${lignes.length} règlements enregistrés — ${fm(d.total)} au total.`
          : 'Règlement enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ------------------------------------------- Modèles et duplication ----- */

/* Le loyer de février ressemble à celui de janvier, la paie de mars à celle
   de février. Sans cela, tout se retape : journal, libellé, chaque compte,
   chaque montant. Deux chemins pour le même besoin — reprendre une écriture
   qu'on a sous les yeux, ou rejouer une forme mise de côté une fois pour
   toutes. */

/** Rouvre la saisie pré-remplie à partir d'une écriture existante. */
function dupliqueEcriture(e) {
  fermeModale();
  saisieEcriture({
    titre: `Copie de l'écriture ${e.numero}`,
    journal: e.journal,
    libelle: e.libelle,
    piece: '',                      // le numéro de pièce, lui, est propre à l'original
    perimetre: e.perimetre,
    // La date reste celle du jour : c'est ce qu'on veut neuf fois sur dix,
    // et une date recopiée par inadvertance se voit mal.
    lignes: (e.lignes || []).map((l) => ({
      compte: l.compte, tiers_id: l.tiers_id, libelle: l.libelle,
      debit: l.debit, credit: l.credit,
    })),
  });
}

/** Met la saisie en cours de côté, sous un nom. */
async function gardeModeleEcriture(conteneur, litLignes) {
  const lignes = litLignes();
  if (!lignes.length) {
    notifie('Renseignez au moins une ligne avant de garder un modèle.', 'alerte');
    return;
  }
  const nom = prompt('Nom du modèle (ex : « Loyer du local », « Paie mensuelle ») :',
                     $('#e-libelle', conteneur).value || '');
  if (!nom || !nom.trim()) return;
  try {
    await envoie('/api/modeles-ecriture', {
      nom: nom.trim(),
      journal: $('#e-journal', conteneur).value,
      libelle: $('#e-libelle', conteneur).value,
      perimetre: $('#e-perimetre', conteneur).value,
      lignes,
    });
    notifie(`Modèle « ${nom.trim()} » gardé. Vous le retrouverez sous « Depuis un modèle ».`,
            'succes', 7000);
  } catch (err) { erreur(err); }
}

/** Liste des modèles, pour en rejouer un. */
async function choisitModeleEcriture() {
  const d = await charge('/api/modeles-ecriture');
  if (!d.modeles.length) {
    modale({
      titre: 'Aucun modèle pour l\'instant',
      contenu: `<p>Un modèle garde la forme d'une écriture qui revient — le
        loyer, la paie, les charges fixes — pour n'avoir plus qu'à changer
        la date.</p>
        <p class="petit">Pour en créer un : ouvrez <strong>+ Écriture</strong>,
        remplissez-la, puis cliquez sur <strong>« Garder comme modèle »</strong>.
        Vous pouvez aussi ouvrir une écriture existante et la
        <strong>Dupliquer</strong>.</p>`,
      boutons: [{ libelle: 'Fermer' }],
    });
    return;
  }
  modale({
    titre: 'Écrire depuis un modèle',
    large: true,
    contenu: tableau([
      { titre: 'Modèle', rendu: (m) => `<strong>${ech(m.nom)}</strong>` },
      { titre: 'Journal', cle: 'journal', largeur: '70px' },
      { titre: 'Libellé', rendu: (m) => ech(m.libelle || '') },
      { titre: 'Lignes', classe: 'num', largeur: '70px',
        rendu: (m) => String((m.lignes || []).length) },
      { titre: 'Périmètre', rendu: (m) => badgePerimetre(m.perimetre) },
      { titre: 'Employé', classe: 'num', largeur: '80px',
        rendu: (m) => m.emplois ? `${m.emplois} fois` : '<span class="discret">—</span>' },
      {
        titre: '', classe: 'num',
        rendu: (m) => `<button class="petit-bouton primaire" data-modele="${m.id}">Utiliser</button>
          <button class="petit-bouton danger" data-oublie="${m.id}">Oublier</button>`,
      },
    ], d.modeles, { messageVide: 'Aucun modèle.' }),
    boutons: [{ libelle: 'Fermer' }],
  });

  const parId = Object.fromEntries(d.modeles.map((m) => [String(m.id), m]));
  document.querySelectorAll('[data-modele]').forEach((b) => {
    b.onclick = () => employeModeleEcriture(parId[b.dataset.modele]);
  });
  document.querySelectorAll('[data-oublie]').forEach((b) => {
    // Confirmation sur le bouton : une seconde fenêtre remplacerait celle-ci.
    b.onclick = async () => {
      if (b.dataset.sur !== '1') {
        b.dataset.sur = '1';
        b.textContent = 'Confirmer ?';
        return;
      }
      await api(`/api/modeles-ecriture/${b.dataset.oublie}`, { method: 'DELETE' });
      notifie('Modèle oublié.', 'succes');
      choisitModeleEcriture();
    };
  });
}

function employeModeleEcriture(modele) {
  if (!modele) return;
  fermeModale();
  // Le compteur sert à remonter les modèles les plus employés ; il ne doit
  // pas empêcher la saisie s'il échoue.
  envoie(`/api/modeles-ecriture/${modele.id}/employe`, {}).catch(() => {});
  saisieEcriture({
    titre: `Écriture depuis « ${modele.nom} »`,
    journal: modele.journal,
    libelle: modele.libelle,
    perimetre: modele.perimetre,
    lignes: modele.lignes || [],
  });
}
