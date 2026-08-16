"""Résumés envoyés au dirigeant, sur son téléphone.

Deux canaux, au choix et cumulables :

* **Telegram** — gratuit et instantané. Le destinataire installe Telegram,
  ouvre le bot de l'entreprise et envoie le code d'appairage affiché dans
  l'application. Il reçoit ensuite le résumé automatiquement, et peut en
  demander un à tout moment en écrivant « situation ».
* **Courriel** — via le serveur SMTP de votre choix.

Aucun service tiers payant, aucune donnée hébergée ailleurs : c'est le poste
du comptable qui envoie le message, à la demande ou à heure fixe.
"""

from __future__ import annotations

import json
import secrets
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from noyau import base as db
from noyau import util
from noyau.serveur import ErreurApplicative, route
from modules import comptabilite as compta

TELEGRAM = "https://api.telegram.org/bot{token}/{methode}"
DELAI_RESEAU = 25

_arret = threading.Event()


# ---------------------------------------------------------------------------
# Construction du résumé
# ---------------------------------------------------------------------------

def construit_resume(societe_id: int, perimetre: str | None = None,
                     jour: str | None = None) -> dict:
    """Chiffres clés du jour, tels que les attend un dirigeant."""
    soc = compta.societe(societe_id)
    jour = jour or util.aujourdhui()
    ex = db.ligne(
        "SELECT * FROM exercices WHERE societe_id = ? AND date_debut <= ? "
        "AND date_fin >= ?", (societe_id, jour, jour)
    ) or db.ligne("SELECT * FROM exercices WHERE societe_id = ? "
                  "ORDER BY date_debut DESC LIMIT 1", (societe_id,))
    if not ex:
        raise ErreurApplicative("Aucun exercice pour ce dossier.")

    debut, fin = ex["date_debut"], ex["date_fin"]

    def solde(prefixe, du=None, au=None):
        return compta.solde_compte(societe_id, prefixe, du or debut, au or fin,
                                   perimetre=perimetre)

    banque = solde("512")["solde"] + solde("515")["solde"]
    caisse = solde("53")["solde"]
    produits = solde("7")
    charges = solde("6")

    fragment, params = compta.clause_perimetre(perimetre)
    encaissements_jour = int(db.valeur(
        "SELECT COALESCE(SUM(l.debit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND e.date = ? "
        "AND (l.compte LIKE '51%' OR l.compte LIKE '53%')" + fragment,
        [societe_id, jour] + params, 0))
    decaissements_jour = int(db.valeur(
        "SELECT COALESCE(SUM(l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND e.date = ? "
        "AND (l.compte LIKE '51%' OR l.compte LIKE '53%')" + fragment,
        [societe_id, jour] + params, 0))

    resume = {
        "societe": soc["raison_sociale"],
        "jour": jour,
        "exercice": ex["libelle"],
        "perimetre": perimetre or "tous",
        "tresorerie": banque + caisse,
        "banque": banque,
        "caisse": caisse,
        "encaissements_jour": encaissements_jour,
        "decaissements_jour": decaissements_jour,
        "chiffre_affaires": solde("70")["credit"] - solde("70")["debit"],
        "resultat": (produits["credit"] - produits["debit"])
                    - (charges["debit"] - charges["credit"]),
        "creances_clients": solde("411")["solde"],
        "du_aux_proprietaires": -solde("4671")["solde"],
    }

    # Loyers impayés
    impayes = db.lignes(
        "SELECT q.numero, q.periode, q.total, q.montant_encaisse, q.date_echeance, "
        "       l.raison_sociale AS locataire, bi.designation AS bien "
        "FROM quittances q JOIN baux b ON b.id = q.bail_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id "
        "LEFT JOIN biens bi ON bi.id = b.bien_id "
        "WHERE q.societe_id = ? AND q.statut IN ('a_encaisser','impayee') "
        "AND q.date_echeance <= ? ORDER BY q.date_echeance", (societe_id, jour))
    resume["impayes"] = [dict(i) for i in impayes[:10]]
    resume["total_impayes"] = sum(i["total"] - i["montant_encaisse"] for i in impayes)
    resume["nb_impayes"] = len(impayes)

    # Échéances VSP exigibles ou en retard
    echeances = db.lignes(
        "SELECT ev.libelle, ev.montant, ev.montant_regle, ev.date_prevue, "
        "       c.numero AS contrat, lo.numero AS lot, t.raison_sociale AS acquereur "
        "FROM echeances_vsp ev JOIN contrats_vsp c ON c.id = ev.contrat_id "
        "JOIN lots lo ON lo.id = c.lot_id JOIN tiers t ON t.id = c.acquereur_id "
        "WHERE c.societe_id = ? AND ev.statut IN ('exigible','partielle') "
        "AND (ev.date_prevue IS NULL OR ev.date_prevue <= ?) "
        "ORDER BY ev.date_prevue LIMIT 10", (societe_id, jour))
    resume["echeances_vsp"] = [dict(e) for e in echeances]
    resume["total_echeances_vsp"] = sum(e["montant"] - e["montant_regle"] for e in echeances)

    # Programmes en cours
    resume["programmes"] = db.lignes(
        "SELECT p.code, p.intitule, p.avancement, "
        "  (SELECT COALESCE(SUM(montant_encaisse),0) FROM contrats_vsp WHERE programme_id = p.id) AS encaisse, "
        "  (SELECT COALESCE(SUM(prix_total - montant_encaisse),0) FROM contrats_vsp "
        "   WHERE programme_id = p.id AND statut = 'en_cours') AS reste, "
        "  (SELECT COUNT(*) FROM lots WHERE programme_id = p.id AND statut = 'disponible') AS disponibles "
        "FROM programmes p WHERE p.societe_id = ? AND p.statut IN ('en_cours','lancement','acheve')",
        (societe_id,))

    # Prochaine obligation déclarative
    resume["prochaine_obligation"] = db.ligne(
        "SELECT libelle, date_limite FROM obligations WHERE societe_id = ? "
        "AND statut = 'a_faire' AND date_limite >= ? ORDER BY date_limite LIMIT 1",
        (societe_id, jour))
    resume["obligations_en_retard"] = db.valeur(
        "SELECT COUNT(*) FROM obligations WHERE societe_id = ? AND statut = 'a_faire' "
        "AND date_limite < ?", (societe_id, jour), 0)

    return resume


def resume_en_texte(r: dict, format_html: bool = True) -> str:
    """Met le résumé en forme pour un téléphone : court, chiffré, hiérarchisé."""
    gras = (lambda t: f"<b>{t}</b>") if format_html else (lambda t: t.upper())
    # `formate_montant` ajoute déjà la devise : on la retire pour la placer nous-mêmes.
    m = lambda cts: util.formate_montant(cts, "")            # noqa: E731
    lignes = [
        gras(r["societe"]),
        f"Situation au {util.date_fr(r['jour'])}",
        "",
        gras("💰 Trésorerie"),
        f"  Total : {m(r['tresorerie'])} DA",
        f"  Banque {m(r['banque'])} · Caisse {m(r['caisse'])}",
    ]
    if r["encaissements_jour"] or r["decaissements_jour"]:
        lignes.append(f"  Aujourd'hui : +{m(r['encaissements_jour'])}"
                      f" / −{m(r['decaissements_jour'])}")

    lignes += [
        "",
        gras("📊 Exercice " + r["exercice"]),
        f"  Chiffre d'affaires : {m(r['chiffre_affaires'])} DA",
        f"  Résultat : {m(r['resultat'])} DA",
        f"  Créances clients : {m(r['creances_clients'])} DA",
    ]
    if r["du_aux_proprietaires"]:
        lignes.append("  Dû aux propriétaires : "
                      f"{m(r['du_aux_proprietaires'])} DA")

    if r["nb_impayes"]:
        lignes += ["", gras(f"⚠️ Loyers impayés — {r['nb_impayes']}"),
                   f"  Total : {m(r['total_impayes'])} DA"]
        for i in r["impayes"][:5]:
            reste = i["total"] - i["montant_encaisse"]
            lignes.append(f"  • {i['locataire'] or '—'} — {m(reste)} DA"
                          f" ({util.libelle_periode(i['periode'])})")

    if r["echeances_vsp"]:
        lignes += ["", gras(f"📅 Échéances VSP exigibles — "
                            f"{m(r['total_echeances_vsp'])} DA")]
        for e in r["echeances_vsp"][:5]:
            reste = e["montant"] - e["montant_regle"]
            lignes.append(f"  • {e['acquereur']} lot {e['lot']} — "
                          f"{m(reste)} DA")

    if r["programmes"]:
        lignes += ["", gras("🏗️ Programmes")]
        for p in r["programmes"]:
            lignes.append(
                f"  • {p['intitule']} — {util.taux_pourcent(p['avancement']):g} % "
                f"· encaissé {m(p['encaisse'])} DA "
                f"· reste {m(p['reste'])} DA "
                f"· {p['disponibles']} lot(s) libre(s)")

    if r["prochaine_obligation"]:
        lignes += ["", gras("🗓️ Prochaine échéance fiscale"),
                   f"  {r['prochaine_obligation']['libelle']} — "
                   f"{util.date_fr(r['prochaine_obligation']['date_limite'])}"]
    if r["obligations_en_retard"]:
        lignes.append(f"  ⚠️ {r['obligations_en_retard']} déclaration(s) en retard")

    if r["perimetre"] != "declare":
        lignes += ["", "ℹ️ Chiffres réels (déclaré + hors déclaration)."]
    else:
        lignes += ["", "ℹ️ Périmètre déclaré uniquement."]

    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------

def _parametre(cle: str, defaut=None):
    return db.valeur("SELECT valeur FROM meta WHERE cle = ?", (cle,), defaut)


def _enregistre_parametre(cle: str, valeur: str) -> None:
    db.execute("INSERT INTO meta (cle, valeur) VALUES (?,?) "
               "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
               (cle, str(valeur)))


def appelle_telegram(methode: str, donnees: dict, token: str | None = None) -> dict:
    token = token or _parametre("telegram_token")
    if not token:
        raise ErreurApplicative(
            "Aucun jeton Telegram enregistré. Créez un bot avec @BotFather sur "
            "Telegram, puis collez le jeton dans Paramètres > Notifications."
        )
    url = TELEGRAM.format(token=token, methode=methode)
    charge = urllib.parse.urlencode(donnees).encode()
    try:
        with urllib.request.urlopen(url, charge, timeout=DELAI_RESEAU) as reponse:
            return json.loads(reponse.read().decode())
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:200]
        raise ErreurApplicative(f"Telegram a refusé la requête : {detail}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise ErreurApplicative(
            f"Impossible de joindre Telegram : {err}. Vérifiez la connexion Internet."
        ) from err


def envoie_telegram(destinataire: str, texte: str) -> dict:
    return appelle_telegram("sendMessage", {
        "chat_id": destinataire, "text": texte, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })


def envoie_courriel(destinataire: str, sujet: str, texte: str) -> None:
    hote = _parametre("smtp_hote")
    if not hote:
        raise ErreurApplicative(
            "Serveur d'envoi de courriel non configuré (Paramètres > Notifications)."
        )
    port = int(_parametre("smtp_port", 587) or 587)
    utilisateur = _parametre("smtp_utilisateur")
    mot_de_passe = _parametre("smtp_mot_de_passe")
    expediteur = _parametre("smtp_expediteur") or utilisateur or "cabinet-immo@local"

    message = EmailMessage()
    message["From"] = expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(texte)

    contexte = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(hote, port, timeout=DELAI_RESEAU, context=contexte) as serveur:
            if utilisateur:
                serveur.login(utilisateur, mot_de_passe or "")
            serveur.send_message(message)
    else:
        with smtplib.SMTP(hote, port, timeout=DELAI_RESEAU) as serveur:
            serveur.starttls(context=contexte)
            if utilisateur:
                serveur.login(utilisateur, mot_de_passe or "")
            serveur.send_message(message)


def diffuse(societe_id: int, canaux=None, motif: str = "manuel") -> dict:
    """Envoie le résumé sur tous les canaux actifs du dossier."""
    canaux = canaux if canaux is not None else db.lignes(
        "SELECT * FROM canaux_notification WHERE societe_id = ? AND actif = 1",
        (societe_id,))
    resultats = []
    for canal in canaux:
        if not canal["destinataire"]:
            resultats.append({"canal": canal["libelle"], "ok": False,
                              "erreur": "Destinataire non appairé."})
            continue
        try:
            resume = construit_resume(societe_id, canal["perimetre"])
            if canal["type"] == "telegram":
                envoie_telegram(canal["destinataire"], resume_en_texte(resume, True))
            else:
                envoie_courriel(
                    canal["destinataire"],
                    f"{resume['societe']} — situation au {util.date_fr(resume['jour'])}",
                    resume_en_texte(resume, False))
            with db.transaction():
                db.modifie("canaux_notification", canal["id"],
                           {"dernier_envoi": util.maintenant()})
            resultats.append({"canal": canal["libelle"], "ok": True})
        except Exception as err:                                  # noqa: BLE001
            resultats.append({"canal": canal["libelle"], "ok": False,
                              "erreur": str(err)})
    db.trace("diffusion_resume", "notification", societe_id,
             {"motif": motif, "resultats": resultats})
    return {"resultats": resultats,
            "envoyes": sum(1 for r in resultats if r["ok"])}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@route("GET", "/api/notifications")
def api_canaux(ctx):
    societe_id = ctx.arg_int("societe")
    canaux = db.lignes(
        "SELECT * FROM canaux_notification WHERE societe_id = ? ORDER BY id",
        (societe_id,))
    return {
        "canaux": canaux,
        "telegram_configure": bool(_parametre("telegram_token")),
        "smtp_configure": bool(_parametre("smtp_hote")),
        "smtp": {
            "hote": _parametre("smtp_hote", ""),
            "port": _parametre("smtp_port", "587"),
            "utilisateur": _parametre("smtp_utilisateur", ""),
            "expediteur": _parametre("smtp_expediteur", ""),
        },
    }


@route("PUT", "/api/notifications/reglages")
def api_reglages(ctx):
    """Jeton du bot Telegram et serveur d'envoi de courriel."""
    ctx.exige_role("admin", "comptable")
    with db.transaction():
        for cle, champ in [
            ("telegram_token", "telegram_token"),
            ("smtp_hote", "smtp_hote"), ("smtp_port", "smtp_port"),
            ("smtp_utilisateur", "smtp_utilisateur"),
            ("smtp_expediteur", "smtp_expediteur"),
        ]:
            valeur = ctx.champ(champ)
            if valeur is not None:
                _enregistre_parametre(cle, valeur)
        if ctx.champ("smtp_mot_de_passe"):
            _enregistre_parametre("smtp_mot_de_passe", ctx.champ("smtp_mot_de_passe"))
        db.trace("modification", "notifications", None, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("POST", "/api/notifications")
def api_cree_canal(ctx):
    ctx.exige_role("admin", "comptable")
    type_canal = ctx.champ("type", "telegram")
    if type_canal not in ("telegram", "email"):
        raise ErreurApplicative("Canal inconnu.")
    with db.transaction():
        identifiant = db.insere("canaux_notification", {
            "societe_id": ctx.entier("societe_id"),
            "type": type_canal,
            "libelle": ctx.champ_requis("libelle"),
            "destinataire": util.nettoie(ctx.champ("destinataire")),
            "code_appairage": (secrets.token_hex(3).upper()
                               if type_canal == "telegram" else None),
            "frequence": ctx.champ("frequence", "quotidien"),
            "heure": ctx.champ("heure", "08:00"),
            "perimetre": compta.normalise_perimetre(ctx.champ("perimetre"), "tous")
                         if ctx.champ("perimetre") != "tous" else "tous",
            "actif": ctx.booleen("actif", True),
            "cree_le": util.maintenant(),
        })
    canal = db.ligne("SELECT * FROM canaux_notification WHERE id = ?", (identifiant,))
    return {"id": identifiant, "code_appairage": canal["code_appairage"]}


@route("PUT", "/api/notifications/<id>")
def api_modifie_canal(ctx):
    ctx.exige_role("admin", "comptable")
    with db.transaction():
        db.modifie("canaux_notification", int(ctx.params["id"]), {
            "libelle": ctx.champ_requis("libelle"),
            "destinataire": util.nettoie(ctx.champ("destinataire")),
            "frequence": ctx.champ("frequence", "quotidien"),
            "heure": ctx.champ("heure", "08:00"),
            "perimetre": ctx.champ("perimetre", "tous"),
            "actif": ctx.booleen("actif", True),
        })
    return {"ok": True}


@route("DELETE", "/api/notifications/<id>")
def api_supprime_canal(ctx):
    ctx.exige_role("admin", "comptable")
    with db.transaction():
        db.supprime("canaux_notification", int(ctx.params["id"]))
    return {"ok": True}


@route("GET", "/api/notifications/apercu")
def api_apercu(ctx):
    societe_id = ctx.arg_int("societe")
    resume = construit_resume(societe_id, ctx.perimetre())
    return {"resume": resume, "texte": resume_en_texte(resume, False)}


@route("POST", "/api/notifications/envoyer")
def api_envoie(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    canal_id = ctx.entier("canal_id")
    canaux = db.lignes("SELECT * FROM canaux_notification WHERE id = ?",
                       (canal_id,)) if canal_id else None
    return diffuse(societe_id, canaux, motif="manuel")


# ---------------------------------------------------------------------------
# Réception : appairage et demandes à la volée
# ---------------------------------------------------------------------------

MOTS_CLES = {
    "situation": "resume", "resume": "resume", "résumé": "resume",
    "point": "resume", "/start": "aide", "aide": "aide", "/aide": "aide",
    "tresorerie": "tresorerie", "trésorerie": "tresorerie", "caisse": "tresorerie",
    "loyers": "loyers", "impayes": "loyers", "impayés": "loyers",
}


def _traite_message(chat_id: str, texte: str) -> str:
    """Répond à un message reçu. Un chat non appairé ne reçoit aucune donnée."""
    texte = (texte or "").strip().lower()

    # Appairage par code
    code = texte.replace("/start", "").strip().upper()
    if code:
        canal = db.ligne(
            "SELECT * FROM canaux_notification WHERE code_appairage = ? "
            "AND (destinataire IS NULL OR destinataire = '')", (code,))
        if canal:
            with db.transaction():
                db.modifie("canaux_notification", canal["id"],
                           {"destinataire": str(chat_id)})
                db.trace("appairage", "notification", canal["id"], str(chat_id))
            return ("✅ Appairage réussi. Vous recevrez la situation "
                    "automatiquement.\n\nÉcrivez « situation » à tout moment "
                    "pour un point immédiat.")

    canal = db.ligne("SELECT * FROM canaux_notification WHERE destinataire = ? "
                     "AND actif = 1", (str(chat_id),))
    if not canal:
        return ("Ce numéro n'est pas encore autorisé.\n"
                "Envoyez le code d'appairage affiché dans l'application "
                "(Paramètres > Notifications).")

    action = MOTS_CLES.get(texte, "aide")
    if action == "aide":
        return ("Commandes disponibles :\n"
                "• <b>situation</b> — le point complet\n"
                "• <b>trésorerie</b> — banque et caisse\n"
                "• <b>loyers</b> — les impayés")

    resume = construit_resume(canal["societe_id"], canal["perimetre"])
    m = lambda cts: util.formate_montant(cts, "")            # noqa: E731
    if action == "tresorerie":
        return (f"<b>{resume['societe']}</b>\n"
                f"Trésorerie au {util.date_fr(resume['jour'])}\n\n"
                f"Banque : {m(resume['banque'])} DA\n"
                f"Caisse : {m(resume['caisse'])} DA\n"
                f"<b>Total : {m(resume['tresorerie'])} DA</b>\n\n"
                f"Aujourd'hui : +{m(resume['encaissements_jour'])}"
                f" / −{m(resume['decaissements_jour'])}")
    if action == "loyers":
        if not resume["nb_impayes"]:
            return "✅ Aucun loyer impayé."
        lignes = [f"<b>Loyers impayés — {resume['nb_impayes']}</b>",
                  f"Total : {m(resume['total_impayes'])} DA", ""]
        for i in resume["impayes"]:
            reste = i["total"] - i["montant_encaisse"]
            lignes.append(f"• {i['locataire'] or '—'} — {m(reste)} DA"
                          f" — échéance {util.date_fr(i['date_echeance'])}")
        return "\n".join(lignes)
    return resume_en_texte(resume, True)


def boucle_reception() -> None:
    """Écoute les messages entrants (thread de fond, arrêté avec l'application)."""
    decalage = int(_parametre("telegram_decalage", 0) or 0)
    while not _arret.is_set():
        token = _parametre("telegram_token")
        if not token:
            _arret.wait(30)
            continue
        try:
            reponse = appelle_telegram(
                "getUpdates", {"offset": decalage + 1, "timeout": 20}, token)
            for maj in reponse.get("result", []):
                decalage = max(decalage, maj["update_id"])
                message = maj.get("message") or {}
                chat = (message.get("chat") or {}).get("id")
                if not chat:
                    continue
                try:
                    reponse_texte = _traite_message(chat, message.get("text", ""))
                    envoie_telegram(chat, reponse_texte)
                except Exception as err:                          # noqa: BLE001
                    print(f"[telegram] réponse impossible : {err}")
            with db.transaction():
                _enregistre_parametre("telegram_decalage", decalage)
        except ErreurApplicative as err:
            print(f"[telegram] {err.message}")
            _arret.wait(60)
        except Exception as err:                                  # noqa: BLE001
            print(f"[telegram] {err}")
            _arret.wait(60)
        finally:
            db.ferme()


def boucle_planification() -> None:
    """Envoie les résumés à l'heure configurée, une fois par jour."""
    while not _arret.is_set():
        _arret.wait(60)
        if _arret.is_set():
            break
        try:
            maintenant = time.strftime("%H:%M")
            aujourdhui = util.aujourdhui()
            canaux = db.lignes(
                "SELECT * FROM canaux_notification WHERE actif = 1 "
                "AND frequence IN ('quotidien','hebdomadaire') AND heure = ?",
                (maintenant,))
            for canal in canaux:
                if (canal["dernier_envoi"] or "")[:10] == aujourdhui:
                    continue
                if canal["frequence"] == "hebdomadaire" and \
                        time.strftime("%w") != "0":
                    continue
                diffuse(canal["societe_id"], [canal], motif="planifie")
        except Exception as err:                                  # noqa: BLE001
            print(f"[résumés] planification : {err}")
        finally:
            db.ferme()


def demarre_taches_de_fond() -> list[threading.Thread]:
    """Lance l'écoute Telegram et le planificateur."""
    _arret.clear()
    fils = []
    for cible, nom in ((boucle_reception, "telegram"),
                       (boucle_planification, "resumes")):
        fil = threading.Thread(target=cible, name=nom, daemon=True)
        fil.start()
        fils.append(fil)
    return fils


def arrete_taches_de_fond() -> None:
    _arret.set()
