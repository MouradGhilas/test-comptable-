#!/usr/bin/env python3
"""Mise a jour : elle doit aboutir, ou se voir.

Deux pannes ont deja atteint le poste du comptable par ce chemin, et les
deux etaient silencieuses : une premiere fois l'outil mourait a sa premiere
ligne sur un accent, une seconde fois les fichiers etaient remplaces sans
que l'application se relance -- interface neuve sur moteur ancien, ecrans
qui existent et routes qui repondent « ressource introuvable ».

Cet outil rejoue le chemin complet sur une installation jetable :

  1. une copie de l'application, rabaissee a une version anterieure ;
  2. le paquet de la version en cours, depose par l'application elle-meme ;
  3. l'application doit revenir seule, sur la bonne version, donnees intactes.

Puis il provoque volontairement l'etat mixte et verifie que l'application
le dit -- au lieu de laisser chercher.

Il verifie enfin le chemin inverse, celui qui manquait : revenir a une
version anterieure. Deux cas a ne pas confondre -- la version visee sait
ouvrir la base telle qu'elle est (seul le programme recule), ou elle ne le
sait pas (les donnees reculent avec, ce qui se confirme et se chiffre).

    python3 outils/test_mise_a_jour.py
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
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from noyau.config import VERSION                                # noqa: E402

#: Version de depart de l'installation d'essai : anterieure a tout.
VERSION_ANCIENNE = "0.0.1"

ok = fails = 0
anomalies = []


def sortie_utf8():
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def v(nom, cond, detail=""):
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


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Installation:
    """Une copie jetable de l'application, sur son propre dossier."""

    def __init__(self, version_depart):
        self.racine = Path(tempfile.mkdtemp(prefix="maj_app_"))
        self.donnees = Path(tempfile.mkdtemp(prefix="maj_donnees_"))
        subprocess.run(
            "tar -c --exclude=.git --exclude=donnees --exclude=__pycache__ . "
            f"| tar -x -C {self.racine}", shell=True, cwd=RACINE, check=True)
        self.ecrit_version(version_depart)
        subprocess.run([sys.executable, "outils/donnees_demonstration.py",
                        "--donnees", str(self.donnees)],
                       cwd=self.racine, check=True, capture_output=True)
        self.port = port_libre()
        self.proc = None
        self.pot = http.cookiejar.CookieJar()
        self.ouvre = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.pot))

    def ecrit_version(self, version):
        cfg = self.racine / "noyau" / "config.py"
        lignes = []
        for ligne in cfg.read_text(encoding="utf-8").splitlines(keepends=True):
            if ligne.startswith("VERSION"):
                ligne = f'VERSION = "{version}"\n'
            lignes.append(ligne)
        cfg.write_text("".join(lignes), encoding="utf-8")

    def demarre(self):
        self.proc = subprocess.Popen(
            [sys.executable, "app.py", "--donnees", str(self.donnees),
             "--port", str(self.port), "--sans-navigateur"],
            cwd=self.racine, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        for _ in range(30):
            if self.repond():
                return True
            time.sleep(1)
        return False

    def repond(self):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/etat", timeout=2)
            return True
        except Exception:                                       # noqa: BLE001
            return False

    def appel(self, chemin, corps=None):
        data = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{chemin}", data=data,
            headers={"Content-Type": "application/json"})
        with self.ouvre.open(req, timeout=120) as r:
            brut = r.read().decode()
            return json.loads(brut) if brut else {}

    def erreur_sur(self, chemin, corps):
        """Le message de refus d'un appel qui doit echouer."""
        try:
            self.appel(chemin, corps)
            return None
        except urllib.error.HTTPError as err:
            try:
                return json.loads(err.read().decode()).get("erreur", "")
            except ValueError:
                return f"code {err.code}"

    def erreur_de(self, chemin):
        try:
            self.appel(chemin)
            return None
        except urllib.error.HTTPError as err:
            try:
                return json.loads(err.read().decode()).get("erreur", "")
            except ValueError:
                return f"code {err.code}"

    def sql(self, requete):
        c = sqlite3.connect(str(self.donnees / "comptabilite.db"))
        c.row_factory = sqlite3.Row
        r = [dict(x) for x in c.execute(requete).fetchall()]
        c.close()
        return r

    def ferme(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        subprocess.run(["pkill", "-f", str(self.racine)], capture_output=True)
        shutil.rmtree(self.racine, ignore_errors=True)
        shutil.rmtree(self.donnees, ignore_errors=True)


def paquet_de_la_version_courante(dossier):
    subprocess.run([sys.executable, "outils/faire_paquet.py", "--vers", dossier],
                   cwd=RACINE, check=True, capture_output=True)
    return Path(dossier) / f"maj-{VERSION}.zip"


def paquet_modifie(source, dossier, version, schema=None):
    """Le meme paquet, qui se declare a une autre version -- et parfois a un
    schema de base anterieur. De quoi rejouer un retour en arriere sans avoir
    a garder sous la main les archives de toutes les versions passees."""
    import re
    import zipfile
    cible = Path(dossier) / f"paquet-{version}.zip"
    with zipfile.ZipFile(source) as entree, \
            zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as sortie:
        for info in entree.infolist():
            octets = entree.read(info.filename)
            if info.filename.endswith("noyau/config.py"):
                octets = re.sub(rb'^VERSION\s*=\s*"[^"]+"',
                                f'VERSION = "{version}"'.encode(),
                                octets, count=1, flags=re.M)
            if schema is not None and info.filename.endswith("noyau/base.py"):
                octets = re.sub(rb"^VERSION_SCHEMA\s*=\s*\d+",
                                f"VERSION_SCHEMA = {schema}".encode(),
                                octets, count=1, flags=re.M)
            sortie.writestr(info, octets)
    return cible


def sauvegarde_fabriquee(app, version, schema):
    """Une sauvegarde telle que la version `version` en aurait laissee.

    Le comptable qui veut revenir a une version d'il y a trois mois a, lui,
    de vraies sauvegardes de cette epoque. Ici on en fabrique une : copie de
    la base, ramenee au schema d'alors, avec le manifeste qui va avec.
    """
    import zipfile
    cible = app.donnees / "sauvegardes" / f"sauvegarde_20250101_000000_essai.zip"
    cible.parent.mkdir(parents=True, exist_ok=True)
    copie = Path(tempfile.mkdtemp(prefix="maj_base_")) / "comptabilite.db"
    source = sqlite3.connect(str(app.donnees / "comptabilite.db"))
    destination = sqlite3.connect(str(copie))
    source.backup(destination)
    destination.execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES "
                        "('version_schema', ?)", (str(schema),))
    # Une sauvegarde identique a la base actuelle ne prouverait rien : on la
    # rend reconnaissable, et on lui retire trois ecritures pour que la perte
    # annoncee soit mesurable.
    destination.execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES "
                        "('essai_retour', 'oui')")
    destination.execute(
        "DELETE FROM lignes WHERE ecriture_id IN "
        "(SELECT id FROM ecritures ORDER BY id DESC LIMIT 3)")
    destination.execute(
        "DELETE FROM ecritures WHERE id IN "
        "(SELECT id FROM ecritures ORDER BY id DESC LIMIT 3)")
    destination.commit()
    destination.close()
    source.close()
    with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(copie, "comptabilite.db")
        archive.writestr("manifeste.json", json.dumps({
            "application": "Cabinet Immo", "version": version,
            "date": "2025-01-01 00:00:00", "motif": "essai", "societes": [],
        }, ensure_ascii=False))
    return cible


def attend_version(app, attendue, tours=90):
    """L'application se ferme et se rouvre : on attend qu'elle reponde."""
    for _ in range(tours):
        time.sleep(2)
        try:
            etat = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{app.port}/api/etat", timeout=3).read().decode())
        except Exception:                                       # noqa: BLE001
            continue
        if etat.get("version") == attendue:
            return etat
    # Muette, une mise a jour ratee ne laisse rien a lire : c'est justement
    # ce que l'outil consigne. On le montre plutot que de dire « pas revenue ».
    journal = app.donnees / "maj" / "journal-maj.txt"
    if journal.is_file():
        print("  --- journal de l'outil ---")
        for ligne in journal.read_text(encoding="utf-8", errors="replace"
                                       ).splitlines()[-40:]:
            print("  | " + ligne)
    return None


def executer():
    paquets = tempfile.mkdtemp(prefix="maj_paquet_")
    archive = paquet_de_la_version_courante(paquets)
    app = Installation(VERSION_ANCIENNE)
    try:
        titre("1. Une installation ancienne, avec ses données")
        v("l'application démarre", app.demarre())
        app.appel("/api/connexion",
                  {"identifiant": "demo", "mot_de_passe": "demo1234"})
        etat = app.appel("/api/etat")
        v(f"elle se déclare en {VERSION_ANCIENNE}",
          etat["version"] == VERSION_ANCIENNE, etat["version"])
        v("elle ne réclame pas de redémarrage",
          not etat.get("redemarrage_requis"), etat)
        avant = app.sql("SELECT COUNT(*) n, COALESCE(SUM(debit),0) d "
                        "FROM lignes")[0]
        print(f"  {avant['n']} lignes, {avant['d'] / 100:,.2f} de débit"
              .replace(",", " "))

        titre("2. Le paquet est déposé dans l'application")
        contenu = base64.b64encode(archive.read_bytes()).decode()
        analyse = app.appel("/api/maj/analyse", {"contenu": contenu})
        v(f"le paquet est reconnu comme la {VERSION}",
          analyse.get("version") == VERSION, analyse)
        v("… et comme plus récent", not analyse.get("identique"), analyse)
        app.appel("/api/maj/appliquer", {"contenu": contenu})

        titre("3. L'application revient seule, sur la bonne version")
        revenue = False
        for _ in range(90):
            time.sleep(2)
            try:
                etat = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{app.port}/api/etat",
                    timeout=3).read().decode())
            except Exception:                                   # noqa: BLE001
                continue
            if etat.get("version") == VERSION:
                revenue = True
                break
        v(f"elle répond en {VERSION}", revenue,
          "toujours pas revenue après trois minutes")
        v("… et sans réclamer de redémarrage",
          revenue and not etat.get("redemarrage_requis"), etat)

        apres = app.sql("SELECT COUNT(*) n, COALESCE(SUM(debit),0) d "
                        "FROM lignes")[0]
        v("aucune ligne comptable n'a bougé", apres["n"] == avant["n"],
          f"{apres['n']} au lieu de {avant['n']}")
        v("le total débit est identique au centime", apres["d"] == avant["d"],
          f"{apres['d']} au lieu de {avant['d']}")
        v("le code installé est celui de la nouvelle version",
          f'VERSION = "{VERSION}"' in
          (app.racine / "noyau" / "config.py").read_text(encoding="utf-8"))

        titre("4. Les fichiers ajoutés par la version le sont vraiment")
        # Une mise à jour qui ne saurait qu'écraser laisserait les nouveaux
        # modules absents, et leurs écrans en « ressource introuvable ».
        manquants = [f for f in ("modules/sante.py", "modules/annuelles.py",
                                 "modules/recherche.py", "web/aide.js")
                     if not (app.racine / f).exists()]
        v("les nouveaux fichiers sont installés", not manquants, manquants)
        v("… et référencés par la page",
          "aide.js" in (app.racine / "web" / "index.html")
          .read_text(encoding="utf-8"))

        titre("5. Un état mixte, provoqué exprès, doit se voir")
        # Exactement ce qu'une mise à jour interrompue laisse derrière elle :
        # les fichiers neufs, le moteur ancien encore en mémoire.
        app.ecrit_version("9.9.9")
        etat = app.appel("/api/etat")
        v("l'application s'aperçoit qu'elle est dépassée",
          etat.get("redemarrage_requis") is True, etat)
        v("… en nommant la version présente sur le disque",
          etat.get("version_disque") == "9.9.9", etat.get("version_disque"))
        message = app.erreur_de("/api/route-qui-nexiste-pas")
        v("une route absente explique la cause au lieu de « introuvable »",
          "ne s'est pas relancée" in (message or ""), message)
        v("… en nommant les deux versions",
          "9.9.9" in (message or "") and VERSION in (message or ""), message)

        # L'état mixte a été provoqué dans le fichier : on le referme, sinon
        # tout ce qui suit se lirait à travers ce faux numéro de version.
        app.ecrit_version(VERSION)

        titre("6. Les versions installées restent disponibles sur le poste")
        # Un paquet reçu par messagerie n'existe qu'une fois. S'il n'est pas
        # gardé, la version qu'il installe devient la seule possible.
        biblio = app.appel("/api/maj/versions")
        presentes = {x["version"]: x for x in biblio.get("versions", [])}
        v("la version installée est rangée sur le poste", VERSION in presentes,
          sorted(presentes))
        v("… et signalée comme celle en cours",
          presentes.get(VERSION, {}).get("installee") is True,
          presentes.get(VERSION))
        v("celle d'avant la mise à jour a été gardée elle aussi",
          VERSION_ANCIENNE in presentes, sorted(presentes))
        v("… et proposée comme un retour",
          presentes.get(VERSION_ANCIENNE, {}).get("sens") == "retour",
          presentes.get(VERSION_ANCIENNE))

        titre("7. Revenir en arrière, quand la version sait lire la base")
        recul = paquet_modifie(archive, paquets, "1.0.0")
        contenu_recul = base64.b64encode(recul.read_bytes()).decode()
        analyse = app.appel("/api/maj/analyse", {"contenu": contenu_recul})
        situation = analyse.get("situation", {})
        v("le paquet antérieur n'est plus refusé d'emblée",
          situation.get("action") == "revenir", situation)
        v("… la comptabilité n'a pas à bouger",
          analyse.get("donnees_compatibles") is True, analyse.get("schema"))
        v("… et le retour demande une confirmation",
          situation.get("confirmation") == "REVENIR", situation)
        refus = app.erreur_sur("/api/maj/appliquer", {"contenu": contenu_recul})
        v("sans ce mot, rien ne se passe", "REVENIR" in (refus or ""), refus)
        v("… et la version en place n'a pas bougé",
          app.appel("/api/etat")["version"] == VERSION)

        app.appel("/api/maj/appliquer",
                  {"contenu": contenu_recul, "confirmation": "REVENIR"})
        etat = attend_version(app, "1.0.0")
        v("l'application revient en 1.0.0", etat is not None,
          "toujours pas revenue après trois minutes")
        recul_lignes = app.sql("SELECT COUNT(*) n, COALESCE(SUM(debit),0) d "
                               "FROM lignes")[0]
        v("aucune écriture n'a été perdue au passage",
          recul_lignes["n"] == avant["n"] and recul_lignes["d"] == avant["d"],
          f"{recul_lignes} au lieu de {avant}")

        titre("8. Revenir plus loin, quand la base a pris de l'avance")
        # Le cas réel : la base a été migrée, la version visée ne connaît pas
        # sa structure. Le programme seul ne suffit pas — les données doivent
        # revenir avec, et ce qui a été saisi depuis est perdu. Ça se dit.
        ecritures_avant = app.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
        schema_base = app.sql("SELECT valeur FROM meta WHERE cle = "
                              "'version_schema'")[0]["valeur"]
        vieux_schema = int(schema_base) - 1
        sauvegarde = sauvegarde_fabriquee(app, "0.8.0", vieux_schema)
        vieux = paquet_modifie(archive, paquets, "0.9.0", schema=vieux_schema)
        contenu_vieux = base64.b64encode(vieux.read_bytes()).decode()
        analyse = app.appel("/api/maj/analyse", {"contenu": contenu_vieux})
        situation = analyse.get("situation", {})
        v("l'application voit que la base est trop récente pour ce paquet",
          analyse.get("donnees_compatibles") is False,
          f"schéma paquet {analyse.get('schema')} / base {analyse.get('schema_base')}")
        v("… et propose de remettre les données d'alors",
          situation.get("action") == "revenir_avec_donnees", situation)
        noms = [x["nom"] for x in analyse.get("sauvegardes", [])]
        v("… en listant les sauvegardes qu'elle saura relire",
          sauvegarde.name in noms, noms)
        refus = app.erreur_sur("/api/maj/appliquer",
                               {"contenu": contenu_vieux, "confirmation": "REVENIR"})
        v("sans choisir de sauvegarde, le retour est refusé",
          "sauvegarde" in (refus or "").lower(), refus)

        app.appel("/api/maj/appliquer", {"contenu": contenu_vieux,
                                         "confirmation": "REVENIR",
                                         "sauvegarde": sauvegarde.name})
        etat = attend_version(app, "0.9.0")
        v("l'application revient en 0.9.0", etat is not None,
          "toujours pas revenue après trois minutes")
        marque = app.sql("SELECT valeur FROM meta WHERE cle = 'essai_retour'")
        v("les données sont bien celles de la sauvegarde choisie",
          marque and marque[0]["valeur"] == "oui", marque)
        restant = app.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"]
        v("… donc les écritures saisies depuis ne sont plus là",
          restant == ecritures_avant - 3, f"{restant} au lieu de "
          f"{ecritures_avant - 3}")
        filets = [f["nom"] for f in app.appel("/api/sauvegardes")["sauvegardes"]]
        v("l'état d'avant le retour reste récupérable",
          any("avant_retour" in n for n in filets), filets)

        titre("9. Et repartir en avant, comme si de rien n'était")
        app.appel("/api/maj/appliquer", {"contenu": contenu})
        etat = attend_version(app, VERSION)
        v(f"l'application repart en {VERSION}", etat is not None,
          "toujours pas revenue après trois minutes")
        v("… en remontant la base au schéma courant",
          app.sql("SELECT valeur FROM meta WHERE cle = 'version_schema'")[0]
          ["valeur"] == schema_base, "schéma non remonté")
        v("… sans perdre les données remises en place",
          app.sql("SELECT COUNT(*) n FROM ecritures")[0]["n"] == restant)

        titre("10. L'application sait se fermer depuis l'écran")
        app.appel("/api/systeme/arreter", {})
        time.sleep(2.5)
        v("le bouton du bandeau la ferme bien", not app.repond())
    finally:
        app.ferme()
        shutil.rmtree(paquets, ignore_errors=True)


if __name__ == "__main__":
    sortie_utf8()
    print("\n\033[1m=== MISE A JOUR — CABINET IMMO ===\033[0m")
    code = 0
    try:
        executer()
    except Exception:                                           # noqa: BLE001
        import traceback
        traceback.print_exc()
        fails += 1
        anomalies.append(("Exception non rattrapée", ""))
    print(f"\n{'=' * 70}")
    print(f"MISE A JOUR : {ok} ok, {fails} anomalie(s)")
    for nom, detail in anomalies:
        print(f"  - {nom}\n      {detail}")
    print("=" * 70)
    sys.exit(1 if fails else 0)
