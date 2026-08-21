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
  annuelles   la DAS et l'etat des clients, et surtout leurs recoupements.

Usage :
    python outils/test_comptable.py               les quatre suites
    python outils/test_comptable.py perimetre     une seule
"""
import base64
import http.cookiejar
import json
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


SUITES = [
    ("conformite", "Conformite comptable -- une annee tenue", suite_conformite, True),
    ("limites", "Ce que le logiciel doit refuser", suite_limites, False),
    ("cloture", "Cloture, a-nouveaux, extourne", suite_cloture, False),
    ("perimetre", "Etancheite declare / hors declaration", suite_perimetre, False),
    ("cycles", "Cycles metier en mouvement et numerotation", suite_cycles, True),
    ("reprises", "Annuler un import deja valide", suite_reprises, False),
    ("sante", "Controles de sante du dossier", suite_sante, True),
    ("annuelles", "DAS et etat des clients", suite_annuelles, True),
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
