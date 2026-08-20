"""Documents imprimables (HTML prêt pour impression / PDF via le navigateur).

Les factures reprennent les mentions obligatoires exigées en Algérie :
identité complète et NIF/NIS/RC/article d'imposition du vendeur et du client,
numéro et date de facture, désignation, prix unitaire, TVA par taux, montant
en toutes lettres, mode de règlement et droit de timbre le cas échéant.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from noyau import base as db
from noyau import util
from noyau.serveur import ErreurApplicative, route, Reponse

STYLE = """
@page { size: A4; margin: 14mm 12mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; color: #16212b;
       margin: 0; background: #f2f4f6; }
.feuille { background: #fff; width: 190mm; min-height: 275mm; margin: 10px auto;
           padding: 12mm; box-shadow: 0 1px 10px rgba(0,0,0,.15); }
h1 { font-size: 20px; margin: 0 0 2px; letter-spacing: .5px; }
h2 { font-size: 13px; margin: 16px 0 6px; padding-bottom: 3px;
     border-bottom: 1.5px solid #1f4e5f; color: #1f4e5f; text-transform: uppercase;
     letter-spacing: .6px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0; }
th { background: #1f4e5f; color: #fff; padding: 6px 7px; text-align: left;
     font-size: 10px; text-transform: uppercase; letter-spacing: .4px; }
td { padding: 5px 7px; border-bottom: 1px solid #dde3e8; vertical-align: top; }
tr:nth-child(even) td { background: #fafbfc; }
.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.centre { text-align: center; }
table.releve { table-layout: fixed; }
table.releve td { font-size: 10px; }
/* Un relevé de compte tient parfois sur trois pages : les en-têtes de
   colonnes doivent revenir en haut de chacune, et un mouvement ne doit
   pas se couper en deux. */
@media print { thead { display: table-header-group; }
               tr { break-inside: avoid; } }
.entete { display: flex; justify-content: space-between; gap: 16px;
          border-bottom: 2.5px solid #1f4e5f; padding-bottom: 10px; }
.entete .societe { max-width: 62%; }
.entete .doc { text-align: right; }
.badge { display: inline-block; background: #1f4e5f; color: #fff; padding: 5px 12px;
         border-radius: 3px; font-size: 13px; font-weight: 700; letter-spacing: .5px; }
.mentions { font-size: 9.5px; color: #4a5a68; line-height: 1.5; }
.parties { display: flex; gap: 12px; margin: 14px 0; }
.partie { flex: 1; border: 1px solid #cfd8de; border-radius: 4px; padding: 9px 11px; }
.partie h3 { margin: 0 0 5px; font-size: 10px; text-transform: uppercase;
             color: #1f4e5f; letter-spacing: .5px; }
.totaux { width: 62mm; margin-left: auto; }
.totaux td { border: none; padding: 3px 7px; }
.totaux .final td { border-top: 2px solid #1f4e5f; font-weight: 700; font-size: 13px;
                    padding-top: 6px; }
.lettres { margin: 10px 0; padding: 8px 11px; background: #eef3f5;
           border-left: 3px solid #1f4e5f; font-style: italic; }
.signature { display: flex; justify-content: space-between; margin-top: 26px; }
.signature div { width: 62mm; text-align: center; }
.signature .ligne { margin-top: 20mm; border-top: 1px solid #8a97a2; padding-top: 4px;
                    font-size: 10px; }
.pied { margin-top: 16px; padding-top: 8px; border-top: 1px solid #dde3e8;
        font-size: 9px; color: #6b7a86; text-align: center; line-height: 1.5; }
.outils { text-align: center; padding: 10px; }
.outils button { background: #1f4e5f; color: #fff; border: 0; padding: 9px 22px;
                 border-radius: 4px; font-size: 13px; cursor: pointer; }
.total-ligne td { font-weight: 700; background: #eef3f5 !important; }
@media print { body { background: #fff; } .feuille { box-shadow: none; margin: 0;
               width: auto; padding: 0; } .outils { display: none; } }
"""


def e(valeur) -> str:
    return escape(str(valeur)) if valeur not in (None, "") else ""


def montant(cts) -> str:
    return util.formate_montant(cts, "")


def page(titre: str, corps: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>{e(titre)}</title><style>{STYLE}</style></head>
<body>
<div class="outils"><button onclick="window.print()">Imprimer / Enregistrer en PDF</button></div>
<div class="feuille">{corps}</div>
</body></html>"""


def reponse_html(html: str) -> Reponse:
    return Reponse(html.encode("utf-8"), "text/html; charset=utf-8")


def bloc_societe(soc: dict) -> str:
    identifiants = " · ".join(filter(None, [
        f"NIF : {e(soc.get('nif'))}" if soc.get("nif") else "",
        f"NIS : {e(soc.get('nis'))}" if soc.get("nis") else "",
        f"RC : {e(soc.get('rc'))}" if soc.get("rc") else "",
        f"Art. imposition : {e(soc.get('article_imposition'))}"
        if soc.get("article_imposition") else "",
    ]))
    contact = " · ".join(filter(None, [
        e(soc.get("telephone")), e(soc.get("email")),
    ]))
    return f"""<div class="societe">
      <h1>{e(soc.get('raison_sociale'))}</h1>
      <div class="mentions">
        {e(soc.get('forme_juridique'))}{' au capital de ' + montant(soc.get('capital_cts')) + ' DA' if soc.get('capital_cts') else ''}<br>
        {e(soc.get('adresse'))}{', ' + e(soc.get('commune')) if soc.get('commune') else ''}
        {' — ' + e(soc.get('wilaya')) if soc.get('wilaya') else ''}<br>
        {contact}<br>{identifiants}
      </div></div>"""


def bloc_tiers(titre: str, t: dict | None) -> str:
    if not t:
        return f'<div class="partie"><h3>{e(titre)}</h3><div class="mentions">—</div></div>'
    identifiants = "<br>".join(filter(None, [
        f"NIF : {e(t.get('nif'))}" if t.get("nif") else "",
        f"RC : {e(t.get('rc'))}" if t.get("rc") else "",
        f"Art. imposition : {e(t.get('article_imposition'))}"
        if t.get("article_imposition") else "",
        f"Pièce d'identité : {e(t.get('piece_identite'))}" if t.get("piece_identite") else "",
    ]))
    return f"""<div class="partie"><h3>{e(titre)}</h3>
      <strong>{e(t.get('raison_sociale'))}</strong>
      <div class="mentions">{e(t.get('adresse'))}
      {'<br>' + e(t.get('commune')) if t.get('commune') else ''}
      {' — ' + e(t.get('wilaya')) if t.get('wilaya') else ''}
      {'<br>Tél. : ' + e(t.get('telephone')) if t.get('telephone') else ''}
      {'<br>' + identifiants if identifiants else ''}</div></div>"""


# ---------------------------------------------------------------------------
# Facture
# ---------------------------------------------------------------------------

TITRES_FACTURE = {
    "vente": "FACTURE", "achat": "FACTURE FOURNISSEUR",
    "avoir_vente": "FACTURE D'AVOIR", "avoir_achat": "AVOIR FOURNISSEUR",
    "proforma": "FACTURE PROFORMA",
}


def facture_html(f: dict) -> str:
    soc = f.get("societe") or {}
    tiers = f.get("tiers") or {}
    titre = TITRES_FACTURE.get(f["sens"], "FACTURE")

    rangs = []
    for l in f["lignes"]:
        quantite = l["quantite"] / 1000
        rangs.append(f"""<tr>
          <td>{e(l['designation'])}</td>
          <td class="num">{quantite:.2f}</td>
          <td>{e(l['unite'] or '')}</td>
          <td class="num">{montant(l['prix_unitaire'])}</td>
          <td class="num">{util.taux_pourcent(l['remise_taux']):g} %</td>
          <td class="num">{util.taux_pourcent(l['taux_tva']):g} %</td>
          <td class="num">{montant(l['montant_ht'])}</td></tr>""")

    # Récapitulatif de TVA par taux (mention obligatoire)
    par_taux: dict[int, dict] = {}
    for l in f["lignes"]:
        entree = par_taux.setdefault(l["taux_tva"], {"base": 0, "tva": 0})
        entree["base"] += l["montant_ht"]
        entree["tva"] += l["montant_tva"]
    recap = "".join(
        f"<tr><td class='num'>{util.taux_pourcent(taux):g} %</td>"
        f"<td class='num'>{montant(v['base'])}</td>"
        f"<td class='num'>{montant(v['tva'])}</td></tr>"
        for taux, v in sorted(par_taux.items())
    )

    timbre = (f"<tr><td>Droit de timbre</td><td class='num'>{montant(f['timbre'])}</td></tr>"
              if f["timbre"] else "")
    echeance = (f"<div>Échéance : <strong>{util.date_fr(f['date_echeance'])}</strong></div>"
                if f.get("date_echeance") else "")

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">{titre}</div>
        <div style="margin-top:8px;font-size:14px"><strong>N° {e(f['numero'])}</strong></div>
        <div>Date : <strong>{util.date_fr(f['date'])}</strong></div>{echeance}
        {'<div>Réf. : ' + e(f['reference']) + '</div>' if f.get('reference') else ''}
      </div></div>

    <div class="parties">
      {bloc_tiers('Vendeur' if f['sens'] in ('vente','avoir_vente','proforma') else 'Fournisseur',
                  soc if f['sens'] in ('vente','avoir_vente','proforma') else tiers)}
      {bloc_tiers('Client' if f['sens'] in ('vente','avoir_vente','proforma') else 'Acheteur',
                  tiers if f['sens'] in ('vente','avoir_vente','proforma') else soc)}
    </div>

    {'<div><strong>Objet :</strong> ' + e(f['objet']) + '</div>' if f.get('objet') else ''}

    <table><thead><tr>
      <th style="width:40%">Désignation</th><th class="num">Quantité</th><th>Unité</th>
      <th class="num">P.U. HT</th><th class="num">Remise</th><th class="num">TVA</th>
      <th class="num">Montant HT</th></tr></thead>
      <tbody>{''.join(rangs)}</tbody></table>

    <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:1">
        <h2 style="margin-top:4px">Récapitulatif de TVA</h2>
        <table><thead><tr><th class="num">Taux</th><th class="num">Base HT</th>
          <th class="num">Montant TVA</th></tr></thead><tbody>{recap}</tbody></table>
      </div>
      <table class="totaux">
        <tr><td>Total HT</td><td class="num">{montant(f['montant_ht'])}</td></tr>
        <tr><td>Total TVA</td><td class="num">{montant(f['montant_tva'])}</td></tr>
        <tr><td>Total TTC</td><td class="num">{montant(f['montant_ttc'])}</td></tr>
        {timbre}
        <tr class="final"><td>NET À PAYER</td>
            <td class="num">{montant(f['net_a_payer'])} DA</td></tr>
      </table>
    </div>

    <div class="lettres">Arrêtée la présente facture à la somme de :
      <strong>{e(util.montant_en_lettres(f['net_a_payer']))}</strong>.</div>

    {'<div class="mentions"><strong>Mode de règlement :</strong> ' + e(f['mode_reglement']) + '</div>' if f.get('mode_reglement') else ''}
    {'<div class="mentions">' + e(f['conditions']) + '</div>' if f.get('conditions') else ''}
    {'<div class="mentions">' + e(f['notes']) + '</div>' if f.get('notes') else ''}

    <div class="signature">
      <div><div class="ligne">Le client (mention « Reçu »)</div></div>
      <div><div class="ligne">Cachet et signature</div></div>
    </div>

    <div class="pied">
      {e(soc.get('raison_sociale'))} — {e(soc.get('adresse'))}<br>
      {'Banque : ' + e(soc.get('banque_nom')) + ' — RIB : ' + e(soc.get('banque_rib')) if soc.get('banque_rib') else ''}
    </div>"""
    return page(f"{titre} {f['numero']}", corps)


# ---------------------------------------------------------------------------
# Quittance de loyer
# ---------------------------------------------------------------------------

@route("GET", "/api/quittances/<id>/impression")
def api_quittance(ctx):
    identifiant = int(ctx.params["id"])
    q = db.ligne(
        "SELECT q.*, b.numero AS bail_numero, b.usage, b.jour_echeance, "
        "  bi.designation AS bien, bi.adresse AS bien_adresse, bi.commune AS bien_commune, "
        "  p.raison_sociale AS proprietaire, p.adresse AS proprietaire_adresse, "
        "  l.raison_sociale AS locataire, l.adresse AS locataire_adresse "
        "FROM quittances q JOIN baux b ON b.id = q.bail_id "
        "LEFT JOIN biens bi ON bi.id = b.bien_id "
        "LEFT JOIN tiers p ON p.id = b.proprietaire_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id WHERE q.id = ?", (identifiant,))
    if not q:
        raise ErreurApplicative("Quittance introuvable.", 404)
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (q["societe_id"],))

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">QUITTANCE DE LOYER</div>
        <div style="margin-top:8px;font-size:14px"><strong>N° {e(q['numero'])}</strong></div>
        <div>Période : <strong>{e(util.libelle_periode(q['periode']))}</strong></div>
        <div>Échéance : {util.date_fr(q['date_echeance'])}</div>
      </div></div>

    <div class="parties">
      <div class="partie"><h3>Propriétaire (bailleur)</h3>
        <strong>{e(q['proprietaire'])}</strong>
        <div class="mentions">{e(q['proprietaire_adresse'])}</div></div>
      <div class="partie"><h3>Locataire</h3>
        <strong>{e(q['locataire'])}</strong>
        <div class="mentions">{e(q['locataire_adresse'])}</div></div>
    </div>

    <h2>Bien loué</h2>
    <div>{e(q['bien'])} — {e(q['bien_adresse'])} {e(q['bien_commune'])}<br>
      <span class="mentions">Bail n° {e(q['bail_numero'])} — usage {e(q['usage'])}</span></div>

    <h2>Détail</h2>
    <table><thead><tr><th>Désignation</th><th class="num">Montant</th></tr></thead>
      <tbody>
        <tr><td>Loyer — {e(util.libelle_periode(q['periode']))}</td>
            <td class="num">{montant(q['loyer'])}</td></tr>
        {'<tr><td>Charges locatives</td><td class="num">' + montant(q['charges']) + '</td></tr>' if q['charges'] else ''}
        <tr class="total-ligne"><td>TOTAL</td><td class="num">{montant(q['total'])} DA</td></tr>
      </tbody></table>

    <div class="lettres">Reçu de {e(q['locataire'])} la somme de
      <strong>{e(util.montant_en_lettres(q['montant_encaisse'] or q['total']))}</strong>
      au titre du loyer et charges de {e(util.libelle_periode(q['periode']))}.</div>

    <div class="mentions">La présente quittance annule tous reçus antérieurs pour la
      même période. Elle ne vaut pas preuve du paiement des périodes précédentes.</div>

    <div class="signature">
      <div><div class="ligne">Fait à {e(soc.get('commune'))},
        le {util.date_fr(q['date_encaissement'] or util.aujourdhui())}</div></div>
      <div><div class="ligne">Pour le bailleur — cachet et signature</div></div>
    </div>"""
    return reponse_html(page(f"Quittance {q['numero']}", corps))


# ---------------------------------------------------------------------------
# Échéancier VSP / appel de fonds
# ---------------------------------------------------------------------------

@route("GET", "/api/contrats-vsp/<id>/impression")
def api_echeancier(ctx):
    from modules import promotion
    identifiant = int(ctx.params["id"])
    c = promotion.api_contrat(ctx)
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (c["societe_id"],))
    acquereur = db.ligne("SELECT * FROM tiers WHERE id = ?", (c["acquereur_id"],))

    rangs = []
    for ech in c["echeances"]:
        declencheur = {
            "date": f"Date : {util.date_fr(ech['date_prevue'])}" if ech["date_prevue"] else "Date",
            "avancement": f"Avancement ≥ {util.taux_pourcent(ech['seuil_avancement']):g} %",
            "livraison": "À la remise des clés",
        }.get(ech["declencheur"], ech["declencheur"])
        rangs.append(f"""<tr>
          <td>{e(ech['libelle'])}</td>
          <td>{e(declencheur)}</td>
          <td class="num">{util.taux_pourcent(ech['pourcentage']):g} %</td>
          <td class="num">{montant(ech['montant'])}</td>
          <td class="num">{montant(ech['montant_regle'])}</td>
          <td class="num">{montant(ech['montant'] - ech['montant_regle'])}</td>
          <td>{e(ech['statut'])}</td></tr>""")

    fgcmpi = ("<div class='mentions'>Garantie FGCMPI n° "
              + e(c["fgcmpi_numero"]) + "</div>") if c["fgcmpi_atteste"] else (
        "<div class='mentions' style='color:#a4362f'><strong>Attention :</strong> "
        "l'attestation de garantie FGCMPI n'est pas enregistrée pour ce contrat. "
        "Elle est obligatoire pour la vente sur plan.</div>")

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">ÉCHÉANCIER DE PAIEMENT</div>
        <div style="margin-top:8px;font-size:14px">
          <strong>Contrat n° {e(c['numero'])}</strong></div>
        <div>Date : {util.date_fr(c['date_contrat'])}</div>
        <div>{e(c['type_contrat'].upper())}</div>
      </div></div>

    <div class="parties">
      {bloc_tiers('Promoteur (vendeur)', soc)}
      {bloc_tiers('Acquéreur', acquereur)}
    </div>

    <h2>Bien vendu</h2>
    <table><tbody>
      <tr><td style="width:34%"><strong>Programme</strong></td>
          <td>{e(c['programme'])} ({e(c['programme_code'])})</td></tr>
      <tr><td><strong>Adresse</strong></td><td>{e(c['programme_adresse'])}</td></tr>
      <tr><td><strong>Lot</strong></td><td>n° {e(c['lot_numero'])} —
          {e(c['type_lot'])} {e(c['typologie'] or '')}
          {' — bâtiment ' + e(c['batiment']) if c.get('batiment') else ''}
          {' — étage ' + e(c['etage']) if c.get('etage') else ''}</td></tr>
      <tr><td><strong>Surface habitable</strong></td>
          <td>{c['surface_habitable'] / 100:.2f} m²</td></tr>
      <tr><td><strong>Prix de vente (TTC)</strong></td>
          <td><strong>{montant(c['prix_total'])} DA</strong>
          <span class="mentions"> — dont TVA {montant(c['tva'])} DA
          ({util.taux_pourcent(c['taux_tva']):g} %)</span></td></tr>
      {'<tr><td><strong>Acte notarié</strong></td><td>' + e(c['num_acte_notarie']) + '</td></tr>' if c.get('num_acte_notarie') else ''}
    </tbody></table>

    <h2>Échéancier</h2>
    <table><thead><tr>
      <th style="width:30%">Échéance</th><th>Déclencheur</th><th class="num">%</th>
      <th class="num">Montant</th><th class="num">Réglé</th><th class="num">Reste</th>
      <th>Statut</th></tr></thead>
      <tbody>{''.join(rangs)}
      <tr class="total-ligne"><td colspan="3">TOTAL</td>
        <td class="num">{montant(c['prix_total'])}</td>
        <td class="num">{montant(c['montant_encaisse'])}</td>
        <td class="num">{montant(c['reste_a_encaisser'])}</td><td></td></tr>
      </tbody></table>

    <div class="lettres">Montant total de la vente :
      <strong>{e(util.montant_en_lettres(c['prix_total']))}</strong>.</div>
    {fgcmpi}

    <div class="mentions" style="margin-top:10px">
      Vente régie par la loi n° 11-04 du 17 février 2011 fixant les règles régissant
      l'activité de promotion immobilière. Les versements sont exigibles au fur et à
      mesure de l'avancement des travaux, conformément au contrat notarié.
    </div>

    <div class="signature">
      <div><div class="ligne">L'acquéreur</div></div>
      <div><div class="ligne">Le promoteur</div></div>
    </div>"""
    return reponse_html(page(f"Échéancier {c['numero']}", corps))


# ---------------------------------------------------------------------------
# G50
# ---------------------------------------------------------------------------

@route("GET", "/api/g50/impression")
def api_g50_impression(ctx):
    from modules import fiscalite
    donnees = fiscalite.api_g50(ctx)
    soc = donnees["societe"]

    def ligne(libelle, valeur, gras=False, indice=""):
        style = ' class="total-ligne"' if gras else ""
        return (f"<tr{style}><td>{e(indice)}</td><td>{e(libelle)}</td>"
                f"<td class='num'>{montant(valeur)}</td></tr>")

    tap_bloc = ""
    if donnees["tap_applicable"]:
        tap_bloc = (
            "<h2>Taxe sur l'activité professionnelle</h2><table><tbody>"
            + ligne("Base imposable", donnees["base_tap"])
            + f"<tr><td></td><td>Taux appliqué</td><td class='num'>"
              f"{util.taux_pourcent(donnees['taux_tap']):g} %</td></tr>"
            + ligne("TAP due", donnees["tap"], True) + "</tbody></table>"
        )

    avertissements = "".join(
        f"<div class='mentions' style='color:#8a5a00;background:#fff6e5;"
        f"padding:6px 9px;border-left:3px solid #d99a00;margin:6px 0'>{e(a)}</div>"
        for a in donnees.get("avertissements", [])
    )

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">DÉCLARATION G n° 50</div>
        <div style="margin-top:8px;font-size:14px">
          <strong>{e(util.libelle_periode(donnees['periode']))}</strong></div>
        <div>À déposer avant le <strong>{util.date_fr(donnees['date_limite'])}</strong></div>
      </div></div>

    {avertissements}

    <h2>Chiffre d'affaires</h2>
    <table><tbody>
      {ligne("Chiffre d'affaires taxable", donnees['ca_taxable'])}
      {ligne("Chiffre d'affaires exonéré ou hors champ", donnees['ca_exonere'])}
      {ligne("Chiffre d'affaires total", donnees['ca_total'], True)}
    </tbody></table>

    <h2>Taxe sur la valeur ajoutée</h2>
    <table><tbody>
      {ligne("TVA collectée sur ventes et prestations", donnees['tva_collectee'], False, "A")}
      {ligne("TVA déductible sur biens et services", donnees['tva_deductible_bs'], False, "B")}
      {ligne("TVA déductible sur immobilisations", donnees['tva_deductible_immo'], False, "C")}
      {ligne("Précompte antérieur reporté", donnees['precompte_anterieur'], False, "D")}
      {ligne("TVA à payer (A − B − C − D)", donnees['tva_a_payer'], True, "E")}
      {ligne("Précompte à reporter sur le mois suivant", donnees['precompte_reporte'], False, "F")}
    </tbody></table>

    {tap_bloc}

    <h2>Retenues à la source et autres droits</h2>
    <table><tbody>
      {ligne("IRG / Salaires", donnees['irg_salaires'])}
      {ligne("IRG / Retenues diverses", donnees['irg_ras_autres'])}
      {ligne("Acompte provisionnel IBS", donnees['acompte_ibs'])}
      {ligne("Droit de timbre", donnees['droit_timbre'])}
    </tbody></table>

    <table class="totaux" style="width:80mm">
      <tr class="final"><td>TOTAL À PAYER</td>
        <td class="num">{montant(donnees['total_a_payer'])} DA</td></tr>
    </table>

    <div class="lettres">Soit :
      <strong>{e(util.montant_en_lettres(donnees['total_a_payer']))}</strong>.</div>

    <div class="mentions">Document d'aide à la déclaration établi à partir de la
      comptabilité. Il ne remplace pas l'imprimé officiel de l'administration fiscale :
      reportez ces montants sur la déclaration G n° 50 déposée auprès de votre inspection
      des impôts, après vérification.</div>

    <div class="signature">
      <div><div class="ligne">Le déclarant</div></div>
      <div><div class="ligne">Cachet et signature</div></div>
    </div>"""
    return reponse_html(page(f"G50 {donnees['periode']}", corps))


# ---------------------------------------------------------------------------
# Bulletin de paie
# ---------------------------------------------------------------------------

@route("GET", "/api/bulletins/<id>/impression")
def api_bulletin(ctx):
    import json
    identifiant = int(ctx.params["id"])
    b = db.ligne(
        "SELECT b.*, s.nom, s.prenom, s.matricule, s.poste, s.num_secu, s.date_embauche, "
        "       s.categorie, s.situation_familiale, s.nb_enfants "
        "FROM bulletins b JOIN salaries s ON s.id = b.salarie_id WHERE b.id = ?",
        (identifiant,))
    if not b:
        raise ErreurApplicative("Bulletin introuvable.", 404)
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (b["societe_id"],))
    detail = json.loads(b["detail"]) if b["detail"] else {}

    rangs = [f"""<tr><td>Salaire de base</td>
        <td class="num">{b['jours_travailles'] / 1000:.0f} j</td>
        <td class="num">{montant(b['salaire_base'])}</td><td class="num"></td></tr>"""]
    for prime in detail.get("primes", []):
        rangs.append(f"""<tr><td>{e(prime['libelle'])}
            <span class="mentions">{'(soumise)' if prime['soumis_cnas'] else '(non soumise)'}</span></td>
          <td class="num"></td><td class="num">{montant(prime['montant'])}</td>
          <td class="num"></td></tr>""")
    rangs.append(f"""<tr class="total-ligne"><td>SALAIRE BRUT</td><td></td>
        <td class="num">{montant(b['salaire_brut'])}</td><td class="num"></td></tr>""")
    rangs.append(f"""<tr><td>Cotisation sécurité sociale (CNAS)
        <span class="mentions">base {montant(b['base_cnas'])} ×
        {util.taux_pourcent(detail.get('taux_cnas_salarie', 900)):g} %</span></td>
        <td class="num"></td><td class="num"></td>
        <td class="num">{montant(b['cnas_salarie'])}</td></tr>""")
    rangs.append(f"""<tr><td>IRG / Salaires
        <span class="mentions">base imposable {montant(b['base_irg'])}
        {'— abattement ' + montant(b['abattement_irg']) if b['abattement_irg'] else ''}</span></td>
        <td class="num"></td><td class="num"></td>
        <td class="num">{montant(b['irg'])}</td></tr>""")
    if b["autres_retenues"]:
        rangs.append(f"""<tr><td>Autres retenues</td><td></td><td></td>
            <td class="num">{montant(b['autres_retenues'])}</td></tr>""")

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">BULLETIN DE PAIE</div>
        <div style="margin-top:8px;font-size:14px">
          <strong>{e(util.libelle_periode(b['periode']))}</strong></div>
      </div></div>

    <div class="parties">
      <div class="partie"><h3>Salarié</h3>
        <strong>{e(b['nom'])} {e(b['prenom'])}</strong>
        <div class="mentions">Matricule : {e(b['matricule'])}<br>
          {'N° sécurité sociale : ' + e(b['num_secu']) + '<br>' if b['num_secu'] else ''}
          Poste : {e(b['poste'])}<br>
          {'Catégorie : ' + e(b['categorie']) + '<br>' if b['categorie'] else ''}
          {'Embauché le ' + util.date_fr(b['date_embauche']) if b['date_embauche'] else ''}</div></div>
      <div class="partie"><h3>Situation</h3>
        <div class="mentions">
          Situation familiale : {e(b['situation_familiale'] or '—')}<br>
          Enfants à charge : {b['nb_enfants']}<br>
          Jours travaillés : {b['jours_travailles'] / 1000:.0f}</div></div>
    </div>

    <table><thead><tr><th style="width:50%">Éléments de paie</th>
      <th class="num">Base</th><th class="num">Gains</th>
      <th class="num">Retenues</th></tr></thead>
      <tbody>{''.join(rangs)}</tbody></table>

    <table class="totaux">
      <tr><td>Total des gains</td><td class="num">{montant(b['salaire_brut'])}</td></tr>
      <tr><td>Total des retenues</td>
        <td class="num">{montant(b['cnas_salarie'] + b['irg'] + b['autres_retenues'])}</td></tr>
      <tr class="final"><td>NET À PAYER</td>
        <td class="num">{montant(b['net_a_payer'])} DA</td></tr>
    </table>

    <div class="lettres">Net à payer :
      <strong>{e(util.montant_en_lettres(b['net_a_payer']))}</strong>.</div>

    <div class="mentions">Charges patronales : CNAS
      {montant(b['cnas_patronale'])} DA — coût employeur total :
      {montant(b['cout_employeur'])} DA.<br>
      Conservez ce bulletin sans limitation de durée.</div>

    <div class="signature">
      <div><div class="ligne">Le salarié</div></div>
      <div><div class="ligne">L'employeur</div></div>
    </div>"""
    return reponse_html(page(f"Bulletin {b['matricule']} {b['periode']}", corps))


# ---------------------------------------------------------------------------
# Situation d'un propriétaire (relevé de gestion locative)
# ---------------------------------------------------------------------------

@route("GET", "/api/proprietaires/<id>/releve")
def api_releve_proprietaire(ctx):
    identifiant = int(ctx.params["id"])
    proprietaire = db.ligne("SELECT * FROM tiers WHERE id = ?", (identifiant,))
    if not proprietaire:
        raise ErreurApplicative("Propriétaire introuvable.", 404)
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (proprietaire["societe_id"],))
    du = ctx.arg("du") or f"{util.aujourdhui()[:4]}-01-01"
    au = ctx.arg("au") or util.aujourdhui()

    quittances = db.lignes(
        "SELECT q.*, bi.designation AS bien FROM quittances q "
        "JOIN baux b ON b.id = q.bail_id LEFT JOIN biens bi ON bi.id = b.bien_id "
        "WHERE b.proprietaire_id = ? AND q.periode >= ? AND q.periode <= ? "
        "ORDER BY q.periode", (identifiant, du[:7], au[:7]))

    rangs = "".join(f"""<tr>
        <td>{e(util.libelle_periode(q['periode']))}</td><td>{e(q['bien'])}</td>
        <td class="num">{montant(q['total'])}</td>
        <td class="num">{montant(q['montant_encaisse'])}</td>
        <td class="num">{montant(q['honoraires_gestion_ht'] + q['tva_honoraires'])}</td>
        <td class="num">{montant(q['net_proprietaire'])}</td>
        <td class="num">{montant(q['montant_reverse'])}</td></tr>""" for q in quittances)

    total_du = db.valeur(
        "SELECT COALESCE(SUM(l.credit - l.debit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE l.tiers_id = ? AND l.compte LIKE '467%'", (identifiant,), 0)

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">RELEVÉ DE GESTION LOCATIVE</div>
        <div style="margin-top:8px">Du {util.date_fr(du)} au {util.date_fr(au)}</div>
      </div></div>

    <div class="parties">{bloc_tiers('Propriétaire mandant', proprietaire)}</div>

    <table><thead><tr><th>Période</th><th>Bien</th><th class="num">Loyer dû</th>
      <th class="num">Encaissé</th><th class="num">Honoraires TTC</th>
      <th class="num">Net propriétaire</th><th class="num">Reversé</th></tr></thead>
      <tbody>{rangs}
      <tr class="total-ligne"><td colspan="2">TOTAUX</td>
        <td class="num">{montant(sum(q['total'] for q in quittances))}</td>
        <td class="num">{montant(sum(q['montant_encaisse'] for q in quittances))}</td>
        <td class="num">{montant(sum(q['honoraires_gestion_ht'] + q['tva_honoraires'] for q in quittances))}</td>
        <td class="num">{montant(sum(q['net_proprietaire'] for q in quittances))}</td>
        <td class="num">{montant(sum(q['montant_reverse'] for q in quittances))}</td></tr>
      </tbody></table>

    <table class="totaux">
      <tr class="final"><td>SOLDE EN VOTRE FAVEUR</td>
        <td class="num">{montant(total_du)} DA</td></tr>
    </table>

    <div class="mentions">Ce relevé récapitule les loyers encaissés pour votre compte,
      les honoraires de gestion prélevés et les sommes déjà reversées. Le solde
      correspond aux fonds détenus par l'agence pour votre compte.</div>

    <div class="signature">
      <div><div class="ligne">Le propriétaire</div></div>
      <div><div class="ligne">L'agence</div></div>
    </div>"""
    return reponse_html(page(f"Relevé {proprietaire['raison_sociale']}", corps))


# ---------------------------------------------------------------------------
# Relevé de compte d'un tiers
# ---------------------------------------------------------------------------

#: Un client qui doit depuis plus de trois mois n'appelle pas la même phrase
#: qu'un client à jour : le relevé le dit lui-même, sans qu'on ait à l'écrire.
TITRES_TYPE_TIERS = {
    "client": "Client", "fournisseur": "Fournisseur",
    "mandant": "Propriétaire mandant", "salarie": "Salarié",
    "notaire": "Notaire", "administration": "Administration",
}


@route("GET", "/api/tiers/<id>/releve/impression")
def api_releve_tiers_impression(ctx):
    """Le relevé tel qu'on l'envoie : chaque mouvement, et le solde qui court.

    La balance auxiliaire dit combien un client doit ; elle ne dit pas
    pourquoi. C'est ce document-là qu'on oppose quand le tiers conteste.
    """
    from modules import tiers as mod_tiers
    identifiant = int(ctx.params["id"])
    societe_id = ctx.arg_int("societe") or db.valeur(
        "SELECT societe_id FROM tiers WHERE id = ?", (identifiant,))
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (societe_id,))
    au = ctx.arg("au") or util.aujourdhui()
    du = ctx.arg("du") or f"{au[:4]}-01-01"
    d = mod_tiers.releve_tiers(societe_id, identifiant, du, au,
                               perimetre=ctx.perimetre(),
                               non_lettrees=ctx.arg("non_lettrees") == "1")
    t = d["tiers"]

    rangs = "".join(f"""<tr>
        <td>{e(util.date_fr(m['date']))}</td><td>{e(m['journal'])}</td>
        <td>{e(m['piece'] or m['numero'] or '')}</td>
        <td>{e(m['libelle'] or m['libelle_ecriture'])}</td>
        <td>{e(m['compte'])}</td>
        <td>{e(util.date_fr(m['echeance'])) if m['echeance'] else ''}</td>
        <td class="centre">{e(m['lettrage'] or '')}</td>
        <td class="num">{montant(m['debit']) if m['debit'] else ''}</td>
        <td class="num">{montant(m['credit']) if m['credit'] else ''}</td>
        <td class="num">{montant(m['solde'])}</td></tr>""" for m in d["mouvements"])

    solde = d["solde_final"]
    sens = ("doit encore" if solde > 0 else
            ("est créditeur de" if solde < 0 else "est soldé"))
    age = d["age"]
    retard = age["t31_60"] + age["t61_90"] + age["t90_plus"]

    corps = f"""
    <div class="entete">{bloc_societe(soc)}
      <div class="doc"><div class="badge">RELEVÉ DE COMPTE</div>
        <div style="margin-top:8px">Du {e(util.date_fr(du))} au {e(util.date_fr(au))}</div>
        <div class="mentions">{e(d['libelle_perimetre'])}
        {' · mouvements non lettrés seulement' if d['non_lettrees'] else ''}</div>
      </div></div>

    <div class="parties">{bloc_tiers(
        TITRES_TYPE_TIERS.get(t.get('type'), 'Tiers'), t)}</div>

    <table class="releve"><colgroup>
      <col style="width:8%"><col style="width:4%"><col style="width:11%">
      <col style="width:29%"><col style="width:6%"><col style="width:8%">
      <col style="width:5%"><col style="width:10%"><col style="width:10%">
      <col style="width:9%"></colgroup><thead><tr>
      <th>Date</th><th>Jal</th><th>Pièce</th><th>Libellé</th><th>Compte</th>
      <th>Échéance</th><th class="centre">Lett.</th>
      <th class="num">Débit</th><th class="num">Crédit</th>
      <th class="num">Solde</th></tr></thead>
      <tbody>
        <tr><td colspan="7"><em>Solde au {e(util.date_fr(du))}</em></td>
          <td class="num"></td><td class="num"></td>
          <td class="num">{montant(d['solde_anterieur'])}</td></tr>
        {rangs or '<tr><td colspan="10"><em>Aucun mouvement sur la période.</em></td></tr>'}
        <tr class="total-ligne"><td colspan="7">TOTAUX DE LA PÉRIODE</td>
          <td class="num">{montant(d['total_debit'])}</td>
          <td class="num">{montant(d['total_credit'])}</td>
          <td class="num">{montant(solde)}</td></tr>
      </tbody></table>

    <table class="totaux">
      <tr class="final"><td>SOLDE AU {e(util.date_fr(au))}</td>
        <td class="num">{montant(abs(solde))} DA
          {'(débiteur)' if solde > 0 else ('(créditeur)' if solde < 0 else '')}</td></tr>
    </table>

    {'' if not (age['t0_30'] or retard) else f'''
    <table><thead><tr><th colspan="4">Ancienneté de ce qui reste dû
      (mouvements non lettrés)</th></tr>
      <tr><th class="num">Moins de 30 j</th><th class="num">31 à 60 j</th>
      <th class="num">61 à 90 j</th><th class="num">Plus de 90 j</th></tr></thead>
      <tbody><tr>
        <td class="num">{montant(age['t0_30'])}</td>
        <td class="num">{montant(age['t31_60'])}</td>
        <td class="num">{montant(age['t61_90'])}</td>
        <td class="num">{montant(age['t90_plus'])}</td>
      </tr></tbody></table>'''}

    <div class="mentions">Ce relevé récapitule les mouvements enregistrés dans
      nos livres pour votre compte. Au {e(util.date_fr(au))}, votre compte
      {sens}{' ' + montant(abs(solde)) + ' DA' if solde else ''}.
      {'Nous vous remercions de bien vouloir régulariser cette situation.'
       if solde > 0 else ''}
      Sauf erreur ou omission de notre part ; toute observation est à nous
      adresser dans les quinze jours.</div>

    <div class="signature">
      <div><div class="ligne">Le tiers</div></div>
      <div><div class="ligne">{e(soc.get('raison_sociale'))}</div></div>
    </div>"""
    return reponse_html(page(f"Relevé {t['raison_sociale']}", corps))
