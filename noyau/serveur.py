"""Serveur HTTP local (bibliothèque standard uniquement).

Sert l'interface web et une API JSON. Écoute par défaut sur 127.0.0.1 :
l'application n'est jamais exposée au réseau sans action délibérée.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import base as db
from . import util
from .config import config, journalise, APPLICATION, VERSION

#: Ruptures de connexion normales quand le navigateur change de page.
#: Windows lève ConnectionAbortedError / ConnectionResetError là où les
#: systèmes Unix lèvent BrokenPipeError.
ERREURS_CONNEXION = (BrokenPipeError, ConnectionAbortedError,
                     ConnectionResetError)

#: Renseigné par app.py au démarrage. Permet à une route de demander l'arrêt
#: propre de l'application — la mise à jour en a besoin pour libérer les
#: fichiers de programme avant qu'ils ne soient remplacés.
demande_arret = None
#: Port réellement servi. L'outil de mise à jour s'en sert pour savoir
#: que l'application a bel et bien rendu la main.
port_courant = 0

#: Vrai quand l'arrêt en cours prépare une mise à jour. L'application saute
#: alors sa sauvegarde de fermeture : l'outil de mise à jour en fait une
#: immédiatement après, et deux archives du même dossier à la suite doublent
#: l'attente et l'espace disque sans rien protéger de plus.
arret_pour_maj = False

# ---------------------------------------------------------------------------
# Erreurs applicatives
# ---------------------------------------------------------------------------


class ErreurApplicative(Exception):
    """Erreur métier destinée à être affichée à l'utilisateur."""

    def __init__(self, message: str, code: int = 400, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class AccesRefuse(ErreurApplicative):
    def __init__(self, message="Authentification requise."):
        super().__init__(message, 401)


# ---------------------------------------------------------------------------
# Routeur
# ---------------------------------------------------------------------------

ROUTES: list[tuple[str, re.Pattern, callable, bool]] = []


def route(methode: str, motif: str, public: bool = False):
    """Décorateur d'enregistrement de route. `<id>` capture un segment."""
    regex = re.compile(
        "^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", motif) + "$"
    )

    def decorateur(fonction):
        ROUTES.append((methode.upper(), regex, fonction, public))
        return fonction

    return decorateur


class Contexte:
    """Ce que reçoit chaque gestionnaire de route."""

    def __init__(self, handler, methode, chemin, params, requete, corps):
        self.handler = handler
        self.methode = methode
        self.chemin = chemin
        self.params = params            # segments d'URL
        self.requete = requete          # query string
        self.corps = corps or {}        # corps JSON décodé
        self.utilisateur = None

    # -- lecture de paramètres ---------------------------------------------
    def arg(self, nom, defaut=None):
        valeurs = self.requete.get(nom)
        if not valeurs:
            return defaut
        return valeurs[0]

    def arg_int(self, nom, defaut=None):
        val = self.arg(nom)
        if val in (None, ""):
            return defaut
        try:
            return int(val)
        except ValueError:
            return defaut

    def champ(self, nom, defaut=None):
        return self.corps.get(nom, defaut)

    def champ_requis(self, nom):
        val = self.corps.get(nom)
        if val in (None, ""):
            raise ErreurApplicative(f"Le champ « {nom} » est obligatoire.")
        return val

    def montant(self, nom, defaut=0):
        return util.centimes(self.corps.get(nom, defaut))

    def taux(self, nom, defaut=0):
        val = self.corps.get(nom)
        return util.vers_taux(val) if val not in (None, "") else defaut

    def entier(self, nom, defaut=None):
        val = self.corps.get(nom)
        if val in (None, ""):
            return defaut
        try:
            return int(val)
        except (TypeError, ValueError):
            return defaut

    def booleen(self, nom, defaut=False):
        val = self.corps.get(nom, defaut)
        if isinstance(val, bool):
            return 1 if val else 0
        if isinstance(val, (int, float)):
            return 1 if val else 0
        return 1 if str(val).lower() in {"1", "true", "oui", "vrai", "on"} else 0

    def date(self, nom, defaut=None):
        return util.date_iso(self.corps.get(nom), defaut)

    def perimetre(self, defaut=None):
        """Périmètre déclaratif demandé : declare | hors_declaration | tous.

        Transmis par l'interface sur chaque requête. `defaut` sert aux écrans
        qui imposent leur propre périmètre (les déclarations fiscales, par
        exemple, ne portent que sur le déclaré).
        """
        return self.arg("perimetre") or self.corps.get("perimetre") or defaut

    @property
    def nom_utilisateur(self):
        return self.utilisateur["identifiant"] if self.utilisateur else None

    def exige_role(self, *roles):
        if not self.utilisateur:
            raise AccesRefuse()
        if self.utilisateur["role"] not in roles and self.utilisateur["role"] != "admin":
            raise ErreurApplicative("Vous n'avez pas les droits pour cette opération.", 403)

    def interdit_lecture_seule(self):
        if self.utilisateur and self.utilisateur["role"] == "lecture":
            raise ErreurApplicative(
                "Votre compte est en consultation seule.", 403)


# ---------------------------------------------------------------------------
# Mots de passe & sessions
# ---------------------------------------------------------------------------

ITERATIONS = 240_000


def hache_mot_de_passe(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS,
        base64.b64encode(sel).decode(),
        base64.b64encode(empreinte).decode(),
    )


def verifie_mot_de_passe(mot_de_passe: str, stocke: str) -> bool:
    try:
        algo, iterations, sel_b64, empreinte_b64 = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        sel = base64.b64decode(sel_b64)
        attendu = base64.b64decode(empreinte_b64)
    except (ValueError, binascii.Error):
        return False
    calcule = hashlib.pbkdf2_hmac(
        "sha256", mot_de_passe.encode("utf-8"), sel, int(iterations)
    )
    return hmac.compare_digest(calcule, attendu)


def cree_session(utilisateur_id: int) -> str:
    jeton = secrets.token_urlsafe(32)
    duree = int(config.get("duree_session_heures", 12))
    import datetime
    expire = (datetime.datetime.now() + datetime.timedelta(hours=duree)).isoformat(sep=" ")
    with db.transaction():
        db.execute(
            "INSERT INTO sessions (jeton, utilisateur_id, cree_le, expire_le) VALUES (?,?,?,?)",
            (jeton, utilisateur_id, util.maintenant(), expire),
        )
        db.execute("DELETE FROM sessions WHERE expire_le < ?", (util.maintenant(),))
        db.execute(
            "UPDATE utilisateurs SET derniere_visite = ? WHERE id = ?",
            (util.maintenant(), utilisateur_id),
        )
    return jeton


def utilisateur_de_session(jeton: str | None):
    if not jeton:
        return None
    return db.ligne(
        "SELECT u.* FROM sessions s JOIN utilisateurs u ON u.id = s.utilisateur_id "
        "WHERE s.jeton = ? AND s.expire_le > ? AND u.actif = 1",
        (jeton, util.maintenant()),
    )


def detruit_session(jeton: str | None):
    if jeton:
        with db.transaction():
            db.execute("DELETE FROM sessions WHERE jeton = ?", (jeton,))


# ---------------------------------------------------------------------------
# Handler HTTP
# ---------------------------------------------------------------------------

TAILLE_MAX_CORPS = 32 * 1024 * 1024   # 32 Mio (pièces jointes scannées)


def _message_route_absente(chemin: str) -> str:
    """« Ressource introuvable » n'apprend rien. Quand la cause est connue,
    on la dit.

    Le cas de loin le plus fréquent : une mise à jour a remplacé les fichiers
    sans que l'application se relance. L'interface, relue sur le disque à
    chaque requête, propose alors des écrans que le moteur en mémoire ne
    connaît pas encore."""
    try:
        from modules.systeme import version_sur_disque
        from noyau.config import VERSION
        disque = version_sur_disque()
        if disque and disque != VERSION:
            return (f"Cet écran appartient à la version {disque}, déjà "
                    f"installée sur le disque, mais l'application tourne "
                    f"encore sur la version {VERSION} : elle ne s'est pas "
                    f"relancée après la mise à jour. Fermez-la complètement "
                    f"et rouvrez-la.")
    except Exception:                                        # noqa: BLE001
        pass
    return "Ressource introuvable."


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = f"{APPLICATION}/{VERSION}"
    protocol_version = "HTTP/1.1"

    #: Ferme les connexions abandonnées (mise en veille, coupure du réseau
    #: privé) pour ne pas accumuler un fil par connexion fantôme. Volontairement
    #: plus long que le délai d'inactivité des navigateurs, qui ferment donc
    #: les leurs les premiers : une connexion n'est jamais coupée sous leurs
    #: pieds au moment où ils la réutilisent.
    timeout = 300

    # -- journalisation silencieuse ----------------------------------------
    def log_message(self, format, *args):   # noqa: A002
        if os.environ.get("CABINET_IMMO_DEBUG"):
            super().log_message(format, *args)

    # -- verbes ------------------------------------------------------------
    def do_GET(self):
        self._traite("GET")

    def do_POST(self):
        self._traite("POST")

    def do_PUT(self):
        self._traite("PUT")

    def do_PATCH(self):
        self._traite("PATCH")

    def do_DELETE(self):
        self._traite("DELETE")

    # -- traitement --------------------------------------------------------
    def _traite(self, methode):
        try:
            self._sert(methode)
        finally:
            # Chaque requête est servie dans son propre fil, et chaque fil
            # ouvre sa connexion SQLite. Sans cette fermeture, elles ne se
            # refermaient qu'au ramasse-miettes : des dizaines de connexions
            # ouvertes sur le fichier de base, et une restauration qui
            # remplace ce fichier tombait sur « disk I/O error ».
            db.ferme()

    def _sert(self, methode):
        try:
            url = urllib.parse.urlparse(self.path)
            chemin = urllib.parse.unquote(url.path)
            requete = urllib.parse.parse_qs(url.query)

            if not chemin.startswith("/api/"):
                return self._sert_fichier(chemin)

            corps, brut = self._lit_corps()
            contexte = Contexte(self, methode, chemin, {}, requete, corps)
            contexte.corps_brut = brut

            for methode_route, regex, fonction, public in ROUTES:
                if methode_route != methode:
                    continue
                correspondance = regex.match(chemin)
                if not correspondance:
                    continue
                contexte.params = correspondance.groupdict()
                if not public:
                    contexte.utilisateur = utilisateur_de_session(self._jeton())
                    if not contexte.utilisateur:
                        raise AccesRefuse()
                resultat = fonction(contexte)
                if isinstance(resultat, Reponse):
                    return resultat.envoie(self)
                return self._json(resultat if resultat is not None else {"ok": True})

            raise ErreurApplicative(_message_route_absente(chemin), 404)

        except ErreurApplicative as err:
            self._repond_erreur({"erreur": err.message, "details": err.details},
                                err.code)
        except ERREURS_CONNEXION:
            self.close_connection = True        # le navigateur est parti
        except Exception as err:                        # noqa: BLE001
            trace = traceback.format_exc()
            traceback.print_exc()
            journalise(f"{methode} {self.path}", str(err), trace)
            self._repond_erreur(
                {"erreur": "Erreur interne : " + str(err),
                 "trace": trace if os.environ.get("CABINET_IMMO_DEBUG") else None},
                500,
            )

    def _repond_erreur(self, donnees, code):
        """Envoie l'erreur — et ferme proprement si l'envoi échoue.

        Une exception qui s'échapperait d'ici laisserait la requête sans
        aucune réponse : le navigateur n'afficherait qu'un « NetworkError »,
        sans le message qui explique le problème.
        """
        try:
            self._json(donnees, code)
        except ERREURS_CONNEXION:
            self.close_connection = True
        except Exception:                               # noqa: BLE001
            journalise("reponse", "envoi de l'erreur impossible",
                       traceback.format_exc())
            self.close_connection = True

    def _jeton(self):
        entete = self.headers.get("Cookie", "")
        for morceau in entete.split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == "session_cabinet":
                return valeur
        autorisation = self.headers.get("Authorization", "")
        if autorisation.startswith("Bearer "):
            return autorisation[7:]
        return None

    def _lit_corps(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur <= 0:
            return {}, b""
        if longueur > TAILLE_MAX_CORPS:
            # Le corps n'est pas lu : la connexion ne peut plus servir à une
            # requête suivante, sans quoi les octets restants seraient pris
            # pour la requête d'après.
            self.close_connection = True
            raise ErreurApplicative("Fichier trop volumineux (32 Mio maximum).", 413)
        brut = self.rfile.read(longueur)
        type_contenu = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if type_contenu == "application/json":
            try:
                return json.loads(brut.decode("utf-8")), brut
            except (ValueError, UnicodeDecodeError) as err:
                raise ErreurApplicative(f"Corps de requête JSON invalide : {err}") from err
        if type_contenu == "application/x-www-form-urlencoded":
            donnees = urllib.parse.parse_qs(brut.decode("utf-8"))
            return {c: v[0] for c, v in donnees.items()}, brut
        return {}, brut

    # -- réponses ----------------------------------------------------------
    def _json(self, donnees, code=200, entetes=None):
        charge = json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(charge)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        self.wfile.write(charge)

    def _sert_fichier(self, chemin):
        racine = config.dossier_web
        if chemin in ("/", ""):
            chemin = "/index.html"

        # Fichiers du dossier de données exposés en lecture (pièces jointes, exports)
        if chemin.startswith("/fichiers/"):
            if not utilisateur_de_session(self._jeton()):
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            racine = config.dossier_donnees
            chemin = chemin[len("/fichiers"):]

        cible = (racine / chemin.lstrip("/")).resolve()
        try:
            cible.relative_to(racine.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if not cible.is_file():
            # SPA : toute route inconnue renvoie l'interface
            cible = config.dossier_web / "index.html"
            if not cible.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

        donnees = cible.read_bytes()
        type_mime = mimetypes.guess_type(str(cible))[0] or "application/octet-stream"
        if type_mime.startswith("text/") or type_mime in (
            "application/javascript", "application/json"
        ):
            type_mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(donnees)


class Reponse:
    """Réponse non-JSON (téléchargement de fichier, HTML imprimable…)."""

    def __init__(self, contenu: bytes, type_mime="application/octet-stream",
                 nom_fichier=None, code=200, entetes=None):
        self.contenu = contenu
        self.type_mime = type_mime
        self.nom_fichier = nom_fichier
        self.code = code
        self.entetes = entetes or {}

    def envoie(self, handler: Gestionnaire):
        handler.send_response(self.code)
        handler.send_header("Content-Type", self.type_mime)
        handler.send_header("Content-Length", str(len(self.contenu)))
        if self.nom_fichier:
            nom = urllib.parse.quote(self.nom_fichier)
            handler.send_header(
                "Content-Disposition", f"attachment; filename*=UTF-8''{nom}"
            )
        for nom, valeur in self.entetes.items():
            handler.send_header(nom, valeur)
        handler.end_headers()
        handler.wfile.write(self.contenu)


def reponse_cookie(donnees: dict, jeton: str, code=200) -> Reponse:
    charge = json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8")
    duree = int(config.get("duree_session_heures", 12)) * 3600
    return Reponse(
        charge,
        "application/json; charset=utf-8",
        code=code,
        entetes={
            "Set-Cookie": f"session_cabinet={jeton}; Path=/; HttpOnly; SameSite=Strict; Max-Age={duree}",
            "Cache-Control": "no-store",
        },
    )


def reponse_deconnexion(donnees: dict) -> Reponse:
    charge = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    return Reponse(
        charge,
        "application/json; charset=utf-8",
        entetes={"Set-Cookie": "session_cabinet=; Path=/; HttpOnly; Max-Age=0"},
    )


def demarre(hote: str, port: int) -> ThreadingHTTPServer:
    global port_courant
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    port_courant = serveur.server_address[1]
    serveur.daemon_threads = True
    return serveur
