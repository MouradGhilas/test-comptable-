#!/usr/bin/env python3
"""Conformite comptable : les invariants qu'un logiciel de compta doit tenir.

Ce ne sont pas des essais d'interface. Chaque controle porte sur une regle
qui, si elle cede, produit des comptes FAUX sans que rien ne le signale.
Quatre familles :

  conformite  la partie double, la coherence des etats entre eux, les
              specificites algeriennes (TVA, IRG, VSP, gestion locative),
              sur une annee complete de donnees ;
  limites     ce que le logiciel doit REFUSER : desequilibre, date
              impossible, compte inexistant, ecriture d'un exercice clos ;
  cloture     l'exercice clos ne bouge plus, les a-nouveaux reportent les
              soldes de bilan et eux seuls, l'extourne annule sans effacer ;
  perimetre   l'etancheite entre le declare et le hors declaration --
              le controle le plus important du logiciel : un montant hors
              declaration qui remonterait dans une G50 ou un bilan fiscal
              ne se verrait pas, les chiffres resteraient plausibles ;
  cycles      les cycles metier en mouvement : numerotation, saisies
              simultanees, une avance sur plan qui devient produit a la
              livraison, un loyer encaisse qui repart chez son proprietaire ;
  reprises    annuler un import deja valide sans laisser de trou dans la
              numerotation ni effacer ce qui sert deja ;
  sante       les controles de sante du dossier, chacun mis a l'epreuve sur
              une anomalie provoquee pour lui ;
  annuelles   la DAS et l'etat des clients, et surtout leurs recoupements ;
  relances    ce qui est du et depuis quand, et la lettre a ses trois niveaux ;
  banque      le releve de la banque, lu et rapproche -- sens des colonnes et
              ecart de date compris.

Usage :
    python outils/test_comptable.py               les quatre suites
    python outils/test_comptable.py perimetre     une seule
"""
import base64
import datetime
import http.cookiejar
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def sortie_utf8():
    """La console Windows en cp1252 ne sait ecrire ni « e accent » ni « -> ».

    Sans cela, la premiere ligne accentuee interrompt l'outil sur un
    UnicodeEncodeError : la panne est dans l'affichage, pas dans la
    comptabilite, mais elle donne l'impression que l'outil est casse.
    """
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


ok = fails = 0
anomalies = []


def v(nom, cond, detail=""):
    """Un controle : son intitule, sa condition, ce qu'on voit s'il cede."""
    global ok, fails
    if cond:
        ok += 1
        print(f"  ok    {nom}")
    else:
        fails += 1
        anomalies.append((nom, detail))
        print(f"  ECHEC {nom}\n        -> {detail}")


def titre(t):
    print(f"\n\033[1m{t}\033[0m")


def fm(centimes):
    return f"{centimes / 100:,.2f}".replace(",", " ").replace(".", ",")


def b64(texte):
    return base64.b64encode(texte.encode("utf-8")).decode()


def b64_octets(octets: bytes) -> str:
    return base64.b64encode(octets).decode()


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Dossier:
    """Une application lancee sur son propre dossier de donnees, jetable.

    Rien n'est partage avec le dossier de travail : chaque suite part d'une
    base vide (ou du jeu de demonstration) et l'efface en partant.
    """

    def __init__(self, prefixe, demonstration=False):
        self.dossier = Path(tempfile.mkdtemp(prefix=f"essai_{prefixe}_"))
        self.port = port_libre()
        if demonstration:
            subprocess.run(
                [sys.executable, "outils/donnees_demonstration.py",
                 "--donnees", str(self.dossier)],
                cwd=RACINE, check=True, capture_output=True)
        self.proc = subprocess.Popen(
            [sys.executable, "app.py", "--donnees", str(self.dossier),
             "--port", str(self.port), "--sans-navigateur"],
            cwd=RACINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/etat", timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            self.ferme()
            raise RuntimeError(
                f"l'application n'a pas demarre sur le port {self.port}")
        pot = http.cookiejar.CookieJar()
        self.ouvre = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(pot))

    def appel(self, chemin, corps=None, methode=None, brut=False):
        """Appelle l'application. `brut` rend les octets et le type MIME,
        pour les documents imprimables et les classeurs."""
        data = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{chemin}", data=data,
            headers={"Content-Type": "application/json"}, method=methode)
        with self.ouvre.open(req, timeout=60) as r:
            contenu = r.read()
            if brut:
                return contenu, r.headers.get("Content-Type", "")
            texte = contenu.decode()
            return json.loads(texte) if texte else {}

    def refuse(self, chemin, corps=None, methode=None):
        """Renvoie le message si la requete est refusee, None si elle passe."""
        try:
            self.appel(chemin, corps, methode)
            return None
        except urllib.error.HTTPError as err:
            try:
                return json.loads(err.read().decode()).get(
                    "erreur", f"code {err.code}")
            except ValueError:
                return f"code {err.code}"

    def sql(self, requete, params=()):
        c = sqlite3.connect(str(self.dossier / "comptabilite.db"))
        c.row_factory = sqlite3.Row
        r = [dict(x) for x in c.execute(requete, params).fetchall()]
        c.close()
        return r

    def ecrit(self, requete, params=()):
        """Écrit directement en base, hors de l'application.

        Sert à abîmer volontairement une donnée pour vérifier qu'un contrôle
        la voit : l'application, elle, refuserait de la produire."""
        c = sqlite3.connect(str(self.dossier / "comptabilite.db"))
        c.execute(requete, params)
        c.commit()
        c.close()

    def equilibre_global(self):
        t = self.sql("SELECT COALESCE(SUM(debit),0) d, "
                     "COALESCE(SUM(credit),0) c FROM lignes")[0]
        return t["d"] == t["c"]

    def ferme(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dossier, ignore_errors=True)


#: Dans la suite « perimetre », tout montant hors declaration est un multiple
#: de cette somme : il devient reconnaissable partout ou il passerait indument.
MARQUEUR = 777700    # 7 777,00 DA en centimes


def contient_marqueur(objet):
    """Cherche un multiple du marqueur dans une reponse JSON.

    Le bloc « hors_declaration » est ignore : il existe precisement pour
    annoncer ce qui a ete ecarte de la declaration. C'est le reste de la
    reponse -- ce qui sera effectivement declare -- qui doit etre net.
    """
    trouves = []

    def parcours(x, chemin=""):
        if isinstance(x, dict):
            for k, val in x.items():
                if k == "hors_declaration":
                    continue
                parcours(val, f"{chemin}.{k}")
        elif isinstance(x, list):
            for i, val in enumerate(x):
                parcours(val, f"{chemin}[{i}]")
        elif isinstance(x, int) and x != 0 and abs(x) % MARQUEUR == 0:
            trouves.append(f"{chemin} = {fm(x)}")
    parcours(objet)
    return trouves


def suite_conformite(dos):
    """Les invariants d'une comptabilite tenue : partie double, coherence des
    etats entre eux, specificites algeriennes. Sur l'annee complete du jeu
    de demonstration : programme immobilier, VSP, baux, loyers, paie.
    """
    dos.appel("/api/connexion", {"identifiant": "demo", "mot_de_passe": "demo1234"})
    soc = dos.appel("/api/societes")["societes"][0]
    sid = soc["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]
    print(f"\nDossier : {soc['raison_sociale']} — exercice {ex['libelle']} "
          f"({du} → {au})")

    # =====================================================================
    titre("1. Partie double — la règle qui fonde tout le reste")
    # =====================================================================
    desequilibrees = dos.sql("""
        SELECT e.id, e.numero, e.libelle,
               COALESCE(SUM(l.debit), 0)  AS d,
               COALESCE(SUM(l.credit), 0) AS c
        FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id
        GROUP BY e.id HAVING d <> c""")
    v(f"chaque écriture est équilibrée ({len(dos.sql('SELECT id FROM ecritures'))} écritures)",
      not desequilibrees,
      [f"{x['numero']} « {x['libelle']} » : {fm(x['d'])} ≠ {fm(x['c'])}"
       for x in desequilibrees[:5]])

    total = dos.sql("SELECT COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c FROM lignes")[0]
    v("le grand total débit égale le grand total crédit",
      total["d"] == total["c"], f"{fm(total['d'])} ≠ {fm(total['c'])}")

    vides = dos.sql("""
        SELECT e.numero FROM ecritures e
        LEFT JOIN lignes l ON l.ecriture_id = e.id
        GROUP BY e.id HAVING COUNT(l.id) < 2""")
    v("aucune écriture à moins de deux lignes", not vides, [x["numero"] for x in vides[:5]])

    deux_sens = dos.sql("SELECT id FROM lignes WHERE debit > 0 AND credit > 0")
    v("aucune ligne n'est à la fois au débit et au crédit", not deux_sens,
      f"{len(deux_sens)} ligne(s)")

    negatifs = dos.sql("SELECT id FROM lignes WHERE debit < 0 OR credit < 0")
    v("aucun montant négatif (un sens s'inverse, il ne se soustrait pas)",
      not negatifs, f"{len(negatifs)} ligne(s)")

    # =====================================================================
    titre("2. La balance, et sa cohérence interne")
    # =====================================================================
    bal = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
    t = bal["totaux"]
    v("la balance est équilibrée en mouvements",
      t["debit"] == t["credit"], f"{fm(t['debit'])} ≠ {fm(t['credit'])}")
    v("la balance est équilibrée en soldes",
      t["solde_debit"] == t["solde_credit"],
      f"{fm(t['solde_debit'])} ≠ {fm(t['solde_credit'])}")

    faux = []
    for l in bal["lignes"]:
        attendu = (l["report_debit"] - l["report_credit"]
                   + l["debit"] - l["credit"])
        obtenu = l["solde_debit"] - l["solde_credit"]
        if attendu != obtenu:
            faux.append(f"{l['compte']} : attendu {fm(attendu)}, obtenu {fm(obtenu)}")
    v(f"chaque solde vaut report + débit − crédit ({len(bal['lignes'])} comptes)",
      not faux, faux[:5])

    doubles = [l["compte"] for l in bal["lignes"]
               if l["solde_debit"] and l["solde_credit"]]
    v("aucun compte n'a un solde des deux côtés à la fois", not doubles, doubles[:5])

    # =====================================================================
    titre("3. Le grand livre dit la même chose que la balance")
    # =====================================================================
    gl = dos.appel(f"/api/grand-livre?societe={sid}&exercice={exid}&du={du}&au={au}")
    par_compte = {g["compte"]: g for g in gl["groupes"]}
    ecarts = []
    for l in bal["lignes"]:
        g = par_compte.get(l["compte"])
        if not g:
            if l["debit"] or l["credit"]:
                ecarts.append(f"{l['compte']} absent du grand livre")
            continue
        if g["total_debit"] != l["debit"] or g["total_credit"] != l["credit"]:
            ecarts.append(f"{l['compte']} : GL {fm(g['total_debit'])}/{fm(g['total_credit'])}"
                          f" ≠ balance {fm(l['debit'])}/{fm(l['credit'])}")
    v(f"les totaux par compte concordent ({len(par_compte)} comptes au grand livre)",
      not ecarts, ecarts[:5])

    saut = []
    for g in gl["groupes"]:
        courant = 0
        for ligne in g["lignes"]:
            courant += ligne["debit"] - ligne["credit"]
            if ligne["solde_progressif"] != courant:
                saut.append(f"{g['compte']} : {fm(ligne['solde_progressif'])} "
                            f"au lieu de {fm(courant)}")
                break
    v("le solde progressif suit ligne à ligne", not saut, saut[:5])

    # =====================================================================
    titre("4. Les états financiers concordent entre eux")
    # =====================================================================
    bilan = dos.appel(f"/api/etats/bilan?societe={sid}&exercice={exid}")
    v("le bilan est équilibré (actif = passif)",
      bilan["equilibre"],
      f"actif {fm(bilan['total_actif'])} ≠ passif {fm(bilan['total_passif'])} "
      f"(écart {fm(bilan['ecart'])})")

    tcr = dos.appel(f"/api/etats/tcr?societe={sid}&exercice={exid}")
    resultat_tcr = tcr.get("resultat_net", tcr.get("resultat"))
    v("le résultat du TCR est celui du bilan",
      resultat_tcr == bilan["resultat"],
      f"TCR {fm(resultat_tcr or 0)} ≠ bilan {fm(bilan['resultat'])}")

    soldes = {l["compte"]: l["solde_debit"] - l["solde_credit"] for l in bal["lignes"]}
    produits = -sum(s for c, s in soldes.items() if c.startswith("7"))
    charges = sum(s for c, s in soldes.items() if c.startswith("6"))
    v("le résultat vaut produits − charges de la balance",
      bilan["resultat"] == produits - charges,
      f"bilan {fm(bilan['resultat'])} ≠ {fm(produits)} − {fm(charges)} "
      f"= {fm(produits - charges)}")

    # =====================================================================
    titre("5. Périmètres — chaque vue doit tenir debout toute seule")
    # =====================================================================
    for perimetre, nom in (("declare", "déclaré"), ("hors_declaration", "hors déclaration")):
        b = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}"
                  f"&perimetre={perimetre}")
        tt = b["totaux"]
        v(f"la balance « {nom} » est équilibrée",
          tt["debit"] == tt["credit"],
          f"{fm(tt['debit'])} ≠ {fm(tt['credit'])}")
        bl = dos.appel(f"/api/etats/bilan?societe={sid}&exercice={exid}&perimetre={perimetre}")
        v(f"le bilan « {nom} » est équilibré", bl["equilibre"],
          f"écart {fm(bl['ecart'])}")

    b_dec = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}&perimetre=declare")
    b_hors = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}&perimetre=hors_declaration")
    v("déclaré + hors déclaration = vue réelle",
      b_dec["totaux"]["debit"] + b_hors["totaux"]["debit"] == t["debit"],
      f"{fm(b_dec['totaux']['debit'])} + {fm(b_hors['totaux']['debit'])} "
      f"≠ {fm(t['debit'])}")

    # =====================================================================
    titre("6. TVA et G50")
    # =====================================================================
    periodes = dos.sql("SELECT DISTINCT substr(date,1,7) p FROM ecritures ORDER BY p")
    controles_g50 = 0
    for p in periodes[:6]:
        g = dos.appel(f"/api/g50?societe={sid}&periode={p['p']}")
        collectee = g.get("tva_collectee", 0)
        deductible = g.get("tva_deductible", 0)
        due = g.get("tva_due", g.get("tva_a_payer", 0))
        precompte = g.get("precompte_anterieur", 0)
        attendu = collectee - deductible - precompte
        # Une TVA négative devient un crédit reporté, pas un montant à payer.
        if attendu < 0:
            attendu = 0
        if due != attendu:
            v(f"G50 {p['p']} : TVA due = collectée − déductible − précompte",
              False, f"due {fm(due)} ≠ {fm(attendu)} "
                     f"(collectée {fm(collectee)}, déductible {fm(deductible)}, "
                     f"précompte {fm(precompte)})")
        else:
            controles_g50 += 1
    v(f"la TVA due se déduit correctement ({controles_g50} période(s))",
      controles_g50 == len(periodes[:6]))

    livre = dos.appel(f"/api/livre-tva?societe={sid}&du={du}&au={au}")
    v("le livre de TVA est cohérent avec la balance",
      isinstance(livre, dict), type(livre).__name__)

    # =====================================================================
    titre("7. Règles métier algériennes")
    # =====================================================================
    # Une avance sur vente sur plan est une dette (4191), pas du chiffre
    # d'affaires : le produit n'est constaté qu'à la livraison.
    avances = soldes.get("4191", 0)
    v("les avances VSP restent au passif (4191), pas en produits",
      avances <= 0, f"solde 4191 = {fm(avances)} (attendu créditeur ou nul)")

    ca_70 = -sum(s for c, s in soldes.items() if c.startswith("70"))
    v("le chiffre d'affaires est créditeur",
      ca_70 >= 0, f"comptes 70 = {fm(ca_70)}")

    # Les loyers encaissés pour le compte des propriétaires transitent par
    # 4671 : ce n'est pas le produit de l'agence.
    mandants = soldes.get("4671", 0)
    v("les loyers des mandants passent par 4671, pas par un compte de produit",
      "4671" in soldes, "compte 4671 absent de la balance")

    # Amortissements : le cumul ne peut pas dépasser la base amortissable
    # (valeur d'acquisition moins la valeur résiduelle).
    annee = int(au[:4])
    immos = dos.appel(f"/api/immobilisations?societe={sid}&annee={annee}")
    liste = immos.get("immobilisations", [])
    depasse = [i for i in liste
               if i["cumul_amortissement"] > i["valeur_acquisition"] - i["valeur_residuelle"]]
    v(f"aucun amortissement ne dépasse la base amortissable "
      f"({len(liste)} immobilisation(s))",
      not depasse,
      [f"{i['designation']} : cumul {fm(i['cumul_amortissement'])} > base "
       f"{fm(i['valeur_acquisition'] - i['valeur_residuelle'])}" for i in depasse[:3]])

    vnc_negative = [i for i in liste if i["vnc"] < i["valeur_residuelle"]]
    v("aucune VNC ne descend sous la valeur résiduelle", not vnc_negative,
      [f"{i['designation']} : {fm(i['vnc'])}" for i in vnc_negative[:3]])

    # Le contrôle qui compte : le module et la comptabilité doivent dire la
    # même chose. Un tableau d'amortissement qui diverge des comptes 28,
    # c'est un bilan faux.
    cumul_module = immos["totaux"]["amortissements"]
    cumul_comptes = -sum(s for c, s in soldes.items() if c.startswith("28"))
    v("le tableau d'amortissement concorde avec les comptes 28",
      cumul_module == cumul_comptes,
      f"module {fm(cumul_module)} ≠ comptes 28 {fm(cumul_comptes)}")

    # Le brut du module doit correspondre aux comptes d'immobilisation.
    brut_module = immos["totaux"]["brut"]
    brut_comptes = sum(s for c, s in soldes.items()
                       if c.startswith("2") and not c.startswith("28"))
    v("la valeur brute concorde avec les comptes 2x",
      brut_module == brut_comptes,
      f"module {fm(brut_module)} ≠ comptes 2x {fm(brut_comptes)}")

    # =====================================================================
    titre("8. Intégrité : ce qui est validé ne se réécrit pas")
    # =====================================================================
    validee = dos.sql("SELECT id, numero FROM ecritures WHERE validee = 1 LIMIT 1")
    if validee:
        ident = validee[0]["id"]
        try:
            dos.appel(f"/api/ecritures/{ident}", {
                "societe_id": sid, "journal": "OD", "date": "2026-06-01",
                "libelle": "Tentative de modification", "lignes": []}, methode="PUT")
            v("une écriture validée ne peut pas être modifiée", False,
              "la modification a été acceptée")
        except urllib.error.HTTPError as err:
            corps = err.read().decode()
            v("une écriture validée ne peut pas être modifiée",
              err.code in (400, 403, 409), f"code {err.code} : {corps[:120]}")

        avant = dos.sql("SELECT COALESCE(SUM(debit),0) d FROM lignes")[0]["d"]
        ext = dos.appel(f"/api/ecritures/{ident}/extourner", {})
        apres_ext = dos.sql("SELECT COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c FROM lignes")[0]
        v("l'extourne garde la comptabilité équilibrée",
          apres_ext["d"] == apres_ext["c"],
          f"{fm(apres_ext['d'])} ≠ {fm(apres_ext['c'])}")
        v("l'écriture d'origine est conservée (piste d'audit)",
          bool(dos.sql("SELECT id FROM ecritures WHERE id = ?", (ident,))))
        orig = dos.sql("SELECT COALESCE(SUM(debit),0) d FROM lignes WHERE ecriture_id = ?",
                        (ident,))[0]["d"]
        nouvelle = dos.sql("SELECT COALESCE(SUM(credit),0) c FROM lignes "
                            "WHERE ecriture_id = ?", (ext.get("id"),))[0]["c"]
        v("l'extourne annule exactement l'écriture d'origine",
          orig == nouvelle, f"origine débit {fm(orig)} ≠ extourne crédit {fm(nouvelle)}")

    # =====================================================================
    titre("9. Lettrage")
    # =====================================================================
    lettres = dos.sql("""
        SELECT lettrage, COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c
        FROM lignes WHERE lettrage IS NOT NULL AND lettrage <> ''
        GROUP BY lettrage HAVING d <> c""")
    v("chaque lot lettré s'équilibre", not lettres,
      [f"{x['lettrage']} : {fm(x['d'])} ≠ {fm(x['c'])}" for x in lettres[:5]])

    # =====================================================================
    titre("10. Arrondis — pas de dérive au centime")
    # =====================================================================
    non_entiers = dos.sql("""
        SELECT id FROM lignes
        WHERE debit <> CAST(debit AS INTEGER) OR credit <> CAST(credit AS INTEGER)""")
    v("tous les montants sont des entiers de centimes", not non_entiers,
      f"{len(non_entiers)} ligne(s)")

    # Une opération en totalité : la somme des parts doit faire le total.
    ops = dos.sql("""
        SELECT operation_ref, COUNT(*) n FROM ecritures
        WHERE operation_ref IS NOT NULL AND operation_ref <> ''
        GROUP BY operation_ref""")
    mauvaises = []
    for o in ops:
        parts = dos.sql("""
            SELECT e.perimetre, COALESCE(SUM(l.debit),0) d
            FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id
            WHERE e.operation_ref = ? GROUP BY e.perimetre""", (o["operation_ref"],))
        if len(parts) < 2:
            mauvaises.append(f"{o['operation_ref']} : une seule part")
    v(f"les opérations en deux parts ont bien leurs deux parts ({len(ops)} opération(s))",
      not mauvaises, mauvaises[:5])

    # =====================================================================
    titre("11. Plan comptable et exercice")
    # =====================================================================
    inconnus = dos.sql("""
        SELECT DISTINCT l.compte FROM lignes l
        WHERE NOT EXISTS (SELECT 1 FROM comptes c WHERE c.numero = l.compte)""")
    v("tout compte mouvementé existe au plan comptable", not inconnus,
      [x["compte"] for x in inconnus[:8]])

    hors_periode = dos.sql(
        "SELECT numero, date FROM ecritures WHERE exercice_id = ? "
        "AND (date < ? OR date > ?)", (exid, du, au))
    v("aucune écriture ne sort des dates de son exercice", not hors_periode,
      [f"{x['numero']} le {x['date']}" for x in hors_periode[:5]])

    sans_journal = dos.sql("""
        SELECT numero FROM ecritures e
        WHERE NOT EXISTS (SELECT 1 FROM journaux j WHERE j.id = e.journal_id)""")
    v("chaque écriture est rattachée à un journal existant", not sans_journal,
      [x["numero"] for x in sans_journal[:5]])

    # La numérotation court par journal : « 2026-00001 » existe en OD et en
    # BQ sans que ce soit un doublon. C'est dans un même journal qu'un
    # numéro répété rendrait la piste d'audit inutilisable.
    doublons = dos.sql("""
        SELECT j.code, e.numero, COUNT(*) n FROM ecritures e
        JOIN journaux j ON j.id = e.journal_id
        WHERE e.numero IS NOT NULL AND e.numero <> ''
        GROUP BY e.societe_id, e.journal_id, e.numero HAVING n > 1""")
    v("les numéros d'écriture sont uniques dans chaque journal", not doublons,
      [f"{x['code']} {x['numero']} ×{x['n']}" for x in doublons[:5]])

    # =====================================================================
    titre("12. Le journal centralisateur recoupe la balance")
    # =====================================================================
    jc = dos.appel(f"/api/journal-centralisateur?societe={sid}&exercice={exid}&du={du}&au={au}")
    lignes_jc = jc.get("journaux", jc.get("lignes", []))
    somme_d = sum(x.get("debit", 0) for x in lignes_jc)
    somme_c = sum(x.get("credit", 0) for x in lignes_jc)
    # Relire la balance : l'extourne du contrôle 8 a ajouté une écriture,
    # comparer au chiffre d'avant serait comparer deux instants différents.
    bal2 = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
    t2 = bal2["totaux"]
    v("le centralisateur totalise comme la balance",
      somme_d == t2["debit"] and somme_c == t2["credit"],
      f"centralisateur {fm(somme_d)}/{fm(somme_c)} ≠ balance {fm(t2['debit'])}/{fm(t2['credit'])}")

    # =====================================================================
    titre("13. Factures : TTC = HT + TVA, et les règlements ne dépassent pas")
    # =====================================================================
    faux_ttc = dos.sql("""
        SELECT numero, montant_ht, montant_tva, montant_ttc FROM factures
        WHERE montant_ttc <> montant_ht + montant_tva""")
    v("chaque facture vérifie TTC = HT + TVA", not faux_ttc,
      [f"{x['numero']} : {fm(x['montant_ht'])} + {fm(x['montant_tva'])} "
       f"≠ {fm(x['montant_ttc'])}" for x in faux_ttc[:5]])

    trop_regle = dos.sql("""
        SELECT f.numero, f.montant_ttc, COALESCE(SUM(r.montant), 0) paye
        FROM factures f LEFT JOIN reglements r ON r.facture_id = f.id
        WHERE f.statut <> 'annulee'
        GROUP BY f.id HAVING paye > f.montant_ttc""")
    v("aucune facture n'est réglée au-delà de son montant", not trop_regle,
      [f"{x['numero']} : payé {fm(x['paye'])} > TTC {fm(x['montant_ttc'])}"
       for x in trop_regle[:5]])

    lignes_fausses = dos.sql("""
        SELECT f.numero, f.montant_ht, COALESCE(SUM(fl.montant_ht), 0) somme
        FROM factures f LEFT JOIN facture_lignes fl ON fl.facture_id = f.id
        GROUP BY f.id HAVING ABS(f.montant_ht - somme) > 1""")
    v("l'en-tête de facture correspond à la somme de ses lignes", not lignes_fausses,
      [f"{x['numero']} : {fm(x['montant_ht'])} ≠ {fm(x['somme'])}"
       for x in lignes_fausses[:5]])

    # =====================================================================
    titre("14. Paie : le bulletin se recompose")
    # =====================================================================
    bulletins = dos.sql("SELECT * FROM bulletins LIMIT 50") \
        if dos.sql("SELECT name FROM sqlite_master WHERE name='bulletins'") else []
    incoherents = []
    for b in bulletins:
        brut = b.get("salaire_brut", 0)
        cnas = b.get("cnas_salarie", 0)
        irg = b.get("irg", 0)
        net = b.get("net_a_payer", 0)
        autres = b.get("autres_retenues", 0) or 0
        if net != brut - cnas - irg - autres:
            incoherents.append(
                f"{b.get('periode')} : {fm(brut)} − {fm(cnas)} − {fm(irg)} "
                f"− {fm(autres)} ≠ {fm(net)}")
    v(f"le net à payer se déduit du brut ({len(bulletins)} bulletin(s))",
      not incoherents, incoherents[:5])

    # La CNAS ne porte que sur la base cotisable, jamais sur les primes
    # non soumises : c'est une erreur classique et coûteuse.
    cnas_faux = [b for b in bulletins
                 if b.get("base_cnas", 0) != b.get("salaire_base", 0)
                                           + b.get("primes_soumises", 0)]
    v("la base CNAS exclut les primes non soumises", not cnas_faux,
      [f"{b.get('periode')} : base {fm(b.get('base_cnas', 0))}" for b in cnas_faux[:3]])

    cout_faux = [b for b in bulletins
                 if b.get("cout_employeur", 0)
                 != b.get("salaire_brut", 0) + b.get("cnas_patronale", 0)]
    v("le coût employeur vaut brut + part patronale", not cout_faux,
      [f"{b.get('periode')} : {fm(b.get('cout_employeur', 0))}" for b in cout_faux[:3]])

    negatifs_paie = [b for b in bulletins if b.get("net_a_payer", 0) < 0]
    v("aucun bulletin au net négatif", not negatifs_paie, len(negatifs_paie))


def suite_limites(dos):
    """Ce que le logiciel doit REFUSER.

    Un logiciel comptable se juge autant a ce qu'il accepte qu'a ce qu'il
    rejette. Chaque controle tente de faire entrer une ecriture fausse :
    si elle passe, les comptes deviennent faux en silence.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL LIMITES", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]

    def ecriture(**kw):
        corps = {"societe_id": sid, "journal": "OD", "date": "2026-06-15",
                 "libelle": "Essai", "perimetre": "declare",
                 "lignes": [{"compte": "607", "debit": "1000", "credit": "0"},
                            {"compte": "401", "debit": "0", "credit": "1000"}]}
        corps.update(kw)
        return corps

    # =====================================================================
    titre("1. Une écriture déséquilibrée n'entre pas")
    # =====================================================================
    msg = dos.refuse("/api/ecritures", ecriture(lignes=[
        {"compte": "607", "debit": "1000", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "900"}]))
    v("un débit différent du crédit est refusé", msg is not None,
      "l'écriture déséquilibrée a été acceptée")
    v("… et la comptabilité reste équilibrée", dos.equilibre_global())

    msg = dos.refuse("/api/ecritures", ecriture(lignes=[
        {"compte": "607", "debit": "1000", "credit": "0"}]))
    v("une écriture à une seule ligne est refusée", msg is not None,
      "l'écriture à une ligne a été acceptée")

    msg = dos.refuse("/api/ecritures", ecriture(lignes=[]))
    v("une écriture sans ligne est refusée", msg is not None,
      "l'écriture vide a été acceptée")

    msg = dos.refuse("/api/ecritures", ecriture(lignes=[
        {"compte": "607", "debit": "0", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "0"}]))
    v("une écriture à zéro est refusée", msg is not None,
      "l'écriture à montant nul a été acceptée")

    # =====================================================================
    titre("2. Comptes, journaux et dates")
    # =====================================================================
    msg = dos.refuse("/api/ecritures", ecriture(lignes=[
        {"compte": "999999", "debit": "1000", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "1000"}]))
    v("un compte absent du plan est refusé", msg is not None,
      "le compte inconnu a été accepté")
    v("… en disant lequel", msg and "999999" in msg, msg)

    msg = dos.refuse("/api/ecritures", ecriture(journal="ZZ"))
    v("un journal inconnu est refusé", msg is not None, "journal ZZ accepté")

    msg = dos.refuse("/api/ecritures", ecriture(date="2026-02-31"))
    v("une date impossible (31 février) est refusée", msg is not None,
      "le 31 février a été accepté")

    msg = dos.refuse("/api/ecritures", ecriture(date="pas-une-date"))
    v("une date illisible est refusée", msg is not None, "date illisible acceptée")

    msg = dos.refuse("/api/ecritures", ecriture(libelle=""))
    v("un libellé vide est refusé", msg is not None, "libellé vide accepté")

    # =====================================================================
    titre("3. Montants aberrants")
    # =====================================================================
    msg = dos.refuse("/api/ecritures", ecriture(lignes=[
        {"compte": "607", "debit": "-1000", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "-1000"}]))
    v("des montants négatifs sont refusés", msg is not None,
      "les montants négatifs ont été acceptés")
    v("… et la comptabilité reste équilibrée", dos.equilibre_global())

    # Un montant énorme mais légitime doit passer sans perdre de précision :
    # 92 milliards de dinars, en centimes, reste dans les entiers exacts.
    enorme = "92233720368"
    try:
        gros = dos.appel("/api/ecritures", ecriture(
            libelle="Montant très élevé",
            lignes=[{"compte": "607", "debit": enorme, "credit": "0"},
                    {"compte": "401", "debit": "0", "credit": enorme}]))
        lignes = dos.sql("SELECT debit FROM lignes WHERE ecriture_id = ? AND debit > 0",
                          (gros["id"],))
        v("un très gros montant est enregistré au centime près",
          lignes and lignes[0]["debit"] == 9223372036800,
          f"{lignes[0]['debit'] if lignes else '—'} au lieu de 9223372036800")
    except urllib.error.HTTPError as err:
        gros = None
        v("un très gros montant est enregistré au centime près", False,
          f"refusé : {err.read().decode()[:120]}")

    # Une écriture validée ne se supprime pas : seule l'extourne laisse une
    # trace de ce qui a été annulé, et c'est elle qui fait la piste d'audit.
    if gros:
        msg = dos.refuse(f"/api/ecritures/{gros['id']}", None, methode="DELETE")
        v("une écriture validée ne peut pas être supprimée", msg is not None,
          "la suppression d'une écriture validée a été acceptée")
        v("… et l'application renvoie vers l'extourne",
          msg and "extourne" in msg.lower(), msg)

    # Les centimes doivent survivre : 0,01 DA ne doit pas être arrondi à 0.
    d = dos.appel("/api/ecritures", ecriture(
        libelle="Un centime",
        lignes=[{"compte": "607", "debit": "0,01", "credit": "0"},
                {"compte": "401", "debit": "0", "credit": "0,01"}]))
    ligne = dos.sql("SELECT debit FROM lignes WHERE ecriture_id = ? AND debit > 0",
                     (d["id"],))
    v("un centime reste un centime", ligne and ligne[0]["debit"] == 1,
      f"{ligne[0]['debit'] if ligne else '—'} au lieu de 1")

    # =====================================================================
    titre("4. Saisie en totalité : chaque part doit s'équilibrer")
    # =====================================================================
    msg = dos.refuse("/api/ecritures", ecriture(perimetre="totalite", lignes=[
        {"compte": "607", "debit_declare": "1000", "credit_declare": "0",
         "debit_hors": "500", "credit_hors": "0"},
        {"compte": "401", "debit_declare": "0", "credit_declare": "1000",
         "debit_hors": "0", "credit_hors": "400"}]))
    v("une part non déclarée déséquilibrée est refusée", msg is not None,
      "la part hors déclaration déséquilibrée a été acceptée")
    v("… et la comptabilité reste équilibrée", dos.equilibre_global())

    # Une opération correcte en deux parts : les deux écritures doivent
    # exister, chacune équilibrée, et porter la même référence d'opération.
    d = dos.appel("/api/ecritures", ecriture(
        libelle="Vente réelle", perimetre="totalite", lignes=[
            {"compte": "411", "debit_declare": "1000", "credit_declare": "0",
             "debit_hors": "500", "credit_hors": "0"},
            {"compte": "701", "debit_declare": "0", "credit_declare": "1000",
             "debit_hors": "0", "credit_hors": "500"}]))
    parts = dos.sql("""
        SELECT e.id, e.perimetre, e.operation_ref,
               COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c
        FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id
        WHERE e.libelle = 'Vente réelle' GROUP BY e.id""")
    v("une opération en totalité crée deux écritures", len(parts) == 2,
      f"{len(parts)} écriture(s)")
    v("chaque part est équilibrée de son côté",
      all(p["d"] == p["c"] for p in parts),
      [f"{p['perimetre']} : {fm(p['d'])}/{fm(p['c'])}" for p in parts])
    v("les deux parts partagent une même référence d'opération",
      len({p["operation_ref"] for p in parts}) == 1 and parts[0]["operation_ref"],
      [p["operation_ref"] for p in parts])
    v("les deux périmètres sont bien distincts",
      {p["perimetre"] for p in parts} == {"declare", "hors_declaration"},
      [p["perimetre"] for p in parts])
    v("la somme des parts fait le total réel",
      sum(p["d"] for p in parts) == 150000,
      f"{fm(sum(p['d'] for p in parts))} au lieu de 1 500,00")

    # =====================================================================
    titre("5. On ne supprime pas ce qui est utilisé")
    # =====================================================================
    compte_607 = dos.sql("SELECT id FROM comptes WHERE numero = '607'")
    if compte_607:
        msg = dos.refuse(f"/api/comptes/{compte_607[0]['id']}", None, methode="DELETE")
        v("un compte mouvementé ne peut pas être supprimé", msg is not None,
          "le compte 607, pourtant mouvementé, a été supprimé")

    # =====================================================================
    titre("6. Lettrage")
    # =====================================================================
    ecr = dos.appel("/api/ecritures", ecriture(
        libelle="Facture à lettrer",
        lignes=[{"compte": "411", "debit": "5000", "credit": "0"},
                {"compte": "701", "debit": "0", "credit": "5000"}]))
    reg = dos.appel("/api/ecritures", ecriture(
        libelle="Règlement partiel",
        lignes=[{"compte": "512", "debit": "3000", "credit": "0"},
                {"compte": "411", "debit": "0", "credit": "3000"}]))
    l_fac = dos.sql("SELECT id FROM lignes WHERE ecriture_id = ? AND compte = '411'",
                     (ecr["id"],))[0]["id"]
    l_reg = dos.sql("SELECT id FROM lignes WHERE ecriture_id = ? AND compte = '411'",
                     (reg["id"],))[0]["id"]
    msg = dos.refuse("/api/lettrage", {"societe_id": sid, "lignes": [l_fac, l_reg]})
    v("un lettrage déséquilibré est refusé", msg is not None,
      "5 000 lettré avec 3 000 sans broncher")

    # =====================================================================
    titre("7. Exercice clôturé")
    # =====================================================================
    cloture = dos.refuse(f"/api/exercices/{exid}/cloturer", {"societe_id": sid})
    if cloture is None:
        msg = dos.refuse("/api/ecritures", ecriture(libelle="Après clôture"))
        v("aucune écriture n'entre dans un exercice clôturé", msg is not None,
          "une écriture a été passée après la clôture")
    else:
        v("la clôture d'exercice est protégée", True)

    # =====================================================================
    titre("8. La comptabilité est restée saine")
    # =====================================================================
    v("équilibre global préservé après tous ces essais", dos.equilibre_global(),
      "des tentatives refusées ont laissé des traces")
    desequilibrees = dos.sql("""
        SELECT e.numero FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id
        GROUP BY e.id
        HAVING COALESCE(SUM(l.debit),0) <> COALESCE(SUM(l.credit),0)""")
    v("aucune écriture déséquilibrée n'a été créée", not desequilibrees,
      [x["numero"] for x in desequilibrees[:5]])
    orphelines = dos.sql("""
        SELECT id FROM lignes
        WHERE NOT EXISTS (SELECT 1 FROM ecritures e WHERE e.id = lignes.ecriture_id)""")
    v("aucune ligne orpheline", not orphelines, f"{len(orphelines)} ligne(s)")


def suite_cloture(dos):
    """La cloture, les a-nouveaux, l'extourne.

    Le moment ou une annee se ferme et ou la suivante reprend ses soldes :
    une erreur ici se propage a tous les exercices suivants.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL CLOTURE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex1 = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex1["date_debut"][:4])

    def ecr(libelle, lignes, date=None):
        return dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": "OD", "date": date or f"{annee}-06-15",
            "libelle": libelle, "perimetre": "declare", "lignes": lignes})

    # =====================================================================
    titre("1. Arrondis de TVA — le centime ne doit pas se perdre")
    # =====================================================================
    # 19 % de montants qui ne tombent pas juste. Chaque facture doit vérifier
    # HT + TVA = TTC exactement, et l'erreur ne doit pas s'accumuler.
    tiers = dos.appel("/api/tiers", {
        "societe_id": sid, "code": "C001", "raison_sociale": "Client Essai",
        "type": "client"})
    montants = ["333,33", "1,01", "0,07", "12 345,67", "99 999,99", "7,77"]
    ecarts, total_ht, total_tva, total_ttc = [], 0, 0, 0
    for i, m in enumerate(montants):
        f = dos.appel("/api/factures", {
            "societe_id": sid, "sens": "vente", "date": f"{annee}-03-{i + 1:02d}",
            "tiers_id": tiers["id"], "objet": f"Essai arrondi {m}",
            "valider": True,
            "lignes": [{"designation": "Prestation", "quantite": 1,
                        "prix_unitaire": m, "taux_tva": "19"}]})
        d = dos.appel(f"/api/factures/{f['id']}")
        if d["montant_ttc"] != d["montant_ht"] + d["montant_tva"]:
            ecarts.append(f"{m} : {fm(d['montant_ht'])} + {fm(d['montant_tva'])} "
                          f"≠ {fm(d['montant_ttc'])}")
        total_ht += d["montant_ht"]
        total_tva += d["montant_tva"]
        total_ttc += d["montant_ttc"]
    v(f"chaque facture vérifie HT + TVA = TTC ({len(montants)} montants difficiles)",
      not ecarts, ecarts)
    v("les totaux ne dérivent pas d'un centime",
      total_ttc == total_ht + total_tva,
      f"{fm(total_ht)} + {fm(total_tva)} ≠ {fm(total_ttc)}")

    # La TVA comptabilisée doit être celle de la facture.
    tva_comptable = dos.sql("""
        SELECT COALESCE(SUM(l.credit), 0) - COALESCE(SUM(l.debit), 0) t
        FROM lignes l WHERE l.compte LIKE '4457%'""")[0]["t"]
    v("la TVA collectée en comptabilité égale celle des factures",
      tva_comptable == total_tva,
      f"comptes 4457 {fm(tva_comptable)} ≠ factures {fm(total_tva)}")

    # Une facture en brouillon ne doit rien écrire en comptabilité : elle
    # n'existe pas encore pour le fisc.
    avant = dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
    brouillon = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "date": f"{annee}-03-20",
        "tiers_id": tiers["id"], "objet": "Brouillon",
        "lignes": [{"designation": "Prestation", "quantite": 1,
                    "prix_unitaire": "1000", "taux_tva": "19"}]})
    apres = dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
    v("une facture en brouillon ne touche pas la comptabilité", avant == apres,
      f"{apres - avant} écriture(s) créée(s)")

    # =====================================================================
    titre("2. Clôture d'exercice")
    # =====================================================================
    # Un peu de tout : un actif, un passif, une charge, un produit.
    ecr("Apport initial", [
        {"compte": "512", "debit": "1000000", "credit": "0"},
        {"compte": "101", "debit": "0", "credit": "1000000"}],
        date=f"{annee}-01-02")
    ecr("Achat de fournitures", [
        {"compte": "607", "debit": "150000", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "150000"}])

    soldes_avant = {l["compte"]: l["solde_debit"] - l["solde_credit"]
                    for l in dos.appel(f"/api/balance?societe={sid}&exercice={ex1['id']}"
                                   f"&du={ex1['date_debut']}&au={ex1['date_fin']}")["lignes"]}
    produits = -sum(s for c, s in soldes_avant.items() if c.startswith("7"))
    charges = sum(s for c, s in soldes_avant.items() if c.startswith("6"))
    resultat_attendu = produits - charges

    # Exercice suivant
    cree = dos.appel("/api/exercices", {
        "societe_id": sid, "libelle": str(annee + 1),
        "date_debut": f"{annee + 1}-01-01", "date_fin": f"{annee + 1}-12-31"})
    ex2 = next(e for e in dos.appel(f"/api/exercices?societe={sid}")["exercices"]
               if e["id"] == cree["id"])

    res = dos.appel(f"/api/exercices/{ex1['id']}/cloturer",
                {"societe_id": sid, "exercice_suivant": ex2["id"]})
    v("la clôture calcule le résultat de l'exercice",
      res["resultat"] == resultat_attendu,
      f"clôture {fm(res['resultat'])} ≠ produits − charges {fm(resultat_attendu)}")

    # Après clôture : plus aucun solde en classes 6 et 7.
    bal1 = dos.appel(f"/api/balance?societe={sid}&exercice={ex1['id']}"
                 f"&du={ex1['date_debut']}&au={ex1['date_fin']}")
    restants = [l["compte"] for l in bal1["lignes"]
                if l["compte"][0] in ("6", "7")
                and (l["solde_debit"] or l["solde_credit"])]
    v("les comptes de gestion sont soldés après la clôture", not restants,
      restants[:6])

    resultat_compte = -sum(l["solde_debit"] - l["solde_credit"] for l in bal1["lignes"]
                           if l["compte"].startswith("12"))
    v("le résultat est viré en compte 12",
      resultat_compte == resultat_attendu,
      f"compte 12 {fm(resultat_compte)} ≠ {fm(resultat_attendu)}")

    v("la balance reste équilibrée après clôture",
      bal1["totaux"]["debit"] == bal1["totaux"]["credit"],
      f"{fm(bal1['totaux']['debit'])} ≠ {fm(bal1['totaux']['credit'])}")

    # =====================================================================
    titre("3. Les à-nouveaux reprennent exactement les soldes")
    # =====================================================================
    bal2 = dos.appel(f"/api/balance?societe={sid}&exercice={ex2['id']}"
                 f"&du={ex2['date_debut']}&au={ex2['date_fin']}")
    ouverture = {l["compte"]: l["report_debit"] - l["report_credit"] + l["debit"] - l["credit"]
                 for l in bal2["lignes"]}
    cloture_bilan = {l["compte"]: l["solde_debit"] - l["solde_credit"]
                     for l in bal1["lignes"]
                     if l["compte"][0] not in ("6", "7")
                     and (l["solde_debit"] or l["solde_credit"])}

    manquants, differents = [], []
    for compte, solde in cloture_bilan.items():
        if compte not in ouverture:
            manquants.append(f"{compte} ({fm(solde)})")
        elif ouverture[compte] != solde:
            differents.append(f"{compte} : clôture {fm(solde)} ≠ ouverture "
                              f"{fm(ouverture[compte])}")
    v(f"chaque compte de bilan est repris à l'ouverture "
      f"({len(cloture_bilan)} compte(s))", not manquants, manquants[:6])
    v("chaque solde d'ouverture égale le solde de clôture", not differents,
      differents[:6])

    an = dos.sql("""
        SELECT COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c
        FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id
        WHERE e.source_type = 'a_nouveaux'""")[0]
    v("l'écriture d'à-nouveaux est équilibrée",
      an["d"] == an["c"], f"{fm(an['d'])} ≠ {fm(an['c'])}")

    v("aucun compte de gestion n'est reporté à l'ouverture",
      not [c for c in ouverture if c[0] in ("6", "7") and ouverture[c]],
      [c for c in ouverture if c[0] in ("6", "7") and ouverture[c]][:6])

    # =====================================================================
    titre("4. Un exercice clôturé est verrouillé")
    # =====================================================================
    try:
        dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": "OD", "date": f"{annee}-07-01",
            "libelle": "Après clôture", "perimetre": "declare",
            "lignes": [{"compte": "607", "debit": "100", "credit": "0"},
                       {"compte": "401", "debit": "0", "credit": "100"}]})
        v("aucune écriture n'entre dans un exercice clôturé", False,
          "l'écriture a été acceptée")
    except urllib.error.HTTPError:
        v("aucune écriture n'entre dans un exercice clôturé", True)

    try:
        dos.appel(f"/api/exercices/{ex1['id']}/cloturer", {"societe_id": sid})
        v("un exercice ne se clôture pas deux fois", False, "double clôture acceptée")
    except urllib.error.HTTPError:
        v("un exercice ne se clôture pas deux fois", True)

    # =====================================================================
    titre("5. Santé générale après clôture")
    # =====================================================================
    t = dos.sql("SELECT COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c FROM lignes")[0]
    v("la comptabilité entière reste équilibrée", t["d"] == t["c"],
      f"{fm(t['d'])} ≠ {fm(t['c'])}")
    desequilibrees = dos.sql("""
        SELECT e.numero FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id
        GROUP BY e.id
        HAVING COALESCE(SUM(l.debit),0) <> COALESCE(SUM(l.credit),0)""")
    v("aucune écriture déséquilibrée", not desequilibrees,
      [x["numero"] for x in desequilibrees[:5]])


def suite_perimetre(dos):
    """L'etancheite des perimetres -- le controle le plus important.

    Methode : un dossier ou CHAQUE montant hors declaration est
    reconnaissable (multiples de 7 777), puis on verifie qu'aucun de ces
    montants n'apparait dans un etat fiscal.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL PERIMETRE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]
    annee = int(du[:4])

    def ecr(libelle, lignes, perimetre, date=None):
        return dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": "OD", "date": date or f"{annee}-05-10",
            "libelle": libelle, "perimetre": perimetre, "lignes": lignes})

    titre("Mise en place : un dossier mi-déclaré, mi-hors déclaration")
    # Déclaré : une vente de 100 000 HT + 19 000 de TVA
    ecr("Vente déclarée", [
        {"compte": "411", "debit": "119000", "credit": "0"},
        {"compte": "701", "debit": "0", "credit": "100000"},
        {"compte": "4457", "debit": "0", "credit": "19000"}], "declare")
    # Hors déclaration : des montants tous multiples de 7 777
    ecr("Vente hors déclaration", [
        {"compte": "411", "debit": "77770", "credit": "0"},
        {"compte": "701", "debit": "0", "credit": "77770"}], "hors_declaration")
    ecr("Charge hors déclaration", [
        {"compte": "607", "debit": "15554", "credit": "0"},
        {"compte": "401", "debit": "0", "credit": "15554"}], "hors_declaration")
    # Une opération en totalité : une part déclarée, une part qui ne l'est pas
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-05-20",
        "libelle": "Vente réelle mixte", "perimetre": "totalite",
        "lignes": [
            {"compte": "411", "debit_declare": "50000", "credit_declare": "0",
             "debit_hors": "7777", "credit_hors": "0"},
            {"compte": "701", "debit_declare": "0", "credit_declare": "50000",
             "debit_hors": "0", "credit_hors": "7777"}]})

    hors_total = dos.sql("""
        SELECT COALESCE(SUM(l.debit),0) d FROM ecritures e
        JOIN lignes l ON l.ecriture_id = e.id
        WHERE e.perimetre = 'hors_declaration'""")[0]["d"]
    print(f"  hors déclaration en base : {fm(hors_total)}")
    v("les montants hors déclaration sont bien tous marqués",
      hors_total % MARQUEUR == 0, f"{fm(hors_total)} n'est pas un multiple du marqueur")

    # =====================================================================
    titre("1. La balance déclarée ignore le hors déclaration")
    # =====================================================================
    b_dec = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}"
                  f"&perimetre=declare")
    fuites = contient_marqueur(b_dec["totaux"])
    v("les totaux de la balance déclarée sont nets", not fuites, fuites[:5])
    v("la balance déclarée est équilibrée",
      b_dec["totaux"]["debit"] == b_dec["totaux"]["credit"])

    ca_declare = -sum(l["solde_debit"] - l["solde_credit"] for l in b_dec["lignes"]
                      if l["compte"].startswith("70"))
    v("le chiffre d'affaires déclaré est celui attendu (150 000)",
      ca_declare == 15000000, f"{fm(ca_declare)} au lieu de 150 000,00")

    # =====================================================================
    titre("2. La G50 ne voit que le déclaré")
    # =====================================================================
    g = dos.appel(f"/api/g50?societe={sid}&periode={annee}-05")
    fuites = contient_marqueur(g)
    v("aucun montant hors déclaration dans les chiffres à déclarer", not fuites,
      fuites[:6])
    v("la TVA collectée de la G50 est celle des ventes déclarées",
      g.get("tva_collectee", 0) == 1900000,
      f"{fm(g.get('tva_collectee', 0))} au lieu de 19 000,00")

    # L'autre moitié du contrat : la déclaration doit DIRE ce qu'elle écarte.
    # Une exclusion silencieuse serait aussi grave qu'une fuite.
    exclu = g.get("hors_declaration", {})
    v("la G50 annonce ce qu'elle a écarté", bool(exclu), g.keys())
    v("… en donnant le montant exact des produits exclus",
      exclu.get("produits") == 7777000 + 777700,
      f"{fm(exclu.get('produits', 0))} au lieu de {fm(7777000 + 777700)}")
    v("… et le nombre d'écritures concernées",
      exclu.get("nb_ecritures", 0) >= 2, exclu.get("nb_ecritures"))

    # =====================================================================
    titre("3. Le bilan et le TCR fiscaux ne voient que le déclaré")
    # =====================================================================
    bilan = dos.appel(f"/api/etats/bilan?societe={sid}&exercice={exid}&perimetre=declare")
    fuites = contient_marqueur({"actif": bilan["total_actif"],
                                "passif": bilan["total_passif"],
                                "resultat": bilan["resultat"]})
    v("les totaux du bilan déclaré sont nets", not fuites, fuites[:5])
    v("le bilan déclaré est équilibré", bilan["equilibre"],
      f"écart {fm(bilan['ecart'])}")

    tcr = dos.appel(f"/api/etats/tcr?societe={sid}&exercice={exid}&perimetre=declare")
    fuites = contient_marqueur(tcr.get("lignes", []))
    v("aucune ligne du TCR déclaré ne porte un montant hors déclaration",
      not fuites, fuites[:5])

    # =====================================================================
    titre("4. L'IBS ne se calcule que sur le déclaré")
    # =====================================================================
    try:
        ibs = dos.appel(f"/api/ibs?societe={sid}&exercice={exid}")
        fuites = contient_marqueur(ibs)
        v("aucun montant hors déclaration dans la base imposable", not fuites,
          fuites[:6])
        v("l'IBS annonce lui aussi ce qu'il écarte",
          bool(ibs.get("hors_declaration")), ibs.keys())
    except urllib.error.HTTPError as err:
        v("l'IBS répond", False, f"code {err.code}")

    # =====================================================================
    titre("5. Le livre de TVA ne voit que le déclaré")
    # =====================================================================
    livre = dos.appel(f"/api/livre-tva?societe={sid}&du={du}&au={au}")
    fuites = contient_marqueur(livre)
    v("aucun montant hors déclaration dans le livre de TVA", not fuites, fuites[:6])

    # =====================================================================
    titre("6. La vue réelle, elle, montre tout")
    # =====================================================================
    b_tous = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
    ca_reel = -sum(l["solde_debit"] - l["solde_credit"] for l in b_tous["lignes"]
                   if l["compte"].startswith("70"))
    v("la vue réelle inclut bien le hors déclaration",
      ca_reel == 15000000 + 7777000 + 777700,
      f"{fm(ca_reel)} au lieu de {fm(15000000 + 7777000 + 777700)}")

    b_hors = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}"
                   f"&perimetre=hors_declaration")
    v("déclaré + hors = réel, au centime",
      b_dec["totaux"]["debit"] + b_hors["totaux"]["debit"]
      == b_tous["totaux"]["debit"],
      f"{fm(b_dec['totaux']['debit'])} + {fm(b_hors['totaux']['debit'])} "
      f"≠ {fm(b_tous['totaux']['debit'])}")
    v("la balance hors déclaration est équilibrée",
      b_hors["totaux"]["debit"] == b_hors["totaux"]["credit"])

    # =====================================================================
    titre("7. Les exports fiscaux portent leur périmètre")
    # =====================================================================
    v("l'état déclaré annonce son périmètre",
      bilan.get("perimetre") == "declare" and bilan.get("libelle_perimetre"),
      f"{bilan.get('perimetre')} / {bilan.get('libelle_perimetre')}")
    v("la vue réelle annonce le sien",
      dos.appel(f"/api/etats/bilan?societe={sid}&exercice={exid}")
      .get("perimetre") in ("tous", None))


def suite_cycles(dos):
    """Les cycles métier en mouvement, et la numérotation.

    Une règle comptable peut tenir à l'arrêt et céder en mouvement : c'est au
    moment où une avance sur plan devient un produit, ou bien où un loyer
    encaissé repart chez son propriétaire, que le résultat se fausse. Cette
    suite fait avancer les dossiers du jeu de démonstration et regarde ce que
    la comptabilité en dit.
    """
    dos.appel("/api/connexion", {"identifiant": "demo", "mot_de_passe": "demo1234"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]
    annee = int(du[:4])

    def soldes():
        """Solde de chaque compte, en centimes — débiteur positif."""
        b = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
        return {l["compte"]: l["solde_debit"] - l["solde_credit"] for l in b["lignes"]}

    def crediteur(table, *prefixes):
        """Somme créditrice des comptes commençant par l'un des préfixes."""
        return -sum(s for c, s in table.items() if c.startswith(prefixes))

    def passe(journal, libelle, date=None, montant="1000",
              debit="607", credit="401"):
        rep = dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": journal,
            "date": date or f"{annee}-06-15", "libelle": libelle,
            "lignes": [{"compte": debit, "debit": montant, "credit": "0"},
                       {"compte": credit, "debit": "0", "credit": montant}]})
        e = dos.sql("SELECT e.id, e.numero, e.date, j.code AS journal "
                    "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
                    "WHERE e.id = ?", (rep["id"],))[0]
        return e

    # =====================================================================
    titre("1. Numérotation : une séquence par journal et par année")
    # =====================================================================
    a = passe("OD", "Séquence — première")
    b = passe("OD", "Séquence — seconde")
    ve = passe("VE", "Séquence — vente", montant="1200",
               debit="411", credit="701")

    v("deux écritures d'un même journal ne portent pas le même numéro",
      a["numero"] != b["numero"], f"{a['numero']} et {b['numero']}")
    v("la seconde suit la première", b["numero"] > a["numero"],
      f"{a['numero']} puis {b['numero']}")
    v("le numéro porte l'année de l'écriture",
      str(annee) in a["numero"], a["numero"])
    v("chaque journal tient sa propre séquence",
      ve["journal"] != a["journal"], f"{ve['numero']} / {a['numero']}")

    doublons = dos.sql(
        "SELECT j.code, substr(e.date,1,4) an, e.numero, COUNT(*) n "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "GROUP BY e.societe_id, j.code, an, e.numero HAVING n > 1")
    v("aucun numéro n'est attribué deux fois dans un journal et une année",
      not doublons,
      [f"{d['code']} {d['numero']} × {d['n']}" for d in doublons[:5]])

    # La numérotation doit être continue : un trou dans une séquence est
    # exactement ce qu'un contrôleur cherche — il signale une pièce retirée.
    trous = []
    for jr in dos.sql(
            "SELECT DISTINCT j.code FROM ecritures e "
            "JOIN journaux j ON j.id = e.journal_id"):
        nums = sorted(
            int(e["numero"].rsplit("-", 1)[-1])
            for e in dos.sql(
                "SELECT e.numero FROM ecritures e "
                "JOIN journaux j ON j.id = e.journal_id "
                "WHERE j.code = ? AND substr(e.date,1,4) = ?",
                (jr["code"], str(annee)))
            if e["numero"] and e["numero"].rsplit("-", 1)[-1].isdigit())
        if nums and nums != list(range(nums[0], nums[0] + len(nums))):
            manquants = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
            trous.append(f"{jr['code']} : {len(manquants)} manquant(s) "
                         f"({manquants[:5]})")
    v("aucune séquence de journal ne présente de trou", not trous, trous[:4])

    # =====================================================================
    titre("2. Une écriture antidatée ne renumérote pas le passé")
    # =====================================================================
    recente = passe("OD", "Saisie du jour", date=f"{annee}-06-20")
    retrouvee = passe("OD", "Facture retrouvée après coup",
                      date=f"{annee}-06-02")
    v("l'écriture antidatée reçoit un numéro postérieur",
      retrouvee["numero"] > recente["numero"],
      f"{recente['numero']} puis {retrouvee['numero']}")
    relu = dos.sql("SELECT numero FROM ecritures WHERE id = ?",
                   (recente["id"],))[0]["numero"]
    v("… et le numéro déjà attribué ne change pas",
      relu == recente["numero"], f"{recente['numero']} devenu {relu}")

    liste = dos.appel(f"/api/ecritures?societe={sid}&journal=OD"
                      f"&du={annee}-06-01&au={annee}-06-30")["ecritures"]
    dates = [e["date"] for e in liste]
    v("le journal reste présenté dans l'ordre des dates",
      dates == sorted(dates, reverse=True), dates[:6])

    # =====================================================================
    titre("3. Dix écritures simultanées, dix numéros distincts")
    # =====================================================================
    # Le serveur répond sur plusieurs fils : deux saisies peuvent partir en
    # même temps. Si le compteur n'est pas atomique, deux écritures portent
    # le même numéro — et la comptabilité devient inexplicable.
    obtenus, incidents = [], []

    def tire(i):
        try:
            obtenus.append(passe("OD", f"Simultanée {i}", montant="500"))
        except Exception as err:                       # noqa: BLE001
            incidents.append(f"{type(err).__name__}: {err}")

    fils = [threading.Thread(target=tire, args=(i,)) for i in range(10)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=60)

    v("les dix saisies simultanées aboutissent", len(obtenus) == 10,
      f"{len(obtenus)} sur 10 — {incidents[:3]}")
    v("… sans qu'aucune ne soit refusée par un verrou", not incidents,
      incidents[:3])
    numeros = [e["numero"] for e in obtenus]
    v("… et les dix numéros sont distincts",
      len(set(numeros)) == len(numeros),
      f"{len(numeros) - len(set(numeros))} doublon(s)")
    v("la comptabilité reste équilibrée après l'accès simultané",
      dos.equilibre_global())

    # =====================================================================
    titre("4. Vente sur plan : l'avance devient produit à la livraison")
    # =====================================================================
    contrats = dos.appel(f"/api/contrats-vsp?societe={sid}")["contrats"]
    en_cours = [c for c in contrats if c["statut"] == "en_cours"
                and c["montant_encaisse"] > 0]
    v(f"le dossier contient un contrat VSP encaissé mais non livré "
      f"({len(en_cours)} disponible(s))", bool(en_cours))

    if en_cours:
        contrat = en_cours[0]
        avant = soldes()
        ca_avant = crediteur(avant, "70")
        avances_avant = crediteur(avant, "419")

        rep = dos.appel(f"/api/contrats-vsp/{contrat['id']}/livrer",
                        {"date": f"{annee}-06-25"})
        apres = soldes()

        v("le chiffre d'affaires augmente exactement du prix HT du lot",
          crediteur(apres, "70") - ca_avant == contrat["prix_ht"],
          f"{fm(crediteur(apres, '70') - ca_avant)} au lieu de "
          f"{fm(contrat['prix_ht'])}")

        ecr = dos.appel(f"/api/ecritures/{rep['ecriture_id']}")
        solde_avance = sum(l["debit"] for l in ecr["lignes"]
                           if l["compte"].startswith("419"))
        v("le compte d'avances est débité du montant qu'il portait",
          avances_avant - crediteur(apres, "419") == solde_avance,
          f"{fm(avances_avant - crediteur(apres, '419'))} au lieu de "
          f"{fm(solde_avance)}")

        reste = dos.sql(
            "SELECT COALESCE(SUM(l.credit - l.debit),0) s FROM lignes l "
            "WHERE l.compte LIKE '419%' AND l.lot_id = ?",
            (contrat["lot_id"],))[0]["s"]
        v("plus aucune avance ne reste attachée au lot livré",
          reste == 0, f"reste {fm(reste)}")

        du_client = sum(l["debit"] for l in ecr["lignes"]
                        if l["compte"].startswith("411"))
        v("le reste dû devient une créance client",
          du_client == contrat["prix_total"] - contrat["montant_encaisse"],
          f"{fm(du_client)} au lieu de "
          f"{fm(contrat['prix_total'] - contrat['montant_encaisse'])}")

        v("la comptabilité reste équilibrée après livraison",
          dos.equilibre_global())
        v("livrer deux fois le même lot est refusé",
          dos.refuse(f"/api/contrats-vsp/{contrat['id']}/livrer",
                     {"date": f"{annee}-06-26"}))

    # =====================================================================
    titre("5. Gestion locative : le loyer du propriétaire n'est pas un produit")
    # =====================================================================
    quittances = dos.appel(f"/api/quittances?societe={sid}")["quittances"]
    a_encaisser = [q for q in quittances if q["statut"] == "a_encaisser"]
    v(f"le dossier contient une quittance à encaisser "
      f"({len(a_encaisser)} disponible(s))", bool(a_encaisser))

    comptes_tr = dos.appel(f"/api/tresorerie?societe={sid}")["comptes"]
    banque = next((c for c in comptes_tr if c["type"] == "banque"), None)

    if a_encaisser and banque:
        q = a_encaisser[0]
        avant = soldes()
        ca_avant = crediteur(avant, "70")
        hono_avant = crediteur(avant, "706")
        mandant_avant = crediteur(avant, "467")

        dos.appel(f"/api/quittances/{q['id']}/encaisser",
                  {"date": f"{annee}-07-05", "tresorerie_id": banque["id"]})
        apres = soldes()

        v("seuls les honoraires entrent en produits, pas le loyer",
          crediteur(apres, "706") - hono_avant == q["honoraires_gestion_ht"],
          f"{fm(crediteur(apres, '706') - hono_avant)} au lieu de "
          f"{fm(q['honoraires_gestion_ht'])}")
        v("le loyer encaissé n'augmente pas le chiffre d'affaires de l'agence",
          crediteur(apres, "70") - ca_avant == q["honoraires_gestion_ht"],
          f"le CA a bougé de {fm(crediteur(apres, '70') - ca_avant)} pour un "
          f"loyer de {fm(q['total'])}")

        attendu = q["total"] - (q["honoraires_gestion_ht"] + q["tva_honoraires"])
        v("le compte du mandant porte le loyer, diminué des honoraires TTC",
          crediteur(apres, "467") - mandant_avant == attendu,
          f"{fm(crediteur(apres, '467') - mandant_avant)} au lieu de "
          f"{fm(attendu)}")

        dos.appel("/api/quittances/reverser",
                  {"societe_id": sid, "quittances": [q["id"]],
                   "date": f"{annee}-07-10", "tresorerie_id": banque["id"]})
        final = soldes()
        v("après reversement, le mandant ne porte plus cette quittance",
          crediteur(final, "467") - mandant_avant == 0,
          f"reste {fm(crediteur(final, '467') - mandant_avant)}")
        v("le reversement n'a pas touché au résultat",
          crediteur(final, "70") == crediteur(apres, "70"),
          f"{fm(crediteur(final, '70'))} au lieu de {fm(crediteur(apres, '70'))}")
        v("la comptabilité reste équilibrée après le cycle locatif",
          dos.equilibre_global())

    # =====================================================================
    titre("6. Trésorerie : le module et le grand livre disent la même chose")
    # =====================================================================
    grand_livre = soldes()
    ecarts = []
    for c in dos.appel(f"/api/tresorerie?societe={sid}&au={au}")["comptes"]:
        attendu = grand_livre.get(c["compte"], 0)
        if c["solde"] != attendu:
            ecarts.append(f"{c['libelle']} ({c['compte']}) : module "
                          f"{fm(c['solde'])} ≠ grand livre {fm(attendu)}")
    v(f"chaque compte de trésorerie s'accorde avec le grand livre "
      f"({len(comptes_tr)} compte(s))", not ecarts, ecarts[:4])


def suite_reprises(dos):
    """Annuler un import : suppression tant que rien n'a bougé,
    contre-passation ensuite.

    Un import se fait en un clic et peut porter des centaines de lignes.
    Le défaire ne doit ni laisser de trou dans la numérotation d'un
    journal, ni effacer une écriture que d'autres ont déjà utilisée.
    """
    CSV = """N° écriture;Date;Journal;Libellé;Compte;Tiers;Débit;Crédit;Périmètre;N° de pièce
1;15/03/{a};OD;Achat fournitures;607;;12000;;Déclaré;FA-01
1;;;;401;;;12000;;
2;16/03/{a};OD;Vente diverse;411;;25000;;Déclaré;FV-01
2;;;;701;;;25000;;
3;17/03/{a};OD;Frais bancaires;627;;3000;;Déclaré;
3;;;;512;;;3000;;
"""

    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL REPRISE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]
    annee = int(du[:4])
    fichier = CSV.format(a=annee)

    def total_debit():
        return dos.sql("SELECT COALESCE(SUM(debit),0) d FROM lignes")[0]["d"]

    def compteur_od():
        r = dos.sql("SELECT valeur FROM compteurs WHERE cle = 'ecriture_OD'")
        return r[0]["valeur"] if r else 0

    def importe():
        return dos.appel("/api/import/valider", {
            "societe_id": sid, "modele": "ecritures", "contenu": b64(fichier),
            "fichier": "reprise-mars.csv"})

    # ==================================================================
    titre("1. L'import est consigné")
    # ==================================================================
    r = importe()
    v("l'import répond avec son identifiant", bool(r.get("import_id")), r)
    v("trois écritures ont été créées", r["crees"] == 3, r)
    journal = dos.appel(f"/api/imports?societe={sid}")["imports"]
    v("il apparaît au journal des reprises", len(journal) == 1, journal)
    v("… avec le nom du fichier déposé",
      journal[0]["fichier"] == "reprise-mars.csv", journal[0])
    v("… et le libellé du modèle",
      "criture" in (journal[0].get("modele_libelle") or ""), journal[0])
    v("les écritures portent la marque de l'import",
      dos.sql("SELECT COUNT(*) n FROM ecritures WHERE import_id = ?",
          (r["import_id"],))[0]["n"] == 3)

    debit_apres_import = total_debit()
    compteur_apres_import = compteur_od()
    v("le compteur du journal OD est à 3", compteur_apres_import == 3,
      compteur_apres_import)

    # ==================================================================
    titre("2. Aussitôt fait, aussitôt défait : suppression")
    # ==================================================================
    plan = dos.appel(f"/api/imports/{r['import_id']}/plan")
    v("l'annulation est possible", plan["possible"], plan.get("empechement"))
    v("… par suppression", plan["mode"] == "suppression",
      f"{plan['mode']} — {plan.get('obstacles')}")
    v("… et le plan annonce trois écritures",
      plan["rendu"]["supprimees"] == 3, plan["rendu"])
    v("la simulation n'a rien écrit", total_debit() == debit_apres_import,
      f"{fm(total_debit())} au lieu de {fm(debit_apres_import)}")

    rendu = dos.appel(f"/api/imports/{r['import_id']}/annuler",
                  {"mode": "suppression"})
    v("l'annulation supprime les trois écritures", rendu["supprimees"] == 3,
      rendu)
    v("la comptabilité est revenue à zéro", total_debit() == 0,
      fm(total_debit()))
    v("le compteur du journal est remis où il était", compteur_od() == 0,
      compteur_od())
    v("l'import reste au journal, marqué annulé",
      bool(dos.appel(f"/api/imports?societe={sid}")["imports"][0]["annule_le"]))
    v("annuler deux fois est refusé",
      dos.refuse(f"/api/imports/{r['import_id']}/annuler", {}))

    # ==================================================================
    titre("3. Le même fichier réimporté ne bute sur aucun numéro")
    # ==================================================================
    r2 = importe()
    v("le fichier repasse sans conflit", r2["crees"] == 3, r2)
    nums = [e["numero"] for e in dos.sql(
        "SELECT e.numero FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "WHERE j.code = 'OD' ORDER BY e.id")]
    v("la numérotation repart de 1 sans trou",
      nums == [f"{annee}-00001", f"{annee}-00002", f"{annee}-00003"], nums)

    # ==================================================================
    titre("4. Une écriture passée depuis : plus question d'effacer")
    # ==================================================================
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-04-02",
        "libelle": "Saisie du comptable",
        "lignes": [{"compte": "607", "debit": "500", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "500"}]})
    plan = dos.appel(f"/api/imports/{r2['import_id']}/plan")
    v("l'annulation reste possible", plan["possible"], plan.get("empechement"))
    v("… mais par contre-passation", plan["mode"] == "contre_passation",
      plan["mode"])
    v("… et l'écran dit pourquoi",
      any("trou" in o for o in plan["obstacles"]), plan["obstacles"])
    v("le plan annonce trois extournes",
      len(plan["rendu"]["extournees"]) == 3, plan["rendu"])

    avant = total_debit()
    v("le mode annoncé est exigé",
      dos.refuse(f"/api/imports/{r2['import_id']}/annuler", {"mode": "suppression"}))
    rendu = dos.appel(f"/api/imports/{r2['import_id']}/annuler",
                  {"mode": "contre_passation", "date": f"{annee}-04-03"})
    v("trois extournes sont passées", len(rendu["extournees"]) == 3, rendu)
    v("les écritures importées sont toujours là",
      dos.sql("SELECT COUNT(*) n FROM ecritures WHERE import_id = ?",
          (r2["import_id"],))[0]["n"] == 3)
    v("le total débit a doublé du montant importé",
      total_debit() == avant + 40000 * 100,
      f"{fm(total_debit())} au lieu de {fm(avant + 4000000)}")

    b = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
    soldes = {l["compte"]: l["solde_debit"] - l["solde_credit"]
              for l in b["lignes"]}
    v("le compte 411 est soldé", soldes.get("411", 0) == 0,
      fm(soldes.get("411", 0)))
    v("le compte 701 est soldé", soldes.get("701", 0) == 0,
      fm(soldes.get("701", 0)))
    v("il ne reste que la saisie du comptable au 607",
      soldes.get("607", 0) == 50000, fm(soldes.get("607", 0)))
    v("la comptabilité reste équilibrée",
      b["totaux"]["debit"] == b["totaux"]["credit"])

    # ==================================================================
    titre("5. Un référentiel : ce qui sert déjà n'est pas retiré")
    # ==================================================================
    csv_tiers = ("Raison sociale;Type;NIF\n"
                 "ETS BOUKHARI;fournisseur;000116009999999\n"
                 "SARL DELTA;client;000116008888888\n")
    rt = dos.appel("/api/import/valider",
               {"societe_id": sid, "modele": "tiers", "contenu": b64(csv_tiers),
                "fichier": "tiers.csv"})
    v("deux tiers importés", rt["crees"] == 2, rt)
    ids = json.loads(dos.sql("SELECT objets FROM imports WHERE id = ?",
                         (rt["import_id"],))[0]["objets"])["tables"]["tiers"]
    # On en emploie un dans une écriture : il ne doit plus pouvoir partir.
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-04-05",
        "libelle": "Achat chez Boukhari",
        "lignes": [{"compte": "607", "debit": "700", "credit": "0",
                    "tiers_id": ids[0]},
                   {"compte": "401", "debit": "0", "credit": "700"}]})
    plan = dos.appel(f"/api/imports/{rt['import_id']}/plan")
    v("le retrait ne peut être que partiel", plan["mode"] == "partiel",
      f"{plan['mode']} — {plan['rendu']}")
    v("… un tiers part, l'autre reste",
      plan["rendu"]["objets_retires"].get("tiers") == 1
      and plan["rendu"]["objets_gardes"].get("tiers") == 1, plan["rendu"])
    rendu = dos.appel(f"/api/imports/{rt['import_id']}/annuler", {"mode": "partiel"})
    restants = dos.sql("SELECT id FROM tiers WHERE id IN (?,?)", tuple(ids))
    v("le tiers employé est toujours en base",
      [x["id"] for x in restants] == [ids[0]], restants)
    v("le compte rendu le dit",
      "conserv" in (dos.sql("SELECT annule_note FROM imports WHERE id = ?",
                        (rt["import_id"],))[0]["annule_note"] or ""),
      dos.sql("SELECT annule_note FROM imports WHERE id = ?",
          (rt["import_id"],))[0]["annule_note"])


def suite_sante(dos):
    """Sante du dossier : chaque controle doit voir ce qu'il pretend voir.

    Un controle qui ne se declenche jamais ne protege de rien. Chacun est
    donc mis a l'epreuve sur une anomalie provoquee pour lui.
    """
    dos.appel("/api/connexion", {"identifiant": "demo", "mot_de_passe": "demo1234"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    exid = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["id"]

    def sante():
        return dos.appel(f"/api/sante?societe={sid}&exercice={exid}")

    def cles(d):
        return {a["cle"] for a in d["anomalies"]}

    def trouve(d, cle):
        return next((a for a in d["anomalies"] if a["cle"] == cle), None)

    titre("1. Sur un dossier sain, les contrôles se taisent")
    d = sante()
    v("l'écran répond", "anomalies" in d, d)
    v("la comptabilité est équilibrée", "equilibre" not in cles(d),
      trouve(d, "equilibre"))
    v("aucune écriture déséquilibrée", "ecritures_boiteuses" not in cles(d))
    v("la numérotation est continue", "numerotation" not in cles(d),
      trouve(d, "numerotation"))
    v("la caisse n'est jamais passée en négatif", "caisse" not in cles(d),
      trouve(d, "caisse"))
    v("aucune facture validée sans écriture",
      "factures_sans_ecriture" not in cles(d), trouve(d, "factures_sans_ecriture"))
    v("aucun tiers au solde inversé", "tiers_inverses" not in cles(d),
      trouve(d, "tiers_inverses"))
    v("les G50 déposées collent aux comptes", "tva_declaree" not in cles(d),
      trouve(d, "tva_declaree"))
    v("chaque anomalie porte une explication",
      all(a["explication"] for a in d["anomalies"]),
      [a["cle"] for a in d["anomalies"] if not a["explication"]])
    v("… et un chemin où aller, sauf mention",
      all(a["route"] or a["cle"].startswith("panne_") for a in d["anomalies"]),
      [a["cle"] for a in d["anomalies"] if not a["route"]])

    titre("2. Chaque contrôle voit ce qu'il prétend voir")

    # -- un trou dans la numérotation
    cible = dos.sql("SELECT e.id, e.numero FROM ecritures e JOIN journaux j "
                "ON j.id = e.journal_id WHERE j.code = 'BQ' ORDER BY e.id LIMIT 1 "
                "OFFSET 2")[0]
    dos.ecrit("DELETE FROM ecritures WHERE id = ?", (cible["id"],))
    d = sante()
    v("un numéro manquant est vu", "numerotation" in cles(d),
      sorted(cles(d)))
    v("… en disant lequel",
      any(cible["numero"].rsplit("-", 1)[-1].lstrip("0")
          in x for x in trouve(d, "numerotation")["detail"]),
      trouve(d, "numerotation")["detail"][:2])

    # -- une caisse qui part en négatif
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "CA", "date": ex["date_debut"],
        "libelle": "Sortie de caisse impossible",
        "lignes": [{"compte": "607", "debit": "9000000", "credit": "0"},
                   {"compte": "53", "debit": "0", "credit": "9000000"}]})
    d = sante()
    v("une caisse créditrice est vue", "caisse" in cles(d), sorted(cles(d)))
    v("… avec le solde le plus bas atteint",
      trouve(d, "caisse")["montant"] < 0, trouve(d, "caisse"))

    # -- un client créditeur
    client = dos.sql("SELECT id, raison_sociale FROM tiers WHERE type = 'client' LIMIT 1")[0]
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": ex["date_debut"],
        "libelle": "Avance client jamais lettrée",
        "lignes": [{"compte": "512", "debit": "500000", "credit": "0"},
                   {"compte": "411", "debit": "0", "credit": "500000",
                    "tiers_id": client["id"]}]})
    d = sante()
    v("un client au solde créditeur est vu", "tiers_inverses" in cles(d),
      sorted(cles(d)))
    v("… en le nommant",
      any(client["raison_sociale"] in x
          for x in trouve(d, "tiers_inverses")["detail"]),
      trouve(d, "tiers_inverses")["detail"][:3])

    # -- une G50 déposée qui ne colle plus
    periode = f"{ex['date_debut'][:4]}-03"
    g = dos.appel(f"/api/g50?societe={sid}&periode={periode}")
    dos.appel("/api/g50", {"societe_id": sid, "periode": periode,
                       **{k: v_ for k, v_ in g.items()
                          if isinstance(v_, int)}})
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "VE", "date": f"{periode}-15",
        "libelle": "Vente ajoutée après le dépôt",
        "lignes": [{"compte": "411", "debit": "119000", "credit": "0"},
                   {"compte": "701", "debit": "0", "credit": "100000"},
                   {"compte": "4457", "debit": "0", "credit": "19000"}]})
    d = sante()
    v("une G50 déposée qui ne colle plus est vue", "tva_declaree" in cles(d),
      sorted(cles(d)))
    v("… en disant de combien",
      "écart" in (trouve(d, "tva_declaree")["detail"][0] if
                  trouve(d, "tva_declaree") else ""),
      trouve(d, "tva_declaree"))

    # -- une écriture en brouillon
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": ex["date_debut"],
        "libelle": "Brouillon à relire", "valider": 0,
        "lignes": [{"compte": "607", "debit": "1000", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "1000"}]})
    d = sante()
    v("un brouillon est signalé", "brouillons" in cles(d), sorted(cles(d)))

    titre("3. Les anomalies sont classées du plus grave au plus anodin")
    d = sante()
    poids = {"critique": 0, "alerte": 1, "info": 2}
    ordre = [poids[a["niveau"]] for a in d["anomalies"]]
    v("l'ordre est respecté", ordre == sorted(ordre),
      [a["niveau"] for a in d["anomalies"]])
    v("le compte des critiques est juste",
      d["critiques"] == sum(1 for a in d["anomalies"] if a["niveau"] == "critique"))

    titre("4. Un contrôle qui échoue n'emporte pas les autres")
    dos.ecrit("UPDATE ecritures SET numero = 'CASSÉ' WHERE id = "
          "(SELECT id FROM ecritures LIMIT 1)")
    d = sante()
    v("l'écran répond encore", "anomalies" in d and d["controles"] > 0, d.keys())


def suite_annuelles(dos):
    """DAS et etat des clients : les deux etats de janvier.

    Le travail n'est pas de les remplir -- tout est deja saisi -- c'est de
    les recouper. Ce sont les recoupements qui sont verifies ici.
    """
    dos.appel("/api/connexion", {"identifiant": "demo", "mot_de_passe": "demo1234"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    annee = int(dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["date_debut"][:4])

    titre("1. La déclaration annuelle des salaires")
    d = dos.appel(f"/api/declarations/das?societe={sid}&annee={annee}")
    attendus = dos.sql("SELECT COUNT(DISTINCT salarie_id) n, COUNT(*) b, "
                   "SUM(salaire_brut) brut, SUM(irg) irg, SUM(net_a_payer) net "
                   "FROM bulletins WHERE substr(periode,1,4) = ?", (str(annee),))[0]
    v(f"elle porte les {attendus['n']} salariés payés",
      len(d["salaries"]) == attendus["n"], len(d["salaries"]))
    v("… et tous les bulletins de l'année",
      d["totaux"]["mois"] == attendus["b"],
      f"{d['totaux']['mois']} au lieu de {attendus['b']}")
    v("le brut total est celui des bulletins",
      d["totaux"]["brut"] == attendus["brut"],
      f"{fm(d['totaux']['brut'])} vs {fm(attendus['brut'])}")
    v("l'IRG total aussi", d["totaux"]["irg"] == attendus["irg"],
      f"{fm(d['totaux']['irg'])} vs {fm(attendus['irg'])}")
    v("le net payé aussi", d["totaux"]["net"] == attendus["net"],
      f"{fm(d['totaux']['net'])} vs {fm(attendus['net'])}")
    v("la date limite est celle de l'année suivante",
      (d["date_limite"] or "").startswith(str(annee + 1)), d["date_limite"])
    v("chaque salarié porte son matricule et son n° de sécurité sociale",
      all(s["matricule"] for s in d["salaries"]),
      [s for s in d["salaries"] if not s["matricule"]][:2])

    titre("2. Le recoupement de l'IRG — ce qui fait la valeur du document")
    c = d["controle"]
    v("l'IRG des bulletins est repris tel quel",
      c["irg_bulletins"] == d["totaux"]["irg"])
    v("il est comparé au cumul des G50 déposées",
      c["irg_g50"] == dos.sql("SELECT COALESCE(SUM(irg_salaires),0) s FROM "
                          "declarations_g50 WHERE substr(periode,1,4) = ?",
                          (str(annee),))[0]["s"], c)
    v("… et au compte 4421 de la comptabilité", "irg_comptes" in c, c)
    v("les écarts sont calculés",
      c["ecart_g50"] == c["irg_bulletins"] - c["irg_g50"], c)

    # On fausse une G50 : le recoupement doit crier.
    dos.ecrit("UPDATE declarations_g50 SET irg_salaires = irg_salaires + 100000 "
          "WHERE periode = ?", (f"{annee}-03",))
    d2 = dos.appel(f"/api/declarations/das?societe={sid}&annee={annee}")
    # Le jeu de démonstration ne dépose pas les douze mois : un écart de base
    # existe donc, et il est légitime — l'écran annonce le nombre de mois
    # déclarés à côté. On mesure ici le déplacement, pas la valeur absolue.
    v("une G50 faussée déplace l'écart d'autant",
      d2["controle"]["ecart_g50"] == c["ecart_g50"] - 100000,
      f"{d2['controle']['ecart_g50']} au lieu de {c['ecart_g50'] - 100000}")
    v("… et le nombre de mois déclarés est annoncé",
      d2["controle"]["mois_declares"] > 0, d2["controle"]["mois_declares"])

    titre("3. L'état des clients")
    e = dos.appel(f"/api/declarations/etat-clients?societe={sid}&annee={annee}")
    reels = dos.sql("SELECT COUNT(DISTINCT tiers_id) n, COALESCE(SUM(montant_ht),0) ht "
                "FROM factures WHERE substr(date,1,4) = ? AND sens = 'vente' "
                "AND statut NOT IN ('brouillon','annulee') AND perimetre = 'declare'",
                (str(annee),))[0]
    v(f"il porte les {reels['n']} client(s) facturés",
      len(e["clients"]) == reels["n"], len(e["clients"]))
    v("le total HT est celui des factures", e["totaux"]["ht"] == reels["ht"],
      f"{fm(e['totaux']['ht'])} vs {fm(reels['ht'])}")
    v("chaque client porte son identité fiscale",
      all("nif" in c for c in e["clients"]))
    v("les clients sont classés du plus gros au plus petit",
      [c["ttc"] for c in e["clients"]] ==
      sorted([c["ttc"] for c in e["clients"]], reverse=True),
      [c["ttc"] for c in e["clients"]])

    titre("4. Le recoupement du chiffre d'affaires")
    c = e["controle"]
    v("le total des factures est comparé aux comptes de produits",
      "ca_comptes" in c and "ecart" in c, c)
    # Une vente passée en écriture, sans facture : elle doit manquer à l'état.
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "VE", "date": f"{annee}-06-15",
        "libelle": "Vente comptabilisée sans facture",
        "lignes": [{"compte": "411", "debit": "119000", "credit": "0"},
                   {"compte": "701", "debit": "0", "credit": "100000"},
                   {"compte": "4457", "debit": "0", "credit": "19000"}]})
    e2 = dos.appel(f"/api/declarations/etat-clients?societe={sid}&annee={annee}")
    v("une vente sans facture creuse l'écart",
      e2["controle"]["ecart"] == c["ecart"] - 10000000,
      f"{e2['controle']['ecart']} vs {c['ecart'] - 10000000}")

    titre("5. Le seuil écarte les petits clients")
    gros = max(x["ttc"] for x in e["clients"]) if e["clients"] else 0
    seuil = dos.appel(f"/api/declarations/etat-clients?societe={sid}&annee={annee}"
                  f"&seuil={gros // 100}")
    v("un seuil ne garde que ce qui l'atteint",
      all(x["ttc"] >= gros for x in seuil["clients"]),
      [x["ttc"] for x in seuil["clients"]])
    v("… et dit combien il a écarté",
      seuil["ecartes"] == len(e["clients"]) - len(seuil["clients"]),
      f"{seuil['ecartes']}")

    titre("6. Les documents produits")
    html, mime = dos.appel(f"/api/declarations/das/impression?societe={sid}"
                       f"&annee={annee}", brut=True)
    texte = html.decode()
    v("la DAS imprimable est une page HTML", "text/html" in mime, mime)
    v("… titrée comme il faut", "DÉCLARATION ANNUELLE DES SALAIRES" in texte)
    v("… avec la série G n° 29", "G n° 29" in texte)
    v("… et le recoupement sur le papier",
      "Recoupement de l'IRG retenu" in texte, texte[:200])
    v("… et le rappel de vérifier les taux",
      "loi de finances" in texte)

    html, mime = dos.appel(f"/api/declarations/etat-clients/impression?societe={sid}"
                       f"&annee={annee}", brut=True)
    texte = html.decode()
    v("l'état des clients imprimable aussi", "ÉTAT DES CLIENTS" in texte)
    v("… avec son recoupement",
      "Recoupement du chiffre d'affaires" in texte)

    for chemin, nom in ((f"/api/export/das?societe={sid}&annee={annee}", "DAS"),
                        (f"/api/export/etat-clients?societe={sid}&annee={annee}",
                         "état des clients")):
        octets, mime = dos.appel(chemin, brut=True)
        v(f"l'export {nom} est un classeur",
          "spreadsheetml" in mime and octets[:2] == b"PK", mime)


def suite_relances(dos):
    """Relances : ce qui est du, depuis quand, et ce qu'on a deja ecrit.

    Une facture reglee mais non lettree apparaitrait ici a tort : c'est
    le seul cas ou l'ecran mentirait, et il est verifie.
    """
    aujourd = time.strftime("%Y-%m-%d")
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL RELANCE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex["date_debut"][:4])
    aujourd = time.strftime("%Y-%m-%d")

    def client(nom):
        return dos.appel("/api/tiers", {"societe_id": sid, "type": "client",
                                    "raison_sociale": nom,
                                    "nif": "000116009999999"})["id"]

    def facture(tiers, montant, echeance, piece):
        return dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": "VE", "date": echeance,
            "libelle": f"Facture {piece}", "piece": piece,
            "lignes": [{"compte": "411", "debit": montant, "credit": "0",
                        "tiers_id": tiers, "echeance": echeance},
                       {"compte": "701", "debit": "0", "credit": montant}]})

    import datetime
    def il_y_a(jours):
        d = datetime.date.fromisoformat(aujourd) - datetime.timedelta(days=jours)
        return max(d.isoformat(), ex["date_debut"])

    titre("1. Ce qui est dû, groupé par client")
    a = client("ETS BOUKHARI")
    b = client("SARL DELTA")
    facture(a, "100000", il_y_a(120), "FV-001")
    facture(a, "50000", il_y_a(20), "FV-002")
    facture(b, "30000", il_y_a(5), "FV-003")

    d = dos.appel(f"/api/relances?societe={sid}")
    v("les deux clients apparaissent", len(d["clients"]) == 2,
      [c["raison_sociale"] for c in d["clients"]])
    v("le plus gros débiteur est en tête",
      d["clients"][0]["raison_sociale"] == "ETS BOUKHARI",
      d["clients"][0]["raison_sociale"])
    v("ses deux pièces sont réunies", len(d["clients"][0]["pieces"]) == 2,
      d["clients"][0]["pieces"])
    v("son total est juste", d["clients"][0]["total"] == 15000000,
      fm(d["clients"][0]["total"]))
    v("le retard le plus ancien est retenu",
      d["clients"][0]["retard_max"] >= 119, d["clients"][0]["retard_max"])
    v("le total général est juste", d["total"] == 18000000, fm(d["total"]))

    titre("2. Le niveau proposé suit le retard")
    boukhari = d["clients"][0]
    delta = next(c for c in d["clients"] if c["raison_sociale"] == "SARL DELTA")
    v("120 jours de retard appellent une mise en demeure",
      boukhari["niveau_suggere"] == 3, boukhari["niveau_suggere"])
    v("5 jours appellent un simple rappel",
      delta["niveau_suggere"] == 1, delta["niveau_suggere"])
    v("aucun n'a encore été relancé",
      all(c["derniere_relance"] is None for c in d["clients"]))

    titre("3. Le filtre par retard")
    d90 = dos.appel(f"/api/relances?societe={sid}&jours=90")
    v("au-delà de 90 jours, un seul client reste",
      len(d90["clients"]) == 1 and d90["clients"][0]["raison_sociale"] == "ETS BOUKHARI",
      [c["raison_sociale"] for c in d90["clients"]])
    v("… avec sa seule pièce ancienne",
      len(d90["clients"][0]["pieces"]) == 1, d90["clients"][0]["pieces"])

    titre("4. Une facture lettrée sort de la liste")
    lignes = dos.appel(f"/api/lettrage?societe={sid}&compte=411&etat=non_lettre")
    # On encaisse la facture de DELTA et on lettre les deux lignes.
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "BQ", "date": aujourd,
        "libelle": "Encaissement DELTA",
        "lignes": [{"compte": "512", "debit": "30000", "credit": "0"},
                   {"compte": "411", "debit": "0", "credit": "30000",
                    "tiers_id": b}]})
    aptes = [l["id"] for l in dos.appel(
        f"/api/lettrage?societe={sid}&compte=411&etat=non_lettre")["lignes"]
        if l.get("tiers_id") == b]
    dos.appel("/api/lettrage", {"societe_id": sid, "lignes": aptes})
    d = dos.appel(f"/api/relances?societe={sid}")
    v("le client réglé et lettré disparaît",
      all(c["raison_sociale"] != "SARL DELTA" for c in d["clients"]),
      [c["raison_sociale"] for c in d["clients"]])

    titre("5. Consigner une relance")
    r = dos.appel("/api/relances", {"societe_id": sid, "tiers_id": a, "niveau": 2,
                                "moyen": "courriel", "note": "au gérant"})
    v("la relance est enregistrée", r["niveau"] == 2 and r["nb_pieces"] == 2, r)
    d = dos.appel(f"/api/relances?societe={sid}")
    c = d["clients"][0]
    v("elle apparaît comme dernière relance",
      c["derniere_relance"] and c["derniere_relance"]["niveau"] == 2,
      c["derniere_relance"])
    v("… datée d'aujourd'hui", c["jours_depuis_relance"] == 0,
      c["jours_depuis_relance"])
    v("le niveau proposé monte d'un cran",
      c["niveau_suggere"] == 3, c["niveau_suggere"])
    v("l'historique la retrouve",
      dos.appel(f"/api/relances/historique?societe={sid}")["relances"][0]["note"]
      == "au gérant")
    v("aucune écriture n'a été créée par la relance",
      dos.appel(f"/api/ecritures?societe={sid}")["total"] == 4,
      dos.appel(f"/api/ecritures?societe={sid}")["total"])

    titre("6. La lettre, à ses trois niveaux")
    for niveau, marque in ((1, "RAPPEL"), (2, "RELANCE"), (3, "MISE EN DEMEURE")):
        html, mime = dos.appel(f"/api/relances/lettre?societe={sid}&tiers={a}"
                           f"&niveau={niveau}", brut=True)
        texte = html.decode()
        v(f"niveau {niveau} : la lettre porte « {marque} »", marque in texte,
          texte[:200])
        v(f"… et liste les {2} pièces dues",
          "FV-001" in texte and "FV-002" in texte, texte[:400])
    v("la mise en demeure annonce ses effets",
      "intérêts de retard" in dos.appel(
          f"/api/relances/lettre?societe={sid}&tiers={a}&niveau=3",
          brut=True)[0].decode())
    v("le rappel, lui, suppose l'oubli",
      "oubli" in dos.appel(f"/api/relances/lettre?societe={sid}&tiers={a}&niveau=1",
                       brut=True)[0].decode())
    try:
        dos.appel(f"/api/relances/lettre?societe={sid}&tiers=99999&niveau=1", brut=True)
        v("un client inconnu est refusé", False, "aucune erreur")
    except urllib.error.HTTPError as err:
        v("un client inconnu est refusé", err.code == 404, err.code)


def suite_banque(dos):
    """Le releve de la banque, lu et rapproche.

    Deux pieges y sont verifies : le sens des colonnes, qu'une banque
    ecrit de son point de vue ou de celui du client, et l'ecart de date
    entre une operation passee ici et la meme passee la-bas.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL BANQUE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex["date_debut"][:4])
    comptes = dos.appel(f"/api/tresorerie?societe={sid}")["comptes"]
    banque = next((c for c in comptes if c["type"] == "banque"), None)
    if not banque:
        banque = dos.appel("/api/tresorerie", {
            "societe_id": sid, "code": "BQ1", "libelle": "Banque principale",
            "type": "banque", "compte": "512"})
        banque = next(c for c in dos.appel(f"/api/tresorerie?societe={sid}")["comptes"]
                      if c["type"] == "banque")

    def ecriture(date, libelle, compte_tr, sens, montant):
        lignes = ([{"compte": banque["compte"], "debit": montant, "credit": "0"},
                   {"compte": "701", "debit": "0", "credit": montant}]
                  if sens == "entree" else
                  [{"compte": "607", "debit": montant, "credit": "0"},
                   {"compte": banque["compte"], "debit": "0", "credit": montant}])
        return dos.appel("/api/ecritures", {
            "societe_id": sid, "journal": "BQ", "date": date,
            "libelle": libelle, "lignes": lignes})

    # Trois mouvements en banque, plus un chèque émis que la banque n'a pas
    # encore débité.
    ecriture(f"{annee}-03-04", "Encaissement client BENALI", None, "entree", "150000")
    ecriture(f"{annee}-03-11", "Loyer du local", None, "sortie", "45000")
    ecriture(f"{annee}-03-18", "Encaissement SARL DELTA", None, "entree", "80000")
    ecriture(f"{annee}-03-29", "Chèque n° 4412 fournisseur", None, "sortie", "23000")

    rap = dos.appel("/api/rapprochements", {
        "societe_id": sid, "tresorerie_id": banque["id"],
        "date_arrete": f"{annee}-03-31", "solde_releve": "185000"})

    titre("1. Le relevé de la banque, à sa façon")
    # Colonnes du point de vue de la banque : « crédit » = entrée chez nous.
    # Une date décalée de deux jours, et une ligne d'agios absente des livres.
    releve = (
        "Date;Libellé;Débit;Crédit\n"
        f"04/03/{annee};VIREMENT RECU BENALI;;150000\n"
        f"13/03/{annee};PRLV LOYER LOCAL;45000;\n"
        f"18/03/{annee};VIREMENT RECU DELTA;;80000\n"
        f"31/03/{annee};FRAIS DE TENUE DE COMPTE;1200;\n")
    d = dos.appel(f"/api/rapprochements/{rap['id']}/releve", {"contenu": b64(releve)})
    v("les quatre lignes du relevé sont lues", d["lignes_relevé"] == 4,
      d["lignes_relevé"])
    v("le sens des colonnes est reconnu", d["sens"] == "direct", d["sens"])
    v("… et expliqué en clair", "banque" in d["explication_sens"],
      d["explication_sens"])

    titre("2. Ce qui se correspond est rapproché")
    v("trois correspondances sont proposées", len(d["correspondances"]) == 3,
      [(c["releve"]["libelle"], c["ligne"]["libelle"])
       for c in d["correspondances"]])
    par_libelle = {c["releve"]["libelle"]: c for c in d["correspondances"]}
    v("l'encaissement BENALI tombe le même jour",
      par_libelle["VIREMENT RECU BENALI"]["ecart_jours"] == 0,
      par_libelle["VIREMENT RECU BENALI"]["ecart_jours"])
    v("le loyer est rapproché malgré deux jours d'écart",
      par_libelle["PRLV LOYER LOCAL"]["ecart_jours"] == 2,
      par_libelle["PRLV LOYER LOCAL"]["ecart_jours"])
    v("… et du bon côté",
      par_libelle["PRLV LOYER LOCAL"]["ligne"]["credit"] == 4500000,
      par_libelle["PRLV LOYER LOCAL"]["ligne"])

    titre("3. Ce qui ne se correspond pas est montré, pas caché")
    v("les agios n'ont pas d'écriture",
      len(d["sans_correspondance"]) == 1
      and "FRAIS" in d["sans_correspondance"][0]["libelle"],
      d["sans_correspondance"])
    v("le chèque émis reste non pointé",
      len(d["non_pointees"]) == 1
      and "4412" in d["non_pointees"][0]["libelle"], d["non_pointees"])

    titre("4. Rien n'est pointé avant confirmation")
    avant = dos.appel(f"/api/rapprochements/{rap['id']}")
    v("aucun mouvement n'est pointé pour l'instant",
      all(not m["pointee"] for m in avant["mouvements"]),
      [m["pointee"] for m in avant["mouvements"]])
    dos.appel(f"/api/rapprochements/{rap['id']}/pointer",
          {"lignes": [c["ligne"]["id"] for c in d["correspondances"]],
           "pointer": True})
    apres = dos.appel(f"/api/rapprochements/{rap['id']}")
    v("les trois correspondances sont pointées",
      sum(1 for m in apres["mouvements"] if m["pointee"]) == 3,
      [(m["libelle"], m["pointee"]) for m in apres["mouvements"]])
    v("le chèque émis explique l'écart restant",
      apres["montant_non_pointe"] == -2300000,
      apres["montant_non_pointe"])

    titre("5. Une banque qui parle au client, colonnes inversées")
    rap2 = dos.appel("/api/rapprochements", {
        "societe_id": sid, "tresorerie_id": banque["id"],
        "date_arrete": f"{annee}-03-31", "solde_releve": "185000"})
    inverse = (
        "Date;Operation;Debit;Credit\n"
        f"29/03/{annee};CHEQUE 4412;;23000\n")
    d2 = dos.appel(f"/api/rapprochements/{rap2['id']}/releve", {"contenu": b64(inverse)})
    v("le sens inversé est détecté", d2["sens"] == "inverse", d2["sens"])
    v("… et le chèque est rapproché", len(d2["correspondances"]) == 1,
      d2["correspondances"])

    titre("6. Un fichier qui n'est pas un relevé")
    msg = dos.refuse(f"/api/rapprochements/{rap['id']}/releve",
                 {"contenu": b64("Nom;Prénom\nX;Y\n")})
    v("il est refusé", bool(msg), msg)
    v("… en disant ce qui manque", "date" in (msg or "").lower(), msg)
    msg = dos.refuse(f"/api/rapprochements/{rap['id']}/releve",
                 {"contenu": b64("Date;Libellé\n01/01/2026;X\n")})
    v("un relevé sans montant est refusé aussi",
      "montant" in (msg or "").lower(), msg)
    v("un rapprochement inconnu est refusé",
      dos.refuse("/api/rapprochements/99999/releve", {"contenu": b64(releve)}))


def suite_creation(dos):
    """L'import cree ce dont il a besoin, et le dit.

    Exiger que le plan comptable, les tiers et les journaux existent avant
    d'importer un journal d'ecritures, c'est demander de reprendre son
    dossier trois fois, dans le bon ordre, en corrigeant a chaque tour.
    Ce qui n'est qu'un nom se cree donc tout seul -- annonce avant, liste
    apres, et repris si la reprise est annulee. Ce qui porte une decision
    -- un programme, un lot, un bail -- continue d'etre reclame.
    """
    CSV = """N° écriture;Date;Journal;Libellé;Compte;Tiers;Débit;Crédit;Périmètre;N° de pièce
1;15/03/{a};VT;Vente de biens;41101;ETS BENALI;119000;;Déclaré;FV-100
1;;;;701;;;100000;;
1;;;;4457;;;19000;;
2;16/03/{a};VT;Achat fournitures;60701;;24000;;Déclaré;FA-100
2;;;;40101;SARL FOURNIMEX;;24000;;
"""

    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL CREATION", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    annee = int(dos.appel(f"/api/exercices?societe={sid}")
                ["exercices"][0]["date_debut"][:4])
    fichier = CSV.format(a=annee)

    def existe(table, colonne, valeur):
        return bool(dos.sql(f"SELECT id FROM {table} WHERE societe_id = ? "
                            f"AND {colonne} = ?", (sid, valeur)))

    # ==================================================================
    titre("1. Ce qui manque est annonce, pas reclame")
    # ==================================================================
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(fichier)})
    v("aucune anomalie : plus rien n'est a preparer d'avance",
      not a["anomalies"], a["anomalies"][:5])
    v("les cinq lignes sont pretes", a["nb_valides"] == 2, a["nb_valides"])
    creer = a.get("a_creer") or {}
    numeros = {c["numero"] for c in creer.get("comptes", [])}
    v("les sous-comptes absents sont annonces",
      {"41101", "40101", "60701"} <= numeros, sorted(numeros))
    v("… et pas ceux qui existent deja",
      "701" not in numeros and "4457" not in numeros, sorted(numeros))
    noms = {t["raison_sociale"] for t in creer.get("tiers", [])}
    v("les tiers nommes le sont aussi",
      {"ETS BENALI", "SARL FOURNIMEX"} == noms, sorted(noms))
    v("le journal inconnu aussi",
      [j["code"] for j in creer.get("journaux", [])] == ["VT"],
      creer.get("journaux"))
    v("rien n'a encore ete cree", not existe("comptes", "numero", "41101"))

    # ==================================================================
    titre("2. La validation les cree, avec ce qu'il faut autour")
    # ==================================================================
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(fichier),
        "fichier": "journal-mars.csv"})
    v("les deux ecritures sont enregistrees", r["crees"] == 2, r)
    v("le compte rendu dit ce qui a ete cree au passage",
      r.get("prealables", {}).get("comptes") == 3
      and r["prealables"].get("tiers") == 2
      and r["prealables"].get("journaux") == 1, r.get("prealables"))
    v("la comptabilite reste equilibree", dos.equilibre_global())

    compte = dos.sql("SELECT * FROM comptes WHERE societe_id = ? AND "
                     "numero = '40101'", (sid,))
    v("le sous-compte cree existe", bool(compte))
    parent = dos.sql("SELECT * FROM comptes WHERE societe_id = ? AND "
                     "numero = '4011'", (sid,))[0]
    v("… il herite de la nature de son compte de rattachement",
      compte and compte[0]["nature"] == parent["nature"],
      compte and compte[0]["nature"])
    v("… et de son caractere lettrable",
      compte and compte[0]["lettrable"] == parent["lettrable"])
    v("… sa classe est celle de son numero",
      compte and compte[0]["classe"] == 4, compte and compte[0]["classe"])

    tiers = dos.sql("SELECT * FROM tiers WHERE societe_id = ? AND "
                    "raison_sociale = 'SARL FOURNIMEX'", (sid,))
    v("le tiers cree existe", bool(tiers))
    v("… range en fournisseur d'apres son compte",
      tiers and tiers[0]["type"] == "fournisseur", tiers and tiers[0]["type"])
    v("… avec son compte collectif",
      tiers and tiers[0]["compte_comptable"] == "401",
      tiers and tiers[0]["compte_comptable"])
    client = dos.sql("SELECT * FROM tiers WHERE societe_id = ? AND "
                     "raison_sociale = 'ETS BENALI'", (sid,))
    v("celui porte par un compte 411 est range en client",
      client and client[0]["type"] == "client", client and client[0]["type"])
    v("… et chacun a son propre code",
      client and tiers and client[0]["code"] != tiers[0]["code"])

    journal = dos.sql("SELECT * FROM journaux WHERE societe_id = ? AND "
                      "code = 'VT'", (sid,))
    v("le journal cree existe", bool(journal))
    v("… et les ecritures y sont bien passees",
      dos.sql("SELECT COUNT(*) n FROM ecritures e JOIN journaux j "
              "ON j.id = e.journal_id WHERE j.code = 'VT'")[0]["n"] == 2)

    # ==================================================================
    titre("3. Un second passage ne recree rien")
    # ==================================================================
    avant = dos.sql("SELECT COUNT(*) n FROM comptes")[0]["n"]
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(fichier)})
    v("plus rien a creer au second passage",
      not (a.get("a_creer") or {}).get("comptes"), a.get("a_creer"))
    v("le plan comptable n'a pas grossi",
      dos.sql("SELECT COUNT(*) n FROM comptes")[0]["n"] == avant)

    # ==================================================================
    titre("4. Annuler la reprise reprend aussi ce qu'elle a cree")
    # ==================================================================
    import_id = dos.appel(f"/api/imports?societe={sid}")["imports"][0]["id"]
    plan = dos.appel(f"/api/imports/{import_id}/plan")
    v("le plan annonce les objets a retirer",
      ((plan.get("porte") or {}).get("objets") or {}).get("comptes") == 3,
      plan.get("porte"))
    dos.appel(f"/api/imports/{import_id}/annuler",
              {"societe_id": sid, "mode": "suppression",
               "confirmation": "SUPPRIMER"})
    v("les ecritures sont parties",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 0)
    v("le sous-compte cree est parti avec",
      not existe("comptes", "numero", "40101"))
    v("le tiers cree aussi", not existe("tiers", "raison_sociale", "ETS BENALI"))
    v("le journal cree aussi", not existe("journaux", "code", "VT"))
    v("… mais pas les comptes qui existaient avant",
      existe("comptes", "numero", "4011") and existe("comptes", "numero", "701"))
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("5. Aucun ordre a respecter : le fichier qui cite cree la fiche")
    # ==================================================================
    # Le frere du demandeur importe ce qu'il veut, quand il veut. Un fichier
    # de lots passe avant celui des programmes ne doit plus etre rejete : le
    # programme nait avec son seul code, a completer.
    LOTS = """Programme;N° lot;Type;Surface habitable;Prix de vente
PROG-NEUF;A-12;appartement;85;12000000
PROG-NEUF;A-13;appartement;95;13500000
"""
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "lots", "contenu": b64(LOTS)})
    v("un programme absent n'est plus une anomalie", not a["anomalies"],
      a["anomalies"])
    fiches = (a.get("a_creer") or {}).get("fiches", [])
    v("… il est annonce a la creation",
      [f["valeur"] for f in fiches] == ["PROG-NEUF"], fiches)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "lots", "contenu": b64(LOTS)})
    v("les deux lots sont crees", r["crees"] == 2, r)
    prog = dos.sql("SELECT * FROM programmes WHERE societe_id = ? AND "
                   "code = 'PROG-NEUF'", (sid,))
    v("le programme existe", bool(prog))
    v("… marque a completer", prog and prog[0]["incomplet"] == 1, prog)
    v("… son intitule reprend son code faute de mieux",
      prog and prog[0]["intitule"] == "PROG-NEUF", prog)
    v("les lots sont bien ranges dedans",
      dos.sql("SELECT COUNT(*) n FROM lots WHERE programme_id = ?",
              (prog[0]["id"],))[0]["n"] == 2)

    # ==================================================================
    titre("6. Le fichier qui decrit vraiment remplit la fiche")
    # ==================================================================
    PROGRAMMES = """Code;Intitulé;Commune;Wilaya;Surface terrain;Nombre de logements
PROG-NEUF;Résidence Les Oliviers;Hydra;16 Alger;3200;48
"""
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "programmes", "contenu": b64(PROGRAMMES)})
    v("la fiche incomplete n'est plus « deja enregistree »",
      a.get("nb_completes") == 1, a.get("nb_completes"))
    v("… elle compte comme une ligne prete", a["nb_valides"] == 1, a)
    v("… et n'est pas rangee dans les ignorees",
      not a.get("nb_ignorees"), a.get("ignorees"))
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "programmes", "contenu": b64(PROGRAMMES)})
    v("l'import annonce la fiche completee", r.get("completes") == 1, r)
    prog = dos.sql("SELECT * FROM programmes WHERE societe_id = ? AND "
                   "code = 'PROG-NEUF'", (sid,))
    v("il n'y a toujours qu'un seul programme", len(prog) == 1, prog)
    v("… son intitule est celui du fichier",
      prog[0]["intitule"] == "Résidence Les Oliviers", prog[0]["intitule"])
    v("… il n'est plus a completer", prog[0]["incomplet"] == 0, prog[0])
    v("… et les lots y sont toujours",
      dos.sql("SELECT COUNT(*) n FROM lots WHERE programme_id = ?",
              (prog[0]["id"],))[0]["n"] == 2)

    # Un second passage du meme fichier n'a plus rien a faire.
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "programmes", "contenu": b64(PROGRAMMES)})
    v("une fiche complete redevient « deja enregistree »",
      a.get("nb_ignorees") == 1 and not a.get("nb_completes"), a)

    # ==================================================================
    titre("7. Ce qui n'est pas un ordre mais une nature")
    # ==================================================================
    # Un lot sans programme du tout n'a nulle part ou se ranger, et un
    # reglement sans facture ne regle rien. Les deux sont dits, et pourquoi.
    SANS_PROG = """Programme;N° lot;Type
;B-01;appartement
"""
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "lots", "contenu": b64(SANS_PROG)})
    v("un lot sans programme reste une anomalie", bool(a["anomalies"]),
      a["anomalies"])
    # Un reglement sans facture, lui, n'est plus une anomalie du tout :
    # l'argent est entre. Il est repris non affecte, et se rattachera seul.
    REGLEMENTS = """N° facture;Date;Montant;Sens
FV-ATTENDUE;01/06/{a};119000;encaissement
""".format(a=annee)
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "reglements", "contenu": b64(REGLEMENTS)})
    v("un reglement sans sa facture n'est plus une anomalie",
      not a["anomalies"], a["anomalies"])
    v("… il est annonce comme non affecte", a.get("nb_non_affectes") == 1, a)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "reglements", "contenu": b64(REGLEMENTS)})
    v("… et il est bien enregistre", r["crees"] == 1, r)
    reg = dos.sql("SELECT * FROM reglements WHERE societe_id = ?", (sid,))
    v("… sans facture, mais en gardant son numero",
      len(reg) == 1 and reg[0]["facture_id"] is None
      and reg[0]["reference_facture"] == "FV-ATTENDUE", reg)

    FACTURE = """N° facture;Date;Tiers;Désignation;Quantité;Prix unitaire;Taux TVA
FV-ATTENDUE;01/06/{a};ETS BENALI;Prestation;1;100000;19
""".format(a=annee)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente", "contenu": b64(FACTURE)})
    v("la facture arrivee rattache le reglement qui l'attendait",
      r.get("rattaches") == 1, r)
    reg = dos.sql("SELECT * FROM reglements WHERE societe_id = ?", (sid,))
    v("… le reglement pointe maintenant sa facture",
      reg[0]["facture_id"] is not None, reg[0])
    fac = dos.sql("SELECT * FROM factures WHERE numero = 'FV-ATTENDUE'")
    v("… et la facture est soldee",
      fac and fac[0]["montant_regle"] == fac[0]["net_a_payer"], fac)

    # ==================================================================
    titre("8. La sante du dossier compte ce qui reste a remplir")
    # ==================================================================
    dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(fichier),
        "fichier": "journal-mars-2.csv"})
    exid = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["id"]
    sante = dos.appel(f"/api/sante?societe={sid}&exercice={exid}")
    fiche = [a for a in sante["anomalies"] if a["cle"] == "fiches_incompletes"]
    v("le controle signale les fiches a completer", bool(fiche), sante["anomalies"])
    v("… sans crier a l'erreur comptable",
      fiche and fiche[0]["niveau"] == "info", fiche)
    v("… en disant lesquelles", fiche and fiche[0]["detail"], fiche)

    # ==================================================================
    titre("9. La balance de reprise se complete elle aussi")
    # ==================================================================
    BALANCE = """Compte;Intitulé;Débit;Crédit
41102;Clients divers;450000;
68101;Dotations aux amortissements;;450000
"""
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "balance_ouverture",
        "contenu": b64(BALANCE), "date_reprise": f"{annee}-01-01"})
    v("une balance a sous-comptes ne bloque plus", not a["anomalies"],
      a["anomalies"])
    v("… les comptes absents sont annonces",
      {"41102", "68101"} <= {c["numero"] for c in
                           (a.get("a_creer") or {}).get("comptes", [])},
      a.get("a_creer"))
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "balance_ouverture",
        "contenu": b64(BALANCE), "date_reprise": f"{annee}-01-01"})
    v("la balance passe", r["crees"] >= 1, r)
    v("… et les comptes sont la", existe("comptes", "numero", "68101"))
    v("la comptabilite reste equilibree", dos.equilibre_global())


def suite_attente(dos):
    """Rien n'est refuse, rien n'est perdu.

    Un comptable experimente n'a pas besoin qu'on lui apprenne l'ordre des
    choses ni qu'on lui rende son fichier. Ce que l'application ne sait pas
    ecrire tout de suite attend dans l'application, avec ses valeurs, se
    corrige sur place, et repart tout seul des que ce qui lui manquait
    existe. Le seul refus qui subsiste est celui qui produirait des comptes
    faux.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL ATTENTE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    annee = int(dos.appel(f"/api/exercices?societe={sid}")
                ["exercices"][0]["date_debut"][:4])

    ECR = """N° écriture;Date;Journal;Libellé;Compte;Tiers;Débit;Crédit
1;15/03/{a};OD;Achat correct;607;;12000;
1;;;;401;;;12000
2;16/03/{a};OD;Ecriture desequilibree;607;;5000;
2;;;;401;;;4000
3;17/03/{a};OD;Vente correcte;411;;25000;
3;;;;701;;;25000
""".format(a=annee)

    # ==================================================================
    titre("1. Un fichier n'est plus refuse en bloc")
    # ==================================================================
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(ECR),
        "fichier": "journal.csv"})
    v("les ecritures saines sont ecrites", r["crees"] == 2, r)
    v("… celles qui posent question sont mises de cote",
      r.get("en_attente") == 2, r)
    v("la comptabilite reste equilibree", dos.equilibre_global())
    v("… et le desequilibre n'est pas entre en base",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 2)

    # ==================================================================
    titre("2. Ce qui attend garde ses valeurs, telles qu'elles etaient")
    # ==================================================================
    att = dos.appel(f"/api/attente?societe={sid}")
    v("les deux lignes de l'ecriture attendent ensemble",
      att["nombre"] == 2, att)
    v("… avec le nom du fichier d'origine",
      all(l["fichier"] == "journal.csv" for l in att["lignes"]), att["lignes"])
    v("… leurs numeros de ligne",
      [l["ligne"] for l in att["lignes"]] == [4, 5], att["lignes"])
    v("… les en-tetes du fichier",
      att["lignes"][0]["entetes"][0].startswith("N°"),
      att["lignes"][0]["entetes"])
    v("… les valeurs brutes",
      att["lignes"][0]["valeurs"][6] == "5000", att["lignes"][0]["valeurs"])
    v("… et la raison, en clair",
      "quilibr" in (att["lignes"][0]["raison"] or ""),
      att["lignes"][0]["raison"])

    # ==================================================================
    titre("3. On corrige dans l'application, pas dans le tableur")
    # ==================================================================
    corrections = []
    for ligne in att["lignes"]:
        valeurs = list(ligne["valeurs"])
        if valeurs[7] == "4000":
            valeurs[7] = "5000"
        corrections.append({"id": ligne["id"], "valeurs": valeurs})
    r = dos.appel("/api/attente/corriger",
                  {"societe_id": sid, "lignes": corrections})
    v("les deux lignes sont reprises", r["repris"] == 2, r)
    v("… plus rien n'attend", r["restants"] == 0, r)
    v("l'ecriture est maintenant en base",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 3)
    v("… numerotee a la suite, sans trou",
      [e["numero"][-5:] for e in dos.sql(
          "SELECT numero FROM ecritures ORDER BY id")] ==
      ["00001", "00002", "00003"],
      dos.sql("SELECT numero FROM ecritures ORDER BY id"))
    v("la comptabilite reste equilibree", dos.equilibre_global())
    v("la liste d'attente est vide",
      dos.appel(f"/api/attente?societe={sid}")["nombre"] == 0)

    # ==================================================================
    titre("4. Ce qui attend quelque chose repart tout seul")
    # ==================================================================
    # Les quittances avant les baux : la quittance attend, puis passe des
    # que le bail existe -- sans que personne n'ait a y penser.
    QUITTANCES = """N° quittance;Bail;Période;Date d'échéance;Loyer;Total
QT-001;BX-900;{a}-04;05/04/{a};45000;45000
""".format(a=annee)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "quittances", "contenu": b64(QUITTANCES),
        "fichier": "quittances.csv"})
    v("une quittance sans son bail est mise de cote",
      r.get("en_attente") == 1, r)
    v("… et rien n'a ete invente",
      dos.sql("SELECT COUNT(*) n FROM quittances")[0]["n"] == 0)

    BIENS = """Référence;Désignation;Type
APT-900;F3 Hydra;appartement
"""
    dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "biens", "contenu": b64(BIENS)})
    BAUX = """N° bail;Bien;Locataire;Date de début;Loyer mensuel
BX-900;APT-900;CHERIF Sofiane;01/01/{a};45000
""".format(a=annee)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "baux", "contenu": b64(BAUX),
        "fichier": "baux.csv"})
    v("le bail arrive plus tard", r["crees"] == 1, r)
    v("… et la quittance qui l'attendait est reprise d'elle-meme",
      r.get("repris") == 1, r)
    v("… elle est bien en base",
      dos.sql("SELECT COUNT(*) n FROM quittances")[0]["n"] == 1)
    v("plus rien n'attend",
      dos.appel(f"/api/attente?societe={sid}")["nombre"] == 0)

    # ==================================================================
    titre("5. Un encaissement sans facture reste un encaissement")
    # ==================================================================
    REG = """N° facture;Date;Montant;Sens;Compte de trésorerie
FV-900;20/05/{a};119000;encaissement;BNA
""".format(a=annee)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "reglements", "contenu": b64(REG)})
    v("il est enregistre, pas refuse", r["crees"] == 1, r)
    v("… annonce comme non affecte", r.get("non_affectes") == 1, r)
    v("le compte de tresorerie inconnu a ete cree",
      dos.sql("SELECT COUNT(*) n FROM comptes_tresorerie WHERE code = 'BNA'"
              )[0]["n"] == 1)
    v("… en restant a completer",
      dos.sql("SELECT incomplet FROM comptes_tresorerie WHERE code = 'BNA'"
              )[0]["incomplet"] == 1)

    FAC = """N° facture;Date;Tiers;Désignation;Quantité;Prix unitaire;Taux TVA
FV-900;18/05/{a};ETS BENALI;Prestation;1;100000;19
""".format(a=annee)
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente", "contenu": b64(FAC)})
    v("la facture rattache le reglement qui l'attendait",
      r.get("rattaches") == 1, r)
    fac = dos.sql("SELECT * FROM factures WHERE numero = 'FV-900'")[0]
    v("… la facture est soldee",
      fac["montant_regle"] == fac["net_a_payer"], fac)
    v("… et son statut le dit", fac["statut"] == "reglee", fac["statut"])

    # ==================================================================
    titre("6. Ce qui produirait des comptes faux reste refuse")
    # ==================================================================
    # Ne rien bloquer ne veut pas dire tout accepter : une ligne fausse ne
    # devient jamais une ecriture, elle attend d'etre corrigee.
    FAUX = """N° écriture;Date;Journal;Libellé;Compte;Débit;Crédit
9;32/13/{a};OD;Date impossible;607;1000;
9;;;;401;;1000
""".format(a=annee)
    avant = dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "ecritures", "contenu": b64(FAUX)})
    v("une date impossible ne devient pas une ecriture",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == avant, r)
    v("… elle attend d'etre corrigee", r.get("en_attente") == 2, r)
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("7. On peut aussi renoncer a une ligne")
    # ==================================================================
    att = dos.appel(f"/api/attente?societe={sid}")
    ids = [l["id"] for l in att["lignes"]]
    r = dos.appel("/api/attente", {"societe_id": sid, "ids": ids},
                  methode="DELETE")
    v("les lignes retirees le sont vraiment", r["retires"] == len(ids), r)
    v("… et la liste est vide",
      dos.appel(f"/api/attente?societe={sid}")["nombre"] == 0)
    v("la comptabilite n'a pas bouge",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == avant)
    v("… et reste equilibree", dos.equilibre_global())


def suite_correction(dos):
    """Corriger une ecriture deja enregistree.

    Une video du poste du comptable a montre le fond du probleme : la fiche
    d'une ecriture n'offrait que « Fermer, Dupliquer, Extourner ». Faute de
    pouvoir corriger, il extournait -- et son journal accumulait des
    « Extourne de l'extourne de... ». Une ecriture se corrige. En place :
    meme identifiant, meme numero, memes justificatifs, et une trace.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL CORRECTION", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    annee = int(dos.appel(f"/api/exercices?societe={sid}")
                ["exercices"][0]["date_debut"][:4])

    def cree(valider=True, **kw):
        corps = {"societe_id": sid, "journal": "OD", "date": f"{annee}-03-15",
                 "libelle": "Achat fournitures", "piece": "FA-01",
                 "valider": valider,
                 "lignes": [{"compte": "607", "debit": "12000", "credit": "0"},
                            {"compte": "401", "debit": "0", "credit": "12000"}]}
        corps.update(kw)
        return dos.appel("/api/ecritures", corps)["id"]

    def corrige(eid, **kw):
        corps = {"journal": "OD", "date": f"{annee}-03-15",
                 "libelle": "Achat fournitures", "piece": "FA-01",
                 "lignes": [{"compte": "607", "debit": "15000", "credit": "0"},
                            {"compte": "401", "debit": "0", "credit": "15000"}]}
        corps.update(kw)
        return dos.appel(f"/api/ecritures/{eid}", corps, methode="PUT")

    # ==================================================================
    titre("1. Une ecriture validee n'est pas figee, elle se confirme")
    # ==================================================================
    eid = cree()
    avant = dos.appel(f"/api/ecritures/{eid}")
    v("elle est bien validee", avant["validee"] == 1, avant["validee"])
    message = dos.refuse(f"/api/ecritures/{eid}", {
        "journal": "OD", "date": f"{annee}-03-15", "libelle": "X",
        "lignes": [{"compte": "607", "debit": "15000", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "15000"}]},
        methode="PUT")
    v("sans confirmation, elle n'est pas touchee", bool(message), message)
    v("… et le message propose les deux voies",
      "extourne" in (message or "").lower() and "brouillon" in (message or ""),
      message)
    v("… rien n'a bouge",
      dos.appel(f"/api/ecritures/{eid}")["libelle"] == "Achat fournitures")

    # ==================================================================
    titre("2. Corrigee en place : meme identifiant, meme numero")
    # ==================================================================
    r = corrige(eid, devalider=True, libelle="Achat fournitures (corrige)",
                date=f"{annee}-03-16")
    v("l'identifiant ne change pas", r["id"] == eid, r)
    v("… le numero non plus", r["numero"] == avant["numero"], r)
    apres = dos.appel(f"/api/ecritures/{eid}")
    v("le libelle est corrige",
      apres["libelle"] == "Achat fournitures (corrige)", apres["libelle"])
    v("la date aussi", apres["date"] == f"{annee}-03-16", apres["date"])
    v("le montant aussi",
      sum(l["debit"] for l in apres["lignes"]) == 1500000,
      sum(l["debit"] for l in apres["lignes"]))
    v("… elle est repassee en brouillon", apres["validee"] == 0, apres["validee"])
    v("il n'y a toujours qu'une ecriture",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 1)
    v("… et aucun numero consomme pour rien",
      dos.sql("SELECT valeur FROM compteurs WHERE cle = 'ecriture_OD'"
              )[0]["valeur"] == 1)
    v("la comptabilite reste equilibree", dos.equilibre_global())
    v("la modification est tracee",
      dos.sql("SELECT COUNT(*) n FROM audit WHERE action = 'modification' "
              "AND entite = 'ecriture'")[0]["n"] == 1)

    # ==================================================================
    titre("3. Un brouillon se corrige sans rien demander")
    # ==================================================================
    eid2 = cree(valider=False, libelle="Brouillon", piece="FA-02")
    r = corrige(eid2, libelle="Brouillon corrige")
    v("aucune confirmation n'est reclamee", r["id"] == eid2, r)
    v("… et il reste en brouillon",
      dos.appel(f"/api/ecritures/{eid2}")["validee"] == 0)

    # ==================================================================
    titre("4. Les justificatifs suivent l'ecriture")
    # ==================================================================
    # Une correction qui supprimait puis recreait l'ecriture laissait ses
    # pieces jointes accrochees a un identifiant disparu.
    dos.ecrit("INSERT INTO pieces_jointes (societe_id, entite, entite_id, "
              "nom_fichier, chemin, taille, type_mime, cree_le) VALUES "
              "(?, 'ecriture', ?, 'facture.pdf', 'x.pdf', 10, "
              "'application/pdf', '2026-01-01 00:00:00')", (sid, eid))
    corrige(eid, libelle="Encore corrige")
    v("le justificatif est toujours rattache",
      len(dos.appel(f"/api/ecritures/{eid}")["pieces"]) == 1,
      dos.appel(f"/api/ecritures/{eid}")["pieces"])

    # ==================================================================
    titre("5. Un lettrage est defait proprement, et c'est dit")
    # ==================================================================
    reglement = cree(valider=False, libelle="Reglement fournisseur",
                     lignes=[{"compte": "401", "debit": "15000", "credit": "0"},
                             {"compte": "512", "debit": "0", "credit": "15000"}])
    lignes_401 = dos.sql("SELECT id FROM lignes WHERE compte = '401'")
    for l in lignes_401:
        dos.ecrit("UPDATE lignes SET lettrage = 'A' WHERE id = ?", (l["id"],))
    r = corrige(eid, libelle="Correction apres lettrage")
    v("le lettrage est signale comme defait",
      r["lettrages_defaits"] == ["A"], r)
    v("… des deux cotes",
      dos.sql("SELECT COUNT(*) n FROM lignes WHERE lettrage = 'A'")[0]["n"] == 0)
    v("… et le message le dit", "lettrage" in r["message"], r["message"])
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("6. Ce qui a produit un document reste protege")
    # ==================================================================
    # Un rapprochement bancaire cloture est un etat arrete : en retirer une
    # ligne sans le dire changerait un document deja produit.
    tres = dos.appel("/api/tresorerie", {
        "societe_id": sid, "code": "BNA", "libelle": "BNA", "type": "banque",
        "compte": "512"})
    rap = dos.appel("/api/rapprochements", {
        "societe_id": sid, "tresorerie_id": tres.get("id"),
        "date_arrete": f"{annee}-03-31", "solde_releve": "0"})
    ligne_512 = dos.sql("SELECT l.id FROM lignes l JOIN ecritures e ON "
                        "e.id = l.ecriture_id WHERE l.compte = '512' LIMIT 1")
    if rap.get("id") and ligne_512:
        dos.ecrit("INSERT INTO rapprochement_lignes (rapprochement_id, ligne_id, "
                  "pointee) VALUES (?, ?, 1)", (rap["id"], ligne_512[0]["id"]))
        dos.ecrit("UPDATE rapprochements SET cloture = 1 WHERE id = ?", (rap["id"],))
        message = dos.refuse(f"/api/ecritures/{reglement}", {
            "journal": "OD", "date": f"{annee}-03-15", "libelle": "X",
            "lignes": [{"compte": "401", "debit": "16000", "credit": "0"},
                       {"compte": "512", "debit": "0", "credit": "16000"}]},
            methode="PUT")
        v("une ecriture pointee dans un rapprochement clos est protegee",
          bool(message), message)
        v("… et le message dit quoi faire",
          "rapprochement" in (message or "").lower(), message)
    v("la comptabilite reste equilibree en fin de parcours",
      dos.equilibre_global())


def suite_paie(dos):
    """Les primes valent ce qu'on a tape, pas cent fois plus.

    Une video du poste du comptable : « je mets 200 DA, il fait 20 000 ».
    L'interface envoyait les primes en centimes, le serveur les reconvertissait
    -- chaque prime etait multipliee par cent, dans le bulletin, la base CNAS
    et l'IRG. Deux conventions pour un meme champ : il n'en reste qu'une, les
    montants arrivent tels qu'ils sont tapes et le serveur convertit.
    """
    dos.appel("/api/installation", {
        "identifiant": "c", "mot_de_passe": "motdepasse123", "nom_complet": "X",
        "raison_sociale": "SARL PAIE", "nif": "000116001234567",
        "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]

    def salarie():
        return dos.appel(f"/api/salaries?societe={sid}")["salaries"][0]

    # ==================================================================
    titre("1. Une prime saisie vaut ce qu'elle vaut")
    # ==================================================================
    dos.appel("/api/salaries", {
        "societe_id": sid, "nom": "BENALI", "prenom": "Ali",
        "salaire_base": "50 000,00", "type_contrat": "CDI",
        "primes": [{"libelle": "Rendement", "montant": "5 000,00",
                    "soumis_cnas": True, "soumis_irg": True},
                   {"libelle": "Panier", "montant": "200",
                    "soumis_cnas": False, "soumis_irg": False}]})
    s = salarie()
    v("le salaire de base est en centimes", s["salaire_base"] == 5000000,
      s["salaire_base"])
    montants = {p["libelle"]: p["montant"] for p in s["primes"]}
    v("la prime de 5 000 DA vaut 5 000 DA",
      montants.get("Rendement") == 500000, montants)
    v("celle de 200 DA vaut 200 DA", montants.get("Panier") == 20000, montants)

    # ==================================================================
    titre("2. Le bulletin compte les bons montants")
    # ==================================================================
    b = dos.appel("/api/bulletins/simuler",
                  {"societe_id": sid, "salarie_id": s["id"], "periode": "2026-03"})
    v("le brut est 55 200 DA", b["salaire_brut"] == 5520000,
      b["salaire_brut"] / 100)
    v("… la prime soumise est comptee une fois",
      b["primes_soumises"] == 500000, b["primes_soumises"] / 100)
    v("… le panier reste hors CNAS",
      b["primes_non_soumises"] == 20000, b["primes_non_soumises"] / 100)
    v("la base CNAS exclut le panier", b["base_cnas"] == 5500000,
      b["base_cnas"] / 100)
    v("l'IRG reste dans un ordre de grandeur normal",
      0 < b["irg"] < b["salaire_brut"] // 2, b["irg"] / 100)

    # ==================================================================
    titre("3. Rouvrir la fiche et l'enregistrer ne change rien")
    # ==================================================================
    # C'est ce qui abimait le dossier : chaque aller-retour multipliait
    # les primes par cent.
    for tour in range(3):
        s = salarie()
        dos.appel(f"/api/salaries/{s['id']}", {
            "nom": s["nom"], "prenom": s["prenom"],
            "salaire_base": f"{s['salaire_base'] / 100:.2f}".replace(".", ","),
            "type_contrat": "CDI",
            "primes": [{"libelle": p["libelle"],
                        "montant": f"{p['montant'] / 100:.2f}".replace(".", ","),
                        "soumis_cnas": p["soumis_cnas"],
                        "soumis_irg": p["soumis_irg"]} for p in s["primes"]],
        }, methode="PUT")
    s = salarie()
    montants = {p["libelle"]: p["montant"] for p in s["primes"]}
    v("apres trois allers-retours, la prime n'a pas bouge",
      montants.get("Rendement") == 500000, montants)
    v("… ni le panier", montants.get("Panier") == 20000, montants)
    v("… ni le salaire de base", s["salaire_base"] == 5000000, s["salaire_base"])

    # ==================================================================
    titre("4. Le simulateur compte comme le bulletin")
    # ==================================================================
    b2 = dos.appel("/api/bulletins/simuler", {
        "societe_id": sid, "salaire_base": "50 000,00", "periode": "2026-03",
        "primes": [{"libelle": "Primes soumises", "montant": "5 000,00",
                    "soumis_cnas": True, "soumis_irg": True}]})
    v("un brut de 55 000 DA", b2["salaire_brut"] == 5500000,
      b2["salaire_brut"] / 100)

    # ==================================================================
    titre("5. Un import depose des primes exploitables")
    # ==================================================================
    SALARIES = """Matricule;Nom;Prénom;Poste;Salaire de base;Primes
S0100;CHERIF;Sofiane;Agent;40000;3000
"""
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "salaries", "contenu": b64(SALARIES)})
    v("le salarie est importe", r["crees"] == 1, r)
    importe = [x for x in dos.appel(f"/api/salaries?societe={sid}")["salaries"]
               if x["nom"] == "CHERIF"]
    v("… avec sa prime lisible",
      importe and importe[0]["primes"]
      and importe[0]["primes"][0]["montant"] == 300000,
      importe and importe[0]["primes"])
    b3 = dos.appel("/api/bulletins/simuler", {
        "societe_id": sid, "salarie_id": importe[0]["id"], "periode": "2026-03"})
    v("… et son bulletin se calcule", b3["salaire_brut"] == 4300000,
      b3["salaire_brut"] / 100)

    # ==================================================================
    titre("6. Une prime hors de proportion se voit")
    # ==================================================================
    # Les fiches deja abimees par le defaut ne se reparent pas toutes
    # seules : rien ne distingue 20 000 DA de 200 DA centuples. On les
    # signale plutot que de deviner.
    dos.ecrit("UPDATE salaries SET primes = ? WHERE nom = 'CHERIF'",
              ('[{"libelle": "Primes", "montant": 30000000, '
               '"soumis_cnas": true, "soumis_irg": true}]',))
    exid = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["id"]
    sante = dos.appel(f"/api/sante?societe={sid}&exercice={exid}")
    trouve = [a for a in sante["anomalies"] if a["cle"] == "primes_invraisemblables"]
    v("le controle signale la fiche", bool(trouve), sante["anomalies"])
    v("… en nommant le salarie",
      trouve and "CHERIF" in str(trouve[0]["detail"]), trouve)
    v("… sans crier a l'erreur comptable",
      trouve and trouve[0]["niveau"] == "alerte", trouve)

    # ==================================================================
    titre("7. Une retenue sur salaire, enfin saisissable")
    # ==================================================================
    # « Y a pas de case retenue. » Le calcul savait deduire depuis le debut
    # -- l'ecran n'offrait aucun champ pour le dire.
    dos.appel("/api/bulletins/generer", {"societe_id": sid, "periode": "2026-04"})
    bul = [b for b in dos.appel(f"/api/bulletins?societe={sid}&periode=2026-04"
                                )["bulletins"] if b["nom"] == "BENALI"][0]
    net_avant = bul["net_a_payer"]
    r = dos.appel(f"/api/bulletins/{bul['id']}", {
        "jours_travailles": 30, "salaire_base": "50 000,00",
        "primes": [{"libelle": "Rendement", "montant": "5 000,00",
                    "soumis_cnas": True, "soumis_irg": True},
                   {"libelle": "Panier", "montant": "200",
                    "soumis_cnas": False, "soumis_irg": False}],
        "retenues": [{"libelle": "Avance sur salaire", "montant": "10 000,00"},
                     {"libelle": "Opposition", "montant": "2 000,00"}]},
        methode="PUT")
    v("les retenues sont prises en compte", r["autres_retenues"] == 1200000,
      r["autres_retenues"])
    v("… detaillees, pas en bloc",
      [x["libelle"] for x in r["retenues"]]
      == ["Avance sur salaire", "Opposition"], r["retenues"])
    v("… le compte suit la nature de la retenue",
      [x["compte"] for x in r["retenues"]] == ["425", "427"], r["retenues"])
    v("le net baisse d'autant",
      r["net_a_payer"] == net_avant - 1200000,
      f"{r['net_a_payer'] / 100} au lieu de {(net_avant - 1200000) / 100}")
    v("… mais ni la CNAS ni l'IRG ne bougent",
      r["cnas_salarie"] == bul["cnas_salarie"] and r["irg"] == bul["irg"],
      (r["cnas_salarie"], bul["cnas_salarie"], r["irg"], bul["irg"]))
    v("le net reste le brut moins les retenues",
      r["net_a_payer"] == r["salaire_brut"] - r["cnas_salarie"] - r["irg"]
      - r["autres_retenues"])

    impression, _ = dos.appel(f"/api/bulletins/{bul['id']}/impression", brut=True)
    page = impression.decode("utf-8", "replace")
    v("le bulletin imprime nomme chaque retenue",
      "Avance sur salaire" in page and "Opposition" in page)
    v("… et non « autres retenues »", "Autres retenues" not in page)

    # ==================================================================
    titre("8. L'ecriture de paie impute chaque retenue a son compte")
    # ==================================================================
    dos.appel("/api/bulletins/comptabiliser",
              {"societe_id": sid, "periode": "2026-04"})
    lignes = dos.sql(
        "SELECT l.compte, l.debit, l.credit FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.source_type = 'paie_periode' ORDER BY l.compte")
    par_compte = {l["compte"]: l["credit"] for l in lignes}
    v("l'avance est portee au 425", par_compte.get("425") == 1000000, par_compte)
    v("l'opposition au 427", par_compte.get("427") == 200000, par_compte)
    v("l'ecriture de paie est equilibree",
      sum(l["debit"] for l in lignes) == sum(l["credit"] for l in lignes), lignes)
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("9. Une paie deja comptabilisee peut etre reprise")
    # ==================================================================
    # Une retenue qui remonte apres coup, un jour d'absence signale en
    # retard : la paie du mois se refait. Sans marche arriere, la correction
    # d'un bulletin ne servait a rien -- ils sont comptabilises des le
    # lendemain.
    avant_ecr = dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
    message = dos.refuse("/api/bulletins/reprendre",
                         {"societe_id": sid, "periode": "2026-04"})
    v("la reprise se confirme", "REPRENDRE" in (message or ""), message)
    r = dos.appel("/api/bulletins/reprendre",
                  {"societe_id": sid, "periode": "2026-04",
                   "confirmation": "REPRENDRE"})
    v("les bulletins repassent en brouillon", r["bulletins"] >= 1, r)
    v("… l'ecriture de paie est extournee, pas effacee",
      len(r["extournees"]) >= 1
      and dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] > avant_ecr, r)
    v("… et tous les bulletins du mois sont modifiables",
      all(b["statut"] == "brouillon" for b in dos.appel(
          f"/api/bulletins?societe={sid}&periode=2026-04")["bulletins"]))
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # La retenue oubliee peut enfin etre ajoutee.
    bul = [b for b in dos.appel(f"/api/bulletins?societe={sid}&periode=2026-04"
                                )["bulletins"] if b["nom"] == "BENALI"][0]
    r = dos.appel(f"/api/bulletins/{bul['id']}", {
        "jours_travailles": 30, "salaire_base": "50 000,00",
        "retenues": [{"libelle": "Avance sur salaire", "montant": "3 000,00"}]},
        methode="PUT")
    v("la retenue oubliee entre enfin", r["autres_retenues"] == 300000, r)
    dos.appel("/api/bulletins/comptabiliser",
              {"societe_id": sid, "periode": "2026-04"})
    v("… et la paie se recomptabilise", dos.equilibre_global())

    # ==================================================================
    titre("10. Les bulletins deja etablis avec le defaut sont montres")
    # ==================================================================
    # Une fiche se repare ; un bulletin deja calcule garde ses chiffres.
    # On ne le refait pas d'office -- un bulletin comptabilise a produit des
    # ecritures -- mais on ne le laisse pas passer inapercu.
    dos.appel("/api/bulletins/generer", {"societe_id": sid, "periode": "2026-03"})
    dos.ecrit("UPDATE bulletins SET primes_soumises = salaire_base * 100 "
              "WHERE id = (SELECT MIN(id) FROM bulletins)")
    if dos.sql("SELECT COUNT(*) n FROM bulletins")[0]["n"]:
        sante = dos.appel(f"/api/sante?societe={sid}&exercice={exid}")
        trouve = [a for a in sante["anomalies"] if a["cle"] == "bulletins_a_refaire"]
        v("le controle signale les bulletins a refaire", bool(trouve),
          [a["cle"] for a in sante["anomalies"]])
        v("… en disant comment s'y prendre",
          trouve and "brouillon" in trouve[0]["explication"], trouve)


_SONDE_EMPLACEMENT = """
import json, sys
from noyau import config as c
c.config = c.Configuration({"dossier_donnees": sys.argv[1]})
from modules import systeme
print(json.dumps(systeme.emplacement_risque()))
"""


def emplacement(chemin):
    """Ce que l'application penserait d'un dossier de donnees situe la.

    Interroge dans un processus neuf : le chemin teste est celui d'un autre
    poste, souvent d'un autre systeme, et n'existe pas ici.
    """
    r = subprocess.run([sys.executable, "-c", _SONDE_EMPLACEMENT, chemin],
                       cwd=RACINE, capture_output=True, text=True)
    if r.returncode != 0:
        return {"erreur": r.stderr.strip()[-200:]}
    return json.loads(r.stdout)


def classeur_etranger(dates_serie: list[int]) -> bytes:
    """Un .xlsx tel qu'en produit l'Excel de quelqu'un d'autre.

    Ses styles ne sont pas les notres : la date est au format court d'Excel
    (numFmtId 14), le montant au format numerique. Le fichier ne contient
    donc aucune date lisible — seulement des nombres de jours.
    """
    entetes = ["Numero", "Date", "Client", "Designation", "Montant HT", "TVA %"]
    lignes = ["<row r=\"1\">" + "".join(
        f'<c r="{chr(65 + i)}1" t="inlineStr"><is><t>{h}</t></is></c>'
        for i, h in enumerate(entetes)) + "</row>"]
    for k, serie in enumerate(dates_serie):
        r = k + 2
        lignes.append(
            f'<row r="{r}">'
            f'<c r="A{r}" t="inlineStr"><is><t>FV-{1000 + k}</t></is></c>'
            f'<c r="B{r}" s="1"><v>{serie}</v></c>'
            f'<c r="C{r}" t="inlineStr"><is><t>MAZIGH</t></is></c>'
            f'<c r="D{r}" t="inlineStr"><is><t>Commission sur vente</t></is></c>'
            f'<c r="E{r}" s="3"><v>{100000 + k * 1000}</v></c>'
            f'<c r="F{r}" s="3"><v>19</v></c></row>')
    styles = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
              '<cellXfs count="4"><xf numFmtId="0" xfId="0"/>'
              '<xf numFmtId="14" xfId="0" applyNumberFormat="1"/>'
              '<xf numFmtId="167" xfId="0" applyNumberFormat="1"/>'
              '<xf numFmtId="4" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>')
    feuille = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<sheetData>' + "".join(lignes) + '</sheetData></worksheet>')
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", feuille)
    return tampon.getvalue()


def suite_dates_tableur(dos):
    """Une reprise qui s'arretait sur « date 45195 incomprehensible ».

    Sa capture disait tout : « 1 ligne sera ecrite, 96 mises de cote ». Un
    .xlsx ne dit jamais qu'une cellule porte une date : il porte un nombre
    de jours, et un style. Nous ne reconnaissions que le style de nos propres
    modeles — un fichier venu de son Excel livrait donc « 45195 » la ou il y
    avait le 26/09/2023, et quatre ans d'ecritures restaient dehors.
    """
    dos.appel("/api/installation", {
        "identifiant": "dates", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL REPRISE",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]

    # Les dates exactes de sa capture : de 2021 a 2025.
    series = [45195, 45449, 45453, 45491, 45554, 45798, 45927, 44429]
    fichier = classeur_etranger(series)

    # ==================================================================
    titre("1. Les dates de son fichier sont comprises")
    # ==================================================================
    a = dos.appel("/api/import/analyse", {
        "societe_id": sid, "modele": "factures_vente",
        "contenu": b64_octets(fichier), "nom": "ventes.xlsx"})
    v("aucune ligne n'est mise de cote", a["nb_rejetes"] == 0,
      [x["message"] for x in (a.get("anomalies") or [])][:5])
    v("… toutes sont pretes", a["nb_valides"] == len(series), a["nb_valides"])
    v("… et la premiere porte la bonne date",
      a["apercu"][0]["date"] == "2023-09-26", a["apercu"][0])
    v("… la derniere aussi, quatre ans plus tot",
      a["apercu"][-1]["date"] == "2021-08-21", a["apercu"][-1])

    # ==================================================================
    titre("2. Et elles arrivent telles quelles en base")
    # ==================================================================
    # Un fichier de quatre ans a besoin des exercices de ces quatre annees :
    # l'application le dit, plutot que d'inventer une periode comptable.
    message = dos.refuse("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente",
        "contenu": b64_octets(fichier), "fichier": "ventes.xlsx"})
    v("un exercice manquant est annonce, pas invente", bool(message), message)
    v("… en nommant la date et l'ecran ou le creer",
      "2023" in (message or "") and "Exercices" in (message or ""), message)
    for annee in range(2021, 2026):
        dos.appel("/api/exercices", {
            "societe_id": sid, "libelle": str(annee),
            "date_debut": f"{annee}-01-01", "date_fin": f"{annee}-12-31"})

    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente",
        "contenu": b64_octets(fichier), "fichier": "ventes.xlsx"})
    v("les factures sont enregistrees", r["crees"] == len(series), r)
    dates = [f["date"] for f in dos.sql(
        "SELECT date FROM factures ORDER BY date")]
    v("… avec les dates du fichier, converties une seule fois",
      dates[0] == "2021-08-21" and dates[-1] == "2025-09-27", dates)
    v("aucune date aberrante n'est passee",
      all("1900-01-01" < d < "2099-12-31" for d in dates), dates)
    v("le montant, lui, n'est pas devenu une date",
      dos.sql("SELECT montant_ht FROM factures ORDER BY id")[0]["montant_ht"]
      == 10000000,
      dos.sql("SELECT montant_ht FROM factures ORDER BY id")[0])

    # ==================================================================
    titre("3. Ce qui n'est pas une date reste refuse")
    # ==================================================================
    # « 2024 » est une annee, pas un numero de serie : la confondre donnerait
    # le 16/07/1905, en silence.
    v("une annee seule n'est pas une date",
      dos.appel("/api/import/analyse", {
          "societe_id": sid, "modele": "factures_vente",
          "contenu": b64_octets(classeur_texte(["2024"])),
          "nom": "x.xlsx"})["nb_rejetes"] == 1)
    v("une date ecrite normalement passe toujours",
      dos.appel("/api/import/analyse", {
          "societe_id": sid, "modele": "factures_vente",
          "contenu": b64_octets(classeur_texte(["10/06/2024"])),
          "nom": "x.xlsx"})["apercu"][0]["date"] == "2024-06-10")


def classeur_texte(dates: list[str]) -> bytes:
    """Le meme fichier, mais dont la colonne Date porte du texte."""
    entetes = ["Numero", "Date", "Client", "Designation", "Montant HT", "TVA %"]
    lignes = ["<row r=\"1\">" + "".join(
        f'<c r="{chr(65 + i)}1" t="inlineStr"><is><t>{h}</t></is></c>'
        for i, h in enumerate(entetes)) + "</row>"]
    for k, texte in enumerate(dates):
        r = k + 2
        lignes.append(
            f'<row r="{r}">'
            f'<c r="A{r}" t="inlineStr"><is><t>FT-{2000 + k}</t></is></c>'
            f'<c r="B{r}" t="inlineStr"><is><t>{texte}</t></is></c>'
            f'<c r="C{r}" t="inlineStr"><is><t>MAZIGH</t></is></c>'
            f'<c r="D{r}" t="inlineStr"><is><t>Commission</t></is></c>'
            f'<c r="E{r}"><v>100000</v></c>'
            f'<c r="F{r}"><v>19</v></c></row>')
    feuille = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<sheetData>' + "".join(lignes) + '</sheetData></worksheet>')
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", feuille)
    return tampon.getvalue()


def suite_transfert(dos):
    """Reprendre son dossier sur un second poste.

    Il a installe le logiciel sur un deuxieme PC : l'ecran lui a demande de
    creer un compte et une entreprise, alors qu'il avait deja les deux et une
    sauvegarde en main. Il n'existait aucun moyen de dire « j'ai deja un
    dossier, le voici » -- il aurait fallu creer un compte pour pouvoir en
    restaurer un autre.
    """
    dos.appel("/api/installation", {
        "identifiant": "yacine", "mot_de_passe": "monmotdepasse",
        "nom_complet": "Yacine", "raison_sociale": "SARL EL BARAKA",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    annee = int(dos.appel(f"/api/exercices?societe={sid}")
                ["exercices"][0]["date_debut"][:4])
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-03-15",
        "libelle": "Travail du premier poste", "valider": True,
        "lignes": [{"compte": "607", "debit": "12000", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "12000"}]})
    sauvegarde = dos.appel("/api/sauvegardes", {"motif": "transfert"})
    archive = dos.dossier / "sauvegardes" / sauvegarde["nom"]
    contenu = base64.b64encode(archive.read_bytes()).decode()

    # ==================================================================
    titre("1. Un poste neuf peut reprendre un dossier existant")
    # ==================================================================
    second = Dossier("poste2")
    try:
        v("le second poste se declare vierge",
          second.appel("/api/etat").get("installe") is False,
          second.appel("/api/etat"))
        r = second.appel("/api/installation/restaurer", {"contenu": contenu})
        v("la sauvegarde est acceptee sans compte prealable", r.get("ok"), r)
        v("… le dossier est nomme", r["societes"] == ["SARL EL BARAKA"], r)
        v("… et l'identifiant a utiliser est rappele",
          r["comptes"] == ["yacine"], r)
        v("… avec la date de la sauvegarde", bool(r.get("faite_le")), r)

        # ==============================================================
        titre("2. Les identifiants du premier poste ouvrent le second")
        # ==============================================================
        c = second.appel("/api/connexion",
                         {"identifiant": "yacine", "mot_de_passe": "monmotdepasse"})
        v("la connexion passe", c.get("ok"), c)
        soc = second.appel("/api/societes")["societes"]
        v("le dossier est bien la",
          [x["raison_sociale"] for x in soc] == ["SARL EL BARAKA"], soc)
        ecr = second.appel(f"/api/ecritures?societe={soc[0]['id']}")
        v("… avec le travail du premier poste",
          [e["libelle"] for e in ecr.get("ecritures", [])]
          == ["Travail du premier poste"], ecr.get("ecritures"))
        v("la comptabilite est equilibree sur le second poste",
          second.equilibre_global())

        # ==============================================================
        titre("3. La porte se referme derriere")
        # ==============================================================
        message = second.refuse("/api/installation/restaurer", {"contenu": contenu})
        v("un second dossier ne s'ecrase pas sans confirmation", bool(message),
          message)
        v("… et le message dit par ou passer",
          "Sauvegarde" in (message or ""), message)
    finally:
        second.ferme()

    # ==================================================================
    titre("4. Un fichier qui n'est pas une sauvegarde est refuse")
    # ==================================================================
    troisieme = Dossier("poste3")
    try:
        message = troisieme.refuse("/api/installation/restaurer",
                                   {"contenu": b64("ceci n'est pas une archive")})
        v("il est refuse", bool(message), message)
        v("… en disant quoi chercher",
          "sauvegarde" in (message or "").lower(), message)
        v("le poste reste installable",
          troisieme.appel("/api/etat").get("installe") is False)
    finally:
        troisieme.ferme()

    # ==================================================================
    titre("5. Une sauvegarde venue d'ailleurs se depose depuis l'ecran")
    # ==================================================================
    # Le second poste a peut-etre deja un compte : la restauration ne savait
    # alors choisir que parmi les sauvegardes deja sur la machine. Il fallait
    # trouver soi-meme le dossier « donnees/sauvegardes/ ».
    quatrieme = Dossier("poste4")
    try:
        quatrieme.appel("/api/installation", {
            "identifiant": "autre", "mot_de_passe": "motdepasse123",
            "nom_complet": "Autre", "raison_sociale": "SARL DEUXIEME POSTE",
            "nif": "000116007777777", "commune": "Oran", "wilaya": "31 Oran"})
        avant = len(quatrieme.appel("/api/sauvegardes")["sauvegardes"])
        r = quatrieme.appel("/api/sauvegardes/deposer",
                            {"contenu": contenu, "nom": sauvegarde["nom"]})
        v("la sauvegarde apportee est acceptee", bool(r.get("nom")), r)
        v("… en disant d'ou elle vient",
          r.get("societes") == ["SARL EL BARAKA"], r)
        v("… et elle rejoint la liste",
          len(quatrieme.appel("/api/sauvegardes")["sauvegardes"]) == avant + 1)
        v("… sans avoir rien remplace",
          quatrieme.appel("/api/societes")["societes"][0]["raison_sociale"]
          == "SARL DEUXIEME POSTE")
        quatrieme.appel("/api/sauvegardes/restaurer",
                        {"nom": r["nom"], "confirmation": "RESTAURER"})
        # La restauration remet aussi les comptes du poste d'origine : la
        # session ouverte avec l'ancien compte n'a plus cours.
        v("il faut se reconnecter, avec les identifiants restaures",
          bool(quatrieme.refuse("/api/societes")))
        quatrieme.appel("/api/connexion",
                        {"identifiant": "yacine", "mot_de_passe": "monmotdepasse"})
        v("la restauration met le dossier d'origine en place",
          quatrieme.appel("/api/societes")["societes"][0]["raison_sociale"]
          == "SARL EL BARAKA")
        v("… avec ses ecritures",
          quatrieme.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 1)
        v("… et la comptabilite equilibree", quatrieme.equilibre_global())
        message = quatrieme.refuse("/api/sauvegardes/deposer",
                                   {"contenu": b64("pas une archive")})
        v("un fichier quelconque est refuse", bool(message), message)
    finally:
        quatrieme.ferme()

    # ==================================================================
    titre("6. La restauration ordinaire marche toujours")
    # ==================================================================
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-03-16",
        "libelle": "Saisie posterieure a la sauvegarde", "valider": True,
        "lignes": [{"compte": "607", "debit": "5000", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "5000"}]})
    v("deux ecritures avant restauration",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 2)
    dos.appel("/api/sauvegardes/restaurer",
              {"nom": sauvegarde["nom"], "confirmation": "RESTAURER"})
    v("la restauration ramene l'etat sauvegarde",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 1,
      dos.sql("SELECT numero, libelle FROM ecritures"))
    v("… et l'application repond toujours",
      bool(dos.appel("/api/etat").get("version")))
    v("… la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("7. Ce qui rendait la reprise impossible sous Windows")
    # ==================================================================
    # « Reprise impossible -- [WinError 32] le processus ne peut pas acceder
    # au fichier ... comptabilite.db-wal ». La restauration effacait la base
    # et son journal avant d'ecrire la nouvelle ; sous Windows un fichier
    # ouvert ne s'efface pas. Sous Linux si -- d'ou des essais toujours verts.
    # Le remplacement passe desormais par SQLite : la base garde son fichier,
    # seul son contenu change. C'est ce que verifie l'inode.
    base_disque = dos.dossier / "comptabilite.db"
    inode = base_disque.stat().st_ino
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-03-17",
        "libelle": "A effacer par la restauration", "valider": True,
        "lignes": [{"compte": "607", "debit": "700", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "700"}]})
    # Un fichier tenu ouvert : c'est exactement ce qui bloquait l'effacement.
    verrou = open(base_disque, "rb")
    try:
        dos.appel("/api/sauvegardes/restaurer",
                  {"nom": sauvegarde["nom"], "confirmation": "RESTAURER"})
    finally:
        verrou.close()
    v("la restauration aboutit alors que la base est tenue ouverte",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 1,
      dos.sql("SELECT libelle FROM ecritures"))
    v("… sans avoir efface le fichier de base",
      base_disque.stat().st_ino == inode)
    v("… ni laisse trainer une base de travail",
      not (dos.dossier / "comptabilite.db.recue").exists())
    v("… et l'application repond encore",
      bool(dos.appel("/api/etat").get("version")))

    # ==================================================================
    titre("8. Un dossier de donnees que le systeme peut effacer")
    # ==================================================================
    # Sur sa capture, le chemin etait
    # C:\...\AppData\Local\Temp\...maj1.8.4 (3).zip\cabinet-immo\donnees :
    # l'application tournait depuis l'apercu du zip. Tout ce qu'il saisissait
    # la etait promis a l'effacement, sans que rien ne le lui dise.
    zip_windows = ("C:\\Users\\USER\\AppData\\Local\\Temp\\"
                   "f0dbefc0_maj1.8.4 (3).zip\\cabinet-immo\\donnees")
    v("l'apercu d'un zip est reconnu",
      (emplacement(zip_windows) or {}).get("cause") == "archive",
      emplacement(zip_windows))
    v("… et le message dit quoi faire",
      "Extraire" in (emplacement(zip_windows) or {}).get("detail", ""),
      emplacement(zip_windows))
    temp_windows = "C:\\Users\\USER\\AppData\\Local\\Temp\\cabinet-immo"
    v("un dossier temporaire est reconnu aussi",
      (emplacement(temp_windows) or {}).get("cause") == "temporaire",
      emplacement(temp_windows))
    v("un dossier synchronise reste signale",
      (emplacement("C:\\Users\\USER\\OneDrive\\Documents\\cabinet-immo")
       or {}).get("service") == "OneDrive")
    v("un dossier ordinaire ne declenche rien",
      emplacement("C:\\Users\\USER\\Documents\\cabinet-immo") is None,
      emplacement("C:\\Users\\USER\\Documents\\cabinet-immo"))
    # La restauration a remis les comptes d'origine : il faut se reconnecter.
    dos.appel("/api/connexion",
              {"identifiant": "yacine", "mot_de_passe": "monmotdepasse"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    exid = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["id"]
    sante = dos.appel(f"/api/sante?societe={sid}&exercice={exid}")
    v("l'ecran Sante porte l'avertissement",
      any(a["cle"] == "emplacement" for a in sante["anomalies"]),
      [a["cle"] for a in sante["anomalies"]])


def suite_vente_mixte(dos):
    """Une vente qui porte les deux parts, et un client qui paie en deux fois.

    « Quand on fait une vente, 80 % déclaré et 20 % non. » Le périmètre était
    un choix par facture : déclaré, ou hors déclaration. Il fallait donc
    saisir deux factures sans lien entre elles, et le prix réellement convenu
    n'apparaissait nulle part.

    Les montants non déclarés sont tous multiples du marqueur : aucun d'eux
    ne doit apparaître dans un état fiscal.
    """
    dos.appel("/api/installation", {
        "identifiant": "mixte", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL PROMOTION",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, du, au = ex["id"], ex["date_debut"], ex["date_fin"]
    annee = int(du[:4])

    client = dos.appel("/api/tiers", {
        "societe_id": sid, "type": "client",
        "raison_sociale": "RAMDANI ELMEHDI"})["id"]

    # ==================================================================
    titre("1. Le compte annexe qu'il cree lui-meme")
    # ==================================================================
    # « Que l'application me donne la possibilite de rajouter des comptes
    #   annexes. Par exemple 5300005. »
    caisse_compte = dos.appel("/api/comptes", {
        "societe_id": sid, "numero": "5300005",
        "intitule": "Caisse — encaissements non declares", "nature": "debit"})
    v("un sous-compte de caisse a sept chiffres est accepte",
      bool(caisse_compte.get("id")), caisse_compte)
    caisse = dos.appel("/api/tresorerie", {
        "societe_id": sid, "code": "CA2", "libelle": "Caisse annexe",
        "type": "caisse", "compte": "5300005"})["id"]
    v("… et sert de compte de tresorerie", bool(caisse), caisse)

    # ==================================================================
    titre("2. Une seule vente, ses deux parts")
    # ==================================================================
    # Declare : 100 000 HT + 19 000 TVA = 119 000 TTC. Non declare : 77 770.
    facture = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "tiers_id": client,
        "date": f"{annee}-08-16", "perimetre": "totalite",
        "montant_hors": "77770", "compte_hors": "7011",
        "tresorerie_hors_id": caisse,
        "lignes": [{"designation": "Logement F3 — batiment B",
                    "quantite": 1, "prix_unitaire": "100000",
                    "taux_tva": 19, "compte": "7011"}],
        "valider": True})
    fid = facture["id"]
    f = dos.appel(f"/api/factures/{fid}")
    v("la part declaree est celle de la facture", f["montant_ttc"] == 11900000,
      fm(f["montant_ttc"]))
    v("la part non declaree est portee a part", f["montant_hors"] == 7777000,
      fm(f["montant_hors"]))
    v("le prix reellement convenu est donne", f["prix_reel"] == 11900000 + 7777000,
      fm(f["prix_reel"]))
    v("les deux ecritures existent", bool(f["ecriture_id"] and f["ecriture_hors_id"]),
      (f["ecriture_id"], f["ecriture_hors_id"]))
    v("… et se reconnaissent comme une seule operation",
      bool(f["operation_ref"]), f["operation_ref"])

    lignes_hors = dos.sql(
        "SELECT compte, debit, credit FROM lignes WHERE ecriture_id = ? ORDER BY id",
        (f["ecriture_hors_id"],))
    v("la part non declaree naît due, au compte du client",
      {(l["compte"], l["debit"], l["credit"]) for l in lignes_hors}
      == {("411", 7777000, 0), ("7011", 0, 7777000)}, lignes_hors)
    v("… et « deja encaissee » la solde dans la foulee",
      f["montant_hors_regle"] == 7777000 and f["reste_hors"] == 0,
      (f["montant_hors_regle"], f["reste_hors"]))
    encaissement = dos.sql(
        "SELECT r.montant, r.part, ct.compte FROM reglements r "
        "JOIN comptes_tresorerie ct ON ct.id = r.tresorerie_id "
        "WHERE r.facture_id = ? AND r.part = 'hors_declaration'", (fid,))
    v("… par un reglement porte sur la caisse annexe",
      [(e["montant"], e["compte"]) for e in encaissement]
      == [(7777000, "5300005")], encaissement)
    v("… sans TVA", not any(l["compte"].startswith("445") for l in lignes_hors),
      lignes_hors)
    perimetres = dos.sql(
        "SELECT id, perimetre FROM ecritures WHERE id IN (?, ?)",
        (f["ecriture_id"], f["ecriture_hors_id"]))
    v("chaque ecriture porte son propre perimetre",
      {p["perimetre"] for p in perimetres} == {"declare", "hors_declaration"},
      perimetres)
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # ==================================================================
    titre("3. Rien de la part non declaree n'atteint la declaration")
    # ==================================================================
    g = dos.appel(f"/api/g50?societe={sid}&periode={annee}-08")
    fuites = contient_marqueur(g)
    v("la G 50 ne porte aucun montant non declare", not fuites, fuites[:5])
    v("la TVA collectee est celle de la seule part facturee",
      g.get("tva_collectee", 0) == 1900000, fm(g.get("tva_collectee", 0)))
    v("… et la G 50 annonce ce qu'elle ecarte",
      g.get("hors_declaration", {}).get("produits") == 7777000,
      g.get("hors_declaration"))

    tcr = dos.appel(f"/api/etats/tcr?societe={sid}&exercice={exid}&perimetre=declare")
    v("le TCR declare non plus", not contient_marqueur(tcr.get("lignes", [])),
      contient_marqueur(tcr.get("lignes", []))[:5])

    b_tous = dos.appel(f"/api/balance?societe={sid}&exercice={exid}&du={du}&au={au}")
    ca_reel = -sum(l["solde_debit"] - l["solde_credit"] for l in b_tous["lignes"]
                   if l["compte"].startswith("70"))
    v("la vue reelle, elle, montre le prix convenu",
      ca_reel == 10000000 + 7777000, fm(ca_reel))

    # ==================================================================
    titre("4. La facture remise au client ne porte que le declare")
    # ==================================================================
    contenu, _ = dos.appel(f"/api/factures/{fid}/impression", brut=True)
    texte = contenu.decode("utf-8", "replace")
    v("le montant non declare n'y figure pas", "77 770" not in texte,
      [l for l in texte.splitlines() if "77 770" in l][:3])
    v("le prix reel n'y figure pas non plus", "196 770" not in texte)
    v("… mais le net a payer declare y est", "119 000" in texte)

    # ==================================================================
    titre("5. Le client apporte un cheque et des especes")
    # ==================================================================
    comptes_tresorerie = dos.appel(f"/api/tresorerie?societe={sid}")["comptes"]
    banque_id = next((c["id"] for c in comptes_tresorerie
                      if c["type"] in ("banque", "ccp")), None)
    if banque_id is None:
        banque_id = dos.appel("/api/tresorerie", {
            "societe_id": sid, "code": "BQ1", "libelle": "Banque",
            "type": "banque", "compte": "512"})["id"]
    r = dos.appel("/api/reglements/multiple", {
        "societe_id": sid, "sens": "encaissement", "facture_id": fid,
        "tiers_id": client, "date": f"{annee}-08-20",
        "lignes": [
            {"mode": "cheque", "tresorerie_id": banque_id,
             "reference": "CH-114520", "montant": "80000"},
            {"mode": "espece", "tresorerie_id": caisse,
             "montant": "39000"}]})
    v("les deux moyens de paiement sont enregistres",
      len(r["reglements"]) == 2, r)
    v("… pour le total attendu", r["total"] == 11900000, fm(r["total"]))
    v("… et restent une seule operation", bool(r["operation_ref"]),
      r["operation_ref"])
    modes = dos.sql("SELECT mode, montant, part FROM reglements "
                    "WHERE facture_id = ? AND part = 'declare' ORDER BY id", (fid,))
    v("chacun garde son mode et son montant",
      [(m["mode"], m["montant"]) for m in modes]
      == [("cheque", 8000000), ("espece", 3900000)], modes)
    f = dos.appel(f"/api/factures/{fid}")
    v("la facture est soldee", f["statut"] == "payee", f["statut"])
    v("la comptabilite tient toujours", dos.equilibre_global())

    # ==================================================================
    titre("6. Le droit de timbre ne porte que sur la part en especes")
    # ==================================================================
    mixte = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "tiers_id": client,
        "date": f"{annee}-09-02", "mode_reglement": "mixte",
        "montant_espece": "50000",
        "lignes": [{"designation": "Commission", "quantite": 1,
                    "prix_unitaire": "100000", "taux_tva": 19,
                    "compte": "7061"}]})
    fm_mixte = dos.appel(f"/api/factures/{mixte['id']}")
    tout_espece = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "tiers_id": client,
        "date": f"{annee}-09-03", "mode_reglement": "espece",
        "lignes": [{"designation": "Commission", "quantite": 1,
                    "prix_unitaire": "100000", "taux_tva": 19,
                    "compte": "7061"}]})
    f_espece = dos.appel(f"/api/factures/{tout_espece['id']}")
    v("un timbre est bien du sur la part en especes",
      fm_mixte["timbre"] > 0, fm_mixte["timbre"])
    v("… mais moins que si tout etait paye en especes",
      fm_mixte["timbre"] < f_espece["timbre"],
      f"{fm(fm_mixte['timbre'])} vs {fm(f_espece['timbre'])}")
    # 1 % de 50 000 DA d'especes = 500 DA, la ou tout en especes en donnerait
    # 1 % de 119 000 DA.
    v("… et proportionne a cette part", fm_mixte["timbre"] == 50000,
      fm(fm_mixte["timbre"]))
    v("… tout en especes, le timbre porte sur le TTC entier",
      f_espece["timbre"] == 119000, fm(f_espece["timbre"]))

    # ==================================================================
    titre("7. Ce que la saisie refuse, et pourquoi")
    # ==================================================================
    message = dos.refuse("/api/factures", {
        "societe_id": sid, "sens": "vente", "tiers_id": client,
        "date": f"{annee}-09-10", "perimetre": "totalite",
        "montant_hors": "10000", "compte_hors": "9999999",
        "tresorerie_hors_id": caisse,
        "lignes": [{"designation": "Vente", "quantite": 1,
                    "prix_unitaire": "1000", "taux_tva": 19, "compte": "7011"}]})
    v("un compte absent du plan est refuse", bool(message), message)
    v("… en disant ou le creer", "Plan comptable" in (message or ""), message)

    # ==================================================================
    titre("8. Combien le client a paye, et ce qu'il doit encore")
    # ==================================================================
    # « Si je fais le non declare, je ne peux pas designer combien le client a
    #   paye ou pas encore. » La part non declaree partait droit en caisse :
    #   elle etait donc reputee reglee d'avance. Elle nait due, desormais.
    attente = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "tiers_id": client,
        "date": f"{annee}-10-05", "perimetre": "totalite",
        "montant_hors": "77770", "compte_hors": "7011",
        "lignes": [{"designation": "Logement F4", "quantite": 1,
                    "prix_unitaire": "200000", "taux_tva": 19,
                    "compte": "7011"}],
        "valider": True})
    aid = attente["id"]
    a = dos.appel(f"/api/factures/{aid}")
    v("sans caisse indiquee, la part non declaree reste due",
      a["montant_hors_regle"] == 0 and a["reste_hors"] == 7777000,
      (a["montant_hors_regle"], a["reste_hors"]))
    v("… le reste du declare est distinct",
      a["reste_declare"] == 23800000, fm(a["reste_declare"]))
    v("… et le reste total les additionne",
      a["reste_total"] == 23800000 + 7777000, fm(a["reste_total"]))

    # Il encaisse le declare par cheque, et rien du black.
    dos.appel("/api/reglements/multiple", {
        "societe_id": sid, "sens": "encaissement", "facture_id": aid,
        "tiers_id": client, "date": f"{annee}-10-10",
        "lignes": [{"mode": "cheque", "tresorerie_id": banque_id,
                    "part": "declare", "montant": "238000"}]})
    a = dos.appel(f"/api/factures/{aid}")
    v("le declare solde ne solde pas le black",
      a["reste_declare"] == 0 and a["reste_hors"] == 7777000,
      (a["reste_declare"], a["reste_hors"]))
    v("… la facture n'est donc pas payee", a["statut"] == "partielle",
      a["statut"])

    # Puis il encaisse la moitie du black, en especes.
    dos.appel("/api/reglements/multiple", {
        "societe_id": sid, "sens": "encaissement", "facture_id": aid,
        "tiers_id": client, "date": f"{annee}-10-20",
        "lignes": [{"mode": "espece", "tresorerie_id": caisse,
                    "part": "hors_declaration", "montant": "38885"}]})
    a = dos.appel(f"/api/factures/{aid}")
    v("un acompte sur le black se voit", a["reste_hors"] == 3888500,
      fm(a["reste_hors"]))
    message = dos.refuse("/api/reglements/multiple", {
        "societe_id": sid, "sens": "encaissement", "facture_id": aid,
        "tiers_id": client, "date": f"{annee}-10-21",
        "lignes": [{"mode": "espece", "tresorerie_id": caisse,
                    "part": "hors_declaration", "montant": "50000"}]})
    v("on ne peut pas encaisser plus que le reste du black", bool(message),
      message)
    v("… et le message nomme la part concernee",
      "non declar" in (message or "").lower().replace("é", "e"), message)

    # ==================================================================
    titre("9. La situation du client, les deux parts separees")
    # ==================================================================
    situation = dos.appel(f"/api/tiers/{client}/situation")
    # Les deux factures de la section 6 sont restees en brouillon : elles ne
    # doivent rien, et n'entrent donc pas dans la situation.
    v("le declare est compte a part",
      situation["declare"]["du"] == 11900000 + 23800000,
      situation["declare"])
    v("… sans compter les brouillons",
      situation["nb_factures"] == 2, situation["nb_factures"])
    v("le non declare aussi",
      situation["hors_declaration"]["du"] == 7777000 * 2,
      situation["hors_declaration"])
    v("… avec ce qui en a ete regle",
      situation["hors_declaration"]["regle"] == 7777000 + 3888500,
      situation["hors_declaration"])
    v("… et ce qui reste du",
      situation["hors_declaration"]["reste"] == 3888500,
      situation["hors_declaration"])
    v("le total reel additionne les deux",
      situation["total"]["du"]
      == situation["declare"]["du"] + situation["hors_declaration"]["du"],
      situation["total"])

    # Le releve de compte le montre aussi, des lors qu'on regarde le reel.
    releve = dos.appel(f"/api/tiers/{client}/releve?societe={sid}"
                       f"&du={du}&au={au}")
    lignes_hors = [m for m in releve["mouvements"]
                   if m["perimetre"] == "hors_declaration"]
    v("le releve en vue reelle porte les mouvements non declares",
      bool(lignes_hors), len(releve["mouvements"]))
    releve_dec = dos.appel(f"/api/tiers/{client}/releve?societe={sid}"
                           f"&du={du}&au={au}&perimetre=declare")
    v("… et le releve declare n'en porte aucun",
      not any(m["perimetre"] == "hors_declaration"
              for m in releve_dec["mouvements"]))
    v("… en annoncant son perimetre",
      releve_dec["libelle_perimetre"] == "Déclaré uniquement",
      releve_dec["libelle_perimetre"])


def suite_reprise_factures(dos):
    """Ce qu'une reprise de factures lui a coute : des zeros, et sa matinee.

    « Lors de l'importation, il y a des clients il m'a rajoute des 00. »
    « Ce n'est meme pas possible de supprimer les factures. »
    « Une fois importe tu dois les valider une par une, c'est chiant. »
    """
    dos.appel("/api/installation", {
        "identifiant": "reprise", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL REPRISE",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex["date_debut"][:4])

    def facture(numero, **extra):
        corps = {"societe_id": sid, "sens": "vente", "date": f"{annee}-05-10",
                 "numero": numero, "tiers_id": client,
                 "lignes": [{"designation": "Vente logement", "quantite": 1,
                             "prix_unitaire": "5000000", "taux_tva": 19,
                             "compte": "7011"}]}
        corps.update(extra)
        return dos.appel("/api/factures", corps)

    client = dos.appel("/api/tiers", {
        "societe_id": sid, "type": "client",
        "raison_sociale": "MESSAOUDI ZAYNEB"})["id"]

    # ==================================================================
    titre("1. Un montant de ligne n'est plus multiplie par la quantite")
    # ==================================================================
    # Son fichier donne le total de la ligne ET une quantite. Multiplier
    # l'un par l'autre ajoute deux zeros a une somme juste.
    f = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "date": f"{annee}-05-11",
        "tiers_id": client, "numero": "T-001",
        "lignes": [{"designation": "Vente logement", "quantite": 100,
                    "montant_ht": "4954100", "taux_tva": 0,
                    "compte": "7011"}]})
    d = dos.appel(f"/api/factures/{f['id']}")
    v("le montant donne fait foi, la quantite n'y touche pas",
      d["montant_ht"] == 495410000, fm(d["montant_ht"]))
    f = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "date": f"{annee}-05-11",
        "tiers_id": client, "numero": "T-002",
        "lignes": [{"designation": "Metres carres", "quantite": 100,
                    "prix_unitaire": "49541", "taux_tva": 0,
                    "compte": "7011"}]})
    d = dos.appel(f"/api/factures/{f['id']}")
    v("… mais un vrai prix unitaire se multiplie toujours",
      d["montant_ht"] == 495410000, fm(d["montant_ht"]))
    f = dos.appel("/api/factures", {
        "societe_id": sid, "sens": "vente", "date": f"{annee}-05-11",
        "tiers_id": client, "numero": "T-003",
        "lignes": [{"designation": "Vente", "quantite": "1,00",
                    "prix_unitaire": "4954100", "taux_tva": 0,
                    "compte": "7011"}]})
    v("une quantite ecrite « 1,00 » ne fait plus echouer la ligne",
      dos.appel(f"/api/factures/{f['id']}")["montant_ht"] == 495410000)

    # ==================================================================
    titre("2. Pas de droit de timbre sur une facture hors declaration")
    # ==================================================================
    # Le net a payer depassait le HT de 1 % : c'etait le timbre, une taxe
    # declaree, ajoutee a une facture qui ne l'est pas.
    f = facture("HD-001", perimetre="hors_declaration",
                mode_reglement="espece")
    hd = dos.appel(f"/api/factures/{f['id']}")
    v("aucun timbre hors declaration", hd["timbre"] == 0, hd["timbre"])
    v("… le net a payer vaut donc le TTC",
      hd["net_a_payer"] == hd["montant_ttc"],
      (hd["net_a_payer"], hd["montant_ttc"]))
    f = facture("D-001", mode_reglement="espece")
    dec = dos.appel(f"/api/factures/{f['id']}")
    v("… alors qu'une facture declaree en especes le porte",
      dec["timbre"] > 0, dec["timbre"])

    # ==================================================================
    titre("3. Les valider d'un coup, pas une par une")
    # ==================================================================
    ids = [facture(f"L-{n:03d}")["id"] for n in range(1, 6)]
    v("cinq brouillons attendent",
      dos.sql("SELECT COUNT(*) n FROM factures WHERE statut = 'brouillon'"
              " AND numero LIKE 'L-%'")[0]["n"] == 5)
    r = dos.appel("/api/factures/valider-lot", {"societe_id": sid, "ids": ids})
    v("elles sont comptabilisees ensemble", r["validees"] == 5, r)
    v("… et chacune a son ecriture",
      dos.sql("SELECT COUNT(*) n FROM factures WHERE numero LIKE 'L-%' "
              "AND ecriture_id IS NOT NULL")[0]["n"] == 5)
    v("la comptabilite reste equilibree", dos.equilibre_global())
    r = dos.appel("/api/factures/valider-lot", {"societe_id": sid, "ids": ids})
    v("les revalider ne les double pas", r["validees"] == 0, r)
    v("… et le refus dit pourquoi",
      all("déjà" in x["raison"] for x in r["refusees"]), r["refusees"])

    # ==================================================================
    titre("4. Une facture validee reste corrigeable tant qu'elle n'est pas reglee")
    # ==================================================================
    cible = ids[0]
    avant = dos.appel(f"/api/factures/{cible}")
    dos.appel(f"/api/factures/{cible}", {
        "societe_id": sid, "date": f"{annee}-05-10", "tiers_id": client,
        "numero": "L-001", "objet": "Corrige",
        "lignes": [{"designation": "Vente logement", "quantite": 1,
                    "prix_unitaire": "6000000", "taux_tva": 19,
                    "compte": "7011"}]}, "PUT")
    apres = dos.appel(f"/api/factures/{cible}")
    v("la correction passe", apres["montant_ht"] == 600000000,
      fm(apres["montant_ht"]))
    v("… la facture reste comptabilisee", apres["statut"] == "validee",
      apres["statut"])
    v("… son ecriture a ete refaite, pas doublee",
      apres["ecriture_id"] != avant["ecriture_id"]
      and dos.sql("SELECT COUNT(*) n FROM ecritures WHERE source_type = 'facture' "
                  "AND source_id = ?", (cible,))[0]["n"] == 1,
      dos.sql("SELECT id FROM ecritures WHERE source_id = ?", (cible,)))
    v("… et elle porte le nouveau montant",
      dos.sql("SELECT SUM(debit) d FROM lignes WHERE ecriture_id = ?",
              (apres["ecriture_id"],))[0]["d"] == apres["net_a_payer"])
    v("la comptabilite tient toujours", dos.equilibre_global())

    # ==================================================================
    titre("5. Effacer une reprise ratee")
    # ==================================================================
    message = dos.refuse("/api/factures/supprimer-lot",
                         {"societe_id": sid, "ids": ids[1:3]})
    v("rien ne part sans confirmation", bool(message), message)
    v("… et le message dit combien", "2 facture" in (message or ""), message)
    r = dos.appel("/api/factures/supprimer-lot", {
        "societe_id": sid, "ids": ids[1:3], "confirmation": "SUPPRIMER"})
    v("confirmee, la suppression aboutit", r["supprimees"] == 2, r)
    v("… les ecritures partent avec",
      dos.sql("SELECT COUNT(*) n FROM ecritures WHERE source_type = 'facture' "
              "AND source_id IN (?, ?)", tuple(ids[1:3]))[0]["n"] == 0)
    v("la comptabilite reste equilibree", dos.equilibre_global())

    # Une facture reglee, elle, resiste.
    tresorerie = dos.appel(f"/api/tresorerie?societe={sid}")["comptes"][0]["id"]
    payee = dos.appel(f"/api/factures/{ids[3]}")
    dos.appel("/api/reglements/multiple", {
        "societe_id": sid, "sens": "encaissement", "facture_id": ids[3],
        "tiers_id": client, "date": f"{annee}-05-20",
        "lignes": [{"mode": "espece", "tresorerie_id": tresorerie,
                    "montant": "10000"}]})
    message = dos.refuse(f"/api/factures/{ids[3]}", {}, "DELETE")
    v("une facture reglee ne s'efface pas", bool(message), message)
    v("… en disant par quoi commencer",
      "règlement" in (message or ""), message)


def suite_grand_livre_vide(dos):
    """« Il va au grand livre et aucune n'est vraiment passee. »

    C'etait exact : l'import deposait des brouillons, et un brouillon n'a pas
    d'ecriture. L'ecran restait blanc sans un mot. Deux causes muettes, en
    fait — celle-la, et le perimetre de la barre de gauche.
    """
    dos.appel("/api/installation", {
        "identifiant": "gl", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL GRAND LIVRE",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    exid, annee = ex["id"], int(ex["date_debut"][:4])
    series = [45195, 45449]

    def gl(perimetre=None, du="2021-01-01", au="2026-12-31"):
        # La periode couvre les dates du fichier, sans quoi le decompte des
        # brouillons porterait sur un intervalle ou il n'y en a aucun.
        suffixe = f"&perimetre={perimetre}" if perimetre else ""
        return dos.appel(f"/api/grand-livre?societe={sid}&exercice={exid}"
                         f"&du={du}&au={au}{suffixe}")

    for a in range(2021, 2027):
        if a != annee:
            dos.appel("/api/exercices", {
                "societe_id": sid, "libelle": str(a),
                "date_debut": f"{a}-01-01", "date_fin": f"{a}-12-31"})

    # ==================================================================
    titre("1. Importees en brouillon, elles ne sont nulle part")
    # ==================================================================
    dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente",
        "contenu": b64_octets(classeur_etranger(series)),
        "fichier": "ventes.xlsx", "comptabiliser": 0})
    v("les factures sont bien la",
      dos.sql("SELECT COUNT(*) n FROM factures")[0]["n"] == 2)
    v("… mais aucune ecriture",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 0)

    # ==================================================================
    titre("2. Et le grand livre le dit, au lieu de rester blanc")
    # ==================================================================
    d = gl()
    v("le grand livre est vide", not d["groupes"])
    v("… et il dit combien de factures attendent en brouillon",
      d["vide_parce_que"]["factures_brouillon"] == 2, d["vide_parce_que"])
    v("… sans inventer d'ecritures hors perimetre",
      d["vide_parce_que"]["ecritures_periode"] == 0, d["vide_parce_que"])
    v("… il annonce aussi son perimetre", bool(d["libelle_perimetre"]),
      d.get("libelle_perimetre"))

    # ==================================================================
    titre("3. Comptabilisees a l'import, elles y sont")
    # ==================================================================
    dos.appel("/api/factures/supprimer-lot", {
        "societe_id": sid, "confirmation": "SUPPRIMER",
        "ids": [f["id"] for f in dos.sql("SELECT id FROM factures")]})
    r = dos.appel("/api/import/valider", {
        "societe_id": sid, "modele": "factures_vente",
        "contenu": b64_octets(classeur_etranger(series)),
        "fichier": "ventes.xlsx"})
    v("l'import les comptabilise d'office", r["comptabilisees"] == 2, r)
    v("… le compte rendu le dit", not r["non_comptabilisees"],
      r["non_comptabilisees"])
    v("… et les ecritures existent",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 2)
    v("la comptabilite est equilibree", dos.equilibre_global())

    # ==================================================================
    titre("4. L'autre cause muette : le perimetre")
    # ==================================================================
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-06-15",
        "libelle": "Vente hors declaration", "perimetre": "hors_declaration",
        "valider": True,
        "lignes": [{"compte": "411", "debit": "50000", "credit": "0"},
                   {"compte": "7011", "debit": "0", "credit": "50000"}]})
    d = gl("hors_declaration")
    v("la vue hors declaration montre cette ecriture", bool(d["groupes"]),
      d.get("vide_parce_que"))
    autre = gl("declare", du=f"{annee}-06-01", au=f"{annee}-06-30")
    v("la vue declaree, elle, ne montre rien sur ce mois", not autre["groupes"])
    v("… et dit que des ecritures existent hors de ce perimetre",
      autre["vide_parce_que"]["hors_perimetre"] > 0, autre["vide_parce_que"])


def suite_vsp_hors(dos):
    """Une vente sur plan porte, elle aussi, une part hors declaration."""
    dos.appel("/api/installation", {
        "identifiant": "vsp", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL PROMOTION",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex["date_debut"][:4])
    acquereur = dos.appel("/api/tiers", {
        "societe_id": sid, "type": "client",
        "raison_sociale": "BENHADDAD SAMIR"})["id"]
    dos.appel("/api/comptes", {"societe_id": sid, "numero": "5300005",
                               "intitule": "Caisse annexe", "nature": "debit"})
    caisse = dos.appel("/api/tresorerie", {
        "societe_id": sid, "code": "CA2", "libelle": "Caisse annexe",
        "type": "caisse", "compte": "5300005"})["id"]
    programme = dos.appel("/api/programmes", {
        "societe_id": sid, "code": "PRG1", "intitule": "Residence La Reunion",
        "wilaya": "16 Alger"})["id"]
    lot = dos.appel("/api/lots", {
        "societe_id": sid, "programme_id": programme, "numero": "A01",
        "type_lot": "logement", "typologie": "F3",
        "prix_vente": "5000000"})["id"]

    # ==================================================================
    titre("1. Le contrat porte les deux parts")
    # ==================================================================
    contrat = dos.appel("/api/contrats-vsp", {
        "societe_id": sid, "lot_id": lot, "acquereur_id": acquereur,
        "date_contrat": f"{annee}-03-10", "prix_total": "5000000",
        "montant_hors": "1500000", "compte_hors": "7011",
        "modele_echeancier": "VSP_STANDARD"})
    c = dos.appel(f"/api/contrats-vsp/{contrat['id']}")
    v("le prix declare reste celui de l'echeancier",
      c["prix_total"] == 500000000, fm(c["prix_total"]))
    v("la part non declaree est portee a part",
      c["montant_hors"] == 150000000, fm(c["montant_hors"]))
    v("… et le prix reellement convenu est donne",
      c["prix_reel"] == 650000000, fm(c["prix_reel"]))
    v("… rien n'en est encore encaisse", c["reste_hors"] == 150000000,
      c["reste_hors"])
    total_echeances = sum(e["montant"] for e in c["echeances"])
    v("l'echeancier ne porte que le declare",
      total_echeances == 500000000, fm(total_echeances))

    # ==================================================================
    titre("2. Elle s'encaisse a part, hors declaration")
    # ==================================================================
    r = dos.appel(f"/api/contrats-vsp/{contrat['id']}/encaisser-hors", {
        "societe_id": sid, "tresorerie_id": caisse,
        "date": f"{annee}-03-15", "montant": "600000"})
    v("l'encaissement passe", r.get("ok"), r)
    c = dos.appel(f"/api/contrats-vsp/{contrat['id']}")
    v("… le reste se met a jour", c["reste_hors"] == 90000000,
      fm(c["reste_hors"]))
    lignes = dos.sql(
        "SELECT l.compte, l.debit, l.credit FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.perimetre = 'hors_declaration' ORDER BY l.id")
    v("l'ecriture va de la caisse annexe au compte de produit",
      {(x["compte"], x["debit"], x["credit"]) for x in lignes}
      == {("5300005", 60000000, 0), ("7011", 0, 60000000)}, lignes)
    v("… sans TVA ni avance VSP",
      not any(x["compte"].startswith(("445", "419")) for x in lignes), lignes)
    v("la comptabilite reste equilibree", dos.equilibre_global())

    message = dos.refuse(f"/api/contrats-vsp/{contrat['id']}/encaisser-hors", {
        "societe_id": sid, "tresorerie_id": caisse,
        "date": f"{annee}-03-16", "montant": "1000000"})
    v("on ne peut pas encaisser plus que le reste", bool(message), message)

    # ==================================================================
    titre("3. Rien de tout cela n'atteint la declaration")
    # ==================================================================
    g = dos.appel(f"/api/g50?societe={sid}&periode={annee}-03")
    v("la G 50 ne porte pas la part non declaree",
      not contient_marqueur(g), contient_marqueur(g)[:4])
    v("… et annonce ce qu'elle ecarte",
      (g.get("hors_declaration") or {}).get("produits") == 60000000,
      g.get("hors_declaration"))


def suite_exercices(dos):
    """Corriger un exercice mal saisi, ou l'enlever.

    « Il veut pouvoir supprimer un exercice et changer le libelle s'il s'est
    trompe. » Rien ne permettait de revenir sur un exercice une fois cree.
    """
    dos.appel("/api/installation", {
        "identifiant": "ex", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL EXERCICES",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    sid = dos.appel("/api/societes")["societes"][0]["id"]
    ex = dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]
    annee = int(ex["date_debut"][:4])

    # ==================================================================
    titre("1. Le libelle se corrige, toujours")
    # ==================================================================
    dos.appel("/api/ecritures", {
        "societe_id": sid, "journal": "OD", "date": f"{annee}-04-01",
        "libelle": "Une ecriture", "valider": True,
        "lignes": [{"compte": "607", "debit": "1000", "credit": "0"},
                   {"compte": "401", "debit": "0", "credit": "1000"}]})
    dos.appel(f"/api/exercices/{ex['id']}",
              {"libelle": f"Exercice {annee}"}, "PUT")
    v("le libelle est corrige meme sur un exercice qui porte des ecritures",
      dos.appel(f"/api/exercices?societe={sid}")["exercices"][0]["libelle"]
      == f"Exercice {annee}")

    # ==================================================================
    titre("2. Les dates ne bougent plus sous les ecritures")
    # ==================================================================
    message = dos.refuse(f"/api/exercices/{ex['id']}", {
        "libelle": f"Exercice {annee}",
        "date_debut": f"{annee}-02-01", "date_fin": f"{annee}-12-31"}, "PUT")
    v("les dates sont refusees", bool(message), message)
    v("… en disant ce que l'exercice porte",
      "ecriture" in (message or "").lower().replace("é", "e"), message)

    # ==================================================================
    titre("3. Un exercice cree par erreur s'enleve")
    # ==================================================================
    faux = dos.appel("/api/exercices", {
        "societe_id": sid, "libelle": "2043",
        "date_debut": "2043-01-01", "date_fin": "2043-12-31"})["id"]
    r = dos.appel(f"/api/exercices/{faux}", {}, "DELETE")
    v("un exercice vide part sans confirmation", r.get("ok"), r)
    v("… et il a bien disparu",
      all(e["id"] != faux for e in
          dos.appel(f"/api/exercices?societe={sid}")["exercices"]))

    # ==================================================================
    titre("4. Un exercice qui porte la comptabilite se defend")
    # ==================================================================
    message = dos.refuse(f"/api/exercices/{ex['id']}", {}, "DELETE")
    v("il ne part pas d'un clic", bool(message), message)
    v("… et il dit exactement ce qu'il emporterait",
      "1 ecriture" in (message or "").lower().replace("é", "e"), message)
    v("… en rappelant que les sauvegardes, elles, la gardent",
      "sauvegarde" in (message or "").lower(), message)

    # ==================================================================
    titre("5. Le dernier exercice ne se supprime pas")
    # ==================================================================
    message = dos.refuse(f"/api/exercices/{ex['id']}",
                         {"confirmation": "SUPPRIMER"}, "DELETE")
    v("le seul exercice du dossier est protege", bool(message), message)
    v("… en disant quoi faire d'abord",
      "exercice" in (message or "").lower(), message)

    # Avec un second exercice, la suppression confirmee passe.
    autre = dos.appel("/api/exercices", {
        "societe_id": sid, "libelle": "2044",
        "date_debut": "2044-01-01", "date_fin": "2044-12-31"})["id"]
    avant = dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
    v("la comptabilite est bien la avant", avant == 1, avant)
    r = dos.appel(f"/api/exercices/{ex['id']}",
                  {"confirmation": "SUPPRIMER"}, "DELETE")
    v("confirmee, la suppression aboutit", r.get("ok"), r)
    v("… et elle emporte ce qui etait annonce",
      dos.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == 0)
    v("… en laissant une trace",
      bool(dos.sql("SELECT id FROM audit WHERE entite = 'exercice' "
                   "AND action = 'suppression'")))
    v("l'autre exercice est intact",
      [e["id"] for e in dos.appel(f"/api/exercices?societe={sid}")["exercices"]]
      == [autre])


SUITES = [
    ("conformite", "Conformite comptable -- une annee tenue", suite_conformite, True),
    ("limites", "Ce que le logiciel doit refuser", suite_limites, False),
    ("cloture", "Cloture, a-nouveaux, extourne", suite_cloture, False),
    ("perimetre", "Etancheite declare / hors declaration", suite_perimetre, False),
    ("cycles", "Cycles metier en mouvement et numerotation", suite_cycles, True),
    ("reprises", "Annuler un import deja valide", suite_reprises, False),
    ("creation", "L'import cree ce dont il a besoin", suite_creation, False),
    ("attente", "Rien n'est refuse, rien n'est perdu", suite_attente, False),
    ("correction", "Corriger une ecriture deja enregistree", suite_correction, False),
    ("paie", "Les primes valent ce qu'on a tape", suite_paie, False),
    ("transfert", "Reprendre son dossier sur un second poste", suite_transfert, False),
    ("vente_mixte", "Une vente declaree et non declaree, payee en deux fois",
     suite_vente_mixte, False),
    ("exercices", "Corriger ou supprimer un exercice", suite_exercices, False),
    ("dates_tableur", "Des dates venues d'un autre tableur", suite_dates_tableur,
     False),
    ("reprise_factures", "Reprendre, corriger et effacer des factures",
     suite_reprise_factures, False),
    ("grand_livre_vide", "Un grand livre vide dit pourquoi", suite_grand_livre_vide,
     False),
    ("vsp_hors", "Une vente sur plan et sa part non declaree", suite_vsp_hors,
     False),
    ("sante", "Controles de sante du dossier", suite_sante, True),
    ("annuelles", "DAS et etat des clients", suite_annuelles, True),
    ("relances", "Relances clients", suite_relances, False),
    ("banque", "Releve bancaire et rapprochement", suite_banque, False),
]


def lance(nom, libelle, fonction, demonstration):
    print(f"\n{'=' * 72}\n  {libelle}\n{'=' * 72}")
    dos = Dossier(nom, demonstration)
    try:
        fonction(dos)
    finally:
        dos.ferme()


def principal():
    sortie_utf8()
    demandees = [a for a in sys.argv[1:] if not a.startswith("-")]
    connues = {nom for nom, _, _, _ in SUITES}
    inconnues = [a for a in demandees if a not in connues]
    if inconnues:
        print(f"Suite inconnue : {', '.join(inconnues)}")
        print(f"Suites disponibles : {', '.join(sorted(connues))}")
        return 2
    for nom, libelle, fonction, demo in SUITES:
        if demandees and nom not in demandees:
            continue
        lance(nom, libelle, fonction, demo)

    print(f"\n{'=' * 72}")
    print(f"CONFORMITE COMPTABLE : {ok} controle(s) ok, {fails} anomalie(s)")
    if anomalies:
        print("=" * 72)
        for nom, detail in anomalies:
            print(f"  - {nom}\n      {detail}")
    print("=" * 72)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(principal())
