"""Signalement d'un incident, sans dépendre d'un canal de support.

Les deux pannes réelles rencontrées jusqu'ici ont été diagnostiquées à partir
de **photos d'écran prises au téléphone**. Le journal des incidents existait,
mais il fallait que quelqu'un aille le chercher sur le poste.

Ici, l'utilisateur clique sur « Signaler ce problème » et obtient un rapport
qu'il **voit avant de l'envoyer**, par le moyen qu'il veut : le copier pour le
coller dans un message, l'enregistrer pour le joindre, ou l'envoyer directement
si un canal Telegram ou courriel est déjà configuré.

**Le rapport ne contient aucune donnée comptable** : ni montant, ni nom de
tiers, ni raison sociale. Les chemins de fichiers sont masqués, car ils
portent le nom de la session Windows. Il ne reste que le contexte technique.
"""

from __future__ import annotations

import platform
import re
import sys

from noyau import base as db
from noyau import util
from noyau.config import config, APPLICATION, VERSION, RACINE
from noyau.serveur import ErreurApplicative, route, Reponse

#: Nombre de lignes de journal jointes. Assez pour comprendre, assez court
#: pour tenir dans un message.
LIGNES_JOURNAL = 80


def masque_chemins(texte: str) -> str:
    """Retire les chemins absolus : ils contiennent le nom de l'utilisateur."""
    if not texte:
        return texte
    from pathlib import Path
    remplacements = [
        (str(config.dossier_donnees), "<donnees>"),
        (str(RACINE), "<application>"),
        (str(Path.home()), "<utilisateur>"),
    ]
    for chemin, marque in remplacements:
        if chemin and chemin not in ("/", ""):
            texte = texte.replace(chemin, marque)
            texte = texte.replace(chemin.replace("\\", "/"), marque)
    # Ce qui resterait d'un chemin Windows personnel.
    texte = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+", "<utilisateur>", texte)
    texte = re.sub(r"/home/[^/\s]+", "<utilisateur>", texte)
    return texte


def lignes_journal(combien: int = LIGNES_JOURNAL) -> list[str]:
    fichier = config.journal_incidents
    if not fichier.exists():
        return []
    try:
        brut = fichier.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return [f"Journal illisible : {err}"]
    return [masque_chemins(l) for l in brut.splitlines()[-combien:]]


def compte_incidents() -> int:
    """Nombre d'entrées du journal, pour signaler qu'il y a quelque chose à dire."""
    fichier = config.journal_incidents
    if not fichier.exists():
        return 0
    try:
        return sum(1 for l in fichier.read_text(encoding="utf-8",
                                                errors="replace").splitlines()
                   if l.startswith("["))
    except OSError:
        return 0


def construit_rapport(ecran: str = "", message: str = "") -> dict:
    """Le contexte technique, et rien d'autre."""
    return {
        "application": APPLICATION,
        "version": VERSION,
        "date": util.maintenant(),
        "systeme": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "ecran": masque_chemins(str(ecran or "")[:200]),
        "message": masque_chemins(str(message or "")[:500]),
        "nb_incidents": compte_incidents(),
        "journal": lignes_journal(),
    }


def rapport_en_texte(rapport: dict) -> str:
    """Mise en forme lisible, à coller dans un message ou à joindre."""
    lignes = [
        f"{rapport['application']} — signalement d'incident",
        "=" * 52,
        f"Version    : {rapport['version']}",
        f"Système    : {rapport['systeme']}",
        f"Python     : {rapport['python']}",
        f"Date       : {rapport['date']}",
    ]
    if rapport["ecran"]:
        lignes.append(f"Écran      : {rapport['ecran']}")
    if rapport["message"]:
        lignes.append(f"Message    : {rapport['message']}")
    lignes += [
        f"Incidents  : {rapport['nb_incidents']} au journal",
        "",
        "Aucune donnée comptable ne figure dans ce rapport.",
        "",
        "Dernières lignes du journal",
        "-" * 52,
    ]
    lignes += rapport["journal"] or ["(journal vide)"]
    return "\n".join(lignes)


def canaux_disponibles(societe_id=None) -> list[dict]:
    """Canaux déjà configurés et appairés : on n'en crée aucun pour l'occasion."""
    conditions = ["actif = 1", "destinataire IS NOT NULL", "destinataire <> ''"]
    params: list = []
    if societe_id:
        conditions.append("societe_id = ?")
        params.append(societe_id)
    return db.lignes(
        "SELECT id, type, libelle, destinataire FROM canaux_notification "
        f"WHERE {' AND '.join(conditions)} ORDER BY libelle", params)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@route("GET", "/api/incidents/rapport")
def api_rapport(ctx):
    """Ce qui sera transmis — montré avant tout envoi."""
    ctx.exige_role("admin", "comptable")
    rapport = construit_rapport(ctx.arg("ecran", ""), ctx.arg("message", ""))
    rapport["texte"] = rapport_en_texte(rapport)
    rapport["canaux"] = [{"id": c["id"], "type": c["type"],
                          "libelle": c["libelle"]}
                         for c in canaux_disponibles(ctx.arg_int("societe"))]
    return rapport


@route("GET", "/api/incidents/fichier")
def api_fichier(ctx):
    """Le même rapport, en fichier texte à joindre à un message."""
    ctx.exige_role("admin", "comptable")
    rapport = construit_rapport(ctx.arg("ecran", ""), ctx.arg("message", ""))
    horodatage = util.maintenant()[:10]
    return Reponse(rapport_en_texte(rapport).encode("utf-8"),
                   "text/plain; charset=utf-8",
                   nom_fichier=f"incident-{horodatage}.txt")


@route("POST", "/api/incidents/envoyer")
def api_envoie(ctx):
    """Envoie par un canal déjà configuré. Aucun canal, aucun envoi."""
    ctx.exige_role("admin", "comptable")
    societe_id = ctx.entier("societe_id")
    canaux = canaux_disponibles(societe_id)
    if not canaux:
        raise ErreurApplicative(
            "Aucun canal n'est configuré pour l'envoi. Copiez le rapport ou "
            "enregistrez-le, puis transmettez-le comme vous voulez. Vous pouvez "
            "aussi configurer Telegram ou le courriel dans "
            "Paramètres > Notifications.")

    from modules import rapports as mod_rapports
    rapport = construit_rapport(ctx.champ("ecran", ""), ctx.champ("message", ""))
    texte = rapport_en_texte(rapport)

    resultats = []
    for canal in canaux:
        try:
            if canal["type"] == "telegram":
                mod_rapports.envoie_telegram(canal["destinataire"], texte)
            else:
                mod_rapports.envoie_courriel(
                    canal["destinataire"],
                    f"{APPLICATION} {VERSION} — signalement d'incident", texte)
            resultats.append({"canal": canal["libelle"], "ok": True})
        except Exception as err:                              # noqa: BLE001
            resultats.append({"canal": canal["libelle"], "ok": False,
                              "erreur": str(err)})

    db.trace("signalement", "incident", None,
             {"canaux": len(resultats)}, ctx.nom_utilisateur)
    envoyes = sum(1 for r in resultats if r["ok"])
    if not envoyes:
        raise ErreurApplicative(
            "L'envoi a échoué : " + " · ".join(
                r.get("erreur", "") for r in resultats if not r["ok"]),
            details=resultats)
    return {"envoyes": envoyes, "resultats": resultats}
