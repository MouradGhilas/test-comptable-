/* ==========================================================================
   Pages fiscalité, paie et immobilisations
   ========================================================================== */

App.pages.fiscalite = {
  titre: 'Fiscalité',
  async afficher(zone, route) {
    const vue = route.segments[1] || 'g50';
    const onglets = [['g50', 'Déclaration G50'], ['tva', 'Livres de TVA'],
      ['ibs', 'IBS'], ['obligations', 'Calendrier'], ['parametres', 'Taux et barèmes']];
    zone.innerHTML = `<div class="onglets">${onglets.map(([v, l]) =>
      `<button class="${v === vue ? 'actif' : ''}" onclick="navigue('/fiscalite/${v}')">${l}</button>`).join('')}</div>
      <div id="vue-fisc"><div class="vide">Chargement…</div></div>`;
    const vues = { g50: vueG50, tva: vueLivreTva, ibs: vueIbs, obligations: vueObligations, parametres: vueParametresFiscaux };
    await (vues[vue] || vueG50)($('#vue-fisc'), route);
  },
};

['g50', 'tva', 'ibs', 'obligations', 'parametres'].forEach((v) => {
  App.pages[`fiscalite/${v}`] = App.pages.fiscalite;
});

/* ------------------------------------------------------------------ G50 -- */

async function vueG50(zone, route) {
  const periode = route.parametres.periode || moisPrecedent(periodeCourante());
  const d = await charge('/api/g50', { periode });
  const enr = d.enregistree;
  actionsPage(`<button onclick="window.open(requete('/api/g50/impression',{periode:'${periode}'}),'_blank')">Imprimer</button>`);

  const ligne = (libelle, valeur, gras = false, indice = '') =>
    `<tr class="${gras ? 'total' : ''}"><td class="petit">${indice}</td>
     <td>${libelle}</td><td class="num">${fm(valeur)}</td></tr>`;

  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ"><span>Période déclarée</span>
        <input type="month" value="${periode}"
          onchange="navigue('/fiscalite/g50?periode='+this.value)"></label>
      <div class="pile" style="margin-left:auto">
        <span class="petit">Date limite de dépôt</span>
        <strong class="${d.date_limite < aujourdhui() && (!enr || enr.statut === 'brouillon') ? 'rouge' : ''}">${fdate(d.date_limite)}</strong>
      </div>
      <div class="pile"><span class="petit">Statut</span>${etiquette(enr?.statut || 'brouillon')}</div>
    </div>

    ${bandeauPerimetre('declare',
      "Une déclaration ne peut porter que sur les opérations déclarées.")}
    ${d.hors_declaration && d.hors_declaration.nb_ecritures ? `
      <div class="message alerte"><strong>Hors de cette déclaration</strong>
        ${d.hors_declaration.nb_ecritures} opération(s) marquée(s) « hors déclaration »
        sur la période, pour ${fm(d.hors_declaration.produits, true)} de produits.
        Elles ne sont pas reprises ci-dessous.</div>` : ''}
    ${(d.avertissements || []).map((a) => `<div class="message info">${ech(a)}</div>`).join('')}

    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('TVA à payer', fm(d.tva_a_payer, true))}
      ${indicateur('Précompte reporté', fm(d.precompte_reporte, true),
        d.precompte_reporte ? 'crédit imputable le mois prochain' : '')}
      ${indicateur('Retenues à la source', fm(d.irg_salaires + d.irg_ras_autres, true))}
      ${indicateur('TOTAL À PAYER', fm(d.total_a_payer, true), fperiode(periode), 'accent')}
    </div>

    <div class="grille c2">
      ${carte('Chiffre d\'affaires', `<div class="enveloppe-table"><table class="donnees"><tbody>
        ${ligne('Chiffre d\'affaires taxable', d.ca_taxable)}
        ${ligne('Chiffre d\'affaires exonéré ou hors champ', d.ca_exonere)}
        ${ligne('Total', d.ca_total, true)}
      </tbody></table></div>`, '', true)}

      ${carte('Taxe sur la valeur ajoutée', `<div class="enveloppe-table"><table class="donnees"><tbody>
        ${ligne('TVA collectée', d.tva_collectee, false, 'A')}
        ${ligne('TVA déductible — biens et services', d.tva_deductible_bs, false, 'B')}
        ${ligne('TVA déductible — immobilisations', d.tva_deductible_immo, false, 'C')}
        ${ligne('Précompte antérieur', d.precompte_anterieur, false, 'D')}
        ${ligne('TVA à payer (A − B − C − D)', d.tva_a_payer, true, 'E')}
        ${ligne('Précompte à reporter', d.precompte_reporte, false, 'F')}
      </tbody></table></div>`, '', true)}
    </div>

    ${d.tap_applicable ? carte('Taxe sur l\'activité professionnelle',
      `<div class="enveloppe-table"><table class="donnees"><tbody>
        ${ligne('Base imposable', d.base_tap)}
        <tr><td></td><td>Taux</td><td class="num">${ft(d.taux_tap)} %</td></tr>
        ${ligne('TAP due', d.tap, true)}
      </tbody></table></div>`, '', true)
      : `<div class="message info">La TAP est désactivée pour cet exercice.
         Si elle s'applique à votre activité, activez-la dans « Taux et barèmes ».</div>`}

    ${carte('Retenues à la source et autres droits', `<div class="enveloppe-table"><table class="donnees"><tbody>
      ${ligne('IRG / Salaires', d.irg_salaires)}
      ${ligne('IRG / Retenues diverses', d.irg_ras_autres)}
      ${ligne('Droit de timbre', d.droit_timbre)}
      <tr><td></td><td>Acompte provisionnel IBS
        <input id="g50-acompte" class="num" style="width:150px;display:inline-block"
          value="${pourChamp(enr?.acompte_ibs || 0)}" placeholder="0,00"></td>
        <td class="num petit">à saisir</td></tr>
      <tr><td></td><td>Autres droits
        <input id="g50-autres" class="num" style="width:150px;display:inline-block"
          value="${pourChamp(enr?.autres || 0)}" placeholder="0,00"></td>
        <td class="num petit">à saisir</td></tr>
      ${ligne('TOTAL À PAYER', d.total_a_payer, true)}
    </tbody></table></div>`,
      `<button class="primaire" onclick="enregistreG50('${periode}')">Enregistrer la déclaration</button>
       ${enr && !enr.ecriture_id ? `<button onclick="comptabiliseG50('${periode}')">Comptabiliser la TVA</button>` : ''}
       ${enr && enr.statut !== 'payee' ? `<button onclick="payeG50('${periode}')">Enregistrer le paiement</button>` : ''}`, true)}

    <div class="message info"><strong>Aide à la déclaration</strong>
      Les montants sont calculés à partir de votre comptabilité. Reportez-les sur
      l'imprimé officiel G n° 50 après vérification. « Comptabiliser la TVA » génère
      l'écriture de liquidation (4457 → 44566 / 4451).</div>`;
}

async function enregistreG50(periode) {
  try {
    const r = await envoie('/api/g50', {
      periode, statut: 'calculee',
      acompte_ibs: $('#g50-acompte')?.value || 0,
      autres: $('#g50-autres')?.value || 0,
    });
    notifie(`Déclaration enregistrée — total à payer ${fm(r.total_a_payer, true)}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function comptabiliseG50(periode) {
  try {
    await envoie('/api/g50/comptabiliser', { periode });
    notifie('Écriture de liquidation de TVA générée.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function payeG50(periode) {
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Payé depuis', type: 'select', requis: true, vide: false, options: await optionsTresorerie() },
    { nom: 'date', libelle: 'Date du paiement', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'reference', libelle: 'Référence du versement' },
  ];
  modale({
    titre: `Paiement de la G50 — ${fperiode(periode)}`,
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/g50/payer', { periode, ...litFormulaire(r, champs) });
        notifie(`Paiement de ${fm(d.montant, true)} enregistré.`, 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ---------------------------------------------------------- Livres TVA -- */

async function vueLivreTva(zone, route) {
  const periode = route.parametres.periode || moisPrecedent(periodeCourante());
  const sens = route.parametres.sens || 'ventes';
  const d = await charge('/api/livre-tva', { periode, sens });
  actionsPage(`<button onclick="telecharge('/api/export/livre-tva',{periode:'${periode}',sens:'${sens}'})">Exporter</button>`);

  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ"><span>Période</span>
        <input type="month" value="${periode}"
          onchange="navigue('/fiscalite/tva?periode='+this.value+'&sens=${sens}')"></label>
      <label class="champ"><span>Livre</span>
        <select onchange="navigue('/fiscalite/tva?periode=${periode}&sens='+this.value)">
          <option value="ventes" ${sens === 'ventes' ? 'selected' : ''}>Ventes (TVA collectée)</option>
          <option value="achats" ${sens === 'achats' ? 'selected' : ''}>Achats (TVA déductible)</option>
        </select></label>
    </div>
    <div class="grille c3" style="margin-bottom:16px">
      ${indicateur('Nombre d\'opérations', d.operations.length)}
      ${indicateur('Base HT', fm(d.total_base, true))}
      ${indicateur(sens === 'ventes' ? 'TVA collectée' : 'TVA déductible', fm(d.total_tva, true), '', 'accent')}
    </div>
    ${carte('', tableau([
      { titre: 'Date', rendu: (o) => fdate(o.date) },
      { titre: 'Jal', cle: 'journal' },
      { titre: 'N°', cle: 'numero' },
      { titre: 'Pièce', cle: 'piece' },
      { titre: 'Tiers', cle: 'tiers' },
      { titre: 'NIF', cle: 'nif' },
      { titre: 'Libellé', rendu: (o) => `<div class="tronque">${ech(o.libelle)}</div>` },
      { titre: 'Base HT', classe: 'num', rendu: (o) => fm(o.base_ht) },
      { titre: 'TVA', classe: 'num', rendu: (o) => `<strong>${fm(o.tva)}</strong>` },
    ], d.operations, { icone: '📗', messageVide: 'Aucune opération taxable sur cette période.' }), '', true)}`;
}

/* ------------------------------------------------------------------ IBS -- */

async function vueIbs(zone, route) {
  const d = await charge('/api/ibs', {
    reintegrations: route.parametres.reintegrations,
    deductions: route.parametres.deductions,
    deficits: route.parametres.deficits,
  });
  actionsPage('');
  const l = (libelle, valeur, gras = false) =>
    `<tr class="${gras ? 'total' : ''}"><td>${libelle}</td><td class="num">${fm(valeur)}</td></tr>`;

  zone.innerHTML = `
    ${bandeauPerimetre('declare', "L'IBS est assis sur le résultat déclaré.")}
    ${d.hors_declaration && d.hors_declaration.nb_ecritures ? `
      <div class="message alerte">${d.hors_declaration.nb_ecritures} opération(s)
        hors déclaration sur l'exercice (${fm(d.hors_declaration.produits, true)} de
        produits) ne sont pas comprises dans ce calcul.</div>` : ''}
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Résultat comptable', fm(d.resultat_comptable, true))}
      ${indicateur('Résultat fiscal', fm(d.resultat_fiscal, true))}
      ${indicateur(`IBS dû (${ft(d.taux_ibs)} %)`, fm(d.ibs_du, true), '', 'accent')}
      ${indicateur('Solde à payer', fm(d.solde_a_payer, true),
        `acomptes versés ${fm(d.acomptes_verses)}`, d.solde_a_payer > 0 ? 'danger' : 'succes')}
    </div>

    <div class="grille c2">
      ${carte('Détermination du résultat fiscal', `<div class="enveloppe-table"><table class="donnees"><tbody>
        ${l('Résultat comptable avant impôt', d.resultat_avant_impot)}
        ${l('+ Réintégrations extra-comptables', d.reintegrations)}
        ${l('− Déductions extra-comptables', d.deductions)}
        ${l('− Déficits antérieurs reportables', d.deficits_anterieurs)}
        ${l('= Résultat fiscal imposable', d.resultat_fiscal, true)}
        ${l(`IBS au taux de ${ft(d.taux_ibs)} %`, d.ibs_brut)}
        ${d.minimum_imposition ? l('Minimum d\'imposition', d.minimum_imposition) : ''}
        ${l('IBS dû', d.ibs_du, true)}
        ${l('− Acomptes provisionnels versés', d.acomptes_verses)}
        ${l('= Solde à payer', d.solde_a_payer, true)}
      </tbody></table></div>`, '', true)}

      ${carte('Ajustements extra-comptables', `
        <p class="petit">Saisissez les retraitements fiscaux propres à votre situation :
          amendes et pénalités, amortissements excédentaires, provisions non déductibles,
          déficits reportables…</p>
        <div class="ligne-champs">
          <label class="champ"><span>Réintégrations</span>
            <input class="num" id="ibs-reint" value="${pourChamp(d.reintegrations)}"></label>
          <label class="champ"><span>Déductions</span>
            <input class="num" id="ibs-deduc" value="${pourChamp(d.deductions)}"></label>
          <label class="champ"><span>Déficits antérieurs</span>
            <input class="num" id="ibs-deficits" value="${pourChamp(d.deficits_anterieurs)}"></label>
        </div>
        <div class="groupe-boutons">
          <button onclick="recalculeIbs()">Recalculer</button>
          <button class="primaire" onclick="comptabiliseIbs(${d.ibs_du}, ${d.acomptes_verses})">Comptabiliser l'IBS</button>
        </div>
        <div class="separateur"></div>
        <div class="liste-definitions">
          <dt>Prochain acompte (${ft(d.taux_acompte)} %)</dt>
          <dd class="num">${fm(d.acompte_suivant, true)}</dd>
        </div>`)}
    </div>
    <div class="message info">${ech(d.note)}</div>`;
}

function recalculeIbs() {
  const p = new URLSearchParams({
    reintegrations: $('#ibs-reint').value,
    deductions: $('#ibs-deduc').value,
    deficits: $('#ibs-deficits').value,
  });
  navigue(`/fiscalite/ibs?${p}`);
}

async function comptabiliseIbs(montant, acomptes) {
  const champs = [
    { nom: 'montant', libelle: 'IBS à comptabiliser', type: 'montant', requis: true, defaut: montant },
    { nom: 'acomptes_imputes', libelle: 'Acomptes à imputer', type: 'montant', defaut: acomptes },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: App.etat.exercice.date_fin },
  ];
  modale({
    titre: 'Comptabiliser l\'impôt sur les bénéfices',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Comptabiliser', classe: 'primaire',
      action: async (r) => {
        await envoie('/api/ibs/comptabiliser', {
          exercice_id: App.etat.exercice.id, ...litFormulaire(r, champs),
        });
        notifie('Écriture d\'IBS générée.', 'succes');
        afficheRoute();
      },
    }],
  });
}

/* ---------------------------------------------------------- Obligations -- */

async function vueObligations(zone, route) {
  const annee = route.parametres.annee || String(new Date().getFullYear());
  const d = await charge('/api/obligations', { annee });
  actionsPage(`<button class="primaire" onclick="genereObligations()">Générer le calendrier ${annee}</button>`);

  zone.innerHTML = carte(`Calendrier fiscal et social ${annee}`, tableau([
    { titre: 'Échéance', rendu: (o) => fdate(o.date_limite), largeur: '100px' },
    { titre: 'Obligation', rendu: (o) => `<strong>${ech(o.libelle)}</strong>` },
    { titre: 'Période', cle: 'periode' },
    { titre: 'Statut', rendu: (o) => o.en_retard ? etiquette('retard') : etiquette(o.statut) },
    {
      titre: 'Délai', classe: 'num',
      rendu: (o) => o.en_retard ? `<span class="rouge">${o.jours_retard} j de retard</span>`
        : (o.statut === 'a_faire' ? `dans ${o.jours_restants} j` : ''),
    },
    { titre: 'Référence', cle: 'reference' },
    {
      titre: '', classe: 'num',
      rendu: (o) => o.statut === 'a_faire'
        ? `<button class="petit-bouton succes" onclick="marqueFait(${o.id})">Marquer fait</button>` : '',
    },
  ], d.obligations, {
    icone: '📅',
    messageVide: 'Aucune échéance. Cliquez sur « Générer le calendrier » pour créer les échéances G50, CNAS, IBS et bilan de l\'année.',
  }), '', true);
}

async function marqueFait(id) {
  try {
    await envoie(`/api/obligations/${id}`, { statut: 'fait', date_execution: aujourdhui() }, 'PUT');
    notifie('Obligation marquée comme faite.', 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* --------------------------------------------------- Paramètres fiscaux -- */

async function vueParametresFiscaux(zone, route) {
  const annee = route.parametres.annee || String(new Date().getFullYear());
  const d = await charge('/api/parametres-fiscaux', { annee });
  actionsPage('');

  const rendu = (p) => {
    // Le barème IRG change à presque chaque loi de finances, et il commande
    // tous les bulletins de paie. C'était pourtant le seul paramètre affiché
    // en lecture seule, alors que sa remarque dit « à vérifier et adapter ».
    if (p.unite === 'bareme') {
      let tranches = [];
      try { tranches = JSON.parse(p.valeur); } catch { tranches = []; }
      return `<td colspan="2"><div id="bareme-${ech(p.cle)}"
                data-bareme="${ech(p.cle)}">${lignesBareme(tranches)}</div>
        <button class="petit-bouton" onclick="ajouteTrancheBareme('${ech(p.cle)}')"
          style="margin-top:6px">+ Ajouter une tranche</button></td>`;
    }
    const valeur = p.unite === 'pourcentage' ? ft(p.valeur)
      : (p.unite === 'montant' ? pourChamp(p.valeur) : p.valeur);
    const suffixe = p.unite === 'pourcentage' ? '%' : (p.unite === 'montant' ? 'DA' : '');
    return `<td><input class="num" data-cle="${ech(p.cle)}" data-unite="${ech(p.unite)}"
              value="${ech(valeur)}"></td><td class="petit">${suffixe}</td>`;
  };

  zone.innerHTML = `
    <div class="message alerte"><strong>À vérifier chaque année</strong>
      La loi de finances modifie régulièrement ces taux. L'application ne les met pas à jour
      automatiquement : contrôlez-les avant d'établir vos déclarations.</div>
    <div class="barre-outils">
      <label class="champ"><span>Exercice</span>
        <select onchange="navigue('/fiscalite/parametres?annee='+this.value)">
          ${[...new Set([...d.annees.map(String), annee])].sort().reverse().map((a) =>
            `<option value="${a}" ${a === annee ? 'selected' : ''}>${a}</option>`).join('')}
        </select></label>
      ${[0, 1, 2].map((i) => {
        const a = String(new Date().getFullYear() + i);
        return d.annees.map(String).includes(a) ? '' :
          `<button onclick="navigue('/fiscalite/parametres?annee=${a}')">Créer ${a}</button>`;
      }).join('')}
    </div>
    ${carte(`Taux et barèmes ${annee}`, `<div class="enveloppe-table"><table class="donnees">
      <thead><tr><th style="width:34%">Paramètre</th><th style="width:14%">Valeur</th>
        <th style="width:5%"></th><th>Référence / remarque</th></tr></thead>
      <tbody>${d.parametres.map((p) => `<tr>
        <td><strong>${ech(p.libelle || p.cle)}</strong><div class="tres-petit">${ech(p.cle)}</div></td>
        ${rendu(p)}
        <td class="petit">${ech(p.source || '')}</td></tr>`).join('')}</tbody>
    </table></div>`, `<button class="primaire" onclick="enregistreParametres('${annee}')">Enregistrer</button>`, true)}`;
}

async function enregistreParametres(annee) {
  const parametres = $$('[data-cle]').map((el) => {
    const unite = el.dataset.unite;
    let valeur = el.value;
    if (unite === 'pourcentage') valeur = Math.round(parseFloat(String(valeur).replace(',', '.') || 0) * 100);
    else if (unite === 'montant') valeur = cts(valeur);
    return { cle: el.dataset.cle, valeur, unite };
  });
  // Les barèmes ne sont pas de simples champs : ils se relisent tranche
  // par tranche. Le serveur accepte déjà une liste et la range en JSON.
  for (const zone of $$('[data-bareme]')) {
    const tranches = litBareme(zone.dataset.bareme);
    if (!tranches || !tranches.length) continue;
    if (tranches.some((t) => t.plafond !== null && t.plafond <= 0)) {
      notifie('Chaque tranche doit avoir un plafond supérieur à zéro.', 'alerte');
      return;
    }
    parametres.push({ cle: zone.dataset.bareme, valeur: tranches, unite: 'bareme' });
  }
  try {
    await envoie('/api/parametres-fiscaux', { annee, parametres }, 'PUT');
    notifie(`Paramètres fiscaux ${annee} enregistrés.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

/* ----------------------------------------------------------------- Paie -- */

App.pages.paie = {
  titre: 'Paie',
  async afficher(zone, route) {
    const vue = route.segments[1] || 'bulletins';
    zone.innerHTML = `<div class="onglets">
      ${[['bulletins', 'Bulletins'], ['salaries', 'Salariés'], ['simulateur', 'Simulateur']]
        .map(([v, l]) => `<button class="${v === vue ? 'actif' : ''}" onclick="navigue('/paie/${v}')">${l}</button>`).join('')}
      </div><div id="vue-paie"><div class="vide">Chargement…</div></div>`;
    const vues = { bulletins: vueBulletins, salaries: vueSalaries, simulateur: vueSimulateur };
    await (vues[vue] || vueBulletins)($('#vue-paie'), route);
  },
};

['bulletins', 'salaries', 'simulateur'].forEach((v) => { App.pages[`paie/${v}`] = App.pages.paie; });

async function vueBulletins(zone, route) {
  const periode = route.parametres.periode || periodeCourante();
  const d = await charge('/api/bulletins', { periode });
  const t = d.totaux;
  actionsPage(`<button class="primaire" onclick="genereBulletins('${periode}')">Générer les bulletins</button>
    <button onclick="telecharge('/api/export/paie',{periode:'${periode}'})">Livre de paie</button>`);

  zone.innerHTML = `
    <div class="barre-outils">
      <label class="champ"><span>Période</span>
        <input type="month" value="${periode}" onchange="navigue('/paie/bulletins?periode='+this.value)"></label>
    </div>
    <div class="grille c4" style="margin-bottom:16px">
      ${indicateur('Masse salariale brute', fm(t.brut, true))}
      ${indicateur('Retenues salariales', fm(t.cnas_salarie + t.irg, true),
        `CNAS ${fm(t.cnas_salarie)} · IRG ${fm(t.irg)}`)}
      ${indicateur('Net à payer', fm(t.net, true), '', 'accent')}
      ${indicateur('Coût employeur', fm(t.cout, true), `dont CNAS patronale ${fm(t.cnas_patronale)}`)}
    </div>
    ${carte('', tableau([
      { titre: 'Matricule', cle: 'matricule' },
      { titre: 'Nom', rendu: (b) => `<strong>${ech(b.nom)} ${ech(b.prenom)}</strong>` },
      { titre: 'Poste', cle: 'poste' },
      { titre: 'Jours', classe: 'num', rendu: (b) => (b.jours_travailles / 1000).toFixed(0) },
      { titre: 'Brut', classe: 'num', rendu: (b) => fm(b.salaire_brut) },
      { titre: 'CNAS 9 %', classe: 'num', rendu: (b) => fm(b.cnas_salarie) },
      { titre: 'IRG', classe: 'num', rendu: (b) => fm(b.irg) },
      { titre: 'Net à payer', classe: 'num', rendu: (b) => `<strong>${fm(b.net_a_payer)}</strong>` },
      { titre: 'CNAS patr.', classe: 'num', rendu: (b) => fm(b.cnas_patronale) },
      { titre: 'Statut', rendu: (b) => etiquette(b.statut) },
      {
        titre: '', classe: 'num',
        rendu: (b) => `<button class="petit-bouton" onclick="window.open('/api/bulletins/${b.id}/impression','_blank')">Bulletin</button>`,
      },
    ], d.bulletins, {
      icone: '💼',
      messageVide: 'Aucun bulletin sur cette période. Cliquez sur « Générer les bulletins ».',
    }),
      `<button onclick="comptabilisePaie('${periode}')">Comptabiliser la paie</button>
       <button onclick="payeSalaires('${periode}')">Enregistrer le paiement</button>`, true)}`;
}

async function genereBulletins(periode) {
  try {
    const r = await envoie('/api/bulletins/generer', { periode });
    notifie(`${r.crees} bulletin(s) généré(s)${r.existants ? `, ${r.existants} déjà présents` : ''}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function comptabilisePaie(periode) {
  try {
    const r = await envoie('/api/bulletins/comptabiliser', { periode });
    notifie(`Paie comptabilisée : ${r.bulletins} bulletin(s), brut ${fm(r.brut, true)}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function payeSalaires(periode) {
  const champs = [
    { nom: 'tresorerie_id', libelle: 'Payé depuis', type: 'select', requis: true, vide: false, options: await optionsTresorerie() },
    { nom: 'date', libelle: 'Date', type: 'date', requis: true, defaut: aujourdhui() },
  ];
  modale({
    titre: `Règlement des salaires — ${fperiode(periode)}`,
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const d = await envoie('/api/bulletins/payer', { periode, ...litFormulaire(r, champs) });
        notifie(`Paiement de ${fm(d.montant, true)} enregistré.`, 'succes');
        afficheRoute();
      },
    }],
  });
}

async function vueSalaries(zone) {
  const d = await charge('/api/salaries');
  actionsPage('<button class="primaire" onclick="editeSalarie()">+ Salarié</button>'
    + boutonImport('salaries', 'Importer des salariés'));
  zone.innerHTML = carte('Salariés', tableau([
    { titre: 'Matricule', cle: 'matricule' },
    { titre: 'Nom', rendu: (s) => `<strong>${ech(s.nom)} ${ech(s.prenom)}</strong>` },
    { titre: 'N° sécurité sociale', cle: 'num_secu' },
    { titre: 'Poste', cle: 'poste' },
    { titre: 'Contrat', cle: 'type_contrat' },
    { titre: 'Embauche', rendu: (s) => fdate(s.date_embauche) },
    { titre: 'Salaire de base', classe: 'num', rendu: (s) => fm(s.salaire_base) },
    { titre: 'Primes', classe: 'num', rendu: (s) => fm(s.primes.reduce((t, p) => t + cts(p.montant), 0)) },
    { titre: 'Actif', classe: 'centre', rendu: (s) => s.actif ? '✓' : '✗' },
    {
      titre: '', classe: 'num',
      rendu: (s) => `<button class="petit-bouton" onclick="editeSalarie(${s.id})">Modifier</button>`,
    },
  ], d.salaries, { icone: '👤', messageVide: 'Aucun salarié enregistré.' }), '', true);
}

const CHAMPS_SALARIE = [
  { groupe: 'Identité' },
  { nom: 'matricule', libelle: 'Matricule' },
  { nom: 'nom', libelle: 'Nom', requis: true },
  { nom: 'prenom', libelle: 'Prénom', requis: true },
  { nom: 'date_naissance', libelle: 'Date de naissance', type: 'date' },
  { nom: 'num_secu', libelle: 'N° de sécurité sociale' },
  { groupe: 'Contrat' },
  { nom: 'poste', libelle: 'Poste' },
  { nom: 'categorie', libelle: 'Catégorie' },
  { nom: 'type_contrat', libelle: 'Type de contrat', type: 'select', options: ['CDI', 'CDD', 'Stage', 'Apprentissage'] },
  { nom: 'date_embauche', libelle: 'Date d\'embauche', type: 'date' },
  { nom: 'date_sortie', libelle: 'Date de sortie', type: 'date' },
  { groupe: 'Rémunération' },
  { nom: 'salaire_base', libelle: 'Salaire de base mensuel', type: 'montant', requis: true },
  { nom: 'situation_familiale', libelle: 'Situation familiale', type: 'select', options: ['Célibataire', 'Marié(e)', 'Divorcé(e)', 'Veuf(ve)'] },
  { nom: 'nb_enfants', libelle: 'Enfants à charge', type: 'number' },
  { nom: 'rib', libelle: 'RIB', large: true },
];

async function editeSalarie(id) {
  const liste = id ? (await charge('/api/salaries')).salaries : [];
  const existant = id ? liste.find((s) => s.id === id) : {};
  const primes = existant?.primes || [];

  const conteneur = document.createElement('div');
  conteneur.appendChild(formulaire(CHAMPS_SALARIE, existant || {}));
  const bloc = document.createElement('fieldset');
  bloc.innerHTML = `<legend>Primes et indemnités</legend>
    <table class="saisie"><thead><tr>
      <th>Libellé</th><th style="width:22%">Montant</th>
      <th style="width:14%" class="centre">Soumis CNAS</th>
      <th style="width:14%" class="centre">Soumis IRG</th><th></th>
    </tr></thead><tbody id="primes"></tbody></table>
    <button class="petit-bouton" id="ajout-prime" type="button">+ Prime</button>
    <div class="aide">Le panier et le transport sont généralement non soumis.</div>`;
  conteneur.appendChild(bloc);

  const corpsPrimes = $('#primes', bloc);
  function ajoutePrime(p = {}) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input class="p-libelle" value="${ech(p.libelle || '')}"></td>
      <td><input class="p-montant num" value="${p.montant ? pourChamp(cts(p.montant)) : ''}"></td>
      <td class="centre"><input type="checkbox" class="p-cnas" ${p.soumis_cnas !== false ? 'checked' : ''}></td>
      <td class="centre"><input type="checkbox" class="p-irg" ${p.soumis_irg !== false ? 'checked' : ''}></td>
      <td><button type="button" class="plat petit-bouton">✕</button></td>`;
    $('button', tr).onclick = () => tr.remove();
    corpsPrimes.appendChild(tr);
  }
  primes.forEach(ajoutePrime);
  if (!primes.length) ajoutePrime();
  $('#ajout-prime', bloc).onclick = () => ajoutePrime();

  modale({
    titre: id ? 'Modifier le salarié' : 'Nouveau salarié',
    contenu: conteneur, large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, CHAMPS_SALARIE);
        donnees.primes = $$('tr', corpsPrimes).map((tr) => ({
          libelle: $('.p-libelle', tr).value,
          montant: cts($('.p-montant', tr).value),
          soumis_cnas: $('.p-cnas', tr).checked,
          soumis_irg: $('.p-irg', tr).checked,
        })).filter((p) => p.libelle && p.montant);
        if (id) await envoie(`/api/salaries/${id}`, donnees, 'PUT');
        else await envoie('/api/salaries', donnees);
        notifie('Salarié enregistré.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function vueSimulateur(zone) {
  actionsPage('');
  zone.innerHTML = `
    <div class="grille c2">
      ${carte('Simulateur de salaire', `
        <p class="petit">Calcule le net à payer et le coût employeur à partir du brut,
          selon les taux CNAS et le barème IRG de l'exercice.</p>
        <div class="ligne-champs">
          <label class="champ"><span>Salaire de base</span>
            <input class="num" id="sim-base" value="60 000,00"></label>
          <label class="champ"><span>Primes soumises</span>
            <input class="num" id="sim-primes" value="0,00"></label>
          <label class="champ"><span>Primes non soumises</span>
            <input class="num" id="sim-non-soumis" value="0,00"></label>
        </div>
        <button class="primaire" onclick="simule()">Calculer</button>`)}
      <div id="resultat-simulation">${carte('Résultat', '<div class="vide">Renseignez un salaire puis calculez.</div>')}</div>
    </div>`;
}

async function simule() {
  try {
    const d = await envoie('/api/bulletins/simuler', {
      salaire_base: $('#sim-base').value,
      periode: periodeCourante(),
      primes: [
        { libelle: 'Primes soumises', montant: cts($('#sim-primes').value), soumis_cnas: true, soumis_irg: true },
        { libelle: 'Primes non soumises', montant: cts($('#sim-non-soumis').value), soumis_cnas: false, soumis_irg: false },
      ].filter((p) => p.montant),
    });
    $('#resultat-simulation').innerHTML = carte('Résultat', `<div class="enveloppe-table"><table class="donnees"><tbody>
      <tr><td>Salaire brut</td><td class="num">${fm(d.salaire_brut)}</td></tr>
      <tr><td>Base cotisable CNAS</td><td class="num">${fm(d.base_cnas)}</td></tr>
      <tr><td>Retenue CNAS (${ft(d.taux_cnas_salarie)} %)</td><td class="num rouge">−${fm(d.cnas_salarie)}</td></tr>
      <tr><td>Base imposable IRG</td><td class="num">${fm(d.base_irg)}</td></tr>
      <tr><td>IRG brut</td><td class="num">${fm(d.irg_brut)}</td></tr>
      <tr><td>Abattement IRG</td><td class="num vert">+${fm(d.abattement_irg)}</td></tr>
      <tr><td>IRG net</td><td class="num rouge">−${fm(d.irg)}</td></tr>
      <tr class="total"><td>NET À PAYER</td><td class="num">${fm(d.net_a_payer)}</td></tr>
      <tr><td>Charge patronale CNAS (${ft(d.taux_cnas_patronale)} %)</td><td class="num">${fm(d.cnas_patronale)}</td></tr>
      <tr class="total"><td>COÛT EMPLOYEUR</td><td class="num">${fm(d.cout_employeur)}</td></tr>
    </tbody></table></div>`, '', true);
  } catch (err) { erreur(err); }
}

/* --------------------------------------------------- Immobilisations ---- */

App.pages.immobilisations = {
  titre: 'Immobilisations',
  async afficher(zone) {
    const d = await charge('/api/immobilisations', { annee: App.etat.exercice?.libelle });
    actionsPage(`<button class="primaire" onclick="editeImmo()">+ Immobilisation</button>`
      + boutonImport('immobilisations', 'Importer des immobilisations')
      + `<button onclick="lanceDotations()">Comptabiliser les dotations</button>
      <button onclick="telecharge('/api/export/immobilisations')">Exporter</button>`);
    const t = d.totaux;
    zone.innerHTML = `
      <div class="grille c4" style="margin-bottom:16px">
        ${indicateur('Valeur brute', fm(t.brut, true))}
        ${indicateur('Amortissements cumulés', fm(t.amortissements, true))}
        ${indicateur('Valeur nette comptable', fm(t.vnc, true), '', 'accent')}
        ${indicateur('Dotation de l\'exercice', fm(t.dotation, true))}
      </div>
      ${carte('', tableau([
        { titre: 'Code', cle: 'code' },
        { titre: 'Désignation', rendu: (i) => `<strong>${ech(i.designation)}</strong>` },
        { titre: 'Compte', cle: 'compte' },
        { titre: 'Acquisition', rendu: (i) => fdate(i.date_acquisition) },
        { titre: 'Valeur brute', classe: 'num', rendu: (i) => fm(i.valeur_acquisition) },
        { titre: 'Durée', classe: 'num', rendu: (i) => `${i.duree_mois} mois` },
        { titre: 'Mode', cle: 'mode' },
        { titre: 'Dotation', classe: 'num', rendu: (i) => fm(i.dotation_annee) },
        { titre: 'Cumul', classe: 'num', rendu: (i) => fm(i.cumul_amortissement) },
        { titre: 'VNC', classe: 'num', rendu: (i) => `<strong>${fm(i.vnc)}</strong>` },
        { titre: 'Statut', rendu: (i) => etiquette(i.statut) },
        {
          titre: '', classe: 'num',
          rendu: (i) => `<button class="petit-bouton" onclick="editeImmo(${i.id})">Modifier</button>
            ${i.statut === 'en_service' ? `<button class="petit-bouton" onclick="cedeImmo(${i.id})">Céder</button>` : ''}`,
        },
      ], d.immobilisations, {
        icone: '🖥️',
        messageVide: 'Aucune immobilisation. Enregistrez vos véhicules, matériels et aménagements.',
      }), '', true)}`;
  },
};

async function editeImmo(id) {
  const champs = [
    { nom: 'designation', libelle: 'Désignation', requis: true, large: true },
    { nom: 'code', libelle: 'Code' },
    { nom: 'compte', libelle: 'Compte d\'immobilisation', type: 'select', requis: true, options: await optionsComptes('2') },
    { nom: 'date_acquisition', libelle: 'Date d\'acquisition', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'date_mise_service', libelle: 'Date de mise en service', type: 'date' },
    { nom: 'valeur_acquisition', libelle: 'Valeur d\'acquisition HT', type: 'montant', requis: true },
    { nom: 'valeur_residuelle', libelle: 'Valeur résiduelle', type: 'montant' },
    { nom: 'duree_mois', libelle: 'Durée d\'amortissement (mois)', type: 'number', defaut: 60 },
    {
      nom: 'mode', libelle: 'Mode', type: 'select', vide: false,
      options: [['lineaire', 'Linéaire'], ['degressif', 'Dégressif']],
    },
    { nom: 'coefficient', libelle: 'Coefficient dégressif (millièmes)', type: 'number', defaut: 1000, aide: '1500 = coefficient 1,5' },
    ...(id ? [] : [
      { groupe: 'Comptabilisation de l\'acquisition' },
      {
        nom: 'comptabiliser', libelle: 'Générer l\'écriture d\'acquisition', type: 'case',
        aide: 'À décocher si l\'achat a déjà été saisi via une facture fournisseur.',
      },
      { nom: 'fournisseur_id', libelle: 'Fournisseur', type: 'select', options: await optionsTiers('fournisseur') },
      { nom: 'taux_tva', libelle: 'TVA récupérable', type: 'taux', defaut: 1900 },
      { nom: 'piece', libelle: 'N° de la facture d\'achat' },
    ]),
  ];
  const existant = id ? await api(`/api/immobilisations/${id}`) : {};
  modale({
    titre: id ? 'Modifier l\'immobilisation' : 'Nouvelle immobilisation',
    contenu: formulaire(champs, existant), large: true,
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Enregistrer', classe: 'primaire',
      action: async (r) => {
        const donnees = litFormulaire(r, champs);
        if (id) await envoie(`/api/immobilisations/${id}`, donnees, 'PUT');
        else await envoie('/api/immobilisations', donnees);
        notifie('Immobilisation enregistrée.', 'succes');
        afficheRoute();
      },
    }],
  });
}

async function lanceDotations() {
  try {
    const r = await envoie('/api/immobilisations/dotations', { exercice_id: App.etat.exercice.id });
    notifie(r.message || `${r.dotations} dotation(s) comptabilisée(s) — ${fm(r.montant, true)}.`, 'succes');
    afficheRoute();
  } catch (err) { erreur(err); }
}

async function cedeImmo(id) {
  const champs = [
    { nom: 'date', libelle: 'Date de cession', type: 'date', requis: true, defaut: aujourdhui() },
    { nom: 'valeur_cession', libelle: 'Prix de cession', type: 'montant' },
    { nom: 'acquereur_id', libelle: 'Acquéreur', type: 'select', options: await optionsTiers() },
  ];
  modale({
    titre: 'Céder l\'immobilisation',
    contenu: formulaire(champs),
    boutons: [{ libelle: 'Annuler' }, {
      libelle: 'Comptabiliser la cession', classe: 'primaire',
      action: async (r) => {
        const d = await api(`/api/immobilisations/${id}/ceder`, {
          method: 'POST', corps: litFormulaire(r, champs),
        });
        notifie(`Cession enregistrée — VNC ${fm(d.vnc, true)}, `
          + `${d.plus_value >= 0 ? 'plus-value' : 'moins-value'} ${fm(Math.abs(d.plus_value), true)}.`,
          'succes', 6000);
        afficheRoute();
      },
    }],
  });
}

/* ------------------------------------------------- Barème progressif ---- */

/* Un barème est une suite de tranches : « jusqu'à X, tel taux », la dernière
   valant « au-delà ». On le saisit tranche par tranche plutôt qu'en JSON —
   c'est un comptable qui le recopie de la loi de finances, pas un
   informaticien. */

function lignesBareme(tranches) {
  const rangs = tranches.length ? tranches : [{ plafond: 0, taux: 0 }, { plafond: null, taux: 0 }];
  return `<table class="donnees" style="margin:0">
    <thead><tr><th>Jusqu'à (DA/mois)</th><th class="num" style="width:90px">Taux %</th>
      <th style="width:34px"></th></tr></thead>
    <tbody>${rangs.map((t, i) => {
      const derniere = t.plafond === null || t.plafond === undefined;
      return `<tr data-tranche>
        <td>${derniere
          ? '<em class="discret">Au-delà</em><input type="hidden" data-plafond value="">'
          : `<input class="num" data-plafond value="${ech(pourChamp(t.plafond))}">`}</td>
        <td><input class="num" data-taux value="${ech(ft(t.taux))}"></td>
        <td>${derniere ? ''
          : `<button class="petit-bouton danger" onclick="retireTrancheBareme(this)"
               title="Retirer cette tranche">×</button>`}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

/** Relit les tranches saisies, dans l'ordre des montants. */
function litBareme(cle) {
  const zone = document.querySelector(`[data-bareme="${cle}"]`);
  if (!zone) return null;
  const tranches = [...zone.querySelectorAll('[data-tranche]')].map((tr) => {
    const brut = tr.querySelector('[data-plafond]').value;
    const taux = Math.round(
      parseFloat(String(tr.querySelector('[data-taux]').value).replace(',', '.') || 0) * 100);
    return { plafond: String(brut).trim() === '' ? null : cts(brut), taux };
  });
  // La tranche ouverte se place toujours en dernier, quel que soit l'ordre
  // de saisie ; les autres se rangent par montant croissant.
  const finies = tranches.filter((t) => t.plafond !== null)
                         .sort((a, b) => a.plafond - b.plafond);
  const ouverte = tranches.find((t) => t.plafond === null);
  return ouverte ? [...finies, ouverte] : finies;
}

function ajouteTrancheBareme(cle) {
  const zone = document.querySelector(`[data-bareme="${cle}"]`);
  const tranches = litBareme(cle) || [];
  const finies = tranches.filter((t) => t.plafond !== null);
  const ouverte = tranches.find((t) => t.plafond === null) || { plafond: null, taux: 0 };
  const dernier = finies.length ? finies[finies.length - 1].plafond : 0;
  finies.push({ plafond: dernier, taux: ouverte.taux });
  zone.innerHTML = lignesBareme([...finies, ouverte]);
}

function retireTrancheBareme(bouton) {
  const ligne = bouton.closest('[data-tranche]');
  const zone = bouton.closest('[data-bareme]');
  ligne.remove();
  // Une seule tranche restante n'aurait plus de sens : on garde l'ouverte.
  if (!zone.querySelectorAll('[data-tranche]').length) {
    zone.innerHTML = lignesBareme([{ plafond: null, taux: 0 }]);
  }
}
