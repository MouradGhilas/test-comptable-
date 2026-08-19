"""Cœur comptable : plan de comptes SCF, journaux, écritures en partie double,
grand livre, balance, lettrage et clôture d'exercice.

Toutes les autres briques (facturation, agence, promotion, paie, fiscalité)
passent obligatoirement par `enregistre_ecriture` : il n'existe qu'un seul
chemin d'écriture dans le journal, ce qui garantit l'équilibre et la
traçabilité de l'origine de chaque mouvement.
"""

from __future__ import annotations

import json

from noyau import base as db
from noyau import util
from noyau.serveur import ErreurApplicative, route, Reponse
from noyau import tableur

# ---------------------------------------------------------------------------
# Périmètre déclaratif
# ---------------------------------------------------------------------------

#: 'declare'          : entre dans la G50, le bilan et la liasse fiscale.
#: 'hors_declaration' : comptabilisé et suivi, mais exclu des déclarations.
PERIMETRES = {
    "declare": "Déclaré",
    "hors_declaration": "Hors déclaration",
}

#: Champs d'une ligne recopiés tels quels dans chacune des deux parts d'une
#: opération saisie en totalité.
_CHAMPS_LIGNE = ("compte", "libelle", "tiers_id", "echeance", "programme_id",
                 "lot_id", "bien_id", "poste_budget")

LIBELLES_VUE = {
    "declare": "Périmètre déclaré",
    "hors_declaration": "Hors déclaration",
    "tous": "Vue réelle (déclaré + hors déclaration)",
}


def normalise_perimetre(valeur, defaut="declare") -> str:
    """Normalise une valeur de périmètre saisie ou reçue de l'interface."""
    if valeur in (None, ""):
        return defaut
    valeur = str(valeur).strip().lower()
    if valeur in ("hors", "hors_declaration", "non_declare", "noir"):
        return "hors_declaration"
    if valeur in ("declare", "declaree", "officiel"):
        return "declare"
    return defaut


def clause_perimetre(perimetre, alias: str = "e") -> tuple[str, list]:
    """Fragment SQL filtrant les écritures sur le périmètre demandé.

    `tous` (ou None) ne filtre rien : c'est la vue réelle, celle qui sert à
    piloter la trésorerie effective.
    """
    if perimetre in (None, "", "tous"):
        return "", []
    return f" AND {alias}.perimetre = ?", [normalise_perimetre(perimetre)]


# ---------------------------------------------------------------------------
# Contexte : société et exercice courants
# ---------------------------------------------------------------------------


def societe(societe_id: int) -> dict:
    soc = db.ligne("SELECT * FROM societes WHERE id = ?", (societe_id,))
    if not soc:
        raise ErreurApplicative("Dossier (société) introuvable.", 404)
    return soc


def exercice(exercice_id: int) -> dict:
    ex = db.ligne("SELECT * FROM exercices WHERE id = ?", (exercice_id,))
    if not ex:
        raise ErreurApplicative("Exercice introuvable.", 404)
    return ex


def exercice_pour_date(societe_id: int, date: str) -> dict:
    ex = db.ligne(
        "SELECT * FROM exercices WHERE societe_id = ? AND date_debut <= ? AND date_fin >= ?",
        (societe_id, date, date),
    )
    if not ex:
        raise ErreurApplicative(
            f"Aucun exercice ouvert ne couvre la date du {util.date_fr(date)}. "
            "Créez l'exercice correspondant dans Paramètres > Exercices."
        )
    return ex


def exige_exercice_ouvert(ex: dict) -> None:
    if ex["cloture"]:
        raise ErreurApplicative(
            f"L'exercice {ex['libelle']} est clôturé : aucune écriture ne peut y être "
            "ajoutée ou modifiée."
        )


def journal_par_code(societe_id: int, code: str) -> dict:
    jrn = db.ligne(
        "SELECT * FROM journaux WHERE societe_id = ? AND code = ?", (societe_id, code)
    )
    if not jrn:
        raise ErreurApplicative(f"Journal « {code} » introuvable.", 404)
    return jrn


def compte_existe(societe_id: int, numero: str) -> dict | None:
    return db.ligne(
        "SELECT * FROM comptes WHERE numero = ? AND (societe_id = ? OR societe_id IS NULL) "
        "ORDER BY societe_id DESC LIMIT 1",
        (numero, societe_id),
    )


def exige_compte(societe_id: int, numero: str) -> dict:
    cpt = compte_existe(societe_id, numero)
    if not cpt:
        raise ErreurApplicative(
            f"Le compte {numero} n'existe pas dans le plan comptable. "
            "Ajoutez-le dans Paramètres > Plan comptable."
        )
    if not cpt["actif"]:
        raise ErreurApplicative(f"Le compte {numero} est désactivé.")
    return cpt


# ---------------------------------------------------------------------------
# Écriture comptable — point d'entrée unique
# ---------------------------------------------------------------------------

def enregistre_ecriture(
    societe_id: int,
    journal_code: str,
    date: str,
    libelle: str,
    lignes: list[dict],
    *,
    piece: str | None = None,
    reference: str | None = None,
    module: str = "manuel",
    source_type: str | None = None,
    source_id: int | None = None,
    utilisateur: str | None = None,
    valider: bool = True,
    exercice_id: int | None = None,
    perimetre: str | None = None,
    operation_ref: str | None = None,
) -> int:
    """Enregistre une écriture équilibrée. À appeler dans une transaction.

    `lignes` : liste de dicts {compte, debit, credit, libelle, tiers_id,
    echeance, programme_id, lot_id, bien_id, poste_budget}. Les montants sont
    en centimes.

    `perimetre` : 'declare' (défaut du dossier) ou 'hors_declaration'.
    """
    date = util.date_iso(date)
    if not date:
        raise ErreurApplicative("Date d'écriture invalide.")
    if not libelle or not str(libelle).strip():
        raise ErreurApplicative("Le libellé de l'écriture est obligatoire.")

    ex = exercice(exercice_id) if exercice_id else exercice_pour_date(societe_id, date)
    exige_exercice_ouvert(ex)
    if not (ex["date_debut"] <= date <= ex["date_fin"]):
        raise ErreurApplicative(
            f"La date {util.date_fr(date)} est hors de l'exercice {ex['libelle']} "
            f"({util.date_fr(ex['date_debut'])} – {util.date_fr(ex['date_fin'])})."
        )

    jrn = journal_par_code(societe_id, journal_code)

    if perimetre is None:
        perimetre = db.valeur(
            "SELECT perimetre_defaut FROM societes WHERE id = ?", (societe_id,),
            "declare")
    perimetre = normalise_perimetre(perimetre)

    # -- normalisation et contrôles des lignes -----------------------------
    propres = []
    total_debit = total_credit = 0
    for index, brute in enumerate(lignes):
        compte = str(brute.get("compte") or "").strip()
        if not compte:
            raise ErreurApplicative(f"Ligne {index + 1} : compte manquant.")
        exige_compte(societe_id, compte)
        debit = int(brute.get("debit") or 0)
        credit = int(brute.get("credit") or 0)
        if debit < 0 or credit < 0:
            raise ErreurApplicative(
                f"Ligne {index + 1} : les montants négatifs sont interdits. "
                "Inversez le sens débit/crédit."
            )
        if debit and credit:
            raise ErreurApplicative(
                f"Ligne {index + 1} : une ligne ne peut pas être à la fois au débit "
                "et au crédit."
            )
        if not debit and not credit:
            continue                       # ligne vide : ignorée silencieusement
        total_debit += debit
        total_credit += credit
        propres.append({
            "ordre": len(propres),
            "compte": compte,
            "tiers_id": brute.get("tiers_id"),
            "libelle": (brute.get("libelle") or libelle)[:250],
            "debit": debit,
            "credit": credit,
            "echeance": util.date_iso(brute.get("echeance")),
            "lettrage": brute.get("lettrage"),
            "programme_id": brute.get("programme_id"),
            "lot_id": brute.get("lot_id"),
            "bien_id": brute.get("bien_id"),
            "poste_budget": brute.get("poste_budget"),
        })

    if len(propres) < 2:
        raise ErreurApplicative("Une écriture comptable comporte au moins deux lignes.")
    if total_debit != total_credit:
        ecart = total_debit - total_credit
        raise ErreurApplicative(
            "Écriture déséquilibrée : débit "
            f"{util.formate_montant(total_debit)} ≠ crédit {util.formate_montant(total_credit)} "
            f"(écart de {util.formate_montant(abs(ecart))})."
        )

    numero = db.numero_suivant(societe_id, f"ecriture_{jrn['code']}", int(date[:4]))

    ecriture_id = db.insere("ecritures", {
        "societe_id": societe_id,
        "exercice_id": ex["id"],
        "journal_id": jrn["id"],
        "date": date,
        "numero": numero,
        "piece": piece,
        "libelle": libelle[:250],
        "reference": reference,
        "module": module,
        "source_type": source_type,
        "source_id": source_id,
        "validee": 1 if valider else 0,
        "perimetre": perimetre,
        "operation_ref": operation_ref,
        "cree_le": util.maintenant(),
        "cree_par": utilisateur,
    })
    for ligne_propre in propres:
        ligne_propre["ecriture_id"] = ecriture_id
        db.insere("lignes", ligne_propre)

    db.trace("creation", "ecriture", ecriture_id,
             {"journal": jrn["code"], "montant": total_debit, "libelle": libelle,
              "perimetre": perimetre}, utilisateur)
    return ecriture_id


def enregistre_operation(societe_id: int, journal_code: str, date: str,
                         libelle: str, lignes: list[dict], **options) -> dict:
    """Enregistre une opération dont le total se décompose en deux parts.

    Chaque ligne porte quatre montants : `debit_declare`, `debit_hors`,
    `credit_declare`, `credit_hors`. Deux écritures sont produites — l'une
    déclarée, l'autre hors déclaration — reliées par une même référence
    d'opération.

    Elles ne sont volontairement pas fondues en une seule écriture : une
    écriture appartient tout entière à un périmètre, sans quoi la G50, le
    bilan et la liasse ne pourraient plus être établis sur le seul déclaré.
    Le total, lui, reste consultable d'un bloc grâce à la référence commune.
    """
    parts = {
        "declare": [{"debit": int(l.get("debit_declare") or 0),
                     "credit": int(l.get("credit_declare") or 0),
                     **{c: l.get(c) for c in _CHAMPS_LIGNE}} for l in lignes],
        "hors_declaration": [{"debit": int(l.get("debit_hors") or 0),
                              "credit": int(l.get("credit_hors") or 0),
                              **{c: l.get(c) for c in _CHAMPS_LIGNE}} for l in lignes],
    }

    for nom, jeu in parts.items():
        debit = sum(l["debit"] for l in jeu)
        credit = sum(l["credit"] for l in jeu)
        if debit != credit:
            raise ErreurApplicative(
                f"La part « {PERIMETRES[nom]} » est déséquilibrée : débit "
                f"{util.formate_montant(debit)} ≠ crédit "
                f"{util.formate_montant(credit)}. Chaque part doit s'équilibrer "
                "séparément."
            )

    if not any(l["debit"] or l["credit"] for jeu in parts.values() for l in jeu):
        raise ErreurApplicative("Aucun montant saisi.")

    reference = f"OP-{util.maintenant().replace('-', '').replace(':', '').replace(' ', '-')}"
    resultat = {"operation_ref": reference, "ecritures": [], "totaux": {}}

    for nom, jeu in parts.items():
        montant = sum(l["debit"] for l in jeu)
        resultat["totaux"][nom] = montant
        if not montant:
            continue                       # part absente : pas d'écriture vide
        identifiant = enregistre_ecriture(
            societe_id=societe_id, journal_code=journal_code, date=date,
            libelle=libelle, lignes=jeu, perimetre=nom,
            operation_ref=reference, **options)
        resultat["ecritures"].append({"id": identifiant, "perimetre": nom,
                                      "montant": montant})

    resultat["totaux"]["total"] = (resultat["totaux"].get("declare", 0)
                                   + resultat["totaux"].get("hors_declaration", 0))
    return resultat


def operation_liee(operation_ref: str) -> list[dict]:
    """Les écritures d'une même opération, déclarée puis hors déclaration."""
    if not operation_ref:
        return []
    return db.lignes(
        "SELECT e.*, j.code AS journal FROM ecritures e "
        "JOIN journaux j ON j.id = e.journal_id "
        "WHERE e.operation_ref = ? ORDER BY e.perimetre DESC", (operation_ref,))


def supprime_ecriture(ecriture_id: int, utilisateur: str | None = None,
                      forcer: bool = False) -> None:
    ecr = db.ligne("SELECT * FROM ecritures WHERE id = ?", (ecriture_id,))
    if not ecr:
        raise ErreurApplicative("Écriture introuvable.", 404)
    exige_exercice_ouvert(exercice(ecr["exercice_id"]))
    if ecr["validee"] and not forcer:
        raise ErreurApplicative(
            "Cette écriture est validée. Passez par une écriture d'extourne "
            "(contre-passation) plutôt que par une suppression, afin de conserver "
            "la piste d'audit."
        )
    db.supprime("ecritures", ecriture_id)
    db.trace("suppression", "ecriture", ecriture_id, ecr["libelle"], utilisateur)


def extourne_ecriture(ecriture_id: int, date: str | None = None,
                      utilisateur: str | None = None) -> int:
    """Contre-passation : réplique l'écriture en inversant débit et crédit."""
    ecr = db.ligne("SELECT * FROM ecritures WHERE id = ?", (ecriture_id,))
    if not ecr:
        raise ErreurApplicative("Écriture introuvable.", 404)
    lignes_origine = db.lignes(
        "SELECT * FROM lignes WHERE ecriture_id = ? ORDER BY ordre", (ecriture_id,)
    )
    jrn = db.ligne("SELECT code FROM journaux WHERE id = ?", (ecr["journal_id"],))
    inversees = [{
        "compte": l["compte"],
        "tiers_id": l["tiers_id"],
        "libelle": "Extourne — " + (l["libelle"] or ""),
        "debit": l["credit"],
        "credit": l["debit"],
        "programme_id": l["programme_id"],
        "lot_id": l["lot_id"],
        "bien_id": l["bien_id"],
        "poste_budget": l["poste_budget"],
    } for l in lignes_origine]
    return enregistre_ecriture(
        ecr["societe_id"], jrn["code"], date or util.aujourdhui(),
        f"Extourne de {ecr['numero']} — {ecr['libelle']}", inversees,
        piece=ecr["piece"], reference=ecr["numero"], module="manuel",
        source_type="extourne", source_id=ecriture_id, utilisateur=utilisateur,
        perimetre=ecr.get("perimetre"),
    )


def ecritures_de_source(source_type: str, source_id: int) -> list[dict]:
    return db.lignes(
        "SELECT * FROM ecritures WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )


def annule_ecritures_de_source(source_type: str, source_id: int,
                               utilisateur: str | None = None) -> None:
    """Supprime les écritures non validées générées par un document métier."""
    for ecr in ecritures_de_source(source_type, source_id):
        ex = db.ligne("SELECT cloture FROM exercices WHERE id = ?", (ecr["exercice_id"],))
        if ex and ex["cloture"]:
            raise ErreurApplicative(
                "L'écriture liée appartient à un exercice clôturé : utilisez une extourne."
            )
        db.supprime("ecritures", ecr["id"])
        db.trace("suppression_auto", "ecriture", ecr["id"], source_type, utilisateur)


# ---------------------------------------------------------------------------
# Soldes, grand livre, balance
# ---------------------------------------------------------------------------

def solde_compte(societe_id: int, compte: str, date_debut: str | None = None,
                 date_fin: str | None = None, prefixe: bool = True,
                 perimetre=None) -> dict:
    conditions = ["e.societe_id = ?"]
    params: list = [societe_id]
    fragment, params_perimetre = clause_perimetre(perimetre)
    if fragment:
        conditions.append(fragment.replace(" AND ", "", 1))
        params += params_perimetre
    if prefixe:
        conditions.append("l.compte LIKE ?")
        params.append(compte + "%")
    else:
        conditions.append("l.compte = ?")
        params.append(compte)
    if date_debut:
        conditions.append("e.date >= ?")
        params.append(date_debut)
    if date_fin:
        conditions.append("e.date <= ?")
        params.append(date_fin)
    res = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) AS debit, COALESCE(SUM(l.credit),0) AS credit "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        f"WHERE {' AND '.join(conditions)}",
        params,
    ) or {"debit": 0, "credit": 0}
    res["solde"] = res["debit"] - res["credit"]
    return res


def soldes_par_compte(societe_id: int, date_debut: str, date_fin: str,
                      prefixe: str | None = None, perimetre=None) -> list[dict]:
    conditions = ["e.societe_id = ?", "e.date >= ?", "e.date <= ?"]
    params: list = [societe_id, date_debut, date_fin]
    fragment, params_perimetre = clause_perimetre(perimetre)
    if fragment:
        conditions.append(fragment.replace(" AND ", "", 1))
        params += params_perimetre
    if prefixe:
        conditions.append("l.compte LIKE ?")
        params.append(prefixe + "%")
    return db.lignes(
        "SELECT l.compte, COALESCE(SUM(l.debit),0) AS debit, "
        "       COALESCE(SUM(l.credit),0) AS credit "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        f"WHERE {' AND '.join(conditions)} "
        "GROUP BY l.compte ORDER BY l.compte",
        params,
    )


def balance(societe_id: int, date_debut: str, date_fin: str,
            date_debut_exercice: str | None = None, perimetre=None) -> list[dict]:
    """Balance générale : reports à nouveau, mouvements de la période, soldes."""
    debut_ex = date_debut_exercice or date_debut
    mouvements = {r["compte"]: r for r in soldes_par_compte(
        societe_id, date_debut, date_fin, perimetre=perimetre)}
    anterieurs = {}
    if debut_ex < date_debut:
        anterieurs = {
            r["compte"]: r
            for r in soldes_par_compte(societe_id, debut_ex, _veille(date_debut),
                                       perimetre=perimetre)
        }
    numeros = sorted(set(mouvements) | set(anterieurs))
    intitules = {
        c["numero"]: c["intitule"]
        for c in db.lignes(
            "SELECT numero, intitule FROM comptes "
            "WHERE societe_id = ? OR societe_id IS NULL", (societe_id,)
        )
    }
    resultat = []
    for numero in numeros:
        ant = anterieurs.get(numero, {"debit": 0, "credit": 0})
        mvt = mouvements.get(numero, {"debit": 0, "credit": 0})
        report = ant["debit"] - ant["credit"]
        solde = report + mvt["debit"] - mvt["credit"]
        resultat.append({
            "compte": numero,
            "intitule": intitules.get(numero, ""),
            "report_debit": max(report, 0),
            "report_credit": max(-report, 0),
            "debit": mvt["debit"],
            "credit": mvt["credit"],
            "solde_debit": max(solde, 0),
            "solde_credit": max(-solde, 0),
            "solde": solde,
        })
    return resultat


def _veille(date: str) -> str:
    import datetime
    return (datetime.date.fromisoformat(date[:10]) - datetime.timedelta(days=1)).isoformat()


def grand_livre(societe_id: int, compte_debut: str | None, compte_fin: str | None,
                date_debut: str, date_fin: str, tiers_id: int | None = None,
                non_lettrees: bool = False, perimetre=None) -> list[dict]:
    conditions = ["e.societe_id = ?", "e.date >= ?", "e.date <= ?"]
    params: list = [societe_id, date_debut, date_fin]
    fragment, params_perimetre = clause_perimetre(perimetre)
    if fragment:
        conditions.append(fragment.replace(" AND ", "", 1))
        params += params_perimetre
    if compte_debut:
        conditions.append("l.compte >= ?")
        params.append(compte_debut)
    if compte_fin:
        conditions.append("l.compte <= ?")
        params.append(compte_fin + "￿")
    if tiers_id:
        conditions.append("l.tiers_id = ?")
        params.append(tiers_id)
    if non_lettrees:
        conditions.append("(l.lettrage IS NULL OR l.lettrage = '')")
    return db.lignes(
        "SELECT l.*, e.date, e.numero AS num_ecriture, e.piece, e.libelle AS libelle_ecriture, "
        "       e.perimetre, j.code AS journal, t.raison_sociale AS tiers, "
        "       c.intitule AS intitule_compte "
        "FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        "LEFT JOIN comptes c ON c.numero = l.compte AND (c.societe_id = e.societe_id OR c.societe_id IS NULL) "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY l.compte, e.date, e.id, l.ordre",
        params,
    )


# ---------------------------------------------------------------------------
# Routes API — plan comptable & journaux
# ---------------------------------------------------------------------------

@route("GET", "/api/comptes")
def api_comptes(ctx):
    societe_id = ctx.arg_int("societe")
    recherche = (ctx.arg("q") or "").strip()
    conditions = ["(societe_id = ? OR societe_id IS NULL)"]
    params: list = [societe_id]
    if recherche:
        conditions.append("(numero LIKE ? OR intitule LIKE ?)")
        params += [recherche + "%", "%" + recherche + "%"]
    if ctx.arg("classe"):
        conditions.append("classe = ?")
        params.append(int(ctx.arg("classe")))
    if ctx.arg("collectif"):
        conditions.append("collectif = ?")
        params.append(ctx.arg("collectif"))
    if ctx.arg("actifs_seuls") == "1":
        conditions.append("actif = 1")
    return {"comptes": db.lignes(
        f"SELECT * FROM comptes WHERE {' AND '.join(conditions)} ORDER BY numero "
        "LIMIT 3000", params
    )}


@route("POST", "/api/comptes")
def api_cree_compte(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    numero = str(ctx.champ_requis("numero")).strip()
    if not numero.isdigit():
        raise ErreurApplicative("Le numéro de compte ne doit contenir que des chiffres.")
    if len(numero) < 2:
        raise ErreurApplicative("Un numéro de compte comporte au moins 2 chiffres.")
    if compte_existe(societe_id, numero):
        raise ErreurApplicative(f"Le compte {numero} existe déjà.")
    with db.transaction():
        identifiant = db.insere("comptes", {
            "societe_id": societe_id,
            "numero": numero,
            "intitule": ctx.champ_requis("intitule"),
            "classe": int(numero[0]),
            "nature": ctx.champ("nature", "mixte"),
            "rubrique": ctx.champ("rubrique"),
            "collectif": util.nettoie(ctx.champ("collectif")),
            "lettrable": ctx.booleen("lettrable"),
            "role_tva": util.nettoie(ctx.champ("role_tva")),
            "actif": 1,
        })
        db.trace("creation", "compte", identifiant, numero, ctx.nom_utilisateur)
    return {"id": identifiant}


@route("PUT", "/api/comptes/<id>")
def api_modifie_compte(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("comptes", identifiant, {
            "intitule": ctx.champ_requis("intitule"),
            "nature": ctx.champ("nature", "mixte"),
            "rubrique": ctx.champ("rubrique"),
            "collectif": util.nettoie(ctx.champ("collectif")),
            "lettrable": ctx.booleen("lettrable"),
            "role_tva": util.nettoie(ctx.champ("role_tva")),
            "actif": ctx.booleen("actif", True),
        })
        db.trace("modification", "compte", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("DELETE", "/api/comptes/<id>")
def api_supprime_compte(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    cpt = db.ligne("SELECT * FROM comptes WHERE id = ?", (identifiant,))
    if not cpt:
        raise ErreurApplicative("Compte introuvable.", 404)
    utilise = db.valeur("SELECT COUNT(*) FROM lignes WHERE compte = ?", (cpt["numero"],), 0)
    if utilise:
        raise ErreurApplicative(
            f"Le compte {cpt['numero']} est utilisé par {utilise} ligne(s) d'écriture. "
            "Vous pouvez le désactiver mais pas le supprimer."
        )
    with db.transaction():
        db.supprime("comptes", identifiant)
        db.trace("suppression", "compte", identifiant, cpt["numero"], ctx.nom_utilisateur)
    return {"ok": True}


@route("GET", "/api/journaux")
def api_journaux(ctx):
    return {"journaux": db.lignes(
        "SELECT * FROM journaux WHERE societe_id = ? ORDER BY code",
        (ctx.arg_int("societe"),)
    )}


@route("POST", "/api/journaux")
def api_cree_journal(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        identifiant = db.insere("journaux", {
            "societe_id": ctx.entier("societe_id"),
            "code": str(ctx.champ_requis("code")).upper()[:6],
            "libelle": ctx.champ_requis("libelle"),
            "type": ctx.champ("type", "OD"),
            "compte_contrepartie": util.nettoie(ctx.champ("compte_contrepartie")),
            "actif": 1,
        })
    return {"id": identifiant}


# ---------------------------------------------------------------------------
# Routes API — écritures
# ---------------------------------------------------------------------------

@route("GET", "/api/ecritures")
def api_ecritures(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["e.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("exercice"):
        conditions.append("e.exercice_id = ?")
        params.append(ctx.arg_int("exercice"))
    if ctx.arg("journal"):
        conditions.append("j.code = ?")
        params.append(ctx.arg("journal"))
    if ctx.arg("du"):
        conditions.append("e.date >= ?")
        params.append(ctx.arg("du"))
    if ctx.arg("au"):
        conditions.append("e.date <= ?")
        params.append(ctx.arg("au"))
    if ctx.arg("q"):
        conditions.append("(e.libelle LIKE ? OR e.numero LIKE ? OR e.piece LIKE ? "
                          "OR e.reference LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif, motif]
    # Retrouver les écritures dont le justificatif manque est le premier
    # geste avant un contrôle : c'est un filtre, pas une recherche à l'œil.
    if ctx.arg("sans_piece") == "1":
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM pieces_jointes pj "
            "WHERE pj.entite = 'ecriture' AND pj.entite_id = e.id)")
    fragment, params_perimetre = clause_perimetre(ctx.perimetre())
    if fragment:
        conditions.append(fragment.replace(" AND ", "", 1))
        params += params_perimetre
    limite = min(ctx.arg_int("limite", 200) or 200, 2000)
    ecritures = db.lignes(
        "SELECT e.*, j.code AS journal, j.libelle AS journal_libelle, "
        "  (SELECT COALESCE(SUM(debit),0) FROM lignes WHERE ecriture_id = e.id) AS montant, "
        "  (SELECT COUNT(*) FROM pieces_jointes pj "
        "     WHERE pj.entite = 'ecriture' AND pj.entite_id = e.id) AS nb_pieces "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY e.date DESC, e.id DESC LIMIT ?",
        params + [limite],
    )
    total = db.valeur(
        "SELECT COUNT(*) FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        f"WHERE {' AND '.join(conditions)}", params, 0
    )
    _attache_operations(ecritures)
    return {"ecritures": ecritures, "total": total}


def _attache_operations(ecritures: list[dict]) -> None:
    """Ajoute le total réel des écritures issues d'une saisie en totalité.

    L'écriture reste filtrable par périmètre ; on lui joint simplement de quoi
    rappeler à l'écran le montant de l'opération entière et sa décomposition.
    """
    references = {e["operation_ref"] for e in ecritures if e.get("operation_ref")}
    if not references:
        return
    marques = ", ".join("?" for _ in references)
    cumuls: dict[str, dict] = {}
    for rang in db.lignes(
            "SELECT e.operation_ref AS ref, e.perimetre, "
            "  COALESCE(SUM(l.debit), 0) AS montant "
            "FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id "
            f"WHERE e.operation_ref IN ({marques}) "
            "GROUP BY e.operation_ref, e.perimetre", list(references)):
        entree = cumuls.setdefault(rang["ref"], {"declare": 0, "hors_declaration": 0})
        entree[rang["perimetre"]] = rang["montant"]
    for ecriture in ecritures:
        cumul = cumuls.get(ecriture.get("operation_ref"))
        if cumul:
            ecriture["operation"] = {
                **cumul, "total": cumul["declare"] + cumul["hors_declaration"]}


@route("GET", "/api/ecritures/<id>")
def api_ecriture(ctx):
    identifiant = int(ctx.params["id"])
    ecr = db.ligne(
        "SELECT e.*, j.code AS journal FROM ecritures e "
        "JOIN journaux j ON j.id = e.journal_id WHERE e.id = ?", (identifiant,)
    )
    if not ecr:
        raise ErreurApplicative("Écriture introuvable.", 404)
    ecr["lignes"] = db.lignes(
        "SELECT l.*, t.raison_sociale AS tiers_nom, c.intitule AS compte_intitule "
        "FROM lignes l "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        "LEFT JOIN comptes c ON c.numero = l.compte AND (c.societe_id IS NULL OR c.societe_id = ?) "
        "WHERE l.ecriture_id = ? ORDER BY l.ordre", (ecr["societe_id"], identifiant)
    )
    ecr["pieces"] = db.lignes(
        "SELECT * FROM pieces_jointes WHERE entite = 'ecriture' AND entite_id = ?",
        (identifiant,)
    )
    return ecr


def _ligne_commune(l: dict) -> dict:
    return {
        "compte": l.get("compte"),
        "tiers_id": l.get("tiers_id") or None,
        "libelle": l.get("libelle"),
        "echeance": l.get("echeance"),
        "programme_id": l.get("programme_id") or None,
        "lot_id": l.get("lot_id") or None,
        "bien_id": l.get("bien_id") or None,
        "poste_budget": l.get("poste_budget") or None,
    }


@route("POST", "/api/ecritures")
def api_cree_ecriture(ctx):
    ctx.interdit_lecture_seule()
    lignes_saisies = ctx.champ("lignes") or []
    if not isinstance(lignes_saisies, list):
        raise ErreurApplicative("Format des lignes invalide.")

    commun = dict(
        piece=util.nettoie(ctx.champ("piece")),
        reference=util.nettoie(ctx.champ("reference")),
        module="manuel",
        utilisateur=ctx.nom_utilisateur,
        valider=bool(ctx.booleen("valider", True)),
    )

    # Saisie en totalité : chaque ligne porte une part déclarée et une part
    # hors déclaration, enregistrées en une seule fois.
    if ctx.champ("perimetre") == "totalite":
        lignes_pretes = [{
            **_ligne_commune(l),
            "debit_declare": util.centimes(l.get("debit_declare")),
            "credit_declare": util.centimes(l.get("credit_declare")),
            "debit_hors": util.centimes(l.get("debit_hors")),
            "credit_hors": util.centimes(l.get("credit_hors")),
        } for l in lignes_saisies]
        with db.transaction():
            return enregistre_operation(
                ctx.entier("societe_id"),
                ctx.champ_requis("journal"),
                ctx.champ_requis("date"),
                ctx.champ_requis("libelle"),
                lignes_pretes,
                **commun,
            )

    lignes_pretes = [{
        **_ligne_commune(l),
        "debit": util.centimes(l.get("debit")),
        "credit": util.centimes(l.get("credit")),
    } for l in lignes_saisies]

    with db.transaction():
        identifiant = enregistre_ecriture(
            ctx.entier("societe_id"),
            ctx.champ_requis("journal"),
            ctx.champ_requis("date"),
            ctx.champ_requis("libelle"),
            lignes_pretes,
            perimetre=ctx.champ("perimetre"),
            **commun,
        )
    return {"id": identifiant}


@route("PUT", "/api/ecritures/<id>")
def api_modifie_ecriture(ctx):
    """Modification = suppression + recréation, uniquement si non validée."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    ancienne = db.ligne("SELECT * FROM ecritures WHERE id = ?", (identifiant,))
    if not ancienne:
        raise ErreurApplicative("Écriture introuvable.", 404)
    if ancienne["validee"]:
        raise ErreurApplicative(
            "Écriture validée : elle n'est plus modifiable. Utilisez l'extourne."
        )
    exige_exercice_ouvert(exercice(ancienne["exercice_id"]))

    lignes_pretes = [{
        "compte": l.get("compte"),
        "tiers_id": l.get("tiers_id") or None,
        "libelle": l.get("libelle"),
        "debit": util.centimes(l.get("debit")),
        "credit": util.centimes(l.get("credit")),
        "echeance": l.get("echeance"),
        "programme_id": l.get("programme_id") or None,
        "lot_id": l.get("lot_id") or None,
        "bien_id": l.get("bien_id") or None,
    } for l in (ctx.champ("lignes") or [])]

    with db.transaction():
        db.supprime("ecritures", identifiant)
        nouvel_id = enregistre_ecriture(
            ancienne["societe_id"],
            ctx.champ_requis("journal"),
            ctx.champ_requis("date"),
            ctx.champ_requis("libelle"),
            lignes_pretes,
            piece=util.nettoie(ctx.champ("piece")),
            reference=util.nettoie(ctx.champ("reference")),
            module="manuel",
            utilisateur=ctx.nom_utilisateur,
            valider=bool(ctx.booleen("valider", False)),
            perimetre=ctx.champ("perimetre"),
        )
        db.trace("modification", "ecriture", nouvel_id,
                 f"remplace #{identifiant}", ctx.nom_utilisateur)
    return {"id": nouvel_id}


@route("POST", "/api/ecritures/<id>/valider")
def api_valide_ecriture(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.execute("UPDATE ecritures SET validee = 1, modifie_le = ? WHERE id = ?",
                   (util.maintenant(), identifiant))
        db.trace("validation", "ecriture", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("POST", "/api/ecritures/<id>/extourner")
def api_extourne(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        nouvel_id = extourne_ecriture(
            int(ctx.params["id"]), ctx.champ("date"), ctx.nom_utilisateur
        )
    return {"id": nouvel_id}


@route("DELETE", "/api/ecritures/<id>")
def api_supprime_ecriture(ctx):
    ctx.exige_role("admin", "comptable")
    with db.transaction():
        supprime_ecriture(int(ctx.params["id"]), ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes API — grand livre, balance, journal
# ---------------------------------------------------------------------------

@route("GET", "/api/grand-livre")
def api_grand_livre(ctx):
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    lignes_gl = grand_livre(
        societe_id, ctx.arg("compte_debut"), ctx.arg("compte_fin"),
        ctx.arg("du") or ex["date_debut"], ctx.arg("au") or ex["date_fin"],
        ctx.arg_int("tiers"), ctx.arg("non_lettrees") == "1",
        perimetre=ctx.perimetre(),
    )
    # Regroupement par compte avec solde progressif
    groupes: list[dict] = []
    courant = None
    for l in lignes_gl:
        if courant is None or courant["compte"] != l["compte"]:
            courant = {"compte": l["compte"], "intitule": l["intitule_compte"],
                       "lignes": [], "total_debit": 0, "total_credit": 0}
            groupes.append(courant)
        courant["total_debit"] += l["debit"]
        courant["total_credit"] += l["credit"]
        l["solde_progressif"] = courant["total_debit"] - courant["total_credit"]
        courant["lignes"].append(l)
    for g in groupes:
        g["solde"] = g["total_debit"] - g["total_credit"]
    return {"groupes": groupes}


@route("GET", "/api/balance")
def api_balance(ctx):
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    perimetre = ctx.perimetre()
    donnees = balance(societe_id, du, au, ex["date_debut"], perimetre=perimetre)
    niveau = ctx.arg_int("niveau")
    if niveau:
        agrege: dict[str, dict] = {}
        for l in donnees:
            cle = l["compte"][:niveau]
            entree = agrege.setdefault(cle, {
                "compte": cle, "intitule": "", "report_debit": 0, "report_credit": 0,
                "debit": 0, "credit": 0, "solde_debit": 0, "solde_credit": 0, "solde": 0,
            })
            for champ in ("report_debit", "report_credit", "debit", "credit"):
                entree[champ] += l[champ]
        for cle, entree in agrege.items():
            solde = (entree["report_debit"] - entree["report_credit"]
                     + entree["debit"] - entree["credit"])
            entree["solde"] = solde
            entree["solde_debit"] = max(solde, 0)
            entree["solde_credit"] = max(-solde, 0)
            cpt = compte_existe(societe_id, cle)
            entree["intitule"] = cpt["intitule"] if cpt else ""
        donnees = [agrege[c] for c in sorted(agrege)]
    totaux = {
        "report_debit": sum(l["report_debit"] for l in donnees),
        "report_credit": sum(l["report_credit"] for l in donnees),
        "debit": sum(l["debit"] for l in donnees),
        "credit": sum(l["credit"] for l in donnees),
        "solde_debit": sum(l["solde_debit"] for l in donnees),
        "solde_credit": sum(l["solde_credit"] for l in donnees),
    }
    return {"lignes": donnees, "totaux": totaux, "du": du, "au": au,
            "perimetre": perimetre or "tous",
            "libelle_perimetre": LIBELLES_VUE.get(perimetre or "tous", ""),
            "equilibree": totaux["debit"] == totaux["credit"]}


@route("GET", "/api/journal-centralisateur")
def api_journal_centralisateur(ctx):
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    return {"lignes": db.lignes(
        "SELECT j.code, j.libelle, substr(e.date,1,7) AS periode, "
        "  COALESCE(SUM(l.debit),0) AS debit, COALESCE(SUM(l.credit),0) AS credit, "
        "  COUNT(DISTINCT e.id) AS nb_ecritures "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "JOIN lignes l ON l.ecriture_id = e.id "
        "WHERE e.societe_id = ? AND e.date >= ? AND e.date <= ? "
        "GROUP BY j.code, periode ORDER BY periode, j.code",
        (societe_id, du, au)
    )}


# ---------------------------------------------------------------------------
# Lettrage
# ---------------------------------------------------------------------------

@route("GET", "/api/lettrage")
def api_lettrage_lignes(ctx):
    """Lignes lettrables d'un compte/tiers, avec l'état de rapprochement."""
    societe_id = ctx.arg_int("societe")
    conditions = ["e.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("compte"):
        conditions.append("l.compte LIKE ?")
        params.append(ctx.arg("compte") + "%")
    if ctx.arg("tiers"):
        conditions.append("l.tiers_id = ?")
        params.append(ctx.arg_int("tiers"))
    if ctx.arg("etat") == "non_lettre":
        conditions.append("(l.lettrage IS NULL OR l.lettrage = '')")
    elif ctx.arg("etat") == "lettre":
        conditions.append("l.lettrage IS NOT NULL AND l.lettrage <> ''")
    lignes_res = db.lignes(
        "SELECT l.*, e.date, e.numero AS num_ecriture, e.libelle AS libelle_ecriture, "
        "       j.code AS journal, t.raison_sociale AS tiers "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY e.date, l.id LIMIT 1000",
        params,
    )
    return {
        "lignes": lignes_res,
        "total_debit": sum(l["debit"] for l in lignes_res),
        "total_credit": sum(l["credit"] for l in lignes_res),
    }


@route("POST", "/api/lettrage")
def api_lettre(ctx):
    """Lettre un groupe de lignes : le total débit doit égaler le total crédit."""
    ctx.interdit_lecture_seule()
    identifiants = ctx.champ("lignes") or []
    if len(identifiants) < 2:
        raise ErreurApplicative("Sélectionnez au moins deux lignes à lettrer.")
    marques = ",".join("?" for _ in identifiants)
    selection = db.lignes(
        f"SELECT l.*, e.societe_id FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        f"WHERE l.id IN ({marques})", identifiants
    )
    if len(selection) != len(identifiants):
        raise ErreurApplicative("Certaines lignes sélectionnées n'existent plus.")
    total_debit = sum(l["debit"] for l in selection)
    total_credit = sum(l["credit"] for l in selection)
    tolerance = util.centimes(ctx.champ("tolerance", 0))
    if abs(total_debit - total_credit) > tolerance:
        raise ErreurApplicative(
            f"Lettrage impossible : débit {util.formate_montant(total_debit)} ≠ crédit "
            f"{util.formate_montant(total_credit)} "
            f"(écart {util.formate_montant(abs(total_debit - total_credit))})."
        )
    societe_id = selection[0]["societe_id"]
    code = ctx.champ("code") or _prochain_code_lettrage(societe_id)
    with db.transaction():
        db.execute(
            f"UPDATE lignes SET lettrage = ? WHERE id IN ({marques})",
            [code] + list(identifiants),
        )
        db.trace("lettrage", "lignes", None,
                 {"code": code, "lignes": identifiants}, ctx.nom_utilisateur)
    return {"code": code, "lignes": len(identifiants)}


@route("POST", "/api/delettrage")
def api_delettre(ctx):
    ctx.interdit_lecture_seule()
    code = ctx.champ("code")
    identifiants = ctx.champ("lignes")
    with db.transaction():
        if code:
            db.execute(
                "UPDATE lignes SET lettrage = NULL WHERE lettrage = ? AND ecriture_id IN "
                "(SELECT id FROM ecritures WHERE societe_id = ?)",
                (code, ctx.entier("societe_id")),
            )
        elif identifiants:
            marques = ",".join("?" for _ in identifiants)
            db.execute(f"UPDATE lignes SET lettrage = NULL WHERE id IN ({marques})",
                       identifiants)
        else:
            raise ErreurApplicative("Indiquez un code de lettrage ou des lignes.")
    return {"ok": True}


def _prochain_code_lettrage(societe_id: int) -> str:
    """Codes AAA, AAB… propres à la société."""
    dernier = db.valeur(
        "SELECT MAX(l.lettrage) FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.lettrage IS NOT NULL AND length(l.lettrage) = 3",
        (societe_id,),
    )
    if not dernier:
        return "AAA"
    chiffres = [ord(c) - 65 for c in dernier]
    i = len(chiffres) - 1
    while i >= 0:
        chiffres[i] += 1
        if chiffres[i] < 26:
            break
        chiffres[i] = 0
        i -= 1
    return "".join(chr(65 + c) for c in chiffres)


@route("POST", "/api/lettrage/automatique")
def api_lettrage_auto(ctx):
    """Lettrage automatique : rapproche les montants identiques débit/crédit
    d'un même tiers (facture ↔ règlement)."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    compte = ctx.champ("compte", "411")
    candidates = db.lignes(
        "SELECT l.*, e.date FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.compte LIKE ? "
        "AND (l.lettrage IS NULL OR l.lettrage = '') AND l.tiers_id IS NOT NULL "
        "ORDER BY e.date",
        (societe_id, compte + "%"),
    )
    par_tiers: dict[int, dict[int, list]] = {}
    for l in candidates:
        par_tiers.setdefault(l["tiers_id"], {"debit": [], "credit": []})
        if l["debit"]:
            par_tiers[l["tiers_id"]]["debit"].append(l)
        else:
            par_tiers[l["tiers_id"]]["credit"].append(l)

    apparies = 0
    with db.transaction():
        for groupes in par_tiers.values():
            credits_restants = list(groupes["credit"])
            for ligne_debit in groupes["debit"]:
                for i, ligne_credit in enumerate(credits_restants):
                    if ligne_credit["credit"] == ligne_debit["debit"]:
                        code = _prochain_code_lettrage(societe_id)
                        db.execute("UPDATE lignes SET lettrage = ? WHERE id IN (?,?)",
                                   (code, ligne_debit["id"], ligne_credit["id"]))
                        credits_restants.pop(i)
                        apparies += 1
                        break
    return {"apparies": apparies}


# ---------------------------------------------------------------------------
# Clôture d'exercice et à-nouveaux
# ---------------------------------------------------------------------------

@route("POST", "/api/exercices/<id>/cloturer")
def api_cloture(ctx):
    """Clôture : détermine le résultat, le vire en compte 120/129, génère les
    à-nouveaux sur l'exercice suivant, puis verrouille l'exercice."""
    ctx.exige_role("admin", "comptable")
    exercice_id = int(ctx.params["id"])
    ex = exercice(exercice_id)
    if ex["cloture"]:
        raise ErreurApplicative("Cet exercice est déjà clôturé.")
    societe_id = ex["societe_id"]

    controle = api_balance_interne(societe_id, ex)
    if controle["debit"] != controle["credit"]:
        raise ErreurApplicative(
            "La balance de l'exercice n'est pas équilibrée : clôture impossible. "
            f"Écart de {util.formate_montant(abs(controle['debit'] - controle['credit']))}."
        )

    exercice_suivant_id = ctx.entier("exercice_suivant")
    resultat = _resultat_exercice(societe_id, ex)

    with db.transaction():
        # 1. Soldes des comptes de gestion (classes 6 et 7) vers le résultat
        lignes_solde = []
        for l in soldes_par_compte(societe_id, ex["date_debut"], ex["date_fin"]):
            if l["compte"][0] not in ("6", "7"):
                continue
            solde = l["debit"] - l["credit"]
            if solde == 0:
                continue
            if solde > 0:      # compte de charge : on le crédite pour le solder
                lignes_solde.append({"compte": l["compte"], "credit": solde, "debit": 0})
            else:
                lignes_solde.append({"compte": l["compte"], "debit": -solde, "credit": 0})
        if lignes_solde:
            compte_resultat = "120" if resultat >= 0 else "129"
            if resultat >= 0:
                lignes_solde.append({"compte": compte_resultat, "credit": resultat, "debit": 0})
            else:
                lignes_solde.append({"compte": compte_resultat, "debit": -resultat, "credit": 0})
            enregistre_ecriture(
                societe_id, "OD", ex["date_fin"],
                f"Clôture de l'exercice {ex['libelle']} — détermination du résultat",
                lignes_solde, module="cloture", source_type="cloture",
                source_id=exercice_id, utilisateur=ctx.nom_utilisateur,
                exercice_id=exercice_id,
            )

        # 2. À-nouveaux sur l'exercice suivant
        nb_an = 0
        if exercice_suivant_id:
            suivant = exercice(exercice_suivant_id)
            if suivant["cloture"]:
                raise ErreurApplicative("L'exercice suivant est clôturé.")
            lignes_an = []
            for l in balance(societe_id, ex["date_debut"], ex["date_fin"], ex["date_debut"]):
                if l["compte"][0] in ("6", "7"):
                    continue
                solde = l["solde"]
                if solde == 0:
                    continue
                if solde > 0:
                    lignes_an.append({"compte": l["compte"], "debit": solde, "credit": 0})
                else:
                    lignes_an.append({"compte": l["compte"], "credit": -solde, "debit": 0})
            if lignes_an:
                enregistre_ecriture(
                    societe_id, "AN", suivant["date_debut"],
                    f"À-nouveaux de l'exercice {ex['libelle']}", lignes_an,
                    module="cloture", source_type="a_nouveaux", source_id=exercice_id,
                    utilisateur=ctx.nom_utilisateur, exercice_id=exercice_suivant_id,
                )
                nb_an = len(lignes_an)

        db.execute("UPDATE exercices SET cloture = 1, date_cloture = ? WHERE id = ?",
                   (util.maintenant(), exercice_id))
        db.trace("cloture", "exercice", exercice_id,
                 {"resultat": resultat, "a_nouveaux": nb_an}, ctx.nom_utilisateur)

    return {"resultat": resultat, "a_nouveaux": nb_an,
            "message": f"Exercice {ex['libelle']} clôturé. Résultat : "
                       f"{util.formate_montant(resultat)}."}


@route("POST", "/api/exercices/<id>/rouvrir")
def api_rouvre_exercice(ctx):
    ctx.exige_role("admin")
    exercice_id = int(ctx.params["id"])
    with db.transaction():
        db.execute("UPDATE exercices SET cloture = 0, date_cloture = NULL WHERE id = ?",
                   (exercice_id,))
        db.trace("reouverture", "exercice", exercice_id, None, ctx.nom_utilisateur)
    return {"ok": True, "message": "Exercice rouvert. Les écritures de clôture et "
                                   "d'à-nouveaux existantes n'ont pas été supprimées : "
                                   "vérifiez-les avant de re-clôturer."}


def api_balance_interne(societe_id, ex) -> dict:
    res = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) AS debit, COALESCE(SUM(l.credit),0) AS credit "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND e.date BETWEEN ? AND ?",
        (societe_id, ex["date_debut"], ex["date_fin"]),
    )
    return res or {"debit": 0, "credit": 0}


def _resultat_exercice(societe_id: int, ex: dict) -> int:
    """Produits (classe 7) - Charges (classe 6)."""
    produits = solde_compte(societe_id, "7", ex["date_debut"], ex["date_fin"])
    charges = solde_compte(societe_id, "6", ex["date_debut"], ex["date_fin"])
    return (produits["credit"] - produits["debit"]) - (charges["debit"] - charges["credit"])


@route("GET", "/api/perimetres/synthese")
def api_synthese_perimetres(ctx):
    """Compare le déclaré et le hors déclaration sur la période.

    Sert à mesurer l'écart entre la comptabilité déposée et l'activité réelle,
    et à voir depuis combien de temps il court.
    """
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]

    resultat = {"du": du, "au": au, "perimetres": {}}
    for cle in ("declare", "hors_declaration"):
        produits = solde_compte(societe_id, "7", du, au, perimetre=cle)
        charges = solde_compte(societe_id, "6", du, au, perimetre=cle)
        tresorerie = solde_compte(societe_id, "5", du, au, perimetre=cle)
        resultat["perimetres"][cle] = {
            "libelle": PERIMETRES[cle],
            "produits": produits["credit"] - produits["debit"],
            "charges": charges["debit"] - charges["credit"],
            "resultat": (produits["credit"] - produits["debit"])
                        - (charges["debit"] - charges["credit"]),
            "tresorerie": tresorerie["solde"],
            "nb_ecritures": db.valeur(
                "SELECT COUNT(*) FROM ecritures WHERE societe_id = ? "
                "AND date BETWEEN ? AND ? AND perimetre = ?",
                (societe_id, du, au, cle), 0),
        }

    hors = resultat["perimetres"]["hors_declaration"]
    total_produits = (resultat["perimetres"]["declare"]["produits"] + hors["produits"])
    resultat["part_hors_declaration"] = (
        util.part_proportionnelle(util.BASE_TAUX, hors["produits"], total_produits)
        if total_produits else 0)
    resultat["plus_ancienne"] = db.valeur(
        "SELECT MIN(date) FROM ecritures WHERE societe_id = ? AND perimetre = "
        "'hors_declaration' AND date BETWEEN ? AND ?", (societe_id, du, au))
    resultat["par_mois"] = db.lignes(
        "SELECT substr(e.date,1,7) AS periode, e.perimetre, "
        "  COALESCE(SUM(CASE WHEN l.compte LIKE '7%' THEN l.credit - l.debit END),0) AS produits "
        "FROM ecritures e JOIN lignes l ON l.ecriture_id = e.id "
        "WHERE e.societe_id = ? AND e.date BETWEEN ? AND ? "
        "GROUP BY periode, e.perimetre ORDER BY periode",
        (societe_id, du, au))
    return resultat


@route("GET", "/api/exercices/<id>/controles")
def api_controles(ctx):
    """Contrôles de cohérence avant clôture — le « check-up » du comptable."""
    exercice_id = int(ctx.params["id"])
    ex = exercice(exercice_id)
    societe_id = ex["societe_id"]
    anomalies = []

    equilibre = api_balance_interne(societe_id, ex)
    if equilibre["debit"] != equilibre["credit"]:
        anomalies.append({
            "gravite": "bloquant", "code": "balance",
            "message": "La balance générale n'est pas équilibrée.",
            "detail": util.formate_montant(equilibre["debit"] - equilibre["credit"]),
        })

    desequilibrees = db.lignes(
        "SELECT e.id, e.numero, e.date, e.libelle, "
        "  COALESCE(SUM(l.debit),0) AS d, COALESCE(SUM(l.credit),0) AS c "
        "FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id "
        "WHERE e.exercice_id = ? GROUP BY e.id HAVING d <> c", (exercice_id,)
    )
    for e in desequilibrees:
        anomalies.append({
            "gravite": "bloquant", "code": "ecriture",
            "message": f"Écriture {e['numero']} déséquilibrée ({util.date_fr(e['date'])}).",
            "detail": e["libelle"], "lien": f"#/ecritures/{e['id']}",
        })

    non_validees = db.valeur(
        "SELECT COUNT(*) FROM ecritures WHERE exercice_id = ? AND validee = 0",
        (exercice_id,), 0
    )
    if non_validees:
        anomalies.append({
            "gravite": "avertissement", "code": "brouillon",
            "message": f"{non_validees} écriture(s) encore en brouillon.",
        })

    attente = solde_compte(societe_id, "471", ex["date_debut"], ex["date_fin"])
    if attente["solde"] != 0:
        anomalies.append({
            "gravite": "avertissement", "code": "compte_attente",
            "message": "Le compte d'attente 471 n'est pas soldé.",
            "detail": util.formate_montant(attente["solde"]),
        })

    caisse = solde_compte(societe_id, "53", ex["date_debut"], ex["date_fin"])
    if caisse["solde"] < 0:
        anomalies.append({
            "gravite": "bloquant", "code": "caisse_negative",
            "message": "La caisse présente un solde créditeur (impossible physiquement).",
            "detail": util.formate_montant(caisse["solde"]),
        })

    tva_a_payer = solde_compte(societe_id, "4451", ex["date_debut"], ex["date_fin"])
    if tva_a_payer["solde"] > 0:
        anomalies.append({
            "gravite": "info", "code": "tva",
            "message": "Le compte 4451 « TVA à décaisser » est débiteur : à vérifier.",
            "detail": util.formate_montant(tva_a_payer["solde"]),
        })

    lettrables_ouverts = db.valeur(
        "SELECT COUNT(*) FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.exercice_id = ? AND (l.compte LIKE '40%' OR l.compte LIKE '41%') "
        "AND (l.lettrage IS NULL OR l.lettrage = '')", (exercice_id,), 0
    )
    if lettrables_ouverts:
        anomalies.append({
            "gravite": "info", "code": "lettrage",
            "message": f"{lettrables_ouverts} ligne(s) client/fournisseur non lettrée(s).",
        })

    return {
        "anomalies": anomalies,
        "resultat": _resultat_exercice(societe_id, ex),
        "bloquants": sum(1 for a in anomalies if a["gravite"] == "bloquant"),
    }


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

@route("GET", "/api/export/balance")
def api_export_balance(ctx):
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    soc = societe(societe_id)
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    donnees = balance(societe_id, du, au, ex["date_debut"])

    classeur = tableur.Classeur()
    f = classeur.feuille("Balance générale")
    f.titre(f"{soc['raison_sociale']} — Balance générale")
    f.ajoute(tableur.texte(f"Période du {util.date_fr(du)} au {util.date_fr(au)}"))
    f.vide()
    f.entetes("Compte", "Intitulé", "Report débit", "Report crédit",
              "Mouvement débit", "Mouvement crédit", "Solde débit", "Solde crédit")
    f.largeurs_auto(12, 45, 16, 16, 16, 16, 16, 16)
    for l in donnees:
        f.ajoute(
            tableur.texte(l["compte"]), tableur.texte(l["intitule"]),
            tableur.monnaie(l["report_debit"]), tableur.monnaie(l["report_credit"]),
            tableur.monnaie(l["debit"]), tableur.monnaie(l["credit"]),
            tableur.monnaie(l["solde_debit"]), tableur.monnaie(l["solde_credit"]),
        )
    f.ajoute(
        tableur.texte("TOTAUX", tableur.GRAS), tableur.texte(""),
        tableur.monnaie(sum(l["report_debit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["report_credit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["debit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["credit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["solde_debit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["solde_credit"] for l in donnees), total=True),
    )
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"balance_{soc['code']}_{du}_{au}.xlsx")


@route("GET", "/api/export/grand-livre")
def api_export_grand_livre(ctx):
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    soc = societe(societe_id)
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    donnees = grand_livre(societe_id, ctx.arg("compte_debut"), ctx.arg("compte_fin"),
                          du, au, ctx.arg_int("tiers"))
    classeur = tableur.Classeur()
    f = classeur.feuille("Grand livre")
    f.titre(f"{soc['raison_sociale']} — Grand livre")
    f.ajoute(tableur.texte(f"Du {util.date_fr(du)} au {util.date_fr(au)}"))
    f.vide()
    f.entetes("Compte", "Intitulé", "Date", "Journal", "N° écriture", "Pièce",
              "Libellé", "Tiers", "Débit", "Crédit", "Solde", "Lettrage")
    f.largeurs_auto(12, 32, 12, 8, 14, 14, 42, 26, 15, 15, 15, 9)
    solde = 0
    compte_courant = None
    for l in donnees:
        if compte_courant != l["compte"]:
            compte_courant, solde = l["compte"], 0
        solde += l["debit"] - l["credit"]
        f.ajoute(
            tableur.texte(l["compte"]), tableur.texte(l["intitule_compte"]),
            tableur.date_cel(l["date"]), tableur.texte(l["journal"]),
            tableur.texte(l["num_ecriture"]), tableur.texte(l["piece"]),
            tableur.texte(l["libelle"]), tableur.texte(l["tiers"]),
            tableur.monnaie(l["debit"]), tableur.monnaie(l["credit"]),
            tableur.monnaie(solde), tableur.texte(l["lettrage"]),
        )
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"grand_livre_{soc['code']}_{du}_{au}.xlsx")


@route("GET", "/api/export/journal")
def api_export_journal(ctx):
    """Export du livre-journal — pièce exigible en cas de contrôle fiscal."""
    societe_id = ctx.arg_int("societe")
    ex = exercice(ctx.arg_int("exercice"))
    soc = societe(societe_id)
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    conditions = ["e.societe_id = ?", "e.date >= ?", "e.date <= ?"]
    params: list = [societe_id, du, au]
    if ctx.arg("journal"):
        conditions.append("j.code = ?")
        params.append(ctx.arg("journal"))
    donnees = db.lignes(
        "SELECT e.date, e.numero, e.piece, e.libelle AS libelle_ecriture, j.code AS journal, "
        "  l.compte, l.libelle, l.debit, l.credit, l.lettrage, t.raison_sociale AS tiers, "
        "  c.intitule AS intitule_compte "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "JOIN lignes l ON l.ecriture_id = e.id "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        "LEFT JOIN comptes c ON c.numero = l.compte AND (c.societe_id IS NULL OR c.societe_id = e.societe_id) "
        f"WHERE {' AND '.join(conditions)} ORDER BY e.date, e.id, l.ordre",
        params,
    )
    classeur = tableur.Classeur()
    f = classeur.feuille("Livre-journal")
    f.titre(f"{soc['raison_sociale']} — Livre-journal")
    f.ajoute(tableur.texte(f"Du {util.date_fr(du)} au {util.date_fr(au)}"))
    f.vide()
    f.entetes("Date", "Journal", "N°", "Pièce", "Compte", "Intitulé", "Tiers",
              "Libellé", "Débit", "Crédit")
    f.largeurs_auto(12, 8, 14, 14, 12, 32, 26, 42, 15, 15)
    for l in donnees:
        f.ajoute(
            tableur.date_cel(l["date"]), tableur.texte(l["journal"]),
            tableur.texte(l["numero"]), tableur.texte(l["piece"]),
            tableur.texte(l["compte"]), tableur.texte(l["intitule_compte"]),
            tableur.texte(l["tiers"]), tableur.texte(l["libelle"]),
            tableur.monnaie(l["debit"]), tableur.monnaie(l["credit"]),
        )
    f.ajoute(
        tableur.texte("TOTAL", tableur.GRAS), *[tableur.texte("")] * 7,
        tableur.monnaie(sum(l["debit"] for l in donnees), total=True),
        tableur.monnaie(sum(l["credit"] for l in donnees), total=True),
    )
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"journal_{soc['code']}_{du}_{au}.xlsx")
