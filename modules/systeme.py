"""Système : première installation, authentification, dossiers (sociétés),
exercices, utilisateurs et tableau de bord.
"""

from __future__ import annotations

import json
import platform
import sys

from noyau import base as db
from noyau import util
from noyau.config import config, APPLICATION, VERSION
from noyau.serveur import (
    ErreurApplicative, route, hache_mot_de_passe, verifie_mot_de_passe,
    cree_session, detruit_session, reponse_cookie, reponse_deconnexion,
)

# ---------------------------------------------------------------------------
# État de l'installation
# ---------------------------------------------------------------------------


@route("GET", "/api/etat", public=True)
def api_etat(ctx):
    nb_utilisateurs = db.valeur("SELECT COUNT(*) FROM utilisateurs", (), 0)
    utilisateur = None
    if nb_utilisateurs:
        from noyau.serveur import utilisateur_de_session
        utilisateur = utilisateur_de_session(ctx.handler._jeton())
    reponse = {
        "application": APPLICATION,
        "version": VERSION,
        "installe": bool(nb_utilisateurs),
        "connecte": bool(utilisateur),
        "dossier_donnees": str(config.dossier_donnees),
    }
    if utilisateur:
        reponse["utilisateur"] = {
            "id": utilisateur["id"],
            "identifiant": utilisateur["identifiant"],
            "nom_complet": utilisateur["nom_complet"],
            "role": utilisateur["role"],
        }
        reponse["societes"] = db.lignes(
            "SELECT id, code, raison_sociale, activite, actif FROM societes "
            "WHERE actif = 1 ORDER BY raison_sociale"
        )
    return reponse


@route("GET", "/api/diagnostic")
def api_diagnostic(ctx):
    """Ce qu'il faut savoir pour dépanner à distance, en une seule page."""
    ctx.exige_role("admin", "comptable")
    lignes_journal = []
    fichier = config.journal_incidents
    if fichier.exists():
        try:
            lignes_journal = fichier.read_text(
                encoding="utf-8", errors="replace").splitlines()[-200:]
        except OSError as err:
            lignes_journal = [f"Journal illisible : {err}"]
    return {
        "application": APPLICATION,
        "version": VERSION,
        "python": sys.version.split()[0],
        "systeme": f"{platform.system()} {platform.release()}",
        "dossier_donnees": str(config.dossier_donnees),
        "base_de_donnees": str(config.base_de_donnees),
        "taille_base": (config.base_de_donnees.stat().st_size
                        if config.base_de_donnees.exists() else 0),
        "adresse": ctx.handler.headers.get("Host", ""),
        "journal": lignes_journal,
        "fichier_journal": str(fichier),
    }


@route("POST", "/api/installation", public=True)
def api_installation(ctx):
    """Première installation : crée l'administrateur et le premier dossier."""
    if db.valeur("SELECT COUNT(*) FROM utilisateurs", (), 0):
        raise ErreurApplicative("L'application est déjà installée.", 409)

    identifiant = str(ctx.champ_requis("identifiant")).strip().lower()
    mot_de_passe = str(ctx.champ_requis("mot_de_passe"))
    if len(mot_de_passe) < 6:
        raise ErreurApplicative("Le mot de passe doit comporter au moins 6 caractères.")

    with db.transaction():
        utilisateur_id = db.insere("utilisateurs", {
            "identifiant": identifiant,
            "nom_complet": ctx.champ("nom_complet", "Administrateur"),
            "mot_de_passe": hache_mot_de_passe(mot_de_passe),
            "role": "admin",
            "actif": 1,
            "cree_le": util.maintenant(),
        })
        societe_id = _cree_societe(ctx, utilisateur_id)
    jeton = cree_session(utilisateur_id)
    return reponse_cookie({"ok": True, "societe_id": societe_id}, jeton)


@route("POST", "/api/connexion", public=True)
def api_connexion(ctx):
    identifiant = str(ctx.champ_requis("identifiant")).strip().lower()
    mot_de_passe = str(ctx.champ_requis("mot_de_passe"))
    utilisateur = db.ligne(
        "SELECT * FROM utilisateurs WHERE lower(identifiant) = ? AND actif = 1",
        (identifiant,),
    )
    if not utilisateur or not verifie_mot_de_passe(mot_de_passe, utilisateur["mot_de_passe"]):
        db.trace("connexion_refusee", "utilisateur", None, identifiant)
        raise ErreurApplicative("Identifiant ou mot de passe incorrect.", 401)
    jeton = cree_session(utilisateur["id"])
    db.trace("connexion", "utilisateur", utilisateur["id"], None, identifiant)
    return reponse_cookie({
        "ok": True,
        "utilisateur": {
            "id": utilisateur["id"], "identifiant": utilisateur["identifiant"],
            "nom_complet": utilisateur["nom_complet"], "role": utilisateur["role"],
        },
    }, jeton)


@route("POST", "/api/deconnexion")
def api_deconnexion(ctx):
    detruit_session(ctx.handler._jeton())
    return reponse_deconnexion({"ok": True})


@route("POST", "/api/mot-de-passe")
def api_change_mot_de_passe(ctx):
    ancien = str(ctx.champ_requis("ancien"))
    nouveau = str(ctx.champ_requis("nouveau"))
    if len(nouveau) < 6:
        raise ErreurApplicative("Le nouveau mot de passe doit comporter au moins 6 caractères.")
    if not verifie_mot_de_passe(ancien, ctx.utilisateur["mot_de_passe"]):
        raise ErreurApplicative("Mot de passe actuel incorrect.")
    with db.transaction():
        db.modifie("utilisateurs", ctx.utilisateur["id"],
                   {"mot_de_passe": hache_mot_de_passe(nouveau)})
        db.trace("changement_mot_de_passe", "utilisateur", ctx.utilisateur["id"],
                 None, ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------

@route("GET", "/api/utilisateurs")
def api_utilisateurs(ctx):
    ctx.exige_role("admin")
    return {"utilisateurs": db.lignes(
        "SELECT id, identifiant, nom_complet, role, actif, derniere_visite, cree_le "
        "FROM utilisateurs ORDER BY identifiant"
    )}


@route("POST", "/api/utilisateurs")
def api_cree_utilisateur(ctx):
    ctx.exige_role("admin")
    mot_de_passe = str(ctx.champ_requis("mot_de_passe"))
    if len(mot_de_passe) < 6:
        raise ErreurApplicative("Le mot de passe doit comporter au moins 6 caractères.")
    identifiant = str(ctx.champ_requis("identifiant")).strip().lower()
    if db.ligne("SELECT id FROM utilisateurs WHERE lower(identifiant) = ?", (identifiant,)):
        raise ErreurApplicative("Cet identifiant est déjà utilisé.")
    with db.transaction():
        nouvel_id = db.insere("utilisateurs", {
            "identifiant": identifiant,
            "nom_complet": ctx.champ_requis("nom_complet"),
            "mot_de_passe": hache_mot_de_passe(mot_de_passe),
            "role": ctx.champ("role", "comptable"),
            "actif": 1,
            "cree_le": util.maintenant(),
        })
    return {"id": nouvel_id}


@route("PUT", "/api/utilisateurs/<id>")
def api_modifie_utilisateur(ctx):
    ctx.exige_role("admin")
    identifiant = int(ctx.params["id"])
    donnees = {
        "nom_complet": ctx.champ_requis("nom_complet"),
        "role": ctx.champ("role", "comptable"),
        "actif": ctx.booleen("actif", True),
    }
    if ctx.champ("mot_de_passe"):
        if len(str(ctx.champ("mot_de_passe"))) < 6:
            raise ErreurApplicative("Le mot de passe doit comporter au moins 6 caractères.")
        donnees["mot_de_passe"] = hache_mot_de_passe(str(ctx.champ("mot_de_passe")))
    with db.transaction():
        db.modifie("utilisateurs", identifiant, donnees)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sociétés (dossiers comptables)
# ---------------------------------------------------------------------------

def _cree_societe(ctx, utilisateur_id=None) -> int:
    """Crée un dossier avec son plan comptable, ses journaux et son exercice."""
    code = str(ctx.champ("code") or util.code_depuis(ctx.champ_requis("raison_sociale"), 8))
    if db.ligne("SELECT id FROM societes WHERE code = ?", (code,)):
        raise ErreurApplicative(f"Le code dossier « {code} » existe déjà.")

    activite = ctx.champ("activite", "mixte")
    if activite not in ("agence", "promotion", "mixte"):
        raise ErreurApplicative("Activité invalide : agence, promotion ou mixte.")

    nif = util.nettoie(ctx.champ("nif"))
    valide, message = util.valide_nif(nif)
    if not valide:
        raise ErreurApplicative(message)

    taux_defaut = {"agence": 2600, "promotion": 2300, "mixte": 2600}[activite]
    societe_id = db.insere("societes", {
        "code": code,
        "raison_sociale": ctx.champ_requis("raison_sociale"),
        "forme_juridique": ctx.champ("forme_juridique", "SARL"),
        "activite": activite,
        "adresse": ctx.champ("adresse"),
        "commune": ctx.champ("commune"),
        "wilaya": ctx.champ("wilaya"),
        "telephone": ctx.champ("telephone"),
        "email": ctx.champ("email"),
        "nif": nif,
        "nis": util.nettoie(ctx.champ("nis")),
        "rc": util.nettoie(ctx.champ("rc")),
        "article_imposition": util.nettoie(ctx.champ("article_imposition")),
        "capital_cts": ctx.montant("capital"),
        "regime_tva": ctx.champ("regime_tva", "reel"),
        "assujetti_tva": ctx.booleen("assujetti_tva", True),
        "taux_ibs": ctx.taux("taux_ibs", taux_defaut),
        "agrement_promoteur": util.nettoie(ctx.champ("agrement_promoteur")),
        "num_fgcmpi": util.nettoie(ctx.champ("num_fgcmpi")),
        "banque_nom": util.nettoie(ctx.champ("banque_nom")),
        "banque_rib": util.nettoie(ctx.champ("banque_rib")),
        "actif": 1,
        "cree_le": util.maintenant(),
    })

    installe_plan_comptable(societe_id, activite)

    annee = int(ctx.champ("annee_exercice") or util.aujourdhui()[:4])
    db.insere("exercices", {
        "societe_id": societe_id,
        "libelle": str(annee),
        "date_debut": f"{annee}-01-01",
        "date_fin": f"{annee}-12-31",
        "cloture": 0,
    })

    db.insere("comptes_tresorerie", {
        "societe_id": societe_id, "code": "CAISSE", "libelle": "Caisse principale",
        "type": "caisse", "compte": "531", "devise": "DZD", "actif": 1,
    })
    if ctx.champ("banque_nom"):
        db.insere("comptes_tresorerie", {
            "societe_id": societe_id, "code": "BANQUE",
            "libelle": ctx.champ("banque_nom"), "type": "banque", "compte": "5121",
            "banque": ctx.champ("banque_nom"), "rib": ctx.champ("banque_rib"),
            "devise": "DZD", "actif": 1,
        })

    db.trace("creation", "societe", societe_id, code)
    return societe_id


def installe_plan_comptable(societe_id: int, activite: str = "mixte") -> int:
    """Charge la nomenclature SCF de référence dans le dossier."""
    fichier = config.dossier_reference / "plan_comptable_scf.json"
    donnees = json.loads(fichier.read_text(encoding="utf-8"))

    nombre = 0
    for c in donnees["comptes"]:
        numero = c["numero"]
        if db.ligne("SELECT id FROM comptes WHERE societe_id = ? AND numero = ?",
                    (societe_id, numero)):
            continue
        db.insere("comptes", {
            "societe_id": societe_id,
            "numero": numero,
            "intitule": c["intitule"],
            "classe": int(numero[0]),
            "nature": c.get("nature", "mixte"),
            "rubrique": c.get("rubrique"),
            "collectif": c.get("collectif"),
            "lettrable": c.get("lettrable", 0),
            "role_tva": c.get("role_tva"),
            "actif": 1,
        })
        nombre += 1

    for j in donnees["journaux"]:
        if db.ligne("SELECT id FROM journaux WHERE societe_id = ? AND code = ?",
                    (societe_id, j["code"])):
            continue
        db.insere("journaux", {
            "societe_id": societe_id, "code": j["code"], "libelle": j["libelle"],
            "type": j["type"], "compte_contrepartie": j.get("compte_contrepartie"),
            "actif": 1,
        })

    for m in donnees.get("modeles_echeancier", []):
        if db.ligne("SELECT id FROM modeles_echeancier WHERE societe_id = ? AND code = ?",
                    (societe_id, m["code"])):
            continue
        db.insere("modeles_echeancier", {
            "societe_id": societe_id, "code": m["code"], "libelle": m["libelle"],
            "lignes": json.dumps(m["lignes"], ensure_ascii=False),
        })

    return nombre


@route("GET", "/api/societes")
def api_societes(ctx):
    return {"societes": db.lignes("SELECT * FROM societes ORDER BY raison_sociale")}


@route("GET", "/api/societes/<id>")
def api_societe(ctx):
    identifiant = int(ctx.params["id"])
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (identifiant,))
    if not soc:
        raise ErreurApplicative("Dossier introuvable.", 404)
    soc["exercices"] = db.lignes(
        "SELECT * FROM exercices WHERE societe_id = ? ORDER BY date_debut DESC",
        (identifiant,)
    )
    soc["tresorerie"] = db.lignes(
        "SELECT * FROM comptes_tresorerie WHERE societe_id = ? ORDER BY code",
        (identifiant,)
    )
    return soc


@route("POST", "/api/societes")
def api_cree_societe(ctx):
    ctx.exige_role("admin", "comptable")
    with db.transaction():
        societe_id = _cree_societe(ctx)
    return {"id": societe_id}


@route("PUT", "/api/societes/<id>")
def api_modifie_societe(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    nif = util.nettoie(ctx.champ("nif"))
    valide, message = util.valide_nif(nif)
    if not valide:
        raise ErreurApplicative(message)
    with db.transaction():
        db.modifie("societes", identifiant, {
            "raison_sociale": ctx.champ_requis("raison_sociale"),
            "forme_juridique": ctx.champ("forme_juridique"),
            "activite": ctx.champ("activite", "mixte"),
            "adresse": ctx.champ("adresse"),
            "commune": ctx.champ("commune"),
            "wilaya": ctx.champ("wilaya"),
            "telephone": ctx.champ("telephone"),
            "email": ctx.champ("email"),
            "nif": nif,
            "nis": util.nettoie(ctx.champ("nis")),
            "rc": util.nettoie(ctx.champ("rc")),
            "article_imposition": util.nettoie(ctx.champ("article_imposition")),
            "capital_cts": ctx.montant("capital"),
            "regime_tva": ctx.champ("regime_tva", "reel"),
            "assujetti_tva": ctx.booleen("assujetti_tva", True),
            "taux_ibs": ctx.taux("taux_ibs"),
            "agrement_promoteur": util.nettoie(ctx.champ("agrement_promoteur")),
            "num_fgcmpi": util.nettoie(ctx.champ("num_fgcmpi")),
            "banque_nom": util.nettoie(ctx.champ("banque_nom")),
            "banque_rib": util.nettoie(ctx.champ("banque_rib")),
        })
        db.trace("modification", "societe", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Exercices
# ---------------------------------------------------------------------------

@route("GET", "/api/exercices")
def api_exercices(ctx):
    return {"exercices": db.lignes(
        "SELECT * FROM exercices WHERE societe_id = ? ORDER BY date_debut DESC",
        (ctx.arg_int("societe"),)
    )}


@route("POST", "/api/exercices")
def api_cree_exercice(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    debut = ctx.date("date_debut")
    fin = ctx.date("date_fin")
    if not debut or not fin or debut >= fin:
        raise ErreurApplicative("Dates d'exercice invalides.")
    chevauche = db.ligne(
        "SELECT libelle FROM exercices WHERE societe_id = ? "
        "AND date_debut <= ? AND date_fin >= ?",
        (societe_id, fin, debut),
    )
    if chevauche:
        raise ErreurApplicative(
            f"Cette période chevauche l'exercice existant « {chevauche['libelle']} »."
        )
    with db.transaction():
        identifiant = db.insere("exercices", {
            "societe_id": societe_id,
            "libelle": ctx.champ("libelle") or debut[:4],
            "date_debut": debut, "date_fin": fin, "cloture": 0,
        })
        db.trace("creation", "exercice", identifiant, None, ctx.nom_utilisateur)
    return {"id": identifiant}


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------

@route("GET", "/api/tableau-de-bord")
def api_tableau_de_bord(ctx):
    from modules import comptabilite as compta

    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    exercice_id = ctx.arg_int("exercice")
    ex = compta.exercice(exercice_id) if exercice_id else db.ligne(
        "SELECT * FROM exercices WHERE societe_id = ? AND cloture = 0 "
        "ORDER BY date_debut DESC LIMIT 1", (societe_id,)
    )
    if not ex:
        ex = db.ligne("SELECT * FROM exercices WHERE societe_id = ? "
                      "ORDER BY date_debut DESC LIMIT 1", (societe_id,))
    if not ex:
        raise ErreurApplicative("Aucun exercice n'est défini pour ce dossier.")

    debut, fin = ex["date_debut"], ex["date_fin"]
    perimetre = ctx.perimetre()

    def solde(prefixe):
        return compta.solde_compte(societe_id, prefixe, debut, fin, perimetre=perimetre)

    produits = solde("7")
    charges = solde("6")
    chiffre_affaires = solde("70")
    tresorerie_banque = solde("512")
    tresorerie_ccp = solde("515")
    caisse = solde("53")
    clients = solde("411")
    fournisseurs = solde("40")
    tva_collectee = solde("4457")
    tva_deductible = solde("4456")
    avances_vsp = solde("419")
    mandants = solde("4671")

    tableau = {
        "societe": {"id": soc["id"], "raison_sociale": soc["raison_sociale"],
                    "activite": soc["activite"], "code": soc["code"]},
        "exercice": ex,
        "perimetre": perimetre or "tous",
        "libelle_perimetre": compta.LIBELLES_VUE.get(perimetre or "tous", ""),
        "indicateurs": {
            "chiffre_affaires": chiffre_affaires["credit"] - chiffre_affaires["debit"],
            "produits": produits["credit"] - produits["debit"],
            "charges": charges["debit"] - charges["credit"],
            "resultat": (produits["credit"] - produits["debit"])
                        - (charges["debit"] - charges["credit"]),
            "tresorerie": (tresorerie_banque["solde"] + tresorerie_ccp["solde"]
                           + caisse["solde"]),
            "banque": tresorerie_banque["solde"] + tresorerie_ccp["solde"],
            "caisse": caisse["solde"],
            "creances_clients": clients["solde"],
            "dettes_fournisseurs": -fournisseurs["solde"],
            "tva_collectee": -tva_collectee["solde"],
            "tva_deductible": tva_deductible["solde"],
            "tva_solde": -tva_collectee["solde"] - tva_deductible["solde"],
            "avances_clients_vsp": -avances_vsp["solde"],
            "du_aux_proprietaires": -mandants["solde"],
        },
    }

    # Évolution mensuelle du chiffre d'affaires et des charges
    fragment, params_perimetre = compta.clause_perimetre(perimetre)
    tableau["evolution"] = db.lignes(
        "SELECT substr(e.date,1,7) AS periode, "
        "  COALESCE(SUM(CASE WHEN l.compte LIKE '7%' THEN l.credit - l.debit END),0) AS produits, "
        "  COALESCE(SUM(CASE WHEN l.compte LIKE '6%' THEN l.debit - l.credit END),0) AS charges "
        "FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id "
        "WHERE e.societe_id = ? AND e.date BETWEEN ? AND ?" + fragment + " "
        "GROUP BY periode ORDER BY periode",
        [societe_id, debut, fin] + params_perimetre,
    )

    # Poids du hors déclaration, affiché sans détour
    hors = compta.solde_compte(societe_id, "7", debut, fin,
                               perimetre="hors_declaration")
    produits_hors = hors["credit"] - hors["debit"]
    produits_declares = compta.solde_compte(
        societe_id, "7", debut, fin, perimetre="declare")
    produits_declares = produits_declares["credit"] - produits_declares["debit"]
    tableau["repartition_perimetres"] = {
        "declare": produits_declares,
        "hors_declaration": produits_hors,
        "part_hors": util.part_proportionnelle(
            util.BASE_TAUX, produits_hors, produits_declares + produits_hors)
        if (produits_declares + produits_hors) else 0,
    }

    # Alertes du comptable
    alertes = []
    aujourdhui = util.aujourdhui()
    periode_courante = util.periode_de(aujourdhui)
    periode_g50 = util.mois_precedent(periode_courante)
    g50 = db.ligne(
        "SELECT * FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
        (societe_id, periode_g50),
    )
    if not g50 or g50["statut"] not in ("deposee", "payee"):
        jour_limite = db.parametre_fiscal_int(int(aujourdhui[:4]), "g50_jour_limite", 20)
        limite = util.jour_du_mois(periode_courante, jour_limite)
        alertes.append({
            "type": "g50",
            "gravite": "urgent" if aujourdhui > limite else "important",
            "message": f"Déclaration G50 de {util.libelle_periode(periode_g50)} "
                       f"{'en retard' if aujourdhui > limite else 'à déposer'} "
                       f"(échéance : {util.date_fr(limite)}).",
            "lien": f"#/fiscalite/g50?periode={periode_g50}",
        })

    impayes = db.valeur(
        "SELECT COUNT(*) FROM quittances WHERE societe_id = ? AND statut IN "
        "('a_encaisser','impayee') AND date_echeance < ?", (societe_id, aujourdhui), 0
    )
    if impayes:
        alertes.append({
            "type": "loyers", "gravite": "important",
            "message": f"{impayes} quittance(s) de loyer en retard d'encaissement.",
            "lien": "#/agence/quittances?statut=impayee",
        })

    echeances_vsp = db.valeur(
        "SELECT COUNT(*) FROM echeances_vsp ev JOIN contrats_vsp c ON c.id = ev.contrat_id "
        "WHERE c.societe_id = ? AND ev.statut IN ('exigible','a_venir','partielle') "
        "AND ev.date_prevue IS NOT NULL AND ev.date_prevue < ?",
        (societe_id, aujourdhui), 0
    )
    if echeances_vsp:
        alertes.append({
            "type": "vsp", "gravite": "important",
            "message": f"{echeances_vsp} échéance(s) VSP dépassée(s) non réglée(s).",
            "lien": "#/promotion/echeances",
        })

    if caisse["solde"] < 0:
        alertes.append({
            "type": "caisse", "gravite": "urgent",
            "message": "La caisse est créditrice : une sortie a été saisie sans "
                       "provision suffisante.",
            "lien": "#/tresorerie",
        })

    brouillons = db.valeur(
        "SELECT COUNT(*) FROM ecritures WHERE societe_id = ? AND exercice_id = ? "
        "AND validee = 0", (societe_id, ex["id"]), 0
    )
    if brouillons:
        alertes.append({
            "type": "brouillon", "gravite": "info",
            "message": f"{brouillons} écriture(s) en brouillon à valider.",
            "lien": "#/comptabilite/ecritures",
        })

    tableau["alertes"] = alertes
    tableau["obligations"] = db.lignes(
        "SELECT * FROM obligations WHERE societe_id = ? AND statut = 'a_faire' "
        "ORDER BY date_limite LIMIT 10", (societe_id,)
    )
    tableau["dernieres_ecritures"] = db.lignes(
        "SELECT e.id, e.date, e.numero, e.libelle, j.code AS journal, "
        "  (SELECT COALESCE(SUM(debit),0) FROM lignes WHERE ecriture_id = e.id) AS montant "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "WHERE e.societe_id = ? ORDER BY e.id DESC LIMIT 8", (societe_id,)
    )

    if soc["activite"] in ("promotion", "mixte"):
        tableau["promotion"] = {
            "programmes": db.valeur(
                "SELECT COUNT(*) FROM programmes WHERE societe_id = ? "
                "AND statut NOT IN ('cloture')", (societe_id,), 0),
            "lots_vendus": db.valeur(
                "SELECT COUNT(*) FROM lots l JOIN programmes p ON p.id = l.programme_id "
                "WHERE p.societe_id = ? AND l.statut IN ('vendu','livre')", (societe_id,), 0),
            "lots_disponibles": db.valeur(
                "SELECT COUNT(*) FROM lots l JOIN programmes p ON p.id = l.programme_id "
                "WHERE p.societe_id = ? AND l.statut = 'disponible'", (societe_id,), 0),
            "encaisse": db.valeur(
                "SELECT COALESCE(SUM(montant_encaisse),0) FROM contrats_vsp "
                "WHERE societe_id = ?", (societe_id,), 0),
            "reste_a_encaisser": db.valeur(
                "SELECT COALESCE(SUM(prix_total - montant_encaisse),0) FROM contrats_vsp "
                "WHERE societe_id = ? AND statut = 'en_cours'", (societe_id,), 0),
        }

    if soc["activite"] in ("agence", "mixte"):
        tableau["agence"] = {
            "mandats_actifs": db.valeur(
                "SELECT COUNT(*) FROM mandats WHERE societe_id = ? AND statut = 'actif'",
                (societe_id,), 0),
            "baux_actifs": db.valeur(
                "SELECT COUNT(*) FROM baux WHERE societe_id = ? AND statut = 'actif'",
                (societe_id,), 0),
            "loyers_du_mois": db.valeur(
                "SELECT COALESCE(SUM(total),0) FROM quittances WHERE societe_id = ? "
                "AND periode = ?", (societe_id, periode_courante), 0),
            "commissions_exercice": (
                compta.solde_compte(societe_id, "706", debut, fin)["credit"]
                - compta.solde_compte(societe_id, "706", debut, fin)["debit"]),
            "biens_portefeuille": db.valeur(
                "SELECT COUNT(*) FROM biens WHERE societe_id = ? AND statut = 'disponible'",
                (societe_id,), 0),
        }

    return tableau


@route("GET", "/api/audit")
def api_audit(ctx):
    ctx.exige_role("admin", "comptable")
    limite = min(ctx.arg_int("limite", 200) or 200, 1000)
    return {"evenements": db.lignes(
        "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limite,)
    )}
